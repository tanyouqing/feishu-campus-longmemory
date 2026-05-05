from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from feishu_campus_longmemory.config import Settings
from feishu_campus_longmemory.events.privacy import redact_text
from feishu_campus_longmemory.events.types import WorkEvent
from feishu_campus_longmemory.memory.reminder import ReminderParser
from feishu_campus_longmemory.memory.store import MemoryStore
from feishu_campus_longmemory.memory.types import MemoryWrite

logger = logging.getLogger(__name__)

PREFERENCE_MARKERS = ("以后", "今后", "我喜欢", "记住")
FORGET_MARKERS = ("忘掉", "忘记")
REMINDER_CANCEL_MARKERS = ("别提醒", "不要提醒", "不用提醒", "取消提醒", "不要再提醒")
STRONG_SECRET_MARKERS = ("[REDACTED_SECRET]", "[REDACTED_PRIVATE_KEY]")
SUPPORTED_LLM_MEMORY_CATEGORIES = {"WorkPreferenceMemory", "ReminderPreferenceMemory"}
SUPPORTED_WORK_TYPES = {
    "weekly_report",
    "meeting_minutes",
    "document_writing",
    "task_followup",
    "knowledge_lookup",
    "general",
}

LLM_EXTRACTOR_NAME = "llm_v0_6"

LLM_SYSTEM_PROMPT = """你是个人工作记忆抽取器，只从单条已脱敏事件文本中抽取长期有用的工作偏好或提醒偏好候选。
你不能执行写库、删除、更新或任何副作用，只能返回 JSON。
只抽取用户明确表达或强烈暗示的稳定偏好、输出格式偏好、工作流程偏好、提醒需求。
不要抽取忘记、取消提醒、闲聊、一次性事实、账号密钥、联系方式或隐私信息。
候选类别只允许 WorkPreferenceMemory 或 ReminderPreferenceMemory。
work_type 只允许 weekly_report、meeting_minutes、document_writing、task_followup、knowledge_lookup、general。
返回格式必须是 JSON object：
{"memories":[{"memory_category":"","work_type":"","summary":"","preference":"","reminder_text":"","polarity":"","confidence":0.0,"evidence_text":""}]}
字段说明：
- WorkPreferenceMemory 使用 summary、preference、polarity；reminder_text 为空字符串。
- ReminderPreferenceMemory 使用 summary、reminder_text；preference 和 polarity 可为空字符串。
- confidence 必须在 0 到 1 之间。
- evidence_text 必须逐字来自用户事件文本，不能改写或补全。
如果没有可靠候选，返回 {"memories":[]}。"""


@dataclass(frozen=True)
class ExtractionResult:
    memory_ids: list[str]
    deleted_memory_ids: list[str]


@dataclass(frozen=True)
class LLMMemoryCandidate:
    memory_category: str
    work_type: str
    summary: str
    preference: str
    reminder_text: str
    polarity: str
    confidence: float
    evidence_text: str


class ExplicitMemoryExtractor:
    def __init__(
        self,
        reminder_parser: ReminderParser | None = None,
        settings: Settings | None = None,
        llm_extractor: Any | None = None,
    ) -> None:
        self._reminder_parser = reminder_parser or ReminderParser()
        self._llm_extractor = llm_extractor if llm_extractor is not None else _build_llm_extractor(settings)

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

        llm_memory_ids = self._process_llm_candidates(event, store, text)
        if llm_memory_ids:
            return ExtractionResult(memory_ids=llm_memory_ids, deleted_memory_ids=[])

        return self._process_rules(event, store, text)

    def _process_rules(self, event: WorkEvent, store: MemoryStore, text: str) -> ExtractionResult:
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

    def _process_llm_candidates(self, event: WorkEvent, store: MemoryStore, text: str) -> list[str]:
        if self._llm_extractor is None:
            return []

        try:
            candidates = self._llm_extractor.extract_candidates(text)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("LLM memory extraction failed; falling back to rules: %s", exc.__class__.__name__)
            return []

        memory_ids: list[str] = []
        for candidate in candidates:
            write = _candidate_to_memory_write(
                candidate,
                event=event,
                text=text,
                reminder_parser=self._reminder_parser,
            )
            if write is None:
                continue
            try:
                result = store.write_memory(write)
            except ValueError as exc:
                logger.warning("LLM memory candidate rejected by MemoryStore: %s", exc.__class__.__name__)
                continue
            memory_ids.append(result.memory["memory_id"])
        return memory_ids


class OpenAICompatibleMemoryCandidateExtractor:
    def __init__(self, settings: Settings) -> None:
        from openai import OpenAI

        self._settings = settings
        self._client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
        )

    def extract_candidates(self, text: str) -> list[LLMMemoryCandidate]:
        response = self._client.chat.completions.create(
            model=self._settings.llm_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": f"事件文本：\n{text}"},
            ],
        )
        content = response.choices[0].message.content or ""
        return _parse_llm_candidates(content)


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


