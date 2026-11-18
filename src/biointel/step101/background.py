from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from biointel.jobs.local_queue import LocalJobQueue


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _windows_pid_alive(pid: int) -> bool:
    """Return process liveness without calling os.kill(pid, 0) on Windows.

    CPython's Windows os.kill implementation can raise SystemError/WinError 87 for
    stale or malformed PIDs. Querying a process handle is non-destructive and
    handles stale state files safely.
    """

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
            process_query_limited_information | synchronize, False, int(pid)
        )
        if not handle:
            # Access denied means a protected process exists; invalid/stale PIDs
            # normally report ERROR_INVALID_PARAMETER (87) and are not alive.
            return ctypes.get_last_error() == error_access_denied
        try:
            return int(kernel32.WaitForSingleObject(handle, 0)) == wait_timeout
        finally:
            kernel32.CloseHandle(handle)
    except (Exception, SystemError, ValueError):
        return False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
        return True
    except (OSError, SystemError, ValueError):
        return False


@dataclass(frozen=True)
class ServiceStatus:
    running: bool
    pid: int
    started_at_utc: str
    state_path: str
    log_path: str
    worker_id: str
    queue_summary: dict[str, Any]


class BackgroundJobService:
    """Manage a persistent local worker process independent of Streamlit reruns."""

    def __init__(self, project_root: str | Path, *, python_executable: str | Path | None = None) -> None:
        self.root = Path(project_root).resolve()
        self.user_data = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or self.root)
        self.runtime = self.user_data / "runtime_logs"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.queue = LocalJobQueue(runtime_database_path(self.root, "jobs.sqlite3"))
        self.state_path = self.runtime / "background-worker-state.json"
        self.stop_path = self.runtime / "background-worker.stop"
        self.log_path = self.runtime / "background-worker.log"
        self.python = Path(python_executable or sys.executable).resolve()

    def _read_state(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}

    def status(self) -> ServiceStatus:
        state = self._read_state()
        pid = int(state.get("pid", 0) or 0)
        running = _pid_alive(pid)
        if state and not running:
            self.queue.recover_orphaned_jobs(stale_after_seconds=30)
            # Remove stale worker identity so the next startup is never blocked by
            # an invalid Windows PID left behind after a crash or forced shutdown.
            self.state_path.unlink(missing_ok=True)
            state = {}
            pid = 0
        return ServiceStatus(
            running=running,
            pid=pid,
            started_at_utc=str(state.get("started_at_utc", "")),
            state_path=str(self.state_path),
            log_path=str(self.log_path),
            worker_id=str(state.get("worker_id", "background-worker")),
            queue_summary=self.queue.orchestration_summary(),
        )

    @staticmethod
    def _creation_flags() -> int:
        if os.name != "nt":
            return 0
        return int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) | int(
            getattr(subprocess, "DETACHED_PROCESS", 0)
        ) | int(getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def start(
        self,
        *,
        poll_seconds: float = 1.0,
        startup_timeout_seconds: float = 180.0,
    ) -> ServiceStatus:
        current = self.status()
        if current.running:
            return current
        self.stop_path.unlink(missing_ok=True)
        worker_id = f"background-{os.getpid()}-{int(time.time())}"
        log = self.log_path.open("ab", buffering=0)
        try:
            process = subprocess.Popen(
                [
                    str(self.python),
                    str(self.root / "scripts" / "background_job_worker.py"),
                    "--root",
                    str(self.root),
                    "--worker-id",
                    worker_id,
                    "--poll-seconds",
                    str(max(0.25, float(poll_seconds))),
                ],
                cwd=str(self.root),
                env={**os.environ, "PYTHONPATH": str(self.root / "src")},
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=self._creation_flags(),
                close_fds=os.name != "nt",
            )
        finally:
            log.close()
        payload = {
            "pid": process.pid,
            "worker_id": worker_id,
            "started_at_utc": _now(),
            "log_path": str(self.log_path),
            "root": str(self.root),
        }
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        deadline = time.monotonic() + max(10.0, float(startup_timeout_seconds))
        registered = False
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"Background worker exited with code {process.returncode}")
            if any(
                str(row.get("worker_id")) == worker_id
                and str(row.get("status")) == "online"
                for row in self.queue.workers()
            ):
                registered = True
                break
            time.sleep(0.25)
        if not registered:
            raise RuntimeError(
                "Background worker process started but did not become online in the local queue "
                f"within {max(10.0, float(startup_timeout_seconds)):g} seconds."
            )
        return self.status()

    def stop(self, *, timeout_seconds: int = 15) -> ServiceStatus:
        state = self._read_state()
        pid = int(state.get("pid", 0) or 0)
        self.stop_path.write_text(_now() + "\n", encoding="utf-8")
        deadline = time.monotonic() + max(1, int(timeout_seconds))
        while _pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.25)
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        self.state_path.unlink(missing_ok=True)
        self.queue.recover_orphaned_jobs(stale_after_seconds=30)
        return self.status()

    def restart(self) -> ServiceStatus:
        self.stop()
        return self.start()

    def recover(self) -> dict[str, int]:
        return self.queue.recover_orphaned_jobs(stale_after_seconds=60)
