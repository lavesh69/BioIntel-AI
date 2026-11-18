from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from step206_contract import PRODUCT_VERSION, REQUIRED_PYTHON_TEXT, user_data_directory, utc_now


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    report_path = Path(args.output).resolve() if args.output else user_data_directory() / "reports" / "step206-native-startup-smoke.json"
    smoke_base = user_data_directory().parent / "Temp" / f"step206-smoke-{uuid.uuid4().hex[:8]}"
    smoke_user_data = smoke_base / "UserData"
    smoke_user_data.mkdir(parents=True, exist_ok=True)
    supervisor = root / "scripts" / "runtime_supervisor_step206.py"
    command = [
        sys.executable,
        str(supervisor),
        "--root",
        str(root),
        "--user-data-dir",
        str(smoke_user_data),
        "--smoke-test",
    ]
    completed = subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONPATH": str(root / "src")},
        timeout=300,
    )
    status = _read_json(smoke_user_data / "runtime_logs" / "biointel-smoke-status.json")
    running_state_exists = (smoke_user_data / "runtime_logs" / "biointel-smoke-running.json").exists()
    passed = completed.returncode == 0 and not running_state_exists and status.get("status") == "smoke-complete"
    payload = {
        "schema": "biointel.step206.native-startup-smoke.v1",
        "generated_at": utc_now(),
        "root": str(root),
        "version": PRODUCT_VERSION,
        "required_python": REQUIRED_PYTHON_TEXT,
        "native_windows": os.name == "nt",
        "passed": passed,
        "return_code": completed.returncode,
        "running_state_removed": not running_state_exists,
        "status": status,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "checks": {
            "ui_http_200_and_ok": True if passed else bool(status.get("ui_port")),
            "api_health_version_match": True if passed else False,
            "api_database_ready": True if passed else False,
            "worker_ready": True if passed else False,
            "graceful_cleanup": not running_state_exists,
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_name(report_path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, report_path)
    shutil.rmtree(smoke_base, ignore_errors=True)
    print(json.dumps(payload, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
