from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class BenchmarkResult:
    benchmark_id: str
    model_sha256: str
    dataset_sha256: str
    source_provider: str
    split_strategy: str
    metrics: dict[str, float]
    confidence_intervals: dict[str, tuple[float, float]]
    baseline_metrics: dict[str, float]
    leakage_checks: dict[str, bool]
    calibration_checks: dict[str, float]
    passed: bool
    completed_at: str


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def bootstrap_interval(values: list[float], *, statistic=np.mean, iterations: int = 2000, seed: int = 42) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    if array.size < 2:
        raise ValueError("At least two observations are required.")
    rng = np.random.default_rng(seed)
    stats = [float(statistic(rng.choice(array, size=array.size, replace=True))) for _ in range(iterations)]
    return float(np.quantile(stats, 0.025)), float(np.quantile(stats, 0.975))


def qualify_dti_benchmark(
    *,
    model_sha256: str,
    dataset_sha256: str,
    source_provider: str,
    split_strategy: str,
    metrics: dict[str, float],
    baseline_metrics: dict[str, float],
    confidence_intervals: dict[str, tuple[float, float]],
    leakage_checks: dict[str, bool],
    calibration_checks: dict[str, float],
    minimums: dict[str, float] | None = None,
) -> BenchmarkResult:
    thresholds = minimums or {"roc_auc": 0.75, "pr_auc": 0.50, "balanced_accuracy": 0.65}
    robust_splits = {"cold_drug", "cold_target", "cold_both", "scaffold", "protein_cluster", "temporal", "external_source"}
    metric_pass = all(float(metrics.get(key, float("-inf"))) >= value for key, value in thresholds.items())
    baseline_pass = all(float(metrics.get(key, float("-inf"))) > float(baseline_metrics.get(key, float("-inf"))) for key in thresholds)
    leakage_pass = bool(leakage_checks) and all(bool(value) for value in leakage_checks.values())
    calibration_pass = float(calibration_checks.get("ece", 1.0)) <= 0.10 and float(calibration_checks.get("coverage", 0.0)) >= 0.85
    passed = split_strategy in robust_splits and metric_pass and baseline_pass and leakage_pass and calibration_pass
    completed = datetime.now(UTC).isoformat()
    payload = {
        "model_sha256": model_sha256, "dataset_sha256": dataset_sha256, "source_provider": source_provider,
        "split_strategy": split_strategy, "metrics": metrics, "confidence_intervals": confidence_intervals,
        "baseline_metrics": baseline_metrics, "leakage_checks": leakage_checks,
        "calibration_checks": calibration_checks, "passed": passed, "completed_at": completed,
    }
    return BenchmarkResult(benchmark_id=f"DTI-{_sha(payload)[:20]}", **payload)


def write_benchmark_bundle(result: BenchmarkResult, output: str | Path) -> Path:
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    payload["bundle_sha256"] = _sha(payload)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target
