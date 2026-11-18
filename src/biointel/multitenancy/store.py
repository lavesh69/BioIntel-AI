from __future__ import annotations

import json
import re
import sqlite3
from biointel.database.core import managed_connect
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .context import TenantContext

TENANT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Tenant:
    tenant_id: str
    display_name: str
    status: str
    plan: str
    created_at_utc: str
    metadata: dict[str, Any]


class TenantStore:
    """Persistent tenant registry with membership-enforced, row-scoped resources.

    Every resource query includes tenant_id in the primary key and WHERE clause. The
    caller never supplies a free-form tenant identifier after context resolution,
    which prevents accidental cross-tenant reads and writes.
    """

    VALID_MEMBERSHIP_ROLES = {"viewer", "reviewer", "operator", "admin", "owner"}

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self.ensure_tenant("default", "Default Workspace", plan="local")

    def _connect(self) -> sqlite3.Connection:
        connection = managed_connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tenants(
                    tenant_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('active','suspended','archived')),
                    plan TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS tenant_memberships(
                    tenant_id TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    membership_role TEXT NOT NULL CHECK(membership_role IN ('viewer','reviewer','operator','admin','owner')),
                    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
                    created_at_utc TEXT NOT NULL,
                    PRIMARY KEY(tenant_id, client_id),
                    FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS tenant_resources(
                    tenant_id TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY(tenant_id, resource_id),
                    FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS tenant_audit_events(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource_type TEXT NOT NULL DEFAULT '',
                    resource_id TEXT NOT NULL DEFAULT '',
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    occurred_at_utc TEXT NOT NULL,
                    FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_tenant_membership_client
                    ON tenant_memberships(client_id, enabled);
                CREATE INDEX IF NOT EXISTS idx_tenant_resources_type
                    ON tenant_resources(tenant_id, resource_type, updated_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_tenant_audit_time
                    ON tenant_audit_events(tenant_id, occurred_at_utc DESC);
                """
            )

    @staticmethod
    def _validate_id(tenant_id: str) -> str:
        normalized = tenant_id.strip().lower()
        if not TENANT_PATTERN.fullmatch(normalized):
            raise ValueError("tenant_id must be 2-63 lowercase letters, numbers or hyphens.")
        return normalized

    def ensure_tenant(
        self,
        tenant_id: str,
        display_name: str,
        *,
        plan: str = "standard",
        metadata: dict[str, Any] | None = None,
    ) -> Tenant:
        tenant_id = self._validate_id(tenant_id)
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tenants(tenant_id,display_name,status,plan,created_at_utc,updated_at_utc,metadata_json)
                VALUES(?,?,'active',?,?,?,?)
                ON CONFLICT(tenant_id) DO UPDATE SET
                    display_name=excluded.display_name,
                    plan=excluded.plan,
                    updated_at_utc=excluded.updated_at_utc,
                    metadata_json=excluded.metadata_json
                WHERE tenants.display_name IS NOT excluded.display_name
                   OR tenants.plan IS NOT excluded.plan
                   OR tenants.metadata_json IS NOT excluded.metadata_json
                """,
                (tenant_id, display_name.strip() or tenant_id, plan, now, now, json.dumps(metadata or {}, sort_keys=True)),
            )
        return self.get_tenant(tenant_id)

    def get_tenant(self, tenant_id: str) -> Tenant:
        tenant_id = self._validate_id(tenant_id)
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tenants WHERE tenant_id=?", (tenant_id,)).fetchone()
        if row is None:
            raise KeyError(tenant_id)
        return Tenant(
            tenant_id=str(row["tenant_id"]),
            display_name=str(row["display_name"]),
            status=str(row["status"]),
            plan=str(row["plan"]),
            created_at_utc=str(row["created_at_utc"]),
            metadata=json.loads(str(row["metadata_json"] or "{}")),
        )

    def add_membership(self, tenant_id: str, client_id: str, role: str) -> None:
        tenant_id = self._validate_id(tenant_id)
        normalized_role = role.strip().lower()
        if normalized_role not in self.VALID_MEMBERSHIP_ROLES:
            raise ValueError(f"Unsupported tenant membership role: {role}")
        self.get_tenant(tenant_id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tenant_memberships(tenant_id,client_id,membership_role,enabled,created_at_utc)
                VALUES(?,?,?,1,?)
                ON CONFLICT(tenant_id,client_id) DO UPDATE SET
                    membership_role=excluded.membership_role, enabled=1
                """,
                (tenant_id, client_id.strip(), normalized_role, utc_now()),
            )

    def resolve_context(
        self,
        *,
        client_id: str,
        api_role: str,
        requested_tenant: str | None,
        allow_local_default: bool = False,
    ) -> TenantContext:
        tenant_id = self._validate_id(requested_tenant or "default")
        tenant = self.get_tenant(tenant_id)
        if tenant.status != "active":
            raise PermissionError(f"Tenant '{tenant_id}' is not active.")
        if allow_local_default and client_id == "local-operator" and tenant_id == "default":
            return TenantContext(tenant_id, client_id, api_role, "owner")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT membership_role FROM tenant_memberships
                WHERE tenant_id=? AND client_id=? AND enabled=1
                """,
                (tenant_id, client_id),
            ).fetchone()
        if row is None:
            raise PermissionError(f"Client '{client_id}' is not a member of tenant '{tenant_id}'.")
        return TenantContext(tenant_id, client_id, api_role, str(row["membership_role"]))

    def list_for_client(self, client_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT t.*, m.membership_role
                FROM tenant_memberships m JOIN tenants t ON t.tenant_id=m.tenant_id
                WHERE m.client_id=? AND m.enabled=1 AND t.status='active'
                ORDER BY t.display_name
                """,
                (client_id,),
            ).fetchall()
        return [
            {
                **asdict(self.get_tenant(str(row["tenant_id"]))),
                "membership_role": str(row["membership_role"]),
            }
            for row in rows
        ]

    def put_resource(
        self,
        context: TenantContext,
        *,
        resource_type: str,
        name: str,
        payload: dict[str, Any],
        resource_id: str | None = None,
    ) -> dict[str, Any]:
        if context.membership_role not in {"operator", "admin", "owner"}:
            raise PermissionError("Tenant role cannot create or update resources.")
        resource_id = resource_id or uuid4().hex
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tenant_resources(
                    tenant_id,resource_id,resource_type,name,payload_json,created_by,created_at_utc,updated_at_utc
                ) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(tenant_id,resource_id) DO UPDATE SET
                    resource_type=excluded.resource_type,
                    name=excluded.name,
                    payload_json=excluded.payload_json,
                    updated_at_utc=excluded.updated_at_utc
                """,
                (
                    context.tenant_id,
                    resource_id,
                    resource_type.strip(),
                    name.strip(),
                    json.dumps(payload, sort_keys=True, default=str),
                    context.client_id,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO tenant_audit_events(
                    tenant_id,client_id,action,resource_type,resource_id,detail_json,occurred_at_utc
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (context.tenant_id, context.client_id, "resource_upsert", resource_type, resource_id, "{}", now),
            )
        return self.get_resource(context, resource_id)

    def get_resource(self, context: TenantContext, resource_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM tenant_resources WHERE tenant_id=? AND resource_id=?
                """,
                (context.tenant_id, resource_id),
            ).fetchone()
        if row is None:
            raise KeyError(resource_id)
        return {
            "tenant_id": context.tenant_id,
            "resource_id": str(row["resource_id"]),
            "resource_type": str(row["resource_type"]),
            "name": str(row["name"]),
            "payload": json.loads(str(row["payload_json"])),
            "created_by": str(row["created_by"]),
            "created_at_utc": str(row["created_at_utc"]),
            "updated_at_utc": str(row["updated_at_utc"]),
        }

    def list_resources(self, context: TenantContext, *, resource_type: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        parameters: list[Any] = [context.tenant_id]
        sql = "SELECT resource_id FROM tenant_resources WHERE tenant_id=?"
        if resource_type:
            sql += " AND resource_type=?"
            parameters.append(resource_type)
        sql += " ORDER BY updated_at_utc DESC LIMIT ?"
        parameters.append(max(1, min(int(limit), 1000)))
        with self._connect() as connection:
            ids = [str(row[0]) for row in connection.execute(sql, parameters).fetchall()]
        return [self.get_resource(context, resource_id) for resource_id in ids]
