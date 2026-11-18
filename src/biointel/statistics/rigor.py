from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class StatisticalDisclosure:
    analysis_name: str
    test_name: str
    null_hypothesis: str
    alternative_hypothesis: str
    sample_count: int
    biological_replicates: int | None
    technical_replicates: int | None
    groups: tuple[str, ...]
    effect_measure: str
    effect_size: float | None
    confidence_level: float
    confidence_interval: tuple[float | None, float | None]
    p_value: float | None
    adjusted_p_value: float | None
    multiple_testing_method: str
    missing_count: int
    excluded_count: int
    missing_policy: str
    outlier_policy: str
    assumptions: tuple[dict[str, Any], ...]
    random_seed: int | None
    software_versions: Mapping[str, str]
    data_hash: str
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["groups"] = list(self.groups)
        result["assumptions"] = list(self.assumptions)
        result["warnings"] = list(self.warnings)
        result["confidence_interval"] = list(self.confidence_interval)
        result["software_versions"] = dict(self.software_versions)
        return result

    def to_frame(self) -> pd.DataFrame:
        rows = []
        for key, value in self.to_dict().items():
            if isinstance(value, (dict, list, tuple)):
                value = json.dumps(value, sort_keys=True, default=str)
            rows.append({"Field": key.replace("_", " ").title(), "Value": value})
        return pd.DataFrame(rows)


def dataframe_hash(frame: pd.DataFrame, columns: Iterable[str] | None = None) -> str:
    selected = (frame[list(columns)] if columns else frame).copy()
    digest = hashlib.sha256()
    digest.update("|".join(map(str, selected.columns)).encode("utf-8"))
    for column in selected.select_dtypes(include=["object"]).columns:
        selected[column] = selected[column].map(
            lambda value: json.dumps(value, sort_keys=True, default=str)
            if isinstance(value, (dict, list, tuple, set))
            else value
        )
    try:
        values = pd.util.hash_pandas_object(selected, index=True).to_numpy(dtype=np.uint64, copy=False)
    except TypeError:
        values = pd.util.hash_pandas_object(selected.astype(str), index=True).to_numpy(dtype=np.uint64, copy=False)
    digest.update(values.tobytes())
    return digest.hexdigest()


def benjamini_hochberg(p_values: Iterable[float | None]) -> np.ndarray:
    values = np.asarray([np.nan if value is None else float(value) for value in p_values], dtype=float)
    adjusted = np.full(values.shape, np.nan, dtype=float)
    valid = np.isfinite(values)
    if not valid.any():
        return adjusted
    raw = values[valid]
    order = np.argsort(raw)
    ranked = raw[order]
    n = len(ranked)
    corrected = ranked * n / np.arange(1, n + 1)
    corrected = np.minimum.accumulate(corrected[::-1])[::-1]
    corrected = np.clip(corrected, 0, 1)
    restored = np.empty_like(corrected)
    restored[order] = corrected
    adjusted[valid] = restored
    return adjusted


def cohen_d(group_a: Iterable[float], group_b: Iterable[float]) -> float | None:
    a = np.asarray(list(group_a), dtype=float)
    b = np.asarray(list(group_b), dtype=float)
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return None
    pooled_denominator = len(a) + len(b) - 2
    if pooled_denominator <= 0:
        return None
    pooled_variance = ((len(a) - 1) * np.var(a, ddof=1) + (len(b) - 1) * np.var(b, ddof=1)) / pooled_denominator
    if pooled_variance <= 0:
        return 0.0 if math.isclose(float(np.mean(a)), float(np.mean(b))) else None
    return float((np.mean(a) - np.mean(b)) / math.sqrt(pooled_variance))


def hedges_g(group_a: Iterable[float], group_b: Iterable[float]) -> float | None:
    d = cohen_d(group_a, group_b)
    if d is None:
        return None
    n = len(list(group_a)) + len(list(group_b))
    if n <= 3:
        return d
    correction = 1 - 3 / (4 * n - 9)
    return float(d * correction)


