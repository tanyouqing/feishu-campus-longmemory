from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from starlette import status

from feishu_campus_longmemory.config import Settings
from feishu_campus_longmemory.errors import AppError
from feishu_campus_longmemory.proactive.dispatcher import ReminderDispatcher, ReminderSender
from feishu_campus_longmemory.proactive.types import ReminderDispatchResult
from feishu_campus_longmemory.security import require_ingest_token

router = APIRouter(tags=["proactive"])


class ProactiveTriggerRequest(BaseModel):
    job_id: str | None = None
    limit: int = Field(default=10, ge=1, le=100)


class ProactiveTriggerResult(BaseModel):
    job_id: str
    status: str
    work_event_id: str | None = None
    message_id: str | None = None
    next_run_at: datetime | None = None
    error: str | None = None


class ProactiveTriggerResponse(BaseModel):
    processed: int
    results: list[ProactiveTriggerResult]


@router.post("/proactive/trigger", response_model=ProactiveTriggerResponse)
def trigger_proactive_reminders(
    payload: ProactiveTriggerRequest,
    request: Request,
    _: None = Depends(require_ingest_token),
) -> ProactiveTriggerResponse:
    settings: Settings = request.app.state.settings
    sender = _sender_for_request(request, settings)
    results = ReminderDispatcher(request.app.state.db_engine, settings, sender=sender).trigger_due(
        job_id=payload.job_id,
        limit=payload.limit,
    )
    return ProactiveTriggerResponse(
        processed=sum(1 for result in results if result.status != "skipped"),
        results=[_response_item(result) for result in results],
    )


def _sender_for_request(request: Request, settings: Settings) -> ReminderSender | None:
    sender = getattr(request.app.state, "reminder_sender", None)
    if sender is not None:
        return sender
    if not settings.feishu_app_id or not settings.feishu_app_secret:
        raise AppError(
            "feishu_sender_not_configured",
            "LONGMEMORY_FEISHU_APP_ID and LONGMEMORY_FEISHU_APP_SECRET must be configured before sending reminders; confirm the Feishu app has im:message:send_as_bot permission",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return None


def _response_item(result: ReminderDispatchResult) -> ProactiveTriggerResult:
    return ProactiveTriggerResult(
        job_id=result.job_id,
        status=result.status,
        work_event_id=result.work_event_id,
        message_id=result.message_id,
        next_run_at=result.next_run_at,
        error=result.error,
    )
