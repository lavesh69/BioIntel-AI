from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from step206_contract import (
    active_record_path,
    app_directory,
    managed_release_root,
    user_data_directory,
)

ROOT = Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _validated_target(record: dict[str, Any]) -> Path:
    expected = managed_release_root().resolve()
    candidate_text = str(record.get("application_root", "")).strip()
    candidate = Path(candidate_text).expanduser().resolve() if candidate_text else expected
    releases = (app_directory() / "Releases").resolve()
    try:
        candidate.relative_to(releases)
    except ValueError as exc:
        raise RuntimeError("Refused to uninstall an application path outside the managed BioIntel Releases folder.") from exc
    if candidate != expected:
        raise RuntimeError(f"Refused unexpected active release path: {candidate}")
    return candidate


def _remove_recorded_shortcuts(record: dict[str, Any], *, dry_run: bool) -> list[str]:
    removed: list[str] = []
    for key in (
        "desktop_shortcut",
        "start_menu_shortcut",
        "stop_shortcut",
        "restart_shortcut",
        "repair_shortcut",
        "diagnostic_shortcut",
        "safe_mode_shortcut",
        "uninstall_shortcut",
    ):
        text = str(record.get(key, "")).strip()
        if not text:
            continue
        path = Path(text).expanduser()
        if path.suffix.lower() != ".lnk" or "BioIntel" not in path.name:
            continue
        if not dry_run:
            path.unlink(missing_ok=True)
        removed.append(str(path))
    return removed


def _stop_runtime(target: Path, *, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"state": "dry-run"}
    source = str(target / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    from biointel.operations.runtime_control import stop_local_runtime

    result = stop_local_runtime(target, user_data_directory())
    if result.get("state") not in {"stopped", "not-running"}:
        raise RuntimeError("BioIntel runtime could not be stopped safely; uninstall was cancelled.")
    return result


def _schedule_cleanup(target: Path, *, dry_run: bool) -> str:
    if dry_run:
        return "dry-run; no cleanup scheduled"
    if os.name != "nt":
        return "deferred-non-windows; application files were not removed"
    script = Path(tempfile.gettempdir()) / f"biointel-uninstall-{os.getpid()}.ps1"
    content = """param([int]$ParentPid)
$ErrorActionPreference = 'SilentlyContinue'
Wait-Process -Id $ParentPid -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 1200
Remove-Item -LiteralPath $env:BIOINTEL_UNINSTALL_TARGET -Recurse -Force
Get-ChildItem -LiteralPath $env:BIOINTEL_UNINSTALL_APP_DIR -Filter '*BIOINTEL_ACTIVE.bat' -File | Remove-Item -Force
Remove-Item -LiteralPath $env:BIOINTEL_UNINSTALL_ACTIVE_RECORD -Force
Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force
"""
    script.write_text(content, encoding="utf-8-sig")
    env = {
        **os.environ,
        "BIOINTEL_UNINSTALL_TARGET": str(target),
        "BIOINTEL_UNINSTALL_APP_DIR": str(app_directory()),
        "BIOINTEL_UNINSTALL_ACTIVE_RECORD": str(active_record_path()),
    }
    flags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) | int(getattr(subprocess, "DETACHED_PROCESS", 0))
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), str(os.getpid())],
        cwd=tempfile.gettempdir(),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=False,
    )
    return str(script)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--confirmed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.confirmed and not args.dry_run:
        print("Uninstall requires the explicit --confirmed flag.")
        return 2

    record = _read_json(active_record_path())
    target = _validated_target(record)
    runtime = _stop_runtime(target, dry_run=args.dry_run)
    shortcuts = _remove_recorded_shortcuts(record, dry_run=args.dry_run)
    cleanup = _schedule_cleanup(target, dry_run=args.dry_run)
    report = {
        "schema": "biointel.step206.safe-uninstall.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "target": str(target),
        "runtime": runtime,
        "removed_or_planned_shortcuts": shortcuts,
        "cleanup": cleanup,
        "dry_run": args.dry_run,
        "preserved": [
            str(user_data_directory()),
            "projects",
            "reports",
            "settings",
            "local databases",
            "exports",
            "backups",
        ],
        "application_recovery": "Reinstall from the same verified five-part release; UserData remains in place.",
    }
    output = user_data_directory() / "reports" / "step206-uninstall.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