def bootstrap_confidence_interval(
    values: Iterable[float],
    *,
    statistic: str = "mean",
    confidence_level: float = 0.95,
    iterations: int = 2000,
    seed: int = 42,
) -> tuple[float | None, float | None]:
    data = np.asarray(list(values), dtype=float)
    data = data[np.isfinite(data)]
    if len(data) < 2:
        return None, None
    if iterations < 100:
        raise ValueError("Bootstrap iterations must be at least 100")
    rng = np.random.default_rng(seed)
    stats_values = np.empty(iterations, dtype=float)
    for index in range(iterations):
        sample = rng.choice(data, size=len(data), replace=True)
        if statistic == "median":
            stats_values[index] = float(np.median(sample))
        elif statistic == "std":
            stats_values[index] = float(np.std(sample, ddof=1))
        else:
            stats_values[index] = float(np.mean(sample))
    alpha = 1 - confidence_level
    low, high = np.quantile(stats_values, [alpha / 2, 1 - alpha / 2])
    return float(low), float(high)


def _normality_check(values: np.ndarray) -> dict[str, Any]:
    finite = values[np.isfinite(values)]
    if len(finite) < 3:
        return {"assumption": "normality", "status": "not_tested", "reason": "fewer than 3 observations"}
    if len(finite) > 5000:
        finite = finite[:5000]
    statistic, p_value = stats.shapiro(finite)
    return {"assumption": "normality", "status": "pass" if p_value >= 0.05 else "review", "statistic": float(statistic), "p_value": float(p_value), "method": "Shapiro-Wilk"}


def _variance_check(group_a: np.ndarray, group_b: np.ndarray) -> dict[str, Any]:
    a = group_a[np.isfinite(group_a)]
    b = group_b[np.isfinite(group_b)]
    if len(a) < 2 or len(b) < 2:
        return {"assumption": "variance_homogeneity", "status": "not_tested", "reason": "insufficient observations"}
    statistic, p_value = stats.levene(a, b, center="median")
    return {"assumption": "variance_homogeneity", "status": "pass" if p_value >= 0.05 else "review", "statistic": float(statistic), "p_value": float(p_value), "method": "Brown-Forsythe/Levene"}


