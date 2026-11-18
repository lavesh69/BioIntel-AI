"""Safe inspection, graceful shutdown, and restart controls for BioIntel runtime."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

_STATE_NAMES = ("biointel-running.json", "step101-running.json")
_STATUS_STATE_NAME = "biointel-runtime-status.json"
_PUBLIC_PID_FIELDS = ("ui_pid", "api_pid", "worker_pid")
_ALL_PID_FIELDS = ("supervisor_pid",) + _PUBLIC_PID_FIELDS


def _windows_no_window_flags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0


def _state_paths(user_data: Path) -> tuple[Path, ...]:
    runtime = user_data / "runtime_logs"
    return tuple(runtime / name for name in _STATE_NAMES)


def _read_state(user_data: Path) -> tuple[Path | None, dict[str, Any]]:
    primary_path: Path | None = None
    for path in _state_paths(user_data):
        if not path.is_file():
            continue
        if primary_path is None:
            primary_path = path
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload:
            return path, payload

    # The supervisor maintains an atomic status snapshot separately from the
    # legacy running-state file. If the primary file was truncated or filled
    # with NUL bytes by an interrupted write, use this verified snapshot for
    # process ownership while retaining the primary path for safe cleanup.
    status_path = user_data / "runtime_logs" / _STATUS_STATE_NAME
    if status_path.is_file():
        try:
            payload = json.loads(status_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict) and payload:
            return primary_path or status_path, payload
    return primary_path, {}


def _valid_pid(value: Any) -> int:
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return 0
    return pid if pid > 0 else 0


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        # Query the process handle directly first. Some locked-down Windows
        # accounts deny tasklist/CIM even for the user's own child processes.
        try:
            import ctypes
            from ctypes import wintypes

            process_query_limited_information = 0x1000
            still_active = 259
            handle = ctypes.windll.kernel32.OpenProcess(
                process_query_limited_information, False, int(pid)
            )
            if handle:
                try:
                    exit_code = wintypes.DWORD()
                    if ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                        return exit_code.value == still_active
                finally:
                    ctypes.windll.kernel32.CloseHandle(handle)
        except (AttributeError, OSError, ValueError):
            pass
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


def _same_root(expected_root: Path, value: object) -> bool:
    try:
        return bool(value) and Path(str(value)).resolve() == expected_root.resolve()
    except (OSError, ValueError):
        return False


def _command_line_for_pid(pid: int) -> str:
    if pid <= 0:
        return ""
    if os.name == "nt":
        command = (
            "$p=Get-CimInstance Win32_Process -Filter 'ProcessId = "
            f"{int(pid)}' -ErrorAction SilentlyContinue;"
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
                timeout=5,
                creationflags=_windows_no_window_flags(),
            )
            return completed.stdout.strip() if completed.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def _normalise(value: object) -> str:
    return str(value).replace("\\", "/").casefold()


def _owned_process(role: str, pid: int, root: Path) -> bool:
    command = _normalise(_command_line_for_pid(pid))
    root_text = _normalise(root.resolve()).rstrip("/")
    if not command or root_text not in command:
        return False
    required = {
        "supervisor": ("runtime_supervisor_step206.py",),
        "ui": ("streamlit", "app.py"),
        "api": ("uvicorn", "biointel.api.main"),
        "worker": ("background_job_worker.py",),
    }.get(role, ())
    return bool(required) and all(token in command for token in required)


def inspect_local_runtime(root: str | Path, user_data: str | Path) -> dict[str, Any]:
    expected_root = Path(root).resolve()
    data_root = Path(user_data).expanduser().resolve()
    state_path, state = _read_state(data_root)
    if state_path is None:
        return {"state": "not-running", "reason": "No local runtime state file exists.", "processes": []}
    app_root = str(state.get("app_root", "")).strip()
    same_release = _same_root(expected_root, app_root)
    processes = []
    for field in _PUBLIC_PID_FIELDS:
        pid = _valid_pid(state.get(field, 0))
        processes.append({"role": field.removesuffix("_pid"), "pid": pid, "alive": _pid_alive(pid)})
    supervisor_pid = _valid_pid(state.get("supervisor_pid", 0))
    alive = [row for row in processes if row["alive"]]
    supervisor_alive = _pid_alive(supervisor_pid)
    running = bool(alive or supervisor_alive)
    return {
        "state": "running" if running and same_release else ("stale" if not running else "different-release"),
        "status": str(state.get("status", "")),
        "state_path": str(state_path),
        "app_root": app_root,
        "matches_current_release": same_release,
        "supervisor_pid": supervisor_pid,
        "supervisor_alive": supervisor_alive,
        "processes": processes,
        "ui_url": str(state.get("ui_url", "")),
    }


def _force_stop_verified(role: str, pid: int, root: Path) -> dict[str, Any]:
    if not _pid_alive(pid):
        return {"role": role, "pid": pid, "state": "already-stopped"}
    if not _owned_process(role, pid, root):
        return {
            "role": role,
            "pid": pid,
            "state": "refused-unverified-process",
            "detail": "PID command line did not match the recorded BioIntel root and role.",
        }
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                creationflags=_windows_no_window_flags(),
            )
            return {
                "role": role,
                "pid": pid,
                "state": "stopped" if completed.returncode == 0 or not _pid_alive(pid) else "stop-failed",
                "detail": (completed.stderr or completed.stdout).strip()[:500],
            }
        except (OSError, subprocess.SubprocessError) as exc:
            return {"role": role, "pid": pid, "state": "stop-failed", "detail": str(exc)}
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return {"role": role, "pid": pid, "state": "stop-failed", "detail": str(exc)}
    return {"role": role, "pid": pid, "state": "stopped"}


def stop_local_runtime(
    root: str | Path,
    user_data: str | Path,
    *,
    graceful_timeout_seconds: int = 25,
) -> dict[str, Any]:
    root_path = Path(root).resolve()
    data_root = Path(user_data).expanduser().resolve()
    state_path, state = _read_state(data_root)
    if state_path is None:
        return {"state": "not-running", "stopped": []}
    if not _same_root(root_path, state.get("app_root", "")):
        return {
            "state": "refused-different-release",
            "reason": "Runtime state does not belong to the requested BioIntel release.",
            "stopped": [],
        }

    stop_path = data_root / "runtime_logs" / "biointel-stop.request"
    try:
        stop_path.parent.mkdir(parents=True, exist_ok=True)
        stop_path.write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n", encoding="utf-8")
    except OSError as exc:
        return {"state": "stop-failed", "reason": f"Could not create graceful stop request: {exc}", "stopped": []}

    role_pids = {
        field.removesuffix("_pid"): _valid_pid(state.get(field, 0)) for field in _ALL_PID_FIELDS
    }
    # Do not spend the graceful timeout waiting on a PID that Windows has
    # already reused for an unrelated process. Command-line ownership is
    # checked before waiting and again before any force-stop decision.
    recorded_owned = {
        role: pid
        for role, pid in role_pids.items()
        if pid and _pid_alive(pid) and _owned_process(role, pid, root_path)
    }
    # A graceful stop request is safe even when Windows policy blocks command-line
    # inspection. Wait for every recorded live PID to observe the request; force
    # termination below remains restricted to independently verified ownership.
    recorded_alive = {
        role: pid for role, pid in role_pids.items() if pid and _pid_alive(pid)
    }
    deadline = time.monotonic() + max(1, int(graceful_timeout_seconds))
    while recorded_alive and time.monotonic() < deadline:
        if all(not _pid_alive(pid) for pid in recorded_alive.values()):
            break
        time.sleep(0.25)

    stopped = []
    # Supervisor owns normal child cleanup. Force it first only after graceful timeout,
    # then verify and clean any child that survived.
    order = ("supervisor", "ui", "api", "worker")
    for role in order:
        pid = role_pids.get(role, 0)
        if pid:
            stopped.append(_force_stop_verified(role, pid, root_path))

    # A PID recorded earlier may now belong to an unrelated Windows process.
    # Only a still-alive process whose command line matches both the recorded
    # BioIntel root and role may block activation. Unverified/reused PIDs are
    # never terminated and are treated as stale state.
    blocking_owned = {
        role: pid
        for role, pid in role_pids.items()
        if pid and _pid_alive(pid) and _owned_process(role, pid, root_path)
    }
    all_stopped = not blocking_owned
    if all_stopped:
        state_path.unlink(missing_ok=True)
        stop_path.unlink(missing_ok=True)
    return {
        "state": "stopped" if all_stopped else "stop-requested",
        "stopped": stopped,
        "recorded_owned_processes": recorded_owned,
        "blocking_owned_processes": blocking_owned,
        "state_path": str(state_path),
        "graceful_timeout_seconds": graceful_timeout_seconds,
    }
