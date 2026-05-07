from __future__ import annotations

import json
import logging
import re
from typing import Any

from feishu_campus_longmemory.config import Settings
from feishu_campus_longmemory.events.privacy import redact_text
from feishu_campus_longmemory.events.types import WorkEvent
from feishu_campus_longmemory.profile.store import UserProfileStore
from feishu_campus_longmemory.profile.types import PROFILE_DIMENSIONS, UserProfilePatch

logger = logging.getLogger(__name__)

STRONG_REDACTION_MARKERS = (
    "[REDACTED_SECRET]",
    "[REDACTED_PRIVATE_KEY]",
    "[REDACTED_EMAIL]",
    "[REDACTED_PHONE]",
)
DELETE_INTENT_MARKERS = ("忘掉", "忘记", "删除", "别提醒", "不要提醒", "不用提醒", "取消提醒", "不要再提醒")
MAX_PROFILE_CLAIM_CHARS = 180

PROFILE_LLM_SYSTEM_PROMPT = """你是用户画像抽取器，只从单条已脱敏事件文本中抽取长期用户建模信息。
你不能写库、删除、更新或执行任何副作用，只能返回 JSON。
可以抽取广义用户画像：职位/角色、当前阶段工作、工作偏好、沟通偏好、工具偏好、主动提醒偏好、饮食偏好、非敏感生活习惯等。
不要抽取密码、token、密钥、联系方式、身份证件、私钥、原始证据 ID、一次性闲聊或删除/忘记/取消类指令。
dimension 只允许：
work_identity, current_work_stage, work_preferences, communication_style, tool_usage,
reminder_and_proactive_service, life_preferences, other_profile_traits。
返回格式必须是 JSON object：
{"patches":[{"dimension":"","claim":"","confidence":0.0,"evidence_text":""}]}
要求：
- claim 用中文短句概括，必须是长期画像信息。
- confidence 必须在 0 到 1 之间。
- evidence_text 必须逐字来自用户事件文本，不能改写或补全。
如果没有可靠画像，返回 {"patches":[]}。"""


class UserProfileExtractor:
    def __init__(self, settings: Settings | None = None, llm_extractor: Any | None = None) -> None:
        self._settings = settings
        self._llm_extractor = llm_extractor if llm_extractor is not None else _build_llm_extractor(settings)

    def process_event(self, event: WorkEvent, store: UserProfileStore) -> list[UserProfilePatch]:
        text = _event_text(event)
        if not text or _contains_redaction_marker(text) or _contains_delete_intent(text):
            return []
        if self._llm_extractor is None:
            return []

        try:
            candidates = self._llm_extractor.extract_patches(text)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("LLM user profile extraction failed: %s", exc.__class__.__name__)
            return []

        patches = [_validated_patch(candidate, text) for candidate in candidates]
        patches = [patch for patch in patches if patch is not None]
        if not patches:
            return []

        try:
            store.upsert_profile(
                user_id=event.user_id,
                tenant_id=event.tenant_id,
                patches=patches,
                event_id=event.event_id,
            )
        except ValueError as exc:
            logger.warning("User profile patches rejected by store: %s", exc.__class__.__name__)
            return []
        return patches


class OpenAICompatibleUserProfilePatchExtractor:
    def __init__(self, settings: Settings) -> None:
        from openai import OpenAI

        self._settings = settings
        self._client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
        )

    def extract_patches(self, text: str) -> list[UserProfilePatch]:
        response = self._client.chat.completions.create(
            model=self._settings.llm_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": PROFILE_LLM_SYSTEM_PROMPT},
                {"role": "user", "content": f"事件文本：\n{text}"},
            ],
        )
        content = response.choices[0].message.content or ""
        return _parse_profile_patches(content)


def _build_llm_extractor(settings: Settings | None) -> OpenAICompatibleUserProfilePatchExtractor | None:
    if settings is None or not settings.llm_extraction_enabled or not settings.llm_api_key:
        return None
    try:
        return OpenAICompatibleUserProfilePatchExtractor(settings)
    except Exception as exc:  # pragma: no cover - startup safety net
        logger.warning("LLM user profile extractor unavailable: %s", exc.__class__.__name__)
        return None


def _parse_profile_patches(content: str) -> list[UserProfilePatch]:
    payload = json.loads(_strip_json_fence(content.strip()))
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("patches", [])
    else:
        return []
    if not isinstance(items, list):
        return []

    patches: list[UserProfilePatch] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        patch = _patch_from_dict(item)
        if patch is not None:
            patches.append(patch)
    return patches


def _patch_from_dict(item: dict[str, Any]) -> UserProfilePatch | None:
    try:
        confidence = float(item.get("confidence", 0))
    except (TypeError, ValueError):
        return None
    return UserProfilePatch(
        dimension=_string_value(item.get("dimension")),
        claim=_string_value(item.get("claim")),
        confidence=confidence,
        evidence_text=_string_value(item.get("evidence_text")),
    )


def _validated_patch(patch: UserProfilePatch, text: str) -> UserProfilePatch | None:
    claim = " ".join(patch.claim.split())
    evidence_text = patch.evidence_text.strip()
    if patch.dimension not in PROFILE_DIMENSIONS:
        return None
    if not claim or len(claim) > MAX_PROFILE_CLAIM_CHARS:
        return None
    if not 0 <= patch.confidence <= 1:
        return None
    if not evidence_text or not _evidence_is_in_text(evidence_text, text):
        return None
    if _contains_sensitive_value(claim, evidence_text):
        return None
    return UserProfilePatch(
        dimension=patch.dimension,
        claim=claim,
        confidence=patch.confidence,
        evidence_text=evidence_text,
    )


def _event_text(event: WorkEvent) -> str | None:
    summary = event.content_json.get("summary")
    if isinstance(summary, dict):
        text = summary.get("text")
        return text if isinstance(text, str) else None
    return None


def _contains_redaction_marker(text: str) -> bool:
    return any(marker in text for marker in STRONG_REDACTION_MARKERS) or "[REDACTED_" in text


def _contains_delete_intent(text: str) -> bool:
    return any(marker in text for marker in DELETE_INTENT_MARKERS)


def _contains_sensitive_value(*values: str) -> bool:
    for value in values:
        if not value:
            continue
        if _contains_redaction_marker(value) or redact_text(value).redacted:
            return True
    return False


def _evidence_is_in_text(evidence_text: str, text: str) -> bool:
    return evidence_text in text or _compact(evidence_text) in _compact(text)


def _strip_json_fence(value: str) -> str:
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    return value


def _string_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _compact(value: str) -> str:
    return "".join(value.lower().split())
