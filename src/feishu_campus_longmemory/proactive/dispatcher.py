from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy import Engine

from feishu_campus_longmemory.config import Settings
from feishu_campus_longmemory.events.normalize import build_event_id
from feishu_campus_longmemory.events.privacy import RedactionResult, redact_text
from feishu_campus_longmemory.events.store import EvidenceStore
from feishu_campus_longmemory.events.types import WorkEvent
from feishu_campus_longmemory.proactive.feishu import FeishuConfigurationError, FeishuDeliveryError, FeishuMessageSender
from feishu_campus_longmemory.proactive.types import FeishuSendResult, ReminderDispatchResult
from feishu_campus_longmemory.tables import reminder_jobs


class ReminderSender(Protocol):
    def send_text(self, *, receive_id: str, receive_id_type: str, text: str, uuid: str) -> FeishuSendResult:
        ...


class ReminderDispatcher:
    def __init__(self, engine: Engine, settings: Settings, sender: ReminderSender | None = None) -> None:
        self._engine = engine
        self._settings = settings
        self._sender = sender or FeishuMessageSender(settings)

    def trigger_due(
        self,
        *,
        job_id: str | None = None,
        limit: int | None = None,
        now: datetime | None = None,
    ) -> list[ReminderDispatchResult]:
        current = _utc(now)
        batch_limit = limit or self._settings.reminder_batch_size
        jobs = self._claim_due_jobs(job_id=job_id, limit=batch_limit, now=current)
        if not jobs:
            return [ReminderDispatchResult(job_id=job_id, status="skipped", error="job is not due or not active")] if job_id else []
        return [self._dispatch_job(job, now=current) for job in jobs]

    def _claim_due_jobs(self, *, job_id: str | None, limit: int, now: datetime) -> list[dict[str, Any]]:
        claimed: list[dict[str, Any]] = []
        with self._engine.begin() as connection:
            stmt = sa.select(reminder_jobs).where(reminder_jobs.c.status == "active").order_by(reminder_jobs.c.next_run_at.asc()).limit(limit)
            if job_id:
                stmt = stmt.where(reminder_jobs.c.job_id == job_id)
            rows = [dict(row) for row in connection.execute(stmt).mappings().all()]

            for row in rows:
                if _utc(row["next_run_at"]) > now:
                    continue
                payload = _payload(row)
                attempt_id = uuid.uuid4().hex
                payload.update(
                    {
                        "delivery_status": "dispatching",
                        "dispatch_started_at": now.isoformat(),
                        "attempt_id": attempt_id,
                        "attempt_count": int(payload.get("attempt_count") or 0) + 1,
                    }
                )
                result = connection.execute(
                    sa.update(reminder_jobs)
                    .where(reminder_jobs.c.job_id == row["job_id"])
                    .where(reminder_jobs.c.status == "active")
                    .values(status="paused", payload_json=payload, updated_at=now)
                )
                if result.rowcount == 1:
                    claimed.append({**row, "status": "paused", "payload_json": payload})
        return claimed

    def _dispatch_job(self, job: dict[str, Any], *, now: datetime) -> ReminderDispatchResult:
        payload = _payload(job)
        reminder_text = _reminder_text(payload)
        redaction = redact_text(reminder_text)
        if _contains_strong_secret(redaction.text):
            event = self._record_failure_event(job, redaction, "Reminder contains strong sensitive content", now)
            self._mark_failed(job, event.event_id, "Reminder contains strong sensitive content", now)
            return ReminderDispatchResult(job_id=job["job_id"], status="failed", work_event_id=event.event_id, error="Reminder contains strong sensitive content")

        message_text = _message_text(redaction.text)
        receive_id = str(payload.get("feishu_receive_id") or job["user_id"])
        receive_id_type = str(payload.get("feishu_receive_id_type") or self._settings.feishu_default_receive_id_type)
        attempt_id = str(payload.get("attempt_id") or uuid.uuid4().hex)

        try:
            sent = self._sender.send_text(
                receive_id=receive_id,
                receive_id_type=receive_id_type,
                text=message_text,
                uuid=f"rmd-{attempt_id}",
            )
        except (FeishuConfigurationError, FeishuDeliveryError, RuntimeError) as exc:
            event = self._record_failure_event(job, redaction, _safe_error(exc), now)
            self._mark_failed(job, event.event_id, _safe_error(exc), now)
            return ReminderDispatchResult(job_id=job["job_id"], status="failed", work_event_id=event.event_id, error=_safe_error(exc))

        event = self._record_success_event(job, redaction, sent, now)
        next_run_at = _next_run_at(job, now)
        self._mark_sent(job, event.event_id, sent, next_run_at, now)
        return ReminderDispatchResult(
            job_id=job["job_id"],
            status="sent",
            work_event_id=event.event_id,
            message_id=sent.message_id,
            next_run_at=next_run_at,
        )

    def _record_success_event(self, job: dict[str, Any], redaction: RedactionResult, sent: FeishuSendResult, now: datetime) -> WorkEvent:
        source_event_id = f"reminder:{job['job_id']}:{job['payload_json'].get('attempt_id')}:sent"
        event = WorkEvent(
            event_id=build_event_id("feishu", source_event_id),
            user_id=job["user_id"],
            tenant_id=None,
            source="feishu",
            event_type="im.message.create_v1",
            actor_type="system",
            object_type="message",
            object_id=sent.message_id,
            work_type="general",
            timestamp=now,
            content_json={
                "source_event_id": source_event_id,
                "summary": {"text": _message_text(redaction.text), "redacted": redaction.redacted},
                "metadata": {
                    "job_id": job["job_id"],
                    "memory_id": job["memory_id"],
                    "schedule_type": job["schedule_type"],
                    "delivery_status": "sent",
                    "chat_id": sent.chat_id,
                    "log_id": sent.log_id,
                },
            },
            privacy_level=redaction.privacy_level,
        )
        EvidenceStore(self._engine).insert_work_event(event)
        return event

    def _record_failure_event(self, job: dict[str, Any], redaction: RedactionResult, error: str, now: datetime) -> WorkEvent:
        source_event_id = f"reminder:{job['job_id']}:{job['payload_json'].get('attempt_id')}:failed"
        event = WorkEvent(
            event_id=build_event_id("longmemory", source_event_id),
            user_id=job["user_id"],
            tenant_id=None,
            source="longmemory",
            event_type="reminder.delivery.failed",
            actor_type="system",
            object_type="reminder_job",
            object_id=job["job_id"],
            work_type="general",
            timestamp=now,
            content_json={
                "source_event_id": source_event_id,
                "summary": {"text": _message_text(redaction.text), "redacted": redaction.redacted},
                "metadata": {
                    "job_id": job["job_id"],
                    "memory_id": job["memory_id"],
                    "schedule_type": job["schedule_type"],
                    "delivery_status": "failed",
                    "error": error[:300],
                },
            },
            privacy_level=redaction.privacy_level,
        )
        EvidenceStore(self._engine).insert_work_event(event)
        return event

    def _mark_sent(
        self,
        job: dict[str, Any],
        event_id: str,
        sent: FeishuSendResult,
        next_run_at: datetime | None,
        now: datetime,
    ) -> None:
        payload = _payload(job)
        payload.update(
            {
                "delivery_status": "sent",
                "sent_event_id": event_id,
                "feishu_message_id": sent.message_id,
                "feishu_chat_id": sent.chat_id,
                "last_sent_at": now.isoformat(),
            }
        )
        status = "triggered" if job["schedule_type"] == "once" else "active"
        values: dict[str, Any] = {"status": status, "last_run_at": now, "payload_json": payload, "updated_at": now}
        if next_run_at is not None:
            values["next_run_at"] = next_run_at
        with self._engine.begin() as connection:
            connection.execute(sa.update(reminder_jobs).where(reminder_jobs.c.job_id == job["job_id"]).values(**values))

    def _mark_failed(self, job: dict[str, Any], event_id: str, error: str, now: datetime) -> None:
        payload = _payload(job)
        payload.update(
            {
                "delivery_status": "failed",
                "failed_event_id": event_id,
                "last_error": error[:300],
                "last_failed_at": now.isoformat(),
            }
        )
        with self._engine.begin() as connection:
            connection.execute(
                sa.update(reminder_jobs)
                .where(reminder_jobs.c.job_id == job["job_id"])
                .values(status="paused", payload_json=payload, updated_at=now)
            )


def _payload(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload_json")
    return dict(payload) if isinstance(payload, dict) else {}


def _reminder_text(payload: dict[str, Any]) -> str:
    for key in ("reminder_text", "summary", "source_text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "你有一个到期提醒"


def _message_text(reminder_text: str) -> str:
    return f"提醒：{reminder_text}"


def _next_run_at(job: dict[str, Any], now: datetime) -> datetime | None:
    schedule_type = job["schedule_type"]
    if schedule_type == "once":
        return None
    timezone_name = job.get("timezone") or "Asia/Shanghai"
    local_tz = ZoneInfo(timezone_name)
    base = _utc(job["next_run_at"]).astimezone(local_tz)
    delta = timedelta(days=1 if schedule_type == "daily" else 7)
    next_run_at = base + delta
    while next_run_at <= now.astimezone(local_tz):
        next_run_at += delta
    return next_run_at.astimezone(timezone.utc)


def _utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _contains_strong_secret(redacted_text: str) -> bool:
    return "[REDACTED_SECRET]" in redacted_text or "[REDACTED_PRIVATE_KEY]" in redacted_text


def _safe_error(exc: BaseException) -> str:
    return str(exc) or exc.__class__.__name__
