from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import platform
import shutil
import sqlite3
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from .execution import DependencyManager
from .models import PlatformValidationError, new_id, optional_text, require_text, utc_now
from .storage import DiscoveryPlatformStore


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.dwLength = ctypes.sizeof(self)


def _filetime_value(value: Any) -> int:
    return (int(value.dwHighDateTime) << 32) + int(value.dwLowDateTime)


def cpu_percent(sample_seconds: float = 0.1) -> float | None:
    if os.name != "nt":
        try:
            load = os.getloadavg()[0]
            return float(min(100.0, max(0.0, load / max(1, os.cpu_count() or 1) * 100)))
        except (AttributeError, OSError):
            return None
    first_idle = wintypes.FILETIME()
    first_kernel = wintypes.FILETIME()
    first_user = wintypes.FILETIME()
    second_idle = wintypes.FILETIME()
    second_kernel = wintypes.FILETIME()
    second_user = wintypes.FILETIME()
    get_times = ctypes.windll.kernel32.GetSystemTimes
    if not get_times(
        ctypes.byref(first_idle), ctypes.byref(first_kernel), ctypes.byref(first_user)
    ):
        return None
    time.sleep(max(0.02, min(float(sample_seconds), 1.0)))
    if not get_times(
        ctypes.byref(second_idle), ctypes.byref(second_kernel), ctypes.byref(second_user)
    ):
        return None
    idle = _filetime_value(second_idle) - _filetime_value(first_idle)
    total = (
        _filetime_value(second_kernel) - _filetime_value(first_kernel)
        + _filetime_value(second_user) - _filetime_value(first_user)
    )
    return float(max(0.0, min(100.0, (1 - idle / total) * 100))) if total > 0 else None


def memory_snapshot() -> dict[str, Any]:
    if os.name == "nt":
        status = _MemoryStatusEx()
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            used = int(status.ullTotalPhys - status.ullAvailPhys)
            return {
                "total_bytes": int(status.ullTotalPhys),
                "available_bytes": int(status.ullAvailPhys),
                "used_bytes": used,
                "used_percent": float(status.dwMemoryLoad),
            }
    return {
        "total_bytes": None,
        "available_bytes": None,
        "used_bytes": None,
        "used_percent": None,
    }


