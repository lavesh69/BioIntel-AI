from __future__ import annotations

import json
import sqlite3
from biointel.database.core import managed_connect
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    tenant_id: str
    metric: str
    used: float
    requested: float
    limit: float | None
    remaining: float | None
    reason: str


class SaaSControlPlane:
    """Tenant subscription, entitlement, usage, quota and data-rights control plane."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

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
                CREATE TABLE IF NOT EXISTS plans (
                    plan_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    entitlements_json TEXT NOT NULL,
                    quotas_json TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS subscriptions (
                    subscription_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL UNIQUE,
                    plan_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    renews_at TEXT,
                    cancel_at TEXT,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY(plan_id) REFERENCES plans(plan_id)
                );
                CREATE TABLE IF NOT EXISTS usage_events (
                    usage_event_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(tenant_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_usage_tenant_metric ON usage_events(tenant_id, metric, recorded_at);
                CREATE TABLE IF NOT EXISTS data_rights_requests (
                    request_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    request_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    completed_at TEXT,
                    export_location TEXT,
                    reason TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS service_events (
                    event_id TEXT PRIMARY KEY,
                    tenant_id TEXT,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    resolved_at TEXT,
                    public_status TEXT NOT NULL
                );
                """
            )

    def upsert_plan(
        self,
        *,
        plan_id: str,
        display_name: str,
        entitlements: dict[str, bool],
        quotas: dict[str, float | int | None],
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO plans(plan_id, display_name, entitlements_json, quotas_json, active, created_at)
                VALUES(?,?,?,?,1,?)
                ON CONFLICT(plan_id) DO UPDATE SET
                    display_name=excluded.display_name,
                    entitlements_json=excluded.entitlements_json,
                    quotas_json=excluded.quotas_json,
                    active=1
                """,
                (plan_id, display_name, json.dumps(entitlements, sort_keys=True), json.dumps(quotas, sort_keys=True), utc_now()),
            )
        return {"plan_id": plan_id, "display_name": display_name, "entitlements": entitlements, "quotas": quotas}

    def subscribe(
        self,
        *,
        tenant_id: str,
        plan_id: str,
        status: str = "active",
        renews_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status not in {"trialing", "active", "past_due", "paused", "cancelled"}:
            raise ValueError("Unsupported subscription status")
        subscription_id = uuid.uuid4().hex
        started_at = utc_now()
        with self._connect() as connection:
            plan = connection.execute("SELECT 1 FROM plans WHERE plan_id=? AND active=1", (plan_id,)).fetchone()
            if plan is None:
                raise KeyError(plan_id)
            connection.execute(
                """
                INSERT INTO subscriptions(
                    subscription_id, tenant_id, plan_id, status, started_at, renews_at, metadata_json
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(tenant_id) DO UPDATE SET
                    plan_id=excluded.plan_id,
                    status=excluded.status,
                    renews_at=excluded.renews_at,
                    metadata_json=excluded.metadata_json
                """,
                (subscription_id, tenant_id, plan_id, status, started_at, renews_at, json.dumps(metadata or {}, sort_keys=True)),
            )
            row = connection.execute("SELECT * FROM subscriptions WHERE tenant_id=?", (tenant_id,)).fetchone()
        return dict(row)

    def _subscription_context(self, tenant_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT s.*, p.display_name, p.entitlements_json, p.quotas_json
                FROM subscriptions s JOIN plans p ON p.plan_id=s.plan_id
                WHERE s.tenant_id=? AND p.active=1
                """,
                (tenant_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"No active plan found for tenant {tenant_id}")
        payload = dict(row)
        payload["entitlements"] = json.loads(payload.pop("entitlements_json"))
        payload["quotas"] = json.loads(payload.pop("quotas_json"))
        payload["metadata"] = json.loads(payload.pop("metadata_json"))
        return payload

    def has_entitlement(self, tenant_id: str, entitlement: str) -> bool:
        context = self._subscription_context(tenant_id)
        return context["status"] in {"trialing", "active"} and bool(context["entitlements"].get(entitlement, False))

    def record_usage(
        self,
        *,
        tenant_id: str,
        metric: str,
        quantity: float,
        idempotency_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if quantity <= 0:
            raise ValueError("Usage quantity must be positive")
        self._subscription_context(tenant_id)
        event_id = uuid.uuid4().hex
        recorded_at = utc_now()
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO usage_events(
                        usage_event_id, tenant_id, metric, quantity, idempotency_key, recorded_at, metadata_json
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (event_id, tenant_id, metric, float(quantity), idempotency_key, recorded_at, json.dumps(metadata or {}, sort_keys=True)),
                )
            except sqlite3.IntegrityError:
                row = connection.execute(
                    "SELECT * FROM usage_events WHERE tenant_id=? AND idempotency_key=?",
                    (tenant_id, idempotency_key),
                ).fetchone()
                return dict(row)
        return {
            "usage_event_id": event_id, "tenant_id": tenant_id, "metric": metric,
            "quantity": float(quantity), "idempotency_key": idempotency_key,
            "recorded_at": recorded_at, "metadata": metadata or {},
        }

    def usage(self, tenant_id: str, metric: str) -> float:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(SUM(quantity),0) FROM usage_events WHERE tenant_id=? AND metric=?",
                (tenant_id, metric),
            ).fetchone()
        return float(row[0])

    def quota_decision(self, tenant_id: str, metric: str, requested: float = 0.0) -> QuotaDecision:
        context = self._subscription_context(tenant_id)
        used = self.usage(tenant_id, metric)
        raw_limit = context["quotas"].get(metric)
        limit = float(raw_limit) if raw_limit is not None else None
        if context["status"] not in {"trialing", "active"}:
            return QuotaDecision(False, tenant_id, metric, used, requested, limit, None, "subscription_not_active")
        if limit is None:
            return QuotaDecision(True, tenant_id, metric, used, requested, None, None, "unlimited")
        remaining = max(limit - used, 0.0)
        allowed = used + requested <= limit
        return QuotaDecision(
            allowed, tenant_id, metric, used, requested, limit, remaining,
            "within_quota" if allowed else "quota_exceeded",
        )

    def enforce_quota(self, tenant_id: str, metric: str, requested: float = 0.0) -> QuotaDecision:
        decision = self.quota_decision(tenant_id, metric, requested)
        if not decision.allowed:
            raise PermissionError(
                f"Tenant {tenant_id} cannot consume {requested} {metric}: {decision.reason}"
            )
        return decision

    def request_data_right(
        self,
        *,
        tenant_id: str,
        request_type: str,
        requested_by: str,
        reason: str,
    ) -> dict[str, Any]:
        if request_type not in {"export", "delete", "restrict", "rectify"}:
            raise ValueError("Unsupported data-right request")
        request_id = uuid.uuid4().hex
        requested_at = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO data_rights_requests(
                    request_id, tenant_id, request_type, status, requested_by, requested_at, reason
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (request_id, tenant_id, request_type, "open", requested_by, requested_at, reason),
            )
        return {
            "request_id": request_id, "tenant_id": tenant_id, "request_type": request_type,
            "status": "open", "requested_by": requested_by, "requested_at": requested_at,
            "reason": reason,
        }

    def complete_data_right(
        self,
        request_id: str,
        *,
        export_location: str | None = None,
    ) -> dict[str, Any]:
        completed_at = utc_now()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM data_rights_requests WHERE request_id=?", (request_id,)
            ).fetchone()
            if row is None:
                raise KeyError(request_id)
            if row["request_type"] == "export" and not export_location:
                raise ValueError("Export completion requires an export_location")
            connection.execute(
                """
                UPDATE data_rights_requests
                SET status='completed', completed_at=?, export_location=?
                WHERE request_id=?
                """,
                (completed_at, export_location, request_id),
            )
        return {
            "request_id": request_id, "status": "completed", "completed_at": completed_at,
            "export_location": export_location,
        }

    def tenant_snapshot(self, tenant_id: str) -> dict[str, Any]:
        context = self._subscription_context(tenant_id)
        with self._connect() as connection:
            usage_rows = connection.execute(
                "SELECT metric, SUM(quantity) AS quantity FROM usage_events WHERE tenant_id=? GROUP BY metric",
                (tenant_id,),
            ).fetchall()
            rights = connection.execute(
                "SELECT request_type, status, COUNT(*) AS count FROM data_rights_requests WHERE tenant_id=? GROUP BY request_type,status",
                (tenant_id,),
            ).fetchall()
        return {
            "subscription": context,
            "usage": {row["metric"]: float(row["quantity"]) for row in usage_rows},
            "data_rights": [dict(row) for row in rights],
        }
