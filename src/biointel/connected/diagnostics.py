from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from biointel.connected.config import settings_from_environment
from biointel.connected.http import ConnectedHttpClient, ConnectedServiceError
from biointel.connected.providers import PROVIDERS, ConnectedProviderService
from biointel.connected.secrets import redact_text


def _openai_headers(api_key: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    project = os.getenv("OPENAI_PROJECT", "").strip()
    organization = os.getenv("OPENAI_ORGANIZATION", "").strip()
    if project:
        headers["OpenAI-Project"] = project
    if organization:
        headers["OpenAI-Organization"] = organization
    return headers


def test_openai_connection(
    project_root: str | Path,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> dict[str, object]:
    settings = settings_from_environment()
    key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
    selected_model = (model or settings.openai_model).strip()
    checked_at = datetime.now(UTC).isoformat(timespec="seconds")
    if not key:
        return {
            "provider": "openai",
            "available": False,
            "configured": False,
            "status": "key_required",
            "model": selected_model,
            "model_visible": False,
            "latency_ms": 0.0,
            "error_type": "configuration_error",
            "error": "OPENAI_API_KEY is not configured.",
            "checked_at_utc": checked_at,
        }
    host = (urlsplit(settings.openai_base_url).hostname or "api.openai.com").lower().rstrip(".")
    if host != "api.openai.com" and not settings.openai_custom_base_url_allowed:
        return {
            "provider": "openai",
            "available": False,
            "configured": True,
            "status": "blocked_custom_base_url",
            "model": selected_model,
            "model_visible": False,
            "latency_ms": 0.0,
            "error_type": "network_policy",
            "error": "Custom OpenAI base URLs are blocked. Restore https://api.openai.com/v1 or explicitly opt in with OPENAI_ALLOW_CUSTOM_BASE_URL=1.",
            "checked_at_utc": checked_at,
        }
    client = ConnectedHttpClient(
        Path(project_root) / "cache" / "connected_diagnostics",
        timeout_seconds=settings.timeout_seconds,
        connect_timeout_seconds=settings.connect_timeout_seconds,
        retries=1,
        cache_ttl_seconds=60,
        maximum_redirects=0,
    )
    try:
        payload, response = client.get_json(
            "openai",
            f"{settings.openai_base_url}/models",
            allowed_hosts={host},
            headers=_openai_headers(key),
            requests_per_second=2,
            cache_response=False,
            allow_stale_on_error=False,
            maximum_bytes=5 * 1024 * 1024,
        )
        model_ids = {
            str(row.get("id", ""))
            for row in payload.get("data", [])
            if isinstance(row, dict)
        } if isinstance(payload, dict) else set()
        return {
            "provider": "openai",
            "available": True,
            "configured": True,
            "status": "connected",
            "model": selected_model,
            "model_visible": selected_model in model_ids,
            "visible_model_count": len(model_ids),
            "latency_ms": response.elapsed_ms,
            "request_id": response.request_id,
            "error_type": "" if selected_model in model_ids else "model_not_listed",
            "error": "" if selected_model in model_ids else (
                f"The key is valid, but model {selected_model!r} was not present in the models list available to this project."
            ),
            "checked_at_utc": checked_at,
        }
    except ConnectedServiceError as exc:
        return {
            "provider": "openai",
            "available": False,
            "configured": True,
            "status": "failed",
            "model": selected_model,
            "model_visible": False,
            "latency_ms": 0.0,
            "http_status": exc.status_code,
            "error_type": exc.category,
            "error": redact_text(exc, [key]),
            "checked_at_utc": checked_at,
        }


def test_provider_connections(
    project_root: str | Path,
    providers: list[str] | None = None,
) -> dict[str, object]:
    selected = providers or list(PROVIDERS)
    service = ConnectedProviderService(project_root, persist_queries=False)
    rows = service.probe_all(selected)
    available = sum(1 for row in rows if row.get("available"))
    return {
        "checked_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "requested": len(selected),
        "available": available,
        "failed": len(selected) - available,
        "results": rows,
    }
