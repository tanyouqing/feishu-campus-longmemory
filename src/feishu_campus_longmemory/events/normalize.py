from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from feishu_campus_longmemory.events.privacy import redact_text
from feishu_campus_longmemory.events.types import WorkEvent


def build_event_id(source: str, source_event_id: str) -> str:
    return hashlib.sha256(f"{source}:{source_event_id}".encode("utf-8")).hexdigest()


def normalize_openclaw_event(payload: Mapping[str, Any]) -> WorkEvent:
    event_type = _openclaw_event_type(payload)
    timestamp = parse_timestamp(payload.get("timestamp"))
    context = _as_dict(payload.get("context"))
    metadata = _as_dict(context.get("metadata"))
    session_key = _first_nonempty(payload.get("sessionKey"), payload.get("session_key"))
    channel_id = _first_nonempty(payload.get("channelId"), payload.get("channel_id"), context.get("channelId"), context.get("channel_id"))
    source_event_id = _first_nonempty(
        payload.get("source_event_id"),
        payload.get("event_id"),
        payload.get("object_id"),
        metadata.get("messageId"),
        metadata.get("message_id"),
    )

    text = _extract_openclaw_text(payload, context)
    redaction = redact_text(text)
    if not source_event_id:
        source_event_id = _fallback_source_event_id(payload, event_type, session_key, timestamp)

    object_id = _first_nonempty(
        payload.get("object_id"),
        metadata.get("messageId"),
        metadata.get("message_id"),
        source_event_id,
    )
    user_id = _first_nonempty(
        payload.get("user_id"),
        metadata.get("senderId"),
        metadata.get("sender_id"),
        metadata.get("open_id"),
        metadata.get("user_id"),
        context.get("from"),
        context.get("to"),
        session_key,
        "unknown",
    )
    actor_type = _first_nonempty(payload.get("actor_type"), _infer_openclaw_actor_type(event_type))

    content_json: dict[str, Any] = {
        "source_event_id": source_event_id,
        "summary": {
            "text": redaction.text if text is not None else None,
            "redacted": redaction.redacted,
        },
        "metadata": {
            "session_key": session_key,
            "channel_id": channel_id,
            "openclaw_type": payload.get("type"),
            "openclaw_action": payload.get("action"),
            "context_metadata": _jsonable(metadata),
        },
    }

    return WorkEvent(
        event_id=build_event_id("openclaw", str(source_event_id)),
        user_id=str(user_id),
        tenant_id=_optional_str(payload.get("tenant_id")),
        source="openclaw",
        event_type=event_type,
        actor_type=str(actor_type),
        object_type=_optional_str(payload.get("object_type")) or ("message" if event_type.startswith("message:") else "tool_call"),
        object_id=_optional_str(object_id),
        work_type=str(payload.get("work_type") or "general"),
        timestamp=timestamp,
        content_json=content_json,
        privacy_level=redaction.privacy_level,
    )


def normalize_feishu_message(data: Any) -> WorkEvent:
    event = data.event
    sender = event.sender
    message = event.message
    sender_id = sender.sender_id

    user_id = _first_nonempty(
        getattr(sender_id, "open_id", None),
        getattr(sender_id, "union_id", None),
        getattr(sender_id, "user_id", None),
        "unknown",
    )
    tenant_id = _first_nonempty(
        getattr(sender, "tenant_key", None),
        getattr(data, "tenant_key", None),
        getattr(getattr(data, "header", None), "tenant_key", None),
    )
    source_event_id = _first_nonempty(
        getattr(message, "message_id", None),
        getattr(getattr(data, "header", None), "event_id", None),
    )
    if not source_event_id:
        source_event_id = _fallback_source_event_id(
            {"tenant_id": tenant_id, "user_id": user_id},
            "im.message.receive_v1",
            getattr(message, "chat_id", None),
            parse_timestamp(getattr(message, "create_time", None)),
        )

    message_type = getattr(message, "message_type", None)
    content_payload = _parse_message_content(getattr(message, "content", None))
    text = content_payload.get("text") if message_type == "text" else None
    redaction = redact_text(text)

    content_json: dict[str, Any] = {
        "source_event_id": source_event_id,
        "summary": {
            "text": redaction.text if text is not None else None,
            "message_type": message_type,
            "redacted": redaction.redacted,
        },
        "metadata": {
            "chat_id": getattr(message, "chat_id", None),
            "chat_type": getattr(message, "chat_type", None),
            "thread_id": getattr(message, "thread_id", None),
            "root_id": getattr(message, "root_id", None),
            "parent_id": getattr(message, "parent_id", None),
            "sender_type": getattr(sender, "sender_type", None),
            "feishu_event_id": getattr(getattr(data, "header", None), "event_id", None),
        },
    }

    return WorkEvent(
        event_id=build_event_id("feishu", str(source_event_id)),
        user_id=str(user_id),
        tenant_id=_optional_str(tenant_id),
        source="feishu",
        event_type="im.message.receive_v1",
        actor_type="user",
        object_type="message",
        object_id=_optional_str(getattr(message, "message_id", None)),
        work_type="general",
        timestamp=parse_timestamp(getattr(message, "create_time", None)),
        content_json=content_json,
        privacy_level=redaction.privacy_level,
    )


def parse_timestamp(value: Any) -> datetime:
    if value is None or value == "":
        return datetime.now(timezone.utc)

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    if isinstance(value, int | float) or (isinstance(value, str) and value.isdigit()):
        number = float(value)
        if number > 10_000_000_000:
            number = number / 1000
        return datetime.fromtimestamp(number, tz=timezone.utc)

    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    return datetime.now(timezone.utc)


def _openclaw_event_type(payload: Mapping[str, Any]) -> str:
    explicit_type = payload.get("event_type")
    if explicit_type:
        return str(explicit_type)

    event_type = payload.get("type")
    action = payload.get("action")
    if event_type and action:
        return f"{event_type}:{action}"

    raise ValueError("OpenClaw event payload must include event_type or type/action")


def _infer_openclaw_actor_type(event_type: str) -> str:
    if event_type == "message:sent" or "tool" in event_type:
        return "agent_on_behalf_of_user"
    return "user"


def _extract_openclaw_text(payload: Mapping[str, Any], context: Mapping[str, Any]) -> str | None:
    for candidate in (
        payload.get("text"),
        payload.get("content"),
        context.get("content"),
        context.get("bodyForAgent"),
        context.get("transcript"),
    ):
        if isinstance(candidate, str):
            return candidate
    return None


def _parse_message_content(content: Any) -> dict[str, Any]:
    if not isinstance(content, str) or not content:
        return {}
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _fallback_source_event_id(payload: Mapping[str, Any], event_type: str, session_key: Any, timestamp: datetime) -> str:
    stable_payload = json.dumps(_jsonable(payload), ensure_ascii=True, sort_keys=True, default=str)
    payload_hash = hashlib.sha256(stable_payload.encode("utf-8")).hexdigest()[:24]
    return f"{session_key or 'unknown'}:{event_type}:{timestamp.isoformat()}:{payload_hash}"


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True, default=str))

