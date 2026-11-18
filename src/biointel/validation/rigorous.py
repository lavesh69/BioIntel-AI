from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)


@dataclass(frozen=True)
class BootstrapInterval:
    estimate: float
    lower_95: float
    upper_95: float
    samples: int


@dataclass(frozen=True)
class ValidationEvidence:
    task: str
    sample_count: int
    metrics: dict[str, float]
    confidence_intervals: dict[str, dict[str, float | int]]
    calibration: dict[str, float]
    permutation_p_value: float | None
    subgroup_metrics: dict[str, dict[str, float]]
    passed: bool
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _arrays(y_true: Iterable[float], y_pred: Iterable[float]) -> tuple[np.ndarray, np.ndarray]:
    truth = np.asarray(list(y_true), dtype=float)
    predicted = np.asarray(list(y_pred), dtype=float)
    if truth.ndim != 1 or predicted.ndim != 1 or truth.size != predicted.size:
        raise ValueError("y_true and y_pred must be one-dimensional arrays with equal length.")
    if truth.size < 10:
        raise ValueError("Rigorous validation requires at least 10 observations.")
    if not np.isfinite(truth).all() or not np.isfinite(predicted).all():
        raise ValueError("Validation arrays must contain only finite values.")
    return truth, predicted


def _bootstrap(
    truth: np.ndarray,
    predicted: np.ndarray,
    metric: Callable[[np.ndarray, np.ndarray], float],
    *,
    iterations: int,
    random_seed: int,
) -> BootstrapInterval:
    estimate = float(metric(truth, predicted))
    rng = np.random.default_rng(random_seed)
    values: list[float] = []
    for _ in range(max(int(iterations), 200)):
        indices = rng.integers(0, truth.size, truth.size)
        try:
            value = float(metric(truth[indices], predicted[indices]))
        except (ValueError, ZeroDivisionError, FloatingPointError):
            continue
        if np.isfinite(value):
            values.append(value)
    if len(values) < 100:
        return BootstrapInterval(estimate, estimate, estimate, len(values))
    lower, upper = np.quantile(values, [0.025, 0.975])
    return BootstrapInterval(estimate, float(lower), float(upper), len(values))


def _permutation_p_value(
    truth: np.ndarray,
    predicted: np.ndarray,
    metric: Callable[[np.ndarray, np.ndarray], float],
    *,
    iterations: int,
    random_seed: int,
) -> float:
    observed = float(metric(truth, predicted))
    rng = np.random.default_rng(random_seed)
    exceed = 0
    valid = 0
    for _ in range(max(int(iterations), 200)):
        shuffled = rng.permutation(truth)
        try:
            candidate = float(metric(shuffled, predicted))
        except ValueError:
            continue
        if np.isfinite(candidate):
            valid += 1
            if candidate >= observed:
                exceed += 1
    return float((exceed + 1) / (valid + 1))


def calibration_diagnostics(
    y_true: Iterable[float], probabilities: Iterable[float]
) -> dict[str, float]:
    truth, prob = _arrays(y_true, probabilities)
    if not np.isin(truth, [0.0, 1.0]).all():
        raise ValueError("Classification calibration requires binary labels.")
    clipped = np.clip(prob, 1e-6, 1 - 1e-6)
    logits = np.log(clipped / (1.0 - clipped))
    design = np.column_stack([np.ones_like(logits), logits])
    intercept, slope = np.linalg.lstsq(design, truth, rcond=None)[0]
    bins = np.linspace(0.0, 1.0, 11)
    ece = 0.0
    for left, right in zip(bins[:-1], bins[1:]):
        mask = (prob >= left) & ((prob < right) if right < 1 else (prob <= right))
        if mask.any():
            ece += float(mask.mean()) * abs(float(truth[mask].mean()) - float(prob[mask].mean()))
    return {
        "brier_score": float(brier_score_loss(truth, prob)),
        "log_loss": float(log_loss(truth, clipped, labels=[0, 1])),
        "calibration_intercept": float(intercept),
        "calibration_slope": float(slope),
        "expected_calibration_error": float(ece),
    }


def _subgroups(
    truth: np.ndarray,
    predicted: np.ndarray,
    groups: Iterable[str] | None,
    metrics: dict[str, Callable[[np.ndarray, np.ndarray], float]],
) -> dict[str, dict[str, float]]:
    if groups is None:
        return {}
    group_array = np.asarray(list(groups), dtype=object)
    if group_array.size != truth.size:
        raise ValueError("groups must have the same length as validation labels.")
    output: dict[str, dict[str, float]] = {}
    for group in sorted({str(item) for item in group_array}):
        mask = group_array.astype(str) == group
        if int(mask.sum()) < 10:
            continue
        values: dict[str, float] = {"n": float(mask.sum())}
        for name, metric in metrics.items():
            try:
                values[name] = float(metric(truth[mask], predicted[mask]))
            except ValueError:
                continue
        output[group] = values
    return output


