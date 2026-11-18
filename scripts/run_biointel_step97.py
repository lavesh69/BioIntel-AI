from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


APP_ROOT = Path(__file__).resolve().parents[1]
_RUNTIME_PID_FIELDS = ("ui_pid", "api_pid", "worker_pid")


def _local_app_data() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if value:
        return Path(value).expanduser()
    return Path.home() / "AppData" / "Local"


def _free_port(start: int, end: int) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free localhost port is available between {start} and {end}.")


def _url_ready(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= int(response.status) < 500
    except (OSError, urllib.error.URLError, ValueError):
        return False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        # CPython implements ``os.kill(pid, 0)`` differently on Windows and can
        # raise WinError 87/SystemError for stale PIDs. Query a process handle
        # instead so an old launcher state file never prevents startup.
        try:
            import ctypes
            from ctypes import wintypes

            process_query_limited_information = 0x1000
            synchronize = 0x00100000
            wait_timeout = 0x00000102
            error_access_denied = 5
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel32.WaitForSingleObject.restype = wintypes.DWORD
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            handle = kernel32.OpenProcess(
                process_query_limited_information | synchronize,
                False,
                int(pid),
            )
            if not handle:
                return ctypes.get_last_error() == error_access_denied
            try:
                return int(kernel32.WaitForSingleObject(handle, 0)) == wait_timeout
            finally:
                kernel32.CloseHandle(handle)
        except (Exception, SystemError, ValueError):
            return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, SystemError, ValueError):
        return False


def _state_pid(state: dict[str, object], field: str) -> int:
    try:
        pid = int(state.get(field, 0) or 0)
    except (TypeError, ValueError):
        return 0
    return pid if pid > 0 else 0


def _same_release(root: Path, recorded_root: str) -> bool:
    """Compare release roots without trusting malformed shared state."""
    try:
        return bool(recorded_root) and Path(recorded_root).expanduser().resolve() == root.resolve()
    except (OSError, ValueError):
        return False


def _normalise_command_value(value: str | Path) -> str:
    return str(value).replace("\\", "/").casefold()


def _command_line_for_pid(pid: int) -> str:
    """Return a local process command line when the platform permits it.

    A cross-release handover must never kill a PID merely because a stale JSON
    file names it.  The caller uses this value to require both the recorded
    extracted root and the expected BioIntel role in the command line.
    """
    if pid <= 0:
        return ""
    if os.name == "nt":
        command = (
            "$p=Get-CimInstance Win32_Process -Filter 'ProcessId = "
            f"{int(pid)}' -ErrorAction SilentlyContinue; "
            "if($p){[Console]::Out.Write($p.CommandLine)}"
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=4,
            )
            return completed.stdout.strip() if completed.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def _matches_recorded_biointel_process(role: str, command_line: str, recorded_root: str) -> bool:
    """Confirm that a PID is the old BioIntel role before a handover stops it."""
    if not command_line or not recorded_root:
        return False
    command = _normalise_command_value(command_line)
    root_marker = _normalise_command_value(recorded_root).rstrip("/")
    if not root_marker or root_marker not in command:
        return False
    required_tokens = {
        "ui": ("streamlit", "app.py"),
        "api": ("uvicorn", "biointel.api.main"),
        "worker": ("background_job_worker.py",),
    }.get(role, ())
    return bool(required_tokens) and all(token in command for token in required_tokens)


def _terminate_pid(pid: int) -> bool:
    """Terminate a process tree only after ownership verification."""
    if not _pid_alive(pid):
        return True
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=12,
            )
            return completed.returncode == 0 or not _pid_alive(pid)
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        import signal

        os.kill(pid, signal.SIGTERM)
    except OSError:
        return not _pid_alive(pid)
    return True


def _wait_ready(url: str, process: subprocess.Popen[bytes], seconds: int = 120) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        if _url_ready(url):
            return True
        time.sleep(0.7)
    return False


def _tail(path: Path, lines: int = 80) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(text[-lines:])
    except OSError:
        return "(log unavailable)"



def _rotate_logs(directory: Path, *, max_files: int = 24, max_total_bytes: int = 128 * 1024 * 1024) -> None:
    """Bound detached UI/API logs without touching diagnostic error reports."""

    candidates: list[Path] = []
    for pattern in ("step*-api-*.log", "step*-ui-*.log", "biointel-api-*.log", "biointel-ui-*.log"):
        candidates.extend(directory.glob(pattern))
    unique = sorted(set(candidates), key=lambda item: item.stat().st_mtime_ns if item.exists() else 0, reverse=True)
    retained = 0
    for index, path in enumerate(unique):
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if index >= max_files or retained + size > max_total_bytes:
            path.unlink(missing_ok=True)
        else:
            retained += size


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _record_runtime_reconciliation(runtime_dir: Path, payload: dict[str, object]) -> None:
    """Keep a compact local audit of automatic runtime cleanup decisions."""
    try:
        runtime_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(runtime_dir / "biointel-runtime-reconciliation-latest.json", payload)
    except OSError:
        # Launch safety must not depend on diagnostic-report persistence.
        pass


