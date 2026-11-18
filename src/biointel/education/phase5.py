from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import secrets
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .permissions import PermissionService
from .platform import ADMIN, Conflict, Denied, EducationError, Missing, ident, now

MIGRATION_ID = "education_phase5_institution_platform_v1"

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS education_campuses(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 code TEXT NOT NULL,
 name TEXT NOT NULL,
 timezone TEXT NOT NULL DEFAULT 'UTC',
 address_json TEXT NOT NULL DEFAULT '{}',
 state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,code)
);
CREATE TABLE IF NOT EXISTS education_campus_units(
 campus_id TEXT NOT NULL REFERENCES education_campuses(id),
 unit_id TEXT NOT NULL REFERENCES academic_units(id),
 linked_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 PRIMARY KEY(campus_id,unit_id)
);
CREATE TABLE IF NOT EXISTS education_identity_providers(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 provider_type TEXT NOT NULL,
 display_name TEXT NOT NULL,
 issuer_url TEXT NOT NULL DEFAULT '',
 client_id TEXT NOT NULL DEFAULT '',
 metadata_url TEXT NOT NULL DEFAULT '',
 secret_reference TEXT NOT NULL DEFAULT '',
 allowed_domains_json TEXT NOT NULL DEFAULT '[]',
 state TEXT NOT NULL DEFAULT 'draft',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,provider_type,display_name)
);
CREATE TABLE IF NOT EXISTS education_mfa_policies(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 required_roles_json TEXT NOT NULL DEFAULT '[]',
 methods_json TEXT NOT NULL DEFAULT '["totp"]',
 grace_hours INTEGER NOT NULL DEFAULT 0,
 recovery_codes_required INTEGER NOT NULL DEFAULT 1,
 state TEXT NOT NULL DEFAULT 'active',
 changed_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id)
);

