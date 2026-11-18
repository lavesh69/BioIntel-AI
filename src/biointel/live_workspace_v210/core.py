from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from biointel.database.core import managed_connect

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MENTION = re.compile(r"(?<![\w@])@([A-Za-z0-9][A-Za-z0-9._-]{0,63})")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class LiveWorkspaceError(RuntimeError):
    """Base error for collaboration operations."""


class PermissionDenied(LiveWorkspaceError):
    pass


class RecordLocked(LiveWorkspaceError):
    def __init__(self, message: str, *, lock: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.lock = lock or {}


class RevisionConflict(LiveWorkspaceError):
    def __init__(self, message: str, *, current_revision: int) -> None:
        super().__init__(message)
        self.current_revision = int(current_revision)


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_text(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat(timespec="seconds")


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _clean_text(value: object, *, maximum: int, field: str, allow_empty: bool = True) -> str:
    text = _CONTROL.sub("", str(value or "")).strip()
    text = " ".join(text.split())
    if not allow_empty and not text:
        raise ValueError(f"{field} is required.")
    if len(text) > maximum:
        raise ValueError(f"{field} must be {maximum} characters or fewer.")
    return text


def _safe_id(value: object, *, field: str, allow_empty: bool = False) -> str:
    text = _clean_text(value, maximum=128, field=field, allow_empty=allow_empty)
    if not text and allow_empty:
        return ""
    if not _SAFE_ID.fullmatch(text):
        raise ValueError(f"{field} contains unsupported characters.")
    return text


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _decode(value: object, fallback: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (json.JSONDecodeError, TypeError):
        return fallback


def _hash_secret(secret: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 180_000)
    return f"pbkdf2_sha256$180000${salt.hex()}${digest.hex()}"


def _verify_secret(secret: str, encoded: str) -> bool:
    try:
        algorithm, rounds_text, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        computed = hashlib.pbkdf2_hmac(
            "sha256", secret.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds_text)
        ).hex()
        return hmac.compare_digest(computed, digest_hex)
    except (ValueError, TypeError):
        return False


def _state_root() -> Path:
    configured = os.environ.get("BIOINTEL_USER_DATA_DIR", "").strip()
    base = Path(configured).expanduser() if configured else PROJECT_ROOT / "UserData"
    target = base.resolve() / "workspace" / "live_workspace"
    target.mkdir(parents=True, exist_ok=True)
    return target


def default_store_path() -> Path:
    override = os.environ.get("BIOINTEL_LIVE_WORKSPACE_DB", "").strip()
    if override:
        path = Path(override).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return _state_root() / "live_workspace.sqlite3"


def host_config_path() -> Path:
    override = os.environ.get("BIOINTEL_LIVE_WORKSPACE_HOST_CONFIG", "").strip()
    return Path(override).expanduser().resolve() if override else _state_root() / "host_config.json"


def load_host_config() -> dict[str, Any]:
    path = host_config_path()
    defaults = {
        "enabled": False,
        "workspace_name": "BioIntel Lab Workspace",
        "presence_ttl_seconds": 45,
        "lock_ttl_seconds": 120,
        "default_join_role": "researcher",
        "allow_lan_only": True,
        "bind_lan": False,
        "require_ui_auth": True,
        "api_lan_enabled": False,
        "max_active_users": 25,
        "backup_retention": 20,
        "backup_interval_hours": 12,
        "https_enabled": False,
        "tls_cert_file": "",
        "tls_key_file": "",
        "updated_at_utc": "",
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(payload, dict):
        return defaults
    return {**defaults, **payload}


def save_host_config(payload: dict[str, Any]) -> dict[str, Any]:
    current = load_host_config()
    allowed = {
        "enabled",
        "workspace_name",
        "presence_ttl_seconds",
        "lock_ttl_seconds",
        "default_join_role",
        "allow_lan_only",
        "bind_lan",
        "require_ui_auth",
        "api_lan_enabled",
        "max_active_users",
        "backup_retention",
        "backup_interval_hours",
        "https_enabled",
        "tls_cert_file",
        "tls_key_file",
    }
    for key, value in payload.items():
        if key in allowed:
            current[key] = value
    current["workspace_name"] = _clean_text(
        current.get("workspace_name"), maximum=120, field="workspace_name", allow_empty=False
    )
    current["presence_ttl_seconds"] = min(max(int(current.get("presence_ttl_seconds", 45)), 20), 300)
    current["lock_ttl_seconds"] = min(max(int(current.get("lock_ttl_seconds", 120)), 30), 900)
    role = str(current.get("default_join_role", "researcher")).strip().lower()
    if role not in LiveWorkspaceStore.MEMBER_ROLES - {"owner", "admin", "guest"}:
        raise ValueError("default_join_role must be viewer, reviewer or researcher.")
    current["default_join_role"] = role
    current["enabled"] = bool(current.get("enabled"))
    current["allow_lan_only"] = bool(current.get("allow_lan_only", True))
    current["bind_lan"] = bool(current.get("bind_lan", current["enabled"]))
    current["require_ui_auth"] = bool(current.get("require_ui_auth", True))
    current["api_lan_enabled"] = bool(current.get("api_lan_enabled", False))
    current["max_active_users"] = min(max(int(current.get("max_active_users", 25)), 2), 100)
    current["backup_retention"] = min(max(int(current.get("backup_retention", 20)), 1), 200)
    current["backup_interval_hours"] = min(max(int(current.get("backup_interval_hours", 12)), 1), 168)
    current["https_enabled"] = bool(current.get("https_enabled", False))
    current["tls_cert_file"] = _clean_text(current.get("tls_cert_file", ""), maximum=1000, field="tls_cert_file")
    current["tls_key_file"] = _clean_text(current.get("tls_key_file", ""), maximum=1000, field="tls_key_file")
    if current["https_enabled"] and not (current["tls_cert_file"] and current["tls_key_file"]):
        raise ValueError("HTTPS requires both a TLS certificate file and private-key file.")
    current["updated_at_utc"] = utc_text()
    path = host_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(_json(current) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return current


@dataclass(frozen=True)
class Workspace:
    workspace_id: str
    tenant_id: str
    name: str
    description: str
    status: str
    default_join_role: str
    created_by: str
    created_at_utc: str
    updated_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LiveWorkspaceStore:
    """Concurrent local-first collaboration store.

    Presence contains only explicit workspace context. Uploaded rows, patient fields,
    sequences, images and result payloads are never written to presence/activity tables.
    """

    MEMBER_ROLES = {"guest", "viewer", "reviewer", "researcher", "admin", "owner"}
    WRITE_ROLES = {"reviewer", "researcher", "admin", "owner"}
    EDIT_ROLES = {"researcher", "admin", "owner"}
    ADMIN_ROLES = {"admin", "owner"}
    REVIEW_STATUSES = {"draft", "ready_for_review", "requested", "in_review", "reviewed", "approved", "changes_requested", "rejected", "closed", "archived"}
    ACTIVITY_STATES = {"viewing", "editing", "reviewing", "running", "idle"}

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or default_store_path()).resolve()
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
                CREATE TABLE IF NOT EXISTS live_workspaces(
                    workspace_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK(status IN ('active','archived')),
                    access_code_hash TEXT NOT NULL,
                    default_join_role TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    settings_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS live_workspace_members(
                    workspace_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
                    joined_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY(workspace_id,user_id),
                    FOREIGN KEY(workspace_id) REFERENCES live_workspaces(workspace_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS live_presence_sessions(
                    session_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    page_key TEXT NOT NULL DEFAULT '',
                    page_title TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    project_id TEXT NOT NULL DEFAULT '',
                    record_type TEXT NOT NULL DEFAULT '',
                    record_id TEXT NOT NULL DEFAULT '',
                    activity_state TEXT NOT NULL DEFAULT 'viewing',
                    status_message TEXT NOT NULL DEFAULT '',
                    client_label TEXT NOT NULL DEFAULT '',
                    started_at_utc TEXT NOT NULL,
                    last_seen_at_utc TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(workspace_id,user_id) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS live_record_locks(
                    workspace_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL,
                    owner_display_name TEXT NOT NULL,
                    owner_session_id TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'edit',
                    note TEXT NOT NULL DEFAULT '',
                    revision INTEGER NOT NULL DEFAULT 1,
                    acquired_at_utc TEXT NOT NULL,
                    heartbeat_at_utc TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL,
                    PRIMARY KEY(workspace_id,resource_type,resource_id),
                    FOREIGN KEY(workspace_id,owner_user_id) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS live_comments(
                    comment_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    author_user_id TEXT NOT NULL,
                    author_display_name TEXT NOT NULL,
                    body TEXT NOT NULL,
                    mentions_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    FOREIGN KEY(workspace_id,author_user_id) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS live_review_requests(
                    review_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    assigned_to TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'normal',
                    decision_note TEXT NOT NULL DEFAULT '',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    completed_at_utc TEXT,
                    FOREIGN KEY(workspace_id,requested_by) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS live_record_versions(
                    workspace_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL,
                    updated_by_display_name TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    PRIMARY KEY(workspace_id,resource_type,resource_id,revision),
                    FOREIGN KEY(workspace_id,updated_by) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS live_shared_jobs(
                    workspace_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL,
                    owner_display_name TEXT NOT NULL,
                    workflow TEXT NOT NULL,
                    page_key TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0 CHECK(progress >= 0 AND progress <= 1),
                    current_stage TEXT NOT NULL DEFAULT '',
                    safe_detail TEXT NOT NULL DEFAULT '',
                    result_reference TEXT NOT NULL DEFAULT '',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY(workspace_id,job_id),
                    FOREIGN KEY(workspace_id,owner_user_id) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS live_activity_events(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id TEXT NOT NULL,
                    actor_user_id TEXT NOT NULL,
                    actor_display_name TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    object_type TEXT NOT NULL DEFAULT '',
                    object_id TEXT NOT NULL DEFAULT '',
                    summary TEXT NOT NULL,
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    FOREIGN KEY(workspace_id) REFERENCES live_workspaces(workspace_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS live_notifications(
                    notification_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    level TEXT NOT NULL DEFAULT 'info',
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    object_type TEXT NOT NULL DEFAULT '',
                    object_id TEXT NOT NULL DEFAULT '',
                    created_at_utc TEXT NOT NULL,
                    read_at_utc TEXT,
                    FOREIGN KEY(workspace_id,user_id) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_live_workspace_tenant ON live_workspaces(tenant_id,status,updated_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_live_presence_workspace ON live_presence_sessions(workspace_id,expires_at_utc,last_seen_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_live_presence_record ON live_presence_sessions(workspace_id,record_type,record_id,expires_at_utc);
                CREATE INDEX IF NOT EXISTS idx_live_activity_workspace ON live_activity_events(workspace_id,event_id DESC);
                CREATE INDEX IF NOT EXISTS idx_live_versions_record ON live_record_versions(workspace_id,resource_type,resource_id,revision DESC);
                CREATE INDEX IF NOT EXISTS idx_live_jobs_workspace ON live_shared_jobs(workspace_id,status,updated_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_live_comments_record ON live_comments(workspace_id,resource_type,resource_id,created_at_utc);
                CREATE INDEX IF NOT EXISTS idx_live_reviews_status ON live_review_requests(workspace_id,status,updated_at_utc DESC);
                CREATE INDEX IF NOT EXISTS idx_live_notifications_user ON live_notifications(workspace_id,user_id,read_at_utc,created_at_utc DESC);
                """
            )

    @staticmethod
    def generate_join_code() -> str:
        return "-".join((secrets.token_hex(2).upper(), secrets.token_hex(2).upper(), secrets.token_hex(2).upper()))

    @staticmethod
    def _workspace(row: sqlite3.Row) -> Workspace:
        return Workspace(
            workspace_id=str(row["workspace_id"]), tenant_id=str(row["tenant_id"]),
            name=str(row["name"]), description=str(row["description"]), status=str(row["status"]),
            default_join_role=str(row["default_join_role"]), created_by=str(row["created_by"]),
            created_at_utc=str(row["created_at_utc"]), updated_at_utc=str(row["updated_at_utc"]),
        )

    def _member(self, connection: sqlite3.Connection, workspace_id: str, user_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM live_workspace_members WHERE workspace_id=? AND user_id=? AND enabled=1",
            (workspace_id, user_id),
        ).fetchone()
        if row is None:
            raise PermissionDenied("You are not an active member of this workspace.")
        return row

    def _require(self, connection: sqlite3.Connection, workspace_id: str, user_id: str, roles: set[str]) -> sqlite3.Row:
        row = self._member(connection, workspace_id, user_id)
        if str(row["role"]) not in roles:
            raise PermissionDenied("Your workspace role does not allow this action.")
        return row

    def _activity(
        self, connection: sqlite3.Connection, workspace_id: str, user_id: str, display_name: str,
        event_type: str, summary: str, *, object_type: str = "", object_id: str = "", detail: dict[str, Any] | None = None,
    ) -> None:
        connection.execute(
            """INSERT INTO live_activity_events(
                workspace_id,actor_user_id,actor_display_name,event_type,object_type,object_id,summary,detail_json,created_at_utc
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                workspace_id, user_id, _clean_text(display_name, maximum=80, field="display_name", allow_empty=False),
                _safe_id(event_type, field="event_type"), _safe_id(object_type, field="object_type", allow_empty=True),
                _safe_id(object_id, field="object_id", allow_empty=True),
                _clean_text(summary, maximum=240, field="summary", allow_empty=False), _json(detail or {}), utc_text(),
            ),
        )

    def create_workspace(
        self, *, tenant_id: str, owner_user_id: str, owner_display_name: str, name: str,
        description: str = "", default_join_role: str = "researcher", access_code: str | None = None,
    ) -> tuple[Workspace, str]:
        tenant_id = _safe_id(tenant_id, field="tenant_id")
        owner_user_id = _safe_id(owner_user_id, field="owner_user_id")
        owner_display_name = _clean_text(owner_display_name, maximum=80, field="owner_display_name", allow_empty=False)
        name = _clean_text(name, maximum=120, field="name", allow_empty=False)
        description = _clean_text(description, maximum=500, field="description")
        role = str(default_join_role).strip().lower()
        if role not in self.MEMBER_ROLES - {"owner", "admin"}:
            raise ValueError("default_join_role must be viewer, reviewer or researcher.")
        code = _clean_text(access_code or self.generate_join_code(), maximum=80, field="access_code", allow_empty=False)
        workspace_id = f"ws-{uuid4().hex[:16]}"
        now = utc_text()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO live_workspaces(
                    workspace_id,tenant_id,name,description,status,access_code_hash,default_join_role,
                    created_by,created_at_utc,updated_at_utc,settings_json
                ) VALUES(?,?,?,?,'active',?,?,?,?,?,?)""",
                (workspace_id, tenant_id, name, description, _hash_secret(code), role, owner_user_id, now, now, "{}"),
            )
            connection.execute(
                """INSERT INTO live_workspace_members(
                    workspace_id,user_id,display_name,role,enabled,joined_at_utc,updated_at_utc
                ) VALUES(?,?,?,'owner',1,?,?)""",
                (workspace_id, owner_user_id, owner_display_name, now, now),
            )
            self._activity(connection, workspace_id, owner_user_id, owner_display_name, "workspace_created", f"Created workspace {name}")
            connection.commit()
        return self.get_workspace(workspace_id), code

    def get_workspace(self, workspace_id: str) -> Workspace:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM live_workspaces WHERE workspace_id=?", (workspace_id,)).fetchone()
        if row is None:
            raise KeyError(workspace_id)
        return self._workspace(row)

    def list_workspaces(self, *, tenant_id: str, user_id: str | None = None) -> list[dict[str, Any]]:
        tenant_id = _safe_id(tenant_id, field="tenant_id")
        with self._connect() as connection:
            if user_id:
                rows = connection.execute(
                    """SELECT w.*,m.role,m.display_name FROM live_workspaces w
                    JOIN live_workspace_members m ON m.workspace_id=w.workspace_id
                    WHERE w.tenant_id=? AND w.status='active' AND m.user_id=? AND m.enabled=1
                    ORDER BY w.updated_at_utc DESC""",
                    (tenant_id, _safe_id(user_id, field="user_id")),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT *,'' AS role,'' AS display_name FROM live_workspaces WHERE tenant_id=? AND status='active' ORDER BY updated_at_utc DESC",
                    (tenant_id,),
                ).fetchall()
        return [{**self._workspace(row).to_dict(), "role": str(row["role"]), "member_display_name": str(row["display_name"])} for row in rows]

    def verify_access_code(self, workspace_id: str, access_code: str) -> bool:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT access_code_hash,status FROM live_workspaces WHERE workspace_id=?", (workspace_id,)
            ).fetchone()
        return bool(row and row["status"] == "active" and _verify_secret(str(access_code), str(row["access_code_hash"])))

    def join_workspace(
        self, *, workspace_id: str, access_code: str, user_id: str, display_name: str, requested_role: str | None = None,
    ) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        user_id = _safe_id(user_id, field="user_id")
        display_name = _clean_text(display_name, maximum=80, field="display_name", allow_empty=False)
        now = utc_text()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            workspace = connection.execute("SELECT * FROM live_workspaces WHERE workspace_id=?", (workspace_id,)).fetchone()
            if workspace is None or workspace["status"] != "active":
                raise KeyError(workspace_id)
            if not _verify_secret(_clean_text(access_code, maximum=80, field="access_code", allow_empty=False), str(workspace["access_code_hash"])):
                raise PermissionDenied("Workspace join code is incorrect.")
            role = str(workspace["default_join_role"])
            requested = str(requested_role or "").strip().lower()
            if requested in {"viewer", "reviewer"}:
                role = requested
            existing = connection.execute(
                "SELECT role FROM live_workspace_members WHERE workspace_id=? AND user_id=?", (workspace_id, user_id)
            ).fetchone()
            if existing is not None:
                role = str(existing["role"])
            connection.execute(
                """INSERT INTO live_workspace_members(
                    workspace_id,user_id,display_name,role,enabled,joined_at_utc,updated_at_utc
                ) VALUES(?,?,?,?,1,?,?)
                ON CONFLICT(workspace_id,user_id) DO UPDATE SET
                    display_name=excluded.display_name,enabled=1,updated_at_utc=excluded.updated_at_utc""",
                (workspace_id, user_id, display_name, role, now, now),
            )
            self._activity(connection, workspace_id, user_id, display_name, "member_joined", f"{display_name} joined the workspace")
            connection.commit()
        return self.get_member(workspace_id, user_id)

    def get_member(self, workspace_id: str, user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = self._member(connection, _safe_id(workspace_id, field="workspace_id"), _safe_id(user_id, field="user_id"))
        return dict(row)

    def list_members(self, workspace_id: str, *, actor_user_id: str) -> list[dict[str, Any]]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        with self._connect() as connection:
            self._member(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"))
            rows = connection.execute(
                """SELECT m.*,MAX(p.last_seen_at_utc) AS last_seen_at_utc,
                MAX(CASE WHEN p.expires_at_utc>? THEN 1 ELSE 0 END) AS online
                FROM live_workspace_members m LEFT JOIN live_presence_sessions p
                ON p.workspace_id=m.workspace_id AND p.user_id=m.user_id
                WHERE m.workspace_id=? AND m.enabled=1 GROUP BY m.workspace_id,m.user_id ORDER BY m.display_name""",
                (utc_text(), workspace_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_member_role(self, workspace_id: str, *, actor_user_id: str, target_user_id: str, role: str) -> None:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        role = str(role).strip().lower()
        if role not in self.MEMBER_ROLES:
            raise ValueError("Unsupported workspace role.")
        with self._connect() as connection:
            actor = self._require(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"), self.ADMIN_ROLES)
            target = self._member(connection, workspace_id, _safe_id(target_user_id, field="target_user_id"))
            if target["role"] == "owner" and role != "owner":
                owners = connection.execute(
                    "SELECT COUNT(*) FROM live_workspace_members WHERE workspace_id=? AND role='owner' AND enabled=1",
                    (workspace_id,),
                ).fetchone()[0]
                if int(owners) <= 1:
                    raise PermissionDenied("The workspace must retain at least one owner.")
            connection.execute(
                "UPDATE live_workspace_members SET role=?,updated_at_utc=? WHERE workspace_id=? AND user_id=?",
                (role, utc_text(), workspace_id, target_user_id),
            )
            self._activity(
                connection, workspace_id, str(actor["user_id"]), str(actor["display_name"]), "member_role_changed",
                f"Changed {target['display_name']} role to {role}", object_type="member", object_id=str(target_user_id),
            )

    def heartbeat(
        self, *, workspace_id: str, session_id: str, user_id: str, display_name: str,
        page_key: str = "", page_title: str = "", category: str = "", project_id: str = "",
        record_type: str = "", record_id: str = "", activity_state: str = "viewing",
        status_message: str = "", client_label: str = "", ttl_seconds: int = 45,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        session_id = _safe_id(session_id, field="session_id")
        user_id = _safe_id(user_id, field="user_id")
        display_name = _clean_text(display_name, maximum=80, field="display_name", allow_empty=False)
        page_key = _safe_id(page_key, field="page_key", allow_empty=True)
        page_title = _clean_text(page_title, maximum=140, field="page_title")
        category = _clean_text(category, maximum=80, field="category")
        project_id = _safe_id(project_id, field="project_id", allow_empty=True)
        record_type = _safe_id(record_type, field="record_type", allow_empty=True)
        record_id = _safe_id(record_id, field="record_id", allow_empty=True)
        state = str(activity_state).strip().lower()
        if state not in self.ACTIVITY_STATES:
            raise ValueError("Unsupported activity_state.")
        ttl = min(max(int(ttl_seconds), 20), 300)
        now_dt = utc_now()
        now = utc_text(now_dt)
        expires = utc_text(now_dt + timedelta(seconds=ttl))
        with self._connect() as connection:
            member = self._member(connection, workspace_id, user_id)
            previous = connection.execute(
                "SELECT page_key,record_type,record_id,activity_state FROM live_presence_sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
            connection.execute(
                """INSERT INTO live_presence_sessions(
                    session_id,workspace_id,user_id,display_name,role,page_key,page_title,category,project_id,
                    record_type,record_id,activity_state,status_message,client_label,started_at_utc,last_seen_at_utc,expires_at_utc,metadata_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET
                    workspace_id=excluded.workspace_id,user_id=excluded.user_id,display_name=excluded.display_name,
                    role=excluded.role,page_key=excluded.page_key,page_title=excluded.page_title,category=excluded.category,
                    project_id=excluded.project_id,record_type=excluded.record_type,record_id=excluded.record_id,
                    activity_state=excluded.activity_state,status_message=excluded.status_message,client_label=excluded.client_label,
                    last_seen_at_utc=excluded.last_seen_at_utc,expires_at_utc=excluded.expires_at_utc,metadata_json=excluded.metadata_json""",
                (
                    session_id, workspace_id, user_id, display_name, str(member["role"]), page_key, page_title, category,
                    project_id, record_type, record_id, state,
                    _clean_text(status_message, maximum=140, field="status_message"),
                    _clean_text(client_label, maximum=80, field="client_label"), now, now, expires, _json(metadata or {}),
                ),
            )
            if previous is None:
                self._activity(connection, workspace_id, user_id, display_name, "presence_joined", f"{display_name} came online")
            elif (str(previous["page_key"]), str(previous["record_type"]), str(previous["record_id"]), str(previous["activity_state"])) != (page_key, record_type, record_id, state):
                summary = f"{display_name} is {state} {page_title or page_key or 'the workspace'}"
                self._activity(connection, workspace_id, user_id, display_name, "presence_context_changed", summary, object_type=record_type, object_id=record_id)
            connection.execute("DELETE FROM live_presence_sessions WHERE expires_at_utc<=?", (now,))
            connection.execute("DELETE FROM live_record_locks WHERE expires_at_utc<=?", (now,))
        return {
            "session_id": session_id, "workspace_id": workspace_id, "user_id": user_id,
            "display_name": display_name, "role": str(member["role"]), "last_seen_at_utc": now, "expires_at_utc": expires,
        }

    def disconnect(self, workspace_id: str, session_id: str, *, user_id: str) -> None:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        session_id = _safe_id(session_id, field="session_id")
        user_id = _safe_id(user_id, field="user_id")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM live_presence_sessions WHERE workspace_id=? AND session_id=? AND user_id=?",
                (workspace_id, session_id, user_id),
            ).fetchone()
            if row is None:
                return
            connection.execute("DELETE FROM live_presence_sessions WHERE session_id=?", (session_id,))
            connection.execute("DELETE FROM live_record_locks WHERE workspace_id=? AND owner_session_id=?", (workspace_id, session_id))
            self._activity(connection, workspace_id, user_id, str(row["display_name"]), "presence_left", f"{row['display_name']} went offline")

    def list_presence(self, workspace_id: str, *, actor_user_id: str, page_key: str = "", record_type: str = "", record_id: str = "") -> list[dict[str, Any]]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        now = utc_text()
        clauses = ["workspace_id=?", "expires_at_utc>?"]
        params: list[Any] = [workspace_id, now]
        if page_key:
            clauses.append("page_key=?")
            params.append(_safe_id(page_key, field="page_key"))
        if record_type or record_id:
            clauses.extend(("record_type=?", "record_id=?"))
            params.extend((_safe_id(record_type, field="record_type"), _safe_id(record_id, field="record_id")))
        with self._connect() as connection:
            self._member(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"))
            connection.execute("DELETE FROM live_presence_sessions WHERE expires_at_utc<=?", (now,))
            rows = connection.execute(
                f"SELECT * FROM live_presence_sessions WHERE {' AND '.join(clauses)} ORDER BY last_seen_at_utc DESC",
                tuple(params),
            ).fetchall()
        return [{**dict(row), "metadata": _decode(row["metadata_json"], {})} for row in rows]

    def acquire_lock(
        self, *, workspace_id: str, user_id: str, session_id: str, resource_type: str, resource_id: str,
        note: str = "", ttl_seconds: int = 120, force: bool = False,
    ) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        user_id = _safe_id(user_id, field="user_id")
        session_id = _safe_id(session_id, field="session_id")
        resource_type = _safe_id(resource_type, field="resource_type")
        resource_id = _safe_id(resource_id, field="resource_id")
        ttl = min(max(int(ttl_seconds), 30), 900)
        now_dt = utc_now(); now = utc_text(now_dt); expires = utc_text(now_dt + timedelta(seconds=ttl))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            member = self._require(connection, workspace_id, user_id, self.EDIT_ROLES)
            existing = connection.execute(
                "SELECT * FROM live_record_locks WHERE workspace_id=? AND resource_type=? AND resource_id=?",
                (workspace_id, resource_type, resource_id),
            ).fetchone()
            if existing is not None and str(existing["expires_at_utc"]) <= now:
                connection.execute(
                    "DELETE FROM live_record_locks WHERE workspace_id=? AND resource_type=? AND resource_id=?",
                    (workspace_id, resource_type, resource_id),
                )
                existing = None
            if existing is not None and str(existing["owner_user_id"]) != user_id:
                if not force or str(member["role"]) not in self.ADMIN_ROLES:
                    raise RecordLocked(f"Record is currently locked by {existing['owner_display_name']}.", lock=dict(existing))
            revision = int(existing["revision"]) + 1 if existing is not None else 1
            connection.execute(
                """INSERT INTO live_record_locks(
                    workspace_id,resource_type,resource_id,owner_user_id,owner_display_name,owner_session_id,
                    mode,note,revision,acquired_at_utc,heartbeat_at_utc,expires_at_utc
                ) VALUES(?,?,?,?,?,?,'edit',?,?,?,?,?)
                ON CONFLICT(workspace_id,resource_type,resource_id) DO UPDATE SET
                    owner_user_id=excluded.owner_user_id,owner_display_name=excluded.owner_display_name,
                    owner_session_id=excluded.owner_session_id,note=excluded.note,revision=excluded.revision,
                    acquired_at_utc=excluded.acquired_at_utc,heartbeat_at_utc=excluded.heartbeat_at_utc,
                    expires_at_utc=excluded.expires_at_utc""",
                (
                    workspace_id, resource_type, resource_id, user_id, str(member["display_name"]), session_id,
                    _clean_text(note, maximum=240, field="note"), revision, now, now, expires,
                ),
            )
            self._activity(
                connection, workspace_id, user_id, str(member["display_name"]), "record_lock_acquired",
                f"Locked {resource_type} {resource_id} for editing", object_type=resource_type, object_id=resource_id,
                detail={"revision": revision, "forced": bool(force)},
            )
            connection.commit()
        return self.get_lock(workspace_id, resource_type, resource_id, actor_user_id=user_id) or {}

    def get_lock(self, workspace_id: str, resource_type: str, resource_id: str, *, actor_user_id: str) -> dict[str, Any] | None:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        with self._connect() as connection:
            self._member(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"))
            connection.execute("DELETE FROM live_record_locks WHERE expires_at_utc<=?", (utc_text(),))
            row = connection.execute(
                "SELECT * FROM live_record_locks WHERE workspace_id=? AND resource_type=? AND resource_id=?",
                (workspace_id, _safe_id(resource_type, field="resource_type"), _safe_id(resource_id, field="resource_id")),
            ).fetchone()
        return dict(row) if row else None

    def renew_lock(self, *, workspace_id: str, user_id: str, session_id: str, resource_type: str, resource_id: str, ttl_seconds: int = 120) -> dict[str, Any]:
        ttl = min(max(int(ttl_seconds), 30), 900); now_dt = utc_now(); now = utc_text(now_dt); expires = utc_text(now_dt + timedelta(seconds=ttl))
        with self._connect() as connection:
            self._require(connection, _safe_id(workspace_id, field="workspace_id"), _safe_id(user_id, field="user_id"), self.EDIT_ROLES)
            cursor = connection.execute(
                """UPDATE live_record_locks SET heartbeat_at_utc=?,expires_at_utc=?
                WHERE workspace_id=? AND resource_type=? AND resource_id=? AND owner_user_id=? AND owner_session_id=?""",
                (now, expires, workspace_id, _safe_id(resource_type, field="resource_type"), _safe_id(resource_id, field="resource_id"), user_id, _safe_id(session_id, field="session_id")),
            )
            if cursor.rowcount != 1:
                raise RecordLocked("The edit lock is no longer owned by this session.")
        return self.get_lock(workspace_id, resource_type, resource_id, actor_user_id=user_id) or {}

    def release_lock(self, *, workspace_id: str, user_id: str, resource_type: str, resource_id: str, force: bool = False) -> bool:
        workspace_id = _safe_id(workspace_id, field="workspace_id"); user_id = _safe_id(user_id, field="user_id")
        with self._connect() as connection:
            member = self._member(connection, workspace_id, user_id)
            lock = connection.execute(
                "SELECT * FROM live_record_locks WHERE workspace_id=? AND resource_type=? AND resource_id=?",
                (workspace_id, _safe_id(resource_type, field="resource_type"), _safe_id(resource_id, field="resource_id")),
            ).fetchone()
            if lock is None:
                return False
            if str(lock["owner_user_id"]) != user_id and (not force or str(member["role"]) not in self.ADMIN_ROLES):
                raise PermissionDenied("Only the lock owner or a workspace admin can release this lock.")
            connection.execute(
                "DELETE FROM live_record_locks WHERE workspace_id=? AND resource_type=? AND resource_id=?",
                (workspace_id, resource_type, resource_id),
            )
            self._activity(connection, workspace_id, user_id, str(member["display_name"]), "record_lock_released", f"Released lock on {resource_type} {resource_id}", object_type=resource_type, object_id=resource_id)
        return True

    def commit_record_revision(
        self, *, workspace_id: str, user_id: str, session_id: str, resource_type: str, resource_id: str,
        expected_revision: int, payload_sha256: str, summary: str = "",
    ) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        user_id = _safe_id(user_id, field="user_id")
        session_id = _safe_id(session_id, field="session_id")
        resource_type = _safe_id(resource_type, field="resource_type")
        resource_id = _safe_id(resource_id, field="resource_id")
        digest = str(payload_sha256).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("payload_sha256 must be a 64-character SHA-256 digest.")
        expected = max(int(expected_revision), 0)
        now = utc_text()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            member = self._require(connection, workspace_id, user_id, self.EDIT_ROLES)
            lock = connection.execute(
                """SELECT * FROM live_record_locks WHERE workspace_id=? AND resource_type=? AND resource_id=?
                AND owner_user_id=? AND owner_session_id=? AND expires_at_utc>?""",
                (workspace_id, resource_type, resource_id, user_id, session_id, now),
            ).fetchone()
            if lock is None:
                raise RecordLocked("An active edit lock owned by this browser session is required.")
            row = connection.execute(
                """SELECT COALESCE(MAX(revision),0) AS revision FROM live_record_versions
                WHERE workspace_id=? AND resource_type=? AND resource_id=?""",
                (workspace_id, resource_type, resource_id),
            ).fetchone()
            current = int(row["revision"] if row else 0)
            if current != expected:
                raise RevisionConflict(
                    f"Record changed from revision {expected} to {current}; refresh before saving.",
                    current_revision=current,
                )
            revision = current + 1
            connection.execute(
                """INSERT INTO live_record_versions(
                    workspace_id,resource_type,resource_id,revision,payload_sha256,summary,updated_by,
                    updated_by_display_name,created_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (workspace_id, resource_type, resource_id, revision, digest,
                 _clean_text(summary, maximum=500, field="summary"), user_id, str(member["display_name"]), now),
            )
            self._activity(
                connection, workspace_id, user_id, str(member["display_name"]), "record_revision_committed",
                f"Committed {resource_type} {resource_id} revision {revision}",
                object_type=resource_type, object_id=resource_id,
                detail={"revision": revision, "payload_sha256": digest},
            )
            connection.commit()
        return {
            "workspace_id": workspace_id, "resource_type": resource_type, "resource_id": resource_id,
            "revision": revision, "payload_sha256": digest, "summary": summary,
            "updated_by": user_id, "updated_by_display_name": str(member["display_name"]),
            "created_at_utc": now,
        }

    def list_record_versions(
        self, workspace_id: str, *, actor_user_id: str, resource_type: str, resource_id: str, limit: int = 100,
    ) -> list[dict[str, Any]]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        with self._connect() as connection:
            self._member(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"))
            rows = connection.execute(
                """SELECT * FROM live_record_versions WHERE workspace_id=? AND resource_type=? AND resource_id=?
                ORDER BY revision DESC LIMIT ?""",
                (workspace_id, _safe_id(resource_type, field="resource_type"),
                 _safe_id(resource_id, field="resource_id"), min(max(int(limit), 1), 500)),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_shared_job(
        self, *, workspace_id: str, user_id: str, job_id: str, workflow: str, status: str,
        progress: float = 0.0, page_key: str = "", current_stage: str = "", safe_detail: str = "",
        result_reference: str = "",
    ) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        user_id = _safe_id(user_id, field="user_id")
        job_id = _safe_id(job_id, field="job_id")
        status = _safe_id(str(status).lower(), field="status")
        normalized_progress = min(max(float(progress), 0.0), 1.0)
        now = utc_text()
        with self._connect() as connection:
            member = self._require(connection, workspace_id, user_id, self.WRITE_ROLES)
            existing = connection.execute(
                "SELECT created_at_utc,status FROM live_shared_jobs WHERE workspace_id=? AND job_id=?",
                (workspace_id, job_id),
            ).fetchone()
            created_at = str(existing["created_at_utc"]) if existing else now
            connection.execute(
                """INSERT INTO live_shared_jobs(
                    workspace_id,job_id,owner_user_id,owner_display_name,workflow,page_key,status,progress,
                    current_stage,safe_detail,result_reference,created_at_utc,updated_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(workspace_id,job_id) DO UPDATE SET
                    workflow=excluded.workflow,page_key=excluded.page_key,status=excluded.status,progress=excluded.progress,
                    current_stage=excluded.current_stage,safe_detail=excluded.safe_detail,
                    result_reference=excluded.result_reference,updated_at_utc=excluded.updated_at_utc""",
                (workspace_id, job_id, user_id, str(member["display_name"]),
                 _clean_text(workflow, maximum=180, field="workflow", allow_empty=False),
                 _safe_id(page_key, field="page_key", allow_empty=True), status, normalized_progress,
                 _clean_text(current_stage, maximum=160, field="current_stage"),
                 _clean_text(safe_detail, maximum=500, field="safe_detail"),
                 _safe_id(result_reference, field="result_reference", allow_empty=True), created_at, now),
            )
            if existing is None or str(existing["status"]) != status:
                self._activity(
                    connection, workspace_id, user_id, str(member["display_name"]), "shared_job_updated",
                    f"{workflow} is {status}", object_type="job", object_id=job_id,
                    detail={"progress": normalized_progress, "current_stage": current_stage},
                )
        return {
            "workspace_id": workspace_id, "job_id": job_id, "owner_user_id": user_id,
            "owner_display_name": str(member["display_name"]), "workflow": workflow, "page_key": page_key,
            "status": status, "progress": normalized_progress, "current_stage": current_stage,
            "safe_detail": safe_detail, "result_reference": result_reference,
            "created_at_utc": created_at, "updated_at_utc": now,
        }

    def list_shared_jobs(
        self, workspace_id: str, *, actor_user_id: str, status: str = "", limit: int = 100,
    ) -> list[dict[str, Any]]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        clauses = ["workspace_id=?"]; params: list[Any] = [workspace_id]
        if status:
            clauses.append("status=?"); params.append(_safe_id(str(status).lower(), field="status"))
        params.append(min(max(int(limit), 1), 500))
        with self._connect() as connection:
            self._member(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"))
            rows = connection.execute(
                f"SELECT * FROM live_shared_jobs WHERE {' AND '.join(clauses)} ORDER BY updated_at_utc DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def rotate_access_code(
        self, workspace_id: str, *, actor_user_id: str, new_code: str | None = None,
    ) -> str:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        code = _clean_text(new_code or self.generate_join_code(), maximum=80, field="access_code", allow_empty=False)
        with self._connect() as connection:
            actor = self._require(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"), self.ADMIN_ROLES)
            connection.execute(
                "UPDATE live_workspaces SET access_code_hash=?,updated_at_utc=? WHERE workspace_id=?",
                (_hash_secret(code), utc_text(), workspace_id),
            )
            self._activity(
                connection, workspace_id, str(actor["user_id"]), str(actor["display_name"]),
                "join_code_rotated", "Rotated the workspace join code",
            )
        return code

    def add_comment(self, *, workspace_id: str, user_id: str, resource_type: str, resource_id: str, body: str) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id"); user_id = _safe_id(user_id, field="user_id")
        resource_type = _safe_id(resource_type, field="resource_type"); resource_id = _safe_id(resource_id, field="resource_id")
        body = _clean_text(body, maximum=4000, field="comment", allow_empty=False)
        mentions = sorted(set(_MENTION.findall(body)))[:30]
        comment_id = f"comment-{uuid4().hex}"; now = utc_text()
        with self._connect() as connection:
            member = self._require(connection, workspace_id, user_id, self.WRITE_ROLES)
            connection.execute(
                """INSERT INTO live_comments(comment_id,workspace_id,resource_type,resource_id,author_user_id,
                author_display_name,body,mentions_json,status,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?,?,?, 'open',?,?)""",
                (comment_id, workspace_id, resource_type, resource_id, user_id, str(member["display_name"]), body, _json(mentions), now, now),
            )
            self._activity(connection, workspace_id, user_id, str(member["display_name"]), "comment_added", f"Commented on {resource_type} {resource_id}", object_type=resource_type, object_id=resource_id, detail={"comment_id": comment_id, "mentions": mentions})
            if mentions:
                targets = connection.execute(
                    "SELECT user_id,display_name FROM live_workspace_members WHERE workspace_id=? AND enabled=1",
                    (workspace_id,),
                ).fetchall()
                for target in targets:
                    normalized = re.sub(r"[^a-z0-9._-]+", "", str(target["display_name"]).lower())
                    if any(item.lower() in {str(target["user_id"]).lower(), normalized} for item in mentions):
                        connection.execute(
                            """INSERT INTO live_notifications(notification_id,workspace_id,user_id,level,title,body,object_type,object_id,created_at_utc)
                            VALUES(?,?,?,?,?,?,?,?,?)""",
                            (f"notification-{uuid4().hex}", workspace_id, str(target["user_id"]), "info", "You were mentioned", f"{member['display_name']} mentioned you in a comment.", resource_type, resource_id, now),
                        )
        return self.get_comment(comment_id, actor_user_id=user_id)

    def get_comment(self, comment_id: str, *, actor_user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM live_comments WHERE comment_id=?", (_safe_id(comment_id, field="comment_id"),)).fetchone()
            if row is None:
                raise KeyError(comment_id)
            self._member(connection, str(row["workspace_id"]), _safe_id(actor_user_id, field="actor_user_id"))
        return {**dict(row), "mentions": _decode(row["mentions_json"], [])}

    def list_comments(self, workspace_id: str, *, actor_user_id: str, resource_type: str, resource_id: str, limit: int = 200) -> list[dict[str, Any]]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        with self._connect() as connection:
            self._member(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"))
            rows = connection.execute(
                """SELECT * FROM live_comments WHERE workspace_id=? AND resource_type=? AND resource_id=?
                ORDER BY created_at_utc DESC LIMIT ?""",
                (workspace_id, _safe_id(resource_type, field="resource_type"), _safe_id(resource_id, field="resource_id"), min(max(int(limit), 1), 500)),
            ).fetchall()
        return [{**dict(row), "mentions": _decode(row["mentions_json"], [])} for row in rows]

    def request_review(
        self, *, workspace_id: str, user_id: str, resource_type: str, resource_id: str,
        title: str, assigned_to: str = "", priority: str = "normal",
    ) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id"); user_id = _safe_id(user_id, field="user_id")
        review_id = f"review-{uuid4().hex}"; now = utc_text(); priority = str(priority).strip().lower()
        if priority not in {"low", "normal", "high", "urgent"}:
            raise ValueError("Unsupported review priority.")
        with self._connect() as connection:
            member = self._require(connection, workspace_id, user_id, self.WRITE_ROLES)
            assigned = _safe_id(assigned_to, field="assigned_to", allow_empty=True)
            if assigned:
                self._member(connection, workspace_id, assigned)
            connection.execute(
                """INSERT INTO live_review_requests(review_id,workspace_id,resource_type,resource_id,title,requested_by,
                assigned_to,status,priority,decision_note,created_at_utc,updated_at_utc,completed_at_utc)
                VALUES(?,?,?,?,?,?,?,'requested',?,'',?,?,NULL)""",
                (review_id, workspace_id, _safe_id(resource_type, field="resource_type"), _safe_id(resource_id, field="resource_id"), _clean_text(title, maximum=200, field="title", allow_empty=False), user_id, assigned, priority, now, now),
            )
            self._activity(connection, workspace_id, user_id, str(member["display_name"]), "review_requested", f"Requested review: {title}", object_type=resource_type, object_id=resource_id, detail={"review_id": review_id, "assigned_to": assigned})
            if assigned:
                connection.execute(
                    """INSERT INTO live_notifications(notification_id,workspace_id,user_id,level,title,body,object_type,object_id,created_at_utc)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (f"notification-{uuid4().hex}", workspace_id, assigned, "info", "Review assigned", str(title), resource_type, resource_id, now),
                )
        return self.get_review(review_id, actor_user_id=user_id)

    def get_review(self, review_id: str, *, actor_user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM live_review_requests WHERE review_id=?", (_safe_id(review_id, field="review_id"),)).fetchone()
            if row is None:
                raise KeyError(review_id)
            self._member(connection, str(row["workspace_id"]), _safe_id(actor_user_id, field="actor_user_id"))
        return dict(row)

    def update_review(self, *, review_id: str, user_id: str, status: str, decision_note: str = "") -> dict[str, Any]:
        status = str(status).strip().lower()
        if status not in self.REVIEW_STATUSES:
            raise ValueError("Unsupported review status.")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM live_review_requests WHERE review_id=?", (_safe_id(review_id, field="review_id"),)).fetchone()
            if row is None:
                raise KeyError(review_id)
            workspace_id = str(row["workspace_id"])
            member = self._require(connection, workspace_id, _safe_id(user_id, field="user_id"), self.WRITE_ROLES)
            if str(row["assigned_to"]) and str(row["assigned_to"]) != user_id and str(member["role"]) not in self.ADMIN_ROLES:
                raise PermissionDenied("This review is assigned to another member.")
            completed = utc_text() if status in {"reviewed", "approved", "changes_requested", "rejected", "closed", "archived"} else None
            connection.execute(
                "UPDATE live_review_requests SET status=?,decision_note=?,updated_at_utc=?,completed_at_utc=? WHERE review_id=?",
                (status, _clean_text(decision_note, maximum=2000, field="decision_note"), utc_text(), completed, review_id),
            )
            self._activity(connection, workspace_id, user_id, str(member["display_name"]), "review_updated", f"Review status changed to {status}", object_type=str(row["resource_type"]), object_id=str(row["resource_id"]), detail={"review_id": review_id})
            connection.commit()
        return self.get_review(review_id, actor_user_id=user_id)

    def list_reviews(self, workspace_id: str, *, actor_user_id: str, status: str = "", limit: int = 200) -> list[dict[str, Any]]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        clauses = ["workspace_id=?"]; params: list[Any] = [workspace_id]
        if status:
            normalized = str(status).strip().lower()
            if normalized not in self.REVIEW_STATUSES:
                raise ValueError("Unsupported review status.")
            clauses.append("status=?"); params.append(normalized)
        params.append(min(max(int(limit), 1), 500))
        with self._connect() as connection:
            self._member(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"))
            rows = connection.execute(
                f"SELECT * FROM live_review_requests WHERE {' AND '.join(clauses)} ORDER BY updated_at_utc DESC LIMIT ?", tuple(params)
            ).fetchall()
        return [dict(row) for row in rows]

    def list_activity(self, workspace_id: str, *, actor_user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        with self._connect() as connection:
            self._member(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"))
            rows = connection.execute(
                "SELECT * FROM live_activity_events WHERE workspace_id=? ORDER BY event_id DESC LIMIT ?",
                (workspace_id, min(max(int(limit), 1), 500)),
            ).fetchall()
        return [{**dict(row), "detail": _decode(row["detail_json"], {})} for row in rows]

    def list_notifications(self, workspace_id: str, *, user_id: str, unread_only: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        workspace_id = _safe_id(workspace_id, field="workspace_id"); user_id = _safe_id(user_id, field="user_id")
        clauses = ["workspace_id=?", "user_id=?"]; params: list[Any] = [workspace_id, user_id]
        if unread_only:
            clauses.append("read_at_utc IS NULL")
        params.append(min(max(int(limit), 1), 500))
        with self._connect() as connection:
            self._member(connection, workspace_id, user_id)
            rows = connection.execute(
                f"SELECT * FROM live_notifications WHERE {' AND '.join(clauses)} ORDER BY created_at_utc DESC LIMIT ?", tuple(params)
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_notification_read(self, notification_id: str, *, user_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE live_notifications SET read_at_utc=? WHERE notification_id=? AND user_id=?",
                (utc_text(), _safe_id(notification_id, field="notification_id"), _safe_id(user_id, field="user_id")),
            )
        return cursor.rowcount == 1

    def dashboard(self, workspace_id: str, *, actor_user_id: str) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id"); actor_user_id = _safe_id(actor_user_id, field="actor_user_id")
        now = utc_text()
        with self._connect() as connection:
            self._member(connection, workspace_id, actor_user_id)
            connection.execute("DELETE FROM live_presence_sessions WHERE expires_at_utc<=?", (now,))
            connection.execute("DELETE FROM live_record_locks WHERE expires_at_utc<=?", (now,))
            online = int(connection.execute("SELECT COUNT(DISTINCT user_id) FROM live_presence_sessions WHERE workspace_id=?", (workspace_id,)).fetchone()[0])
            sessions = int(connection.execute("SELECT COUNT(*) FROM live_presence_sessions WHERE workspace_id=?", (workspace_id,)).fetchone()[0])
            locks = int(connection.execute("SELECT COUNT(*) FROM live_record_locks WHERE workspace_id=?", (workspace_id,)).fetchone()[0])
            open_reviews = int(connection.execute("SELECT COUNT(*) FROM live_review_requests WHERE workspace_id=? AND status NOT IN ('approved','closed')", (workspace_id,)).fetchone()[0])
            comments = int(connection.execute("SELECT COUNT(*) FROM live_comments WHERE workspace_id=?", (workspace_id,)).fetchone()[0])
        return {"online_members": online, "active_sessions": sessions, "active_locks": locks, "open_reviews": open_reviews, "comments": comments, "generated_at_utc": now}


__all__ = [
    "LiveWorkspaceError", "PermissionDenied", "RecordLocked", "RevisionConflict", "Workspace", "LiveWorkspaceStore",
    "default_store_path", "host_config_path", "load_host_config", "save_host_config",
]
