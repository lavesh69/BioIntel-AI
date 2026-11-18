from __future__ import annotations

import hmac
import logging
import os
import re
from urllib.parse import parse_qsl, urlencode
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from biointel.api.security_store import ApiIdentity, ApiSecurityStore
from biointel.observability.metrics import METRICS


class RequestBodyTooLarge(RuntimeError):
    pass


class RequestSizeLimitMiddleware:
    """Enforce request size for both Content-Length and chunked request bodies."""

    def __init__(
        self,
        app,
        max_bytes: int = 16 * 1024 * 1024,
        upload_max_bytes: int = 100 * 1024 * 1024,
    ) -> None:
        self.app = app
        self.max_bytes = int(max_bytes)
        self.upload_max_bytes = max(int(upload_max_bytes), self.max_bytes)

    def _limit_for_path(self, path: str) -> int:
        upload_markers = ("/upload", "/imports", "/datasets", "/documents", "/media", "/files", "/ingest")
        return self.upload_max_bytes if any(marker in path for marker in upload_markers) else self.max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        request_limit = self._limit_for_path(str(scope.get("path", "")))
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                supplied = int(content_length.decode("ascii"))
            except (ValueError, UnicodeDecodeError):
                await JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header."})(scope, receive, send)
                return
            if supplied > request_limit:
                await JSONResponse(
                    status_code=413,
                    content={"detail": f"Request body exceeds the local {request_limit} byte limit."},
                )(scope, receive, send)
                return

        state = scope.setdefault("state", {})
        consumed = 0
        response_started = False

        async def limited_receive():
            nonlocal consumed
            message = await receive()
            if message.get("type") == "http.request":
                consumed += len(message.get("body", b""))
                state["biointel_request_bytes"] = consumed
                if consumed > request_limit:
                    raise RequestBodyTooLarge
            return message

        async def tracked_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestBodyTooLarge:
            if not response_started:
                await JSONResponse(
                    status_code=413,
                    content={"detail": f"Streamed request body exceeds the local {request_limit} byte limit."},
                )(scope, receive, send)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach conservative browser/API security and version headers."""

    def __init__(
        self,
        app,
        *,
        api_version: str = "v1",
        strict_transport_security: bool = False,
    ) -> None:
        super().__init__(app)
        self.api_version = api_version
        self.strict_transport_security = bool(strict_transport_security)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), usb=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        if self.strict_transport_security:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-BioIntel-API-Version"] = self.api_version
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'; object-src 'none'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response


class OptionalApiKeyMiddleware(BaseHTTPMiddleware):
    """Backward-compatible API key middleware with optional role-aware clients.

    A legacy BIOINTEL_API_KEY authenticates as operator. Additional clients can be
    registered in ApiSecurityStore and supplied through X-API-Key. With no configured
    keys, localhost-first no-login mode operates as a local operator.
    """

    REVIEWER_WRITE_RULES = (
        ("POST", re.compile(r"^/evidence/datasets/[^/]+/reviews$")),
        ("POST", re.compile(r"^/documents/history/[^/]+/ocr-corrections$")),
        ("POST", re.compile(r"^/documents/ask$")),
        ("POST", re.compile(r"^/documents/compare$")),
        ("POST", re.compile(r"^/jobs$")),
        ("POST", re.compile(r"^/v1/live-workspace(?:/.*)?$")),
    )

    def __init__(
        self,
        app,
        *,
        api_key: str | None,
        security_store: ApiSecurityStore | None = None,
        require_auth: bool = False,
        default_quota_per_minute: int = 120,
        excluded_paths: tuple[str, ...] = (
            "/health",
            "/ready",
            "/live",
            "/v1/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/legal",
            "/v1/mobile/bootstrap",
        ),
    ) -> None:
        super().__init__(app)
        self.api_key = api_key.strip() if api_key else None
        self.security_store = security_store
        self.require_auth = bool(require_auth)
        self.default_quota_per_minute = max(int(default_quota_per_minute), 1)
        self.excluded_paths = excluded_paths

    @staticmethod
    def _allowed(role: str, method: str, path: str) -> bool:
        if role in {"admin", "operator", "local_operator"}:
            return True
        if method.upper() in {"GET", "HEAD", "OPTIONS"}:
            return True
        if role == "reviewer" and any(
            method.upper() == allowed_method and pattern.fullmatch(path)
            for allowed_method, pattern in OptionalApiKeyMiddleware.REVIEWER_WRITE_RULES
        ):
            return True
        return False

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        excluded = any(path == item or path.startswith(item.rstrip("/") + "/") for item in self.excluded_paths)
        supplied = request.headers.get("X-API-Key", "")
        identity: ApiIdentity | None = None
        local_session_token = os.environ.get("BIOINTEL_LOCAL_SESSION_TOKEN", "").strip()

        if local_session_token and supplied and hmac.compare_digest(supplied, local_session_token):
            identity = ApiIdentity("desktop-session", "Desktop session", "local_operator", self.default_quota_per_minute, "launch_token")
        if identity is None and supplied and self.security_store is not None:
            identity = self.security_store.authenticate(supplied)
        if identity is None and self.api_key and supplied and hmac.compare_digest(supplied, self.api_key):
            identity = ApiIdentity("legacy-operator", "Legacy operator", "operator", self.default_quota_per_minute, "legacy_key")

        remote_host_mode = os.environ.get("BIOINTEL_COLLABORATION_HOST", "").strip().lower() in {"1", "true", "yes", "on"}
        allow_unauthenticated_lan = os.environ.get("BIOINTEL_ALLOW_UNAUTHENTICATED_LAN", "").strip().lower() in {"1", "true", "yes", "on"}
        client_host = request.client.host if request.client else ""
        remote_client = bool(client_host) and client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}
        # Non-loopback callers require authentication by default even if the process
        # was started outside the official supervisor. An explicit opt-in remains
        # available for isolated trusted LAN demonstrations.
        remote_api_auth_required = remote_client and not allow_unauthenticated_lan and not excluded
        authentication_required = self.require_auth or bool(self.api_key) or bool(local_session_token) or remote_api_auth_required
        if self.security_store is not None:
            authentication_required = authentication_required or self.security_store.status()["enabled_clients"] > 0

        if authentication_required and not excluded and identity is None:
            if self.security_store is not None:
                self.security_store.record_event(
                    "authentication_failed",
                    severity="warning",
                    request_id=getattr(request.state, "request_id", None),
                    subject=request.client.host if request.client else "unknown",
                    detail={"path": path, "method": request.method},
                )
            return JSONResponse(status_code=401, content={"detail": "A valid X-API-Key is required."})

        if identity is None:
            identity = ApiIdentity("local-operator", "Local no-login operator", "local_operator", self.default_quota_per_minute, "local_mode")

        if not excluded and not self._allowed(identity.role, request.method, path):
            if self.security_store is not None:
                self.security_store.record_event(
                    "authorization_denied",
                    severity="warning",
                    request_id=getattr(request.state, "request_id", None),
                    subject=identity.client_id,
                    detail={"role": identity.role, "path": path, "method": request.method},
                )
            return JSONResponse(status_code=403, content={"detail": f"Role '{identity.role}' cannot perform this operation."})

        request.state.api_identity = identity
        response = await call_next(request)
        response.headers["X-BioIntel-Access"] = "api-key" if authentication_required else "no-login-local"
        response.headers["X-BioIntel-Role"] = identity.role
        response.headers["X-BioIntel-Client"] = identity.client_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Persistent fixed-window limiter with in-memory fallback."""

    def __init__(
        self,
        app,
        *,
        requests_per_minute: int = 120,
        security_store: ApiSecurityStore | None = None,
        redis_url: str | None = None,
    ) -> None:
        super().__init__(app)
        self.limit = max(int(requests_per_minute), 1)
        self.security_store = security_store
        self.redis_url = (redis_url or "").strip()
        self.redis_client = None
        if self.redis_url:
            try:
                import redis

                self.redis_client = redis.Redis.from_url(
                    self.redis_url,
                    socket_connect_timeout=0.25,
                    socket_timeout=0.25,
                    decode_responses=True,
                )
            except (ImportError, ValueError):
                self.redis_client = None
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        identity = getattr(request.state, "api_identity", None)
        client_host = request.client.host if request.client else "unknown"
        subject = getattr(identity, "client_id", None) or client_host
        limit = min(getattr(identity, "quota_per_minute", self.limit), self.limit) if identity else self.limit
        backend = "memory"
        allowed = True
        remaining = limit
        retry_after = 60
        if self.redis_client is not None:
            try:
                now_epoch = int(time.time())
                window = now_epoch // 60
                key = f"biointel:rate:{subject}:{window}"
                pipeline = self.redis_client.pipeline(transaction=True)
                pipeline.incr(key, 1)
                pipeline.expire(key, 70)
                count, _ = pipeline.execute()
                count = int(count)
                allowed = count <= limit
                remaining = max(limit - count, 0)
                retry_after = max(1, 60 - (now_epoch % 60))
                backend = "redis"
            except Exception:
                self.redis_client = None
        persistent_sqlite = os.environ.get("BIOINTEL_PERSISTENT_RATE_LIMIT", "").strip().lower() in {"1", "true", "yes", "on"}
        if backend != "redis" and self.security_store is not None and persistent_sqlite:
            allowed, remaining, retry_after = self.security_store.allow_request(
                subject, limit, now_epoch=int(time.time())
            )
            backend = "sqlite"
        elif backend != "redis":
            now = time.monotonic()
            with self._lock:
                history = self._requests[subject]
                while history and now - history[0] >= 60.0:
                    history.popleft()
                allowed = len(history) < limit
                retry_after = max(1, int(60.0 - (now - history[0]))) if history else 60
                if allowed:
                    history.append(now)
                remaining = max(limit - len(history), 0)
        if not allowed:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={"detail": "API rate limit exceeded."},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Backend"] = backend
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Add request IDs, timing, structured logs and persistent audit records."""

    def __init__(
        self,
        app,
        *,
        security_store: ApiSecurityStore | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(app)
        self.security_store = security_store
        self.logger = logger or logging.getLogger("biointel.api")

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        supplied_request_id = request.headers.get("X-Request-ID", "").strip()[:128]
        request_id = re.sub(r"[^A-Za-z0-9._:-]", "_", supplied_request_id) or uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        status_code = 500
        error_code = ""
        try:
            response = await call_next(request)
            status_code = int(response.status_code)
        except Exception as exc:
            error_code = "unhandled_exception"
            METRICS.observe_exception(request.url.path, type(exc).__name__)
            self.logger.exception(
                "Unhandled API request failure",
                extra={"request_id": request_id, "method": request.method, "path": request.url.path},
            )
            raise
        finally:
            duration_seconds = time.perf_counter() - started
            duration_ms = round(duration_seconds * 1000.0, 3)
            METRICS.observe_request(request.method, request.url.path, status_code, duration_seconds)
            identity = getattr(request.state, "api_identity", None)
            request_bytes = int(getattr(request.state, "biointel_request_bytes", 0))
            response_bytes = 0
            if "response" in locals():
                try:
                    response_bytes = int(response.headers.get("content-length", "0") or 0)
                except (TypeError, ValueError):
                    response_bytes = 0
            sensitive_fragments = ("token", "api_key", "api-key", "apikey", "password", "secret", "authorization", "credential", "code")
            safe_query = urlencode([
                (
                    name[:128],
                    "[REDACTED]"
                    if any(fragment in name.casefold() for fragment in sensitive_fragments)
                    else value[:256],
                )
                for name, value in parse_qsl(request.url.query, keep_blank_values=True)
            ])[:2048]
            payload: dict[str, Any] = {
                "request_id": request_id,
                "client_id": getattr(identity, "client_id", None),
                "role": getattr(identity, "role", "unknown"),
                "method": request.method,
                "path": request.url.path,
                "query_string": safe_query,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "request_bytes": request_bytes,
                "response_bytes": response_bytes,
                "client_host": request.client.host if request.client else "unknown",
                "user_agent": request.headers.get("user-agent", ""),
                "error_code": error_code,
                "occurred_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            if self.security_store is not None:
                try:
                    self.security_store.log_request(payload)
                except Exception:
                    self.logger.exception("Unable to persist API request audit", extra={"request_id": request_id})
            self.logger.info(
                "API request",
                extra={
                    "request_id": request_id,
                    "client_id": payload["client_id"],
                    "role": payload["role"],
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
        response.headers["X-Request-ID"] = request_id
        return response