CREATE TABLE IF NOT EXISTS education_database_profiles(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 engine TEXT NOT NULL,
 name TEXT NOT NULL,
 dsn_reference TEXT NOT NULL DEFAULT '',
 pool_min INTEGER NOT NULL DEFAULT 1,
 pool_max INTEGER NOT NULL DEFAULT 10,
 ssl_mode TEXT NOT NULL DEFAULT 'require',
 state TEXT NOT NULL DEFAULT 'draft',
 readiness_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,name)
);
CREATE TABLE IF NOT EXISTS education_storage_backends(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 backend_type TEXT NOT NULL,
 name TEXT NOT NULL,
 endpoint TEXT NOT NULL DEFAULT '',
 bucket TEXT NOT NULL DEFAULT '',
 region TEXT NOT NULL DEFAULT '',
 secret_reference TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'draft',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,name)
);
CREATE TABLE IF NOT EXISTS education_storage_objects(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 backend_id TEXT REFERENCES education_storage_backends(id),
 object_key TEXT NOT NULL,
 original_name TEXT NOT NULL,
 mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
 size_bytes INTEGER NOT NULL,
 sha256 TEXT NOT NULL,
 local_path TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'available',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,object_key)
);
CREATE INDEX IF NOT EXISTS idx_education_storage_hash ON education_storage_objects(institution_id,sha256,state);
CREATE TABLE IF NOT EXISTS education_background_jobs(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 queue_name TEXT NOT NULL DEFAULT 'default',
 job_type TEXT NOT NULL,
 payload_json TEXT NOT NULL DEFAULT '{}',
 state TEXT NOT NULL DEFAULT 'queued',
 priority INTEGER NOT NULL DEFAULT 50,
 attempts INTEGER NOT NULL DEFAULT 0,
 max_attempts INTEGER NOT NULL DEFAULT 3,
 available_at TEXT NOT NULL,
 locked_by TEXT NOT NULL DEFAULT '',
 lock_token TEXT NOT NULL DEFAULT '',
 locked_at TEXT,
 result_json TEXT NOT NULL DEFAULT '{}',
 error_text TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_education_jobs_claim ON education_background_jobs(state,queue_name,available_at,priority,created_at);
CREATE TABLE IF NOT EXISTS education_backup_snapshots(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 label TEXT NOT NULL,
 database_path TEXT NOT NULL,
 manifest_path TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 size_bytes INTEGER NOT NULL,
 state TEXT NOT NULL DEFAULT 'verified',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 verified_at TEXT,
 UNIQUE(institution_id,label)
);
CREATE TABLE IF NOT EXISTS education_integrations(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 provider_type TEXT NOT NULL,
 name TEXT NOT NULL,
 base_url TEXT NOT NULL DEFAULT '',
 client_id TEXT NOT NULL DEFAULT '',
 secret_reference TEXT NOT NULL DEFAULT '',
 settings_json TEXT NOT NULL DEFAULT '{}',
 state TEXT NOT NULL DEFAULT 'draft',
 last_tested_at TEXT,
 readiness_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,provider_type,name)
);
CREATE TABLE IF NOT EXISTS education_import_batches(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 import_type TEXT NOT NULL,
 file_name TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'preview',
 total_rows INTEGER NOT NULL DEFAULT 0,
 valid_rows INTEGER NOT NULL DEFAULT 0,
 invalid_rows INTEGER NOT NULL DEFAULT 0,
 summary_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_import_rows(
 id TEXT PRIMARY KEY,
 batch_id TEXT NOT NULL REFERENCES education_import_batches(id),
 row_number INTEGER NOT NULL,
 raw_json TEXT NOT NULL,
 normalized_json TEXT NOT NULL DEFAULT '{}',
 valid INTEGER NOT NULL DEFAULT 0,
 error_text TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'pending',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(batch_id,row_number)
);
CREATE TABLE IF NOT EXISTS education_governance_reports(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 report_type TEXT NOT NULL,
 title TEXT NOT NULL,
 period_start TEXT NOT NULL DEFAULT '',
 period_end TEXT NOT NULL DEFAULT '',
 payload_json TEXT NOT NULL DEFAULT '{}',
 sha256 TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'generated',
 generated_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);
INSERT OR IGNORE INTO education_migrations(id,applied_at)
 VALUES('education_phase5_institution_platform_v1',datetime('now'));
"""

IDENTITY_PROVIDERS = {"oidc", "saml", "google_workspace", "microsoft_entra"}
STORAGE_BACKENDS = {"local", "s3", "minio"}
INTEGRATION_PROVIDERS = {"moodle", "canvas", "google_classroom", "microsoft_teams", "oneroster", "lti_1_3", "scorm", "xapi"}
IMPORT_TYPES = {"members", "subjects"}
JOB_STATES = {"queued", "running", "succeeded", "failed", "cancelled"}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _decode(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError):
        return fallback


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(value: str, fallback: str = "object") -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in Path(str(value)).name)
    return cleaned[:180] or fallback


class EducationPhase5Service:
    """Institution platform operations with local-first execution and explicit external readiness boundaries."""

    def __init__(self, platform: Any, *, root: str | Path | None = None):
        self.platform = platform
        self.db = platform.db
        self.permissions = PermissionService(platform)
        self.root = Path(root).resolve() if root else Path(__file__).resolve().parents[3]
        self.data_root = Path(platform.storage).resolve() / "institution-platform"
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def migrate(self) -> str:
        with self.db.connection() as db:
            db.executescript(SCHEMA)
        return MIGRATION_ID

    def _roles(self, actor: str, institution_id: str) -> set[str]:
        return {str(row["role"]) for row in self.platform._require(actor, institution_id)}

    def _admin(self, actor: str, institution_id: str, permission: str = "institution.manage") -> None:
        self.permissions.require(actor, institution_id, permission)

    # ---------- Multi-campus hierarchy ----------
    def create_campus(self, actor: str, institution_id: str, code: str, name: str, *, timezone_name: str = "UTC", address: dict[str, Any] | None = None) -> dict[str, Any]:
        self._admin(actor, institution_id, "campus.manage")
        code = str(code).strip().upper()
        name = str(name).strip()
        if not code or not name:
            raise EducationError("Campus code and name are required.")
        campus_id, stamp = ident("campus"), now()
        try:
            with self.db.connection() as db:
                db.execute(
                    "INSERT INTO education_campuses VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (campus_id, institution_id, code, name, str(timezone_name or "UTC"), _json(address or {}), "active", actor, stamp, stamp),
                )
        except sqlite3.IntegrityError as exc:
            raise Conflict("Campus code already exists in this institution.") from exc
        self.platform._audit(actor, "campus_created", "campus", campus_id, institution_id, {"code": code})
        return self.campus(actor, campus_id)

    def campus(self, actor: str, campus_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_campuses WHERE id=?", (campus_id,))
        if not row:
            raise Missing("Campus not found.")
        self.platform._require(actor, row["institution_id"])
        row["address"] = _decode(row.pop("address_json", "{}"), {})
        return row

    def link_unit_to_campus(self, actor: str, campus_id: str, unit_id: str) -> dict[str, Any]:
        campus = self.campus(actor, campus_id)
        self._admin(actor, campus["institution_id"], "campus.manage")
        unit = self.platform._one("SELECT id,institution_id,name,unit_type FROM academic_units WHERE id=?", (unit_id,))
        if not unit:
            raise Missing("Academic unit not found.")
        if unit["institution_id"] != campus["institution_id"]:
            raise Denied("Cross-institution campus mapping denied.")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_campus_units VALUES(?,?,?,?) ON CONFLICT(campus_id,unit_id) DO NOTHING",
                (campus_id, unit_id, actor, now()),
            )
        return {"campus_id": campus_id, "unit_id": unit_id, "linked": True}

    def hierarchy(self, actor: str, institution_id: str) -> dict[str, Any]:
        self.platform._require(actor, institution_id)
        campuses = self.platform._all("SELECT * FROM education_campuses WHERE institution_id=? ORDER BY code", (institution_id,))
        units = self.platform._all("SELECT * FROM academic_units WHERE institution_id=? ORDER BY unit_type,name", (institution_id,))
        links = self.platform._all(
            "SELECT cu.campus_id,cu.unit_id FROM education_campus_units cu JOIN education_campuses c ON c.id=cu.campus_id WHERE c.institution_id=?",
            (institution_id,),
        )
        unit_map: dict[str, list[str]] = {}
        for link in links:
            unit_map.setdefault(link["campus_id"], []).append(link["unit_id"])
        for campus in campuses:
            campus["address"] = _decode(campus.pop("address_json", "{}"), {})
            campus["unit_ids"] = unit_map.get(campus["id"], [])
        return {"institution_id": institution_id, "campuses": campuses, "academic_units": units, "unassigned_unit_ids": [u["id"] for u in units if not any(u["id"] in ids for ids in unit_map.values())]}

    # ---------- Identity and MFA readiness ----------
    @staticmethod
    def _reject_inline_secret(values: Iterable[str]) -> None:
        for value in values:
            text = str(value or "").strip().lower()
            if any(marker in text for marker in ("client_secret=", "password=", "private_key=", "-----begin private key")):
                raise Denied("Inline secrets are forbidden. Store credentials in a secret vault and provide only a reference.")

    def configure_identity_provider(self, actor: str, institution_id: str, provider_type: str, display_name: str, *, issuer_url: str = "", client_id: str = "", metadata_url: str = "", secret_reference: str = "", allowed_domains: list[str] | None = None, activate: bool = False) -> dict[str, Any]:
        self._admin(actor, institution_id, "identity.manage")
        provider_type = str(provider_type).strip().lower()
        if provider_type not in IDENTITY_PROVIDERS:
            raise EducationError("Unsupported identity provider type.")
        self._reject_inline_secret((issuer_url, client_id, metadata_url, secret_reference))
        if activate and not secret_reference:
            raise Conflict("A vault/environment secret reference is required before activation.")
        if provider_type in {"oidc", "google_workspace", "microsoft_entra"} and activate and not issuer_url:
            raise Conflict("OIDC issuer URL is required before activation.")
        if provider_type == "saml" and activate and not metadata_url:
            raise Conflict("SAML metadata URL is required before activation.")
        domains = sorted({str(item).strip().lower() for item in (allowed_domains or []) if str(item).strip()})
        provider_id, stamp = ident("idp"), now()
        state = "ready" if activate else "draft"
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_identity_providers VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (provider_id, institution_id, provider_type, str(display_name).strip(), issuer_url.strip(), client_id.strip(), metadata_url.strip(), secret_reference.strip(), _json(domains), state, actor, stamp, stamp),
            )
        return self.identity_posture(actor, institution_id)

    def save_mfa_policy(self, actor: str, institution_id: str, *, required_roles: list[str], methods: list[str], grace_hours: int = 0, recovery_codes_required: bool = True) -> dict[str, Any]:
        self._admin(actor, institution_id, "identity.manage")
        methods_set = sorted({str(item).strip().lower() for item in methods if str(item).strip()})
        if not methods_set or any(item not in {"totp", "webauthn", "email_otp"} for item in methods_set):
            raise EducationError("MFA methods must use TOTP, WebAuthn or email OTP.")
        if grace_hours < 0 or grace_hours > 720:
            raise EducationError("MFA grace period must be between 0 and 720 hours.")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_mfa_policies VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id) DO UPDATE SET required_roles_json=excluded.required_roles_json,methods_json=excluded.methods_json,
                grace_hours=excluded.grace_hours,recovery_codes_required=excluded.recovery_codes_required,state='active',changed_by=excluded.changed_by,updated_at=excluded.updated_at""",
                (ident("mfa"), institution_id, _json(sorted(set(required_roles))), _json(methods_set), int(grace_hours), int(bool(recovery_codes_required)), "active", actor, stamp, stamp),
            )
        return self.identity_posture(actor, institution_id)

    def identity_posture(self, actor: str, institution_id: str) -> dict[str, Any]:
        self.platform._require(actor, institution_id)
        providers = self.platform._all("SELECT * FROM education_identity_providers WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        for row in providers:
            row["allowed_domains"] = _decode(row.pop("allowed_domains_json", "[]"), [])
            row["secret_reference"] = "configured" if row.get("secret_reference") else "missing"
        policy = self.platform._one("SELECT * FROM education_mfa_policies WHERE institution_id=?", (institution_id,))
        if policy:
            policy["required_roles"] = _decode(policy.pop("required_roles_json", "[]"), [])
            policy["methods"] = _decode(policy.pop("methods_json", "[]"), [])
        active = sum(1 for item in providers if item["state"] == "ready")
        score = min(100, (35 if active else 0) + (35 if policy else 0) + (15 if policy and "webauthn" in policy["methods"] else 0) + (15 if any(p["allowed_domains"] for p in providers) else 0))
        return {"institution_id": institution_id, "providers": providers, "mfa_policy": policy, "readiness_score": score, "external_login_verified": False}


    def configure_database_profile(self, actor: str, institution_id: str, engine: str, name: str, *, dsn_reference: str = "", pool_min: int = 1, pool_max: int = 10, ssl_mode: str = "require", activate: bool = False) -> dict[str, Any]:
        self._admin(actor, institution_id, "database.manage")
        engine = str(engine).strip().lower()
        if engine not in {"sqlite", "postgresql"}:
            raise EducationError("Database engine must be SQLite or PostgreSQL.")
        self._reject_inline_secret((dsn_reference,))
        if pool_min < 1 or pool_max < pool_min or pool_max > 500:
            raise EducationError("Invalid database connection pool limits.")
        if ssl_mode not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
            raise EducationError("Unsupported database SSL mode.")
        if engine == "postgresql" and activate and not dsn_reference:
            raise Conflict("PostgreSQL activation requires a vault/environment DSN reference.")
        readiness = {
            "driver_contract_ready": True,
            "migration_contract_ready": True,
            "dsn_reference_present": bool(dsn_reference) or engine == "sqlite",
            "ssl_required": ssl_mode in {"require", "verify-ca", "verify-full"},
            "network_verified": engine == "sqlite",
            "credentials_verified": engine == "sqlite",
            "failover_verified": False,
        }
        profile_id, stamp = ident("dbprofile"), now()
        state = "local_ready" if engine == "sqlite" else ("configuration_ready" if activate else "draft")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_database_profiles VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (profile_id, institution_id, engine, str(name).strip(), dsn_reference.strip(), int(pool_min), int(pool_max), ssl_mode, state, _json(readiness), actor, stamp, stamp),
            )
        return self.database_profile(actor, profile_id)

    def database_profile(self, actor: str, profile_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_database_profiles WHERE id=?", (profile_id,))
        if not row:
            raise Missing("Database profile not found.")
        self.platform._require(actor, row["institution_id"])
        row["readiness"] = _decode(row.pop("readiness_json", "{}"), {})
        row["dsn_reference"] = "configured" if row.get("dsn_reference") else "missing"
        return row

    def database_posture(self, actor: str, institution_id: str) -> dict[str, Any]:
        self.platform._require(actor, institution_id)
        rows = self.platform._all("SELECT * FROM education_database_profiles WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        profiles = []
        for row in rows:
            row["readiness"] = _decode(row.pop("readiness_json", "{}"), {})
            row["dsn_reference"] = "configured" if row.get("dsn_reference") else "missing"
            profiles.append(row)
        postgres = [row for row in profiles if row["engine"] == "postgresql"]
        return {
            "institution_id": institution_id,
            "profiles": profiles,
            "postgresql_configuration_ready": any(row["state"] == "configuration_ready" for row in postgres),
            "postgresql_network_verified": any(bool(row["readiness"].get("network_verified")) for row in postgres),
            "production_database_verified": False,
        }

    # ---------- Storage and backups ----------
    def configure_storage_backend(self, actor: str, institution_id: str, backend_type: str, name: str, *, endpoint: str = "", bucket: str = "", region: str = "", secret_reference: str = "", activate: bool = False) -> dict[str, Any]:
        self._admin(actor, institution_id, "storage.manage")
        backend_type = str(backend_type).strip().lower()
        if backend_type not in STORAGE_BACKENDS:
            raise EducationError("Unsupported storage backend.")
        self._reject_inline_secret((endpoint, bucket, region, secret_reference))
        if backend_type != "local" and activate and (not endpoint or not bucket or not secret_reference):
            raise Conflict("External storage requires endpoint, bucket and secret reference before activation.")
        backend_id, stamp = ident("storage"), now()
        state = "ready" if backend_type == "local" or activate else "draft"
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_storage_backends VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (backend_id, institution_id, backend_type, str(name).strip(), endpoint.strip(), bucket.strip(), region.strip(), secret_reference.strip(), state, actor, stamp, stamp),
            )
        return self.platform._one("SELECT * FROM education_storage_backends WHERE id=?", (backend_id,))

    def store_local_object(self, actor: str, institution_id: str, source_path: str | Path, *, object_key: str = "", mime_type: str = "application/octet-stream") -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "storage.write")
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise Missing("Source file not found.")
        if source.stat().st_size > 2 * 1024**3:
            raise EducationError("Object exceeds the 2 GiB local storage limit.")
        digest = _sha256_path(source)
        key = str(object_key or f"objects/{digest[:2]}/{digest}-{_safe_name(source.name)}").strip().lstrip("/")
        if ".." in Path(key).parts:
            raise Denied("Unsafe object key.")
        existing = self.platform._one("SELECT * FROM education_storage_objects WHERE institution_id=? AND sha256=? AND state='available'", (institution_id, digest))
        if existing:
            existing["deduplicated"] = True
            return existing
        destination = (self.data_root / institution_id / "objects" / key).resolve()
        tenant_root = (self.data_root / institution_id / "objects").resolve()
        if tenant_root not in destination.parents:
            raise Denied("Object path escaped tenant storage root.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        object_id, stamp = ident("obj"), now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_storage_objects VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (object_id, institution_id, None, key, source.name[:255], mime_type, destination.stat().st_size, digest, str(destination), "available", actor, stamp, stamp),
            )
        result = self.platform._one("SELECT * FROM education_storage_objects WHERE id=?", (object_id,))
        result["deduplicated"] = False
        return result

    def create_backup(self, actor: str, institution_id: str, label: str) -> dict[str, Any]:
        self._admin(actor, institution_id, "backup.manage")
        safe_label = _safe_name(label, "snapshot")
        existing = self.platform._one("SELECT id FROM education_backup_snapshots WHERE institution_id=? AND label=?", (institution_id, safe_label))
        if existing:
            raise Conflict("Backup label already exists.")
        folder = self.data_root / institution_id / "backups" / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{safe_label}"
        folder.mkdir(parents=True, exist_ok=False)
        db_copy = folder / "education.sqlite3"
        source_db = sqlite3.connect(self.db.path, timeout=30)
        target_db = sqlite3.connect(db_copy)
        try:
            source_db.backup(target_db)
        finally:
            target_db.close()
            source_db.close()
        check = sqlite3.connect(db_copy)
        try:
            quick = check.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            check.close()
        if quick != "ok":
            raise EducationError("Backup database integrity check failed.")
        digest = _sha256_path(db_copy)
        media_files = []
        tenant_media = Path(self.platform.storage) / institution_id
        if tenant_media.exists():
            for item in sorted(tenant_media.rglob("*")):
                if item.is_file() and self.data_root not in item.parents:
                    media_files.append({"path": item.relative_to(self.platform.storage).as_posix(), "size_bytes": item.stat().st_size, "sha256": _sha256_path(item)})
        manifest = {"schema": "biointel.education-backup.v1", "institution_id": institution_id, "created_at": now(), "database": {"path": db_copy.name, "size_bytes": db_copy.stat().st_size, "sha256": digest}, "media_inventory": media_files, "live_database_replaced": False}
        manifest_path = folder / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        snapshot_id, stamp = ident("backup"), now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_backup_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (snapshot_id, institution_id, safe_label, str(db_copy), str(manifest_path), digest, db_copy.stat().st_size, "verified", actor, stamp, stamp),
            )
        return self.verify_backup(actor, snapshot_id)

    def verify_backup(self, actor: str, snapshot_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_backup_snapshots WHERE id=?", (snapshot_id,))
        if not row:
            raise Missing("Backup snapshot not found.")
        self._admin(actor, row["institution_id"], "backup.manage")
        db_path, manifest_path = Path(row["database_path"]), Path(row["manifest_path"])
        valid = db_path.is_file() and manifest_path.is_file() and _sha256_path(db_path) == row["sha256"]
        quick = False
        if valid:
            check = sqlite3.connect(db_path)
            try:
                quick = check.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            finally:
                check.close()
        state = "verified" if valid and quick else "invalid"
        with self.db.connection() as db:
            db.execute("UPDATE education_backup_snapshots SET state=?,verified_at=? WHERE id=?", (state, now(), snapshot_id))
        result = self.platform._one("SELECT * FROM education_backup_snapshots WHERE id=?", (snapshot_id,))
        result["integrity_valid"] = state == "verified"
        result["restore_performed"] = False
        return result

    def restore_rehearsal(self, actor: str, snapshot_id: str) -> dict[str, Any]:
        verified = self.verify_backup(actor, snapshot_id)
        if not verified["integrity_valid"]:
            raise Conflict("Invalid backup cannot be rehearsed.")
        source = Path(verified["database_path"])
        target = source.parent / "restore-rehearsal.sqlite3"
        shutil.copy2(source, target)
        check = sqlite3.connect(target)
        try:
            integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
            institution_count = check.execute("SELECT COUNT(*) FROM institutions").fetchone()[0]
        finally:
            check.close()
        return {"snapshot_id": snapshot_id, "rehearsal_path": str(target), "integrity": integrity, "institution_count": institution_count, "live_database_replaced": False}

    # ---------- Durable local queue ----------
    def enqueue_job(self, actor: str, institution_id: str, job_type: str, payload: dict[str, Any] | None = None, *, queue_name: str = "default", priority: int = 50, max_attempts: int = 3, available_at: str | None = None) -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "jobs.enqueue")
        if priority < 0 or priority > 100 or max_attempts < 1 or max_attempts > 20:
            raise EducationError("Invalid job priority or retry policy.")
        stamp, job_id = now(), ident("job")
        due = available_at or stamp
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_background_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (job_id, institution_id, str(queue_name or "default")[:80], str(job_type)[:120], _json(payload or {}), "queued", int(priority), 0, int(max_attempts), due, "", "", None, "{}", "", actor, stamp, stamp),
            )
        return self.job(actor, job_id)

    def claim_job(self, worker_id: str, *, queue_name: str = "default") -> dict[str, Any] | None:
        worker_id = str(worker_id).strip()
        if not worker_id:
            raise EducationError("Worker ID is required.")
        token = secrets.token_urlsafe(24)
        with self.db.connection() as db:
            row = db.execute(
                """SELECT * FROM education_background_jobs WHERE state='queued' AND queue_name=? AND available_at<=?
                ORDER BY priority DESC,created_at LIMIT 1""",
                (queue_name, now()),
            ).fetchone()
            if not row:
                return None
            job_id = row["id"]
            updated = db.execute(
                """UPDATE education_background_jobs SET state='running',locked_by=?,lock_token=?,locked_at=?,attempts=attempts+1,updated_at=?
                WHERE id=? AND state='queued'""",
                (worker_id, token, now(), now(), job_id),
            ).rowcount
            if updated != 1:
                return None
        result = self.platform._one("SELECT * FROM education_background_jobs WHERE id=?", (job_id,))
        result["payload"] = _decode(result.pop("payload_json"), {})
        return result

    def complete_job(self, worker_id: str, job_id: str, lock_token: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.db.connection() as db:
            updated = db.execute(
                """UPDATE education_background_jobs SET state='succeeded',result_json=?,error_text='',updated_at=?
                WHERE id=? AND state='running' AND locked_by=? AND lock_token=?""",
                (_json(result or {}), now(), job_id, worker_id, lock_token),
            ).rowcount
        if updated != 1:
            raise Denied("Job lock ownership validation failed.")
        return self.platform._one("SELECT * FROM education_background_jobs WHERE id=?", (job_id,))

    def fail_job(self, worker_id: str, job_id: str, lock_token: str, error_text: str, *, retry_delay_seconds: int = 60) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_background_jobs WHERE id=?", (job_id,))
        if not row or row["state"] != "running" or row["locked_by"] != worker_id or row["lock_token"] != lock_token:
            raise Denied("Job lock ownership validation failed.")
        retry = int(row["attempts"]) < int(row["max_attempts"])
        state = "queued" if retry else "failed"
        available = (datetime.now(timezone.utc) + timedelta(seconds=max(0, int(retry_delay_seconds)))).isoformat()
        with self.db.connection() as db:
            db.execute(
                "UPDATE education_background_jobs SET state=?,available_at=?,error_text=?,locked_by='',lock_token='',locked_at=NULL,updated_at=? WHERE id=?",
                (state, available, str(error_text)[:4000], now(), job_id),
            )
        return self.platform._one("SELECT * FROM education_background_jobs WHERE id=?", (job_id,))

    def job(self, actor: str, job_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_background_jobs WHERE id=?", (job_id,))
        if not row:
            raise Missing("Background job not found.")
        self.platform._require(actor, row["institution_id"])
        row["payload"] = _decode(row.pop("payload_json"), {})
        row["result"] = _decode(row.pop("result_json"), {})
        row.pop("lock_token", None)
        return row

    # ---------- Integrations ----------
    def configure_integration(self, actor: str, institution_id: str, provider_type: str, name: str, *, base_url: str = "", client_id: str = "", secret_reference: str = "", settings: dict[str, Any] | None = None, activate: bool = False) -> dict[str, Any]:
        self._admin(actor, institution_id, "integrations.manage")
        provider_type = str(provider_type).strip().lower()
        if provider_type not in INTEGRATION_PROVIDERS:
            raise EducationError("Unsupported institutional integration.")
        self._reject_inline_secret((base_url, client_id, secret_reference, _json(settings or {})))
        if activate and provider_type not in {"scorm", "xapi"} and (not base_url or not secret_reference):
            raise Conflict("Remote integration requires endpoint and secret reference before activation.")
        integration_id, stamp = ident("integration"), now()
        readiness = {"configuration_complete": bool(base_url or provider_type in {"scorm", "xapi"}), "secret_reference_present": bool(secret_reference), "network_verified": False, "external_credentials_verified": False}
        state = "configured" if activate else "draft"
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_integrations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (integration_id, institution_id, provider_type, str(name).strip(), base_url.strip(), client_id.strip(), secret_reference.strip(), _json(settings or {}), state, None, _json(readiness), actor, stamp, stamp),
            )
        return self.integration(actor, integration_id)

    def integration(self, actor: str, integration_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_integrations WHERE id=?", (integration_id,))
        if not row:
            raise Missing("Integration not found.")
        self.platform._require(actor, row["institution_id"])
        row["settings"] = _decode(row.pop("settings_json", "{}"), {})
        row["readiness"] = _decode(row.pop("readiness_json", "{}"), {})
        row["secret_reference"] = "configured" if row.get("secret_reference") else "missing"
        return row

    def test_integration_readiness(self, actor: str, integration_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_integrations WHERE id=?", (integration_id,))
        if not row:
            raise Missing("Integration not found.")
        self._admin(actor, row["institution_id"], "integrations.manage")
        settings = _decode(row["settings_json"], {})
        base = str(row["base_url"] or "")
        readiness = {
            "provider_supported": row["provider_type"] in INTEGRATION_PROVIDERS,
            "configuration_complete": bool(base or row["provider_type"] in {"scorm", "xapi"}),
            "secret_reference_present": bool(row["secret_reference"]) or row["provider_type"] in {"scorm", "xapi"},
            "settings_serializable": isinstance(settings, dict),
            "network_verified": False,
            "external_credentials_verified": False,
        }
        state = "configuration_ready" if all(readiness[key] for key in ("provider_supported", "configuration_complete", "secret_reference_present", "settings_serializable")) else "configuration_required"
        with self.db.connection() as db:
            db.execute("UPDATE education_integrations SET state=?,last_tested_at=?,readiness_json=?,updated_at=? WHERE id=?", (state, now(), _json(readiness), now(), integration_id))
        return self.integration(actor, integration_id)

    # ---------- Roster imports ----------
    def preview_import(self, actor: str, institution_id: str, import_type: str, file_name: str, content: bytes | str) -> dict[str, Any]:
        self._admin(actor, institution_id, "imports.manage")
        import_type = str(import_type).strip().lower()
        if import_type not in IMPORT_TYPES:
            raise EducationError("Unsupported import type.")
        raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        if len(raw) > 25 * 1024**2:
            raise EducationError("Import file exceeds 25 MiB.")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise EducationError("Import must be UTF-8 CSV.") from exc
        reader = csv.DictReader(io.StringIO(text))
        required = {"user_id", "role"} if import_type == "members" else {"code", "name"}
        if not reader.fieldnames or not required.issubset({str(x).strip() for x in reader.fieldnames}):
            raise EducationError(f"CSV requires columns: {', '.join(sorted(required))}.")
        rows: list[tuple[int, dict[str, Any], dict[str, Any], bool, str]] = []
        seen: set[str] = set()
        for number, row in enumerate(reader, start=2):
            raw_row = {str(k).strip(): str(v or "").strip() for k, v in row.items() if k is not None}
            if import_type == "members":
                normalized = {"user_id": raw_row.get("user_id", ""), "role": raw_row.get("role", "")}
                key = f"{normalized['user_id']}|{normalized['role']}"
                error = ""
                if not normalized["user_id"] or not normalized["role"]:
                    error = "user_id and role are required"
                elif normalized["role"] not in __import__("biointel.education.platform", fromlist=["ROLES"]).ROLES:
                    error = "unsupported role"
            else:
                normalized = {"code": raw_row.get("code", "").upper(), "name": raw_row.get("name", ""), "syllabus": raw_row.get("syllabus", ""), "unit_id": raw_row.get("unit_id", "")}
                key = normalized["code"]
                error = "" if normalized["code"] and normalized["name"] else "code and name are required"
            if key in seen and not error:
                error = "duplicate row in import"
            seen.add(key)
            rows.append((number, raw_row, normalized, not bool(error), error))
            if len(rows) > 100_000:
                raise EducationError("Import exceeds 100,000 rows.")
        batch_id, stamp = ident("import"), now()
        valid_count = sum(1 for row in rows if row[3])
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_import_batches VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (batch_id, institution_id, import_type, _safe_name(file_name, "import.csv"), hashlib.sha256(raw).hexdigest(), "preview", len(rows), valid_count, len(rows) - valid_count, _json({"required_columns": sorted(required)}), actor, stamp, stamp),
            )
            db.executemany(
                "INSERT INTO education_import_rows VALUES(?,?,?,?,?,?,?,?,?,?)",
                [(ident("importrow"), batch_id, number, _json(raw_row), _json(normalized), int(valid), error, "pending", stamp, stamp) for number, raw_row, normalized, valid, error in rows],
            )
        return self.import_batch(actor, batch_id)

    def import_batch(self, actor: str, batch_id: str) -> dict[str, Any]:
        batch = self.platform._one("SELECT * FROM education_import_batches WHERE id=?", (batch_id,))
        if not batch:
            raise Missing("Import batch not found.")
        self.platform._require(actor, batch["institution_id"])
        batch["summary"] = _decode(batch.pop("summary_json", "{}"), {})
        batch["errors"] = self.platform._all("SELECT row_number,error_text FROM education_import_rows WHERE batch_id=? AND valid=0 ORDER BY row_number LIMIT 100", (batch_id,))
        return batch

    def commit_import(self, actor: str, batch_id: str) -> dict[str, Any]:
        batch = self.import_batch(actor, batch_id)
        self._admin(actor, batch["institution_id"], "imports.manage")
        if batch["state"] != "preview":
            raise Conflict("Only preview imports may be committed.")
        if int(batch["invalid_rows"]) > 0:
            raise Conflict("Import contains invalid rows and cannot be committed.")
        rows = self.platform._all("SELECT * FROM education_import_rows WHERE batch_id=? ORDER BY row_number", (batch_id,))
        with self.db.connection() as db:
            if batch["import_type"] == "members":
                for row in rows:
                    data = _decode(row["normalized_json"], {})
                    stamp = now()
                    db.execute(
                        "INSERT INTO memberships VALUES(?,?,?,?,?,?,?) ON CONFLICT(institution_id,user_id,role) DO UPDATE SET state='active',updated_at=excluded.updated_at",
                        (ident("mem"), batch["institution_id"], data["user_id"], data["role"], "active", stamp, stamp),
                    )
                    db.execute("UPDATE education_import_rows SET state='committed',updated_at=? WHERE id=?", (stamp, row["id"]))
            else:
                for row in rows:
                    data = _decode(row["normalized_json"], {})
                    if data.get("unit_id"):
                        unit = db.execute("SELECT institution_id FROM academic_units WHERE id=?", (data["unit_id"],)).fetchone()
                        if not unit or unit["institution_id"] != batch["institution_id"]:
                            raise Denied("Subject import contains invalid cross-institution unit.")
                    stamp = now()
                    db.execute(
                        "INSERT INTO subjects VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(institution_id,code) DO UPDATE SET name=excluded.name,syllabus=excluded.syllabus,updated_at=excluded.updated_at",
                        (ident("subj"), batch["institution_id"], data.get("unit_id") or None, data["code"], data["name"], data.get("syllabus", ""), "active", stamp, stamp),
                    )
                    db.execute("UPDATE education_import_rows SET state='committed',updated_at=? WHERE id=?", (stamp, row["id"]))
            db.execute("UPDATE education_import_batches SET state='committed',updated_at=? WHERE id=?", (now(), batch_id))
        self.platform._audit(actor, "import_committed", "import_batch", batch_id, batch["institution_id"], {"rows": len(rows), "type": batch["import_type"]})
        return self.import_batch(actor, batch_id)

    # ---------- Governance reporting ----------
    def generate_governance_report(self, actor: str, institution_id: str, *, report_type: str = "institution_readiness", period_start: str = "", period_end: str = "") -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "governance.reports")
        counts = {}
        for key, query in {
            "members": "SELECT COUNT(DISTINCT user_id) n FROM memberships WHERE institution_id=? AND state='active'",
            "campuses": "SELECT COUNT(*) n FROM education_campuses WHERE institution_id=? AND state='active'",
            "subjects": "SELECT COUNT(*) n FROM subjects WHERE institution_id=? AND state='active'",
            "queued_jobs": "SELECT COUNT(*) n FROM education_background_jobs WHERE institution_id=? AND state IN ('queued','running')",
            "verified_backups": "SELECT COUNT(*) n FROM education_backup_snapshots WHERE institution_id=? AND state='verified'",
            "configured_integrations": "SELECT COUNT(*) n FROM education_integrations WHERE institution_id=? AND state IN ('configured','configuration_ready')",
            "storage_objects": "SELECT COUNT(*) n FROM education_storage_objects WHERE institution_id=? AND state='available'",
        }.items():
            counts[key] = int(self.platform._one(query, (institution_id,))["n"])
        identity = self.identity_posture(actor, institution_id)
        payload = {
            "schema": "biointel.education-governance-report.v1",
            "institution_id": institution_id,
            "report_type": report_type,
            "period": {"start": period_start, "end": period_end},
            "counts": counts,
            "identity_readiness": identity["readiness_score"],
            "external_qualification": {"sso_login_verified": False, "external_integrations_verified": False, "production_database_verified": False, "object_storage_network_verified": False},
            "human_review_required": True,
            "generated_at": now(),
        }
        digest = hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()
        report_id = ident("govreport")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_governance_reports VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (report_id, institution_id, report_type, "Institution Platform Readiness", period_start, period_end, _json(payload), digest, "generated", actor, now()),
            )
        return {"id": report_id, "sha256": digest, "payload": payload, "state": "generated"}

    def dashboard(self, actor: str, institution_id: str) -> dict[str, Any]:
        self.platform._require(actor, institution_id)
        hierarchy = self.hierarchy(actor, institution_id)
        identity = self.identity_posture(actor, institution_id)
        def count(sql: str) -> int:
            return int(self.platform._one(sql, (institution_id,))["n"])
        return {
            "institution_id": institution_id,
            "campuses": len(hierarchy["campuses"]),
            "academic_units": len(hierarchy["academic_units"]),
            "identity_readiness": identity["readiness_score"],
            "storage_objects": count("SELECT COUNT(*) n FROM education_storage_objects WHERE institution_id=? AND state='available'"),
            "verified_backups": count("SELECT COUNT(*) n FROM education_backup_snapshots WHERE institution_id=? AND state='verified'"),
            "queued_jobs": count("SELECT COUNT(*) n FROM education_background_jobs WHERE institution_id=? AND state IN ('queued','running')"),
            "integrations": count("SELECT COUNT(*) n FROM education_integrations WHERE institution_id=?"),
            "imports": count("SELECT COUNT(*) n FROM education_import_batches WHERE institution_id=?"),
            "database_profiles": count("SELECT COUNT(*) n FROM education_database_profiles WHERE institution_id=?"),
            "production_database_verified": False,
            "external_services_verified": False,
        }
