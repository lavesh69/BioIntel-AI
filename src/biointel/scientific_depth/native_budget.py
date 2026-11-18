from __future__ import annotations

from contextvars import ContextVar
from dataclasses import asdict, dataclass
import math
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class NativeAnalysisBudget:
    mode: str
    row_limit: int
    feature_limit: int
    cell_limit: int
    sampling: str
    requested_mode: str
    constrained_by_cells: bool = False

    def manifest(self) -> dict[str, Any]:
        return asdict(self)


_DEFAULT = NativeAnalysisBudget(
    mode="interactive",
    row_limit=250_000,
    feature_limit=100,
    cell_limit=20_000_000,
    sampling="deterministic-even-coverage",
    requested_mode="interactive",
)
_CURRENT: ContextVar[NativeAnalysisBudget] = ContextVar("biointel_native_budget", default=_DEFAULT)


_MODE_LIMITS: dict[str, tuple[int, int, int]] = {
    "interactive": (250_000, 100, 20_000_000),
    "extended": (750_000, 256, 50_000_000),
    "full": (1_000_000, 512, 80_000_000),
}


def choose_native_budget(
    metadata: dict[str, Any] | None,
    *,
    rows: int,
    columns: int,
) -> NativeAnalysisBudget:
    values = dict(metadata or {})
    requested = str(values.get("analysis_mode", "interactive") or "interactive").strip().lower()
    effective = str(values.get("effective_analysis_mode", requested) or requested).strip().lower()
    if effective == "auto":
        effective = "interactive"
    if effective not in _MODE_LIMITS:
        effective = "interactive"
    row_limit, feature_limit, cell_limit = _MODE_LIMITS[effective]

    # Optional user limits may only reduce, never silently exceed the qualified mode.
    requested_rows = values.get("row_limit")
    requested_features = values.get("feature_limit")
    if requested_rows is not None:
        try:
            row_limit = min(row_limit, max(1, int(requested_rows)))
        except (TypeError, ValueError):
            pass
    if requested_features is not None:
        try:
            feature_limit = min(feature_limit, max(1, int(requested_features)))
        except (TypeError, ValueError):
            pass

    constrained = False
    if columns > 0 and row_limit * columns > cell_limit:
        row_limit = max(1, cell_limit // columns)
        constrained = True
    # Empty/wide frames still receive a meaningful bound.
    if rows > 0:
        row_limit = min(row_limit, max(rows, 1))
    feature_limit = min(feature_limit, max(columns, 1))
    return NativeAnalysisBudget(
        mode=effective,
        row_limit=int(row_limit),
        feature_limit=int(feature_limit),
        cell_limit=int(cell_limit),
        sampling="deterministic-even-coverage",
        requested_mode=requested,
        constrained_by_cells=constrained,
    )


def current_native_budget() -> NativeAnalysisBudget:
    return _CURRENT.get()


def set_native_budget(budget: NativeAnalysisBudget):
    return _CURRENT.set(budget)


def reset_native_budget(token: Any) -> None:
    _CURRENT.reset(token)


def bounded_frame(frame: pd.DataFrame | None, budget: NativeAnalysisBudget) -> tuple[pd.DataFrame, bool, int, str]:
    if not isinstance(frame, pd.DataFrame):
        return pd.DataFrame(), False, 0, "none"
    total = len(frame)
    if total <= budget.row_limit:
        return frame.copy(), False, total, "complete"
    # Evenly spaced deterministic coverage avoids first-N and random-sample bias,
    # while preserving reproducibility across platforms.
    positions = np.linspace(0, total - 1, num=budget.row_limit, dtype=np.int64)
    positions = np.unique(positions)
    bounded = frame.iloc[positions].copy()
    return bounded, True, total, budget.sampling


def budget_check_detail(budget: NativeAnalysisBudget, *, total_rows: int, analyzed_rows: int, columns: int) -> str:
    cells = analyzed_rows * columns
    return (
        f"mode={budget.mode}; rows={analyzed_rows:,}/{total_rows:,}; "
        f"features≤{budget.feature_limit}; cells={cells:,}/{budget.cell_limit:,}; "
        f"sampling={budget.sampling if analyzed_rows < total_rows else 'complete'}"
    )


__all__ = [
    "NativeAnalysisBudget",
    "bounded_frame",
    "budget_check_detail",
    "choose_native_budget",
    "current_native_budget",
    "reset_native_budget",
    "set_native_budget",
]