def _build_llm_extractor(settings: Settings | None) -> OpenAICompatibleMemoryCandidateExtractor | None:
    if settings is None or not settings.llm_extraction_enabled or not settings.llm_api_key:
        return None
    try:
        return OpenAICompatibleMemoryCandidateExtractor(settings)
    except Exception as exc:  # pragma: no cover - startup safety net
        logger.warning("LLM memory extractor unavailable; using rules only: %s", exc.__class__.__name__)
        return None


def _candidate_to_memory_write(
    candidate: LLMMemoryCandidate,
    *,
    event: WorkEvent,
    text: str,
    reminder_parser: ReminderParser,
) -> MemoryWrite | None:
    if candidate.memory_category not in SUPPORTED_LLM_MEMORY_CATEGORIES:
        return None

    work_type = candidate.work_type.strip() or detect_work_type(text)
    if work_type not in SUPPORTED_WORK_TYPES:
        return None

    confidence = candidate.confidence
    if not 0 <= confidence <= 1:
        return None

    evidence_text = candidate.evidence_text.strip()
    if not evidence_text or not _evidence_is_in_text(evidence_text, text):
        return None

    if candidate.memory_category == "ReminderPreferenceMemory":
        reminder_text = candidate.reminder_text.strip() or candidate.summary.strip()
        summary = candidate.summary.strip() or reminder_text
        if not reminder_text or _contains_sensitive_candidate_value(summary, reminder_text, evidence_text):
            return None
        schedule = reminder_parser.parse(reminder_text) or reminder_parser.parse(text)
        return MemoryWrite(
            user_id=event.user_id,
            memory_category="ReminderPreferenceMemory",
            work_type=work_type,
            content_json={
                "summary": summary,
                "reminder_text": reminder_text,
                "normalized_key": f"{work_type}:reminder:{_normalize_key(reminder_text)}",
                "source_text": text,
                "evidence_text": evidence_text,
                "extractor": LLM_EXTRACTOR_NAME,
            },
            source_channel=event.source,
            source_signal_type="llm_candidate",
            confidence=confidence,
            status="active",
            evidence_event_ids=[event.event_id],
            reminder_schedule=schedule,
        )

    preference = candidate.preference.strip() or candidate.summary.strip()
    summary = candidate.summary.strip() or preference
    if not preference or _contains_sensitive_candidate_value(summary, preference, evidence_text):
        return None

    polarity = candidate.polarity.strip().lower()
    if polarity not in {"positive", "negative"}:
        polarity = "positive"

    return MemoryWrite(
        user_id=event.user_id,
        memory_category="WorkPreferenceMemory",
        work_type=work_type,
        content_json={
            "summary": summary,
            "preference": preference,
            "polarity": polarity,
            "normalized_key": f"{work_type}:preference",
            "source_text": text,
            "evidence_text": evidence_text,
            "extractor": LLM_EXTRACTOR_NAME,
        },
        source_channel=event.source,
        source_signal_type="llm_candidate",
        confidence=confidence,
        status="active",
        evidence_event_ids=[event.event_id],
    )


def _parse_llm_candidates(content: str) -> list[LLMMemoryCandidate]:
    raw = _strip_json_fence(content.strip())
    payload = json.loads(raw)
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("memories", [])
    else:
        return []
    if not isinstance(items, list):
        return []

    candidates: list[LLMMemoryCandidate] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        candidate = _candidate_from_dict(item)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _candidate_from_dict(item: dict[str, Any]) -> LLMMemoryCandidate | None:
    try:
        confidence = float(item.get("confidence", 0))
    except (TypeError, ValueError):
        return None
    return LLMMemoryCandidate(
        memory_category=_string_value(item.get("memory_category")),
        work_type=_string_value(item.get("work_type")),
        summary=_string_value(item.get("summary")),
        preference=_string_value(item.get("preference")),
        reminder_text=_string_value(item.get("reminder_text")),
        polarity=_string_value(item.get("polarity")),
        confidence=confidence,
        evidence_text=_string_value(item.get("evidence_text")),
    )


def _string_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _strip_json_fence(value: str) -> str:
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    return value


def _evidence_is_in_text(evidence_text: str, text: str) -> bool:
    return evidence_text in text or _compact(evidence_text) in _compact(text)


def _contains_sensitive_candidate_value(*values: str) -> bool:
    for value in values:
        if not value:
            continue
        if _contains_strong_secret(value) or redact_text(value).redacted:
            return True
    return False


def _compact(value: str) -> str:
    return "".join(value.split())
