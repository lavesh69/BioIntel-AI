from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    matthews_corrcoef,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)


def _finite_or_none(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None


def classification_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    probabilities: np.ndarray,
) -> dict[str, float | None]:
    """Calculate robust binary-classification metrics."""

    labels = np.unique(y_true)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    specificity = tn / (tn + fp) if (tn + fp) else 0.0

    metrics: dict[str, float | None] = {
        "accuracy": _finite_or_none(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": _finite_or_none(balanced_accuracy_score(y_true, y_pred)),
        "precision": _finite_or_none(precision_score(y_true, y_pred, zero_division=0)),
        "recall": _finite_or_none(recall_score(y_true, y_pred, zero_division=0)),
        "specificity": _finite_or_none(specificity),
        "f1": _finite_or_none(f1_score(y_true, y_pred, zero_division=0)),
        "mcc": _finite_or_none(matthews_corrcoef(y_true, y_pred)),
        "roc_auc": None,
        "pr_auc": None,
        "log_loss": None,
        "brier_score": None,
    }

    if len(labels) == 2:
        metrics["roc_auc"] = _finite_or_none(roc_auc_score(y_true, probabilities))
        metrics["pr_auc"] = _finite_or_none(average_precision_score(y_true, probabilities))
        metrics["log_loss"] = _finite_or_none(
            log_loss(
                y_true,
                np.column_stack([1 - probabilities, probabilities]),
                labels=[0, 1],
            )
        )
        metrics["brier_score"] = _finite_or_none(brier_score_loss(y_true, probabilities))
    return metrics


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float | None]:
    """Calculate error, fit and correlation metrics for regression."""

    mse = mean_squared_error(y_true, y_pred)
    actual = pd.Series(np.asarray(y_true, dtype=float))
    predicted = pd.Series(np.asarray(y_pred, dtype=float))
    pearson = actual.corr(predicted, method="pearson") if actual.nunique() > 1 else np.nan
    spearman = actual.corr(predicted, method="spearman") if actual.nunique() > 1 else np.nan
    return {
        "mae": _finite_or_none(mean_absolute_error(y_true, y_pred)),
        "mse": _finite_or_none(mse),
        "rmse": _finite_or_none(np.sqrt(mse)),
        "r2": _finite_or_none(r2_score(y_true, y_pred)),
        "pearson": _finite_or_none(pearson),
        "spearman": _finite_or_none(spearman),
    }


def optimize_binary_threshold(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    objective: str = "f1",
) -> tuple[float, float]:
    """Select a threshold using validation data only."""

    if len(np.unique(y_true)) < 2:
        return 0.5, 0.0

    best_threshold = 0.5
    best_score = -1.0
    for threshold in np.linspace(0.05, 0.95, 181):
        predicted = (probabilities >= threshold).astype(int)
        if objective == "f1":
            score = f1_score(y_true, predicted, zero_division=0)
        else:
            score = balanced_accuracy_score(y_true, predicted)

        if score > best_score:
            best_score = float(score)
            best_threshold = float(threshold)

    return best_threshold, best_score


def _percentile_interval(values: list[float]) -> dict[str, float] | None:
    finite = np.asarray([value for value in values if math.isfinite(value)], dtype=float)
    if len(finite) < 20:
        return None
    return {
        "lower_95": float(np.percentile(finite, 2.5)),
        "upper_95": float(np.percentile(finite, 97.5)),
        "bootstrap_samples": int(len(finite)),
    }


def bootstrap_classification_intervals(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
    iterations: int = 200,
    random_seed: int = 42,
) -> dict[str, dict[str, float] | None]:
    """Estimate simple non-parametric confidence intervals on the final test set."""

    y_true = np.asarray(y_true, dtype=int)
    probabilities = np.asarray(probabilities, dtype=float)
    if len(y_true) != len(probabilities) or len(y_true) < 4:
        return {}

    rng = np.random.default_rng(random_seed)
    collected: dict[str, list[float]] = {
        "accuracy": [],
        "balanced_accuracy": [],
        "f1": [],
        "roc_auc": [],
        "pr_auc": [],
    }
    for _ in range(max(20, min(iterations, 5000))):
        indices = rng.integers(0, len(y_true), size=len(y_true))
        sampled_true = y_true[indices]
        sampled_probabilities = probabilities[indices]
        sampled_predicted = (sampled_probabilities >= threshold).astype(int)
        metrics = classification_metrics(
            sampled_true,
            sampled_predicted,
            sampled_probabilities,
        )
        for name in collected:
            value = metrics.get(name)
            if value is not None:
                collected[name].append(float(value))

    return {name: _percentile_interval(values) for name, values in collected.items()}


def bootstrap_regression_intervals(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    iterations: int = 200,
    random_seed: int = 42,
) -> dict[str, dict[str, float] | None]:
    """Estimate simple non-parametric confidence intervals on regression metrics."""

    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if len(y_true) != len(y_pred) or len(y_true) < 4:
        return {}

    rng = np.random.default_rng(random_seed)
    collected: dict[str, list[float]] = {
        "mae": [],
        "rmse": [],
        "r2": [],
    }
    for _ in range(max(20, min(iterations, 5000))):
        indices = rng.integers(0, len(y_true), size=len(y_true))
        metrics = regression_metrics(y_true[indices], y_pred[indices])
        for name in collected:
            value = metrics.get(name)
            if value is not None:
                collected[name].append(float(value))

    return {name: _percentile_interval(values) for name, values in collected.items()}
