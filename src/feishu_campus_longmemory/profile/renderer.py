from __future__ import annotations

from typing import Any

DIMENSION_TITLES = {
    "work_identity": "工作身份",
    "current_work_stage": "当前阶段",
    "work_preferences": "工作偏好",
    "communication_style": "沟通风格",
    "tool_usage": "工具使用",
    "reminder_and_proactive_service": "主动服务",
    "life_preferences": "生活偏好",
    "other_profile_traits": "其他画像",
}


class UserProfileRenderer:
    def render(self, profile_json: dict[str, Any], *, max_chars: int = 1200) -> str:
        lines = [
            "User Profile Context",
            "- 以下是长期用户画像，仅在不冲突时使用；当前用户请求优先。",
            "- 不要暴露内部 ID、原始证据或画像注入机制。",
        ]
        summary = _string_value(profile_json.get("summary"))
        if summary:
            lines.append(f"- 摘要：{summary}")

        dimensions = profile_json.get("dimensions")
        if isinstance(dimensions, dict):
            for dimension, payload in dimensions.items():
                title = DIMENSION_TITLES.get(str(dimension), str(dimension))
                claims = _claims_from_dimension(payload)
                for claim in claims:
                    lines.append(f"- {title}：{claim}")

        return _limit_markdown("\n".join(lines), max_chars=max_chars)


def _claims_from_dimension(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    claims = payload.get("claims")
    if not isinstance(claims, list):
        return []
    result: list[str] = []
    for claim in claims:
        if isinstance(claim, dict):
            text = _string_value(claim.get("text"))
        else:
            text = _string_value(claim)
        if text:
            result.append(text)
    return result


def _limit_markdown(markdown: str, *, max_chars: int) -> str:
    compacted = "\n".join(line.rstrip() for line in markdown.splitlines() if line.strip())
    if len(compacted) <= max_chars:
        return compacted
    suffix = "\n- 用户画像已截断。"
    limit = max(max_chars - len(suffix), 0)
    return compacted[:limit].rstrip() + suffix


def _string_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
