from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class DatasetProfile:
    row_count: int
    column_count: int
    duplicate_rows: int
    total_missing_values: int
    missing_fraction: float
    memory_bytes: int
    column_profile: pd.DataFrame
    numeric_outliers: pd.DataFrame
    warnings: tuple[str, ...]


def _iqr_outliers(series: pd.Series) -> tuple[int, float | None, float | None]:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if len(numeric) < 4:
        return 0, None, None
    q1 = float(numeric.quantile(0.25))
    q3 = float(numeric.quantile(0.75))
    iqr = q3 - q1
    if not math.isfinite(iqr) or iqr <= 0:
        return 0, q1, q3
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    count = int(((numeric < lower) | (numeric > upper)).sum())
    return count, lower, upper


def profile_dataframe(dataframe: pd.DataFrame) -> DatasetProfile:
    row_count = len(dataframe)
    column_count = len(dataframe.columns)
    duplicate_rows = int(dataframe.duplicated().sum())
    total_missing = int(dataframe.isna().sum().sum())
    total_cells = max(1, row_count * max(1, column_count))
    missing_fraction = total_missing / total_cells
    memory_bytes = int(dataframe.memory_usage(deep=True).sum())

    column_rows: list[dict[str, object]] = []
    outlier_rows: list[dict[str, object]] = []
    warnings: list[str] = []

    for column in dataframe.columns:
        series = dataframe[column]
        missing = int(series.isna().sum())
        unique = int(series.nunique(dropna=True))
        sample = ""
        non_null = series.dropna()
        if not non_null.empty:
            sample = str(non_null.iloc[0])[:80]

        column_rows.append(
            {
                "column": str(column),
                "dtype": str(series.dtype),
                "missing": missing,
                "missing_percent": (missing / row_count * 100 if row_count else 0.0),
                "unique": unique,
                "unique_percent": (unique / row_count * 100 if row_count else 0.0),
                "sample": sample,
            }
        )

        if pd.api.types.is_numeric_dtype(series):
            count, lower, upper = _iqr_outliers(series)
            outlier_rows.append(
                {
                    "column": str(column),
                    "outlier_count": count,
                    "lower_bound": lower,
                    "upper_bound": upper,
                }
            )

    if duplicate_rows:
        warnings.append(f"{duplicate_rows} exact duplicate row(s) detected.")
    if missing_fraction > 0.10:
        warnings.append(f"Dataset has {missing_fraction:.1%} missing cells.")
    if row_count < 50:
        warnings.append("Dataset is small; model metrics may be unstable.")
    if "label" in dataframe.columns:
        counts = dataframe["label"].value_counts(dropna=False)
        if len(counts) == 2 and counts.min() > 0:
            imbalance = float(counts.max() / counts.min())
            if imbalance >= 4:
                warnings.append(f"Classification labels are imbalanced ({imbalance:.1f}:1).")

    return DatasetProfile(
        row_count=row_count,
        column_count=column_count,
        duplicate_rows=duplicate_rows,
        total_missing_values=total_missing,
        missing_fraction=missing_fraction,
        memory_bytes=memory_bytes,
        column_profile=pd.DataFrame(column_rows),
        numeric_outliers=pd.DataFrame(outlier_rows),
        warnings=tuple(warnings),
    )
