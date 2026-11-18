from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import time
import webbrowser
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Any
from uuid import uuid4

from step206_contract import PRODUCT_VERSION, RELEASE_STEP, REQUIRED_PYTHON, REQUIRED_PYTHON_TEXT, user_data_directory

ROOT = Path(__file__).resolve().parents[1]
USER_DATA = user_data_directory()
RUNTIME_LOGS = USER_DATA / "runtime_logs"
STATE_PATH = RUNTIME_LOGS / "biointel-running.json"
STATUS_PATH = RUNTIME_LOGS / "biointel-runtime-status.json"
LOCK_PATH = USER_DATA / "runtime" / "launcher-step206.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                creationflags=_windows_no_window_flags(),
            )
            return completed.returncode == 0 and str(pid) in completed.stdout
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, SystemError, ValueError):
        return False


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _same_root(value: object) -> bool:
    try:
        return bool(value) and Path(str(value)).resolve() == ROOT.resolve()
    except (OSError, ValueError):
        return False


def _positive_pid(value: object) -> int:
    try:
        pid = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return pid if pid > 0 else 0


def _windows_no_window_flags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0


def _creation_flags() -> int:
    if os.name != "nt":
        return 0
    flags = 0
    for name in ("CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS", "CREATE_NO_WINDOW"):
        flags |= int(getattr(subprocess, name, 0))
    return flags


class LauncherFileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: BinaryIO | None = None
        self.token = uuid4().hex

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise RuntimeError("BioIntel AI is already starting. Please use the existing window.") from exc
        self.handle.seek(0)
        self.handle.truncate(0)
        self.handle.write(json.dumps({"pid": os.getpid(), "root": str(ROOT), "token": self.token}).encode("utf-8"))
        self.handle.flush()

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self.handle.close()
        self.handle = None
        try:
            payload = _read_json(self.path)
            if payload.get("token") == self.token:
                self.path.unlink(missing_ok=True)
        except OSError:
            pass


@contextmanager
def launcher_lock():
    lock = LauncherFileLock(LOCK_PATH)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def _rotate_logs() -> None:
    RUNTIME_LOGS.mkdir(parents=True, exist_ok=True)
    files = sorted(
        (path for path in RUNTIME_LOGS.glob("*") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in files[120:]:
        path.unlink(missing_ok=True)


def _run_checked(command: list[str], *, label: str, log_path: Path | None = None) -> None:
    print(f"[BioIntel] {label}...", flush=True)
    if log_path is None:
        completed = subprocess.run(command, cwd=ROOT, check=False, creationflags=_windows_no_window_flags())
    else:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8", errors="replace") as handle:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_windows_no_window_flags(),
            )
    if completed.returncode:
        detail = ""
        if log_path is not None:
            try:
                detail = "\n" + "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-60:])
            except OSError:
                pass
        raise RuntimeError(f"{label} failed with code {completed.returncode}.{detail}")


def _open_browser(ui_url: str) -> None:
    disabled = os.environ.get("BIOINTEL_NO_BROWSER", "").strip().lower() in {"1", "true", "yes", "on"}
    opened = disabled
    if not disabled:
        try:
            opened = bool(webbrowser.open(ui_url, new=1))
        except Exception:
            opened = False

    fallback = RUNTIME_LOGS / "OPEN_BIOINTEL_URL.txt"
    fallback.write_text(ui_url + "\n", encoding="utf-8")
    if disabled:
        print("Automatic browser launch skipped; use the URL below.", flush=True)
    elif not opened and os.name == "nt":
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $env:BIOINTEL_UI_URL"],
                check=False,
                env={**os.environ, "BIOINTEL_UI_URL": ui_url},
                capture_output=True,
                timeout=5,
                creationflags=_windows_no_window_flags(),
            )
        except (OSError, subprocess.SubprocessError):
            pass
        print("Browser automatically open nahi hua. URL clipboard mein copy karne ki koshish ki gayi hai.", flush=True)
    print(f"BioIntel AI URL: {ui_url}", flush=True)


