from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class WorkEvent:
    event_id: str
    user_id: str
    tenant_id: str | None
    source: str
    event_type: str
    actor_type: str
    object_type: str | None
    object_id: str | None
    work_type: str
    timestamp: datetime
    content_json: dict[str, Any]
    privacy_level: str


@dataclass(frozen=True)
class StoreResult:
    event: WorkEvent
    created: bool

