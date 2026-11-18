from __future__ import annotations

import math

import numpy as np


def conformal_quantile(scores: np.ndarray, alpha: float = 0.1) -> float:
    values = np.asarray(scores, dtype=float)
    values = values[np.isfinite(values)]
    if not 0.01 <= alpha <= 0.5:
        raise ValueError("alpha must be between 0.01 and 0.50")
    if len(values) < 3:
        raise ValueError("At least three calibration scores are required.")
    level = min(1.0, math.ceil((len(values) + 1) * (1.0 - alpha)) / len(values))
    return float(np.quantile(values, level, method="higher"))


def fit_classification_conformal(y_true, positive_probabilities, alpha: float = 0.1):
    labels = np.asarray(y_true, dtype=int)
    probabilities = np.asarray(positive_probabilities, dtype=float)
    if len(labels) != len(probabilities):
        raise ValueError("Labels and probabilities must have the same length.")
    if not np.isin(labels, [0, 1]).all():
        raise ValueError("Classification labels must be 0 or 1.")
    true_probability = np.where(labels == 1, probabilities, 1.0 - probabilities)
    quantile = conformal_quantile(1.0 - true_probability, alpha)
    return {
        "method": "split_conformal_classification",
        "alpha": float(alpha),
        "coverage_target": float(1.0 - alpha),
        "score_quantile": quantile,
        "calibration_rows": int(len(labels)),
    }


def classification_prediction_set(
    positive_probability: float, calibration: dict[str, object]
) -> list[int]:
    p = float(positive_probability)
    q = float(calibration.get("score_quantile", 1.0))
    output: list[int] = []
    if p <= q:
        output.append(0)
    if 1.0 - p <= q:
        output.append(1)
    return output


def fit_regression_conformal(y_true, predicted, alpha: float = 0.1):
    actual = np.asarray(y_true, dtype=float)
    estimates = np.asarray(predicted, dtype=float)
    if len(actual) != len(estimates):
        raise ValueError("Actual and predicted values must have the same length.")
    q = conformal_quantile(np.abs(actual - estimates), alpha)
    return {
        "method": "split_conformal_regression",
        "alpha": float(alpha),
        "coverage_target": float(1.0 - alpha),
        "absolute_residual_quantile": q,
        "calibration_rows": int(len(actual)),
    }


def regression_prediction_interval(
    predicted: float, calibration: dict[str, object]
) -> tuple[float, float]:
    radius = float(calibration.get("absolute_residual_quantile", 0.0))
    value = float(predicted)
    return value - radius, value + radius


def classification_conformal_diagnostics(y_true, positive_probabilities, calibration):
    labels = np.asarray(y_true, dtype=int)
    probabilities = np.asarray(positive_probabilities, dtype=float)
    sets = [classification_prediction_set(v, calibration) for v in probabilities]
    covered = [int(label in s) for label, s in zip(labels, sets, strict=True)]
    return {
        "conformal_coverage": float(np.mean(covered)) if covered else 0.0,
        "average_prediction_set_size": float(np.mean([len(s) for s in sets])) if sets else 0.0,
        "empty_prediction_set_fraction": (
            float(np.mean([len(s) == 0 for s in sets])) if sets else 0.0
        ),
    }


def regression_conformal_diagnostics(y_true, predicted, calibration):
    actual = np.asarray(y_true, dtype=float)
    estimates = np.asarray(predicted, dtype=float)
    intervals = [regression_prediction_interval(v, calibration) for v in estimates]
    covered = [int(lo <= y <= hi) for y, (lo, hi) in zip(actual, intervals, strict=True)]
    widths = [hi - lo for lo, hi in intervals]
    return {
        "conformal_coverage": float(np.mean(covered)) if covered else 0.0,
        "average_interval_width": float(np.mean(widths)) if widths else 0.0,
    }
