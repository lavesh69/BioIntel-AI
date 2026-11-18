from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _memory_bytes() -> int:
    try:
        import psutil
        return int(psutil.virtual_memory().total)
    except Exception:
        pass
    if hasattr(os, "sysconf"):
        try:
            pages = int(os.sysconf("SC_PHYS_PAGES"))
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            return pages * page_size
        except (ValueError, OSError):
            pass
    return 0


def _gpu_inventory() -> list[dict[str, Any]]:
    executable = shutil.which("nvidia-smi") or shutil.which("nvidia-smi.exe")
    if not executable:
        return []
    try:
        completed = subprocess.run(
            [executable, "--query-gpu=name,memory.total,driver_version,compute_cap", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode:
        return []
    rows = []
    for index, line in enumerate(completed.stdout.splitlines()):
        values = [value.strip() for value in line.split(",")]
        rows.append({
            "index": index,
            "name": values[0] if values else "NVIDIA GPU",
            "memory_mb": int(float(values[1])) if len(values) > 1 and values[1] else 0,
            "driver_version": values[2] if len(values) > 2 else "",
            "compute_capability": values[3] if len(values) > 3 else "",
        })
    return rows


def hardware_inventory(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path or Path.cwd()).resolve()
    usage = shutil.disk_usage(target)
    wsl = shutil.which("wsl") or shutil.which("wsl.exe")
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": int(os.cpu_count() or 1),
        "memory_bytes": _memory_bytes(),
        "disk_total_bytes": int(usage.total),
        "disk_free_bytes": int(usage.free),
        "wsl_available": bool(wsl),
        "wsl_executable": wsl or "",
        "docker_available": bool(shutil.which("docker") or shutil.which("docker.exe")),
        "micromamba_available": bool(shutil.which("micromamba") or shutil.which("micromamba.exe")),
        "gpus": _gpu_inventory(),
    }


def hardware_fit(*, minimum_ram_gb: float = 0, minimum_free_disk_gb: float = 0, gpu_required: bool = False, wsl_required: bool = False, path: str | Path | None = None) -> dict[str, Any]:
    inventory = hardware_inventory(path)
    failures: list[str] = []
    if inventory["memory_bytes"] < int(minimum_ram_gb * 1024**3):
        failures.append(f"Requires at least {minimum_ram_gb:g} GB RAM")
    if inventory["disk_free_bytes"] < int(minimum_free_disk_gb * 1024**3):
        failures.append(f"Requires at least {minimum_free_disk_gb:g} GB free disk")
    if gpu_required and not inventory["gpus"]:
        failures.append("Qualified NVIDIA GPU is required")
    if wsl_required and not inventory["wsl_available"]:
        failures.append("WSL2 is required")
    return {"passed": not failures, "failures": failures, "inventory": inventory}
