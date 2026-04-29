from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Engine

from feishu_campus_longmemory.memory.extractor import detect_work_type
from feishu_campus_longmemory.memory.types import ACTIVE_MEMORY_STATUSES, MEMORY_CATEGORIES
from feishu_campus_longmemory.tables import memory_evidence_links, personal_memories


DEFAULT_SEARCH_CATEGORIES = ("WorkPreferenceMemory", "ReminderPreferenceMemory")
SUPPORTED_WORK_TYPES = {
    "weekly_report",
    "meeting_minutes",
    "document_writing",
    "task_followup",
    "knowledge_lookup",
    "general",
}

_STATUS_WEIGHT = {"reinforced": 12.0, "active": 10.0, "candidate": 1.0}
_CATEGORY_WEIGHT = {
    "WorkPreferenceMemory": 2.0,
    "ReminderPreferenceMemory": 1.5,
    "WorkTimePatternMemory": 1.0,
    "WorkBehaviorMemory": 1.0,
}
_DOMAIN_TERMS = {
    "周报",
    "会议纪要",
    "纪要",
    "文档",
    "文章",
    "方案",
    "任务",
    "跟进",
    "待办",
    "知识库",
    "查询",
    "检索",
    "weekly",
    "report",
    "meeting",
    "minutes",
    "document",
    "draft",
    "task",
    "todo",
    "lookup",
}


@dataclass(frozen=True)
class RetrievedMemory:
    memory_id: str
    memory_category: str
    work_type: str
    summary: str
    score: float
    evidence_count: int
    updated_at: datetime


@dataclass(frozen=True)
class MemorySearchResult:
    detected_work_type: str
    memories: list[RetrievedMemory]
    context_pack: str

    @property
    def empty(self) -> bool:
        return not self.memories


