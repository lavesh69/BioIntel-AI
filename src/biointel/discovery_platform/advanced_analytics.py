from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial import cKDTree

from .models import PlatformValidationError

RESEARCH_ONLY = (
    "Research-use analytics only. Clinical, diagnostic, and causal interpretation "
    "requires an independently validated protocol and qualified review."
)


def _require(frame: pd.DataFrame, columns: Sequence[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise PlatformValidationError("Missing required columns: " + ", ".join(missing))


def _finite(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def build_cohort(
    frame: pd.DataFrame,
    criteria: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Apply structured criteria without executing user supplied expressions."""

    if len(frame) > 2_000_000:
        raise PlatformValidationError("Cohort builder is limited to 2,000,000 rows per operation")
    selected = pd.Series(True, index=frame.index)
    audit_rows = []
    supported = {"eq", "ne", "in", "not_in", "gt", "ge", "lt", "le", "contains", "not_null"}
    for index, criterion in enumerate(criteria, 1):
        field = str(criterion.get("field", "")).strip()
        operator = str(criterion.get("operator", "")).strip().lower()
        value = criterion.get("value")
        if field not in frame.columns:
            raise PlatformValidationError(f"Criterion {index} references unknown field: {field}")
        if operator not in supported:
            raise PlatformValidationError(f"Criterion {index} uses unsupported operator: {operator}")
        series = frame[field]
        if operator == "eq":
            match = series.eq(value)
        elif operator == "ne":
            match = series.ne(value)
        elif operator in {"in", "not_in"}:
            values = value if isinstance(value, (list, tuple, set)) else [value]
            match = series.isin(values)
            if operator == "not_in":
                match = ~match
        elif operator in {"gt", "ge", "lt", "le"}:
            numeric = _finite(series)
            try:
                threshold = float(value)
            except (TypeError, ValueError) as exc:
                raise PlatformValidationError(
                    f"Criterion {index} requires a numeric value"
                ) from exc
            match = {
                "gt": numeric.gt(threshold),
                "ge": numeric.ge(threshold),
                "lt": numeric.lt(threshold),
                "le": numeric.le(threshold),
            }[operator]
        elif operator == "contains":
            match = series.fillna("").astype(str).str.contains(
                str(value), case=False, regex=False
            )
        else:
            match = series.notna()
        before = int(selected.sum())
        selected &= match.fillna(False)
        audit_rows.append(
            {
                "criterion": index,
                "field": field,
                "operator": operator,
                "value": value,
                "rows_before": before,
                "rows_after": int(selected.sum()),
                "rows_excluded": before - int(selected.sum()),
            }
        )
    return {
        "included_index": frame.index[selected].astype(str).tolist(),
        "excluded_index": frame.index[~selected].astype(str).tolist(),
        "included_rows": int(selected.sum()),
        "excluded_rows": int((~selected).sum()),
        "criteria_audit": audit_rows,
        "research_boundary": RESEARCH_ONLY,
    }


def missingness_analysis(frame: pd.DataFrame, *, maximum_patterns: int = 20) -> dict[str, Any]:
    if frame.empty:
        raise PlatformValidationError("Missingness analysis requires at least one row")
    mask = frame.isna()
    columns = [
        {
            "column": str(column),
            "missing_count": int(mask[column].sum()),
            "missing_fraction": float(mask[column].mean()),
        }
        for column in frame.columns
    ]
    encoded = mask.astype(int).astype(str).agg("".join, axis=1)
    patterns = encoded.value_counts().head(maximum_patterns)
    pattern_rows = []
    for pattern, count in patterns.items():
        missing_columns = [
            str(column) for column, flag in zip(frame.columns, pattern) if flag == "1"
        ]
        pattern_rows.append(
            {
                "missing_columns": missing_columns,
                "rows": int(count),
                "fraction": float(count / len(frame)),
            }
        )
    return {
        "columns": sorted(columns, key=lambda row: row["missing_fraction"], reverse=True),
        "patterns": pattern_rows,
        "complete_rows": int((~mask.any(axis=1)).sum()),
        "research_boundary": RESEARCH_ONLY,
    }


def baseline_characteristics(
    frame: pd.DataFrame,
    *,
    group_column: str,
    columns: Sequence[str] | None = None,
) -> dict[str, Any]:
    _require(frame, (group_column,))
    groups = [str(value) for value in frame[group_column].dropna().unique()]
    if len(groups) < 1 or len(groups) > 20:
        raise PlatformValidationError("Baseline analysis requires between 1 and 20 groups")
    selected = [
        column for column in (columns or list(frame.columns))
        if column != group_column and column in frame.columns
    ]
    rows = []
    balance = []
    grouped = frame.assign(_group=frame[group_column].astype(str))
    for column in selected:
        series = frame[column]
        if pd.api.types.is_numeric_dtype(series):
            summaries = {}
            numeric_groups = []
            for group in groups:
                values = _finite(grouped.loc[grouped["_group"].eq(group), column]).dropna()
                numeric_groups.append(values)
                summaries[group] = {
                    "n": int(len(values)),
                    "mean": float(values.mean()) if len(values) else None,
                    "sd": float(values.std(ddof=1)) if len(values) > 1 else None,
                    "median": float(values.median()) if len(values) else None,
                    "q1": float(values.quantile(0.25)) if len(values) else None,
                    "q3": float(values.quantile(0.75)) if len(values) else None,
                }
            rows.append(
                {
                    "variable": str(column),
                    "kind": "numeric",
                    "groups": summaries,
                    "missing": int(series.isna().sum()),
                }
            )
            if len(groups) == 2 and all(len(values) >= 2 for values in numeric_groups):
                left, right = numeric_groups
                pooled = np.sqrt((left.var(ddof=1) + right.var(ddof=1)) / 2)
                smd = (right.mean() - left.mean()) / pooled if pooled > 0 else 0.0
                balance.append(
                    {
                        "variable": str(column),
                        "type": "numeric",
                        "standardized_mean_difference": float(smd),
                        "absolute_imbalance": float(abs(smd)),
                    }
                )
        else:
            distributions = {}
            for group in groups:
                subset = grouped.loc[grouped["_group"].eq(group), column]
                counts = subset.fillna("<missing>").astype(str).value_counts()
                distributions[group] = {
                    key: {"count": int(value), "fraction": float(value / max(1, len(subset)))}
                    for key, value in counts.items()
                }
            rows.append(
                {
                    "variable": str(column),
                    "kind": "categorical",
                    "groups": distributions,
                    "missing": int(series.isna().sum()),
                }
            )
            if len(groups) == 2:
                levels = set(distributions[groups[0]]) | set(distributions[groups[1]])
                maximum = max(
                    (
                        abs(
                            distributions[groups[1]].get(level, {}).get("fraction", 0.0)
                            - distributions[groups[0]].get(level, {}).get("fraction", 0.0)
                        )
                        for level in levels
                    ),
                    default=0.0,
                )
                balance.append(
                    {
                        "variable": str(column),
                        "type": "categorical",
                        "maximum_level_fraction_difference": float(maximum),
                        "absolute_imbalance": float(maximum),
                    }
                )
    return {
        "group_column": group_column,
        "groups": groups,
        "group_sizes": {
            group: int(grouped["_group"].eq(group).sum()) for group in groups
        },
        "characteristics": rows,
        "balance": sorted(
            balance, key=lambda row: row["absolute_imbalance"], reverse=True
        ),
        "research_boundary": RESEARCH_ONLY,
    }


def propensity_support(
    frame: pd.DataFrame,
    *,
    treatment_column: str,
    covariates: Sequence[str],
    seed: int = 42,
) -> dict[str, Any]:
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    _require(frame, (treatment_column, *covariates))
    if not covariates:
        raise PlatformValidationError("At least one propensity covariate is required")
    if len(frame) < 20:
        raise PlatformValidationError("Propensity support requires at least 20 rows")
    data = frame[[treatment_column, *covariates]].copy()
    data = data.dropna(subset=[treatment_column])
    treatment = pd.Categorical(data[treatment_column])
    if len(treatment.categories) != 2:
        raise PlatformValidationError("Treatment must contain exactly two observed groups")
    y = treatment.codes
    numeric_columns = [
        column for column in covariates
        if pd.api.types.is_numeric_dtype(data[column])
    ]
    categorical_columns = [column for column in covariates if column not in numeric_columns]
    transformers = []
    if numeric_columns:
        transformers.append(
            (
                "numeric",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median")),
                        ("scale", StandardScaler()),
                    ]
                ),
                numeric_columns,
            )
        )
    if categorical_columns:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("encode", OneHotEncoder(handle_unknown="ignore", min_frequency=2)),
                    ]
                ),
                categorical_columns,
            )
        )
    model = Pipeline(
        [
            ("preprocess", ColumnTransformer(transformers)),
            (
                "model",
                LogisticRegression(
                    max_iter=2000, random_state=int(seed), class_weight="balanced"
                ),
            ),
        ]
    )
    model.fit(data[list(covariates)], y)
    probability = model.predict_proba(data[list(covariates)])[:, 1]
    clipped = np.clip(probability, 0.01, 0.99)
    prevalence = float(np.mean(y))
    stabilized_weight = np.where(
        y == 1, prevalence / clipped, (1 - prevalence) / (1 - clipped)
    )
    lower = max(float(np.min(probability[y == 0])), float(np.min(probability[y == 1])))
    upper = min(float(np.max(probability[y == 0])), float(np.max(probability[y == 1])))
    outside = (probability < lower) | (probability > upper)
    rows = [
        {
            "row_index": str(index),
            "treatment": str(treatment.categories[code]),
            "propensity_score": float(score),
            "stabilized_weight": float(weight),
            "outside_common_support": bool(flag),
        }
        for index, code, score, weight, flag in zip(
            data.index, y, probability, stabilized_weight, outside
        )
    ]
    return {
        "treatment_levels": [str(value) for value in treatment.categories],
        "covariates": list(covariates),
        "scores": rows,
        "diagnostics": {
            "model_auc_apparent": float(roc_auc_score(y, probability)),
            "common_support": [lower, upper],
            "outside_common_support": int(outside.sum()),
            "weight_p99": float(np.quantile(stabilized_weight, 0.99)),
            "positivity_warning": bool(
                lower >= upper or outside.mean() > 0.1 or np.quantile(stabilized_weight, 0.99) > 10
            ),
        },
        "method": "Logistic propensity support with median/mode imputation, scaling, and one-hot encoding.",
        "research_boundary": (
            RESEARCH_ONLY
            + " Propensity estimates do not prove exchangeability or identify an unbiased causal effect."
        ),
    }


def longitudinal_summary(
    frame: pd.DataFrame,
    *,
    subject_column: str,
    time_column: str,
    value_column: str,
    group_column: str | None = None,
) -> dict[str, Any]:
    required = [subject_column, time_column, value_column]
    if group_column:
        required.append(group_column)
    _require(frame, required)
    data = frame[required].copy()
    data[time_column] = _finite(data[time_column])
    data[value_column] = _finite(data[value_column])
    data = data.dropna(subset=[subject_column, time_column, value_column])
    if data.empty:
        raise PlatformValidationError("No complete longitudinal observations remain")
    subjects = []
    for subject, subset in data.groupby(subject_column):
        subset = subset.sort_values(time_column)
        unique_time = subset[time_column].nunique()
        slope = (
            stats.linregress(subset[time_column], subset[value_column]).slope
            if unique_time >= 2 else np.nan
        )
        subjects.append(
            {
                "subject_id": str(subject),
                "observations": int(len(subset)),
                "timepoints": int(unique_time),
                "baseline": float(subset[value_column].iloc[0]),
                "last": float(subset[value_column].iloc[-1]),
                "change": float(
                    subset[value_column].iloc[-1] - subset[value_column].iloc[0]
                ),
                "slope": float(slope) if np.isfinite(slope) else None,
                "group": str(subset[group_column].iloc[0]) if group_column else "",
            }
        )
    subject_frame = pd.DataFrame(subjects)
    group_rows = []
    if group_column:
        for group, subset in subject_frame.groupby("group"):
            slopes = _finite(subset["slope"]).dropna()
            changes = _finite(subset["change"]).dropna()
            group_rows.append(
                {
                    "group": str(group),
                    "subjects": int(len(subset)),
                    "mean_slope": float(slopes.mean()) if len(slopes) else None,
                    "mean_change": float(changes.mean()) if len(changes) else None,
                }
            )
    return {
        "subjects": subjects,
        "groups": group_rows,
        "excluded_rows": int(len(frame) - len(data)),
        "research_boundary": (
            RESEARCH_ONLY
            + " Subject slopes are descriptive; a prespecified repeated-measures model is required for inference."
        ),
    }


def random_effects_meta_analysis(frame: pd.DataFrame) -> dict[str, Any]:
    _require(frame, ("study_id", "estimate", "standard_error"))
    data = frame[["study_id", "estimate", "standard_error"]].copy()
    data["estimate"] = _finite(data["estimate"])
    data["standard_error"] = _finite(data["standard_error"])
    data = data.dropna()
    data = data.loc[data["standard_error"] > 0]
    if len(data) < 2:
        raise PlatformValidationError("Meta-analysis requires at least two valid studies")
    estimate = data["estimate"].to_numpy(float)
    variance = np.square(data["standard_error"].to_numpy(float))
    fixed_weight = 1 / variance
    fixed = float(np.sum(fixed_weight * estimate) / np.sum(fixed_weight))
    q = float(np.sum(fixed_weight * np.square(estimate - fixed)))
    degrees = len(data) - 1
    c_value = float(np.sum(fixed_weight) - np.sum(np.square(fixed_weight)) / np.sum(fixed_weight))
    tau_squared = max(0.0, (q - degrees) / c_value) if c_value > 0 else 0.0
    random_weight = 1 / (variance + tau_squared)
    pooled = float(np.sum(random_weight * estimate) / np.sum(random_weight))
    pooled_se = float(np.sqrt(1 / np.sum(random_weight)))
    i_squared = max(0.0, (q - degrees) / q * 100) if q > 0 else 0.0
    return {
        "studies": data.to_dict(orient="records"),
        "fixed_effect": fixed,
        "random_effect": pooled,
        "random_effect_ci95": [pooled - 1.96 * pooled_se, pooled + 1.96 * pooled_se],
        "heterogeneity": {
            "q": q,
            "degrees_of_freedom": degrees,
            "q_p_value": float(stats.chi2.sf(q, degrees)),
            "i_squared_percent": float(i_squared),
            "tau_squared": float(tau_squared),
        },
        "method": "Inverse-variance fixed effect and DerSimonian-Laird random effects.",
        "research_boundary": RESEARCH_ONLY,
    }


def imaging_quality_control(frame: pd.DataFrame) -> dict[str, Any]:
    _require(frame, ("image_id", "width", "height"))
    data = frame.copy()
    data["width"] = _finite(data["width"])
    data["height"] = _finite(data["height"])
    data["pixel_count"] = data["width"] * data["height"]
    data["dimension_valid"] = data["width"].gt(0) & data["height"].gt(0)
    if "focus_score" in data:
        data["focus_score"] = _finite(data["focus_score"])
        threshold = float(data["focus_score"].quantile(0.1))
        data["focus_review"] = data["focus_score"].lt(threshold)
    else:
        threshold = None
        data["focus_review"] = False
    if "saturation_fraction" in data:
        saturation = _finite(data["saturation_fraction"])
        data["saturation_review"] = saturation.gt(0.05)
    else:
        data["saturation_review"] = False
    data["qc_status"] = np.where(
        data[["dimension_valid"]].all(axis=1)
        & ~data[["focus_review", "saturation_review"]].any(axis=1),
        "Pass",
        "Review",
    )
    return {
        "image_qc": data.to_dict(orient="records"),
        "summary": {
            "images": int(len(data)),
            "pass": int(data["qc_status"].eq("Pass").sum()),
            "review": int(data["qc_status"].eq("Review").sum()),
            "adaptive_focus_threshold": threshold,
        },
        "research_boundary": (
            RESEARCH_ONLY
            + " QC flags do not constitute validated segmentation, pathology grading, or diagnosis."
        ),
    }


def spatial_neighborhood_analysis(
    frame: pd.DataFrame,
    *,
    x_column: str = "x",
    y_column: str = "y",
    cell_id_column: str = "cell_id",
    cell_type_column: str = "cell_type",
    radius: float = 50.0,
    maximum_edges: int = 100_000,
) -> dict[str, Any]:
    _require(frame, (x_column, y_column, cell_id_column, cell_type_column))
    if radius <= 0:
        raise PlatformValidationError("Spatial radius must be positive")
    data = frame[[cell_id_column, cell_type_column, x_column, y_column]].copy()
    data[x_column] = _finite(data[x_column])
    data[y_column] = _finite(data[y_column])
    data = data.dropna()
    if len(data) < 2:
        raise PlatformValidationError("Spatial analysis requires at least two valid objects")
    if data[cell_id_column].astype(str).duplicated().any():
        raise PlatformValidationError("Spatial object identifiers must be unique")
    coordinates = data[[x_column, y_column]].to_numpy(float)
    pairs = sorted(cKDTree(coordinates).query_pairs(float(radius)))
    truncated = len(pairs) > maximum_edges
    pairs = pairs[:maximum_edges]
    degree = np.zeros(len(data), dtype=int)
    interaction_counts: dict[tuple[str, str], int] = {}
    edges = []
    for left, right in pairs:
        degree[left] += 1
        degree[right] += 1
        left_type = str(data.iloc[left][cell_type_column])
        right_type = str(data.iloc[right][cell_type_column])
        key = tuple(sorted((left_type, right_type)))
        interaction_counts[key] = interaction_counts.get(key, 0) + 1
        distance = float(np.linalg.norm(coordinates[left] - coordinates[right]))
        edges.append(
            {
                "source": str(data.iloc[left][cell_id_column]),
                "target": str(data.iloc[right][cell_id_column]),
                "distance": distance,
            }
        )
    cells = [
        {
            "cell_id": str(row[cell_id_column]),
            "cell_type": str(row[cell_type_column]),
            "neighbors": int(degree[index]),
            "isolated": bool(degree[index] == 0),
        }
        for index, (_, row) in enumerate(data.iterrows())
    ]
    interactions = [
        {
            "cell_type_a": key[0],
            "cell_type_b": key[1],
            "edge_count": count,
            "fraction_of_edges": float(count / max(1, len(pairs))),
        }
        for key, count in sorted(
            interaction_counts.items(), key=lambda item: item[1], reverse=True
        )
    ]
    return {
        "radius": float(radius),
        "objects": cells,
        "edges": edges,
        "interactions": interactions,
        "summary": {
            "objects": int(len(data)),
            "edges": int(len(pairs)),
            "isolated_objects": int((degree == 0).sum()),
            "mean_neighbors": float(degree.mean()),
            "edge_output_truncated": truncated,
        },
        "research_boundary": (
            RESEARCH_ONLY
            + " Neighborhoods are coordinate-and-radius calculations, not validated cell-cell communication."
        ),
    }


__all__ = [
    "RESEARCH_ONLY",
    "baseline_characteristics",
    "build_cohort",
    "imaging_quality_control",
    "longitudinal_summary",
    "missingness_analysis",
    "propensity_support",
    "random_effects_meta_analysis",
    "spatial_neighborhood_analysis",
]