def _stop_other_release(state: dict[str, Any]) -> None:
    recorded_root = str(state.get("app_root", "")).strip()
    if not recorded_root or _same_root(recorded_root):
        return
    recorded_pids = [
        _positive_pid(state.get(field))
        for field in ("supervisor_pid", "ui_pid", "api_pid", "worker_pid")
    ]
    if not any(_pid_alive(pid) for pid in recorded_pids if pid):
        STATE_PATH.unlink(missing_ok=True)
        return
    source = str(ROOT / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    from biointel.operations.runtime_control import stop_local_runtime

    result = stop_local_runtime(recorded_root, USER_DATA)
    if result.get("state") not in {"stop-requested", "not-running", "stopped"}:
        raise RuntimeError(
            "A different BioIntel release is running and could not be handed off safely. "
            "Use its Stop BioIntel shortcut, then start again."
        )


def _existing_ready_session() -> str:
    state = _read_json(STATE_PATH)
    if not state:
        return ""
    if not _same_root(state.get("app_root")):
        _stop_other_release(state)
        return ""
    supervisor_pid = _positive_pid(state.get("supervisor_pid"))
    if not _pid_alive(supervisor_pid):
        STATE_PATH.unlink(missing_ok=True)
        return ""
    if state.get("status") == "ready":
        return str(state.get("ui_url", "")).strip()

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and _pid_alive(supervisor_pid):
        current = _read_json(STATE_PATH)
        status = str(current.get("status", ""))
        if status == "ready":
            return str(current.get("ui_url", "")).strip()
        if status == "failed":
            raise RuntimeError(str(current.get("message") or "Existing BioIntel startup failed."))
        time.sleep(0.6)
    if _pid_alive(supervisor_pid):
        raise RuntimeError("BioIntel AI is already starting. Please wait for the existing startup to finish.")
    STATE_PATH.unlink(missing_ok=True)
    return ""


def _wait_for_supervisor(supervisor: subprocess.Popen[bytes], *, seconds: int = 180) -> str:
    deadline = time.monotonic() + seconds
    last_message = ""
    while time.monotonic() < deadline:
        state = _read_json(STATE_PATH)
        if state and _same_root(state.get("app_root")):
            status = str(state.get("status", ""))
            last_message = str(state.get("message", ""))
            if status == "ready":
                ui_url = str(state.get("ui_url", "")).strip()
                if ui_url:
                    return ui_url
            if status == "failed":
                raise RuntimeError(last_message or "Runtime supervisor reported a startup failure.")
        if supervisor.poll() is not None:
            status = _read_json(STATUS_PATH)
            raise RuntimeError(str(status.get("message") or f"Runtime supervisor exited with code {supervisor.returncode}."))
        time.sleep(0.6)
    raise RuntimeError("BioIntel AI startup timed out." + (f" Last status: {last_message}" if last_message else ""))


def _write_failure_report(reason: str) -> Path | None:
    try:
        reports = USER_DATA / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        path = reports / f"step206-startup-failure-{datetime.now():%Y%m%d-%H%M%S}.json"
        path.write_text(
            json.dumps(
                {
                    "schema": "biointel.step206.startup-failure.v1",
                    "reason": reason,
                    "time": datetime.now(UTC).isoformat(timespec="seconds"),
                    "root": str(ROOT),
                    "project_data_changed": False,
                    "runtime_status": _read_json(STATUS_PATH),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        support = ROOT / "scripts" / "step206_support_bundle.py"
        if support.is_file():
            subprocess.run(
                [sys.executable, str(support), "--root", str(ROOT)],
                cwd=ROOT,
                check=False,
                creationflags=_windows_no_window_flags(),
            )
        return path
    except OSError:
        return None


def check_python_runtime() -> None:
    if sys.version_info[:2] != REQUIRED_PYTHON or struct.calcsize("P") * 8 != 64:
        current = ".".join(str(part) for part in sys.version_info[:3])
        raise RuntimeError(f"{REQUIRED_PYTHON_TEXT} is required. Active environment uses Python {current}.")


def run() -> int:
    with launcher_lock():
        _rotate_logs()
        check_python_runtime()
        existing = _existing_ready_session()
        if existing:
            print("BioIntel AI already running hai. Existing session open ki ja rahi hai.", flush=True)
            _open_browser(existing)
            return 0

        python = Path(sys.executable)
        if not python.is_file() or python.resolve() != (ROOT / ".venv" / "Scripts" / "python.exe").resolve():
            raise RuntimeError("Managed BioIntel environment missing or incorrect hai. INSTALL_WINDOWS.bat dobara run karein.")

        _run_checked(
            [str(python), str(ROOT / "scripts" / "step206_release_gate.py"), "--root", str(ROOT), "--quick"],
            label=f"Checking Step{RELEASE_STEP} managed release",
            log_path=RUNTIME_LOGS / f"step{RELEASE_STEP}-start-release-gate.log",
        )
        _run_checked(
            [
                str(python),
                str(ROOT / "scripts" / "step196_runtime_preflight.py"),
                "--root",
                str(ROOT),
                "--output",
                str(RUNTIME_LOGS / f"step{RELEASE_STEP}-runtime-preflight.json"),
            ],
            label="Checking scientific runtime",
            log_path=RUNTIME_LOGS / f"step{RELEASE_STEP}-runtime-preflight.log",
        )

        supervisor_script = ROOT / "scripts" / "runtime_supervisor_step206.py"
        if not supervisor_script.is_file():
            raise RuntimeError("Runtime supervisor file missing hai. INSTALL_WINDOWS.bat se repair karein.")
        supervisor_log_path = RUNTIME_LOGS / f"step{RELEASE_STEP}-supervisor-launch-{datetime.now():%Y%m%d-%H%M%S}.log"
        stream = supervisor_log_path.open("ab", buffering=0)
        try:
            supervisor = subprocess.Popen(
                [str(python), str(supervisor_script), "--root", str(ROOT)],
                cwd=ROOT,
                env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                creationflags=_creation_flags(),
                close_fds=os.name != "nt",
            )
        finally:
            stream.close()
        ui_url = _wait_for_supervisor(supervisor)
        print(f"BioIntel AI {PRODUCT_VERSION} ready hai.", flush=True)
        _open_browser(ui_url)
        return 0


def self_check() -> int:
    payload = {
        "script": str(Path(__file__).resolve()),
        "root": str(ROOT),
        "root_exists": ROOT.is_dir(),
        "supervisor": str(ROOT / "scripts" / "runtime_supervisor_step206.py"),
        "strict_python": REQUIRED_PYTHON_TEXT,
        "managed_install": True,
        "browser_fallback": True,
        "safe_mode_supported": True,
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["root_exists"] and Path(payload["supervisor"]).is_file() else 1


def main() -> int:
    if "--self-check" in sys.argv[1:]:
        return self_check()
    try:
        return run()
    except Exception as exc:
        print("", flush=True)
        print("BIOINTEL AI START NAHI HO PAYA", flush=True)
        print(str(exc), flush=True)
        report = _write_failure_report(str(exc))
        print("Project data change nahi hua. INSTALL_WINDOWS.bat se verified repair run karein.", flush=True)
        if report is not None:
            print(f"Diagnostic report: {report}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
