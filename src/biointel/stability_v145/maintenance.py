from __future__ import annotations

from biointel.runtime_paths import runtime_report_path

import gc
import json
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from biointel.database.core import clear_database_health_cache
from biointel.intelligence.data_intelligence import clear_database_fleet_cache
from biointel.stability_v145.cache import cache_registry_snapshot, clear_registered_caches
from biointel.stability_v145.database import maintain_database_fleet
from biointel.stability_v145.errors import ErrorStore
from biointel.stability_v145.jobs import recover_orphaned_job_queues
from biointel.stability_v145.runtime import startup_preflight
from biointel.utils.atomic_io import atomic_write_json
from biointel.utils.runtime_cache import clear_runtime_caches


def _prune_files(base: Path, *, patterns: tuple[str, ...], older_than_days: int, max_files: int) -> dict[str, int]:
    if not base.is_dir():
        return {"removed_files": 0, "removed_bytes": 0}
    cutoff = datetime.now(UTC) - timedelta(days=max(1, int(older_than_days)))
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(path for path in base.rglob(pattern) if path.is_file())
    removed_files = 0
    removed_bytes = 0
    for path in sorted(set(candidates), key=lambda item: item.stat().st_mtime_ns if item.exists() else 0):
        if removed_files >= max_files:
            break
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            size = path.stat().st_size
        except OSError:
            continue
        if modified >= cutoff:
            continue
        try:
            path.unlink()
        except OSError:
            continue
        removed_files += 1
        removed_bytes += size
    return {"removed_files": removed_files, "removed_bytes": removed_bytes}


def run_overall_maintenance(
    root: str | Path,
    *,
    database_maintenance: bool = True,
    recover_jobs: bool = True,
    clear_caches: bool = True,
    prune_old_logs: bool = True,
) -> dict[str, Any]:
    project_root = Path(root).resolve()
    started = datetime.now(UTC)
    before = startup_preflight(project_root, clean_stale_temp=False, use_cache=False)
    report: dict[str, Any] = {
        "schema": "biointel.overall-maintenance.v145", "started_at_utc": started.isoformat(),
        "root": str(project_root), "before": before,
    }
    if database_maintenance:
        report["databases"] = maintain_database_fleet(project_root)
    if recover_jobs:
        report["jobs"] = recover_orphaned_job_queues(project_root)
    if clear_caches:
        report["cache_snapshot_before"] = cache_registry_snapshot()
        report["registered_caches_cleared"] = clear_registered_caches()
        clear_runtime_caches(); clear_database_health_cache(); clear_database_fleet_cache()
    if prune_old_logs:
        user_data = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or (project_root / "UserData")).resolve()
        report["old_runtime_logs"] = _prune_files(user_data / "runtime_logs", patterns=("*.json", "*.log"), older_than_days=30, max_files=500)
        report["old_staged_temp"] = _prune_files(user_data / "workspace", patterns=("*.tmp", "*.partial", "*.part"), older_than_days=7, max_files=500)
        report["error_store_rotation"] = ErrorStore(user_data / "runtime_logs").rotate()
    report["garbage_collected"] = int(gc.collect())
    report["after"] = startup_preflight(project_root, clean_stale_temp=True, use_cache=False)
    report["completed_at_utc"] = datetime.now(UTC).isoformat()
    report["duration_seconds"] = round((datetime.now(UTC) - started).total_seconds(), 3)
    report["passed"] = bool(report["after"]["passed"]) and bool(report.get("databases", {"passed": True}).get("passed", True)) and bool(report.get("jobs", {"passed": True}).get("passed", True))
    output = runtime_report_path(project_root, "step145_overall_maintenance_latest.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output, report, indent=2, sort_keys=False)
    return report
