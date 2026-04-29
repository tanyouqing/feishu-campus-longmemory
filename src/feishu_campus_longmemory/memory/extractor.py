from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from feishu_campus_longmemory.events.types import WorkEvent
from feishu_campus_longmemory.memory.reminder import ReminderParser
from feishu_campus_longmemory.memory.store import MemoryStore
from feishu_campus_longmemory.memory.types import MemoryWrite

PREFERENCE_MARKERS = ("以后", "今后", "我喜欢", "记住")
FORGET_MARKERS = ("忘掉", "忘记")
REMINDER_CANCEL_MARKERS = ("别提醒", "不要提醒", "不用提醒", "取消提醒", "不要再提醒")
STRONG_SECRET_MARKERS = ("[REDACTED_SECRET]", "[REDACTED_PRIVATE_KEY]")


@dataclass(frozen=True)
class ExtractionResult:
    memory_ids: list[str]
    deleted_memory_ids: list[str]


class ExplicitMemoryExtractor:
    def __init__(self, reminder_parser: ReminderParser | None = None) -> None:
        self._reminder_parser = reminder_parser or ReminderParser()

    def process_event(self, event: WorkEvent, store: MemoryStore) -> ExtractionResult:
        text = _event_text(event)
        if not text or _contains_strong_secret(text):
            return ExtractionResult(memory_ids=[], deleted_memory_ids=[])

        if _contains_any(text, REMINDER_CANCEL_MARKERS):
            query = _strip_marker(text, REMINDER_CANCEL_MARKERS)
            deleted = store.forget_memories(
                user_id=event.user_id,
                query=None if _is_generic_reminder_cancel_query(query) else query,
                memory_category="ReminderPreferenceMemory",
                work_type=detect_work_type(query),
                evidence_event_id=event.event_id,
            )
            return ExtractionResult(memory_ids=[], deleted_memory_ids=deleted)

        if _contains_any(text, FORGET_MARKERS):
            query = _strip_marker(text, FORGET_MARKERS)
            deleted = store.forget_memories(
                user_id=event.user_id,
                query=query,
                memory_category=_category_from_forget_query(query),
                work_type=detect_work_type(query),
                evidence_event_id=event.event_id,
            )
            return ExtractionResult(memory_ids=[], deleted_memory_ids=deleted)

        if "提醒我" in text:
            schedule = self._reminder_parser.parse(text)
            reminder_text = _strip_reminder_text(text)
            write = MemoryWrite(
                user_id=event.user_id,
                memory_category="ReminderPreferenceMemory",
                work_type=detect_work_type(text),
                content_json={
                    "summary": reminder_text,
                    "reminder_text": reminder_text,
                    "normalized_key": f"{detect_work_type(text)}:reminder:{_normalize_key(reminder_text)}",
                    "source_text": text,
                    "extractor": "rules_v0_3",
                },
                source_channel=event.source,
                source_signal_type="explicit_statement",
                confidence=0.9 if schedule else 0.7,
                status="active",
                evidence_event_ids=[event.event_id],
                reminder_schedule=schedule,
            )
            result = store.write_memory(write)
            return ExtractionResult(memory_ids=[result.memory["memory_id"]], deleted_memory_ids=[])

        if _contains_any(text, PREFERENCE_MARKERS) or "不要再" in text:
            preference = _strip_marker(text, (*PREFERENCE_MARKERS, "不要再"))
            polarity = "negative" if "不要再" in text else "positive"
            work_type = detect_work_type(text)
            write = MemoryWrite(
                user_id=event.user_id,
                memory_category="WorkPreferenceMemory",
                work_type=work_type,
                content_json={
                    "summary": preference,
                    "preference": preference,
                    "polarity": polarity,
                    "normalized_key": f"{work_type}:preference",
                    "source_text": text,
                    "extractor": "rules_v0_3",
                },
                source_channel=event.source,
                source_signal_type="explicit_statement",
                confidence=0.85,
                status="active",
                evidence_event_ids=[event.event_id],
            )
            result = store.write_memory(write)
            return ExtractionResult(memory_ids=[result.memory["memory_id"]], deleted_memory_ids=[])

        return ExtractionResult(memory_ids=[], deleted_memory_ids=[])


def detect_work_type(text: str | None) -> str:
    if not text:
        return "general"
    normalized = text.lower()
    if "周报" in text or "weekly report" in normalized or "weekly_report" in normalized:
        return "weekly_report"
    if "会议纪要" in text or "纪要" in text or "meeting minutes" in normalized:
        return "meeting_minutes"
    if "文档" in text or "文章" in text or "方案" in text or "draft" in normalized:
        return "document_writing"
    if "任务" in text or "跟进" in text or "待办" in text or "follow up" in normalized or "todo" in normalized:
        return "task_followup"
    if "知识库" in text or "查询" in text or "检索" in text or "搜索" in text or "lookup" in normalized:
        return "knowledge_lookup"
    return "general"


def _event_text(event: WorkEvent) -> str | None:
    summary = event.content_json.get("summary")
    if isinstance(summary, dict):
        text = summary.get("text")
        return text if isinstance(text, str) else None
    return None


def _contains_strong_secret(text: str) -> bool:
    return any(marker in text for marker in STRONG_SECRET_MARKERS)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _strip_marker(text: str, markers: tuple[str, ...]) -> str:
    for marker in markers:
        if marker in text:
            return text.split(marker, 1)[1].strip("，,。 ")
    return text.strip()


def _strip_reminder_text(text: str) -> str:
    if "提醒我" not in text:
        return text.strip()
    return text.split("提醒我", 1)[1].strip("，,。 ") or text.strip()


def _normalize_key(text: str) -> str:
    from datetime import datetime
    normalized = re.sub(r"\s+", "", text.lower())
    # 暴力打破记忆去重，强制让每一条飞书上发的"提醒我吃饭"都成为独立任务
    unique_suffix = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{normalized[:30]}_{unique_suffix}" or "general"


def _category_from_forget_query(query: str) -> str | None:
    if "提醒" in query:
        return "ReminderPreferenceMemory"
    if "偏好" in query or "格式" in query or "喜欢" in query:
        return "WorkPreferenceMemory"
    return None


def _is_generic_reminder_cancel_query(query: str) -> bool:
    normalized = query.strip("，,。 了")
    return normalized in {"", "这个", "这条", "它", "此提醒"}