def _reconcile_existing_runtime_state(
    *,
    root: Path,
    state_path: Path,
    state: dict[str, object],
    runtime_dir: Path,
    pid_alive: Callable[[int], bool] = _pid_alive,
    command_line_for_pid: Callable[[int], str] = _command_line_for_pid,
    terminate_pid: Callable[[int], bool] = _terminate_pid,
    url_ready: Callable[[str], bool] = _url_ready,
) -> dict[str, object]:
    """Resolve a shared runtime record without false cross-release blocking.

    A Windows user can have V13 and V14 extracted in different folders while
    both intentionally share ``%LOCALAPPDATA%\\BioIntelAI\\UserData``.  Earlier
    launchers treated any live PID in that shared record as a hard error.  This
    routine instead:

    * reuses a healthy current-release session;
    * hands off a verified older BioIntel UI/API/worker to the new release;
    * discards an unverified or stale record without ever terminating an
      unrelated process; and
    * never changes project data, reports, workspaces, exports or databases.
    """
    recorded_root = str(state.get("app_root", "")).strip()
    same_release = _same_release(root, recorded_root)
    active = {
        field.removesuffix("_pid"): _state_pid(state, field)
        for field in _RUNTIME_PID_FIELDS
    }
    active = {role: pid for role, pid in active.items() if pid_alive(pid)}
    ui_url = str(state.get("ui_url", "")).strip()
    api_url = str(state.get("api_url", "")).strip()
    if (
        same_release
        and active.get("ui")
        and active.get("api")
        and url_ready(ui_url)
        and url_ready(api_url)
    ):
        payload = {
            "schema": "biointel.runtime-reconciliation.v1",
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "outcome": "already-running-current-release",
            "recorded_root": recorded_root,
            "active_roles": sorted(active),
            "project_data_changed": False,
        }
        _record_runtime_reconciliation(runtime_dir, payload)
        return {**payload, "outcome": "already-running", "ui_url": ui_url}

    verified: dict[str, int] = {}
    unverified: dict[str, int] = {}
    for role, pid in active.items():
        if _matches_recorded_biointel_process(role, command_line_for_pid(pid), recorded_root):
            verified[role] = pid
        else:
            unverified[role] = pid

    # Ask a verified old worker to finish its current polling cycle before the
    # new release starts a replacement.  This is a runtime-only sentinel and
    # the next worker clears it on startup.
    if "worker" in verified:
        try:
            (runtime_dir / "background-worker.stop").write_text(
                datetime.now(timezone.utc).isoformat() + "\n", encoding="utf-8"
            )
        except OSError:
            pass
        graceful_deadline = time.monotonic() + 3.0
        while pid_alive(verified["worker"]) and time.monotonic() < graceful_deadline:
            time.sleep(0.2)

    terminated: dict[str, bool] = {}
    # UI/API first prevents new browser/API traffic.  The worker has already
    # received a short graceful stop window. ``taskkill /T`` is used only after
    # command-line ownership verification above.
    for role in ("ui", "api", "worker"):
        pid = verified.get(role)
        if pid:
            terminated[role] = bool(terminate_pid(pid))

    deadline = time.monotonic() + 8.0
    while verified and any(pid_alive(pid) for pid in verified.values()) and time.monotonic() < deadline:
        time.sleep(0.2)
    remaining_verified = {role: pid for role, pid in verified.items() if pid_alive(pid)}
    if remaining_verified:
        message = (
            "A verified older BioIntel runtime could not be stopped automatically. "
            "Close the old BioIntel window or run it with the same Windows user, then launch again."
        )
        _record_runtime_reconciliation(
            runtime_dir,
            {
                "schema": "biointel.runtime-reconciliation.v1",
                "at_utc": datetime.now(timezone.utc).isoformat(),
                "outcome": "handover-blocked-live-verified-process",
                "recorded_root": recorded_root,
                "remaining_verified_roles": sorted(remaining_verified),
                "project_data_changed": False,
            },
        )
        raise RuntimeError(message)

    # A mismatched command line indicates a stale/reused PID.  Do not kill it;
    # just remove the stale record so a valid new release can choose free ports.
    state_path.unlink(missing_ok=True)
    outcome = (
        "handed-off-verified-release" if verified else "discarded-stale-or-unverified-runtime-record"
    )
    payload = {
        "schema": "biointel.runtime-reconciliation.v1",
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "outcome": outcome,
        "recorded_root": recorded_root,
        "same_release": same_release,
        "verified_roles": sorted(verified),
        "unverified_roles": sorted(unverified),
        "terminated": terminated,
        "project_data_changed": False,
    }
    _record_runtime_reconciliation(runtime_dir, payload)
    return payload


