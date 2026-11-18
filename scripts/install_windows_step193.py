from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


APP_ROOT = Path(__file__).resolve().parents[1]


def _local_app_data() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if value:
        return Path(value).expanduser()
    return Path.home() / "AppData" / "Local"


def _venv_python(root: Path) -> Path:
    return root / ".venv" / "Scripts" / "python.exe"


class Installer:
    def __init__(self, root: Path, *, force_repair: bool = False) -> None:
        self.root = root.resolve()
        self.force_repair = force_repair
        self.local_app_data = _local_app_data()
        self.user_data = self.local_app_data / "BioIntelAI" / "UserData"
        self.log_dir = self.user_data / "runtime_logs"
        self.short_temp = self.local_app_data / "B175T"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.short_temp.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_path = self.log_dir / f"step193-install-v1-{stamp}.log"
        self.env = os.environ.copy()
        self.env.update(
            {
                "BIOINTEL_USER_DATA_DIR": str(self.user_data),
                "BIOINTEL_TOOLS_HOME": str(self.local_app_data / "BioIntelAI" / "Tools"),
                "BIOINTEL_REFERENCE_ASSETS_DIR": str(self.local_app_data / "BioIntelAI" / "ReferenceAssets"),
                "BIOINTEL_SHORT_TEMP": str(self.short_temp),
                "TEMP": str(self.short_temp),
                "TMP": str(self.short_temp),
                "PYTHONPATH": str(self.root / "src"),
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PIP_NO_INPUT": "1",
                "PIP_NO_CACHE_DIR": "1",
            }
        )

    def write(self, message: str = "") -> None:
        print(message, flush=True)
        with self.log_path.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(message + "\n")

    def run_process(self, command: Iterable[str], *, cwd: Path | None = None) -> int:
        argv = [str(item) for item in command]
        self.write("RUN: " + subprocess.list2cmdline(argv))
        process = subprocess.Popen(
            argv,
            cwd=str(cwd or self.root),
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            self.write(line.rstrip("\r\n"))
        return process.wait()

    def run_checked(self, command: Iterable[str], *, cwd: Path | None = None) -> None:
        argv = [str(item) for item in command]
        code = self.run_process(argv, cwd=cwd)
        if code != 0:
            raise RuntimeError(
                f"Command failed with exit code {code}: {subprocess.list2cmdline(argv)}"
            )

    def check_python(self) -> None:
        is_64 = struct.calcsize("P") * 8 == 64
        if sys.version_info[:2] != (3, 11) or not is_64:
            raise RuntimeError(
                "Python 3.11 x64 is required. "
                f"Current interpreter: {sys.version.split()[0]} ({platform.architecture()[0]})."
            )
        self.write(f"Python: {sys.executable}")

    def check_package(self) -> None:
        required = (
            "app.py",
            "requirements.lock",
            "requirements.lock.sha256",
            "requirements-windows-cp311-offline.lock",
            "scripts/bootstrap.py",
            "scripts/verify_dependency_lock.py",
            "scripts/verify_windows_wheelhouse.py",
            "scripts/step193_self_test.py",
            "scripts/background_job_worker.py",
            "scripts/run_windows_ui_regression.py",
            "pages/111_Windows_UI_Regression_Performance_Center.py",
            "pages/262_Step193_Mandatory_Module_Completion_Install_Repair_Center.py",
            "scripts/step193_validate_release.py",
            "scripts/step193_self_test.py",
            "STEP193_RELEASE.json",
            "wheelhouse/windows-cp311-x64/MANIFEST_SHA256.txt",
        )
        missing = [name for name in required if not (self.root / name).is_file()]
        if missing:
            raise RuntimeError(
                "Package is incomplete. Missing: "
                + ", ".join(missing)
                + ". Extract all four matching Step 193 ZIP parts into the same new empty destination."
            )

    def prepare_storage(self) -> None:
        for name in ("data", "reports", "workspace", "exports", "projects", "runtime_logs", "cache"):
            (self.user_data / name).mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(self.root).free
        self.write(f"Free disk space: {free / (1024**3):.2f} GB")
        if free < 3 * 1024**3:
            raise RuntimeError("At least 3 GB free disk space is required.")
        probe = self.user_data / ".install-write-probe"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()

    def remove_venv(self) -> None:
        venv = self.root / ".venv"
        if not venv.exists():
            return
        self.write("Removing the existing virtual environment for a clean repair...")
        try:
            shutil.rmtree(venv)
        except OSError as exc:
            raise RuntimeError(
                "The existing .venv is locked. Close every BioIntel/Python window and run the installer again. "
                f"Details: {exc}"
            ) from exc

    def prepare_venv(self) -> None:
        venv = self.root / ".venv"
        venv_python = _venv_python(self.root)
        should_remove = self.force_repair or (venv.exists() and not venv_python.is_file())
        if should_remove:
            self.remove_venv()

    def install_offline_environment(self) -> None:
        self.run_checked([sys.executable, "scripts/bootstrap.py", "--offline"])
        venv_python = _venv_python(self.root)
        if not venv_python.is_file():
            raise RuntimeError("Virtual-environment Python was not created.")
        self.run_checked([str(venv_python), "-m", "pip", "check"])

    def self_test_path(self) -> Path:
        return self.user_data / "reports" / "step193-install-self-test.json"

    def run_install_self_test(self) -> tuple[int, dict[str, object]]:
        venv_python = _venv_python(self.root)
        report = self.self_test_path()
        command = [
            str(venv_python),
            "scripts/step193_self_test.py",
            "--root",
            ".",
            "--output",
            str(report),
            "--allow-degraded",
        ]
        code = self.run_process(command)
        payload: dict[str, object] = {}
        try:
            loaded = json.loads(report.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                payload = loaded
        except (OSError, json.JSONDecodeError) as exc:
            self.write(f"Self-test report could not be read: {type(exc).__name__}: {exc}")
        failed = [
            item for item in payload.get("checks", [])
            if isinstance(item, dict) and item.get("status") != "PASS"
        ]
        if failed:
            self.write("Self-test findings:")
            for item in failed:
                self.write(
                    f"  - {item.get('name', 'Unknown')}: {item.get('detail', 'No detail')} "
                    f"[{item.get('severity', 'unknown')}]"
                )
        return code, payload

    def install(self) -> int:
        self.write("============================================================")
        self.write("BioIntel AI Step 193 - Windows Installer V1")
        self.write("============================================================")
        self.write(f"Application folder: {self.root}")
        self.write(f"Log file: {self.log_path}")

        self.write("[1/9] Checking extracted package...")
        self.check_package()

        self.write("[2/9] Checking Python 3.11 x64...")
        self.check_python()

        self.write("[3/9] Checking disk space and writable folders...")
        self.prepare_storage()

        self.write("[4/9] Verifying dependency locks and wheelhouse...")
        self.run_checked([sys.executable, "scripts/verify_dependency_lock.py", "--root", "."])
        self.run_checked([sys.executable, "scripts/verify_windows_wheelhouse.py", "--root", "."])

        self.write("[5/9] Preparing a clean Python environment...")
        self.prepare_venv()

        self.write("[6/9] Installing bundled offline wheels...")
        try:
            self.install_offline_environment()
        except Exception:
            if (self.root / ".venv").exists():
                self.write("First environment attempt failed; rebuilding .venv once...")
                self.remove_venv()
                self.install_offline_environment()
            else:
                raise

        self.write("[7/9] Running installation self-test...")
        code, payload = self.run_install_self_test()
        if code != 0:
            self.write("Critical self-test failed; performing one automatic clean environment repair...")
            self.remove_venv()
            self.install_offline_environment()
            code, payload = self.run_install_self_test()
        if code != 0:
            critical = [
                item for item in payload.get("checks", [])
                if isinstance(item, dict)
                and item.get("status") != "PASS"
                and item.get("severity", "critical") == "critical"
            ]
            details = " | ".join(
                f"{item.get('name')}: {item.get('detail')}" for item in critical
            ) or "See the Step 193 self-test JSON and installer log."
            raise RuntimeError(f"Critical installation self-test failed after automatic repair: {details}")

        status = str(payload.get("status", "PASS"))
        if status == "DEGRADED":
            self.write(
                "Advisory database/model validation reported a warning, but the verified UI/API runtime is installable. "
                "The detailed report has been saved for repair diagnostics."
            )

        self.write("[8/9] Building mandatory module completion assets...")
        self.run_checked([str(_venv_python(self.root)), "scripts/step193_build_mandatory_completion.py", "--root", "."])

        self.write("[9/9] Finalizing installation...")
        marker = self.root / ".biointel_step193_installed"
        marker.write_text(datetime.now(timezone.utc).isoformat() + "\n", encoding="utf-8")

        self.write("")
        self.write("============================================================")
        self.write("INSTALLATION COMPLETE")
        self.write("Run RUN_BOTH_WINDOWS.bat to open BioIntel AI.")
        self.write("============================================================")
        return 0


def self_check() -> int:
    payload = {
        "script": str(Path(__file__).resolve()),
        "root": str(APP_ROOT),
        "root_exists": APP_ROOT.is_dir(),
        "python_syntax": True,
        "path_roundtrip": Path(str(APP_ROOT)).resolve() == APP_ROOT.resolve(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(payload, indent=2))
    return 0 if all((payload["root_exists"], payload["python_syntax"], payload["path_roundtrip"])) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-repair", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        return self_check()

    installer: Installer | None = None
    try:
        installer = Installer(APP_ROOT, force_repair=args.force_repair)
        return installer.install()
    except Exception as exc:
        print("", flush=True)
        print("============================================================", flush=True)
        print("INSTALLATION FAILED", flush=True)
        print("============================================================", flush=True)
        print(str(exc), flush=True)
        if installer is not None:
            installer.write("ERROR: " + repr(exc))
            with installer.log_path.open("a", encoding="utf-8", errors="replace") as handle:
                traceback.print_exc(file=handle)
            print(f"Log file: {installer.log_path}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
