from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import struct
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from biointel.security.passwords import hash_password
from biointel.security.ui_users import parse_ui_users

_USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_ALLOWED_ROLES = {"admin", "researcher", "reviewer", "viewer"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def user_data_root() -> Path:
    configured = os.environ.get("BIOINTEL_USER_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / "UserData"


def local_ui_users_path() -> Path:
    override = os.environ.get("BIOINTEL_UI_USERS_FILE", "").strip()
    if override:
        path = Path(override).expanduser().resolve()
    else:
        path = user_data_root() / "security" / "ui_users.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_local_ui_users(*, include_disabled: bool = False) -> dict[str, dict[str, Any]]:
    path = local_ui_users_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    users: dict[str, dict[str, Any]] = {}
    for username, record in payload.items():
        if not isinstance(record, dict):
            continue
        key = str(username).strip().lower()
        if not _USERNAME.fullmatch(key):
            continue
        enabled = bool(record.get("enabled", True))
        if not enabled and not include_disabled:
            continue
        password_hash = str(record.get("password_hash", "")).strip()
        if not password_hash:
            continue
        role = str(record.get("role", "researcher")).strip().lower()
        if role not in _ALLOWED_ROLES:
            role = "researcher"
        users[key] = {
            "password_hash": password_hash,
            "display_name": str(record.get("display_name") or key).strip(),
            "role": role,
            "enabled": enabled,
            "updated_at_utc": str(record.get("updated_at_utc", "")),
            "totp_enabled": bool(record.get("totp_enabled", False)),
            "totp_secret": str(record.get("totp_secret", "")).strip(),
        }
    return users


def configured_ui_users() -> dict[str, dict[str, Any]]:
    users: dict[str, dict[str, Any]] = {}
    for username, record in parse_ui_users(os.environ.get("BIOINTEL_UI_USERS_JSON", "")).items():
        users[username] = {**record, "enabled": True, "source": "environment"}
    for username, record in load_local_ui_users().items():
        users[username] = {**record, "source": "local_file"}
    return users


def _write(payload: dict[str, dict[str, Any]]) -> Path:
    path = local_ui_users_path()
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def upsert_local_ui_user(*, username: str, display_name: str, role: str, password: str | None = None, password_hash: str | None = None, enabled: bool = True, totp_enabled: bool | None = None, totp_secret: str | None = None) -> dict[str, Any]:
    key = str(username).strip().lower()
    if not _USERNAME.fullmatch(key):
        raise ValueError("Username must be 3-64 lowercase letters, numbers, dots, underscores or hyphens.")
    role = str(role).strip().lower()
    if role not in _ALLOWED_ROLES:
        raise ValueError("Unsupported UI role.")
    records = load_local_ui_users(include_disabled=True)
    existing = records.get(key, {})
    encoded = str(password_hash or existing.get("password_hash", "")).strip()
    if password is not None:
        encoded = hash_password(password)
    if not encoded:
        raise ValueError("A password or password hash is required for a new UI user.")
    record = {
        "password_hash": encoded,
        "display_name": str(display_name or key).strip()[:120],
        "role": role,
        "enabled": bool(enabled),
        "updated_at_utc": _now(),
        "totp_enabled": bool(existing.get("totp_enabled", False) if totp_enabled is None else totp_enabled),
        "totp_secret": str(existing.get("totp_secret", "") if totp_secret is None else totp_secret).strip(),
    }
    if record["totp_enabled"] and not record["totp_secret"]:
        record["totp_secret"] = generate_totp_secret()
    records[key] = record
    _write(records)
    return {"username": key, "display_name": record["display_name"], "role": role, "enabled": bool(enabled), "updated_at_utc": record["updated_at_utc"], "totp_enabled": record["totp_enabled"], "totp_secret": record["totp_secret"] if record["totp_enabled"] else ""}


def set_local_ui_user_enabled(username: str, *, enabled: bool) -> dict[str, Any]:
    key = str(username).strip().lower()
    records = load_local_ui_users(include_disabled=True)
    if key not in records:
        raise KeyError(key)
    records[key]["enabled"] = bool(enabled)
    records[key]["updated_at_utc"] = _now()
    _write(records)
    return {"username": key, "display_name": records[key]["display_name"], "role": records[key]["role"], "enabled": bool(enabled), "updated_at_utc": records[key]["updated_at_utc"]}


def public_local_ui_users() -> list[dict[str, Any]]:
    return [
        {"username": username, "display_name": record["display_name"], "role": record["role"], "enabled": bool(record.get("enabled", True)), "updated_at_utc": record.get("updated_at_utc", ""), "totp_enabled": bool(record.get("totp_enabled", False))}
        for username, record in sorted(load_local_ui_users(include_disabled=True).items())
    ]


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _totp_code(secret: str, *, timestamp: int | None = None, step_seconds: int = 30, digits: int = 6) -> str:
    normalized = str(secret).strip().replace(" ", "").upper()
    if not normalized:
        return ""
    try:
        key = base64.b32decode(normalized + "=" * (-len(normalized) % 8), casefold=True)
    except Exception:
        return ""
    counter = int((timestamp if timestamp is not None else time.time()) // step_seconds)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(value).zfill(digits)


def verify_totp(secret: str, code: str, *, timestamp: int | None = None, window: int = 1) -> bool:
    supplied = str(code).strip().replace(" ", "")
    if not supplied.isdigit() or len(supplied) != 6:
        return False
    now = int(timestamp if timestamp is not None else time.time())
    return any(hmac.compare_digest(_totp_code(secret, timestamp=now + offset * 30), supplied) for offset in range(-window, window + 1))


def set_local_ui_user_totp(username: str, *, enabled: bool, secret: str | None = None) -> dict[str, Any]:
    key = str(username).strip().lower()
    records = load_local_ui_users(include_disabled=True)
    if key not in records:
        raise KeyError(key)
    records[key]["totp_enabled"] = bool(enabled)
    records[key]["totp_secret"] = str(secret or records[key].get("totp_secret") or generate_totp_secret()).strip() if enabled else ""
    records[key]["updated_at_utc"] = _now()
    _write(records)
    return {"username": key, "totp_enabled": bool(enabled), "totp_secret": records[key]["totp_secret"] if enabled else ""}


__all__ = ["configured_ui_users", "generate_totp_secret", "load_local_ui_users", "local_ui_users_path", "public_local_ui_users", "set_local_ui_user_enabled", "set_local_ui_user_totp", "upsert_local_ui_user", "verify_totp"]