class MemoryRetriever:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def search(
        self,
        *,
        user_id: str,
        query: str,
        work_type: str | None = None,
        memory_categories: list[str] | None = None,
        limit: int = 5,
    ) -> MemorySearchResult:
        if not user_id:
            raise ValueError("user_id is required")
        if limit < 1 or limit > 20:
            raise ValueError("limit must be between 1 and 20")

        categories = _normalize_categories(memory_categories)
        detected_work_type = _detect_target_work_type(query=query, requested_work_type=work_type)

        with self._engine.connect() as connection:
            rows = self._load_candidate_rows(connection, user_id=user_id, categories=categories)
            evidence_counts = self._load_evidence_counts(connection, [row["memory_id"] for row in rows])

        scored: list[RetrievedMemory] = []
        for row in rows:
            summary = _memory_summary(row["memory_category"], row["content_json"])
            if not summary:
                continue
            keyword_score = _keyword_score(query, _searchable_text(row["content_json"], summary))
            if not _is_relevant(row["work_type"], detected_work_type, keyword_score):
                continue
            score = _score_memory(row, detected_work_type, keyword_score, evidence_counts.get(row["memory_id"], 0))
            scored.append(
                RetrievedMemory(
                    memory_id=row["memory_id"],
                    memory_category=row["memory_category"],
                    work_type=row["work_type"],
                    summary=summary,
                    score=round(score, 3),
                    evidence_count=evidence_counts.get(row["memory_id"], 0),
                    updated_at=_as_datetime(row["updated_at"]),
                )
            )

        memories = sorted(
            scored,
            key=lambda item: (item.score, item.updated_at, item.memory_id),
            reverse=True,
        )[:limit]
        return MemorySearchResult(
            detected_work_type=detected_work_type,
            memories=memories,
            context_pack=ContextBuilder().build(memories),
        )

    def _load_candidate_rows(
        self,
        connection: sa.Connection,
        *,
        user_id: str,
        categories: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        stmt = (
            sa.select(personal_memories)
            .where(personal_memories.c.user_id == user_id)
            .where(personal_memories.c.status.in_(list(ACTIVE_MEMORY_STATUSES)))
            .where(personal_memories.c.memory_category.in_(list(categories)))
            .order_by(personal_memories.c.updated_at.desc())
        )
        return [dict(row) for row in connection.execute(stmt).mappings().all()]

    def _load_evidence_counts(self, connection: sa.Connection, memory_ids: list[str]) -> dict[str, int]:
        if not memory_ids:
            return {}
        stmt = (
            sa.select(memory_evidence_links.c.memory_id, sa.func.count().label("count"))
            .where(memory_evidence_links.c.memory_id.in_(memory_ids))
            .group_by(memory_evidence_links.c.memory_id)
        )
        return {row["memory_id"]: int(row["count"]) for row in connection.execute(stmt).mappings().all()}


class ContextBuilder:
    def build(self, memories: list[RetrievedMemory]) -> str:
        if not memories:
            return ""
        lines = [
            "Memory Context Pack",
            "- 以下是历史偏好，仅在不冲突时使用；当前用户请求优先。",
        ]
        for memory in memories:
            summary = _compact_context_line(memory.summary)
            if not summary:
                continue
            if memory.memory_category == "ReminderPreferenceMemory":
                lines.append(f"- 提醒偏好：{summary}")
            elif memory.memory_category == "WorkTimePatternMemory":
                lines.append(f"- 工作时间偏好：{summary}")
            elif memory.memory_category == "WorkBehaviorMemory":
                lines.append(f"- 工作习惯：{summary}")
            else:
                lines.append(f"- {summary}")
        return "\n".join(lines[:7])


def _normalize_categories(memory_categories: list[str] | None) -> tuple[str, ...]:
    categories = tuple(memory_categories or DEFAULT_SEARCH_CATEGORIES)
    unsupported = sorted(set(categories) - MEMORY_CATEGORIES)
    if unsupported:
        raise ValueError(f"unsupported memory_categories: {', '.join(unsupported)}")
    return categories


def _detect_target_work_type(*, query: str, requested_work_type: str | None) -> str:
    detected = detect_work_type(query)
    if requested_work_type and requested_work_type != "general":
        return requested_work_type
    return detected if detected in SUPPORTED_WORK_TYPES else "general"


def _is_relevant(row_work_type: str, detected_work_type: str, keyword_score: float) -> bool:
    if row_work_type == detected_work_type:
        return True
    if row_work_type == "general":
        return True
    return keyword_score > 0


def _score_memory(row: dict[str, Any], detected_work_type: str, keyword_score: float, evidence_count: int) -> float:
    work_type = row["work_type"]
    score = 0.0
    if work_type == detected_work_type and detected_work_type != "general":
        score += 20.0
    elif work_type == detected_work_type:
        score += 10.0
    elif work_type == "general":
        score += 6.0
    elif keyword_score > 0:
        score += 2.0

    score += _STATUS_WEIGHT.get(row["status"], 0.0)
    score += _CATEGORY_WEIGHT.get(row["memory_category"], 0.0)
    score += float(row["confidence"] or 0.0) * 5.0
    score += min(evidence_count, 4) * 0.75
    score += min(keyword_score, 6.0)
    score += _freshness_score(_as_datetime(row["updated_at"]))
    return score


def _keyword_score(query: str, target: str) -> float:
    terms = _query_terms(query)
    if not terms:
        return 0.0
    target_lower = target.lower()
    score = 0.0
    matched: set[str] = set()
    for term in terms:
        if term in matched:
            continue
        if term.lower() in target_lower:
            matched.add(term)
            score += 1.5 if len(term) >= 4 else 1.0
    return score


def _query_terms(query: str) -> list[str]:
    lowered = query.lower()
    terms = set(re.findall(r"[a-z0-9_]{2,}", lowered))
    for run in re.findall(r"[\u4e00-\u9fff]+", query):
        if len(run) >= 2:
            terms.add(run)
            for size in (2, 3, 4):
                for index in range(0, max(len(run) - size + 1, 0)):
                    terms.add(run[index : index + size])
    for term in _DOMAIN_TERMS:
        if term in query or term in lowered:
            terms.add(term)
    return sorted((term for term in terms if len(term) >= 2), key=len, reverse=True)


def _memory_summary(memory_category: str, content_json: dict[str, Any]) -> str:
    for key in ("summary", "preference", "reminder_text"):
        value = content_json.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            text = value.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    if memory_category == "ReminderPreferenceMemory":
        value = content_json.get("payload_json")
        if isinstance(value, dict) and isinstance(value.get("reminder_text"), str):
            return value["reminder_text"].strip()
    return ""


def _searchable_text(content_json: dict[str, Any], summary: str) -> str:
    parts = [summary]
    for key in ("preference", "reminder_text", "normalized_key"):
        value = content_json.get(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts)


def _compact_context_line(value: str) -> str:
    compacted = " ".join(value.split())
    if len(compacted) <= 120:
        return compacted
    return compacted[:117].rstrip() + "..."


def _freshness_score(updated_at: datetime) -> float:
    now = datetime.now(timezone.utc)
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    days = max((now - updated_at).total_seconds() / 86400, 0)
    if days <= 1:
        return 3.0
    if days <= 7:
        return 2.0
    if days <= 30:
        return 1.0
    return 0.0


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)
