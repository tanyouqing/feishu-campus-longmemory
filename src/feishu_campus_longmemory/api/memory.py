from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from starlette import status

from feishu_campus_longmemory.errors import AppError
from feishu_campus_longmemory.events.normalize import normalize_openclaw_event
from feishu_campus_longmemory.events.store import EvidenceStore
from feishu_campus_longmemory.memory.extractor import detect_work_type
from feishu_campus_longmemory.memory.reminder import DEFAULT_TIMEZONE, ReminderParser
from feishu_campus_longmemory.memory.retriever import MemoryRetriever
from feishu_campus_longmemory.memory.store import MemoryStore
from feishu_campus_longmemory.memory.types import MemoryWrite, ReminderSchedule
from feishu_campus_longmemory.security import require_ingest_token

router = APIRouter(tags=["memory"])


class MemoryWriteRequest(BaseModel):
    user_id: str
    memory_category: str = "WorkPreferenceMemory"
    work_type: str = "general"
    content_json: dict[str, Any]
    source_channel: str = "openclaw"
    source_signal_type: str = "explicit_statement"
    confidence: float = Field(default=0.85, ge=0, le=1)
    status: str = "active"
    evidence_event_ids: list[str] = Field(default_factory=list)
    evidence_event: dict[str, Any] | None = None


class MemoryUpdateRequest(BaseModel):
    memory_id: str
    content_json: dict[str, Any] | None = None
    work_type: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: str | None = None


class MemoryForgetRequest(BaseModel):
    memory_id: str | None = None
    user_id: str | None = None
    query: str | None = None
    memory_category: str | None = None
    work_type: str | None = None
    evidence_event_ids: list[str] = Field(default_factory=list)
    evidence_event: dict[str, Any] | None = None


class ReminderScheduleRequest(BaseModel):
    user_id: str
    reminder_text: str
    work_type: str | None = None
    timezone: str = DEFAULT_TIMEZONE
    schedule_type: str | None = None
    next_run_at: datetime | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    evidence_event_ids: list[str] = Field(default_factory=list)
    evidence_event: dict[str, Any] | None = None


class MemorySearchRequest(BaseModel):
    user_id: str
    query: str
    work_type: str | None = None
    memory_categories: list[str] | None = None
    limit: int = Field(default=5, ge=1, le=20)
    include_evidence_count: bool = True


class MemoryWriteResponse(BaseModel):
    memory_id: str
    created: bool
    replaced_memory_ids: list[str]
    evidence_event_ids: list[str]
    reminder_jobs: list[dict[str, Any]]
    memory: dict[str, Any]


class MemoryForgetResponse(BaseModel):
    deleted_memory_ids: list[str]


class MemorySearchItem(BaseModel):
    memory_id: str
    memory_category: str
    work_type: str
    summary: str
    score: float
    evidence_count: int | None
    updated_at: datetime


class MemorySearchResponse(BaseModel):
    detected_work_type: str
    empty: bool
    context_pack: str
    memories: list[MemorySearchItem]


@router.post("/memory/write", response_model=MemoryWriteResponse)
def write_memory(
    payload: MemoryWriteRequest,
    request: Request,
    _: None = Depends(require_ingest_token),
) -> MemoryWriteResponse:
    evidence_event_ids = _resolve_evidence_event_ids(request, payload.evidence_event_ids, payload.evidence_event)
    try:
        result = MemoryStore(request.app.state.db_engine).write_memory(
            MemoryWrite(
                user_id=payload.user_id,
                memory_category=payload.memory_category,
                work_type=payload.work_type,
                content_json=payload.content_json,
                source_channel=payload.source_channel,
                source_signal_type=payload.source_signal_type,
                confidence=payload.confidence,
                status=payload.status,
                evidence_event_ids=evidence_event_ids,
            )
        )
    except ValueError as exc:
        raise AppError("invalid_memory_payload", str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY) from exc

    return _memory_write_response(result)


@router.post("/memory/search", response_model=MemorySearchResponse)
def search_memory(
    payload: MemorySearchRequest,
    request: Request,
    _: None = Depends(require_ingest_token),
) -> MemorySearchResponse:
    try:
        result = MemoryRetriever(request.app.state.db_engine).search(
            user_id=payload.user_id,
            query=payload.query,
            work_type=payload.work_type,
            memory_categories=payload.memory_categories,
            limit=payload.limit,
        )
    except ValueError as exc:
        raise AppError("invalid_memory_search", str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY) from exc

    return MemorySearchResponse(
        detected_work_type=result.detected_work_type,
        empty=result.empty,
        context_pack=result.context_pack,
        memories=[
            MemorySearchItem(
                memory_id=memory.memory_id,
                memory_category=memory.memory_category,
                work_type=memory.work_type,
                summary=memory.summary,
                score=memory.score,
                evidence_count=memory.evidence_count if payload.include_evidence_count else None,
                updated_at=memory.updated_at,
            )
            for memory in result.memories
        ],
    )