def classification_validation(
    y_true: Iterable[int],
    probabilities: Iterable[float],
    *,
    threshold: float = 0.5,
    groups: Iterable[str] | None = None,
    bootstrap_iterations: int = 1000,
    permutation_iterations: int = 1000,
    random_seed: int = 42,
) -> ValidationEvidence:
    truth, prob = _arrays(y_true, probabilities)
    if not np.isin(truth, [0.0, 1.0]).all() or np.unique(truth).size != 2:
        raise ValueError("Classification validation requires both binary classes.")
    if np.any((prob < 0) | (prob > 1)):
        raise ValueError("Classification probabilities must be between zero and one.")
    metric_functions: dict[str, Callable[[np.ndarray, np.ndarray], float]] = {
        "roc_auc": lambda y, p: roc_auc_score(y, p),
        "pr_auc": lambda y, p: average_precision_score(y, p),
        "balanced_accuracy": lambda y, p: balanced_accuracy_score(y, p >= threshold),
    }
    metrics = {name: float(fn(truth, prob)) for name, fn in metric_functions.items()}
    metrics.update(calibration_diagnostics(truth, prob))
    intervals = {
        name: asdict(
            _bootstrap(
                truth, prob, fn, iterations=bootstrap_iterations, random_seed=random_seed + index
            )
        )
        for index, (name, fn) in enumerate(metric_functions.items())
    }
    p_value = _permutation_p_value(
        truth,
        prob,
        metric_functions["roc_auc"],
        iterations=permutation_iterations,
        random_seed=random_seed,
    )
    subgroup = _subgroups(truth, prob, groups, metric_functions)
    blockers: list[str] = []
    if intervals["roc_auc"]["lower_95"] < 0.65:
        blockers.append("ROC-AUC lower confidence bound is below 0.65.")
    if metrics["balanced_accuracy"] < 0.65:
        blockers.append("Balanced accuracy is below 0.65.")
    if metrics["expected_calibration_error"] > 0.10:
        blockers.append("Expected calibration error exceeds 0.10.")
    if p_value > 0.05:
        blockers.append("Permutation test does not establish performance above chance.")
    return ValidationEvidence(
        task="classification",
        sample_count=int(truth.size),
        metrics=metrics,
        confidence_intervals=intervals,
        calibration=calibration_diagnostics(truth, prob),
        permutation_p_value=p_value,
        subgroup_metrics=subgroup,
        passed=not blockers,
        blockers=tuple(blockers),
    )


def regression_validation(
    y_true: Iterable[float],
    predictions: Iterable[float],
    *,
    groups: Iterable[str] | None = None,
    bootstrap_iterations: int = 1000,
    permutation_iterations: int = 1000,
    random_seed: int = 42,
) -> ValidationEvidence:
    truth, predicted = _arrays(y_true, predictions)
    metric_functions: dict[str, Callable[[np.ndarray, np.ndarray], float]] = {
        "r2": lambda y, p: r2_score(y, p),
        "pearson": lambda y, p: float(np.corrcoef(y, p)[0, 1]),
        "neg_rmse": lambda y, p: -float(mean_squared_error(y, p) ** 0.5),
        "neg_mae": lambda y, p: -float(mean_absolute_error(y, p)),
    }
    raw = {name: float(fn(truth, predicted)) for name, fn in metric_functions.items()}
    metrics = {
        "r2": raw["r2"],
        "pearson": raw["pearson"],
        "rmse": -raw["neg_rmse"],
        "mae": -raw["neg_mae"],
    }
    intervals = {
        name: asdict(
            _bootstrap(
                truth,
                predicted,
                fn,
                iterations=bootstrap_iterations,
                random_seed=random_seed + index,
            )
        )
        for index, (name, fn) in enumerate(metric_functions.items())
    }
    neg_rmse_interval = intervals.pop("neg_rmse")
    intervals["rmse"] = {
        "estimate": -float(neg_rmse_interval["estimate"]),
        "lower_95": -float(neg_rmse_interval["upper_95"]),
        "upper_95": -float(neg_rmse_interval["lower_95"]),
        "samples": int(neg_rmse_interval["samples"]),
    }
    neg_mae_interval = intervals.pop("neg_mae")
    intervals["mae"] = {
        "estimate": -float(neg_mae_interval["estimate"]),
        "lower_95": -float(neg_mae_interval["upper_95"]),
        "upper_95": -float(neg_mae_interval["lower_95"]),
        "samples": int(neg_mae_interval["samples"]),
    }
    p_value = _permutation_p_value(
        truth,
        predicted,
        metric_functions["pearson"],
        iterations=permutation_iterations,
        random_seed=random_seed,
    )
    subgroup = _subgroups(truth, predicted, groups, metric_functions)
    blockers: list[str] = []
    if metrics["r2"] <= 0.0:
        blockers.append("R² does not beat the mean baseline.")
    if float(intervals["r2"]["lower_95"]) <= 0.0:
        blockers.append("R² lower confidence bound does not beat the mean baseline.")
    if metrics["pearson"] < 0.30:
        blockers.append("Pearson correlation is below 0.30.")
    if p_value > 0.05:
        blockers.append("Permutation test does not establish correlation above chance.")
    return ValidationEvidence(
        task="regression",
        sample_count=int(truth.size),
        metrics=metrics,
        confidence_intervals=intervals,
        calibration={},
        permutation_p_value=p_value,
        subgroup_metrics=subgroup,
        passed=not blockers,
        blockers=tuple(blockers),
    )
