from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from biointel.training.evaluation import optimize_binary_threshold


@dataclass(frozen=True)
class GroupThreshold:
    group: str
    rows: int
    threshold: float
    validation_score: float
    fallback_used: bool


def fit_group_thresholds(
    dataframe: pd.DataFrame,
    *,
    group_column: str,
    label_column: str = "interaction_label",
    probability_column: str = "positive_probability",
    objective: str = "balanced",
    minimum_rows: int = 30,
    fallback_threshold: float = 0.5,
) -> tuple[GroupThreshold, ...]:
    required = {group_column, label_column, probability_column}
    missing = required - set(dataframe.columns)
    if missing:
        raise ValueError("Missing calibration columns: " + ", ".join(sorted(missing)))
    thresholds: list[GroupThreshold] = []
    for group, subset in dataframe.groupby(group_column, dropna=False):
        labels = pd.to_numeric(subset[label_column], errors="coerce")
        probabilities = pd.to_numeric(subset[probability_column], errors="coerce")
        valid = labels.notna() & probabilities.notna()
        labels_array = labels[valid].to_numpy(dtype=int)
        probability_array = probabilities[valid].to_numpy(dtype=float)
        fallback = len(labels_array) < minimum_rows or len(np.unique(labels_array)) < 2
        if fallback:
            threshold, score = fallback_threshold, 0.0
        else:
            threshold, score = optimize_binary_threshold(
                labels_array,
                probability_array,
                objective="f1" if objective == "f1" else "balanced",
            )
        thresholds.append(
            GroupThreshold(
                group=str(group),
                rows=int(len(labels_array)),
                threshold=float(threshold),
                validation_score=float(score),
                fallback_used=fallback,
            )
        )
    return tuple(thresholds)
