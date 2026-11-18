from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken

from .base import (
    Conflict,
    IntegrityFailure,
    Missing,
    PermissionDenied,
    PlatformStore,
    ResearchPlatformError,
    canonical_json,
    new_id,
    now_utc,
)

SYNC_OPERATIONS = {
    "CREATE",
    "UPDATE",
    "DELETE",
    "RESTORE",
    "ARCHIVE",
    "ATTACH_FILE",
    "REMOVE_FILE",
}
SYNC_SCOPES = {
    "user_profile",
    "preferences",
    "courses",
    "classrooms",
    "enrolments",
    "assignments",
    "submissions",
    "notes",
    "bookmarks",
    "shiro_conversations",
    "academy_progress",
    "virtual_lab_notebooks",
    "studio_projects",
    "science_pulse_collections",
    "research_projects",
    "portfolio_records",
    "credentials",
    "notifications",
    "institutional_records",
    "selected_files",
}
NEVER_SYNC_KEYS = {
    "password",
    "password_hash",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "private_key",
    "connection_string",
}
CONFLICT_STRATEGIES = {
    "messages": "append_only_merge",
    "audit_logs": "append_only_merge",
    "submissions": "immutable_record_rejection",
    "grades": "server_authoritative",
    "notes": "manual_resolution",
    "files": "manual_resolution",
    "preferences": "field_level_merge",
    "credentials": "server_authoritative",
    "notifications": "latest_valid_version",
}


class SyncAdapter(Protocol):
    name: str

    def push(self, tenant_id: str, changes: list[dict[str, Any]]) -> dict[str, Any]: ...

    def pull(self, tenant_id: str, cursor: str, limit: int) -> dict[str, Any]: ...


