from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from ctypes import wintypes
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from .constants import ROLES, SYNTHETIC_NOTICE
from .models import (
    PlatformConflictError,
    PlatformPermissionError,
    PlatformValidationError,
    check_permission,
    new_id,
    optional_text,
    require_text,
    utc_now,
    validate_choice,
)
from .storage import DiscoveryPlatformStore

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
_SECRET_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_PASSWORD_ITERATIONS = 600_000
_SENSITIVE_KEYS = frozenset(
    {
        "password", "password_hash", "secret", "token", "access_token", "refresh_token",
        "api_key", "authorization", "credential", "private_key",
    }
)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def sanitize_user_text(value: object, *, maximum: int = 10_000) -> str:
    text = str(value or "")
    cleaned = "".join(character for character in text if character in ("\n", "\t") or ord(character) >= 32)
    if len(cleaned) > maximum:
        raise PlatformValidationError(f"Text exceeds the {maximum}-character limit")
    return cleaned.strip()


def safe_local_path(root: str | Path, *parts: str) -> Path:
    base = Path(root).resolve()
    candidate = base.joinpath(*parts).resolve()
    if not candidate.is_relative_to(base):
        raise PlatformValidationError("Path traversal outside the configured root was blocked")
    return candidate


def redact_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in _SENSITIVE_KEYS or any(term in key.lower() for term in ("password", "secret", "token", "api_key")):
            redacted[key] = "[REDACTED]"
        elif isinstance(value, Mapping):
            redacted[key] = redact_mapping(value)
        else:
            redacted[key] = value
    return redacted