def gpu_snapshot() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"available": False, "devices": [], "detail": "nvidia-smi not found"}
    try:
        result = subprocess.run(
            [
                executable,
                "--query-gpu=name,memory.total,memory.used,utilization.gpu,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "devices": [], "detail": str(exc)}
    devices = []
    if result.returncode == 0:
        for index, line in enumerate(result.stdout.splitlines()):
            values = [value.strip() for value in line.split(",")]
            if len(values) >= 5:
                devices.append(
                    {
                        "index": index,
                        "name": values[0],
                        "memory_total_mb": float(values[1]),
                        "memory_used_mb": float(values[2]),
                        "utilization_percent": float(values[3]),
                        "driver_version": values[4],
                    }
                )
    return {
        "available": bool(devices),
        "devices": devices,
        "detail": (result.stderr or "").strip()[:500],
    }


def folder_size(root: str | Path, *, maximum_files: int = 200_000) -> dict[str, Any]:
    base = Path(root).resolve()
    if not base.exists():
        return {"path": str(base), "bytes": 0, "files": 0, "truncated": False}
    total = 0
    files = 0
    truncated = False
    for directory, names, filenames in os.walk(base, followlinks=False):
        names[:] = [
            name for name in names
            if not (Path(directory) / name).is_symlink()
        ]
        for filename in filenames:
            path = Path(directory) / filename
            if path.is_symlink():
                continue
            try:
                total += path.stat().st_size
            except OSError:
                continue
            files += 1
            if files >= maximum_files:
                truncated = True
                break
        if truncated:
            break
    return {"path": str(base), "bytes": total, "files": files, "truncated": truncated}


class SystemHealthService:
    def __init__(
        self,
        store: DiscoveryPlatformStore,
        *,
        cache_roots: Sequence[str | Path] = (),
        log_roots: Sequence[str | Path] = (),
        temp_roots: Sequence[str | Path] = (),
    ):
        self.store = store
        self.cache_roots = tuple(Path(path).resolve() for path in cache_roots)
        self.log_roots = tuple(Path(path).resolve() for path in log_roots)
        self.temp_roots = tuple(Path(path).resolve() for path in temp_roots)
        self.dependencies = DependencyManager(store)

    def snapshot(self) -> dict[str, Any]:
        disk = shutil.disk_usage(self.store.database_path.parent)
        with self.store.connect(read_only=True) as connection:
            jobs = {
                str(row["status"]): int(row["count"])
                for row in connection.execute(
                    "SELECT status,COUNT(*) AS count FROM jobs GROUP BY status"
                )
            }
            project_storage = {
                str(row["project_id"]): int(row["bytes"] or 0)
                for row in connection.execute(
                    "SELECT project_id,SUM(size_bytes) AS bytes FROM artifacts GROUP BY project_id"
                )
            }
        cache = [folder_size(path) for path in self.cache_roots]
        logs = [folder_size(path) for path in self.log_roots]
        temporary = [folder_size(path) for path in self.temp_roots]
        return {
            "generated_at_utc": utc_now(),
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "python": platform.python_version(),
                "machine": platform.machine(),
            },
            "cpu": {
                "logical_processors": os.cpu_count() or 1,
                "utilization_percent": cpu_percent(),
            },
            "memory": memory_snapshot(),
            "gpu": gpu_snapshot(),
            "disk": {
                "path": str(self.store.database_path.parent),
                "total_bytes": disk.total,
                "used_bytes": disk.used,
                "free_bytes": disk.free,
                "free_percent": float(disk.free / max(1, disk.total) * 100),
                "low_space_warning": disk.free < 5 * 1024**3 or disk.free / max(1, disk.total) < 0.1,
            },
            "database": {
                **self.store.integrity(),
                "size_bytes": self.store.database_path.stat().st_size
                if self.store.database_path.exists() else 0,
            },
            "artifact_storage": folder_size(self.store.artifact_root),
            "project_storage_bytes": project_storage,
            "cache": cache,
            "logs": logs,
            "temporary_files": temporary,
            "jobs": {
                "running": jobs.get("Running", 0),
                "queued": jobs.get("Queued", 0),
                "failed": jobs.get("Failed", 0),
                "all_statuses": jobs,
            },
        }

    def dependency_health(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        if refresh:
            return self.dependencies.check_all()
        with self.store.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT checks.* FROM dependency_checks checks
                JOIN (
                    SELECT tool_name,MAX(rowid) AS latest_row
                    FROM dependency_checks GROUP BY tool_name
                ) latest ON latest.latest_row=checks.rowid
                ORDER BY checks.tool_name
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def estimate_run(
        self,
        *,
        module_id: str,
        input_bytes: int,
        rows: int | None = None,
        low_memory: bool = False,
    ) -> dict[str, Any]:
        if input_bytes < 0 or (rows is not None and rows < 0):
            raise PlatformValidationError("Input size and row count cannot be negative")
        multipliers = {
            "sequencing_quality": (1.2, 35.0),
            "alignment_mapping": (4.0, 120.0),
            "differential_expression": (3.0, 45.0),
            "biomarker_discovery": (5.0, 90.0),
            "variant_prioritization": (2.0, 40.0),
            "multi_omics": (6.0, 120.0),
            "single_cell": (8.0, 150.0),
            "proteomics": (4.0, 90.0),
            "metabolomics": (4.0, 90.0),
            "microbiome": (5.0, 120.0),
            "structural_biology": (2.0, 40.0),
        }
        memory_factor, seconds_per_gb = multipliers.get(module_id, (2.0, 30.0))
        input_gb = input_bytes / 1024**3
        memory = max(256 * 1024**2, int(input_bytes * memory_factor))
        runtime = max(1.0, input_gb * seconds_per_gb + (rows or 0) / 100_000)
        if low_memory:
            memory = max(128 * 1024**2, memory // 2)
            runtime *= 1.6
        return {
            "module_id": module_id,
            "input_bytes": int(input_bytes),
            "estimated_peak_memory_bytes": memory,
            "estimated_runtime_seconds": float(runtime),
            "low_memory_mode": bool(low_memory),
            "basis": "Conservative local heuristic; actual runtime depends on tool, storage, and data shape.",
        }

    def cleanup(
        self,
        root: str | Path,
        *,
        older_than_days: int = 7,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        target = Path(root).resolve()
        allowed = {
            *self.cache_roots,
            *self.temp_roots,
            (self.store.artifact_root / "temporary").resolve(),
        }
        if target not in allowed:
            raise PlatformValidationError("Cleanup is restricted to configured cache and temporary roots")
        if older_than_days < 0:
            raise PlatformValidationError("Cleanup age cannot be negative")
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        candidates = []
        reclaimed = 0
        if target.exists():
            for path in target.rglob("*"):
                if not path.is_file() or path.is_symlink():
                    continue
                try:
                    modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
                    size = path.stat().st_size
                except OSError:
                    continue
                if modified <= cutoff:
                    candidates.append(str(path))
                    reclaimed += size
                    if not dry_run:
                        path.unlink(missing_ok=True)
        self.store.audit(
            "storage_cleanup_preview" if dry_run else "storage_cleanup_completed",
            "storage", str(target),
            detail={"files": len(candidates), "bytes": reclaimed, "older_than_days": older_than_days},
        )
        return {
            "root": str(target),
            "dry_run": bool(dry_run),
            "files": len(candidates),
            "reclaimable_bytes": reclaimed,
            "paths": candidates[:1000],
            "paths_truncated": len(candidates) > 1000,
        }

    def backup_database(self, destination: str | Path) -> dict[str, Any]:
        return self.store.backup(destination)

    def validate_backup(self, source: str | Path) -> dict[str, Any]:
        path = Path(source).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            connection.close()
        return {
            "path": str(path),
            "quick_check": quick,
            "schema_version": version,
            "required_tables_present": {"projects", "datasets", "audit_events"}.issubset(tables),
            "valid": quick == "ok" and {"projects", "datasets", "audit_events"}.issubset(tables),
        }


class LabOperationsService:
    def __init__(
        self,
        store: DiscoveryPlatformStore,
        *,
        actor: str = "local_user",
        role: str = "Administrator",
    ):
        self.store = store
        self.actor = actor
        self.role = role

    def register_instrument(
        self,
        *,
        name: str,
        instrument_type: str,
        manufacturer: str = "",
        model: str = "",
        serial_number: str = "",
        location: str = "",
        status: str = "Available",
        owner: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status not in {"Available", "In Use", "Maintenance", "Offline", "Retired"}:
            raise PlatformValidationError("Unsupported instrument status")
        instrument_id = new_id("INST")
        now = utc_now()
        self.store.insert(
            "instruments",
            {
                "instrument_id": instrument_id,
                "name": require_text(name, "instrument name", 200),
                "instrument_type": require_text(instrument_type, "instrument type", 200),
                "manufacturer": optional_text(manufacturer, 200),
                "model": optional_text(model, 200),
                "serial_number": optional_text(serial_number, 200),
                "location": optional_text(location, 300),
                "status": status,
                "owner": optional_text(owner, 200),
                "metadata_json": dict(metadata or {}),
                "created_at_utc": now,
                "updated_at_utc": now,
            },
        )
        self.store.audit(
            "instrument_registered", "instrument", instrument_id,
            actor=self.actor, role=self.role,
            detail={"name": name, "status": status},
        )
        return self.store.row("instruments", "instrument_id", instrument_id) or {}

    def queue_snapshot(self) -> dict[str, Any]:
        with self.store.connect(read_only=True) as connection:
            jobs = [
                dict(row) for row in connection.execute(
                    """
                    SELECT job_id,project_id,job_type,priority,status,progress,
                           cancellation_requested,created_at_utc,updated_at_utc
                    FROM jobs ORDER BY
                        CASE status WHEN 'Failed' THEN 0 WHEN 'Running' THEN 1 ELSE 2 END,
                        priority DESC,created_at_utc
                    LIMIT 1000
                    """
                )
            ]
            projects = [
                dict(row) for row in connection.execute(
                    """
                    SELECT project_id,title,current_stage,owner,target_date,updated_at_utc
                    FROM projects WHERE current_stage NOT IN ('Completed','Archived')
                    ORDER BY target_date IS NULL,target_date,updated_at_utc DESC
                    LIMIT 1000
                    """
                )
            ]
            failed_runs = [
                dict(row) for row in connection.execute(
                    """
                    SELECT run_id,project_id,module_id,status,started_at_utc,errors_json
                    FROM runs WHERE status IN ('Failed','Partial','Timed out','Cancelled')
                    ORDER BY started_at_utc DESC LIMIT 200
                    """
                )
            ]
        return {
            "jobs": jobs,
            "projects": projects,
            "failed_runs": failed_runs,
            "instruments": self.store.rows(
                "instruments", order_by="updated_at_utc", limit=1000
            ),
            "generated_at_utc": utc_now(),
        }

    def retry_job(self, job_id: str) -> dict[str, Any]:
        job = self.store.row("jobs", "job_id", job_id)
        if job is None:
            raise KeyError(job_id)
        if job["status"] not in {"Failed", "Cancelled", "Paused"}:
            raise PlatformValidationError("Only failed, cancelled, or paused jobs can be re-queued")
        self.store.update(
            "jobs", "job_id", job_id,
            {
                "status": "Queued",
                "progress": 0.0,
                "cancellation_requested": 0,
                "error_json": {},
                "updated_at_utc": utc_now(),
            },
        )
        self.store.audit(
            "job_requeued", "job", job_id, project_id=job.get("project_id"),
            actor=self.actor, role=self.role,
            detail={"previous_status": job["status"]},
        )
        return self.store.row("jobs", "job_id", job_id) or {}


__all__ = [
    "LabOperationsService",
    "SystemHealthService",
    "cpu_percent",
    "folder_size",
    "gpu_snapshot",
    "memory_snapshot",
]
