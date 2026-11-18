from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.stability_v145.jobs import recover_orphaned_job_queues
from biointel.stability_v145.runtime import startup_preflight
from biointel.utils.atomic_io import atomic_write_json
from biointel.utils.path_safety import (
    normalize_path_environment,
    path_debug_payload,
    resolve_path_argument,
    sanitize_path_text,
)


def _fallback_report_directories(root: Path) -> list[Path]:
    candidates = [root / "reports"]
    configured = sanitize_path_text(os.environ.get("BIOINTEL_USER_DATA_DIR"))
    if configured:
        candidates.append(Path(configured).expanduser() / "runtime_reports")
    local = sanitize_path_text(os.environ.get("LOCALAPPDATA"))
    if local:
        candidates.append(Path(local).expanduser() / "BioIntelAI" / "runtime_reports")
    candidates.append(Path(tempfile.gettempdir()) / "BioIntelAI" / "runtime_reports")

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(os.fspath(candidate)))
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def write_preflight_report(root: Path, payload: dict[str, Any]) -> Path:
    errors: list[dict[str, str]] = []
    for directory in _fallback_report_directories(root):
        output = directory / "step145_runtime_preflight.json"
        try:
            atomic_write_json(output, payload, indent=2, sort_keys=False)
            if errors:
                payload.setdefault("report_write_warnings", errors)
                atomic_write_json(output, payload, indent=2, sort_keys=False)
            return output.resolve()
        except (OSError, ValueError) as exc:
            errors.append({"path": str(output), "error": str(exc)})
    raise OSError("Unable to write the startup preflight report to any safe location")


def _failure_payload(root: Path, raw_root: str, exc: BaseException) -> dict[str, Any]:
    return {
        "schema": "biointel.startup-preflight.v150",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "root": str(root),
        "path_normalization": path_debug_payload(raw_root, root),
        "repaired_path_environment": {},
        "checks": [],
        "warnings": [],
        "failures": [
            {
                "key": "preflight_exception",
                "status": "fail",
                "message": f"{type(exc).__name__}: {exc}",
                "detail": {},
            }
        ],
        "passed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--no-recover-jobs", action="store_true")
    args = parser.parse_args()
    raw_root = str(args.root)
    repaired_environment = normalize_path_environment(
        (
            "BIOINTEL_PROJECT_ROOT",
            "BIOINTEL_USER_DATA_DIR",
            "LOCALAPPDATA",
            "TEMP",
            "TMP",
        )
    )

    try:
        root = resolve_path_argument(raw_root, default=ROOT, base=Path.cwd())
    except (OSError, ValueError) as exc:
        root = ROOT
        payload = _failure_payload(root, raw_root, exc)
    else:
        try:
            payload = startup_preflight(root, use_cache=False)
            payload["schema"] = "biointel.startup-preflight.v150"
            payload["path_normalization"] = path_debug_payload(raw_root, root)
            payload["repaired_path_environment"] = repaired_environment
            if not args.no_recover_jobs:
                payload["job_recovery"] = recover_orphaned_job_queues(
                    root, stale_after_seconds=300
                )
        except BaseException as exc:  # preflight must report rather than crash
            payload = _failure_payload(root, raw_root, exc)

    try:
        output = write_preflight_report(root, payload)
        payload["report_path"] = str(output)
        # Rewrite once so the report contains its own final location.
        atomic_write_json(output, payload, indent=2, sort_keys=False)
    except (OSError, ValueError) as exc:
        print(json.dumps(payload, indent=2, default=str))
        print(f"REPORT_WRITE_FAILED={type(exc).__name__}: {exc}")
        return 3

    print(json.dumps(payload, indent=2, default=str))
    print(f"REPORT_PATH={output}")
    return 0 if payload.get("passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
