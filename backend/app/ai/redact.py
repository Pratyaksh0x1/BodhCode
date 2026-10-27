"""Zero-trust secret redaction utility for logs, LLM messages, and LangSmith traces."""

import re
from typing import Any

# Sensitive dictionary key substrings (case-insensitive)
SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "authorization",
    "token",
    "api_key",
    "apikey",
    "secret",
    "password",
    "cookie",
)

# Token patterns to detect and mask in strings
# Covers GitHub tokens, Groq keys, LangSmith keys, and Bearer headers
TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ghp_[A-Za-z0-9_]{10,}"),
    re.compile(r"gho_[A-Za-z0-9_]{10,}"),
    re.compile(r"ghu_[A-Za-z0-9_]{10,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{10,}"),
    re.compile(r"gsk_[A-Za-z0-9]{10,}"),
    re.compile(r"lsv2_[A-Za-z0-9_]{10,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE),
)

REDACTED_PLACEHOLDER: str = "[REDACTED]"


def _is_sensitive_key(key: str) -> bool:
    """Check if dictionary key matches sensitive name pattern."""
    k_lower = key.lower()
    return any(sub in k_lower for sub in SENSITIVE_KEY_SUBSTRINGS)


def _redact_string(text: str) -> str:
    """Mask any sensitive token pattern found inside a string."""
    result = text
    for pattern in TOKEN_PATTERNS:
        result = pattern.sub(REDACTED_PLACEHOLDER, result)
    return result


def redact(obj: Any) -> Any:
    """Recursively redact secrets and sensitive values from nested structures.

    Masks token shapes (GitHub, Groq, LangSmith, Bearer auth) and values of
    sensitive dict keys (token, secret, authorization, password, cookie, api_key).
    Safe for arbitrary data structures (dicts, lists, tuples, sets, primitives).
    """
    if isinstance(obj, str):
        return _redact_string(obj)

    if isinstance(obj, dict):
        redacted_dict: dict[Any, Any] = {}
        for k, v in obj.items():
            str_key = str(k)
            if _is_sensitive_key(str_key):
                redacted_dict[k] = REDACTED_PLACEHOLDER
            else:
                redacted_dict[k] = redact(v)
        return redacted_dict

    if isinstance(obj, list):
        return [redact(item) for item in obj]

    if isinstance(obj, tuple):
        return tuple(redact(item) for item in obj)

    if isinstance(obj, set):
        return {redact(item) for item in obj}

    return obj
