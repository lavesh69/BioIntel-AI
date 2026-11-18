from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from .context import tenant_scope
from .store import TenantStore


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Resolve and enforce tenant membership before tenant-aware API handlers run.

    Legacy stateful registries are available only in the default workspace until their
    repository is migrated. Non-default tenants are denied rather than exposed to shared
    state, preserving isolation by default.
    """

    LEGACY_STATEFUL_PREFIXES = (
        "/documents",
        "/jobs",
        "/evidence",
        "/governance",
        "/projects",
        "/analytics",
        "/activity",
        "/downloads",
        "/internet/download",
        "/integrations/sync",
        "/workspace",
    )

    def __init__(
        self,
        app,
        *,
        tenant_store: TenantStore,
        excluded_paths: tuple[str, ...] = (
            "/health",
            "/v1/health",
            "/live",
            "/ready",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
        ),
    ) -> None:
        super().__init__(app)
        self.tenant_store = tenant_store
        self.excluded_paths = excluded_paths

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if any(request.url.path.startswith(path) for path in self.excluded_paths):
            return await call_next(request)
        identity = getattr(request.state, "api_identity", None)
        if identity is None:
            return JSONResponse(status_code=401, content={"detail": "Identity must be resolved before tenant context."})
        requested = request.headers.get("X-BioIntel-Tenant") or getattr(identity, "default_tenant", None)
        try:
            context = self.tenant_store.resolve_context(
                client_id=identity.client_id,
                api_role=identity.role,
                requested_tenant=requested,
                allow_local_default=identity.role == "local_operator",
            )
        except KeyError:
            return JSONResponse(status_code=404, content={"detail": "Tenant not found."})
        except (ValueError, PermissionError) as exc:
            return JSONResponse(status_code=403, content={"detail": str(exc)})
        if context.tenant_id != "default" and any(
            request.url.path.startswith(prefix) for prefix in self.LEGACY_STATEFUL_PREFIXES
        ):
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "This legacy stateful endpoint is not yet backed by a tenant-scoped repository.",
                    "tenant_id": context.tenant_id,
                    "safe_alternative": "/tenant-resources",
                },
            )
        request.state.tenant = context
        with tenant_scope(context):
            response = await call_next(request)
        response.headers["X-BioIntel-Tenant"] = context.tenant_id
        response.headers["Vary"] = "X-API-Key, X-BioIntel-Tenant"
        return response
