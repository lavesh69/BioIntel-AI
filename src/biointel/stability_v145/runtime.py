from __future__ import annotations

from biointel.runtime_paths import runtime_report_path

import os
import platform
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from biointel.stability_v145.cache import BoundedTTLCache
from biointel.utils.path_safety import normalize_path_environment, resolve_path_argument


_STARTUP_PREFLIGHT_CACHE: BoundedTTLCache[tuple[object, ...], dict[str, Any]] = BoundedTTLCache(
    name="step145-startup-preflight", max_entries=16, max_bytes=4 * 1024 * 1024, ttl_seconds=30.0
)


@dataclass(frozen=True)
class RuntimeCheck:
    key: str
    status: str
    message: str
    detail: dict[str, Any]


def _physical_memory_bytes() -> int | None:
    if sys.platform.startswith("linux"):
        try:
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            return None
    if os.name == "nt":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys)
        except Exception:
            return None
    return None


def apply_process_hardening(root: str | Path) -> dict[str, str]:
    """Apply conservative process defaults once; existing user overrides win."""
    project_root = resolve_path_argument(root)
    repaired_paths = normalize_path_environment(
        (
            "BIOINTEL_PROJECT_ROOT",
            "BIOINTEL_USER_DATA_DIR",
            "BIOINTEL_REFERENCE_ASSETS_DIR",
            "BIOINTEL_TOOLS_HOME",
            "BIOINTEL_SHORT_TEMP",
        )
    )
    # The running package location is authoritative; never retain a malformed
    # project-root value inherited from a previous launcher.
    os.environ["BIOINTEL_PROJECT_ROOT"] = str(project_root)
    defaults = {
        "BIOINTEL_OPTIMIZED_RUNTIME": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "OMP_NUM_THREADS": str(max(1, min(4, (os.cpu_count() or 2) // 2 or 1))),
        "OPENBLAS_NUM_THREADS": str(max(1, min(4, (os.cpu_count() or 2) // 2 or 1))),
        "MKL_NUM_THREADS": str(max(1, min(4, (os.cpu_count() or 2) // 2 or 1))),
        "NUMEXPR_MAX_THREADS": str(max(1, min(4, (os.cpu_count() or 2) // 2 or 1))),
        "TOKENIZERS_PARALLELISM": "false",
        "BIOINTEL_PROJECT_ROOT": str(project_root),
    }
    applied: dict[str, str] = dict(repaired_paths)
    applied["BIOINTEL_PROJECT_ROOT"] = str(project_root)
    for key, value in defaults.items():
        if key == "BIOINTEL_PROJECT_ROOT":
            continue
        if key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    return applied


def _writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".biointel-write-{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _cleanup_stale_temp(root: Path, *, older_than_hours: int = 0, max_remove: int = 500) -> dict[str, int]:
    candidates = [root / "UserData" / "workspace" / "tmp", runtime_report_path(root, "tmp"), root / "tmp"]
    cutoff = datetime.now(UTC) - timedelta(hours=max(0, int(older_than_hours)))
    removed_files = 0

    removed_bytes = 0
    for base in candidates:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if removed_files >= max_remove or not path.is_file():
                continue
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


def startup_preflight(
    root: str | Path,
    *,
    minimum_free_bytes: int = 2 * 1024**3,
    recommended_free_bytes: int = 8 * 1024**3,
    clean_stale_temp: bool = True,
    use_cache: bool = True,
) -> dict[str, Any]:
    project_root = resolve_path_argument(root)
    cache_key = (str(project_root), int(minimum_free_bytes), int(recommended_free_bytes), bool(clean_stale_temp))
    if use_cache:
        cached = _STARTUP_PREFLIGHT_CACHE.get(cache_key)
        if cached is not None:
            return dict(cached)
    apply_process_hardening(project_root)
    user_data = resolve_path_argument(
        os.environ.get("BIOINTEL_USER_DATA_DIR"),
        default=project_root / "UserData",
    )
    report_dir = user_data / "runtime_logs"
    workspace = user_data / "workspace"
    checks: list[RuntimeCheck] = []

    version_ok = sys.version_info >= (3, 11)
    checks.append(RuntimeCheck("python", "pass" if version_ok else "fail", sys.version.split()[0], {"executable": sys.executable}))
    for key, path in (("project_root", project_root), ("user_data", user_data), ("workspace", workspace), ("runtime_logs", report_dir)):
        writable = _writable_directory(path)
        if writable:
            status = "pass"
        elif key == "project_root" and _writable_directory(user_data):
            status = "warn"
        else:
            status = "fail"
        checks.append(RuntimeCheck(key, status, "Writable" if writable else "Read-only", {"path": str(path)}))

    try:
        disk = shutil.disk_usage(user_data if user_data.exists() else project_root)
        if disk.free < minimum_free_bytes:
            disk_status = "fail"
        elif disk.free < recommended_free_bytes:
            disk_status = "warn"
        else:
            disk_status = "pass"
        checks.append(RuntimeCheck("disk", disk_status, f"{disk.free / 1024**3:.2f} GB free", {"free_bytes": disk.free, "total_bytes": disk.total}))
    except OSError as exc:
        checks.append(RuntimeCheck("disk", "fail", str(exc), {}))

    memory = _physical_memory_bytes()
    if memory is None:
        checks.append(RuntimeCheck("memory", "warn", "Physical memory could not be detected", {}))
    else:
        status = "pass" if memory >= 8 * 1024**3 else "warn" if memory >= 4 * 1024**3 else "fail"
        checks.append(RuntimeCheck("memory", status, f"{memory / 1024**3:.1f} GB physical memory", {"total_bytes": memory}))

    version_file = project_root / "VERSION"
    checks.append(RuntimeCheck("version_file", "pass" if version_file.is_file() else "fail", version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "Missing VERSION", {"path": str(version_file)}))
    temp_cleanup = _cleanup_stale_temp(project_root) if clean_stale_temp else {"removed_files": 0, "removed_bytes": 0}
    failures = [asdict(item) for item in checks if item.status == "fail"]
    warnings = [asdict(item) for item in checks if item.status == "warn"]
    result = {
        "schema": "biointel.startup-preflight.v145",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "root": str(project_root),
        "user_data": str(user_data),
        "platform": platform.platform(),
        "python": sys.version,
        "checks": [asdict(item) for item in checks],
        "failures": failures,
        "warnings": warnings,
        "temp_cleanup": temp_cleanup,
        "passed": not failures,
    }
    if use_cache:
        _STARTUP_PREFLIGHT_CACHE.set(cache_key, result)
    return dict(result)
