from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import sqlite3
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from step206_contract import PRODUCT_VERSION, REQUIRED_PYTHON, REQUIRED_PYTHON_TEXT, user_data_directory

APP_ROOT = Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            query = 0x1000
            synchronize = 0x00100000
            wait_timeout = 0x00000102
            access_denied = 5
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel32.WaitForSingleObject.restype = wintypes.DWORD
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            handle = kernel32.OpenProcess(query | synchronize, False, int(pid))
            if not handle:
                return ctypes.get_last_error() == access_denied
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


def _free_port(start: int, end: int) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free localhost port is available between {start} and {end}.")


def _json_response(url: str, *, timeout: float = 2.0) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    try:
        context = (ssl._create_unverified_context() if os.environ.get("BIOINTEL_ALLOW_INSECURE_TLS_PROBE", "").strip().lower() in {"1", "true", "yes"} else ssl.create_default_context()) if url.lower().startswith("https://") else None
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            status = int(response.status)
            body = response.read(2 * 1024 * 1024)
    except (OSError, urllib.error.URLError, ValueError):
        return 0, {}
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return status, {}
    return status, payload if isinstance(payload, dict) else {}


def _text_response(url: str, *, timeout: float = 2.0) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    try:
        context = (ssl._create_unverified_context() if os.environ.get("BIOINTEL_ALLOW_INSECURE_TLS_PROBE", "").strip().lower() in {"1", "true", "yes"} else ssl.create_default_context()) if url.lower().startswith("https://") else None
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return int(response.status), response.read(4096).decode("utf-8", errors="replace").strip()
    except (OSError, urllib.error.URLError, ValueError):
        return 0, ""


def _api_ready(url: str) -> bool:
    status, payload = _json_response(url)
    return status == 200 and payload.get("status") == "ok" and payload.get("version") == PRODUCT_VERSION


def _local_database_ready(path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(path, timeout=5) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS runtime_probe (probe_key TEXT PRIMARY KEY, checked_at TEXT NOT NULL)")
            connection.execute(
                "INSERT OR REPLACE INTO runtime_probe(probe_key, checked_at) VALUES (?, ?)",
                ("step206", _now()),
            )
            value = connection.execute(
                "SELECT checked_at FROM runtime_probe WHERE probe_key = ?", ("step206",)
            ).fetchone()
            connection.commit()
        return bool(value and value[0])
    except (OSError, sqlite3.Error):
        return False


def _ui_ready(url: str) -> bool:
    status, body = _text_response(url)
    return status == 200 and body.casefold() == "ok"


def _creation_flags() -> int:
    if os.name != "nt":
        return 0
    flags = 0
    for name in ("CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS", "CREATE_NO_WINDOW"):
        flags |= int(getattr(subprocess, name, 0))
    return flags


def _terminate_process(process: subprocess.Popen[bytes] | None, *, timeout: int = 12) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=timeout)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                capture_output=True,
                timeout=15,
                creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            process.kill()
        except OSError:
            pass


def _tail(path: Path, lines: int = 80) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(content[-lines:])


