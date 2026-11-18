from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from biointel.integrations.cache import ExternalResponseCache


class ExternalServiceError(RuntimeError):
    """Raised when a remote scientific database request fails safely."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    content_type: str


Transport = Callable[[str, float, dict[str, str]], HttpResponse]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE_DIRECTORY = PROJECT_ROOT / "cache" / "external"
DEFAULT_CACHE_TTL_SECONDS = 24 * 60 * 60
MAX_REMOTE_RESPONSE_BYTES = 50 * 1024 * 1024


def default_transport(
    url: str,
    timeout: float,
    headers: dict[str, str],
) -> HttpResponse:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_REMOTE_RESPONSE_BYTES + 1)
            if len(body) > MAX_REMOTE_RESPONSE_BYTES:
                raise ExternalServiceError("Remote response exceeds the 50 MB safety limit.")
            return HttpResponse(
                status=int(response.status),
                body=body,
                content_type=response.headers.get_content_type(),
            )
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")[:500]
        raise ExternalServiceError(f"Remote service returned HTTP {exc.code}: {message}") from exc
    except URLError as exc:
        raise ExternalServiceError(f"Remote service is unavailable: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ExternalServiceError("Remote request timed out.") from exc


def _fetch_with_cache(
    url: str,
    timeout: float,
    headers: dict[str, str],
    transport: Transport,
    cache_directory: str | Path | None,
    cache_ttl_seconds: float,
    allow_stale_on_error: bool,
) -> HttpResponse:
    use_cache = transport is default_transport
    cache = ExternalResponseCache(cache_directory or DEFAULT_CACHE_DIRECTORY) if use_cache else None
    cached = cache.get(url) if cache is not None else None

    if cached is not None and cached.is_fresh(cache_ttl_seconds):
        return HttpResponse(
            status=200,
            body=cache.read_bytes(cached),
            content_type=cached.content_type,
        )

    try:
        response = transport(url, timeout, headers)
    except ExternalServiceError:
        if cache is not None and cached is not None and allow_stale_on_error:
            return HttpResponse(
                status=200,
                body=cache.read_bytes(cached),
                content_type=cached.content_type,
            )
        raise

    if response.status == 200 and cache is not None:
        cache.put(
            url,
            response.body,
            response.content_type,
        )
    return response


def get_text(
    url: str,
    timeout: float = 15.0,
    transport: Transport = default_transport,
    cache_directory: str | Path | None = None,
    cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
    allow_stale_on_error: bool = True,
) -> str:
    response = _fetch_with_cache(
        url,
        timeout,
        {
            "Accept": "text/plain",
            "User-Agent": "BioIntel-AI/0.9 research-use",
        },
        transport,
        cache_directory,
        cache_ttl_seconds,
        allow_stale_on_error,
    )
    if response.status != 200:
        raise ExternalServiceError(f"Unexpected HTTP status: {response.status}")
    try:
        return response.body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExternalServiceError("Remote service returned invalid UTF-8 text.") from exc


def get_json(
    url: str,
    timeout: float = 15.0,
    transport: Transport = default_transport,
    cache_directory: str | Path | None = None,
    cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
    allow_stale_on_error: bool = True,
) -> dict[str, object]:
    response = _fetch_with_cache(
        url,
        timeout,
        {
            "Accept": "application/json",
            "User-Agent": "BioIntel-AI/0.9 research-use",
        },
        transport,
        cache_directory,
        cache_ttl_seconds,
        allow_stale_on_error,
    )
    if response.status != 200:
        raise ExternalServiceError(f"Unexpected HTTP status: {response.status}")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ExternalServiceError("Remote service returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise ExternalServiceError("Remote service returned an unexpected data structure.")
    return payload
