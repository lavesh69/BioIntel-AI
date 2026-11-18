from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import shutil
from typing import Any

import pandas as pd

_MIB = 1024 * 1024
_GIB = 1024 * _MIB


@dataclass(frozen=True)
class ResourceSnapshot:
    total_memory_bytes: int
    available_memory_bytes: int
    process_rss_bytes: int
    cpu_count: int
    disk_free_bytes: int
    source: str

    @property
    def memory_pressure(self) -> float:
        if self.total_memory_bytes <= 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - self.available_memory_bytes / self.total_memory_bytes))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["memory_pressure"] = self.memory_pressure
        return payload


@dataclass(frozen=True)
class AnalysisAdmission:
    requested_mode: str
    effective_mode: str
    allowed: bool
    estimated_input_bytes: int
    estimated_peak_bytes: int
    available_memory_bytes: int
    reserved_memory_bytes: int
    max_rows: int
    max_features: int
    downgraded: bool
    reason: str
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _fallback_memory() -> tuple[int, int]:
    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        total_pages = int(os.sysconf("SC_PHYS_PAGES"))
        available_pages = int(os.sysconf("SC_AVPHYS_PAGES"))
        return page_size * total_pages, page_size * available_pages
    except (AttributeError, OSError, ValueError):
        return 8 * _GIB, 4 * _GIB


def capture_resource_snapshot(root: str | Path | None = None) -> ResourceSnapshot:
    source = "portable-fallback"
    total, available = _fallback_memory()
    rss = 0
    try:
        import psutil  # type: ignore

        memory = psutil.virtual_memory()
        total = int(memory.total)
        available = int(memory.available)
        rss = int(psutil.Process().memory_info().rss)
        source = "psutil"
    except Exception:
        pass
    target = Path(root or Path.cwd()).expanduser().resolve()
    try:
        disk_free = int(shutil.disk_usage(target).free)
    except OSError:
        disk_free = 0
    return ResourceSnapshot(
        total_memory_bytes=max(0, total),
        available_memory_bytes=max(0, available),
        process_rss_bytes=max(0, rss),
        cpu_count=max(1, os.cpu_count() or 1),
        disk_free_bytes=max(0, disk_free),
        source=source,
    )


def _frame_bytes(frame: pd.DataFrame | None) -> int:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return 0
    try:
        return int(frame.memory_usage(index=True, deep=True).sum())
    except Exception:
        return max(1, int(frame.shape[0]) * max(1, int(frame.shape[1])) * 16)


def _mode_limits(mode: str) -> tuple[int, int, int]:
    return {
        "interactive": (250_000, 100, 20_000_000),
        "extended": (750_000, 256, 50_000_000),
        "full": (1_000_000, 512, 80_000_000),
    }[mode]


def assess_dataframe_admission(
    frame: pd.DataFrame | None,
    requested_mode: str = "auto",
    *,
    root: str | Path | None = None,
    snapshot: ResourceSnapshot | None = None,
) -> AnalysisAdmission:
    snapshot = snapshot or capture_resource_snapshot(root)
    requested = str(requested_mode or "auto").strip().lower()
    if requested not in {"auto", "interactive", "extended", "full"}:
        requested = "auto"
    rows = int(len(frame)) if isinstance(frame, pd.DataFrame) else 0
    columns = int(len(frame.columns)) if isinstance(frame, pd.DataFrame) else 0
    input_bytes = _frame_bytes(frame)
    reserve = max(512 * _MIB, int(snapshot.total_memory_bytes * 0.15))
    usable = max(0, snapshot.available_memory_bytes - reserve)

    # Native workflows can hold transformed copies, metrics, plots and result tables.
    # A conservative multiplier prevents optimistic admission under memory pressure.
    peak_multiplier = 3.5 if columns <= 128 else 4.5
    estimated_peak = max(input_bytes, int(input_bytes * peak_multiplier))

    candidates = ["full", "extended", "interactive"]
    if requested != "auto":
        candidates = candidates[candidates.index(requested) :]
    # High global pressure must cap the mode even when the current input is small;
    # downstream transforms and exports can allocate significantly more memory.
    if snapshot.memory_pressure >= 0.80:
        candidates = ["interactive"]
    elif snapshot.memory_pressure >= 0.70:
        candidates = [candidate for candidate in candidates if candidate != "full"] or ["interactive"]
    effective = "interactive"
    reason = "Qualified interactive fallback selected."
    warnings: list[str] = []
    allowed = True

    for candidate in candidates:
        row_limit, feature_limit, cell_limit = _mode_limits(candidate)
        bounded_rows = min(rows or row_limit, row_limit)
        bounded_features = min(columns or feature_limit, feature_limit)
        bounded_cells = bounded_rows * bounded_features
        proportional_peak = estimated_peak
        if rows > 0 and bounded_rows < rows:
            proportional_peak = max(64 * _MIB, int(estimated_peak * bounded_rows / rows))
        if columns > 0 and bounded_features < columns:
            proportional_peak = max(64 * _MIB, int(proportional_peak * bounded_features / columns))
        if bounded_cells <= cell_limit and proportional_peak <= max(usable, 256 * _MIB):
            effective = candidate
            reason = f"{candidate.title()} mode fits the qualified cell and memory envelope."
            break
    else:
        effective = "interactive"
        allowed = usable >= 128 * _MIB or input_bytes == 0
        reason = "Available memory is below the normal interactive reserve; strict bounded mode applied."
        warnings.append("Close other applications before running large analyses.")

    row_limit, feature_limit, _ = _mode_limits(effective)
    if effective != requested and requested != "auto":
        warnings.append(f"Requested {requested} mode was safely downgraded to {effective}.")
    if snapshot.memory_pressure >= 0.85:
        warnings.append("System memory pressure is high; result generation may be slower.")
    if snapshot.disk_free_bytes and snapshot.disk_free_bytes < 2 * _GIB:
        warnings.append("Less than 2 GiB disk space is available for temporary results and exports.")
    if input_bytes > 0 and estimated_peak > usable > 0:
        warnings.append("The complete input may exceed the safe in-memory envelope; deterministic bounded coverage will be used.")

    return AnalysisAdmission(
        requested_mode=requested,
        effective_mode=effective,
        allowed=allowed,
        estimated_input_bytes=input_bytes,
        estimated_peak_bytes=estimated_peak,
        available_memory_bytes=snapshot.available_memory_bytes,
        reserved_memory_bytes=reserve,
        max_rows=row_limit,
        max_features=feature_limit,
        downgraded=requested not in {"auto", effective},
        reason=reason,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def resource_manifest(root: str | Path | None = None) -> dict[str, Any]:
    snapshot = capture_resource_snapshot(root)
    return {
        "schema": "biointel.step159.resource-guard.v1",
        "snapshot": snapshot.to_dict(),
        "policy": {
            "minimum_reserved_memory_bytes": 512 * _MIB,
            "memory_reserve_ratio": 0.15,
            "high_pressure_threshold": 0.85,
            "analysis_modes": {
                name: {"row_limit": values[0], "feature_limit": values[1], "cell_limit": values[2]}
                for name, values in {
                    "interactive": _mode_limits("interactive"),
                    "extended": _mode_limits("extended"),
                    "full": _mode_limits("full"),
                }.items()
            },
        },
    }
