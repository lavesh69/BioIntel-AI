from __future__ import annotations

from biointel.runtime_paths import runtime_report_path, runtime_reports_directory

import gc
import os
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from biointel.database.core import clear_database_health_cache, database_file_signature
from biointel.engineering.runtime_optimizer import discover_databases, optimize_database_fleet
from biointel.intelligence.data_intelligence import (
    all_database_health,
    clear_database_fleet_cache,
)
from biointel.utils.runtime_cache import clear_runtime_caches, runtime_cache_info

_CACHE_DIRECTORY_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
_RUNTIME_LOG_PATTERNS = ("step*-api-*.log", "step*-ui-*.log", "biointel-*.log")


@dataclass(frozen=True)
class RuntimeAudit:
    root: str
    database_count: int
    healthy_databases: int
    database_rows: int
    database_bytes: int
    wal_bytes: int
    cache_directories: int
    cache_bytes: int
    runtime_log_files: int
    runtime_log_bytes: int
    python_files: int
    process_threads_hint: int
    database_health_ms: float
    cache_info: dict[str, dict[str, int | None]]


def _directory_size(path: Path) -> int:
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    continue
    except OSError:
        return total
    return total


def _cache_directories(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_dir() and path.name in _CACHE_DIRECTORY_NAMES
    )


def _runtime_logs(root: Path) -> list[Path]:
    candidates: set[Path] = set()
    for base in (runtime_report_path(root, "runtime_logs"), runtime_reports_directory(root)):
        if not base.is_dir():
            continue
        for pattern in _RUNTIME_LOG_PATTERNS:
            candidates.update(path for path in base.glob(pattern) if path.is_file())
    return sorted(candidates)


def runtime_audit(root: str | Path) -> RuntimeAudit:
    project_root = Path(root).resolve()
    started = time.perf_counter()
    health = all_database_health(project_root)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    databases = discover_databases(project_root)
    wal_bytes = 0
    for database in databases:
        wal = Path(f"{database}-wal")
        try:
            wal_bytes += wal.stat().st_size
        except OSError:
            pass
    cache_dirs = _cache_directories(project_root)
    logs = _runtime_logs(project_root)
    return RuntimeAudit(
        root=str(project_root),
        database_count=int(health["database_count"]),
        healthy_databases=int(health["healthy_count"]),
        database_rows=int(health["total_rows"]),
        database_bytes=int(health["total_bytes"]),
        wal_bytes=wal_bytes,
        cache_directories=len(cache_dirs),
        cache_bytes=sum(_directory_size(path) for path in cache_dirs),
        runtime_log_files=len(logs),
        runtime_log_bytes=sum(path.stat().st_size for path in logs if path.exists()),
        python_files=sum(1 for _ in project_root.rglob("*.py")),
        process_threads_hint=max(1, min(4, (os.cpu_count() or 2) // 2 or 1)),
        database_health_ms=round(elapsed_ms, 3),
        cache_info=runtime_cache_info(),
    )


def prune_project_caches(root: str | Path) -> dict[str, int]:
    project_root = Path(root).resolve()
    removed_directories = 0
    removed_bytes = 0
    for path in _cache_directories(project_root):
        size = _directory_size(path)
        try:
            shutil.rmtree(path)
        except OSError:
            continue
        removed_directories += 1
        removed_bytes += size
    return {"removed_directories": removed_directories, "removed_bytes": removed_bytes}


def prune_runtime_logs(
    root: str | Path,
    *,
    keep_files: int = 24,
    keep_bytes: int = 128 * 1024 * 1024,
) -> dict[str, int]:
    project_root = Path(root).resolve()
    logs = sorted(
        _runtime_logs(project_root),
        key=lambda item: item.stat().st_mtime_ns if item.exists() else 0,
        reverse=True,
    )
    retained_bytes = 0
    removed_files = 0
    removed_bytes = 0
    for index, path in enumerate(logs):
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if index >= max(0, int(keep_files)) or retained_bytes + size > max(0, int(keep_bytes)):
            try:
                path.unlink()
            except OSError:
                continue
            removed_files += 1
            removed_bytes += size
        else:
            retained_bytes += size
    return {
        "removed_files": removed_files,
        "removed_bytes": removed_bytes,
        "retained_bytes": retained_bytes,
    }


def optimize_workspace(
    root: str | Path,
    *,
    optimize_databases: bool = True,
    prune_caches: bool = True,
    prune_logs: bool = True,
) -> dict[str, Any]:
    project_root = Path(root).resolve()
    before = runtime_audit(project_root)
    result: dict[str, Any] = {
        "schema": "biointel.step123.optimization.v1",
        "root": str(project_root),
        "before": asdict(before),
    }
    if optimize_databases:
        result["databases"] = optimize_database_fleet(project_root)
    if prune_caches:
        result["project_caches"] = prune_project_caches(project_root)
    if prune_logs:
        result["runtime_logs"] = prune_runtime_logs(project_root)

    clear_runtime_caches()
    clear_database_health_cache()
    clear_database_fleet_cache()
    result["garbage_collected"] = int(gc.collect())
    result["after"] = asdict(runtime_audit(project_root))
    result["passed"] = (
        int(result["after"]["database_count"])
        == int(result["after"]["healthy_databases"])
        and int(result["after"]["database_count"]) > 0
    )
    return result


def database_signatures(root: str | Path) -> dict[str, tuple[int, int, int, int, int, int]]:
    return {
        path.relative_to(Path(root).resolve()).as_posix(): database_file_signature(path)
        for path in discover_databases(root)
    }
