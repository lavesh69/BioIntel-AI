from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class UncertaintySummary:
    metric: str
    estimate: float
    lower: float
    upper: float
    bootstrap_iterations: int
    observations: int
    stability_score: float
    sensitivity: pd.DataFrame


def bootstrap_summary(values: pd.Series | np.ndarray, *, metric: str = "mean", iterations: int = 500, confidence: float = 0.95, seed: int = 140) -> UncertaintySummary:
    array = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(dtype=float)
    if len(array) < 2:
        raise ValueError("At least two numeric observations are required for uncertainty estimation.")
    if iterations < 100 or iterations > 10_000:
        raise ValueError("Bootstrap iterations must be between 100 and 10,000.")
    fn = np.median if metric == "median" else np.mean
    estimate = float(fn(array))
    rng = np.random.default_rng(seed)
    stats = np.empty(iterations, dtype=float)
    for index in range(iterations):
        stats[index] = fn(rng.choice(array, size=len(array), replace=True))
    alpha = (1.0 - confidence) / 2.0
    lower, upper = np.quantile(stats, [alpha, 1.0 - alpha])
    leave_one_out = np.array([fn(np.delete(array, i)) for i in range(len(array))]) if len(array) <= 5000 else np.array([fn(array[rng.choice(len(array), len(array)-1, replace=False)]) for _ in range(500)])
    denominator = abs(estimate) + 1e-9
    relative_spread = float(np.std(leave_one_out) / denominator)
    stability = float(np.clip(1.0 - relative_spread, 0.0, 1.0))
    sensitivity = pd.DataFrame({"scenario": ["bootstrap lower", "estimate", "bootstrap upper", "leave-one-out min", "leave-one-out max"], "value": [float(lower), estimate, float(upper), float(leave_one_out.min()), float(leave_one_out.max())]})
    return UncertaintySummary(metric, estimate, float(lower), float(upper), iterations, len(array), stability, sensitivity)


def choose_numeric_metric(frame: pd.DataFrame) -> str | None:
    preferred = ("priority_score", "effect_size", "score", "quality", "support", "expression", "signal", "value", "allele_fraction")
    for column in preferred:
        if column in frame.columns and pd.to_numeric(frame[column], errors="coerce").notna().sum() >= 2:
            return column
    numeric = frame.select_dtypes(include="number").columns.tolist()
    return numeric[0] if numeric else None


def uncertainty_table(frame: pd.DataFrame, *, iterations: int = 500) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows = []
    for column in frame.select_dtypes(include="number").columns[:12]:
        series = pd.to_numeric(frame[column], errors="coerce").dropna()
        if len(series) < 2:
            continue
        summary = bootstrap_summary(series, metric="mean", iterations=iterations)
        rows.append({"metric": column, "estimate": summary.estimate, "lower_95": summary.lower, "upper_95": summary.upper, "observations": summary.observations, "stability_score": summary.stability_score})
    table = pd.DataFrame(rows)
    overall = float(table["stability_score"].mean()) if not table.empty else 0.0
    return table, {"metrics_evaluated": len(table), "overall_stability": overall, "bootstrap_iterations": iterations}


__all__ = ["UncertaintySummary", "bootstrap_summary", "choose_numeric_metric", "uncertainty_table"]
