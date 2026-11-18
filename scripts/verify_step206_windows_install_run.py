from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from step206_contract import (
    PACKAGE_GENERATION,
    PART_COUNT,
    PRODUCT_VERSION,
    RELEASE_NAME,
    RELEASE_STEP,
    REQUIRED_PYTHON,
    REQUIRED_PYTHON_TEXT,
    managed_release_root,
    user_data_directory,
    utc_now,
)


def text(root: Path, path: str) -> str:
    return (root / path).read_text(encoding="utf-8-sig", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--installed-python")
    parser.add_argument("--allow-builder-python", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    try:
        release = json.loads(text(root, RELEASE_NAME))
        with (root / "pyproject.toml").open("rb") as handle:
            project_version = str(tomllib.load(handle).get("project", {}).get("version", "")).strip()
        add(
            "release identity",
            text(root, "VERSION").strip() == PRODUCT_VERSION
            and project_version == PRODUCT_VERSION
            and release.get("version") == PRODUCT_VERSION
            and release.get("step") == RELEASE_STEP
            and release.get("part_count") == PART_COUNT
            and release.get("package_generation") == PACKAGE_GENERATION,
            release,
        )
        install = text(root, "INSTALL_WINDOWS.bat")
        run_bat = text(root, "RUN_BOTH_WINDOWS.bat")
        stop_bat = text(root, "STOP_BIOINTEL_WINDOWS.bat")
        restart_bat = text(root, "RESTART_BIOINTEL_WINDOWS.bat")
        online_fallback = text(root, "INSTALL_WINDOWS_ONLINE_FALLBACK.bat")
        installer = text(root, "scripts/install_windows_step206.py")
        launcher = text(root, "scripts/run_biointel_step206.py")
        supervisor = text(root, "scripts/runtime_supervisor_step206.py")
        control = text(root, "src/biointel/operations/runtime_control.py")
        python_setup = text(root, "scripts/install_python311_user.ps1")
        bootstrap = text(root, "scripts/bootstrap.py")
        compatibility = text(root, "scripts/verify_windows_runtime_compatibility_step206.py")

        all_runtime_files = (install, run_bat, installer, launcher, supervisor, python_setup)
        add(
            "compatible Python 3.11.x x64",
            all("(3,11)" in item.replace(" ", "") or "REQUIRED_PYTHON" in item for item in all_runtime_files),
            REQUIRED_PYTHON_TEXT,
        )
        add("four-part workflow", "for %%P in (1 2 3 4)" in install and f"step{RELEASE_STEP}_part%%P.ok" in install and f"step{RELEASE_STEP}_part%%P.ok" in run_bat, "4/4 markers")
        runtime_preflight = text(root, "scripts/step97_runtime_preflight.py")
        add(
            "four-part scientific runtime preflight",
            "return set(range(1, 5))" in runtime_preflight,
            f"Step{RELEASE_STEP} accepts 4/4 markers",
        )
        add("same-release stale managed copy replacement", "def _target_source_valid(source_root: Path)" in installer and "source_manifest.read_bytes() != target_manifest.read_bytes()" in installer, "source manifest comparison")
        add("two supported user entrypoints", "install_windows_step206.py" in install and "run_biointel_step206.py" in run_bat, "INSTALL_WINDOWS.bat -> RUN_BOTH_WINDOWS.bat")
        add(
            "managed online fallback",
            "install_windows_step206.py" in online_fallback
            and "--force-repair --online" in online_fallback
            and 'parser.add_argument("--online"' in installer,
            "same managed installation, verification, smoke test, and stable launchers",
        )
        add("managed LocalAppData install", "managed_release_root" in installer and "install_managed_source" in installer and "stable_launcher_path" in installer, str(managed_release_root()))
        add("atomic source staging", ".staging-" in installer and "staging.replace(TARGET_ROOT)" in installer and "invalid-backup" in installer, "staging plus rollback")
        add("environment rollback", ".venv.step206-backup" in installer and "backup.replace(venv)" in installer, "previous venv restored on failure")
        add("automatic deep integrity", "step206_release_gate.py" in installer and "--deep-hashes" in installer and "verify_windows_wheelhouse.py" in installer, "source and wheelhouse")
        add(
            "pkg_resources runtime compatibility",
            "setuptools==80.9.0" in bootstrap
            and "setuptools==83.0.0" not in bootstrap
            and "verify_windows_runtime_compatibility_step206.py" in installer
            and "verify_windows_runtime_compatibility_step206.py" in run_bat
            and "pkg_resources" in compatibility
            and "ont_fast5_api" in compatibility,
            "setuptools 80.9.0 plus full V19.6 import verification",
        )
        # Step220 R2 moved from a fixed database-path constant to recursive UserData
        # discovery plus legacy release discovery. Verify the active implementation
        # instead of requiring the removed RUNTIME_DATABASE_RELATIVE_PATHS symbol.
        database_backup_ok = (
            "def _backup_databases" in installer
            and "def _migrate_previous_runtime_databases" in installer
            and "def _legacy_release_databases" in installer
            and "USER_DATA.rglob" in installer
            and 'destination = USER_DATA / "databases"' in installer
            and "LEGACY_RUNTIME_DATABASE_NAMES" in installer
            and "pre-step206-" in installer
        )
        add(
            "database backup and migration before activation",
            database_backup_ok,
            "recursive UserData backup plus legacy release SQLite migration",
        )
        add("stable shortcut refresh", "RUN_BIOINTEL_ACTIVE.bat" in text(root, "scripts/step206_contract.py") and "Start Menu" in installer and "BioIntel AI*.lnk" in installer, "Desktop and Start Menu")
        runtime_paths = text(root, "src/biointel/runtime_paths.py")
        relationship_integrity = text(root, "src/biointel/data/relationship_integrity.py")
        portfolio_demo_ui = text(root, "src/biointel/portfolio_demo_v183/ui.py")
        page_excellence_ui = text(root, "src/biointel/page_excellence_v187/ui.py")
        add(
            "managed bundled assurance assets",
            "seed_bundled_user_data" in installer
            and "BUNDLED_USER_DATA_SEED_NAMES" in installer
            and "BIOINTEL_USER_DATA_DIR" in runtime_paths
            and "user_data_root" in runtime_paths,
            "Step183-Step193 seeds copy missing-only into managed UserData",
        )
        add(
            "missing runtime artifacts fail safely",
            "if not validation.demo_ready" in portfolio_demo_ui
            and "if not r.qualified_10_of_10" in page_excellence_ui
            and 'message.startswith("no such table:")' in relationship_integrity,
            "missing demo/page assets and optional legacy tables no longer crash Home or page panels",
        )
        add(
            "no-flash Windows launch",
            "RUN_BIOINTEL_ACTIVE_HIDDEN.vbs" in installer
            and "wscript.exe" in installer
            and ", 0, False" in installer
            and "CREATE_NO_WINDOW" in launcher
            and "CREATE_NO_WINDOW" in supervisor
            and "CREATE_NO_WINDOW" in control,
            "hidden Desktop/Start launcher plus no-window runtime fallbacks",
        )
        add("Stop and Restart controls", "runtime_control_step206.py" in stop_bat and "runtime_control_step206.py" in restart_bat and "biointel-stop.request" in control, "graceful lifecycle")
        add("resident supervisor", "RuntimeSupervisor" in supervisor and "monitor(self)" in supervisor and "restart loop" in supervisor, "UI/API/worker monitoring")
        add("strict readiness", "status == 200" in supervisor and "payload.get(\"version\") == PRODUCT_VERSION" in supervisor and "_local_database_ready" in supervisor and "runtime-readiness.sqlite3" in supervisor and "body.casefold() == \"ok\"" in supervisor, "API health, local SQLite read/write, Streamlit health")
        add("startup failure cleanup", "self.cleanup()" in supervisor and "worker_service.stop" in supervisor and "_terminate_process(self.ui)" in supervisor and "_terminate_process(self.api)" in supervisor, "no orphan UI/API/worker")
        add("native smoke test is installer-blocking", "windows_smoke_test_step206.py" in installer and "run_native_smoke_test" in installer, "starts, verifies, and stops runtime on Windows")
        add("Streamlit app exception gate", "streamlit_startup_check_step206.py" in installer and "AppTest.from_file" in text(root, "scripts/streamlit_startup_check_step206.py") and "app.exception" in text(root, "scripts/streamlit_startup_check_step206.py"), "home app executes before activation")
        add("optional services isolated", "setup_free_web_ai_windows.py" not in launcher and "setup_scientific_runtime_windows.py" not in launcher and "optional_services" in installer, "offline core unaffected")
        add("browser fallback", "OPEN_BIOINTEL_URL.txt" in launcher and "Set-Clipboard" in launcher, "visible URL and clipboard fallback")
        add("sanitized automatic support bundle", "step206_support_bundle.py" in launcher and "step206_support_bundle.py" in installer and "No project datasets" in text(root, "scripts/step206_support_bundle.py"), "failure diagnostics without project data")
        add("space-safe batch paths", 'pushd "%~dp0"' in install and 'pushd "%~dp0"' in run_bat and '"%PYTHON_EXE%"' in install and '"%PY%"' in run_bat, "quoted paths")
    except Exception as exc:
        add("source contract inspection", False, f"{type(exc).__name__}: {exc}")

    missing_markers = [part for part in range(1, PART_COUNT + 1) if not (root / ".release_parts" / f"step{RELEASE_STEP}_part{part}.ok").is_file()]
    add("extracted package markers", not missing_markers, missing_markers or "4/4 present")

    installed_python = Path(args.installed_python) if args.installed_python else None
    if installed_python and not installed_python.is_absolute():
        installed_python = root / installed_python
    if installed_python:
        if not installed_python.is_file():
            add("installed Python", False, f"missing: {installed_python}")
        else:
            completed = subprocess.run(
                [
                    str(installed_python),
                    "-c",
                    (
                        "import struct,sys;"
                        "print(sys.version.split()[0],struct.calcsize('P')*8);"
                        f"raise SystemExit(0 if sys.version_info[:2]=={REQUIRED_PYTHON!r} "
                        "and struct.calcsize('P')*8==64 else 1)"
                    ),
                ],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            add("installed Python", completed.returncode == 0, (completed.stdout or completed.stderr).strip())
            if completed.returncode == 0:
                pip_check = subprocess.run(
                    [str(installed_python), "-m", "pip", "check"],
                    cwd=root,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                add("installed dependency consistency", pip_check.returncode == 0, (pip_check.stdout or pip_check.stderr or "complete")[-1500:])
                imports = subprocess.run(
                    [
                        str(installed_python),
                        str(root / "scripts" / "verify_windows_runtime_compatibility_step206.py"),
                        "--root",
                        str(root),
                        "--strict-python",
                        "--output",
                        str(user_data_directory() / "reports" / "step206-windows-runtime-compatibility-verification.json"),
                    ],
                    cwd=root,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                add("installed scientific imports", imports.returncode == 0, (imports.stdout or imports.stderr or "complete")[-3000:])
                self_check = subprocess.run(
                    [str(installed_python), str(root / "scripts" / "runtime_supervisor_step206.py"), "--root", str(root), "--self-check"],
                    cwd=root,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                add("runtime supervisor self-check", self_check.returncode == 0, (self_check.stdout or self_check.stderr)[-1500:])
    else:
        builder_ok = args.allow_builder_python or (sys.version_info[:3] == REQUIRED_PYTHON and struct.calcsize("P") * 8 == 64)
        add("builder runtime informational", builder_ok, {"version": sys.version.split()[0], "allow_builder_python": args.allow_builder_python})

    passed = all(row["passed"] for row in checks)
    payload = {
        "schema": f"biointel.step{RELEASE_STEP}.windows-install-run-verification.v2",
        "generated_at": utc_now(),
        "root": str(root),
        "passed": passed,
        "failed_checks": [row["name"] for row in checks if not row["passed"]],
        "checks": checks,
        "native_windows_execution": os.name == "nt",
    }
    output = Path(args.output) if args.output else user_data_directory() / "reports" / f"step{RELEASE_STEP}-install-run-verification.json"
    if not output.is_absolute():
        output = root / output
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        payload["report_path"] = str(output)
    except OSError:
        pass
    print(json.dumps(payload, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
