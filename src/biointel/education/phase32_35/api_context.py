from __future__ import annotations

from fastapi import HTTPException, Request


def require_tenant(request: Request, tenant_id: str) -> None:
    """Bind remote authenticated calls to the tenant resolved by API middleware.

    Standalone router tests and the local desktop operator do not carry a remote
    tenant context. Remote configured API identities do and are fail-closed.
    """

    identity = getattr(request.state, "api_identity", None)
    if identity is None or getattr(identity, "role", "") == "local_operator":
        return
    context = getattr(request.state, "tenant", None)
    if context is None:
        raise HTTPException(401, detail="Authenticated tenant context is required.")
    if str(getattr(context, "tenant_id", "")) != str(tenant_id):
        raise HTTPException(403, detail="Resource belongs to a different tenant.")
