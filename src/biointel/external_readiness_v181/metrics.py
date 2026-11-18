from __future__ import annotations

import math
from statistics import mean, median
from typing import Iterable, Sequence


def as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "pass", "passed", "approved"}


def finite(values: Iterable[float]) -> bool:
    return all(math.isfinite(float(value)) for value in values)


def pearson(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        return float("nan")
    x = [float(v) for v in left]
    y = [float(v) for v in right]
    mx, my = mean(x), mean(y)
    numerator = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = math.sqrt(sum((a - mx) ** 2 for a in x))
    dy = math.sqrt(sum((b - my) ** 2 for b in y))
    return numerator / (dx * dy) if dx and dy else float("nan")


def rmse(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return float("nan")
    return math.sqrt(mean([(float(a) - float(b)) ** 2 for a, b in zip(left, right)]))


def z_prime(pos_mean: float, pos_sd: float, neg_mean: float, neg_sd: float) -> float:
    delta = abs(float(pos_mean) - float(neg_mean))
    if delta <= 0:
        return float("-inf")
    return 1.0 - 3.0 * (abs(float(pos_sd)) + abs(float(neg_sd))) / delta


def confusion(truth: Sequence[bool], predicted: Sequence[bool]) -> tuple[int, int, int, int]:
    tp = sum(t and p for t, p in zip(truth, predicted))
    tn = sum((not t) and (not p) for t, p in zip(truth, predicted))
    fp = sum((not t) and p for t, p in zip(truth, predicted))
    fn = sum(t and (not p) for t, p in zip(truth, predicted))
    return tp, tn, fp, fn


def precision_recall(truth: Sequence[bool], predicted: Sequence[bool]) -> tuple[float, float]:
    tp, _, fp, fn = confusion(truth, predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return precision, recall


def balanced_accuracy(truth: Sequence[bool], predicted: Sequence[bool]) -> float:
    tp, tn, fp, fn = confusion(truth, predicted)
    sensitivity = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    return (sensitivity + specificity) / 2.0


def roc_auc(truth: Sequence[bool], scores: Sequence[float]) -> float:
    positives = [float(score) for label, score in zip(truth, scores) if label]
    negatives = [float(score) for label, score in zip(truth, scores) if not label]
    if not positives or not negatives:
        return float("nan")
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            wins += 1.0 if positive > negative else (0.5 if positive == negative else 0.0)
    return wins / (len(positives) * len(negatives))


def cohen_kappa(left: Sequence[object], right: Sequence[object]) -> float:
    if len(left) != len(right) or not left:
        return float("nan")
    labels = sorted({str(v) for v in left} | {str(v) for v in right})
    observed = sum(str(a) == str(b) for a, b in zip(left, right)) / len(left)
    expected = 0.0
    for label in labels:
        p_left = sum(str(v) == label for v in left) / len(left)
        p_right = sum(str(v) == label for v in right) / len(right)
        expected += p_left * p_right
    return (observed - expected) / (1.0 - expected) if expected < 1.0 else 1.0


def consensus(left: Sequence[object], right: Sequence[object]) -> list[str]:
    return [str(a) if str(a) == str(b) else str(a) for a, b in zip(left, right)]


def median_value(values: Sequence[float]) -> float:
    return float(median([float(value) for value in values])) if values else float("nan")


__all__ = [
    "as_bool",
    "finite",
    "pearson",
    "rmse",
    "z_prime",
    "precision_recall",
    "balanced_accuracy",
    "roc_auc",
    "cohen_kappa",
    "consensus",
    "median_value",
]
