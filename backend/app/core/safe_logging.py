from collections.abc import Mapping
import re
from typing import Any


SENSITIVE_LOG_KEYS = frozenset(
    {
        "api_key",
        "token",
        "password",
        "secret",
        "authorization",
        "access_key",
    }
)
MAX_LOG_VALUE_LENGTH = 200
MASKED_LOG_VALUE = "***"
RECURSION_LOG_VALUE = "<recursion>"
SENSITIVE_TEXT_PATTERNS = (
    re.compile(
        r"(?P<prefix>\bAuthorization\s*[:=]\s*)(?P<value>[^,\s;]+(?:\s+[^,\s;]+)?)",
        re.IGNORECASE,
    ),
    re.compile(r"(?P<prefix>\bBearer\s+)(?P<value>[A-Za-z0-9._~+/=-]+)", re.IGNORECASE),
    re.compile(
        r"(?P<prefix>\b(?:api[_-]?key|token|password|secret|access[_-]?key)\b\s*[:=]\s*)"
        r"(?P<quote>['\"]?)(?P<value>[^'\"\s,;]+)(?P=quote)",
        re.IGNORECASE,
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
)


def safe_log_data(value: Any, max_length: int = MAX_LOG_VALUE_LENGTH) -> Any:
    """Return a log-safe copy of nested data without mutating the original value."""

    return _safe_log_value(value, key=None, max_length=max_length, seen=set())


def safe_log_field(key: str, value: Any, max_length: int = MAX_LOG_VALUE_LENGTH) -> Any:
    """Return a log-safe value using the provided field name for masking decisions."""

    return _safe_log_value(value, key=key, max_length=max_length, seen=set())


def mask_sensitive_text(value: str) -> str:
    """Mask secret-looking substrings in free-form log text."""

    masked = str(value)
    for pattern in SENSITIVE_TEXT_PATTERNS:
        masked = pattern.sub(_mask_match, masked)
    return masked


def _safe_log_value(
    value: Any,
    key: str | None,
    max_length: int,
    seen: set[int],
) -> Any:
    if key is not None and is_sensitive_log_key(key):
        return MASKED_LOG_VALUE

    if isinstance(value, Mapping):
        value_id = id(value)
        if value_id in seen:
            return RECURSION_LOG_VALUE
        seen.add(value_id)
        try:
            return {
                nested_key: _safe_log_value(
                    nested_value,
                    key=str(nested_key),
                    max_length=max_length,
                    seen=seen,
                )
                for nested_key, nested_value in value.items()
            }
        finally:
            seen.remove(value_id)

    if isinstance(value, list):
        value_id = id(value)
        if value_id in seen:
            return RECURSION_LOG_VALUE
        seen.add(value_id)
        try:
            return [
                _safe_log_value(item, key=None, max_length=max_length, seen=seen)
                for item in value
            ]
        finally:
            seen.remove(value_id)

    if isinstance(value, tuple):
        value_id = id(value)
        if value_id in seen:
            return RECURSION_LOG_VALUE
        seen.add(value_id)
        try:
            return tuple(
                _safe_log_value(item, key=None, max_length=max_length, seen=seen)
                for item in value
            )
        finally:
            seen.remove(value_id)

    if isinstance(value, str):
        masked_value = mask_sensitive_text(value)
        if len(masked_value) > max_length:
            return f"{masked_value[:max_length]}..."
        return masked_value

    return value


def _mask_match(match: re.Match[str]) -> str:
    prefix = match.groupdict().get("prefix")
    if prefix is not None:
        quote = match.groupdict().get("quote") or ""
        return f"{prefix}{quote}{MASKED_LOG_VALUE}{quote}"
    return MASKED_LOG_VALUE


def is_sensitive_log_key(key: str) -> bool:
    normalized_key = key.strip().lower()
    if normalized_key in SENSITIVE_LOG_KEYS:
        return True

    return any(
        normalized_key.endswith(f"_{sensitive_key}") for sensitive_key in SENSITIVE_LOG_KEYS
    )
