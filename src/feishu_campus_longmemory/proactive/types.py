from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FeishuSendResult:
    message_id: str
    chat_id: str | None = None
    create_time: int | None = None
    log_id: str | None = None


@dataclass(frozen=True)
class ReminderDispatchResult:
    job_id: str
    status: str
    work_event_id: str | None = None
    message_id: str | None = None
    next_run_at: datetime | None = None
    error: str | None = None

