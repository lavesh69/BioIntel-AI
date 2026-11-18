from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SENSITIVE_QUERY_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "key",
        "token",
        "access_token",
        "secret",
        "client_secret",
        "subscription-key",
    }
)
SENSITIVE_HEADER_KEYS = frozenset(
    {
        "authorization",
        "x-api-key",
        "api-key",
        "openai-organization",
        "openai-project",
    }
)


def redact_url(url: str) -> str:
    """Return a URL safe for logs, cache metadata and provenance."""
    try:
        parts = urlsplit(str(url))
    except ValueError:
        return "<invalid-url>"
    redacted: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        redacted.append((key, "REDACTED" if key.lower() in SENSITIVE_QUERY_KEYS else value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(redacted, doseq=True), parts.fragment))


def redact_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    return {
        str(key): ("REDACTED" if str(key).lower() in SENSITIVE_HEADER_KEYS else str(value))
        for key, value in (headers or {}).items()
    }


def redact_text(value: object, secrets: list[str] | tuple[str, ...] = ()) -> str:
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "REDACTED")
    text = re.sub(r"sk-[A-Za-z0-9_\-]{12,}", "sk-REDACTED", text)
    text = re.sub(r"(?i)(api[_-]?key|access[_-]?token|client[_-]?secret)=([^&\s]+)", r"\1=REDACTED", text)
    return text
