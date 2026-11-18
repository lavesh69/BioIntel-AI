from __future__ import annotations

from pathlib import Path

from .context import TenantContext


class TenantStorageRouter:
    """Resolve tenant-specific filesystem/object keys without cross-tenant traversal."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def tenant_root(self, context: TenantContext) -> Path:
        destination = (self.root / context.tenant_id).resolve()
        if destination.parent != self.root:
            raise ValueError("Invalid tenant storage root.")
        destination.mkdir(parents=True, exist_ok=True)
        return destination

    def path(self, context: TenantContext, *parts: str, create_parent: bool = False) -> Path:
        base = self.tenant_root(context)
        destination = base.joinpath(*parts).resolve()
        if destination != base and base not in destination.parents:
            raise ValueError("Tenant storage path traversal is not allowed.")
        if create_parent:
            destination.parent.mkdir(parents=True, exist_ok=True)
        return destination

    def object_key(self, context: TenantContext, *parts: str) -> str:
        cleaned = [part.strip("/") for part in parts if part.strip("/")]
        if any(part in {".", ".."} or "../" in part or "\\" in part for part in cleaned):
            raise ValueError("Invalid tenant object key.")
        return "/".join(("tenants", context.tenant_id, *cleaned))
