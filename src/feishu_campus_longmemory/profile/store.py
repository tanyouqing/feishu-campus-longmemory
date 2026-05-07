from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Engine

from feishu_campus_longmemory.profile.renderer import UserProfileRenderer
from feishu_campus_longmemory.profile.types import PROFILE_DIMENSIONS, UserProfilePatch, UserProfileSnapshot
from feishu_campus_longmemory.tables import user_profile_evidence_links, user_profiles, work_events

MAX_CLAIMS_PER_DIMENSION = 8


class UserProfileStore:
    def __init__(self, engine: Engine, *, renderer: UserProfileRenderer | None = None, max_markdown_chars: int = 1200) -> None:
        self._engine = engine
        self._renderer = renderer or UserProfileRenderer()
        self._max_markdown_chars = max_markdown_chars

    def upsert_profile(
        self,
        *,
        user_id: str,
        tenant_id: str | None,
        patches: list[UserProfilePatch],
        event_id: str,
    ) -> UserProfileSnapshot | None:
        valid_patches = [patch for patch in patches if _is_valid_patch(patch)]
        if not user_id or not valid_patches:
            return None

        now = _now()
        with self._engine.begin() as connection:
            self._ensure_evidence_exists(connection, event_id)
            existing = self._get_profile_row(connection, user_id)
            if existing:
                profile_json = deepcopy(existing["profile_json"])
                version = int(existing["version"]) + 1
                created_at = existing["created_at"]
            else:
                profile_json = _empty_profile_json()
                version = 1
                created_at = now

            changed = _merge_patches(profile_json, valid_patches, now)
            if not changed and existing:
                self._link_evidence(connection, user_id, event_id, "reinforced_by", now)
                return self.get_profile(user_id)

            profile_json["summary"] = _build_summary(profile_json)
            profile_json["last_updated_reason"] = valid_patches[-1].claim
            markdown = self._renderer.render(profile_json, max_chars=self._max_markdown_chars)
            confidence = _profile_confidence(profile_json)
            values = {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "profile_json": profile_json,
                "profile_markdown": markdown,
                "confidence": confidence,
                "version": version,
                "last_event_id": event_id,
                "created_at": created_at,
                "updated_at": now,
            }

            if existing:
                connection.execute(sa.update(user_profiles).where(user_profiles.c.user_id == user_id).values(**values))
            else:
                connection.execute(sa.insert(user_profiles).values(**values))
            self._link_evidence(connection, user_id, event_id, "updated_from", now)

        return self.get_profile(user_id)

    def get_profile(self, user_id: str) -> UserProfileSnapshot | None:
        with self._engine.connect() as connection:
            row = self._get_profile_row(connection, user_id)
        return _snapshot_from_row(row) if row else None

    def get_profile_markdown(self, user_id: str, *, max_chars: int | None = None) -> str:
        profile = self.get_profile(user_id)
        if profile is None:
            return ""
        if max_chars is None or len(profile.profile_markdown) <= max_chars:
            return profile.profile_markdown
        return self._renderer.render(profile.profile_json, max_chars=max_chars)

    def _ensure_evidence_exists(self, connection: sa.Connection, event_id: str) -> None:
        row = connection.execute(sa.select(work_events.c.event_id).where(work_events.c.event_id == event_id)).first()
        if row is None:
            raise ValueError(f"evidence event not found: {event_id}")

    def _get_profile_row(self, connection: sa.Connection, user_id: str) -> dict[str, Any] | None:
        row = connection.execute(sa.select(user_profiles).where(user_profiles.c.user_id == user_id)).mappings().first()
        return dict(row) if row else None

    def _link_evidence(self, connection: sa.Connection, user_id: str, event_id: str, relation_type: str, now: datetime) -> None:
        stmt = (
            sa.insert(user_profile_evidence_links)
            .values(user_id=user_id, event_id=event_id, relation_type=relation_type, created_at=now)
            .prefix_with("OR IGNORE")
        )
        connection.execute(stmt)


def _empty_profile_json() -> dict[str, Any]:
    return {
        "summary": "",
        "dimensions": {},
        "last_updated_reason": "",
    }


def _merge_patches(profile_json: dict[str, Any], patches: list[UserProfilePatch], now: datetime) -> bool:
    dimensions = profile_json.setdefault("dimensions", {})
    changed = False
    for patch in patches:
        dimension = dimensions.setdefault(patch.dimension, {"claims": [], "confidence": 0.0})
        claims = dimension.setdefault("claims", [])
        if not isinstance(claims, list):
            claims = []
            dimension["claims"] = claims

        normalized = _compact(patch.claim)
        existing = next((claim for claim in claims if isinstance(claim, dict) and _compact(str(claim.get("text", ""))) == normalized), None)
        if existing:
            old_confidence = float(existing.get("confidence") or 0)
            if patch.confidence > old_confidence:
                existing["confidence"] = round(patch.confidence, 3)
                existing["updated_at"] = now.isoformat()
                changed = True
        else:
            claims.append(
                {
                    "text": patch.claim,
                    "confidence": round(patch.confidence, 3),
                    "updated_at": now.isoformat(),
                }
            )
            changed = True

        claims.sort(key=lambda item: (float(item.get("confidence") or 0), str(item.get("updated_at") or "")), reverse=True)
        del claims[MAX_CLAIMS_PER_DIMENSION:]
        dimension["confidence"] = _dimension_confidence(claims)

    return changed


def _build_summary(profile_json: dict[str, Any]) -> str:
    dimensions = profile_json.get("dimensions")
    if not isinstance(dimensions, dict):
        return ""
    claims: list[str] = []
    for dimension in dimensions.values():
        if not isinstance(dimension, dict):
            continue
        for claim in dimension.get("claims", [])[:2]:
            if isinstance(claim, dict) and isinstance(claim.get("text"), str):
                claims.append(claim["text"])
            if len(claims) >= 3:
                break
        if len(claims) >= 3:
            break
    return "；".join(claims)[:240]


def _profile_confidence(profile_json: dict[str, Any]) -> float:
    dimensions = profile_json.get("dimensions")
    if not isinstance(dimensions, dict):
        return 0.5
    values = [
        float(value.get("confidence") or 0)
        for value in dimensions.values()
        if isinstance(value, dict) and float(value.get("confidence") or 0) > 0
    ]
    if not values:
        return 0.5
    return round(sum(values) / len(values), 3)


def _dimension_confidence(claims: list[dict[str, Any]]) -> float:
    values = [float(claim.get("confidence") or 0) for claim in claims]
    return round(max(values), 3) if values else 0.0


def _is_valid_patch(patch: UserProfilePatch) -> bool:
    return patch.dimension in PROFILE_DIMENSIONS and bool(patch.claim.strip()) and 0 <= patch.confidence <= 1


def _snapshot_from_row(row: dict[str, Any]) -> UserProfileSnapshot:
    return UserProfileSnapshot(
        user_id=row["user_id"],
        tenant_id=row["tenant_id"],
        profile_json=row["profile_json"],
        profile_markdown=row["profile_markdown"] or "",
        confidence=float(row["confidence"]),
        version=int(row["version"]),
        last_event_id=row["last_event_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _compact(value: str) -> str:
    return "".join(value.lower().split())


def _now() -> datetime:
    return datetime.now(timezone.utc)