def _write_startup_failure(runtime_dir: Path, exc: BaseException) -> Path | None:
    """Save a short local diagnostic without exposing a traceback in the console."""
    try:
        runtime_dir.mkdir(parents=True, exist_ok=True)
        path = runtime_dir / f"biointel-startup-failure-{datetime.now():%Y%m%d-%H%M%S}.log"
        path.write_text(
            "BioIntel AI startup failure\n"
            f"Time (UTC): {datetime.now(timezone.utc).isoformat()}\n"
            f"Type: {type(exc).__name__}\n"
            f"Reason: {exc}\n",
            encoding="utf-8",
            errors="replace",
        )
        return path
    except OSError:
        return None

def _creation_flags() -> int:
    if os.name != "nt":
        return 0
    flags = 0
    for name in ("CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS", "CREATE_NO_WINDOW"):
        flags |= int(getattr(subprocess, name, 0))
    return flags


def run() -> int:
    root = APP_ROOT.resolve()
    if sys.version_info[:2] != (3, 11) or struct.calcsize("P") * 8 != 64:
        current = ".".join(str(part) for part in sys.version_info[:3])
        raise RuntimeError(
            "BioIntel AI requires CPython 3.11.x x64. "
            f"The active environment uses Python {current}. Run INSTALL_WINDOWS.bat to rebuild it."
        )
    local = _local_app_data()
    user_data = local / "BioIntelAI" / "UserData"
    runtime_dir = user_data / "runtime_logs"
    runtime_temp = local / "BioIntelAI" / "Temp" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime_temp.mkdir(parents=True, exist_ok=True)
    cache_root = user_data / "cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    _rotate_logs(runtime_dir)
    worker_threads = str(max(1, min(4, (os.cpu_count() or 2) // 2 or 1)))

    env = os.environ.copy()
    env.update(
        {
            "BIOINTEL_USER_DATA_DIR": str(user_data),
            "BIOINTEL_TOOLS_HOME": str(local / "BioIntelAI" / "Tools"),
            "BIOINTEL_REFERENCE_ASSETS_DIR": str(local / "BioIntelAI" / "ReferenceAssets"),
            "BIOINTEL_RUNTIME_TEMP": str(runtime_temp),
            "TEMP": str(runtime_temp),
            "TMP": str(runtime_temp),
            "MPLCONFIGDIR": str(user_data / "cache" / "matplotlib"),
            "PYTHONPATH": str(root / "src"),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
            "PYTHONPYCACHEPREFIX": str(cache_root / "pycache"),
            "JOBLIB_TEMP_FOLDER": str(cache_root / "joblib"),
            "TOKENIZERS_PARALLELISM": "false",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "OMP_NUM_THREADS": worker_threads,
            "OPENBLAS_NUM_THREADS": worker_threads,
            "MKL_NUM_THREADS": worker_threads,
            "NUMEXPR_MAX_THREADS": worker_threads,
            "VECLIB_MAXIMUM_THREADS": worker_threads,
            "OMP_WAIT_POLICY": "PASSIVE",
            "KMP_BLOCKTIME": "0",
        }
    )

    python = root / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        raise RuntimeError("The BioIntel AI environment is missing. Run INSTALL_WINDOWS.bat first.")

    state_path = runtime_dir / "biointel-running.json"
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            state = {}
        if not isinstance(state, dict):
            state = {}
        reconciliation = _reconcile_existing_runtime_state(
            root=root,
            state_path=state_path,
            state=state,
            runtime_dir=runtime_dir,
        )
        if reconciliation.get("outcome") == "already-running":
            print("BioIntel AI is already running. Opening the existing session...", flush=True)
            webbrowser.open(str(reconciliation.get("ui_url", "")))
            return 0
        if reconciliation.get("outcome") == "handed-off-verified-release":
            print("[BioIntel] Previous extracted release handed off safely.", flush=True)

    print("[1/5] Running startup preflight...", flush=True)
    preflight_log = runtime_dir / "biointel-runtime-preflight.log"
    preflight_json = runtime_dir / "biointel-runtime-preflight.json"
    with preflight_log.open("w", encoding="utf-8", errors="replace") as log:
        result = subprocess.run(
            [
                str(python),
                "scripts/step196_runtime_preflight.py",
                "--root",
                ".",
                "--output",
                str(preflight_json),
            ],
            cwd=str(root),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    if result.returncode != 0:
        print(_tail(preflight_log), flush=True)
        raise RuntimeError("BioIntel AI startup preflight failed. Run INSTALL_WINDOWS.bat again.")

    print("[2/5] Starting persistent background worker...", flush=True)
    os.environ.update(env)
    if str(root / "src") not in sys.path:
        sys.path.insert(0, str(root / "src"))
    from biointel.step101.background import BackgroundJobService

    worker_service = BackgroundJobService(root, python_executable=python)
    worker_state = worker_service.start()

    ui_port = _free_port(8501, 8599)
    api_port = _free_port(8000, 8099)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    api_log_path = runtime_dir / f"biointel-api-{stamp}.log"
    ui_log_path = runtime_dir / f"biointel-ui-{stamp}.log"

    print(f"[3/5] Starting API on 127.0.0.1:{api_port}...", flush=True)
    api_log = api_log_path.open("ab", buffering=0)
    api = subprocess.Popen(
        [
            str(python),
            "-m",
            "uvicorn",
            "biointel.api.main:app",
            "--app-dir",
            "src",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
        ],
        cwd=str(root),
        env=env,
        stdout=api_log,
        stderr=subprocess.STDOUT,
        creationflags=_creation_flags(),
    )

    print(f"[4/5] Starting UI on 127.0.0.1:{ui_port}...", flush=True)
    ui_log = ui_log_path.open("ab", buffering=0)
    ui = subprocess.Popen(
        [
            str(python),
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.address",
            "127.0.0.1",
            "--server.port",
            str(ui_port),
            "--server.fileWatcherType",
            "none",
            "--server.runOnSave",
            "false",
            "--browser.gatherUsageStats",
            "false",
            "--server.headless",
            "true",
        ],
        cwd=str(root),
        env=env,
        stdout=ui_log,
        stderr=subprocess.STDOUT,
        creationflags=_creation_flags(),
    )

    api_url = f"http://127.0.0.1:{api_port}/openapi.json"
    ui_health = f"http://127.0.0.1:{ui_port}/_stcore/health"
    ui_url = f"http://127.0.0.1:{ui_port}"

    print("[5/5] Waiting for UI, API and worker readiness...", flush=True)
    api_ready = _wait_ready(api_url, api)
    ui_ready = _wait_ready(ui_health, ui)
    api_log.close()
    ui_log.close()

    if not (api_ready and ui_ready):
        for process in (api, ui):
            try:
                process.terminate()
            except OSError:
                pass
        print("--- API log ---", flush=True)
        print(_tail(api_log_path), flush=True)
        print("--- UI log ---", flush=True)
        print(_tail(ui_log_path), flush=True)
        raise RuntimeError("UI or API did not become ready. The browser was not opened.")

    state = {
        "schema": "biointel.runtime-state.v4",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app_root": str(root),
        "ui_pid": ui.pid,
        "api_pid": api.pid,
        "ui_port": ui_port,
        "api_port": api_port,
        "ui_url": ui_url,
        "api_url": api_url,
        "ui_log": str(ui_log_path),
        "api_log": str(api_log_path),
        "worker_pid": worker_state.pid,
        "worker_id": worker_state.worker_id,
        "worker_log": worker_state.log_path,
    }
    _atomic_write_json(state_path, state)

    print("", flush=True)
    print("BioIntel AI is ready.", flush=True)
    print(f"UI:  {ui_url}", flush=True)
    print(f"API: http://127.0.0.1:{api_port}/docs", flush=True)
    webbrowser.open(ui_url)
    return 0


def self_check() -> int:
    root = APP_ROOT.resolve()
    port = _free_port(58600, 58650)
    payload = {
        "script": str(Path(__file__).resolve()),
        "root": str(root),
        "root_exists": root.is_dir(),
        "free_port_probe": port,
        "python_syntax": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["root_exists"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        return self_check()
    try:
        return run()
    except Exception as exc:
        runtime_dir = _local_app_data() / "BioIntelAI" / "UserData" / "runtime_logs"
        diagnostic = _write_startup_failure(runtime_dir, exc)
        print("", flush=True)
        print("BIOINTEL AI COULD NOT START", flush=True)
        print(str(exc), flush=True)
        print("No project data was changed.", flush=True)
        if diagnostic is not None:
            print(f"Diagnostic log: {diagnostic}", flush=True)
        print("Run INSTALL_WINDOWS.bat to repair the qualified local environment.", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
