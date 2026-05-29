from __future__ import annotations

import re


SENSITIVE_KEYWORDS = (
    "api key",
    "api_key",
    "apikey",
    "access token",
    "auth token",
    "bearer ",
    "client secret",
    "dashscope_api_key",
    "jwt secret",
    "modelscope_api_token",
    "password",
    "passwd",
    "private key",
    "secret",
    "token",
    "密码",
    "密钥",
    "令牌",
    "私钥",
)

SENSITIVE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(api[_-]?key|password|passwd|secret|token)\s*[:=]\s*\S+"),
)


def contains_sensitive_content(*values: str | None) -> bool:
    """Return True when text appears to contain credentials or secrets."""

    text = "\n".join(str(value or "") for value in values)
    if not text.strip():
        return False

    lowered = text.lower()
    if any(keyword in lowered for keyword in SENSITIVE_KEYWORDS):
        return True

    return any(pattern.search(text) for pattern in SENSITIVE_PATTERNS)


def normalize_memory_text(value: str, max_chars: int) -> str:
    """Normalize whitespace and cap stored memory text."""

    clean = re.sub(r"\s+", " ", str(value or "")).strip()
    return clean[:max_chars]
