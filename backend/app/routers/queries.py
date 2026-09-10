"""Saved queries and parameterised templates."""

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.db import get_session
from app.models import Endpoint, SavedQuery
from app.odata.builder import BuildError, QuerySpec, build_url
from app.odata.client import UpstreamError, execute
from app.routers.query import (
    build_or_400,
    collect_columns,
    record_run,
    upstream_http_error,
)
from app.schemas import (
    QueryPreview,
    QueryResponse,
    RunSavedQueryRequest,
    SavedQueryCreate,
    SavedQueryRead,
    SavedQueryUpdate,
)
from app.templating import QueryParam, TemplateError, find_placeholders, resolve_spec

router = APIRouter(prefix="/api/queries", tags=["queries"])


def _to_read(row: SavedQuery) -> SavedQueryRead:
    return SavedQueryRead(
        id=row.id,
        name=row.name,
        description=row.description,
        tags=row.tags,
        is_builtin=row.is_builtin,
        endpoint_id=row.endpoint_id,
        entity_set=row.entity_set,
        mode=row.mode,
        # A template's stored spec may hold placeholders in int fields (e.g. top), so
        # it is parsed leniently and only validated once parameters are resolved.
        spec=_safe_spec(row.spec_json),
        raw_query=row.raw_query,
        params=[QueryParam(**item) for item in json.loads(row.params_json or "[]")],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _safe_spec(spec_json: str) -> QuerySpec:
    """Parse a stored spec, tolerating placeholders that are not yet valid values."""
    data = json.loads(spec_json or "{}")
    try:
        return QuerySpec(**data)
    except Exception:
        cleaned = {
            key: value
            for key, value in data.items()
            if not (isinstance(value, str) and "{{" in value and key in ("top", "skip"))
        }
        try:
            return QuerySpec(**cleaned)
        except Exception:
            return QuerySpec()


def get_query_or_404(query_id: int, session: Session) -> SavedQuery:
    row = session.get(SavedQuery, query_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No saved query with id {query_id}.")
    return row


@router.get("", response_model=list[SavedQueryRead])
def list_queries(
    endpoint_id: Optional[int] = None, session: Session = Depends(get_session)
):
    """All saved queries. `endpoint_id` narrows to that endpoint plus the
    endpoint-agnostic templates, which is what the workspace shows."""
    statement = select(SavedQuery)
    if endpoint_id is not None:
        statement = statement.where(
            (SavedQuery.endpoint_id == endpoint_id) | (SavedQuery.endpoint_id.is_(None))
        )
    rows = session.exec(statement.order_by(SavedQuery.name)).all()
    return [_to_read(row) for row in rows]


@router.post("", response_model=SavedQueryRead, status_code=status.HTTP_201_CREATED)
def create_query(payload: SavedQueryCreate, session: Session = Depends(get_session)):
    params = payload.params
    if not params:
        params = _infer_params(payload)
    row = SavedQuery(
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
        endpoint_id=payload.endpoint_id,
        entity_set=payload.entity_set,
        mode=payload.mode,
        spec_json=payload.spec.model_dump_json(exclude_none=True),
        raw_query=payload.raw_query,
        params_json=json.dumps([param.model_dump() for param in params]),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_read(row)


def _infer_params(payload) -> list[QueryParam]:
    """Turn any {{placeholder}} the user typed into a declared parameter.

    Saves them having to define parameters twice; the types can be adjusted afterwards.
    """
    spec_json = payload.spec.model_dump_json() if payload.spec else "{}"
    names = find_placeholders(spec_json, payload.raw_query)
    return [QueryParam(name=name, label=name.replace("_", " ").title()) for name in names]


@router.get("/{query_id}", response_model=SavedQueryRead)
def read_query(query_id: int, session: Session = Depends(get_session)):
    return _to_read(get_query_or_404(query_id, session))


@router.patch("/{query_id}", response_model=SavedQueryRead)
def update_query(
    query_id: int, payload: SavedQueryUpdate, session: Session = Depends(get_session)
):
    row = get_query_or_404(query_id, session)
    changes = payload.model_dump(exclude_unset=True)

    if "spec" in changes and payload.spec is not None:
        row.spec_json = payload.spec.model_dump_json(exclude_none=True)
        changes.pop("spec")
    if "params" in changes and payload.params is not None:
        row.params_json = json.dumps([param.model_dump() for param in payload.params])
        changes.pop("params")

    for field, value in changes.items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)

    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_read(row)


@router.delete("/{query_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_query(query_id: int, session: Session = Depends(get_session)):
    session.delete(get_query_or_404(query_id, session))
    session.commit()
    return None


def _resolve(row: SavedQuery, endpoint: Endpoint, payload: RunSavedQueryRequest) -> QuerySpec:
    params = [QueryParam(**item) for item in json.loads(row.params_json or "[]")]
    spec_dict = json.loads(row.spec_json or "{}")
    if row.mode == "raw":
        spec_dict["raw_query"] = row.raw_query
    if row.entity_set:
        spec_dict.setdefault("entity_set", row.entity_set)

    try:
        resolved = resolve_spec(spec_dict, params, payload.params, endpoint.odata_version)
    except TemplateError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"message": exc.message, "missing": exc.missing},
        ) from exc

    # Paging from the UI overrides whatever the template stored.
    if payload.top is not None:
        resolved["top"] = payload.top
    if payload.skip is not None:
        resolved["skip"] = payload.skip

    try:
        return QuerySpec(**resolved)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Resolved query is not valid: {exc}"
        ) from exc


def _endpoint_for(row: SavedQuery, payload: RunSavedQueryRequest, session: Session) -> Endpoint:
    endpoint_id = payload.endpoint_id or row.endpoint_id
    if endpoint_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This template is not tied to an endpoint; choose one to run it against.",
        )
    endpoint = session.get(Endpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No endpoint with id {endpoint_id}.")
    return endpoint


@router.post("/{query_id}/preview", response_model=QueryPreview)
def preview_saved_query(
    query_id: int, payload: RunSavedQueryRequest, session: Session = Depends(get_session)
):
    row = get_query_or_404(query_id, session)
    endpoint = _endpoint_for(row, payload, session)
    spec = _resolve(row, endpoint, payload)
    return QueryPreview(url=build_or_400(endpoint, spec))


@router.post("/{query_id}/run", response_model=QueryResponse)
async def run_saved_query(
    query_id: int, payload: RunSavedQueryRequest, session: Session = Depends(get_session)
):
    row = get_query_or_404(query_id, session)
    endpoint = _endpoint_for(row, payload, session)
    spec = _resolve(row, endpoint, payload)
    url = build_or_400(endpoint, spec)

    try:
        result = await execute(endpoint, url)
    except UpstreamError as exc:
        record_run(session, endpoint, spec, url, error=exc.message,
                   saved_query_id=row.id, saved_query_name=row.name)
        raise upstream_http_error(exc) from exc

    record_run(session, endpoint, spec, url, result=result,
               saved_query_id=row.id, saved_query_name=row.name)
    return QueryResponse(
        url=result.url,
        status_code=result.status_code,
        duration_ms=result.duration_ms,
        count=result.count,
        total_count=result.total_count,
        has_next=bool(result.next_link),
        rows=result.rows,
        columns=collect_columns(result.rows),
    )
