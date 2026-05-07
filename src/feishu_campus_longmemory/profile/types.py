from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


PROFILE_DIMENSIONS = {
    "work_identity",
    "current_work_stage",
    "work_preferences",
    "communication_style",
    "tool_usage",
    "reminder_and_proactive_service",
    "life_preferences",
    "other_profile_traits",
}


@dataclass(frozen=True)
class UserProfilePatch:
    dimension: str
    claim: str
    confidence: float
    evidence_text: str


@dataclass(frozen=True)
class UserProfileDimensionPatch:
    dimension: str
    claims: list[UserProfilePatch]


@dataclass(frozen=True)
class UserProfileSnapshot:
    user_id: str
    tenant_id: str | None
    profile_json: dict[str, Any]
    profile_markdown: str
    confidence: float
    version: int
    last_event_id: str | None
    created_at: datetime
    updated_at: datetime
