from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REQUIRED_PYTHON = (3, 11, 9)


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
        install = (root / "INSTALL_WINDOWS.bat").read_text(encoding="utf-8-sig", errors="replace")
        run_bat = (root / "RUN_BOTH_WINDOWS.bat").read_text(encoding="utf-8-sig", errors="replace")
        locator = (root / "scripts/find_python311_windows.ps1").read_text(encoding="utf-8-sig", errors="replace")
        helper = (root / "scripts/install_windows_step196.py").read_text(encoding="utf-8-sig", errors="replace")
        launcher = (root / "scripts/run_biointel_step196.py").read_text(encoding="utf-8-sig", errors="replace")
        runtime = (root / "scripts/run_biointel_step97.py").read_text(encoding="utf-8-sig", errors="replace")
        add("exact Python 3.11.9 policy", all("(3,11,9)" in text.replace(" ", "") for text in (install, run_bat, locator, helper, launcher, runtime)), "installer, locator, venv and launchers")
        add("four-part active markers", "for %%P in (1 2 3 4)" in install and "step205_part%%P.ok" in install and "step205_part%%P.ok" in run_bat, "Step205 4/4")
        add("space-safe batch paths", all(token in install for token in ('pushd "%~dp0"', '"%PYTHON_EXE%"')) and all(token in run_bat for token in ('pushd "%~dp0"', '"%PY%"')), "quoted root and executables")
        add("runtime log directory before redirection", run_bat.index('mkdir "%LOGDIR%"') < run_bat.index('step205-start-preflight.log'), "created before use")
        add("automatic integrity gate", "step205_release_gate.py" in install and "--deep-hashes" in helper, "source SHA-256 inside installer")
        add("optional services isolated", "launch_optional_free_web_ai_setup(py)" not in helper and "setup_free_web_ai_windows.py" not in launcher, "not started or probed by core install/run")
        add("startup verification is blocking", "INSTALLATION VERIFICATION FAILED" in install and "exit /b 204" in install, "failure propagates")
        add("current support bundle reference", "CREATE_STEP193_SUPPORT_BUNDLE_WINDOWS.bat" in run_bat and "CREATE_STEP202_SUPPORT_BUNDLE_WINDOWS.bat" not in run_bat, "existing support bundle")
        add("stale shortcut cleanup scoped", "_remove_stale_biointel_shortcuts" in helper and "RUN_BOTH_WINDOWS.bat" in helper and "BioIntel AI*.lnk" in helper, "only BioIntel launcher shortcuts")
    except Exception as exc:
        add("source contract inspection", False, f"{type(exc).__name__}: {exc}")

    marker_missing = [part for part in range(1, 5) if not (root / ".release_parts" / f"step205_part{part}.ok").is_file()]
    add("extracted package markers", not marker_missing, marker_missing or "4/4 present")

    installed_python = Path(args.installed_python) if args.installed_python else None
    if installed_python and not installed_python.is_absolute():
        installed_python = root / installed_python
    if installed_python:
        if not installed_python.is_file():
            add("installed Python", False, f"missing: {installed_python}")
        else:
            completed = subprocess.run(
                [str(installed_python), "-c", "import struct,sys;print(sys.version.split()[0],struct.calcsize('P')*8);raise SystemExit(0 if sys.version_info[:3]==(3,11,9) and struct.calcsize('P')*8==64 else 1)"],
                cwd=root, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            add("installed Python", completed.returncode == 0, (completed.stdout or completed.stderr).strip())
            if completed.returncode == 0:
                imports = subprocess.run(
                    [str(installed_python), "-c", "import pandas,numpy,scipy,sklearn,streamlit,fastapi,Bio,rdkit,reportlab,pypdf"],
                    cwd=root, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
                )
                add("installed scientific imports", imports.returncode == 0, (imports.stderr or "complete")[-1000:])
                self_check = subprocess.run(
                    [str(installed_python), str(root / "scripts/run_biointel_step97.py"), "--self-check"],
                    cwd=root, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
                )
                add("runtime launcher self-check", self_check.returncode == 0, (self_check.stdout or self_check.stderr)[-1500:])
    else:
        builder_ok = args.allow_builder_python or (sys.version_info[:3] == REQUIRED_PYTHON and struct.calcsize("P") * 8 == 64)
        add("builder runtime informational", builder_ok, {"version": sys.version.split()[0], "allow_builder_python": args.allow_builder_python})

    passed = all(row["passed"] for row in checks)
    payload = {
        "schema": "biointel.step205.windows-install-run-verification.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "root": str(root), "passed": passed, "checks": checks,
        "native_windows_execution": os.name == "nt",
    }
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    output = Path(args.output) if args.output else local / "BioIntelAI" / "UserData" / "reports" / "step205-install-run-verification.json"
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
