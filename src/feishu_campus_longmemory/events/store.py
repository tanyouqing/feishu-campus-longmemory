from __future__ import annotations

from dataclasses import asdict
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Engine

from feishu_campus_longmemory.events.types import StoreResult, WorkEvent
from feishu_campus_longmemory.tables import work_events


class EvidenceStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def insert_work_event(self, event: WorkEvent) -> StoreResult:
        values = asdict(event)
        stmt = sa.insert(work_events).values(**values)
        stmt = stmt.prefix_with("OR IGNORE")

        with self._engine.begin() as connection:
            result = connection.execute(stmt)
            created = result.rowcount == 1
            stored = self._fetch_by_id(connection, event.event_id)

        if stored is None:
            raise RuntimeError(f"failed to fetch inserted work event: {event.event_id}")
        return StoreResult(event=stored, created=created)

    def get_work_event(self, event_id: str) -> WorkEvent | None:
        with self._engine.connect() as connection:
            return self._fetch_by_id(connection, event_id)

    def list_work_events(
        self,
        *,
        user_id: str | None = None,
        source: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[WorkEvent]:
        stmt = sa.select(work_events).order_by(work_events.c.timestamp.desc(), work_events.c.created_at.desc()).limit(limit)
        if user_id:
            stmt = stmt.where(work_events.c.user_id == user_id)
        if source:
            stmt = stmt.where(work_events.c.source == source)
        if event_type:
            stmt = stmt.where(work_events.c.event_type == event_type)

        with self._engine.connect() as connection:
            rows = connection.execute(stmt).mappings().all()

        return [self._row_to_event(row) for row in rows]

    def _fetch_by_id(self, connection: sa.Connection, event_id: str) -> WorkEvent | None:
        stmt = sa.select(work_events).where(work_events.c.event_id == event_id)
        row = connection.execute(stmt).mappings().first()
        if row is None:
            return None
        return self._row_to_event(row)

    @staticmethod
    def _row_to_event(row: Any) -> WorkEvent:
        return WorkEvent(
            event_id=row["event_id"],
            user_id=row["user_id"],
            tenant_id=row["tenant_id"],
            source=row["source"],
            event_type=row["event_type"],
            actor_type=row["actor_type"],
            object_type=row["object_type"],
            object_id=row["object_id"],
            work_type=row["work_type"],
            timestamp=row["timestamp"],
            content_json=row["content_json"],
            privacy_level=row["privacy_level"],
        )

