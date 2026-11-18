from pathlib import Path

from biointel.multitenancy.context import TenantContext
from biointel.multitenancy.storage import TenantStorageRouter


def _context(tenant_id: str) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id, client_id="integration", role="admin", membership_role="owner"
    )


def test_tenant_storage_contract(isolated_workspace: Path) -> None:
    router = TenantStorageRouter(isolated_workspace)
    a = router.path(_context("tenant-a"), "datasets", "x.csv")
    b = router.path(_context("tenant-b"), "datasets", "x.csv")
    assert a != b
    assert isolated_workspace in a.parents and isolated_workspace in b.parents
