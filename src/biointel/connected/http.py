from __future__ import annotations

import email.utils
import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from biointel.connected.secrets import redact_text, redact_url
from biointel.integrations.cache import ExternalResponseCache
from biointel.internet.network_policy import (
    InternetPolicy,
    NetworkPolicyError,
    validate_public_https_url,
)


class ConnectedServiceError(RuntimeError):
    """Raised when an approved external service cannot be queried safely."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "provider_error",
        status_code: int | None = None,
        provider: str = "",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.status_code = status_code
        self.provider = provider
        self.retryable = retryable


@dataclass(frozen=True)
class ConnectedHttpResponse:
    url: str
    status_code: int
    content_type: str
    body: bytes
    sha256: str
    cache_status: str
    elapsed_ms: float
    request_id: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConnectedServiceError(
                "Provider returned invalid JSON.", category="invalid_response"
            ) from exc

    def text(self) -> str:
        try:
            return self.body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ConnectedServiceError(
                "Provider returned invalid UTF-8 text.", category="invalid_response"
            ) from exc


class ProviderRateLimiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._last_request: dict[str, float] = {}

    def wait(self, provider: str, requests_per_second: float) -> None:
        interval = 1.0 / max(0.1, float(requests_per_second))
        with self._lock:
            previous = self._last_request.get(provider, 0.0)
            delay = interval - (time.monotonic() - previous)
            if delay > 0:
                time.sleep(delay)
            self._last_request[provider] = time.monotonic()


class ProviderCircuitBreaker:
    """In-process circuit breaker that prevents repeated provider failure storms."""

    def __init__(self, failure_threshold: int = 3, recovery_seconds: float = 60.0) -> None:
        self.failure_threshold = max(1, int(failure_threshold))
        self.recovery_seconds = max(1.0, float(recovery_seconds))
        self._lock = Lock()
        self._state: dict[str, dict[str, float | int]] = {}

    def state(self, provider: str) -> dict[str, Any]:
        key = provider.strip().lower()
        now = time.monotonic()
        with self._lock:
            item = dict(self._state.get(key, {"failures": 0, "opened_at": 0.0}))
            opened_at = float(item.get("opened_at", 0.0))
            open_now = bool(opened_at and now - opened_at < self.recovery_seconds)
            if opened_at and not open_now:
                self._state[key] = {"failures": 0, "opened_at": 0.0}
                item = {"failures": 0, "opened_at": 0.0}
            remaining = (
                max(0.0, self.recovery_seconds - (now - opened_at)) if open_now else 0.0
            )
        return {
            "provider": key,
            "failures": int(item.get("failures", 0)),
            "open": open_now,
            "retry_after_seconds": round(remaining, 3),
            "failure_threshold": self.failure_threshold,
            "recovery_seconds": self.recovery_seconds,
        }

    def allow_request(self, provider: str) -> bool:
        return not bool(self.state(provider)["open"])

    def record_success(self, provider: str) -> None:
        with self._lock:
            self._state[provider.strip().lower()] = {"failures": 0, "opened_at": 0.0}

    def record_failure(self, provider: str) -> None:
        key = provider.strip().lower()
        with self._lock:
            item = self._state.setdefault(key, {"failures": 0, "opened_at": 0.0})
            failures = int(item.get("failures", 0)) + 1
            item["failures"] = failures
            if failures >= self.failure_threshold:
                item["opened_at"] = time.monotonic()


_LIMITER = ProviderRateLimiter()
_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
_REDIRECT_STATUS = frozenset({301, 302, 303, 307, 308})


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0.0, (parsed - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _classify_http_status(status_code: int) -> tuple[str, bool]:
    if status_code in {401, 403}:
        return "authentication_error", False
    if status_code == 404:
        return "not_found", False
    if status_code == 429:
        return "rate_limited", True
    if status_code >= 500:
        return "provider_unavailable", True
    if status_code >= 400:
        return "invalid_request", False
    return "provider_error", False


def _enforce_allowed_host(url: str, allowed_hosts: set[str]) -> None:
    hostname = (urlsplit(url).hostname or "").lower().rstrip(".")
    approved = {host.lower().rstrip(".") for host in allowed_hosts}
    if hostname not in approved:
        raise ConnectedServiceError(
            f"Outbound host {hostname or '<missing>'} is not approved for this provider.",
            category="network_policy",
        )


class ConnectedHttpClient:
    def __init__(
        self,
        cache_directory: str | Path,
        *,
        timeout_seconds: float = 30.0,
        connect_timeout_seconds: float = 8.0,
        retries: int = 3,
        cache_ttl_seconds: int = 86400,
        policy: InternetPolicy | None = None,
        maximum_redirects: int = 2,
        transport: httpx.BaseTransport | None = None,
        circuit_failure_threshold: int = 3,
        circuit_recovery_seconds: float = 60.0,
    ) -> None:
        self.cache = ExternalResponseCache(cache_directory)
        self.timeout_seconds = max(3.0, float(timeout_seconds))
        self.connect_timeout_seconds = max(1.0, float(connect_timeout_seconds))
        self.retries = max(0, int(retries))
        self.cache_ttl_seconds = max(60, int(cache_ttl_seconds))
        self.policy = policy
        self.maximum_redirects = min(5, max(0, int(maximum_redirects)))
        self.transport = transport
        self.circuit_breaker = ProviderCircuitBreaker(
            failure_threshold=circuit_failure_threshold,
            recovery_seconds=circuit_recovery_seconds,
        )

    @staticmethod
    def _cache_key(method: str, url: str, json_body: dict[str, Any] | None) -> str:
        safe_url = redact_url(url)
        if not json_body:
            return f"{method.upper()}::{safe_url}"
        body_digest = hashlib.sha256(
            json.dumps(json_body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        return f"{method.upper()}::{safe_url}::{body_digest}"

    @staticmethod
    def _request_id(headers: httpx.Headers | dict[str, str]) -> str:
        lowered = {str(key).lower(): str(value) for key, value in headers.items()}
        for key in ("x-request-id", "request-id", "x-amzn-requestid", "cf-ray"):
            if lowered.get(key):
                return lowered[key][:200]
        return ""

    def _cached_response(
        self,
        *,
        safe_url: str,
        cached: Any,
        cache_status: str,
        started: float,
    ) -> ConnectedHttpResponse:
        body = self.cache.read_bytes(cached)
        return ConnectedHttpResponse(
            url=redact_url(safe_url),
            status_code=200,
            content_type=cached.content_type,
            body=body,
            sha256=hashlib.sha256(body).hexdigest(),
            cache_status=cache_status,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    def request(
        self,
        provider: str,
        method: str,
        url: str,
        *,
        allowed_hosts: set[str],
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        requests_per_second: float = 3.0,
        allow_stale_on_error: bool = True,
        maximum_bytes: int = 20 * 1024 * 1024,
        cache_response: bool = True,
        expected_content_types: tuple[str, ...] = ("application/json", "text/json", "text/plain"),
    ) -> ConnectedHttpResponse:
        method = method.upper().strip()
        if method not in {"GET", "POST"}:
            raise ConnectedServiceError("Only GET and POST provider requests are supported.", category="invalid_request")
        _enforce_allowed_host(url, allowed_hosts)
        safe_url = validate_public_https_url(
            url,
            policy=self.policy,
            allowed_hosts=allowed_hosts,
            resolve_dns=False,
        )
        cache_key = self._cache_key(method, safe_url, json_body)
        cached = self.cache.get(cache_key) if cache_response else None
        started = time.perf_counter()
        if cached is not None and cached.is_fresh(self.cache_ttl_seconds):
            return self._cached_response(
                safe_url=safe_url,
                cached=cached,
                cache_status="fresh_cache",
                started=started,
            )

        if not self.circuit_breaker.allow_request(provider):
            if cached is not None and allow_stale_on_error:
                return self._cached_response(
                    safe_url=safe_url,
                    cached=cached,
                    cache_status="stale_cache_circuit_open",
                    started=started,
                )
            state = self.circuit_breaker.state(provider)
            raise ConnectedServiceError(
                f"{provider} is temporarily paused after repeated failures; retry in "
                f"{state['retry_after_seconds']:.0f} seconds.",
                category="circuit_open",
                provider=provider,
                retryable=True,
            )

        request_headers = {
            "Accept": "application/json",
            "User-Agent": "BioIntel-AI/5.2 connected-research-use",
            **(headers or {}),
        }
        timeout = httpx.Timeout(
            timeout=self.timeout_seconds,
            connect=self.connect_timeout_seconds,
            read=self.timeout_seconds,
            write=self.timeout_seconds,
            pool=self.connect_timeout_seconds,
        )
        last_error: Exception | None = None
        secret_values = [
            value
            for key, value in request_headers.items()
            if key.lower() in {"authorization", "x-api-key", "api-key"}
        ]

        for attempt in range(self.retries + 1):
            _LIMITER.wait(provider, requests_per_second)
            current_url = safe_url
            current_method = method
            redirect_count = 0
            try:
                # Resolve and reject non-public addresses immediately before the network call.
                validate_public_https_url(
                    current_url,
                    policy=self.policy,
                    allowed_hosts=allowed_hosts,
                    resolve_dns=self.transport is None,
                )
                with httpx.Client(
                    timeout=timeout,
                    follow_redirects=False,
                    transport=self.transport,
                    trust_env=True,
                ) as client:
                    while True:
                        with client.stream(
                            current_method,
                            current_url,
                            headers=request_headers,
                            json=json_body if current_method == "POST" else None,
                        ) as response:
                            if response.status_code in _REDIRECT_STATUS:
                                location = response.headers.get("location", "")
                                if not location:
                                    raise ConnectedServiceError(
                                        f"{provider} returned a redirect without a destination.",
                                        category="invalid_response",
                                        status_code=response.status_code,
                                        provider=provider,
                                    )
                                if redirect_count >= self.maximum_redirects:
                                    raise ConnectedServiceError(
                                        f"{provider} exceeded the approved redirect limit.",
                                        category="redirect_error",
                                        status_code=response.status_code,
                                        provider=provider,
                                    )
                                if current_method != "GET" and response.status_code in {301, 302, 303}:
                                    raise ConnectedServiceError(
                                        f"{provider} attempted an unsafe method-changing redirect.",
                                        category="redirect_error",
                                        status_code=response.status_code,
                                        provider=provider,
                                    )
                                next_url = urljoin(current_url, location)
                                _enforce_allowed_host(next_url, allowed_hosts)
                                validate_public_https_url(
                                    next_url,
                                    policy=self.policy,
                                    allowed_hosts=allowed_hosts,
                                    resolve_dns=self.transport is None,
                                )
                                current_url = next_url
                                redirect_count += 1
                                continue

                            if response.status_code >= 400:
                                category, retryable = _classify_http_status(response.status_code)
                                preview = b""
                                try:
                                    preview = next(response.iter_bytes(), b"")[:1000]
                                except Exception:
                                    preview = b""
                                detail = redact_text(preview.decode("utf-8", errors="replace"), secret_values)
                                error = ConnectedServiceError(
                                    f"{provider} returned HTTP {response.status_code}: {detail or response.reason_phrase}",
                                    category=category,
                                    status_code=response.status_code,
                                    provider=provider,
                                    retryable=retryable,
                                )
                                retry_after = _retry_after_seconds(response.headers.get("retry-after"))
                                setattr(error, "retry_after", retry_after)
                                raise error

                            content_type = response.headers.get("content-type", "application/octet-stream")
                            mime = content_type.split(";", 1)[0].strip().lower()
                            if expected_content_types and not any(mime.startswith(item) for item in expected_content_types):
                                raise ConnectedServiceError(
                                    f"{provider} returned unexpected content type {content_type!r}.",
                                    category="invalid_response",
                                    status_code=response.status_code,
                                    provider=provider,
                                )
                            chunks: list[bytes] = []
                            total = 0
                            for chunk in response.iter_bytes():
                                total += len(chunk)
                                if total > maximum_bytes:
                                    raise ConnectedServiceError(
                                        "Provider response exceeded the configured safety limit.",
                                        category="response_too_large",
                                        provider=provider,
                                    )
                                chunks.append(chunk)
                            body = b"".join(chunks)
                            final_url = redact_url(str(response.url))
                            if cache_response:
                                self.cache.put(cache_key, body, content_type)
                            self.circuit_breaker.record_success(provider)
                            return ConnectedHttpResponse(
                                url=final_url,
                                status_code=int(response.status_code),
                                content_type=content_type,
                                body=body,
                                sha256=hashlib.sha256(body).hexdigest(),
                                cache_status="network",
                                elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
                                request_id=self._request_id(response.headers),
                                headers={
                                    key.lower(): value
                                    for key, value in response.headers.items()
                                    if key.lower() in {"etag", "last-modified", "x-request-id", "retry-after", "x-ratelimit-remaining"}
                                },
                            )
            except ConnectedServiceError as exc:
                last_error = exc
                retryable = exc.retryable
                if not retryable or attempt >= self.retries:
                    break
                retry_after = getattr(exc, "retry_after", None)
                delay = retry_after if retry_after is not None else min(8.0, 0.5 * (2**attempt) + random.uniform(0, 0.2))
                time.sleep(min(15.0, max(0.0, delay)))
            except NetworkPolicyError as exc:
                last_error = ConnectedServiceError(
                    redact_text(exc, secret_values), category="network_policy", provider=provider
                )
                break
            except httpx.TimeoutException:
                last_error = ConnectedServiceError(
                    f"{provider} timed out after {self.timeout_seconds:.0f} seconds.",
                    category="timeout",
                    provider=provider,
                    retryable=True,
                )
                if attempt < self.retries:
                    time.sleep(min(8.0, 0.5 * (2**attempt)))
                    continue
                break
            except httpx.ConnectError as exc:
                message = redact_text(exc, secret_values)
                category = "dns_error" if "name resolution" in message.lower() or "nodename" in message.lower() else "connection_error"
                last_error = ConnectedServiceError(
                    f"{provider} connection failed: {message}",
                    category=category,
                    provider=provider,
                    retryable=True,
                )
                if attempt < self.retries:
                    time.sleep(min(8.0, 0.5 * (2**attempt)))
                    continue
                break
            except httpx.HTTPError as exc:
                last_error = ConnectedServiceError(
                    f"{provider} request failed: {redact_text(exc, secret_values)}",
                    category="connection_error",
                    provider=provider,
                    retryable=True,
                )
                if attempt < self.retries:
                    time.sleep(min(8.0, 0.5 * (2**attempt)))
                    continue
                break

        if (
            isinstance(last_error, ConnectedServiceError)
            and last_error.category
            in {"provider_unavailable", "rate_limited", "timeout", "connection_error", "dns_error"}
        ):
            self.circuit_breaker.record_failure(provider)

        if cached is not None and allow_stale_on_error:
            return self._cached_response(
                safe_url=safe_url,
                cached=cached,
                cache_status="stale_cache",
                started=started,
            )
        if isinstance(last_error, ConnectedServiceError):
            raise last_error
        raise ConnectedServiceError(
            f"{provider} request failed safely: {redact_text(last_error, secret_values)}",
            category="provider_error",
            provider=provider,
        )


    def circuit_state(self, provider: str) -> dict[str, Any]:
        return self.circuit_breaker.state(provider)

    def get_json(
        self,
        provider: str,
        url: str,
        *,
        allowed_hosts: set[str],
        **kwargs: Any,
    ) -> tuple[Any, ConnectedHttpResponse]:
        response = self.request(provider, "GET", url, allowed_hosts=allowed_hosts, **kwargs)
        return response.json(), response

    def post_json(
        self,
        provider: str,
        url: str,
        *,
        allowed_hosts: set[str],
        json_body: dict[str, Any],
        **kwargs: Any,
    ) -> tuple[Any, ConnectedHttpResponse]:
        response = self.request(
            provider,
            "POST",
            url,
            allowed_hosts=allowed_hosts,
            json_body=json_body,
            **kwargs,
        )
        return response.json(), response