class RuntimeSupervisor:
    def __init__(self, root: Path, *, user_data: Path, smoke_test: bool = False) -> None:
        self.root = root.resolve()
        self.user_data = user_data.resolve()
        self.smoke_test = smoke_test
        self.safe_mode = os.environ.get("BIOINTEL_SAFE_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
        self.runtime_logs = self.user_data / "runtime_logs"
        self.runtime_temp = self.user_data.parent / "Temp" / ("smoke-runtime" if smoke_test else "runtime")
        self.runtime_logs.mkdir(parents=True, exist_ok=True)
        self.runtime_temp.mkdir(parents=True, exist_ok=True)
        self.state_path = self.runtime_logs / ("biointel-smoke-running.json" if smoke_test else "biointel-running.json")
        self.status_path = self.runtime_logs / ("biointel-smoke-status.json" if smoke_test else "biointel-runtime-status.json")
        self.stop_path = self.runtime_logs / ("biointel-smoke-stop.request" if smoke_test else "biointel-stop.request")
        self.supervisor_log = self.runtime_logs / ("biointel-smoke-supervisor.log" if smoke_test else "biointel-supervisor.log")
        self.python = self.root / ".venv" / "Scripts" / "python.exe"
        self.ui: subprocess.Popen[bytes] | None = None
        self.api: subprocess.Popen[bytes] | None = None
        self.worker_service: Any = None
        self.worker_state: Any = None
        self.ui_log_handle: Any = None
        self.api_log_handle: Any = None
        self.ui_log_path: Path | None = None
        self.api_log_path: Path | None = None
        self.ui_port = 0
        self.api_port = 0
        self.restart_history: dict[str, deque[float]] = defaultdict(deque)
        self.health_failures: dict[str, int] = defaultdict(int)
        self.started_at = _now()
        self.database_probe_path = self.user_data / "runtime" / "runtime-readiness.sqlite3"
        self.last_collaboration_backup_monotonic = 0.0
        self.live_workspace_config = self._load_live_workspace_config()
        self.collaboration_host = bool(
            not self.safe_mode
            and self.live_workspace_config.get("enabled")
            and self.live_workspace_config.get("bind_lan", self.live_workspace_config.get("enabled"))
            and not self.smoke_test
        )
        self.ui_bind_host = "0.0.0.0" if self.collaboration_host else "127.0.0.1"
        self.api_bind_host = (
            "0.0.0.0"
            if self.collaboration_host and bool(self.live_workspace_config.get("api_lan_enabled", False))
            else "127.0.0.1"
        )
        self.https_enabled = bool(self.collaboration_host and self.live_workspace_config.get("https_enabled", False))
        self.tls_cert_file = Path(str(self.live_workspace_config.get("tls_cert_file", ""))).expanduser() if self.https_enabled else None
        self.tls_key_file = Path(str(self.live_workspace_config.get("tls_key_file", ""))).expanduser() if self.https_enabled else None

    def _load_live_workspace_config(self) -> dict[str, Any]:
        path = self.user_data / "workspace" / "live_workspace" / "host_config.json"
        defaults = {
            "enabled": False,
            "bind_lan": False,
            "require_ui_auth": True,
            "api_lan_enabled": False,
            "allow_lan_only": True,
            "max_active_users": 25,
            "backup_retention": 20,
            "backup_interval_hours": 12,
            "https_enabled": False,
            "tls_cert_file": "",
            "tls_key_file": "",
        }
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return defaults
        return {**defaults, **payload} if isinstance(payload, dict) else defaults

    @staticmethod
    def _private_ipv4_addresses() -> list[str]:
        addresses: set[str] = set()
        try:
            hostname = socket.gethostname()
            for item in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
                address = str(item[4][0])
                if address and not address.startswith("127.") and not address.startswith("169.254."):
                    addresses.add(address)
        except OSError:
            pass
        return sorted(addresses)

    def _write_lan_access_file(self) -> None:
        path = self.user_data.parent / "OPEN_BIOINTEL_LAN_URLS.txt"
        if not self.collaboration_host:
            path.unlink(missing_ok=True)
            return
        lines = [
            "BioIntel Live Workspace - trusted LAN access",
            "",
            *[f"{'https' if self.https_enabled else 'http'}://{address}:{self.ui_port}" for address in self._private_ipv4_addresses()],
            "",
            "Use only on a trusted private network. Public internet port-forwarding is not supported.",
        ]
        temporary = path.with_suffix(".tmp")
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(temporary, path)

    def log(self, message: str) -> None:
        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}"
        print(line, flush=True)
        with self.supervisor_log.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(line + "\n")

    def environment(self) -> dict[str, str]:
        cache_root = self.user_data / "cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        threads = str(max(1, min(4, (os.cpu_count() or 2) // 2 or 1)))
        env = os.environ.copy()
        if self.smoke_test:
            env["BIOINTEL_RUNTIME_SMOKE_TEST"] = "1"
        if self.collaboration_host:
            env["BIOINTEL_COLLABORATION_HOST"] = "1"
            if bool(self.live_workspace_config.get("require_ui_auth", True)):
                env["BIOINTEL_UI_AUTH_REQUIRED"] = "1"
        env.update(
            {
                "BIOINTEL_USER_DATA_DIR": str(self.user_data),
                "BIOINTEL_TOOLS_HOME": str(self.user_data.parent / "Tools"),
                "BIOINTEL_REFERENCE_ASSETS_DIR": str(self.user_data.parent / "ReferenceAssets"),
                "BIOINTEL_RUNTIME_TEMP": str(self.runtime_temp),
                "TEMP": str(self.runtime_temp),
                "TMP": str(self.runtime_temp),
                "MPLCONFIGDIR": str(cache_root / "matplotlib"),
                "NUMBA_CACHE_DIR": str(cache_root / "numba"),
                "PYTHONPATH": str(self.root / "src"),
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
                "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
                "PYTHONPYCACHEPREFIX": str(cache_root / "pycache"),
                "JOBLIB_TEMP_FOLDER": str(cache_root / "joblib"),
                "TOKENIZERS_PARALLELISM": "false",
                "HF_HUB_DISABLE_TELEMETRY": "1",
                "OMP_NUM_THREADS": threads,
                "OPENBLAS_NUM_THREADS": threads,
                "MKL_NUM_THREADS": threads,
                "NUMEXPR_MAX_THREADS": threads,
                "VECLIB_MAXIMUM_THREADS": threads,
                "OMP_WAIT_POLICY": "PASSIVE",
                "KMP_BLOCKTIME": "0",
            }
        )
        return env

    def validate(self) -> None:
        if sys.version_info[:2] != REQUIRED_PYTHON or struct.calcsize("P") * 8 != 64:
            current = ".".join(str(part) for part in sys.version_info[:3])
            raise RuntimeError(f"{REQUIRED_PYTHON_TEXT} is required; supervisor is using Python {current}.")
        if not self.python.is_file():
            raise RuntimeError("The managed BioIntel Python environment is missing. Run INSTALL_WINDOWS.bat.")
        if self.collaboration_host and bool(self.live_workspace_config.get("require_ui_auth", True)):
            source = str(self.root / "src")
            if source not in sys.path:
                sys.path.insert(0, source)
            from biointel.security.ui_user_store import configured_ui_users

            if not configured_ui_users():
                raise RuntimeError(
                    "Live Workspace LAN Host Mode requires at least one enabled UI account. "
                    "Open BioIntel locally, create an account in Live Workspace > Admin, then enable host mode."
                )
        if self.api_bind_host == "0.0.0.0" and not os.environ.get("BIOINTEL_API_KEY", "").strip():
            raise RuntimeError("LAN API exposure requires BIOINTEL_API_KEY. Keep API LAN disabled for normal team use.")
        if self.https_enabled:
            if not self.tls_cert_file or not self.tls_cert_file.is_file():
                raise RuntimeError("Live Workspace HTTPS certificate file is missing.")
            if not self.tls_key_file or not self.tls_key_file.is_file():
                raise RuntimeError("Live Workspace HTTPS private-key file is missing.")
        for required in (self.root / "app.py", self.root / "src" / "biointel" / "api" / "main.py"):
            if not required.is_file():
                raise RuntimeError(f"Managed application file is missing: {required.name}")

    def _open_logs(self) -> None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        prefix = "biointel-smoke" if self.smoke_test else "biointel"
        self.api_log_path = self.runtime_logs / f"{prefix}-api-{stamp}.log"
        self.ui_log_path = self.runtime_logs / f"{prefix}-ui-{stamp}.log"
        self.api_log_handle = self.api_log_path.open("ab", buffering=0)
        self.ui_log_handle = self.ui_log_path.open("ab", buffering=0)

    def _close_logs(self) -> None:
        for handle_name in ("api_log_handle", "ui_log_handle"):
            handle = getattr(self, handle_name, None)
            if handle is not None:
                try:
                    handle.close()
                except OSError:
                    pass
                setattr(self, handle_name, None)

    def start_worker(self) -> None:
        os.environ.update(self.environment())
        source = str(self.root / "src")
        if source not in sys.path:
            sys.path.insert(0, source)
        from biointel.step101.background import BackgroundJobService

        self.worker_service = BackgroundJobService(self.root, python_executable=self.python)
        self.worker_state = self.worker_service.start()
        if not self.worker_state.running or not _pid_alive(int(self.worker_state.pid)):
            raise RuntimeError("Background worker did not become ready.")

    def start_api(self) -> None:
        if self.api_port <= 0:
            self.api_port = _free_port(8000, 8099)
        if self.api_log_handle is None:
            self._open_logs()
        api_command = [
            str(self.python),
            "-m",
            "uvicorn",
            "biointel.api.main:app",
            "--app-dir",
            "src",
            "--host",
            self.api_bind_host,
            "--port",
            str(self.api_port),
        ]
        if self.https_enabled and self.api_bind_host == "0.0.0.0":
            api_command.extend(["--ssl-certfile", str(self.tls_cert_file), "--ssl-keyfile", str(self.tls_key_file)])
        self.api = subprocess.Popen(
            api_command,
            cwd=str(self.root),
            env=self.environment(),
            stdin=subprocess.DEVNULL,
            stdout=self.api_log_handle,
            stderr=subprocess.STDOUT,
            creationflags=_creation_flags(),
        )

    def start_ui(self) -> None:
        if self.ui_port <= 0:
            self.ui_port = _free_port(8501, 8599)
        if self.ui_log_handle is None:
            self._open_logs()
        ui_command = [
            str(self.python),
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.address",
            self.ui_bind_host,
            "--server.port",
            str(self.ui_port),
            "--server.fileWatcherType",
            "none",
            "--server.runOnSave",
            "false",
            "--browser.gatherUsageStats",
            "false",
            "--server.headless",
            "true",
        ]
        if self.safe_mode:
            ui_command.extend(["--server.maxUploadSize", "100", "--server.maxMessageSize", "100"])
        if self.https_enabled:
            ui_command.extend(["--server.sslCertFile", str(self.tls_cert_file), "--server.sslKeyFile", str(self.tls_key_file)])
        self.ui = subprocess.Popen(
            ui_command,
            cwd=str(self.root),
            env=self.environment(),
            stdin=subprocess.DEVNULL,
            stdout=self.ui_log_handle,
            stderr=subprocess.STDOUT,
            creationflags=_creation_flags(),
        )

    @property
    def ui_url(self) -> str:
        return f"{'https' if self.https_enabled else 'http'}://127.0.0.1:{self.ui_port}"

    @property
    def api_uses_https(self) -> bool:
        # The API receives the TLS flags only when it is explicitly exposed on LAN.
        # In the normal secure configuration the API stays localhost-only over HTTP
        # while the Streamlit UI may use HTTPS for team access.
        return bool(self.https_enabled and self.api_bind_host == "0.0.0.0")

    @property
    def api_health_url(self) -> str:
        scheme = "https" if self.api_uses_https else "http"
        return f"{scheme}://127.0.0.1:{self.api_port}/health"

    @property
    def api_ready_url(self) -> str:
        scheme = "https" if self.api_uses_https else "http"
        return f"{scheme}://127.0.0.1:{self.api_port}/ready"

    @property
    def ui_health_url(self) -> str:
        scheme = "https" if self.https_enabled else "http"
        return f"{scheme}://127.0.0.1:{self.ui_port}/_stcore/health"

    def state(self, status: str, *, message: str = "") -> dict[str, Any]:
        return {
            "schema": "biointel.runtime-state.v5",
            "status": status,
            "message": message,
            "generated_at": _now(),
            "started_at": self.started_at,
            "app_root": str(self.root),
            "release_version": PRODUCT_VERSION,
            "supervisor_pid": os.getpid(),
            "ui_pid": self.ui.pid if self.ui is not None and self.ui.poll() is None else 0,
            "api_pid": self.api.pid if self.api is not None and self.api.poll() is None else 0,
            "worker_pid": int(getattr(self.worker_state, "pid", 0) or 0),
            "ui_port": self.ui_port,
            "api_port": self.api_port,
            "ui_url": self.ui_url if self.ui_port else "",
            "api_url": f"http://127.0.0.1:{self.api_port}/docs" if self.api_port else "",
            "collaboration_host": self.collaboration_host,
            "ui_bind_host": self.ui_bind_host,
            "api_bind_host": self.api_bind_host,
            "lan_ui_urls": [f"{'https' if self.https_enabled else 'http'}://{address}:{self.ui_port}" for address in self._private_ipv4_addresses()] if self.collaboration_host and self.ui_port else [],
            "ui_log": str(self.ui_log_path or ""),
            "api_log": str(self.api_log_path or ""),
            "worker_log": str(getattr(self.worker_state, "log_path", "")),
            "supervisor_log": str(self.supervisor_log),
            "restart_counts": {role: len(rows) for role, rows in self.restart_history.items()},
            "smoke_test": self.smoke_test,
            "safe_mode": self.safe_mode,
        }

    def write_state(self, status: str, *, message: str = "") -> None:
        payload = self.state(status, message=message)
        _atomic_json(self.state_path, payload)
        _atomic_json(self.status_path, payload)

    def wait_ready(self, seconds: int = 150) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.api is None or self.api.poll() is not None:
                raise RuntimeError("FastAPI exited before readiness.")
            if self.ui is None or self.ui.poll() is not None:
                raise RuntimeError("Streamlit exited before readiness.")
            worker_running = bool(self.worker_service and self.worker_service.status().running)
            if _api_ready(self.api_health_url) and _local_database_ready(self.database_probe_path) and _ui_ready(self.ui_health_url) and worker_running:
                return
            time.sleep(0.7)
        detail = "\n--- API log ---\n" + _tail(self.api_log_path or Path())
        detail += "\n--- UI log ---\n" + _tail(self.ui_log_path or Path())
        raise RuntimeError("UI, API, local database, or worker readiness timed out." + detail[-6000:])

    def backup_live_workspace(self, *, force: bool = False) -> None:
        if self.smoke_test:
            return
        interval_seconds = min(max(int(self.live_workspace_config.get("backup_interval_hours", 12)), 1), 168) * 3600
        now = time.monotonic()
        if not force and now - self.last_collaboration_backup_monotonic < interval_seconds:
            return
        source = self.user_data / "workspace" / "live_workspace" / "live_workspace.sqlite3"
        backup_dir = self.user_data.parent / "Backups" / "LiveWorkspace"
        try:
            source_root = str(self.root / "src")
            if source_root not in sys.path:
                sys.path.insert(0, source_root)
            from biointel.live_workspace_v210.backup import create_live_workspace_snapshot

            result = create_live_workspace_snapshot(
                source,
                backup_dir,
                retention=int(self.live_workspace_config.get("backup_retention", 20)),
            )
            if result:
                self.log(f"Live Workspace automatic backup verified: {result['archive_file']}")
        except Exception as exc:
            self.log(f"Live Workspace automatic backup warning: {type(exc).__name__}: {exc}")
        finally:
            self.last_collaboration_backup_monotonic = now

    def start_all(self) -> None:
        self.stop_path.unlink(missing_ok=True)
        self.write_state("starting", message="Starting API, UI, and background worker.")
        try:
            self.start_worker()
            self.start_api()
            self.start_ui()
            self.wait_ready()
        except Exception:
            self.cleanup()
            raise
        self.write_state("ready", message="BioIntel AI is ready.")
        self._write_lan_access_file()
        self.backup_live_workspace(force=True)
        self.log(f"BioIntel AI ready: UI={self.ui_url}, API={self.api_health_url}")
        if self.collaboration_host:
            self.log("Live Workspace LAN URLs: " + ", ".join(f"{'https' if self.https_enabled else 'http'}://{address}:{self.ui_port}" for address in self._private_ipv4_addresses()))

    def _record_restart(self, role: str) -> None:
        now = time.monotonic()
        history = self.restart_history[role]
        history.append(now)
        while history and now - history[0] > 600:
            history.popleft()
        if len(history) > 3:
            raise RuntimeError(f"{role} entered a restart loop. Automatic restart was stopped after 3 attempts in 10 minutes.")

    def restart_role(self, role: str) -> None:
        self._record_restart(role)
        self.log(f"Restarting {role} after a process or health failure.")
        if role == "api":
            _terminate_process(self.api)
            self.api = None
            self.api_port = 0
            self.start_api()
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if self.api.poll() is not None:
                    break
                if _api_ready(self.api_health_url) and _local_database_ready(self.database_probe_path):
                    self.health_failures[role] = 0
                    return
                time.sleep(0.7)
        elif role == "ui":
            _terminate_process(self.ui)
            self.ui = None
            self.ui_port = 0
            self.start_ui()
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if self.ui.poll() is not None:
                    break
                if _ui_ready(self.ui_health_url):
                    self.health_failures[role] = 0
                    return
                time.sleep(0.7)
        elif role == "worker":
            if self.worker_service is not None:
                self.worker_service.stop(timeout_seconds=10)
                self.worker_state = self.worker_service.start()
                if self.worker_state.running:
                    self.health_failures[role] = 0
                    return
        raise RuntimeError(f"{role} could not recover after restart.")

    def monitor(self) -> None:
        last_health = 0.0
        while True:
            if self.stop_path.exists():
                self.log("Graceful stop requested.")
                return
            if self.api is None or self.api.poll() is not None:
                self.restart_role("api")
            if self.ui is None or self.ui.poll() is not None:
                self.restart_role("ui")
            if not (self.worker_service and self.worker_service.status().running):
                self.restart_role("worker")

            now = time.monotonic()
            self.backup_live_workspace()
            if now - last_health >= 10:
                last_health = now
                health = {
                    "api": _api_ready(self.api_health_url),
                    "database": _local_database_ready(self.database_probe_path),
                    "ui": _ui_ready(self.ui_health_url),
                    "worker": bool(self.worker_service and self.worker_service.status().running),
                }
                for role, ready in health.items():
                    self.health_failures[role] = 0 if ready else self.health_failures[role] + 1
                    if self.health_failures[role] >= 3:
                        if role == "database":
                            raise RuntimeError("Local SQLite readiness probe failed repeatedly.")
                        self.restart_role(role)
                self.write_state("ready", message="BioIntel AI is healthy.")
            time.sleep(1.5)

    def cleanup(self) -> None:
        _terminate_process(self.ui)
        _terminate_process(self.api)
        if self.worker_service is not None:
            try:
                self.worker_service.stop(timeout_seconds=15)
            except Exception as exc:
                self.log(f"Worker cleanup warning: {exc}")
        self._close_logs()
        self.stop_path.unlink(missing_ok=True)

    def run(self) -> int:
        self.validate()
        try:
            self.start_all()
            if self.smoke_test:
                self.write_state("passed", message="Native startup smoke test passed.")
                return 0
            self.monitor()
            self.write_state("stopping", message="Graceful shutdown in progress.")
            return 0
        except Exception as exc:
            self.log(f"Runtime failure: {type(exc).__name__}: {exc}")
            try:
                self.write_state("failed", message=str(exc))
            except OSError:
                pass
            return 1
        finally:
            self.cleanup()
            final = self.state("stopped" if not self.smoke_test else "smoke-complete")
            try:
                _atomic_json(self.status_path, final)
                self.state_path.unlink(missing_ok=True)
            except OSError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(APP_ROOT))
    parser.add_argument("--user-data-dir")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    user_data = Path(args.user_data_dir).resolve() if args.user_data_dir else user_data_directory()
    if args.self_check:
        payload = {
            "script": str(Path(__file__).resolve()),
            "root": str(root),
            "root_exists": root.is_dir(),
            "required_python": REQUIRED_PYTHON_TEXT,
            "free_ui_port": _free_port(58600, 58650),
            "free_api_port": _free_port(58651, 58700),
            "strict_api_health": True,
            "strict_ui_health": True,
            "worker_readiness": True,
            "failure_cleanup": True,
            "restart_budget": "3 per role per 10 minutes",
        }
        print(json.dumps(payload, indent=2))
        return 0 if payload["root_exists"] else 1
    return RuntimeSupervisor(root, user_data=user_data, smoke_test=args.smoke_test).run()


if __name__ == "__main__":
    raise SystemExit(main())
