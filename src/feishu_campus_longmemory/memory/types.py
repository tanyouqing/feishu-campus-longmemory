from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


MEMORY_CATEGORIES = {
    "WorkPreferenceMemory",
    "WorkTimePatternMemory",
    "WorkBehaviorMemory",
    "ReminderPreferenceMemory",
}

MEMORY_STATUSES = {"candidate", "active", "reinforced", "outdated", "replaced", "deleted"}
REMINDER_SCHEDULE_TYPES = {"once", "weekly", "daily", "cron_like"}
ACTIVE_MEMORY_STATUSES = {"candidate", "active", "reinforced"}


@dataclass(frozen=True)
class ReminderSchedule:
    schedule_type: str
    timezone: str
    next_run_at: datetime
    payload_json: dict[str, Any]


@dataclass(frozen=True)
class MemoryWrite:
    user_id: str
    memory_category: str
    work_type: str
    content_json: dict[str, Any]
    source_channel: str
    source_signal_type: str
    confidence: float
    status: str
    evidence_event_ids: list[str]
    reminder_schedule: ReminderSchedule | None = None


@dataclass(frozen=True)
class MemoryWriteResult:
    memory: dict[str, Any]
    created: bool
    replaced_memory_ids: list[str]
    evidence_event_ids: list[str]
    reminder_jobs: list[dict[str, Any]]

