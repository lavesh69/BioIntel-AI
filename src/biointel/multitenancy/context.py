from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    client_id: str
    role: str
    membership_role: str


_CURRENT_TENANT: ContextVar[TenantContext | None] = ContextVar("biointel_current_tenant", default=None)


def current_tenant(*, required: bool = True) -> TenantContext | None:
    value = _CURRENT_TENANT.get()
    if required and value is None:
        raise RuntimeError("A tenant context is required for this operation.")
    return value


@contextmanager
def tenant_scope(context: TenantContext) -> Iterator[TenantContext]:
    token = _CURRENT_TENANT.set(context)
    try:
        yield context
    finally:
        _CURRENT_TENANT.reset(token)
