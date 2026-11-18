from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
USER = LOCAL / "BioIntelAI" / "UserData"
RUNTIME = USER / "runtime"
LOCK = RUNTIME / "launcher-step195.lock"


def support(reason: str) -> None:
    out = USER / "reports" / f"step195-startup-failure-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "schema": "biointel.step195.startup-failure.v2",
                "reason": reason,
                "time": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    script = ROOT / "scripts" / "create_step192_support_bundle.py"
    py = Path(sys.executable)
    if script.is_file() and py.is_file():
        subprocess.run([str(py), str(script), "--root", str(ROOT)], cwd=ROOT, check=False)


def acquire() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            payload = json.loads(LOCK.read_text(encoding="utf-8"))
            age = time.time() - float(payload.get("epoch", 0))
        except Exception:
            age = 999999
        if age < 300:
            raise RuntimeError("BioIntel AI launcher is already starting. Wait a moment and retry.")
        LOCK.unlink(missing_ok=True)
    LOCK.write_text(json.dumps({"pid": os.getpid(), "epoch": time.time()}), encoding="utf-8")


def rotate_logs() -> None:
    logs = USER / "runtime_logs"
    if not logs.exists():
        return
    files = sorted(
        (path for path in logs.glob("*") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in files[80:]:
        path.unlink(missing_ok=True)


def run_command(command: list[str], *, label: str) -> int:
    print(f"[BioIntel] {label}...", flush=True)
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def main() -> int:
    try:
        acquire()
        rotate_logs()
        py = Path(sys.executable)
        if not py.is_file():
            raise RuntimeError("BioIntel AI Python environment is unavailable. Run INSTALL_WINDOWS.bat first.")

        repair_script = ROOT / "scripts" / "repair_step195_release_metadata.py"
        if repair_script.is_file():
            rc = run_command(
                [str(py), str(repair_script), "--root", str(ROOT), "--quiet"],
                label="Repairing current release metadata",
            )
            if rc:
                raise RuntimeError("Release metadata repair failed. Do not mix different ZIP releases.")

        validator = ROOT / "scripts" / "step195_validate_release.py"
        if validator.is_file():
            rc = run_command(
                [str(py), str(validator), "--root", str(ROOT)],
                label="Validating current release",
            )
            if rc:
                installer = ROOT / "scripts" / "install_windows_step195.py"
                if not installer.is_file():
                    raise RuntimeError("Release validation failed and installer repair script is missing.")
                repair_rc = run_command(
                    [str(py), str(installer), "--force-repair"],
                    label="Running automatic verified repair",
                )
                if repair_rc:
                    raise RuntimeError("Automatic verified repair failed.")
                if run_command(
                    [str(py), str(validator), "--root", str(ROOT)],
                    label="Re-validating repaired release",
                ):
                    raise RuntimeError("Release remains invalid after automatic repair.")

        free_setup = ROOT / "scripts" / "setup_free_web_ai_windows.py"
        if free_setup.is_file() and os.environ.get("BIOINTEL_SKIP_FREE_WEB_AI_SETUP", "").strip().lower() not in {"1", "true", "yes"}:
            run_command(
                [str(py), str(free_setup), "--no-install", "--no-pull", "--model", os.environ.get("BIOINTEL_OLLAMA_MODEL", "gemma3:1b")],
                label="Starting optional free local AI service",
            )

        runner = ROOT / "scripts" / "run_biointel_step97.py"
        if not runner.is_file():
            raise RuntimeError("BioIntel runtime launcher is missing.")
        rc = run_command([str(py), str(runner)], label="Starting BioIntel AI")
        if rc:
            raise RuntimeError(f"BioIntel runtime exited with code {rc}.")
        return 0
    except Exception as exc:
        print(f"BIOINTEL STARTUP FAILED: {exc}", flush=True)
        support(str(exc))
        traceback.print_exc()
        return 1
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
