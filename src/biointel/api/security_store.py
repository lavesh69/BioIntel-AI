from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from biointel.database.core import managed_connect
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ApiIdentity:
    client_id: str
    display_name: str
    role: str
    quota_per_minute: int
    source: str
    default_tenant: str = "default"
    tenant_ids: tuple[str, ...] = ("default",)


class ApiSecurityStore:
    """Persistent local API identity, request-audit, rate-limit and idempotency store.

    The store remains localhost-friendly and dependency-light while providing deterministic
    behaviour across API restarts and multiple local workers. API keys are stored only as
    SHA-256 digests; raw keys are never written to disk.
    """

    VALID_ROLES = {"viewer", "reviewer", "operator", "admin"}

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = managed_connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS api_clients(
                    client_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('viewer','reviewer','operator','admin')),
                    key_hash TEXT NOT NULL UNIQUE,
                    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
                    quota_per_minute INTEGER NOT NULL DEFAULT 120 CHECK(quota_per_minute >= 1),
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    last_used_at_utc TEXT,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS api_rate_windows(
                    subject TEXT NOT NULL,
                    window_start_epoch INTEGER NOT NULL,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY(subject, window_start_epoch)
                );
                CREATE TABLE IF NOT EXISTS api_request_log(
                    request_id TEXT PRIMARY KEY,
                    client_id TEXT,
                    role TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    query_string TEXT NOT NULL DEFAULT '',
                    status_code INTEGER NOT NULL,
                    duration_ms REAL NOT NULL,
                    request_bytes INTEGER NOT NULL DEFAULT 0,
                    response_bytes INTEGER NOT NULL DEFAULT 0,
                    client_host TEXT NOT NULL DEFAULT '',
                    user_agent TEXT NOT NULL DEFAULT '',
                    error_code TEXT NOT NULL DEFAULT '',
                    occurred_at_utc TEXT NOT NULL,
                    FOREIGN KEY(client_id) REFERENCES api_clients(client_id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS api_security_events(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT,
                    severity TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    subject TEXT NOT NULL DEFAULT '',
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    occurred_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_idempotency(
                    idempotency_key TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL,
                    PRIMARY KEY(idempotency_key, endpoint)
                );
                CREATE INDEX IF NOT EXISTS idx_api_clients_role_enabled
                    ON api_clients(role, enabled);
                CREATE INDEX IF NOT EXISTS idx_api_request_log_time
                    ON api_request_log(occurred_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_api_request_log_path_status
                    ON api_request_log(path, status_code);
                CREATE INDEX IF NOT EXISTS idx_api_security_events_time
                    ON api_security_events(occurred_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_api_rate_windows_updated
                    ON api_rate_windows(updated_at_utc);
                CREATE INDEX IF NOT EXISTS idx_api_idempotency_expires
                    ON api_idempotency(expires_at_utc);
                """
            )

    def register_client(
        self,
        *,
        client_id: str,
        display_name: str,
        role: str,
        raw_key: str,
        quota_per_minute: int = 120,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        normalized_role = role.strip().lower()
        if normalized_role not in self.VALID_ROLES:
            raise ValueError(f"Unsupported API role: {role}")
        if not client_id.strip() or not raw_key:
            raise ValueError("client_id and raw_key are required")
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO api_clients(
                    client_id, display_name, role, key_hash, enabled,
                    quota_per_minute, created_at_utc, updated_at_utc, metadata_json
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(client_id) DO UPDATE SET
                    display_name=excluded.display_name,
                    role=excluded.role,
                    key_hash=excluded.key_hash,
                    quota_per_minute=excluded.quota_per_minute,
                    updated_at_utc=excluded.updated_at_utc,
                    metadata_json=excluded.metadata_json
                """,
                (
                    client_id.strip(),
                    display_name.strip() or client_id.strip(),
                    normalized_role,
                    hash_api_key(raw_key),
                    max(int(quota_per_minute), 1),
                    now,
                    now,
                    json.dumps(metadata or {}, sort_keys=True, default=str),
                ),
            )

    def authenticate(self, raw_key: str) -> ApiIdentity | None:
        if not raw_key:
            return None
        digest = hash_api_key(raw_key)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT client_id, display_name, role, quota_per_minute, key_hash, metadata_json
                FROM api_clients
                WHERE enabled=1 AND key_hash=?
                """,
                (digest,),
            ).fetchone()
            if row is None or not hmac.compare_digest(str(row["key_hash"]), digest):
                return None
            connection.execute(
                """
                UPDATE api_clients
                SET last_used_at_utc=?, request_count=request_count+1
                WHERE client_id=?
                """,
                (utc_now(), row["client_id"]),
            )
        try:
            metadata = json.loads(str(row["metadata_json"] or "{}"))
        except (json.JSONDecodeError, TypeError):
            metadata = {}
        tenant_ids = tuple(
            str(item).strip().lower()
            for item in metadata.get("tenant_ids", [metadata.get("default_tenant", "default")])
            if str(item).strip()
        ) or ("default",)
        return ApiIdentity(
            client_id=str(row["client_id"]),
            display_name=str(row["display_name"]),
            role=str(row["role"]),
            quota_per_minute=int(row["quota_per_minute"]),
            source="registered_key",
            default_tenant=str(metadata.get("default_tenant") or tenant_ids[0]),
            tenant_ids=tenant_ids,
        )

    def allow_request(self, subject: str, limit: int, *, now_epoch: int) -> tuple[bool, int, int]:
        window_start = now_epoch - (now_epoch % 60)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO api_rate_windows(subject, window_start_epoch, request_count, updated_at_utc)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(subject, window_start_epoch) DO UPDATE SET
                    request_count=request_count+1,
                    updated_at_utc=excluded.updated_at_utc
                """,
                (subject, window_start, utc_now()),
            )
            row = connection.execute(
                """
                SELECT request_count FROM api_rate_windows
                WHERE subject=? AND window_start_epoch=?
                """,
                (subject, window_start),
            ).fetchone()
            connection.execute(
                "DELETE FROM api_rate_windows WHERE window_start_epoch < ?",
                (window_start - 3600,),
            )
            connection.commit()
        count = int(row["request_count"]) if row else 1
        return count <= limit, max(limit - count, 0), max(1, 60 - (now_epoch - window_start))

    def log_request(self, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            client_id = payload.get("client_id")
            if client_id:
                exists = connection.execute(
                    "SELECT 1 FROM api_clients WHERE client_id=?",
                    (client_id,),
                ).fetchone()
                if exists is None:
                    # Local/operator identities are valid audit subjects even when
                    # they are not persisted API-key clients. Store NULL so the
                    # request log remains durable without violating the FK.
                    client_id = None
            connection.execute(
                """
                INSERT OR REPLACE INTO api_request_log(
                    request_id, client_id, role, method, path, query_string,
                    status_code, duration_ms, request_bytes, response_bytes,
                    client_host, user_agent, error_code, occurred_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["request_id"],
                    client_id,
                    payload.get("role", "local_operator"),
                    payload.get("method", ""),
                    payload.get("path", ""),
                    payload.get("query_string", ""),
                    int(payload.get("status_code", 0)),
                    float(payload.get("duration_ms", 0.0)),
                    int(payload.get("request_bytes", 0)),
                    int(payload.get("response_bytes", 0)),
                    payload.get("client_host", ""),
                    payload.get("user_agent", "")[:500],
                    payload.get("error_code", ""),
                    payload.get("occurred_at_utc", utc_now()),
                ),
            )

    def record_event(
        self,
        event_type: str,
        *,
        severity: str = "info",
        request_id: str | None = None,
        subject: str = "",
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO api_security_events(
                    request_id, severity, event_type, subject, detail_json, occurred_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    severity,
                    event_type,
                    subject,
                    json.dumps(detail or {}, sort_keys=True, default=str),
                    utc_now(),
                ),
            )

    def status(self) -> dict[str, Any]:
        with self._connect() as connection:
            clients = int(connection.execute("SELECT COUNT(*) FROM api_clients WHERE enabled=1").fetchone()[0])
            requests = int(connection.execute("SELECT COUNT(*) FROM api_request_log").fetchone()[0])
            errors = int(connection.execute("SELECT COUNT(*) FROM api_request_log WHERE status_code>=400").fetchone()[0])
            events = int(connection.execute("SELECT COUNT(*) FROM api_security_events").fetchone()[0])
            recent = [dict(row) for row in connection.execute(
                """
                SELECT request_id, client_id, role, method, path, status_code,
                       duration_ms, request_bytes, occurred_at_utc
                FROM api_request_log
                ORDER BY occurred_at_utc DESC LIMIT 20
                """
            ).fetchall()]
        return {
            "enabled_clients": clients,
            "request_log_count": requests,
            "error_count": errors,
            "security_event_count": events,
            "recent_requests": recent,
        }

    def store_idempotent_response(
        self,
        *,
        key: str,
        endpoint: str,
        request_hash: str,
        status_code: int,
        response: dict[str, Any],
        ttl_hours: int = 24,
    ) -> None:
        now = datetime.now(UTC)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO api_idempotency(
                    idempotency_key, endpoint, request_hash, status_code,
                    response_json, created_at_utc, expires_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    endpoint,
                    request_hash,
                    int(status_code),
                    json.dumps(response, sort_keys=True, default=str),
                    now.isoformat(timespec="seconds"),
                    (now + timedelta(hours=max(ttl_hours, 1))).isoformat(timespec="seconds"),
                ),
            )

    def get_idempotent_response(self, *, key: str, endpoint: str, request_hash: str) -> tuple[int, dict[str, Any]] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT status_code, response_json, request_hash, expires_at_utc
                FROM api_idempotency WHERE idempotency_key=? AND endpoint=?
                """,
                (key, endpoint),
            ).fetchone()
            if row is None:
                return None
            if str(row["expires_at_utc"]) < utc_now():
                connection.execute(
                    "DELETE FROM api_idempotency WHERE idempotency_key=? AND endpoint=?",
                    (key, endpoint),
                )
                return None
            if not hmac.compare_digest(str(row["request_hash"]), request_hash):
                raise ValueError("Idempotency key was already used with a different request payload.")
            return int(row["status_code"]), json.loads(str(row["response_json"]))