class MemorySyncAdapter:
    """Deterministic provider-independent test/reference adapter."""

    name = "memory"

    def __init__(self) -> None:
        self._changes: dict[str, list[dict[str, Any]]] = {}
        self.available = True
        self.reject_device_ids: set[str] = set()

    def push(self, tenant_id: str, changes: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.available:
            raise ConnectionError("remote_server_unavailable")
        bucket = self._changes.setdefault(tenant_id, [])
        existing = {row["change_id"] for row in bucket}
        acknowledged = []
        for change in changes:
            if change["device_id"] in self.reject_device_ids:
                continue
            if change["change_id"] not in existing:
                bucket.append(dict(change))
                existing.add(change["change_id"])
            acknowledged.append(change["change_id"])
        return {"acknowledged": acknowledged}

    def pull(self, tenant_id: str, cursor: str, limit: int) -> dict[str, Any]:
        if not self.available:
            raise ConnectionError("remote_server_unavailable")
        offset = max(0, int(cursor or "0"))
        bucket = self._changes.get(tenant_id, [])
        rows = bucket[offset : offset + max(1, min(limit, 5_000))]
        return {"changes": [dict(row) for row in rows], "cursor": str(offset + len(rows))}


class HttpSyncAdapter:
    """HTTPS adapter with standard certificate validation and bounded responses."""

    name = "https"

    def __init__(self, endpoint_url: str, token: str, *, timeout_seconds: float = 30.0):
        parsed = urlsplit(endpoint_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ResearchPlatformError("Remote sync requires a valid HTTPS endpoint.")
        self.endpoint_url = endpoint_url.rstrip("/")
        self.token = token
        self.timeout_seconds = max(2.0, min(timeout_seconds, 120.0))

    def _post(self, route: str, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(
            timeout=self.timeout_seconds,
            verify=True,
            follow_redirects=False,
            headers={"Authorization": f"Bearer {self.token}"},
        ) as client:
            response = client.post(f"{self.endpoint_url}{route}", json=payload)
            response.raise_for_status()
            if int(response.headers.get("content-length", "0") or 0) > 10 * 1024**2:
                raise IntegrityFailure("Remote sync response exceeded the 10 MiB limit.")
            result = response.json()
            if not isinstance(result, dict):
                raise IntegrityFailure("Remote sync response must be a JSON object.")
            return result

    def push(self, tenant_id: str, changes: list[dict[str, Any]]) -> dict[str, Any]:
        return self._post("/v1/sync/push", {"tenant_id": tenant_id, "changes": changes})

    def pull(self, tenant_id: str, cursor: str, limit: int) -> dict[str, Any]:
        return self._post(
            "/v1/sync/pull",
            {"tenant_id": tenant_id, "cursor": cursor, "limit": min(limit, 5_000)},
        )


@dataclass(frozen=True)
class SyncResult:
    pushed: int
    pulled: int
    acknowledged: int
    conflicts: int
    cursor: str
    support_reference: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _contains_secret(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normal = str(key).strip().lower()
            if normal in NEVER_SYNC_KEYS or normal.endswith(("_token", "_secret", "_password")):
                return True
            if _contains_secret(child):
                return True
    elif isinstance(value, list):
        return any(_contains_secret(item) for item in value)
    return False


class SyncEngine:
    def __init__(
        self,
        database: str | Path,
        storage_root: str | Path,
        *,
        recovery_key: bytes | None = None,
    ):
        self.store = PlatformStore(database)
        self.storage_root = Path(storage_root).resolve()
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.sync_root = self.storage_root / "phase32-sync"
        self.sync_root.mkdir(parents=True, exist_ok=True)
        self.key_path = self.sync_root / ".account-recovery-key"
        if recovery_key is not None:
            Fernet(recovery_key)
            if self.key_path.exists() and self.key_path.read_bytes() != recovery_key:
                raise IntegrityFailure("Recovery key does not match the configured sync account.")
            self.key_path.write_bytes(recovery_key)
        elif not self.key_path.exists():
            self.key_path.write_bytes(Fernet.generate_key())
        try:
            os.chmod(self.key_path, 0o600)
        except OSError:
            pass
        self._key = self.key_path.read_bytes()
        self._cipher = Fernet(self._key)
        fingerprint = hashlib.sha256(self._key).hexdigest()
        with self.store.connection() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO education_p32_key_versions
                (key_version,key_fingerprint,state,created_at_utc,rotated_by)
                VALUES(1,?,'active',?,'system')""",
                (fingerprint, now_utc()),
            )

    def export_recovery_key(self, *, confirmed: bool) -> bytes:
        if not confirmed:
            raise PermissionDenied("Explicit recovery-key export confirmation is required.")
        return self._key

    def _encrypt(self, payload: Any) -> str:
        return self._cipher.encrypt(canonical_json(payload).encode("utf-8")).decode("ascii")

    def _decrypt(self, ciphertext: str) -> Any:
        try:
            return json.loads(self._cipher.decrypt(ciphertext.encode("ascii")))
        except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
            raise IntegrityFailure("Encrypted sync payload failed authentication.") from exc

    def register_device(
        self,
        tenant_id: str,
        owner_id: str,
        *,
        device_name: str,
        device_type: str,
        operating_system: str,
        permissions: list[str],
        public_key: str = "",
        approved_by: str = "",
    ) -> dict[str, Any]:
        requested = sorted(set(permissions))
        unknown = set(requested).difference(SYNC_SCOPES)
        if unknown:
            raise ResearchPlatformError(f"Unsupported sync scope: {sorted(unknown)[0]}")
        state = "trusted" if approved_by else "pending"
        device_id = new_id("device")
        timestamp = now_utc()
        public_fingerprint = (
            hashlib.sha256(public_key.encode("utf-8")).hexdigest() if public_key else ""
        )
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p32_sync_devices
                (device_id,tenant_id,owner_id,device_name,device_type,operating_system,
                 public_key_fingerprint,state,permissions_json,registered_at_utc,
                 approved_at_utc,approved_by,last_activity_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    device_id,
                    tenant_id,
                    owner_id,
                    device_name[:160],
                    device_type[:80],
                    operating_system[:160],
                    public_fingerprint,
                    state,
                    canonical_json(requested),
                    timestamp,
                    timestamp if approved_by else None,
                    approved_by or None,
                    timestamp,
                ),
            )
        return self.device(device_id)

    def device(self, device_id: str) -> dict[str, Any]:
        row = self.store.one(
            "SELECT * FROM education_p32_sync_devices WHERE device_id=?",
            (device_id,),
        )
        if not row:
            raise Missing("Sync device not found.")
        row["permissions"] = json.loads(row.pop("permissions_json"))
        return row

    def approve_device(self, device_id: str, administrator_id: str) -> dict[str, Any]:
        timestamp = now_utc()
        with self.store.connection() as connection:
            result = connection.execute(
                """UPDATE education_p32_sync_devices SET state='trusted',
                approved_at_utc=?,approved_by=?,revoked_at_utc=NULL,revoked_by=NULL
                WHERE device_id=? AND state IN ('pending','untrusted')""",
                (timestamp, administrator_id, device_id),
            )
            if result.rowcount != 1:
                raise Conflict("Device is not eligible for approval.")
        return self.device(device_id)

    def revoke_device(
        self,
        device_id: str,
        administrator_id: str,
        *,
        lost: bool = False,
    ) -> dict[str, Any]:
        state = "lost" if lost else "revoked"
        timestamp = now_utc()
        with self.store.connection() as connection:
            result = connection.execute(
                """UPDATE education_p32_sync_devices SET state=?,revoked_at_utc=?,
                revoked_by=? WHERE device_id=? AND state!='revoked'""",
                (state, timestamp, administrator_id, device_id),
            )
            if result.rowcount != 1:
                raise Missing("Active device not found.")
            connection.execute(
                """UPDATE education_p32_device_sessions SET revoked_at_utc=?,
                revoked_by=? WHERE device_id=? AND revoked_at_utc IS NULL""",
                (timestamp, administrator_id, device_id),
            )
            device = connection.execute(
                "SELECT tenant_id FROM education_p32_sync_devices WHERE device_id=?",
                (device_id,),
            ).fetchone()
            connection.execute(
                """INSERT INTO education_p32_sync_incidents
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    new_id("syncincident"),
                    device["tenant_id"],
                    device_id,
                    "high" if lost else "medium",
                    "DEVICE_LOST" if lost else "DEVICE_REVOKED",
                    "Device access and active sync sessions were revoked.",
                    new_id("support"),
                    canonical_json(
                        {
                            "administrator_id": administrator_id,
                            "session_invalidation": True,
                        }
                    ),
                    timestamp,
                    None,
                    None,
                ),
            )
        return self.device(device_id)

    def create_session(
        self,
        device_id: str,
        token: str,
        *,
        expires_at_utc: str,
    ) -> dict[str, Any]:
        device = self.device(device_id)
        if device["state"] != "trusted":
            raise PermissionDenied("Only trusted devices may create sync sessions.")
        if not token:
            raise ResearchPlatformError("Session token is required.")
        session_id = new_id("syncsession")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p32_device_sessions
                (session_id,tenant_id,device_id,token_ciphertext,token_fingerprint,
                 created_at_utc,expires_at_utc,last_seen_at_utc)
                VALUES(?,?,?,?,?,?,?,?)""",
                (
                    session_id,
                    device["tenant_id"],
                    device_id,
                    self._cipher.encrypt(token.encode("utf-8")).decode("ascii"),
                    hashlib.sha256(token.encode("utf-8")).hexdigest()[:16],
                    now_utc(),
                    expires_at_utc,
                    now_utc(),
                ),
            )
        return {"session_id": session_id, "device_id": device_id, "expires_at_utc": expires_at_utc}

    def set_policy(
        self,
        tenant_id: str,
        administrator_id: str,
        *,
        allowed_categories: list[str],
        excluded_categories: list[str] | None = None,
        data_residency: str = "local",
        retention_days: int = 365,
        allowed_device_types: list[str] | None = None,
        sync_windows: list[dict[str, Any]] | None = None,
        bandwidth_limit_kib: int = 0,
        quota_bytes: int = 10 * 1024**3,
        metered_allowed: bool = False,
        low_bandwidth_default: bool = False,
        paused: bool = False,
    ) -> dict[str, Any]:
        allowed = sorted(set(allowed_categories))
        excluded = sorted(set(excluded_categories or []))
        unknown = set(allowed + excluded).difference(SYNC_SCOPES)
        if unknown:
            raise ResearchPlatformError(f"Unsupported sync scope: {sorted(unknown)[0]}")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p32_sync_policies
                (tenant_id,allowed_categories_json,excluded_categories_json,data_residency,
                 retention_days,allowed_device_types_json,sync_windows_json,bandwidth_limit_kib,
                 quota_bytes,metered_allowed,low_bandwidth_default,paused,updated_at_utc,updated_by)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(tenant_id) DO UPDATE SET
                 allowed_categories_json=excluded.allowed_categories_json,
                 excluded_categories_json=excluded.excluded_categories_json,
                 data_residency=excluded.data_residency,
                 retention_days=excluded.retention_days,
                 allowed_device_types_json=excluded.allowed_device_types_json,
                 sync_windows_json=excluded.sync_windows_json,
                 bandwidth_limit_kib=excluded.bandwidth_limit_kib,
                 quota_bytes=excluded.quota_bytes,
                 metered_allowed=excluded.metered_allowed,
                 low_bandwidth_default=excluded.low_bandwidth_default,
                 paused=excluded.paused,updated_at_utc=excluded.updated_at_utc,
                 updated_by=excluded.updated_by""",
                (
                    tenant_id,
                    canonical_json(allowed),
                    canonical_json(excluded),
                    data_residency[:120],
                    max(1, retention_days),
                    canonical_json(allowed_device_types or []),
                    canonical_json(sync_windows or []),
                    max(0, bandwidth_limit_kib),
                    max(0, quota_bytes),
                    int(metered_allowed),
                    int(low_bandwidth_default),
                    int(paused),
                    now_utc(),
                    administrator_id,
                ),
            )
        return self.policy(tenant_id)

    def policy(self, tenant_id: str) -> dict[str, Any]:
        row = self.store.one(
            "SELECT * FROM education_p32_sync_policies WHERE tenant_id=?",
            (tenant_id,),
        )
        if not row:
            return {
                "tenant_id": tenant_id,
                "allowed_categories": sorted(SYNC_SCOPES),
                "excluded_categories": [],
                "paused": 0,
                "quota_bytes": 10 * 1024**3,
                "allowed_device_types": [],
            }
        for field in (
            "allowed_categories_json",
            "excluded_categories_json",
            "allowed_device_types_json",
            "sync_windows_json",
        ):
            row[field.removesuffix("_json")] = json.loads(row.pop(field))
        return row

    def record_consent(
        self,
        tenant_id: str,
        user_id: str,
        actor_id: str,
        *,
        categories: list[str],
        policy_version: str,
        granted: bool,
    ) -> dict[str, Any]:
        if set(categories).difference(SYNC_SCOPES):
            raise ResearchPlatformError("Consent contains an unsupported sync scope.")
        consent_id = new_id("consent")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p32_sync_consents VALUES(?,?,?,?,?,?,?,?)""",
                (
                    consent_id,
                    tenant_id,
                    user_id,
                    canonical_json(sorted(set(categories))),
                    policy_version[:80],
                    int(granted),
                    now_utc(),
                    actor_id,
                ),
            )
        return {"consent_id": consent_id, "granted": bool(granted)}

    def configure_endpoint(
        self,
        tenant_id: str,
        *,
        endpoint_kind: str,
        endpoint_url: str,
        auth_config: dict[str, Any] | None = None,
        certificate_pins: list[str] | None = None,
        enabled: bool = False,
    ) -> dict[str, Any]:
        parsed = urlsplit(endpoint_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ResearchPlatformError("Sync endpoint must be a credential-free HTTPS URL.")
        endpoint_id = new_id("endpoint")
        timestamp = now_utc()
        encrypted = self._encrypt(auth_config or {}) if auth_config else ""
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p32_sync_endpoints
                (endpoint_id,tenant_id,endpoint_kind,endpoint_url,certificate_pins_json,
                 encrypted_auth_config,enabled,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    endpoint_id,
                    tenant_id,
                    endpoint_kind[:80],
                    endpoint_url,
                    canonical_json(certificate_pins or []),
                    encrypted,
                    int(enabled),
                    timestamp,
                    timestamp,
                ),
            )
        return {
            "endpoint_id": endpoint_id,
            "tenant_id": tenant_id,
            "endpoint_kind": endpoint_kind,
            "endpoint_url": endpoint_url,
            "enabled": enabled,
            "auth_configured": bool(auth_config),
        }

    def _trusted_device(self, device_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        device = self.device(device_id)
        if device["state"] != "trusted":
            raise PermissionDenied("Sync device is not trusted.")
        if tenant_id is not None and device["tenant_id"] != tenant_id:
            raise PermissionDenied("Sync device belongs to a different tenant.")
        return device

    def append_change(
        self,
        tenant_id: str,
        device_id: str,
        actor_id: str,
        *,
        entity_type: str,
        entity_id: str,
        operation: str,
        payload: dict[str, Any] | list[Any] | None,
        idempotency_key: str,
        entity_version: int | None = None,
    ) -> dict[str, Any]:
        device = self._trusted_device(device_id, tenant_id)
        if operation not in SYNC_OPERATIONS:
            raise ResearchPlatformError("Unsupported sync operation.")
        if entity_type not in SYNC_SCOPES:
            raise ResearchPlatformError("Entity type is not eligible for synchronization.")
        if entity_type not in device["permissions"]:
            raise PermissionDenied("Device lacks permission for this sync category.")
        policy = self.policy(tenant_id)
        if (
            entity_type not in policy["allowed_categories"]
            or entity_type in policy["excluded_categories"]
        ):
            raise PermissionDenied("Institution sync policy excludes this category.")
        if _contains_secret(payload):
            raise PermissionDenied("Secrets and credentials are never eligible for sync.")
        existing = self.store.one(
            "SELECT * FROM education_p32_sync_journal WHERE idempotency_key=?",
            (idempotency_key,),
        )
        if existing:
            return existing
        state = self.store.one(
            """SELECT * FROM education_p32_entity_state
            WHERE tenant_id=? AND entity_type=? AND entity_id=?""",
            (tenant_id, entity_type, entity_id),
        )
        version = entity_version if entity_version is not None else int((state or {}).get("entity_version", 0)) + 1
        if version < 1:
            raise ResearchPlatformError("Entity version must be positive.")
        tombstone = int(operation in {"DELETE", "REMOVE_FILE"})
        payload_value = payload if payload is not None else {}
        plain = canonical_json(payload_value)
        checksum = hashlib.sha256(plain.encode("utf-8")).hexdigest()
        ciphertext = self._encrypt(payload_value)
        change_id = new_id("change")
        timestamp = now_utc()
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p32_sync_journal
                (change_id,idempotency_key,tenant_id,entity_type,entity_id,operation,
                 entity_version,device_id,actor_id,created_at_utc,checksum,tombstone,
                 payload_ciphertext,key_version)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    change_id,
                    idempotency_key,
                    tenant_id,
                    entity_type,
                    entity_id,
                    operation,
                    version,
                    device_id,
                    actor_id,
                    timestamp,
                    checksum,
                    tombstone,
                    ciphertext,
                ),
            )
            connection.execute(
                """INSERT INTO education_p32_sync_delivery(change_id,sync_status)
                VALUES(?,'pending')""",
                (change_id,),
            )
            connection.execute(
                """INSERT INTO education_p32_entity_state
                (tenant_id,entity_type,entity_id,entity_version,checksum,payload_ciphertext,
                 key_version,tombstone,source_device_id,updated_at_utc)
                VALUES(?,?,?,?,?,?,1,?,?,?)
                ON CONFLICT(tenant_id,entity_type,entity_id) DO UPDATE SET
                 entity_version=excluded.entity_version,checksum=excluded.checksum,
                 payload_ciphertext=excluded.payload_ciphertext,key_version=excluded.key_version,
                 tombstone=excluded.tombstone,source_device_id=excluded.source_device_id,
                 updated_at_utc=excluded.updated_at_utc""",
                (
                    tenant_id,
                    entity_type,
                    entity_id,
                    version,
                    checksum,
                    ciphertext,
                    tombstone,
                    device_id,
                    timestamp,
                ),
            )
        return self.store.one(
            "SELECT * FROM education_p32_sync_journal WHERE change_id=?",
            (change_id,),
        ) or {}

    def pending_changes(self, tenant_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
        return self.store.all(
            """SELECT j.* FROM education_p32_sync_journal j
            JOIN education_p32_sync_delivery d ON d.change_id=j.change_id
            WHERE j.tenant_id=? AND d.sync_status IN ('pending','failed')
            ORDER BY j.created_at_utc LIMIT ?""",
            (tenant_id, max(1, min(limit, 5_000))),
        )

    def _record_conflict(
        self,
        local: dict[str, Any],
        remote: dict[str, Any],
        strategy: str,
        state: str,
        reason: str,
    ) -> str:
        conflict_id = new_id("conflict")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p32_sync_conflicts
                (conflict_id,tenant_id,entity_type,entity_id,local_change_id,remote_change_id,
                 strategy,state,local_checksum,remote_checksum,resolution_reason,
                 resolved_payload_ciphertext,detected_at_utc,resolved_at_utc,resolved_by)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    conflict_id,
                    remote["tenant_id"],
                    remote["entity_type"],
                    remote["entity_id"],
                    local.get("change_id"),
                    remote.get("change_id"),
                    strategy,
                    state,
                    local["checksum"],
                    remote["checksum"],
                    reason,
                    remote["payload_ciphertext"],
                    now_utc(),
                    now_utc() if state != "open" else None,
                    "sync-engine" if state != "open" else None,
                ),
            )
        return conflict_id

    def apply_remote_change(self, tenant_id: str, remote: dict[str, Any]) -> str:
        required = {
            "change_id",
            "tenant_id",
            "entity_type",
            "entity_id",
            "entity_version",
            "device_id",
            "checksum",
            "payload_ciphertext",
            "operation",
            "created_at_utc",
            "actor_id",
            "tombstone",
            "idempotency_key",
        }
        if not required.issubset(remote):
            raise IntegrityFailure("Remote change is incomplete.")
        if remote["tenant_id"] != tenant_id:
            raise PermissionDenied("Remote change belongs to a different tenant.")
        self._trusted_device(str(remote["device_id"]), tenant_id)
        payload = self._decrypt(str(remote["payload_ciphertext"]))
        actual = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        if actual != remote["checksum"]:
            raise IntegrityFailure("Remote payload checksum mismatch.")
        if self.store.one(
            "SELECT change_id FROM education_p32_sync_journal WHERE change_id=?",
            (remote["change_id"],),
        ):
            return "duplicate"
        local = self.store.one(
            """SELECT * FROM education_p32_entity_state
            WHERE tenant_id=? AND entity_type=? AND entity_id=?""",
            (tenant_id, remote["entity_type"], remote["entity_id"]),
        )
        strategy = CONFLICT_STRATEGIES.get(remote["entity_type"], "latest_valid_version")
        if local and local["checksum"] != remote["checksum"]:
            if strategy in {"manual_resolution", "immutable_record_rejection", "client_authoritative"}:
                state = "rejected" if strategy == "immutable_record_rejection" else "open"
                self._record_conflict(local, remote, strategy, state, "Conflicting protected state.")
                return "conflict"
            if strategy == "field_level_merge":
                local_payload = self._decrypt(local["payload_ciphertext"])
                if isinstance(local_payload, dict) and isinstance(payload, dict):
                    payload = {**local_payload, **payload}
                    remote = dict(remote)
                    remote["payload_ciphertext"] = self._encrypt(payload)
                    remote["checksum"] = hashlib.sha256(
                        canonical_json(payload).encode("utf-8")
                    ).hexdigest()
                    self._record_conflict(local, remote, strategy, "resolved", "Field-level merge.")
            elif strategy == "latest_valid_version" and int(remote["entity_version"]) <= int(
                local["entity_version"]
            ):
                self._record_conflict(local, remote, strategy, "resolved", "Local version retained.")
                return "local_retained"
            elif strategy == "server_authoritative":
                self._record_conflict(local, remote, strategy, "resolved", "Authorized server version accepted.")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p32_sync_journal
                (change_id,idempotency_key,tenant_id,entity_type,entity_id,operation,
                 entity_version,device_id,actor_id,created_at_utc,checksum,tombstone,
                 payload_ciphertext,key_version)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    remote["change_id"],
                    remote["idempotency_key"],
                    tenant_id,
                    remote["entity_type"],
                    remote["entity_id"],
                    remote["operation"],
                    remote["entity_version"],
                    remote["device_id"],
                    remote["actor_id"],
                    remote["created_at_utc"],
                    remote["checksum"],
                    int(remote["tombstone"]),
                    remote["payload_ciphertext"],
                ),
            )
            connection.execute(
                """INSERT INTO education_p32_sync_delivery
                (change_id,sync_status,remote_acknowledgement)
                VALUES(?,'acknowledged','remote-import')""",
                (remote["change_id"],),
            )
            connection.execute(
                """INSERT INTO education_p32_entity_state
                (tenant_id,entity_type,entity_id,entity_version,checksum,payload_ciphertext,
                 key_version,tombstone,source_device_id,updated_at_utc)
                VALUES(?,?,?,?,?,?,1,?,?,?)
                ON CONFLICT(tenant_id,entity_type,entity_id) DO UPDATE SET
                 entity_version=excluded.entity_version,checksum=excluded.checksum,
                 payload_ciphertext=excluded.payload_ciphertext,key_version=excluded.key_version,
                 tombstone=excluded.tombstone,source_device_id=excluded.source_device_id,
                 updated_at_utc=excluded.updated_at_utc""",
                (
                    tenant_id,
                    remote["entity_type"],
                    remote["entity_id"],
                    remote["entity_version"],
                    remote["checksum"],
                    remote["payload_ciphertext"],
                    int(remote["tombstone"]),
                    remote["device_id"],
                    remote["created_at_utc"],
                ),
            )
        return "applied"

    def conflicts(self, tenant_id: str, *, state: str = "open") -> list[dict[str, Any]]:
        if state not in {"open", "resolved", "rejected"}:
            raise ResearchPlatformError("Unsupported conflict state.")
        return self.store.all(
            """SELECT conflict_id,tenant_id,entity_type,entity_id,local_change_id,
            remote_change_id,strategy,state,local_checksum,remote_checksum,
            resolution_reason,detected_at_utc,resolved_at_utc,resolved_by
            FROM education_p32_sync_conflicts
            WHERE tenant_id=? AND state=? ORDER BY detected_at_utc""",
            (tenant_id, state),
        )

    def resolve_conflict(
        self,
        tenant_id: str,
        conflict_id: str,
        resolver_id: str,
        *,
        decision: str,
        merged_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        conflict = self.store.one(
            """SELECT * FROM education_p32_sync_conflicts
            WHERE conflict_id=? AND tenant_id=?""",
            (conflict_id, tenant_id),
        )
        if not conflict:
            raise Missing("Sync conflict not found.")
        if conflict["state"] != "open":
            raise Conflict("Sync conflict is already closed.")
        if decision not in {"keep_local", "accept_remote", "merge"}:
            raise ResearchPlatformError("Unsupported manual conflict decision.")
        local = self.store.one(
            """SELECT * FROM education_p32_entity_state
            WHERE tenant_id=? AND entity_type=? AND entity_id=?""",
            (tenant_id, conflict["entity_type"], conflict["entity_id"]),
        )
        if not local:
            raise Missing("Local conflict state is missing.")
        if decision == "keep_local":
            payload = self._decrypt(local["payload_ciphertext"])
        elif decision == "accept_remote":
            payload = self._decrypt(conflict["resolved_payload_ciphertext"])
            digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            if digest != conflict["remote_checksum"]:
                raise IntegrityFailure("Stored remote conflict candidate failed integrity.")
        else:
            if not isinstance(merged_payload, dict):
                raise ResearchPlatformError("Manual merge requires an object payload.")
            payload = merged_payload
        resolution = self.append_change(
            tenant_id,
            local["source_device_id"],
            resolver_id,
            entity_type=conflict["entity_type"],
            entity_id=conflict["entity_id"],
            operation="UPDATE",
            payload=payload,
            idempotency_key=f"conflict-resolution:{conflict_id}",
            entity_version=int(local["entity_version"]) + 1,
        )
        with self.store.connection() as connection:
            connection.execute(
                """UPDATE education_p32_sync_conflicts
                SET state='resolved',resolution_reason=?,resolved_payload_ciphertext=?,
                resolved_at_utc=?,resolved_by=? WHERE conflict_id=?""",
                (
                    f"Manual resolution: {decision}",
                    resolution["payload_ciphertext"],
                    now_utc(),
                    resolver_id,
                    conflict_id,
                ),
            )
        return self.store.one(
            """SELECT conflict_id,tenant_id,entity_type,entity_id,strategy,state,
            local_checksum,remote_checksum,resolution_reason,detected_at_utc,
            resolved_at_utc,resolved_by FROM education_p32_sync_conflicts
            WHERE conflict_id=?""",
            (conflict_id,),
        ) or {}

    def sync_once(
        self,
        tenant_id: str,
        device_id: str,
        adapter: SyncAdapter,
        *,
        cursor: str = "0",
        limit: int = 500,
        cancelled: bool = False,
    ) -> SyncResult:
        self._trusted_device(device_id, tenant_id)
        policy = self.policy(tenant_id)
        if policy.get("paused"):
            raise Conflict("Synchronization is paused by policy.")
        if cancelled:
            return SyncResult(0, 0, 0, 0, cursor, new_id("support"))
        pending = self.pending_changes(tenant_id, limit=limit)
        reference = new_id("support")
        try:
            response = adapter.push(tenant_id, pending)
            acknowledged = set(response.get("acknowledged", []))
            with self.store.connection() as connection:
                for change in pending:
                    state = "acknowledged" if change["change_id"] in acknowledged else "failed"
                    connection.execute(
                        """UPDATE education_p32_sync_delivery SET sync_status=?,
                        retry_count=retry_count+1,last_attempt_at_utc=?,
                        remote_acknowledgement=?,last_error_code=?,
                        support_reference=? WHERE change_id=?""",
                        (
                            state,
                            now_utc(),
                            adapter.name if state == "acknowledged" else "",
                            "" if state == "acknowledged" else "remote_not_acknowledged",
                            reference,
                            change["change_id"],
                        ),
                    )
            pulled = adapter.pull(tenant_id, cursor, limit)
            conflicts = 0
            applied = 0
            for change in pulled.get("changes", []):
                result = self.apply_remote_change(tenant_id, change)
                conflicts += int(result == "conflict")
                applied += int(result == "applied")
            with self.store.connection() as connection:
                connection.execute(
                    """UPDATE education_p32_sync_devices SET last_sync_at_utc=?,
                    last_activity_at_utc=? WHERE device_id=?""",
                    (now_utc(), now_utc(), device_id),
                )
            return SyncResult(
                pushed=len(pending),
                pulled=applied,
                acknowledged=len(acknowledged),
                conflicts=conflicts,
                cursor=str(pulled.get("cursor", cursor)),
                support_reference=reference,
            )
        except (ConnectionError, TimeoutError, OSError) as exc:
            retry_at = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
            with self.store.connection() as connection:
                for change in pending:
                    connection.execute(
                        """UPDATE education_p32_sync_delivery SET sync_status='failed',
                        retry_count=retry_count+1,last_attempt_at_utc=?,next_retry_at_utc=?,
                        last_error_code='remote_unavailable',support_reference=?
                        WHERE change_id=?""",
                        (now_utc(), retry_at, reference, change["change_id"]),
                    )
                connection.execute(
                    """INSERT INTO education_p32_sync_incidents
                    (incident_id,tenant_id,device_id,severity,code,safe_message,
                     support_reference,details_json,created_at_utc)
                    VALUES(?,?,?,'warning','remote_unavailable',
                    'The sync service is unavailable; local changes remain queued.',?,?,?)""",
                    (
                        new_id("incident"),
                        tenant_id,
                        device_id,
                        reference,
                        canonical_json({"adapter": adapter.name, "exception": type(exc).__name__}),
                        now_utc(),
                    ),
                )
            raise ResearchPlatformError(
                f"Remote sync unavailable; changes remain queued. Reference: {reference}"
            ) from exc

    def register_file(
        self,
        tenant_id: str,
        owner_id: str,
        actor_id: str,
        *,
        entity_type: str,
        entity_id: str,
        source_path: str | Path,
        local_only: bool = False,
    ) -> dict[str, Any]:
        source = Path(source_path).resolve()
        if not source.is_file():
            raise Missing("File selected for sync was not found.")
        if source.stat().st_size > 5 * 1024**3:
            raise ResearchPlatformError("File exceeds the 5 GiB local sync limit.")
        mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        if source.suffix.lower() in {".exe", ".dll", ".msi", ".bat", ".cmd", ".ps1", ".vbs"}:
            raise PermissionDenied("Executable content is not eligible for sync.")
        policy = self.policy(tenant_id)
        used = self.store.one(
            "SELECT COALESCE(SUM(size_bytes),0) AS total FROM education_p32_sync_files WHERE tenant_id=?",
            (tenant_id,),
        )
        if int((used or {}).get("total", 0)) + source.stat().st_size > int(policy["quota_bytes"]):
            raise Conflict("Institution sync storage quota would be exceeded.")
        digest = sha256_file(source)
        existing = self.store.one(
            """SELECT * FROM education_p32_sync_files
            WHERE tenant_id=? AND entity_type=? AND entity_id=? AND sha256=?""",
            (tenant_id, entity_type, entity_id, digest),
        )
        if existing:
            return existing
        file_id = new_id("syncfile")
        destination = self.sync_root / "files" / tenant_id / digest[:2] / digest
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            staged = destination.with_suffix(".partial")
            shutil.copyfile(source, staged)
            if sha256_file(staged) != digest:
                staged.unlink(missing_ok=True)
                raise IntegrityFailure("Staged sync file checksum mismatch.")
            os.replace(staged, destination)
        timestamp = now_utc()
        version_id = new_id("fileversion")
        with self.store.connection() as connection:
            connection.execute(
                """INSERT INTO education_p32_sync_files
                (file_id,tenant_id,owner_id,entity_type,entity_id,original_name,mime_type,
                 size_bytes,sha256,current_version,local_path,availability,local_only,
                 created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,1,?,'local',?,?,?)""",
                (
                    file_id,
                    tenant_id,
                    owner_id,
                    entity_type,
                    entity_id,
                    source.name[:255],
                    mime,
                    source.stat().st_size,
                    digest,
                    str(destination),
                    int(local_only),
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                """INSERT INTO education_p32_sync_file_versions
                (file_version_id,file_id,version_number,sha256,size_bytes,storage_path,
                 created_at_utc,actor_id) VALUES(?,?,1,?,?,?,?,?)""",
                (
                    version_id,
                    file_id,
                    digest,
                    source.stat().st_size,
                    str(destination),
                    timestamp,
                    actor_id,
                ),
            )
        return self.store.one(
            "SELECT * FROM education_p32_sync_files WHERE file_id=?",
            (file_id,),
        ) or {}

    def plan_chunks(
        self,
        file_id: str,
        *,
        direction: str,
        chunk_size: int = 4 * 1024**2,
    ) -> list[dict[str, Any]]:
        if direction not in {"upload", "download"}:
            raise ResearchPlatformError("Chunk direction must be upload or download.")
        row = self.store.one(
            "SELECT * FROM education_p32_sync_files WHERE file_id=?",
            (file_id,),
        )
        if not row or not row.get("local_path"):
            raise Missing("Local file is unavailable for chunk planning.")
        source = Path(row["local_path"])
        chunks = []
        with source.open("rb") as handle:
            index = 0
            offset = 0
            while block := handle.read(max(64 * 1024, min(chunk_size, 64 * 1024**2))):
                digest = hashlib.sha256(block).hexdigest()
                chunks.append(
                    {
                        "file_id": file_id,
                        "direction": direction,
                        "chunk_index": index,
                        "byte_offset": offset,
                        "size_bytes": len(block),
                        "sha256": digest,
                        "state": "pending",
                    }
                )
                index += 1
                offset += len(block)
        with self.store.connection() as connection:
            for chunk in chunks:
                connection.execute(
                    """INSERT INTO education_p32_sync_file_chunks
                    (file_id,direction,chunk_index,byte_offset,size_bytes,sha256,state,updated_at_utc)
                    VALUES(?,?,?,?,?,?,'pending',?)
                    ON CONFLICT(file_id,direction,chunk_index) DO UPDATE SET
                     byte_offset=excluded.byte_offset,size_bytes=excluded.size_bytes,
                     sha256=excluded.sha256,updated_at_utc=excluded.updated_at_utc""",
                    (
                        file_id,
                        direction,
                        chunk["chunk_index"],
                        chunk["byte_offset"],
                        chunk["size_bytes"],
                        chunk["sha256"],
                        now_utc(),
                    ),
                )
        return chunks

    def verify_file(self, file_id: str) -> bool:
        row = self.store.one(
            "SELECT local_path,sha256 FROM education_p32_sync_files WHERE file_id=?",
            (file_id,),
        )
        if not row or not row["local_path"]:
            return False
        path = Path(row["local_path"])
        return path.is_file() and sha256_file(path) == row["sha256"]

    def status(self, tenant_id: str) -> dict[str, Any]:
        devices = self.store.all(
            """SELECT device_id,owner_id,device_name,device_type,operating_system,state,
            last_sync_at_utc,last_activity_at_utc FROM education_p32_sync_devices
            WHERE tenant_id=? ORDER BY registered_at_utc""",
            (tenant_id,),
        )
        pending = self.store.one(
            """SELECT COUNT(*) AS count FROM education_p32_sync_journal j
            JOIN education_p32_sync_delivery d ON d.change_id=j.change_id
            WHERE j.tenant_id=? AND d.sync_status IN ('pending','failed')""",
            (tenant_id,),
        )
        conflicts = self.store.one(
            "SELECT COUNT(*) AS count FROM education_p32_sync_conflicts WHERE tenant_id=? AND state='open'",
            (tenant_id,),
        )
        storage = self.store.one(
            "SELECT COALESCE(SUM(size_bytes),0) AS bytes FROM education_p32_sync_files WHERE tenant_id=?",
            (tenant_id,),
        )
        return {
            "tenant_id": tenant_id,
            "optional": True,
            "local_first": True,
            "devices": devices,
            "pending_changes": int((pending or {}).get("count", 0)),
            "open_conflicts": int((conflicts or {}).get("count", 0)),
            "storage_bytes": int((storage or {}).get("bytes", 0)),
            "policy": self.policy(tenant_id),
            "encryption_boundary": {
                "transport": "TLS required for configured remote endpoints",
                "local_sensitive_cache": "Fernet authenticated encryption",
                "end_to_end": "opaque payload mode only when devices share the account recovery key",
                "not_e2ee": "server-processed institutional records",
            },
        }

    def diagnostic_bundle(self, tenant_id: str) -> dict[str, Any]:
        incidents = self.store.all(
            """SELECT severity,code,safe_message,support_reference,created_at_utc,resolved_at_utc
            FROM education_p32_sync_incidents WHERE tenant_id=?
            ORDER BY created_at_utc DESC LIMIT 100""",
            (tenant_id,),
        )
        return {
            "schema": "biointel.phase32.sync-diagnostic.v1",
            "generated_at_utc": now_utc(),
            "status": self.status(tenant_id),
            "incidents": incidents,
            "redaction": "Tokens, authentication configuration, raw endpoints responses, and payloads excluded.",
        }
