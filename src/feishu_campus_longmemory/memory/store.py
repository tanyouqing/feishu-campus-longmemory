from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Engine

from feishu_campus_longmemory.memory.types import (
    ACTIVE_MEMORY_STATUSES,
    MEMORY_CATEGORIES,
    MEMORY_STATUSES,
    REMINDER_SCHEDULE_TYPES,
    MemoryWrite,
    MemoryWriteResult,
    ReminderSchedule,
)
from feishu_campus_longmemory.tables import (
    memory_audit_logs,
    memory_evidence_links,
    personal_memories,
    reminder_jobs,
    work_events,
)


class MemoryStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write_memory(self, write: MemoryWrite) -> MemoryWriteResult:
        _validate_write(write)
        now = _now()
        normalized_key = _normalized_key(write.content_json)

        with self._engine.begin() as connection:
            self._ensure_evidence_exists(connection, write.evidence_event_ids)
            existing = self._find_active_by_key(
                connection,
                user_id=write.user_id,
                memory_category=write.memory_category,
                work_type=write.work_type,
                normalized_key=normalized_key,
            )
            same_memory = _find_equivalent_memory(existing, write.content_json)
            if same_memory:
                memory_id = same_memory["memory_id"]
                self._link_evidence(connection, memory_id, write.evidence_event_ids, "reinforced_by", now)
                after = dict(same_memory)
                if after["status"] == "active":
                    after["status"] = "reinforced"
                    after["updated_at"] = now
                    connection.execute(
                        sa.update(personal_memories)
                        .where(personal_memories.c.memory_id == memory_id)
                        .values(status="reinforced", updated_at=now)
                    )
                self._insert_audit(connection, memory_id, write.user_id, "update", same_memory, after, now)
                return MemoryWriteResult(
                    memory=self._get_memory_row(connection, memory_id),
                    created=False,
                    replaced_memory_ids=[],
                    evidence_event_ids=self._get_evidence_ids(connection, memory_id),
                    reminder_jobs=self._get_reminder_jobs(connection, memory_id),
                )

            replaced_ids: list[str] = []
            for row in existing:
                replaced_ids.append(row["memory_id"])
                before = dict(row)
                after = {**before, "status": "replaced", "updated_at": now}
                connection.execute(
                    sa.update(personal_memories)
                    .where(personal_memories.c.memory_id == row["memory_id"])
                    .values(status="replaced", updated_at=now)
                )
                self._insert_audit(connection, row["memory_id"], write.user_id, "replace", before, after, now)

            memory_id = uuid.uuid4().hex
            memory_values = {
                "memory_id": memory_id,
                "user_id": write.user_id,
                "memory_category": write.memory_category,
                "work_type": write.work_type,
                "content_json": {**write.content_json, "normalized_key": normalized_key},
                "source_channel": write.source_channel,
                "source_signal_type": write.source_signal_type,
                "confidence": write.confidence,
                "status": write.status,
                "created_at": now,
                "updated_at": now,
            }
            connection.execute(sa.insert(personal_memories).values(**memory_values))
            self._link_evidence(connection, memory_id, write.evidence_event_ids, "created_from", now)
            self._insert_audit(connection, memory_id, write.user_id, "create", None, memory_values, now)

            if write.reminder_schedule:
                self._create_reminder_job(connection, memory_id, write.user_id, write.reminder_schedule, now)

            return MemoryWriteResult(
                memory=self._get_memory_row(connection, memory_id),
                created=True,
                replaced_memory_ids=replaced_ids,
                evidence_event_ids=self._get_evidence_ids(connection, memory_id),
                reminder_jobs=self._get_reminder_jobs(connection, memory_id),
            )

    def update_memory(
        self,
        *,
        memory_id: str,
        content_json: dict[str, Any] | None = None,
        work_type: str | None = None,
        confidence: float | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        now = _now()
        if status and status not in MEMORY_STATUSES:
            raise ValueError(f"unsupported memory status: {status}")
        if confidence is not None and not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")

        with self._engine.begin() as connection:
            before = self._get_memory_row(connection, memory_id)
            if before is None:
                raise KeyError(memory_id)

            values: dict[str, Any] = {"updated_at": now}
            if content_json is not None:
                values["content_json"] = {
                    **content_json,
                    "normalized_key": _normalized_key(content_json),
                }
            if work_type is not None:
                values["work_type"] = work_type
            if confidence is not None:
                values["confidence"] = confidence
            if status is not None:
                values["status"] = status

            connection.execute(sa.update(personal_memories).where(personal_memories.c.memory_id == memory_id).values(**values))
            after = self._get_memory_row(connection, memory_id)
            self._insert_audit(connection, memory_id, before["user_id"], "update", before, after, now)
            return after

    def forget_memories(
        self,
        *,
        user_id: str | None = None,
        query: str | None = None,
        memory_id: str | None = None,
        memory_category: str | None = None,
        work_type: str | None = None,
        evidence_event_id: str | None = None,
    ) -> list[str]:
        now = _now()
        with self._engine.begin() as connection:
            if memory_id:
                rows = [self._get_memory_row(connection, memory_id)]
                rows = [row for row in rows if row is not None]
            else:
                rows = self._find_memory_matches(
                    connection,
                    user_id=user_id,
                    query=query,
                    memory_category=memory_category,
                    work_type=work_type,
                )

            deleted_ids: list[str] = []
            for row in rows:
                before = dict(row)
                after = {**before, "status": "deleted", "updated_at": now}
                connection.execute(
                    sa.update(personal_memories)
                    .where(personal_memories.c.memory_id == row["memory_id"])
                    .values(status="deleted", updated_at=now)
                )
                connection.execute(
                    sa.update(reminder_jobs)
                    .where(reminder_jobs.c.memory_id == row["memory_id"])
                    .where(reminder_jobs.c.status.in_(["active", "paused"]))
                    .values(status="cancelled", updated_at=now)
                )
                if evidence_event_id:
                    self._link_evidence(connection, row["memory_id"], [evidence_event_id], "deleted_by", now)
                self._insert_audit(connection, row["memory_id"], row["user_id"], "delete", before, after, now)
                deleted_ids.append(row["memory_id"])

            return deleted_ids

    def schedule_reminder(self, write: MemoryWrite) -> MemoryWriteResult:
        if write.memory_category != "ReminderPreferenceMemory" or write.reminder_schedule is None:
            raise ValueError("schedule_reminder requires a ReminderPreferenceMemory with reminder_schedule")
        return self.write_memory(write)

    def get_memory_detail(self, memory_id: str) -> dict[str, Any] | None:
        with self._engine.connect() as connection:
            memory = self._get_memory_row(connection, memory_id)
            if memory is None:
                return None
            return {
                **memory,
                "evidence_event_ids": self._get_evidence_ids(connection, memory_id),
                "reminder_jobs": self._get_reminder_jobs(connection, memory_id),
            }

    def list_memories(self, user_id: str, *, status: str | None = None) -> list[dict[str, Any]]:
        stmt = sa.select(personal_memories).where(personal_memories.c.user_id == user_id)
        if status:
            stmt = stmt.where(personal_memories.c.status == status)
        stmt = stmt.order_by(personal_memories.c.updated_at.desc())
        with self._engine.connect() as connection:
            return [dict(row) for row in connection.execute(stmt).mappings().all()]

    def _ensure_evidence_exists(self, connection: sa.Connection, event_ids: list[str]) -> None:
        if not event_ids:
            raise ValueError("at least one evidence_event_id is required")
        rows = connection.execute(sa.select(work_events.c.event_id).where(work_events.c.event_id.in_(event_ids))).scalars().all()
        missing = sorted(set(event_ids) - set(rows))
        if missing:
            raise ValueError(f"evidence events not found: {', '.join(missing)}")

    def _find_active_by_key(
        self,
        connection: sa.Connection,
        *,
        user_id: str,
        memory_category: str,
        work_type: str,
        normalized_key: str,
    ) -> list[dict[str, Any]]:
        stmt = (
            sa.select(personal_memories)
            .where(personal_memories.c.user_id == user_id)
            .where(personal_memories.c.memory_category == memory_category)
            .where(personal_memories.c.work_type == work_type)
            .where(personal_memories.c.status.in_(list(ACTIVE_MEMORY_STATUSES)))
        )
        rows = [dict(row) for row in connection.execute(stmt).mappings().all()]
        return [row for row in rows if _normalized_key(row["content_json"]) == normalized_key]

    def _find_memory_matches(
        self,
        connection: sa.Connection,
        *,
        user_id: str | None,
        query: str | None,
        memory_category: str | None,
        work_type: str | None,
    ) -> list[dict[str, Any]]:
        if not user_id:
            return []
        stmt = (
            sa.select(personal_memories)
            .where(personal_memories.c.user_id == user_id)
            .where(personal_memories.c.status.in_(list(ACTIVE_MEMORY_STATUSES)))
        )
        if memory_category:
            stmt = stmt.where(personal_memories.c.memory_category == memory_category)
        if work_type and work_type != "general":
            stmt = stmt.where(personal_memories.c.work_type == work_type)
        rows = [dict(row) for row in connection.execute(stmt).mappings().all()]
        if not query:
            return rows
        query_norm = _compact(query)
        matched = [row for row in rows if query_norm in _compact(str(row["content_json"]))]
        return matched or rows if work_type and work_type != "general" else matched

    def _link_evidence(
        self,
        connection: sa.Connection,
        memory_id: str,
        event_ids: list[str],
        relation_type: str,
        now: datetime,
    ) -> None:
        for event_id in event_ids:
            stmt = (
                sa.insert(memory_evidence_links)
                .values(memory_id=memory_id, event_id=event_id, relation_type=relation_type, created_at=now)
                .prefix_with("OR IGNORE")
            )
            connection.execute(stmt)

    def _create_reminder_job(
        self,
        connection: sa.Connection,
        memory_id: str,
        user_id: str,
        schedule: ReminderSchedule,
        now: datetime,
    ) -> dict[str, Any]:
        if schedule.schedule_type not in REMINDER_SCHEDULE_TYPES:
            raise ValueError(f"unsupported reminder schedule type: {schedule.schedule_type}")
        values = {
            "job_id": uuid.uuid4().hex,
            "user_id": user_id,
            "memory_id": memory_id,
            "schedule_type": schedule.schedule_type,
            "timezone": schedule.timezone,
            "next_run_at": schedule.next_run_at.astimezone(timezone.utc), 
            "payload_json": schedule.payload_json,
            "status": "active",
            "last_run_at": None,
            "created_at": now,
            "updated_at": now,
        }
        connection.execute(sa.insert(reminder_jobs).values(**values))
        return values

    def _insert_audit(
        self,
        connection: sa.Connection,
        memory_id: str,
        user_id: str,
        action: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        now: datetime,
    ) -> None:
        connection.execute(
            sa.insert(memory_audit_logs).values(
                audit_id=uuid.uuid4().hex,
                memory_id=memory_id,
                user_id=user_id,
                action=action,
                before_json=_json_safe(before),
                after_json=_json_safe(after),
                created_at=now,
            )
        )

    def _get_memory_row(self, connection: sa.Connection, memory_id: str) -> dict[str, Any] | None:
        row = connection.execute(sa.select(personal_memories).where(personal_memories.c.memory_id == memory_id)).mappings().first()
        return dict(row) if row else None

    def _get_evidence_ids(self, connection: sa.Connection, memory_id: str) -> list[str]:
        stmt = sa.select(memory_evidence_links.c.event_id).where(memory_evidence_links.c.memory_id == memory_id)
        return list(connection.execute(stmt).scalars().all())

    def _get_reminder_jobs(self, connection: sa.Connection, memory_id: str) -> list[dict[str, Any]]:
        stmt = sa.select(reminder_jobs).where(reminder_jobs.c.memory_id == memory_id).order_by(reminder_jobs.c.created_at.desc())
        return [dict(row) for row in connection.execute(stmt).mappings().all()]


def _validate_write(write: MemoryWrite) -> None:
    if write.memory_category not in MEMORY_CATEGORIES:
        raise ValueError(f"unsupported memory_category: {write.memory_category}")
    if write.status not in MEMORY_STATUSES:
        raise ValueError(f"unsupported memory status: {write.status}")
    if not 0 <= write.confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")


def _normalized_key(content_json: dict[str, Any]) -> str:
    value = content_json.get("normalized_key") or content_json.get("summary") or content_json.get("preference") or "general"
    return _compact(str(value))[:96] or "general"


def _find_equivalent_memory(rows: list[dict[str, Any]], content_json: dict[str, Any]) -> dict[str, Any] | None:
    summary = _compact(str(content_json.get("summary") or content_json))
    for row in rows:
        row_summary = _compact(str(row["content_json"].get("summary") or row["content_json"]))
        if row_summary == summary:
            return row
    return None


def _compact(value: str) -> str:
    return "".join(value.lower().split())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value

