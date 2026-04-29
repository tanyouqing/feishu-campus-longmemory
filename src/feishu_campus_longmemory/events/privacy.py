from __future__ import annotations

import re
from dataclasses import dataclass

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d -]{8,}\d)(?!\d)")
BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(password|passwd|token|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*([^\s,;]+)"
)
PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)


@dataclass(frozen=True)
class RedactionResult:
    text: str
    privacy_level: str
    redacted: bool


def redact_text(text: str | None) -> RedactionResult:
    if text is None:
        return RedactionResult(text="", privacy_level="normal", redacted=False)

    redacted = text
    redacted = PRIVATE_KEY_RE.sub("[REDACTED_PRIVATE_KEY]", redacted)
    redacted = BEARER_RE.sub("Bearer [REDACTED_SECRET]", redacted)
    redacted = SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[REDACTED_SECRET]", redacted)
    redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
    redacted = PHONE_RE.sub("[REDACTED_PHONE]", redacted)

    changed = redacted != text
    return RedactionResult(
        text=redacted,
        privacy_level="sensitive" if changed else "normal",
        redacted=changed,
    )

