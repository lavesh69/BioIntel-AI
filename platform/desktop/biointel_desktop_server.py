from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path


def _free_port(start: int, end: int) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free local port in {start}-{end}.")


def _wait(url: str, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as response:
                if 200 <= int(response.status) < 300:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(0.4)
    raise RuntimeError(f"Local service did not become ready: {url}; {last_error}")


def _prepare(workspace: Path) -> None:
    app_path = workspace / "app.py"
    src = workspace / "src"
    if not app_path.is_file() or not src.is_dir():
        raise SystemExit("Packaged BioIntel workspace is incomplete.")
    os.chdir(workspace)
    sys.path.insert(0, str(src))
    os.environ.setdefault("BIOINTEL_ENVIRONMENT", "desktop")
    os.environ.setdefault("BIOINTEL_UI_AUTH_REQUIRED", "0")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("BIOINTEL_USER_DATA_DIR", str(workspace.parent / "UserData"))


def _run_api(workspace: Path, port: int) -> int:
    _prepare(workspace)
    from biointel.database.bootstrap import bootstrap_databases

    result = bootstrap_databases(workspace)
    if not result.passed:
        raise RuntimeError(f"Database bootstrap failed: {result.failures}")
    import uvicorn

    uvicorn.run(
        "biointel.api.main:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    return 0


def _run_worker(workspace: Path) -> int:
    _prepare(workspace)
    from biointel.jobs.worker import LocalWorker

    worker = LocalWorker(workspace, worker_id="desktop-background-worker")
    worker.queue.recover_orphaned_jobs(stale_after_seconds=60)
    while True:
        result = worker.run_once()
        if not result.processed:
            worker.queue.heartbeat(
                "desktop-background-worker",
                status="online",
                capabilities={"job_types": sorted(worker.handlers)},
                metadata={"service": "electron-desktop"},
            )
            time.sleep(0.75)


def _run_supervisor(workspace: Path, ui_port: int) -> int:
    _prepare(workspace)
    api_port = _free_port(8000, 8099)
    env = os.environ.copy()
    env["BIOINTEL_API_URL"] = f"http://127.0.0.1:{api_port}"
    executable = sys.executable
    api = subprocess.Popen(
        [executable, "--mode", "api", "--workspace", str(workspace), "--api-port", str(api_port)],
        cwd=str(workspace), env=env,
    )
    worker = subprocess.Popen(
        [executable, "--mode", "worker", "--workspace", str(workspace)],
        cwd=str(workspace), env=env,
    )
    try:
        _wait(f"http://127.0.0.1:{api_port}/ready")
        os.environ.update(env)
        sys.argv = [
            "streamlit", "run", str(workspace / "app.py"),
            "--server.headless=true",
            "--server.address=127.0.0.1",
            f"--server.port={ui_port}",
            "--server.enableXsrfProtection=true",
            "--server.enableCORS=true",
            "--server.fileWatcherType=none",
            "--browser.gatherUsageStats=false",
        ]
        from streamlit.web import cli as stcli
        return int(stcli.main() or 0)
    finally:
        for process in (worker, api):
            if process.poll() is None:
                process.terminate()
        for process in (worker, api):
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--api-port", type=int, default=0)
    parser.add_argument("--mode", choices=("supervisor", "api", "worker"), default="supervisor")
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    if args.mode == "api":
        return _run_api(workspace, args.api_port or _free_port(8000, 8099))
    if args.mode == "worker":
        return _run_worker(workspace)
    if not args.port:
        raise SystemExit("--port is required in supervisor mode")
    return _run_supervisor(workspace, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
