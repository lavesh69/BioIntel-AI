from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PRODUCT_NAME = "BioIntel AI"
PRODUCT_VERSION = "15.6.0"
RELEASE_STEP = 220
RELEASE_LABEL = "15.6.0-Step220.0-WINDOWS-V20.5"
PACKAGE_GENERATION = "V20.5"
PART_COUNT = 4
REQUIRED_PYTHON = (3, 11)
REQUIRED_PYTHON_TEXT = "CPython 3.11.x x64"
ARCHIVE_ROOT = "BioIntel-Step220"
RELEASE_ID = f"{PRODUCT_VERSION}-Step{RELEASE_STEP}"
MANIFEST_NAME = "STEP220_SOURCE_MANIFEST_SHA256.json"
CURRENT_SOURCE_MANIFEST_NAME = "release/SOURCE_MANIFEST_SHA256.json"
ASSIGNMENT_NAME = "STEP220_PACKAGE_PART_ASSIGNMENT.json"
RELEASE_NAME = "STEP220_RELEASE.json"


def local_app_data() -> Path:
    value = os.environ.get("LOCALAPPDATA", "").strip()
    if value:
        return Path(value).expanduser()
    return Path.home() / "AppData" / "Local"


def app_home() -> Path:
    configured = os.environ.get("BIOINTEL_APP_HOME", "").strip()
    if configured:
        return Path(configured).expanduser()
    return local_app_data() / "BioIntelAI"


def app_directory() -> Path:
    return app_home() / "App"


def releases_directory() -> Path:
    return app_directory() / "Releases"


def managed_release_root() -> Path:
    return releases_directory() / RELEASE_ID


def user_data_directory() -> Path:
    configured = os.environ.get("BIOINTEL_USER_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return app_home() / "UserData"


def active_record_path() -> Path:
    return app_home() / "active_install.json"


def stable_launcher_path() -> Path:
    return app_directory() / "RUN_BIOINTEL_ACTIVE.bat"


def stable_stop_path() -> Path:
    return app_directory() / "STOP_BIOINTEL_ACTIVE.bat"


def stable_restart_path() -> Path:
    return app_directory() / "RESTART_BIOINTEL_ACTIVE.bat"


def stable_repair_path() -> Path:
    return app_directory() / "REPAIR_BIOINTEL_ACTIVE.bat"


def stable_diagnose_path() -> Path:
    return app_directory() / "DIAGNOSE_BIOINTEL_ACTIVE.bat"


def stable_safe_mode_path() -> Path:
    return app_directory() / "SAFE_MODE_BIOINTEL_ACTIVE.bat"


def stable_uninstall_path() -> Path:
    return app_directory() / "UNINSTALL_BIOINTEL_ACTIVE.bat"


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def active_record(root: Path, shortcut: Path | None = None) -> dict[str, Any]:
    return {
        "schema": "biointel.active-install.v2",
        "release_step": RELEASE_STEP,
        "release_version": PRODUCT_VERSION,
        "package_generation": PACKAGE_GENERATION,
        "application_root": str(root.resolve()),
        "launcher": str(stable_launcher_path().resolve()),
        "managed_launcher": str((root / "RUN_BOTH_WINDOWS.bat").resolve()),
        "stop_launcher": str(stable_stop_path().resolve()),
        "restart_launcher": str(stable_restart_path().resolve()),
        "repair_launcher": str(stable_repair_path().resolve()),
        "diagnostic_launcher": str(stable_diagnose_path().resolve()),
        "safe_mode_launcher": str(stable_safe_mode_path().resolve()),
        "uninstall_launcher": str(stable_uninstall_path().resolve()),
        "desktop_shortcut": str(shortcut) if shortcut is not None else "",
        "updated_at": utc_now(),
    }
