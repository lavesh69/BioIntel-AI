from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from biointel.database.core import connect
from biointel.engineering.runtime_optimizer import discover_databases
from biointel.jobs.local_queue import LocalJobQueue


def _has_local_jobs(path: Path) -> bool:
    try:
        with connect(path, read_only=True) as connection:
            row = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='local_jobs'").fetchone()
            return row is not None
    except sqlite3.Error:
        return False


def recover_orphaned_job_queues(root: str | Path, *, stale_after_seconds: int = 300) -> dict[str, Any]:
    project_root = Path(root).resolve()
    results: list[dict[str, Any]] = []
    for path in discover_databases(project_root):
        if not _has_local_jobs(path):
            continue
        try:
            result = LocalJobQueue(path).recover_orphaned_jobs(stale_after_seconds=stale_after_seconds)
            try:
                display = path.relative_to(project_root).as_posix()
            except ValueError:
                display = str(path)
            results.append({"path": display, **result, "passed": True})
        except (OSError, sqlite3.Error, ValueError) as exc:
            results.append({"path": str(path), "recovered": 0, "passed": False, "error": str(exc)})
    return {
        "queue_count": len(results), "recovered_jobs": sum(int(row.get("recovered", 0)) for row in results),
        "failed_queues": sum(not bool(row.get("passed")) for row in results), "results": results,
        "passed": all(bool(row.get("passed")) for row in results),
    }
