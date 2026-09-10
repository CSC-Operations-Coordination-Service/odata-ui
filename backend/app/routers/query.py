"""Building, previewing and executing ad-hoc queries."""

import csv
import io
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session
from app.models import Endpoint, QueryRun
from app.odata.builder import BuildError, QuerySpec, build_filter, build_url
from app.odata.client import QueryResult, UpstreamError, execute
from app.schemas import QueryPreview, QueryRequest, QueryResponse

router = APIRouter(prefix="/api/query", tags=["query"])


def get_endpoint_or_404(endpoint_id: int, session: Session) -> Endpoint:
    endpoint = session.get(Endpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No endpoint with id {endpoint_id}.")
    return endpoint


def build_or_400(endpoint: Endpoint, spec: QuerySpec) -> str:
    try:
        return build_url(endpoint, spec, max_page_size=get_settings().max_page_size)
    except BuildError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


def upstream_http_error(exc: UpstreamError) -> HTTPException:
    """Surface what the service actually said, rather than a bare 500."""
    return HTTPException(
        status.HTTP_502_BAD_GATEWAY,
        {
            "message": exc.message,
            "url": exc.url,
            "upstream_status": exc.status_code,
            "upstream_body": exc.body,
        },
    )


def collect_columns(rows: list) -> list[str]:
    """Union of the keys across rows, in first-seen order, so the table has stable
    columns even when the service omits nulls."""
    columns: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            for key in row:
                if key not in columns and not key.startswith("@odata."):
                    columns.append(key)
    return columns


def record_run(
    session: Session,
    endpoint: Endpoint,
    spec: QuerySpec,
    url: str,
    result: Optional[QueryResult] = None,
    error: Optional[str] = None,
    saved_query_id: Optional[int] = None,
    saved_query_name: str = "",
) -> None:
    """Append to the history, then trim it to the configured limit."""
    session.add(
        QueryRun(
            endpoint_id=endpoint.id,
            endpoint_name=endpoint.name,
            saved_query_id=saved_query_id,
            saved_query_name=saved_query_name,
            url=url,
            status_code=result.status_code if result else None,
            duration_ms=result.duration_ms if result else None,
            result_count=result.count if result else None,
            error=error,
            spec_json=spec.model_dump_json(),
        )
    )
    session.commit()

    limit = get_settings().history_limit
    ids = session.exec(select(QueryRun.id).order_by(QueryRun.id.desc()).offset(limit)).all()
    if ids:
        for old_id in ids:
            old = session.get(QueryRun, old_id)
            if old is not None:
                session.delete(old)
        session.commit()


@router.post("/preview", response_model=QueryPreview)
def preview(payload: QueryRequest, session: Session = Depends(get_session)):
    """Build the URL without calling the service; drives the live URL bar."""
    endpoint = get_endpoint_or_404(payload.endpoint_id, session)
    url = build_or_400(endpoint, payload.spec)
    try:
        filter_text = build_filter(payload.spec, endpoint.odata_version)
    except BuildError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return QueryPreview(url=url, filter=filter_text)


@router.post("/run", response_model=QueryResponse)
async def run(payload: QueryRequest, session: Session = Depends(get_session)):
    endpoint = get_endpoint_or_404(payload.endpoint_id, session)
    url = build_or_400(endpoint, payload.spec)
    try:
        result = await execute(endpoint, url)
    except UpstreamError as exc:
        record_run(session, endpoint, payload.spec, url, error=exc.message,
                   saved_query_id=payload.saved_query_id)
        raise upstream_http_error(exc) from exc

    record_run(session, endpoint, payload.spec, url, result=result,
               saved_query_id=payload.saved_query_id)
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


def _flatten(value) -> str:
    """Render a nested value for a CSV cell."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


@router.post("/export")
async def export(
    payload: QueryRequest, format: str = "csv", session: Session = Depends(get_session)
):
    """Run the query and return the rows as a downloadable file."""
    if format not in ("csv", "json"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "format must be csv or json.")

    endpoint = get_endpoint_or_404(payload.endpoint_id, session)
    url = build_or_400(endpoint, payload.spec)
    try:
        result = await execute(endpoint, url)
    except UpstreamError as exc:
        raise upstream_http_error(exc) from exc

    entity = payload.spec.entity_set or endpoint.default_entity_set or "results"
    filename = f"{endpoint.name}-{entity}".replace(" ", "_").replace("/", "_")

    if format == "json":
        return Response(
            content=json.dumps(result.rows, indent=2, ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}.json"'},
        )

    columns = collect_columns(result.rows)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in result.rows:
        if isinstance(row, dict):
            writer.writerow({key: _flatten(row.get(key)) for key in columns})
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
    )
