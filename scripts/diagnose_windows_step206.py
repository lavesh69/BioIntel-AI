from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from step206_contract import (
    MANIFEST_NAME,
    PART_COUNT,
    PRODUCT_VERSION,
    RELEASE_NAME,
    RELEASE_STEP,
    REQUIRED_PYTHON,
    REQUIRED_PYTHON_TEXT,
    active_record_path,
    managed_release_root,
    user_data_directory,
)

ROOT = Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _run(command: list[str], *, cwd: Path, timeout: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env={**os.environ, "PYTHONPATH": str(cwd / "src")},
        )
        return {
            "return_code": completed.returncode,
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {"return_code": -1, "error": f"{type(exc).__name__}: {exc}"}


def _probe_unicode_path(base: Path) -> dict[str, Any]:
    probe_root = base / "diagnostic-path-Δ-नमस्ते space"
    probe = probe_root / "round-trip.txt"
    try:
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("BioIntel UTF-8 ✓\n", encoding="utf-8")
        passed = probe.read_text(encoding="utf-8") == "BioIntel UTF-8 ✓\n"
        return {"passed": passed, "path": str(probe)}
    except OSError as exc:
        return {"passed": False, "path": str(probe), "error": str(exc)}
    finally:
        try:
            probe.unlink(missing_ok=True)
            probe_root.rmdir()
        except OSError:
            pass


def diagnose(root: Path, *, deep: bool, support_bundle: bool) -> tuple[dict[str, Any], int]:
    root = root.resolve()
    user_data = user_data_directory()
    reports = user_data / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    critical: list[str] = []
    warnings: list[str] = []

    required = (
        "app.py",
        "INSTALL_WINDOWS.bat",
        "RUN_BOTH_WINDOWS.bat",
        "REPAIR_WINDOWS.bat",
        "DIAGNOSE_WINDOWS.bat",
        "SAFE_MODE_WINDOWS.bat",
        "requirements.lock",
        RELEASE_NAME,
        MANIFEST_NAME,
    )
    missing = [item for item in required if not (root / item).is_file()]
    if missing:
        critical.append("Critical release files are missing.")

    missing_parts = [
        part
        for part in range(1, PART_COUNT + 1)
        if not (root / ".release_parts" / f"step{RELEASE_STEP}_part{part}.ok").is_file()
    ]
    if missing_parts:
        critical.append(f"One or more Step{RELEASE_STEP} package parts are missing.")

    release_gate_output = reports / f"step{RELEASE_STEP}-diagnostic-release-gate.json"
    gate_command = [
        sys.executable,
        str(root / "scripts" / "step206_release_gate.py"),
        "--root",
        str(root),
        "--output",
        str(release_gate_output),
    ]
    if deep:
        gate_command.append("--deep-hashes")
    else:
        gate_command.append("--quick")
    if sys.version_info[:2] != REQUIRED_PYTHON:
        gate_command.append("--allow-builder-python")
    gate = _run(gate_command, cwd=root, timeout=1200 if deep else 180)
    if gate["return_code"] != 0:
        critical.append(f"Step{RELEASE_STEP} release integrity gate failed.")

    active_record = _read_json(active_record_path())
    managed_root = managed_release_root()
    installed_python = managed_root / ".venv" / "Scripts" / "python.exe"
    installed = managed_root.is_dir() and installed_python.is_file()
    python_probe: dict[str, Any]
    if installed_python.is_file():
        python_probe = _run(
            [
                str(installed_python),
                "-c",
                "import json,struct,sys;print(json.dumps({'version':list(sys.version_info[:3]),'bits':struct.calcsize('P')*8}));raise SystemExit(0 if sys.version_info[:3]==(3,11,9) and struct.calcsize('P')*8==64 else 1)",
            ],
            cwd=managed_root,
            timeout=30,
        )
        if python_probe["return_code"] != 0:
            critical.append("Managed Python is not CPython 3.11.x x64.")
    else:
        python_probe = {"return_code": 1, "detail": "Managed environment not installed."}
        warnings.append("Managed installation is absent; run INSTALL_WINDOWS.bat before starting the app.")

    dependency_probe: dict[str, Any] = {"return_code": 1, "detail": "Not run; managed Python absent."}
    if installed_python.is_file():
        dependency_probe = _run([str(installed_python), "-m", "pip", "check"], cwd=managed_root, timeout=300)
        if dependency_probe["return_code"] != 0:
            critical.append("Managed dependency consistency check failed.")

    runtime: dict[str, Any]
    try:
        source = str(root / "src")
        if source not in sys.path:
            sys.path.insert(0, source)
        from biointel.operations.runtime_control import inspect_local_runtime

        runtime = inspect_local_runtime(managed_root, user_data)
    except Exception as exc:
        runtime = {"state": "inspection-failed", "error": f"{type(exc).__name__}: {exc}"}
        warnings.append("Runtime state could not be inspected.")

    registry: dict[str, Any]
    try:
        from biointel.product_registry import registry_integrity

        registry = registry_integrity(root)
        if not registry.get("healthy"):
            critical.append("Authoritative module registry integrity failed.")
    except Exception as exc:
        registry = {"healthy": False, "error": f"{type(exc).__name__}: {exc}"}
        critical.append("Authoritative module registry could not be loaded.")

    disk = shutil.disk_usage(user_data.parent)
    if disk.free < 2 * 1024**3:
        warnings.append("Less than 2 GB free space remains on the BioIntel application drive.")
    unicode_path = _probe_unicode_path(user_data / "runtime")
    if not unicode_path["passed"]:
        critical.append("Spaces/Unicode path round-trip failed.")

    bundle_path = ""
    if support_bundle and (root / "scripts" / "step206_support_bundle.py").is_file():
        bundle = _run(
            [sys.executable, str(root / "scripts" / "step206_support_bundle.py"), "--root", str(root)],
            cwd=root,
            timeout=120,
        )
        if bundle["return_code"] == 0:
            bundle_path = bundle.get("stdout_tail", "").strip().splitlines()[-1]
        else:
            warnings.append("Sanitized support bundle creation failed; the JSON diagnostic report is still available.")

    payload = {
        "schema": f"biointel.step{RELEASE_STEP}.windows-diagnostic.v3",
        "generated_at_utc": _now(),
        "status": "passed" if not critical else "failed",
        "release": {"version": PRODUCT_VERSION, "step": RELEASE_STEP},
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "diagnostic_python": {"version": sys.version.split()[0], "bits": struct.calcsize("P") * 8, "required": REQUIRED_PYTHON_TEXT},
        "root": str(root),
        "managed_root": str(managed_root),
        "installed": installed,
        "active_record": active_record,
        "critical_issues": critical,
        "warnings": warnings,
        "checks": {
            "missing_critical_files": missing,
            "missing_package_parts": missing_parts,
            "release_gate": gate,
            "managed_python": python_probe,
            "dependency_consistency": dependency_probe,
            "runtime": runtime,
            "module_registry": registry,
            "unicode_and_space_path": unicode_path,
            "disk": {"total_bytes": disk.total, "free_bytes": disk.free},
        },
        "support_bundle": bundle_path,
        "privacy": "No project dataset contents are included in this report or the sanitized support bundle.",
    }
    return payload, 0 if not critical else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--output")
    parser.add_argument("--deep", action="store_true")
    parser.add_argument("--support-bundle", action="store_true")
    args = parser.parse_args()
    payload, code = diagnose(Path(args.root), deep=args.deep, support_bundle=args.support_bundle)
    default = user_data_directory() / "reports" / f"step{RELEASE_STEP}-windows-diagnostic-{datetime.now():%Y%m%d-%H%M%S}.json"
    output = Path(args.output).expanduser().resolve() if args.output else default
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    print(json.dumps({"status": payload["status"], "report": str(output), "support_bundle": payload["support_bundle"]}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
