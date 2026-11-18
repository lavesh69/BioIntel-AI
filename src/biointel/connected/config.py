from __future__ import annotations

import os
from dataclasses import asdict, dataclass


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class ConnectedSettings:
    ollama_model: str
    ollama_base_url: str
    searxng_url: str
    searxng_auto_discovery: bool
    openai_model: str
    openai_base_url: str
    openai_configured: bool
    openai_project_configured: bool
    openai_organization_configured: bool
    openai_store_responses: bool
    openai_custom_base_url_allowed: bool
    openai_base_url_is_official: bool
    ncbi_api_key_configured: bool
    ncbi_email_configured: bool
    ncbi_tool: str
    string_caller_identity: str
    timeout_seconds: float
    connect_timeout_seconds: float
    retries: int
    cache_ttl_seconds: int
    maximum_records: int
    maximum_response_bytes: int
    maximum_redirects: int


def settings_from_environment() -> ConnectedSettings:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    return ConnectedSettings(
        ollama_model=os.getenv("BIOINTEL_OLLAMA_MODEL", "gemma3:1b").strip() or "gemma3:1b",
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/") or "http://127.0.0.1:11434",
        searxng_url=os.getenv("SEARXNG_URL", "").strip().rstrip("/"),
        searxng_auto_discovery=not bool(os.getenv("SEARXNG_URL", "").strip()),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.5").strip() or "gpt-5.5",
        openai_base_url=base_url or "https://api.openai.com/v1",
        openai_configured=bool(os.getenv("OPENAI_API_KEY", "").strip()),
        openai_project_configured=bool(os.getenv("OPENAI_PROJECT", "").strip()),
        openai_organization_configured=bool(os.getenv("OPENAI_ORGANIZATION", "").strip()),
        openai_store_responses=_bool_env("OPENAI_STORE_RESPONSES", False),
        openai_custom_base_url_allowed=_bool_env("OPENAI_ALLOW_CUSTOM_BASE_URL", False),
        openai_base_url_is_official=base_url.lower().startswith("https://api.openai.com/"),
        ncbi_api_key_configured=bool(os.getenv("NCBI_API_KEY", "").strip()),
        ncbi_email_configured=bool(os.getenv("NCBI_EMAIL", "").strip()),
        ncbi_tool=os.getenv("NCBI_TOOL", "BioIntelAI").strip() or "BioIntelAI",
        string_caller_identity=os.getenv("STRING_CALLER_IDENTITY", "BioIntelAI").strip() or "BioIntelAI",
        timeout_seconds=max(3.0, float(os.getenv("BIOINTEL_CONNECTED_TIMEOUT", "30"))),
        connect_timeout_seconds=max(1.0, float(os.getenv("BIOINTEL_CONNECTED_CONNECT_TIMEOUT", "8"))),
        retries=max(0, int(os.getenv("BIOINTEL_CONNECTED_RETRIES", "3"))),
        cache_ttl_seconds=max(60, int(os.getenv("BIOINTEL_CONNECTED_CACHE_TTL", "86400"))),
        maximum_records=min(100, max(1, int(os.getenv("BIOINTEL_CONNECTED_MAX_RECORDS", "25")))),
        maximum_response_bytes=max(
            1_048_576,
            int(os.getenv("BIOINTEL_CONNECTED_MAX_RESPONSE_MB", "20")) * 1024 * 1024,
        ),
        maximum_redirects=min(5, max(0, int(os.getenv("BIOINTEL_CONNECTED_MAX_REDIRECTS", "2")))),
    )


def public_connection_status() -> dict[str, object]:
    """Return non-secret configuration only."""
    return asdict(settings_from_environment())