class LocalAuthenticationService:
    """PBKDF2 local accounts, lockout, RBAC, and sliding-expiry sessions."""

    def __init__(
        self,
        store: DiscoveryPlatformStore,
        *,
        actor: str = "local_user",
        role: str = "Administrator",
        session_minutes: int = 30,
        max_failed_attempts: int = 5,
        lockout_minutes: int = 15,
    ):
        self.store = store
        self.actor = actor
        self.role = validate_choice(role, ROLES, "role")
        self.session_minutes = max(5, min(int(session_minutes), 24 * 60))
        self.max_failed_attempts = max(3, min(int(max_failed_attempts), 20))
        self.lockout_minutes = max(1, min(int(lockout_minutes), 24 * 60))

    @staticmethod
    def _normalize_username(username: str) -> str:
        normalized = str(username or "").strip().lower()
        if not _USERNAME_RE.fullmatch(normalized):
            raise PlatformValidationError(
                "Username must be 3-64 characters using letters, numbers, dot, dash, or underscore"
            )
        return normalized

    @staticmethod
    def _validate_password(password: str, username: str) -> None:
        if len(password) < 12 or len(password) > 1024:
            raise PlatformValidationError("Password must be between 12 and 1024 characters")
        classes = (
            any(value.islower() for value in password),
            any(value.isupper() for value in password),
            any(value.isdigit() for value in password),
            any(not value.isalnum() for value in password),
        )
        if sum(classes) < 3:
            raise PlatformValidationError(
                "Password must use at least three of lowercase, uppercase, number, and symbol"
            )
        if username.lower() in password.lower():
            raise PlatformValidationError("Password must not contain the username")
        if password.lower() in {"password123!", "administrator1!", "biointel123!"}:
            raise PlatformValidationError("Common passwords are not permitted")

    @staticmethod
    def _password_hash(password: str, salt: bytes, iterations: int) -> str:
        value = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return base64.b64encode(value).decode("ascii")

    def create_user(
        self,
        *,
        username: str,
        password: str,
        display_name: str,
        role: str,
    ) -> dict[str, Any]:
        if self.role != "Administrator":
            raise PlatformPermissionError("Only an Administrator can create local accounts")
        normalized = self._normalize_username(username)
        selected_role = validate_choice(role, ROLES, "role")
        self._validate_password(password, normalized)
        salt = secrets.token_bytes(32)
        now = utc_now()
        user_id = new_id("USER")
        try:
            self.store.insert(
                "local_users",
                {
                    "user_id": user_id,
                    "username": normalized,
                    "display_name": require_text(display_name, "display name", 160),
                    "role": selected_role,
                    "password_hash": self._password_hash(password, salt, _PASSWORD_ITERATIONS),
                    "salt": base64.b64encode(salt).decode("ascii"),
                    "iterations": _PASSWORD_ITERATIONS,
                    "active": 1,
                    "failed_attempts": 0,
                    "created_at_utc": now,
                    "updated_at_utc": now,
                },
            )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc).upper():
                raise PlatformConflictError("A user with that username already exists") from exc
            raise
        self.store.audit(
            "local_user_created", "local_user", user_id,
            actor=self.actor, role=self.role,
            detail={"username": normalized, "assigned_role": selected_role},
        )
        return self.user_profile(user_id)

    def user_profile(self, user_id: str) -> dict[str, Any]:
        row = self.store.row("local_users", "user_id", user_id)
        if row is None:
            raise KeyError(user_id)
        return {
            key: row.get(key)
            for key in (
                "user_id", "username", "display_name", "role", "active",
                "failed_attempts", "locked_until_utc", "last_login_utc",
                "created_at_utc", "updated_at_utc",
            )
        }

    def authenticate(
        self,
        username: str,
        password: str,
        *,
        client: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalize_username(username)
        with self.store.connect(read_only=True) as connection:
            raw = connection.execute(
                "SELECT * FROM local_users WHERE username=?", (normalized,)
            ).fetchone()
        now = datetime.now(UTC)
        generic_error = PlatformPermissionError("Invalid username or password")
        if raw is None:
            hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), b"0" * 32, _PASSWORD_ITERATIONS)
            raise generic_error
        user = dict(raw)
        if not bool(user["active"]):
            raise PlatformPermissionError("This local account is disabled")
        if user["locked_until_utc"] and _parse_utc(user["locked_until_utc"]) > now:
            raise PlatformPermissionError("Account is temporarily locked after failed sign-in attempts")
        expected = self._password_hash(
            password, base64.b64decode(user["salt"]), int(user["iterations"])
        )
        if not hmac.compare_digest(expected, str(user["password_hash"])):
            attempts = int(user["failed_attempts"]) + 1
            locked_until = None
            if attempts >= self.max_failed_attempts:
                locked_until = (now + timedelta(minutes=self.lockout_minutes)).isoformat(timespec="seconds")
                attempts = 0
            self.store.update(
                "local_users", "user_id", str(user["user_id"]),
                {
                    "failed_attempts": attempts,
                    "locked_until_utc": locked_until,
                    "updated_at_utc": utc_now(),
                },
            )
            self.store.audit(
                "local_sign_in_failed", "local_user", str(user["user_id"]),
                actor=normalized, role=str(user["role"]),
                detail={"locked": bool(locked_until)},
            )
            raise generic_error
        token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        created = now.isoformat(timespec="seconds")
        expires = (now + timedelta(minutes=self.session_minutes)).isoformat(timespec="seconds")
        session_id = new_id("SESSION")
        self.store.insert(
            "local_sessions",
            {
                "session_id": session_id,
                "user_id": user["user_id"],
                "token_hash": token_hash,
                "created_at_utc": created,
                "last_seen_utc": created,
                "expires_at_utc": expires,
                "revoked": 0,
                "client_json": redact_mapping(dict(client or {})),
            },
        )
        self.store.update(
            "local_users", "user_id", str(user["user_id"]),
            {
                "failed_attempts": 0,
                "locked_until_utc": None,
                "last_login_utc": created,
                "updated_at_utc": created,
            },
        )
        self.store.audit(
            "local_sign_in_succeeded", "local_session", session_id,
            actor=normalized, role=str(user["role"]),
            detail={"expires_at_utc": expires},
        )
        return {
            "session_token": token,
            "session_id": session_id,
            "expires_at_utc": expires,
            "user": self.user_profile(str(user["user_id"])),
        }

    def validate_session(self, token: str, *, refresh: bool = True) -> dict[str, Any]:
        token_hash = hashlib.sha256(require_text(token, "session token", 512).encode("utf-8")).hexdigest()
        with self.store.connect(read_only=True) as connection:
            raw = connection.execute(
                """
                SELECT s.*,u.username,u.display_name,u.role,u.active
                FROM local_sessions s JOIN local_users u ON u.user_id=s.user_id
                WHERE s.token_hash=?
                """,
                (token_hash,),
            ).fetchone()
        if raw is None:
            raise PlatformPermissionError("Session is invalid")
        session = dict(raw)
        now = datetime.now(UTC)
        if bool(session["revoked"]) or not bool(session["active"]) or _parse_utc(session["expires_at_utc"]) <= now:
            if not bool(session["revoked"]):
                self.store.update(
                    "local_sessions", "session_id", str(session["session_id"]), {"revoked": 1}
                )
            raise PlatformPermissionError("Session has expired or was revoked")
        expires = str(session["expires_at_utc"])
        if refresh:
            expires = (now + timedelta(minutes=self.session_minutes)).isoformat(timespec="seconds")
            self.store.update(
                "local_sessions", "session_id", str(session["session_id"]),
                {"last_seen_utc": now.isoformat(timespec="seconds"), "expires_at_utc": expires},
            )
        return {
            "session_id": session["session_id"],
            "user_id": session["user_id"],
            "username": session["username"],
            "display_name": session["display_name"],
            "role": session["role"],
            "expires_at_utc": expires,
        }

    def logout(self, token: str) -> bool:
        session = self.validate_session(token, refresh=False)
        changed = self.store.update(
            "local_sessions", "session_id", str(session["session_id"]), {"revoked": 1}
        )
        self.store.audit(
            "local_session_revoked", "local_session", str(session["session_id"]),
            actor=str(session["username"]), role=str(session["role"]),
        )
        return changed

    def prune_sessions(self) -> int:
        now = utc_now()
        with self.store.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM local_sessions WHERE revoked=1 OR expires_at_utc<=?", (now,)
            )
        return int(cursor.rowcount)

    def grant_dataset_permission(
        self, dataset_id: str, principal: str, role: str
    ) -> dict[str, Any]:
        check_permission(self.role, "assign")
        if self.store.row("datasets", "dataset_id", dataset_id) is None:
            raise KeyError(dataset_id)
        selected_role = validate_choice(role, ROLES, "role")
        normalized_principal = require_text(principal, "principal", 160)
        permission_id = new_id("DSPERM")
        with self.store.transaction() as connection:
            connection.execute(
                """
                INSERT INTO dataset_permissions(
                    permission_id,dataset_id,principal,role,granted_by,created_at_utc
                ) VALUES(?,?,?,?,?,?)
                ON CONFLICT(dataset_id,principal) DO UPDATE SET
                    role=excluded.role,granted_by=excluded.granted_by,
                    created_at_utc=excluded.created_at_utc
                """,
                (
                    permission_id, dataset_id, normalized_principal, selected_role,
                    self.actor, utc_now(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM dataset_permissions WHERE dataset_id=? AND principal=?",
                (dataset_id, normalized_principal),
            ).fetchone()
        self.store.audit(
            "dataset_permission_granted", "dataset", dataset_id,
            actor=self.actor, role=self.role,
            detail={"principal": normalized_principal, "assigned_role": selected_role},
        )
        return dict(row)

    def set_export_control(
        self,
        *,
        project_id: str | None,
        sensitive: bool,
        allowed_roles: Sequence[str],
        require_review: bool,
        maximum_rows: int | None = None,
        destination_policy: str = "local_only",
    ) -> dict[str, Any]:
        check_permission(self.role, "approve")
        if project_id and self.store.row("projects", "project_id", project_id) is None:
            raise KeyError(project_id)
        roles = list(dict.fromkeys(validate_choice(value, ROLES, "role") for value in allowed_roles))
        if maximum_rows is not None and int(maximum_rows) < 1:
            raise PlatformValidationError("Maximum export rows must be positive")
        if destination_policy not in {"local_only", "approved_folder", "blocked"}:
            raise PlatformValidationError("Unsupported export destination policy")
        control_id = new_id("EXPORT")
        self.store.insert(
            "export_controls",
            {
                "control_id": control_id,
                "project_id": project_id,
                "sensitive": int(bool(sensitive)),
                "allowed_roles_json": roles,
                "require_review": int(bool(require_review)),
                "maximum_rows": int(maximum_rows) if maximum_rows is not None else None,
                "destination_policy": destination_policy,
                "updated_by": self.actor,
                "updated_at_utc": utc_now(),
            },
        )
        return self.store.row("export_controls", "control_id", control_id) or {}

    def authorize_export(
        self,
        *,
        project_id: str | None,
        role: str,
        row_count: int,
        review_approved: bool = False,
    ) -> dict[str, Any]:
        selected_role = validate_choice(role, ROLES, "role")
        check_permission(selected_role, "export")
        with self.store.connect(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT * FROM export_controls
                WHERE project_id=? OR project_id IS NULL
                ORDER BY CASE WHEN project_id=? THEN 0 ELSE 1 END, rowid DESC LIMIT 1
                """,
                (project_id, project_id),
            ).fetchone()
        if row is None:
            return {"allowed": True, "reason": "No restrictive export control is configured"}
        control = dict(row)
        allowed_roles = set(__import__("json").loads(control["allowed_roles_json"] or "[]"))
        if allowed_roles and selected_role not in allowed_roles:
            raise PlatformPermissionError("Current role is not allowed by the export control")
        if control["destination_policy"] == "blocked":
            raise PlatformPermissionError("Exports are blocked by project policy")
        if control["maximum_rows"] is not None and row_count > int(control["maximum_rows"]):
            raise PlatformPermissionError("Export exceeds the configured row limit")
        if bool(control["require_review"]) and not review_approved:
            raise PlatformPermissionError("Export requires documented reviewer approval")
        return {
            "allowed": True,
            "sensitive": bool(control["sensitive"]),
            "destination_policy": control["destination_policy"],
            "control_id": control["control_id"],
        }


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(value: bytes) -> tuple[_DataBlob, Any]:
    buffer = ctypes.create_string_buffer(value, len(value))
    return _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _dpapi_protect(value: bytes) -> bytes:
    if os.name != "nt":
        raise PlatformConflictError("Windows DPAPI is unavailable on this operating system")
    source, source_buffer = _blob(value)
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    if not crypt32.CryptProtectData(
        ctypes.byref(source), "BioIntel local secret", None, None, None, 1, ctypes.byref(output)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)
        del source_buffer


def _dpapi_unprotect(value: bytes) -> bytes:
    if os.name != "nt":
        raise PlatformConflictError("Windows DPAPI is unavailable on this operating system")
    source, source_buffer = _blob(value)
    output = _DataBlob()
    description = wintypes.LPWSTR()
    crypt32 = ctypes.windll.crypt32
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source), ctypes.byref(description), None, None, None, 1, ctypes.byref(output)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)
        if description:
            ctypes.windll.kernel32.LocalFree(description)
        del source_buffer


class LocalSecretStore:
    """Stores secrets through keyring when available, otherwise Windows DPAPI."""

    def __init__(self, root: str | Path, *, service_name: str = "BioIntelAI"):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.service_name = require_text(service_name, "secret service", 100)
        try:
            import keyring  # type: ignore
        except ImportError:
            keyring = None
        self._keyring = keyring

    def _name(self, name: str) -> str:
        normalized = str(name or "").strip()
        if not _SECRET_NAME_RE.fullmatch(normalized):
            raise PlatformValidationError("Secret name contains unsupported characters")
        return normalized

    def _path(self, name: str) -> Path:
        filename = hashlib.sha256(name.encode("utf-8")).hexdigest() + ".dpapi"
        return safe_local_path(self.root, filename)

    def set(self, name: str, value: str) -> None:
        clean_name = self._name(name)
        secret = require_text(value, "secret value", 100_000)
        if self._keyring is not None:
            try:
                self._keyring.set_password(self.service_name, clean_name, secret)
                return
            except Exception:
                pass
        protected = _dpapi_protect(secret.encode("utf-8"))
        self._path(clean_name).write_bytes(protected)

    def get(self, name: str) -> str | None:
        clean_name = self._name(name)
        environment_name = "BIOINTEL_SECRET_" + re.sub(r"[^A-Za-z0-9]", "_", clean_name).upper()
        if environment_name in os.environ:
            return os.environ[environment_name]
        if self._keyring is not None:
            try:
                value = self._keyring.get_password(self.service_name, clean_name)
                if value is not None:
                    return value
            except Exception:
                pass
        path = self._path(clean_name)
        if not path.exists():
            return None
        return _dpapi_unprotect(path.read_bytes()).decode("utf-8")

    def delete(self, name: str) -> bool:
        clean_name = self._name(name)
        deleted = False
        if self._keyring is not None:
            try:
                self._keyring.delete_password(self.service_name, clean_name)
                deleted = True
            except Exception:
                pass
        path = self._path(clean_name)
        if path.exists():
            path.unlink()
            deleted = True
        return deleted


__all__ = [
    "LocalAuthenticationService",
    "LocalSecretStore",
    "redact_mapping",
    "safe_local_path",
    "sanitize_user_text",
]