def two_group_disclosure(
    frame: pd.DataFrame,
    *,
    value_column: str,
    group_column: str,
    group_a: str | None = None,
    group_b: str | None = None,
    biological_id_column: str | None = None,
    technical_id_column: str | None = None,
    confidence_level: float = 0.95,
    equal_var: bool = False,
    random_seed: int = 42,
    missing_policy: str = "Complete-case analysis",
    outlier_policy: str = "No automatic outlier exclusion",
    excluded_count: int = 0,
    software_versions: Mapping[str, str] | None = None,
) -> StatisticalDisclosure:
    if value_column not in frame.columns or group_column not in frame.columns:
        raise KeyError("Value and group columns must exist")
    working = frame[[value_column, group_column] + ([biological_id_column] if biological_id_column and biological_id_column in frame.columns else []) + ([technical_id_column] if technical_id_column and technical_id_column in frame.columns else [])].copy()
    missing_count = int(working[[value_column, group_column]].isna().any(axis=1).sum())
    working[value_column] = pd.to_numeric(working[value_column], errors="coerce")
    working = working.dropna(subset=[value_column, group_column])
    groups = list(dict.fromkeys(working[group_column].astype(str).tolist()))
    if len(groups) < 2:
        raise ValueError("At least two groups are required")
    a_name = str(group_a or groups[0])
    b_name = str(group_b or next(group for group in groups if group != a_name))
    a = working.loc[working[group_column].astype(str) == a_name, value_column].to_numpy(dtype=float)
    b = working.loc[working[group_column].astype(str) == b_name, value_column].to_numpy(dtype=float)
    if len(a) < 2 or len(b) < 2:
        raise ValueError("Each selected group requires at least two numeric observations")
    test = stats.ttest_ind(a, b, equal_var=equal_var, nan_policy="omit")
    effect = hedges_g(a, b)
    difference = float(np.mean(a) - np.mean(b))
    standard_error = math.sqrt(np.var(a, ddof=1) / len(a) + np.var(b, ddof=1) / len(b))
    degrees = max(1, len(a) + len(b) - 2)
    critical = float(stats.t.ppf(0.5 + confidence_level / 2, degrees))
    ci = (difference - critical * standard_error, difference + critical * standard_error)
    biological = int(working[biological_id_column].nunique()) if biological_id_column and biological_id_column in working.columns else None
    technical = int(working[technical_id_column].nunique()) if technical_id_column and technical_id_column in working.columns else None
    assumptions = (_normality_check(a), _normality_check(b), _variance_check(a, b))
    warnings = []
    if len(a) < 5 or len(b) < 5:
        warnings.append("Very small group size; effect estimates and assumption tests are unstable.")
    if any(item.get("status") == "review" for item in assumptions):
        warnings.append("At least one model assumption needs review; consider a robust or non-parametric sensitivity analysis.")
    if biological is None:
        warnings.append("Biological replicate identifiers were not supplied.")
    versions = {"numpy": np.__version__, "pandas": pd.__version__, "scipy": stats.__version__ if hasattr(stats, "__version__") else "scipy"}
    versions.update(dict(software_versions or {}))
    return StatisticalDisclosure(
        analysis_name=f"{a_name} versus {b_name}",
        test_name="Student t-test" if equal_var else "Welch t-test",
        null_hypothesis=f"Mean {value_column} is equal between {a_name} and {b_name}",
        alternative_hypothesis=f"Mean {value_column} differs between {a_name} and {b_name}",
        sample_count=int(len(a) + len(b)),
        biological_replicates=biological,
        technical_replicates=technical,
        groups=(a_name, b_name),
        effect_measure="Hedges g; mean difference confidence interval",
        effect_size=effect,
        confidence_level=confidence_level,
        confidence_interval=(float(ci[0]), float(ci[1])),
        p_value=float(test.pvalue),
        adjusted_p_value=None,
        multiple_testing_method="Not applicable to one comparison",
        missing_count=missing_count,
        excluded_count=int(excluded_count),
        missing_policy=missing_policy,
        outlier_policy=outlier_policy,
        assumptions=assumptions,
        random_seed=random_seed,
        software_versions=versions,
        data_hash=dataframe_hash(working),
        warnings=tuple(warnings),
    )


def infer_visual_statistics(frame: pd.DataFrame, *, source_count: int | None = None) -> dict[str, Any]:
    """Return a compact, truthful statistical footer for arbitrary visual data."""
    if frame is None:
        frame = pd.DataFrame()
    numeric = frame.select_dtypes(include=[np.number])
    missing = int(frame.isna().sum().sum()) if not frame.empty else 0
    output: dict[str, Any] = {
        "Displayed rows": int(len(frame)),
        "Source rows": int(source_count) if source_count is not None else int(len(frame)),
        "Variables": int(len(frame.columns)),
        "Numeric variables": int(len(numeric.columns)),
        "Missing cells": missing,
        "Data hash": dataframe_hash(frame)[:16] if not frame.empty else "empty",
    }
    if not numeric.empty:
        output["Finite numeric cells"] = int(np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan)).sum())
    return output


def disclosure_from_mapping(mapping: Mapping[str, Any]) -> StatisticalDisclosure:
    values = dict(mapping)
    values["groups"] = tuple(values.get("groups") or ())
    values["assumptions"] = tuple(values.get("assumptions") or ())
    values["warnings"] = tuple(values.get("warnings") or ())
    values["confidence_interval"] = tuple(values.get("confidence_interval") or (None, None))
    return StatisticalDisclosure(**values)


__all__ = [
    "StatisticalDisclosure",
    "benjamini_hochberg",
    "bootstrap_confidence_interval",
    "cohen_d",
    "dataframe_hash",
    "disclosure_from_mapping",
    "hedges_g",
    "infer_visual_statistics",
    "two_group_disclosure",
]
