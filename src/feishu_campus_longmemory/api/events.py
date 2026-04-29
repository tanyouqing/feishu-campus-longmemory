from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from starlette import status

from feishu_campus_longmemory.api.schemas import IngestResponse, WorkEventResponse
from feishu_campus_longmemory.errors import AppError
from feishu_campus_longmemory.events.normalize import normalize_openclaw_event
from feishu_campus_longmemory.events.store import EvidenceStore
from feishu_campus_longmemory.memory.extractor import ExplicitMemoryExtractor
from feishu_campus_longmemory.memory.store import MemoryStore
from feishu_campus_longmemory.security import require_ingest_token

router = APIRouter(tags=["events"])


@router.post("/events/ingest", response_model=IngestResponse)
def ingest_openclaw_event(
    payload: dict[str, Any],
    request: Request,
    _: None = Depends(require_ingest_token),
) -> IngestResponse:
    try:
        event = normalize_openclaw_event(payload)
    except ValueError as exc:
        raise AppError(
            code="invalid_event_payload",
            message=str(exc),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        ) from exc

    result = EvidenceStore(request.app.state.db_engine).insert_work_event(event)
    if result.created:
        ExplicitMemoryExtractor().process_event(result.event, MemoryStore(request.app.state.db_engine))
    return IngestResponse(
        event_id=result.event.event_id,
        created=result.created,
        event=WorkEventResponse(**result.event.__dict__),
    )


@router.get("/events", response_model=list[WorkEventResponse])
def list_events(
    request: Request,
    _: None = Depends(require_ingest_token),
    user_id: str | None = None,
    source: str | None = None,
    event_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> list[WorkEventResponse]:
    events = EvidenceStore(request.app.state.db_engine).list_work_events(
        user_id=user_id,
        source=source,
        event_type=event_type,
        limit=limit,
    )
    return [WorkEventResponse(**event.__dict__) for event in events]


@router.get("/events/{event_id}", response_model=WorkEventResponse)
def get_event(
    event_id: str,
    request: Request,
    _: None = Depends(require_ingest_token),
) -> WorkEventResponse:
    event = EvidenceStore(request.app.state.db_engine).get_work_event(event_id)
    if event is None:
        raise AppError(
            code="event_not_found",
            message="Work event not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return WorkEventResponse(**event.__dict__)