@router.post("/memory/update")
def update_memory(
    payload: MemoryUpdateRequest,
    request: Request,
    _: None = Depends(require_ingest_token),
) -> dict[str, Any]:
    try:
        memory = MemoryStore(request.app.state.db_engine).update_memory(
            memory_id=payload.memory_id,
            content_json=payload.content_json,
            work_type=payload.work_type,
            confidence=payload.confidence,
            status=payload.status,
        )
    except KeyError as exc:
        raise AppError("memory_not_found", "Memory not found", status.HTTP_404_NOT_FOUND) from exc
    except ValueError as exc:
        raise AppError("invalid_memory_payload", str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY) from exc
    return {"memory": memory}


@router.post("/memory/forget", response_model=MemoryForgetResponse)
def forget_memory(
    payload: MemoryForgetRequest,
    request: Request,
    _: None = Depends(require_ingest_token),
) -> MemoryForgetResponse:
    evidence_event_ids = _resolve_optional_evidence_event_ids(request, payload.evidence_event_ids, payload.evidence_event)
    evidence_event_id = evidence_event_ids[0] if evidence_event_ids else None
    deleted_ids = MemoryStore(request.app.state.db_engine).forget_memories(
        memory_id=payload.memory_id,
        user_id=payload.user_id,
        query=payload.query,
        memory_category=payload.memory_category,
        work_type=payload.work_type,
        evidence_event_id=evidence_event_id,
    )
    return MemoryForgetResponse(deleted_memory_ids=deleted_ids)


@router.get("/memory/{memory_id}")
def get_memory(
    memory_id: str,
    request: Request,
    _: None = Depends(require_ingest_token),
) -> dict[str, Any]:
    detail = MemoryStore(request.app.state.db_engine).get_memory_detail(memory_id)
    if detail is None:
        raise AppError("memory_not_found", "Memory not found", status.HTTP_404_NOT_FOUND)
    return detail


@router.post("/reminder/schedule", response_model=MemoryWriteResponse)
def schedule_reminder(
    payload: ReminderScheduleRequest,
    request: Request,
    _: None = Depends(require_ingest_token),
) -> MemoryWriteResponse:
    evidence_event_ids = _resolve_evidence_event_ids(request, payload.evidence_event_ids, payload.evidence_event)
    schedule = _build_schedule(payload)
    work_type = payload.work_type or detect_work_type(payload.reminder_text)
    content_json = {
        "summary": payload.reminder_text,
        "reminder_text": payload.reminder_text,
        "normalized_key": f"{work_type}:reminder:{payload.reminder_text.strip().lower()[:48]}",
        "source_text": payload.reminder_text,
        "extractor": "api_v0_3",
    }

    try:
        result = MemoryStore(request.app.state.db_engine).schedule_reminder(
            MemoryWrite(
                user_id=payload.user_id,
                memory_category="ReminderPreferenceMemory",
                work_type=work_type,
                content_json=content_json,
                source_channel="openclaw",
                source_signal_type="explicit_statement",
                confidence=0.9,
                status="active",
                evidence_event_ids=evidence_event_ids,
                reminder_schedule=schedule,
            )
        )
    except ValueError as exc:
        raise AppError("invalid_reminder_payload", str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY) from exc

    return _memory_write_response(result)


def _resolve_evidence_event_ids(
    request: Request,
    evidence_event_ids: list[str],
    evidence_event: dict[str, Any] | None,
) -> list[str]:
    resolved = list(evidence_event_ids)
    if evidence_event is not None:
        try:
            event = normalize_openclaw_event(evidence_event)
        except ValueError as exc:
            raise AppError("invalid_evidence_event", str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY) from exc
        EvidenceStore(request.app.state.db_engine).insert_work_event(event)
        resolved.append(event.event_id)
    if not resolved:
        raise AppError(
            "evidence_required",
            "At least one evidence_event_id or evidence_event is required",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return resolved


def _resolve_optional_evidence_event_ids(
    request: Request,
    evidence_event_ids: list[str],
    evidence_event: dict[str, Any] | None,
) -> list[str]:
    if not evidence_event_ids and evidence_event is None:
        return []
    return _resolve_evidence_event_ids(request, evidence_event_ids, evidence_event)


def _build_schedule(payload: ReminderScheduleRequest) -> ReminderSchedule:
    if payload.schedule_type and payload.next_run_at:
        return ReminderSchedule(
            schedule_type=payload.schedule_type,
            timezone=payload.timezone,
            next_run_at=payload.next_run_at,
            payload_json={
                "reminder_text": payload.reminder_text,
                **payload.payload_json,
            },
        )

    parsed = ReminderParser().parse(payload.reminder_text, timezone=payload.timezone)
    if parsed is None:
        raise AppError(
            "reminder_schedule_unrecognized",
            "Provide schedule_type and next_run_at, or include a recognizable schedule in reminder_text",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    if payload.payload_json:
        return ReminderSchedule(
            schedule_type=parsed.schedule_type,
            timezone=parsed.timezone,
            next_run_at=parsed.next_run_at,
            payload_json={**parsed.payload_json, **payload.payload_json},
        )
    return parsed


def _memory_write_response(result: Any) -> MemoryWriteResponse:
    return MemoryWriteResponse(
        memory_id=result.memory["memory_id"],
        created=result.created,
        replaced_memory_ids=result.replaced_memory_ids,
        evidence_event_ids=result.evidence_event_ids,
        reminder_jobs=result.reminder_jobs,
        memory=result.memory,
    )
