from __future__ import annotations

import pandas as pd

from biointel.training.evaluation import classification_metrics, regression_metrics


def evaluate_subgroups(
    dataframe: pd.DataFrame,
    *,
    group_column: str,
    truth_column: str,
    prediction_column: str,
    task_type: str,
    probability_column: str = "positive_probability",
    minimum_rows: int = 20,
) -> pd.DataFrame:
    required = {group_column, truth_column, prediction_column}
    if task_type == "classification":
        required.add(probability_column)
    missing = required - set(dataframe.columns)
    if missing:
        raise ValueError("Missing subgroup columns: " + ", ".join(sorted(missing)))
    rows: list[dict[str, object]] = []
    for group, subset in dataframe.groupby(group_column, dropna=False):
        if len(subset) < minimum_rows:
            continue
        if task_type == "classification":
            metrics = classification_metrics(
                subset[truth_column].to_numpy(dtype=int),
                subset[prediction_column].to_numpy(dtype=int),
                subset[probability_column].to_numpy(dtype=float),
            )
        elif task_type == "regression":
            metrics = regression_metrics(
                subset[truth_column].to_numpy(dtype=float),
                subset[prediction_column].to_numpy(dtype=float),
            )
        else:
            raise ValueError("task_type must be classification or regression")
        rows.append({"group": str(group), "rows": len(subset), **metrics})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("rows", ascending=False).reset_index(drop=True)
