"""Recent query runs."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, delete, select

from app.db import get_session
from app.models import QueryRun
from app.odata.builder import QuerySpec
from app.schemas import QueryRunRead

router = APIRouter(prefix="/api/history", tags=["history"])


def _to_read(row: QueryRun) -> QueryRunRead:
    try:
        spec = QuerySpec(**json.loads(row.spec_json or "{}"))
    except Exception:
        spec = QuerySpec()
    return QueryRunRead(
        id=row.id,
        endpoint_id=row.endpoint_id,
        endpoint_name=row.endpoint_name,
        saved_query_id=row.saved_query_id,
        saved_query_name=row.saved_query_name,
        url=row.url,
        status_code=row.status_code,
        duration_ms=row.duration_ms,
        result_count=row.result_count,
        error=row.error,
        spec=spec,
        created_at=row.created_at,
    )


@router.get("", response_model=list[QueryRunRead])
def list_history(
    limit: int = Query(default=100, ge=1, le=500),
    endpoint_id: int = Query(default=None),
    session: Session = Depends(get_session),
):
    statement = select(QueryRun)
    if endpoint_id is not None:
        statement = statement.where(QueryRun.endpoint_id == endpoint_id)
    rows = session.exec(statement.order_by(QueryRun.id.desc()).limit(limit)).all()
    return [_to_read(row) for row in rows]


@router.get("/{run_id}", response_model=QueryRunRead)
def read_run(run_id: int, session: Session = Depends(get_session)):
    row = session.get(QueryRun, run_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No run with id {run_id}.")
    return _to_read(row)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_history(session: Session = Depends(get_session)):
    session.exec(delete(QueryRun))
    session.commit()
    return None
