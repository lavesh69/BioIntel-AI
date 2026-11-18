from __future__ import annotations

from biointel.runtime_paths import runtime_database_path, runtime_report_path

import io
import json
import sqlite3
from biointel.database.core import managed_connect
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOCAL_ACTIVITY_TARGETS = (
    "reports/ui_preferences.json",
    "reports/security/ui_access_events.jsonl",
    "reports/logs/api.jsonl",
)


def _local_activity_files(root: Path) -> list[tuple[str, Path]]:
    """Return legacy and profile-scoped local activity files safely."""

    root = Path(root).resolve()
    candidates: list[tuple[str, Path]] = []
    for relative in LOCAL_ACTIVITY_TARGETS:
        candidates.append((relative, (root / relative).resolve()))
    profile_root = runtime_report_path(root, "ui_profiles")
    if profile_root.is_dir():
        for path in sorted(profile_root.glob("*/preferences.json")):
            resolved = path.resolve()
            try:
                relative = resolved.relative_to(root).as_posix()
            except ValueError:
                continue
            candidates.append((relative, resolved))

    unique: dict[str, Path] = {}
    for relative, candidate in candidates:
        if candidate == root or root not in candidate.parents:
            continue
        unique[relative] = candidate
    return sorted(unique.items())


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sqlite_count(path: Path, table: str) -> int | None:
    if not path.exists():
        return 0
    try:
        with managed_connect(path) as connection:
            return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    except (sqlite3.DatabaseError, OSError):
        return None


def build_privacy_inventory(root: Path) -> dict[str, Any]:
    """Describe data handled by the packaged application without exposing values."""

    root = Path(root).resolve()
    analytics_path = runtime_database_path(root, "analytics.sqlite3")
    api_security_path = runtime_database_path(root, "api_security.sqlite3")
    return {
        "generated_at_utc": _utc_now(),
        "processing_model": "local-first; hosted deployments process data on the configured BioIntel server",
        "medical_scope": "research and education only; not a diagnostic or treatment device",
        "categories": [
            {
                "category": "Scientific inputs",
                "examples": "Sequences, molecular identifiers, assay tables, omics matrices and documents supplied by the operator",
                "purpose": "Run the scientific workflow selected by the operator",
                "default_storage": "Local workspace or operator-controlled hosted deployment",
                "shared_by_default": False,
            },
            {
                "category": "Operational diagnostics",
                "examples": "Request timing, error codes, module name and release version",
                "purpose": "Reliability, security monitoring and troubleshooting",
                "default_storage": "Local reports databases",
                "shared_by_default": False,
            },
            {
                "category": "Preferences",
                "examples": "Theme, accessibility choices, favourites and recent pages",
                "purpose": "Personalise the interface",
                "default_storage": "Local JSON file",
                "shared_by_default": False,
            },
            {
                "category": "Provider requests",
                "examples": "Identifiers or search terms explicitly sent to NCBI, UniProt, PubChem, RCSB, ChEMBL or OpenAI",
                "purpose": "Retrieve requested external scientific information or generate a copilot response",
                "default_storage": "Only when the operator invokes a connected feature",
                "shared_by_default": False,
            },
        ],
        "external_provider_rule": (
            "No uploaded file is automatically sent to an external provider. Connected features display the provider and require an explicit operator action."
        ),
        "local_records": {
            "analytics_events": _sqlite_count(analytics_path, "run_events"),
            "api_request_logs": _sqlite_count(api_security_path, "api_request_log"),
            "api_security_events": _sqlite_count(api_security_path, "api_security_events"),
            "preference_file_present": any(
                relative.endswith("preferences.json") and path.is_file()
                for relative, path in _local_activity_files(root)
            ),
            "ui_access_log_present": (runtime_report_path(root, "security") / "ui_access_events.jsonl").exists(),
        },
        "controls": {
            "export_local_activity": True,
            "clear_preferences_and_local_logs": True,
            "delete_scientific_workspace": "Administrator-controlled; not performed by the privacy page to prevent accidental research-data loss",
        },
    }


def export_local_activity(root: Path) -> bytes:
    """Export non-scientific local activity and configuration evidence as a ZIP."""

    root = Path(root).resolve()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        inventory = json.dumps(build_privacy_inventory(root), indent=2, sort_keys=True)
        archive.writestr("privacy_inventory.json", inventory)
        for relative, path in _local_activity_files(root):
            if not path.is_file():
                continue
            archive.write(path, arcname=relative)
        readme = (
            "BioIntel AI local activity export\n"
            "This archive intentionally excludes scientific datasets, model files, API keys and secrets.\n"
            "Generated: " + _utc_now() + "\n"
        )
        archive.writestr("README.txt", readme)
    return output.getvalue()


def clear_local_activity(root: Path) -> dict[str, Any]:
    """Remove preferences and append-only local UI/API text logs.

    Scientific datasets, models, registries and database records are deliberately
    preserved. Database-level audit records require administrator retention policy
    actions and are not silently removed from a user-facing page.
    """

    root = Path(root).resolve()
    removed: list[str] = []
    failed: dict[str, str] = {}
    for relative, path in _local_activity_files(root):
        if not path.exists():
            continue
        try:
            path.unlink()
            removed.append(relative)
        except OSError as exc:
            failed[relative] = str(exc)
    return {"removed": removed, "failed": failed, "completed": not failed, "at_utc": _utc_now()}
