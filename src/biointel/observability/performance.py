from __future__ import annotations

import json
import os
import platform

try:
    import resource
except ImportError:  # Windows
    resource = None
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class PerformanceMeasurement:
    name: str
    elapsed_seconds: float
    rows: int
    rows_per_second: float
    peak_memory_mb: float
    passed_budget: bool
    budget_seconds: float | None
    captured_at_utc: str


def _peak_memory_mb() -> float:
    if resource is not None:
        value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if platform.system() == "Darwin":
            return value / (1024 * 1024)
        return value / 1024
    try:
        import psutil

        return float(psutil.Process().memory_info().rss) / (1024 * 1024)
    except ImportError:
        return 0.0


def measure_operation(
    name: str,
    operation: Callable[[], object],
    *,
    rows: int = 1,
    budget_seconds: float | None = None,
) -> tuple[object, PerformanceMeasurement]:
    started = time.perf_counter()
    result = operation()
    elapsed = max(time.perf_counter() - started, 0.0)
    measurement = PerformanceMeasurement(
        name=name,
        elapsed_seconds=round(elapsed, 6),
        rows=int(rows),
        rows_per_second=round(rows / elapsed, 3) if elapsed else 0.0,
        peak_memory_mb=round(_peak_memory_mb(), 3),
        passed_budget=budget_seconds is None or elapsed <= budget_seconds,
        budget_seconds=budget_seconds,
        captured_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    return result, measurement


def save_performance_report(
    measurements: list[PerformanceMeasurement],
    path: str | Path,
) -> Path:
    output = Path(path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "measurements": [asdict(item) for item in measurements],
        "all_budgets_passed": all(item.passed_budget for item in measurements),
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output
