from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Compatibility filename retained because existing Windows launchers call it.
RELEASE_STEP = 175
PART_MARKERS = tuple(f".release_parts/step{RELEASE_STEP}_part{i}.ok" for i in range(1, 5))
SOURCE_MANIFEST = f"STEP{RELEASE_STEP}_SOURCE_MANIFEST_SHA256.json"
PACKAGE_ASSIGNMENT = f"STEP{RELEASE_STEP}_PACKAGE_PART_ASSIGNMENT.json"
RELEASE_FILE = f"STEP{RELEASE_STEP}_RELEASE.json"
CRITICAL_FILES = (
    "INSTALL_WINDOWS.bat",
    "RUN_BOTH_WINDOWS.bat",
    "RUN_BIOINTEL_PATH_SAFE_WINDOWS.bat",
    "AUTO_INSTALL_AND_RUN_WINDOWS.bat",
    "scripts/install_windows_step97.py",
    "scripts/run_biointel_step97.py",
    "scripts/step145_runtime_preflight.py",
    "scripts/step150_validate_installation.py",
    "scripts/verify_windows_wheelhouse.py",
    "scripts/step175_release_doctor.py",
    "RUN_STEP175_TARGET_ENVIRONMENT_WINDOWS.bat",
    RELEASE_FILE,
    SOURCE_MANIFEST,
    PACKAGE_ASSIGNMENT,
)


def _sanitize_path_text(value: str | os.PathLike[str] | None) -> str:
    if value is None:
        return ""
    text = os.fspath(value).strip()
    for _ in range(4):
        previous = text
        text = text.strip().lstrip('"').rstrip('"').strip()
        if text == previous:
            break
    return text


def _resolve_root(value: str | os.PathLike[str] | None) -> Path:
    cleaned = _sanitize_path_text(value) or "."
    candidate = Path(cleaned).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_report_path(root: Path) -> Path:
    candidates = [
        root / "reports" / "step175_installation_validation.json",
        Path(tempfile.gettempdir()) / "BioIntelAI" / "step175_installation_validation.json",
    ]
    last_error: OSError | None = None
    for candidate in candidates:
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError as exc:
            last_error = exc
    raise OSError("Unable to create validation report directory") from last_error


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path.name}")
    return payload


def validate(root: Path, *, allow_uninstalled: bool = False) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for marker in PART_MARKERS:
        ok = (root / marker).is_file()
        checks.append({"key": f"part_marker:{marker}", "passed": ok})
        if not ok:
            failures.append({
                "key": "missing_part_marker",
                "path": marker,
                "message": "One or more Step 175 ZIP parts were not extracted into this folder.",
            })

    release: dict[str, Any] = {}
    try:
        release = _load_json(root / RELEASE_FILE)
        release_ok = release.get("step") == RELEASE_STEP and str(release.get("version", "")).strip() == "14.7.0"
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        release_ok = False
        failures.append({"key": "release_file_unreadable", "path": RELEASE_FILE, "message": f"{type(exc).__name__}: {exc}"})
    checks.append({"key": "release_identity", "passed": release_ok})
    if not release_ok and not any(item["key"] == "release_file_unreadable" for item in failures):
        failures.append({"key": "wrong_release", "path": RELEASE_FILE, "message": "The folder is not a complete Step 175 / version 14.7.0 release."})

    manifest_entries: dict[str, dict[str, Any]] = {}
    try:
        manifest = _load_json(root / SOURCE_MANIFEST)
        raw_entries = manifest.get("entries", [])
        if not isinstance(raw_entries, list):
            raise ValueError("Manifest entries must be a list")
        manifest_entries = {
            str(item.get("path")): item
            for item in raw_entries
            if isinstance(item, dict) and item.get("path")
        }
        manifest_ok = manifest.get("schema") == "biointel.step175.source-manifest.v1"
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        manifest_ok = False
        failures.append({"key": "source_manifest_unreadable", "path": SOURCE_MANIFEST, "message": f"{type(exc).__name__}: {exc}"})
    checks.append({"key": "source_manifest", "passed": manifest_ok})

    try:
        assignment = _load_json(root / PACKAGE_ASSIGNMENT)
        assignments = assignment.get("assignments", {})
        assignment_ok = (
            assignment.get("schema") == "biointel.step175.package-assignment.v1"
            and isinstance(assignments, dict)
            and len(assignments) >= 10000
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        assignments = {}
        assignment_ok = False
        failures.append({"key": "package_assignment_unreadable", "path": PACKAGE_ASSIGNMENT, "message": f"{type(exc).__name__}: {exc}"})
    checks.append({"key": "package_assignment", "passed": assignment_ok})

    if assignment_ok:
        missing_assigned = [relative for relative in assignments if not (root / relative).is_file()]
        checks.append({"key": "all_assigned_files_present", "passed": not missing_assigned, "checked": len(assignments)})
        for relative in missing_assigned[:50]:
            failures.append({"key": "assigned_file_missing", "path": relative, "message": "A file assigned to one of the four Step 175 ZIP parts is missing."})
        if len(missing_assigned) > 50:
            failures.append({"key": "assigned_files_missing_truncated", "path": PACKAGE_ASSIGNMENT, "message": f"{len(missing_assigned) - 50} additional assigned files are missing."})

    for relative in CRITICAL_FILES:
        path = root / relative
        present = path.is_file()
        checks.append({"key": f"critical_present:{relative}", "passed": present})
        if not present:
            failures.append({"key": "critical_file_missing", "path": relative, "message": "Critical startup or release file is missing."})
            continue
        expected = manifest_entries.get(relative)
        if expected is None:
            # The two package metadata files are intentionally excluded from the source manifest.
            if relative not in {SOURCE_MANIFEST, PACKAGE_ASSIGNMENT}:
                failures.append({"key": "critical_file_not_manifested", "path": relative, "message": "Critical file is not recorded in the Step 175 source manifest."})
                checks.append({"key": f"critical_hash:{relative}", "passed": False})
            continue
        actual_size = path.stat().st_size
        actual_hash = _sha256(path)
        expected_size = int(expected.get("size_bytes", -1))
        expected_hash = str(expected.get("sha256", "")).lower()
        hash_ok = actual_size == expected_size and actual_hash.lower() == expected_hash
        checks.append({
            "key": f"critical_hash:{relative}",
            "passed": hash_ok,
            "expected_size_bytes": expected_size,
            "actual_size_bytes": actual_size,
            "expected_sha256": expected_hash,
            "actual_sha256": actual_hash,
        })
        if not hash_ok:
            failures.append({"key": "critical_file_hash_mismatch", "path": relative, "message": "A stale, mixed, or damaged critical Step 175 file was found."})

    launcher = root / "RUN_BOTH_WINDOWS.bat"
    launcher_text = launcher.read_text(encoding="utf-8-sig", errors="replace") if launcher.is_file() else ""
    launcher_ok = all(snippet in launcher_text for snippet in ("Step 175", "step175_part", '--root "."')) and "Step 150 ZIP Part" not in launcher_text
    checks.append({"key": "step175_launcher_contract", "passed": launcher_ok})
    if not launcher_ok:
        failures.append({"key": "stale_launcher", "path": "RUN_BOTH_WINDOWS.bat", "message": "The launcher still contains a legacy release-part contract."})

    preflight = root / "scripts" / "step145_runtime_preflight.py"
    preflight_text = preflight.read_text(encoding="utf-8", errors="replace") if preflight.is_file() else ""
    preflight_ok = (
        "resolve_path_argument" in preflight_text
        and "normalize_path_environment" in preflight_text
        and "biointel.startup-preflight.v150" in preflight_text
    )
    checks.append({"key": "protected_runtime_preflight", "passed": preflight_ok})
    if not preflight_ok:
        failures.append({"key": "runtime_preflight_invalid", "path": "scripts/step145_runtime_preflight.py", "message": "The protected path-safe runtime preflight is missing or stale."})

    if not allow_uninstalled:
        venv = root / ".venv" / "Scripts" / "python.exe"
        ok = venv.is_file()
        checks.append({"key": "installed_python", "passed": ok})
        if not ok:
            failures.append({"key": "application_not_installed", "path": ".venv/Scripts/python.exe", "message": "Run INSTALL_WINDOWS.bat before starting the app."})

    return {
        "schema": "biointel.step175.installation-validation.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "root": str(root),
        "release_step": RELEASE_STEP,
        "release_version": release.get("version") if isinstance(release, dict) else None,
        "checks": checks,
        "failures": failures,
        "passed": not failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--allow-uninstalled", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    root = _resolve_root(args.root)
    result = validate(root, allow_uninstalled=args.allow_uninstalled)
    output = Path(args.output).expanduser() if args.output else _safe_report_path(root)
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    result["report_path"] = str(output.resolve())
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"REPORT_PATH={output.resolve()}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
