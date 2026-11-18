from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

Task = Literal["classification", "regression"]


@dataclass(frozen=True)
class AssuranceResult:
    task: Task
    metrics: pd.DataFrame
    calibration: pd.DataFrame
    subgroup_audit: pd.DataFrame
    ood_scores: pd.DataFrame
    explanation_stability: pd.DataFrame
    counterfactuals: pd.DataFrame
    feature_effects: pd.DataFrame
    release_gate: dict[str, Any]
    manifest: dict[str, Any]


def infer_task(target: pd.Series) -> Task:
    non_missing = target.dropna()
    if non_missing.empty:
        raise ValueError("Target column contains no usable values.")
    unique = non_missing.nunique()
    if pd.api.types.is_bool_dtype(non_missing) or unique <= max(12, int(np.sqrt(len(non_missing)))):
        return "classification"
    return "regression"


def _feature_columns(frame: pd.DataFrame, target: str, group: str | None) -> list[str]:
    excluded = {target}
    if group:
        excluded.add(group)
    return [column for column in frame.columns if column not in excluded]


def _build_pipeline(features: pd.DataFrame, task: Task, random_state: int) -> Pipeline:
    numeric = list(features.select_dtypes(include=[np.number, "bool"]).columns)
    categorical = [column for column in features.columns if column not in numeric]
    transformers: list[tuple[str, Any, list[str]]] = []
    if numeric:
        transformers.append(
            (
                "numeric",
                Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]),
                numeric,
            )
        )
    if categorical:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False, max_categories=50)),
                    ]
                ),
                categorical,
            )
        )
    if not transformers:
        raise ValueError("No feature columns are available for assurance analysis.")
    preprocessor = ColumnTransformer(transformers, remainder="drop", verbose_feature_names_out=False)
    model: Any
    if task == "classification":
        model = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=random_state)
    else:
        model = Ridge(alpha=1.0)
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def _binary_target(target: pd.Series) -> tuple[pd.Series, dict[str, int]]:
    labels = sorted(str(value) for value in target.dropna().unique())
    if len(labels) != 2:
        raise ValueError("Model assurance classification currently requires exactly two target classes.")
    mapping = {label: index for index, label in enumerate(labels)}
    return target.astype(str).map(mapping), mapping


def _classification_metrics(y_true: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    prediction = (probability >= 0.5).astype(int)
    metrics = {
        "roc_auc": float(roc_auc_score(y_true, probability)) if len(np.unique(y_true)) == 2 else np.nan,
        "accuracy": float(accuracy_score(y_true, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, prediction)),
        "f1": float(f1_score(y_true, prediction, zero_division=0)),
        "brier": float(brier_score_loss(y_true, probability)),
    }
    return metrics


def _regression_metrics(y_true: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    return {
        "rmse": float(np.sqrt(mean_squared_error(y_true, prediction))),
        "mae": float(mean_absolute_error(y_true, prediction)),
        "r2": float(r2_score(y_true, prediction)),
    }


def calibration_table(y_true: np.ndarray, probability: np.ndarray, bins: int = 10) -> pd.DataFrame:
    edges = np.linspace(0, 1, bins + 1)
    bucket = np.clip(np.digitize(probability, edges, right=True) - 1, 0, bins - 1)
    rows: list[dict[str, Any]] = []
    for index in range(bins):
        mask = bucket == index
        if not mask.any():
            continue
        observed = float(np.mean(y_true[mask]))
        predicted = float(np.mean(probability[mask]))
        rows.append(
            {
                "bin": index + 1,
                "n": int(mask.sum()),
                "predicted_probability": predicted,
                "observed_rate": observed,
                "absolute_gap": abs(predicted - observed),
            }
        )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        total = frame["n"].sum()
        frame.attrs["expected_calibration_error"] = float((frame["n"] * frame["absolute_gap"]).sum() / total)
    return frame


def _subgroup_audit(
    task: Task,
    y_true: np.ndarray,
    prediction: np.ndarray,
    groups: pd.Series | None,
) -> pd.DataFrame:
    if groups is None:
        return pd.DataFrame()
    group_values = groups.reset_index(drop=True).astype(str)
    rows: list[dict[str, Any]] = []
    for label, indices in group_values.groupby(group_values).groups.items():
        idx = np.asarray(list(indices), dtype=int)
        if len(idx) < 3:
            rows.append({"group": label, "n": len(idx), "status": "too_small_for_stable_metric"})
            continue
        if task == "classification":
            metrics = _classification_metrics(y_true[idx], prediction[idx])
        else:
            metrics = _regression_metrics(y_true[idx], prediction[idx])
        rows.append({"group": label, "n": len(idx), "status": "computed", **metrics})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    primary = "balanced_accuracy" if task == "classification" else "mae"
    if primary in frame.columns:
        valid = frame[primary].dropna()
        disparity = float(valid.max() - valid.min()) if len(valid) > 1 else 0.0
        frame["primary_metric"] = primary
        frame["max_group_disparity"] = disparity
    return frame


def _transformed_feature_names(pipeline: Pipeline) -> list[str]:
    preprocessor = pipeline.named_steps["preprocessor"]
    try:
        return list(preprocessor.get_feature_names_out())
    except Exception:
        model = pipeline.named_steps["model"]
        count = int(np.asarray(getattr(model, "coef_", np.empty((1, 0)))).shape[-1])
        return [f"feature_{index}" for index in range(count)]


def _feature_effects(pipeline: Pipeline) -> pd.DataFrame:
    model = pipeline.named_steps["model"]
    coefficients = np.asarray(model.coef_)
    if coefficients.ndim == 2:
        coefficients = coefficients[0]
    names = _transformed_feature_names(pipeline)
    count = min(len(names), len(coefficients))
    frame = pd.DataFrame(
        {
            "feature": names[:count],
            "coefficient": coefficients[:count],
            "absolute_effect": np.abs(coefficients[:count]),
            "direction": np.where(coefficients[:count] >= 0, "positive", "negative"),
        }
    )
    return frame.sort_values("absolute_effect", ascending=False).reset_index(drop=True)


def _explanation_stability(
    base_pipeline: Pipeline,
    x_train: pd.DataFrame,
    y_train: pd.Series,
    *,
    repeats: int,
    random_state: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    base = clone(base_pipeline).fit(x_train, y_train)
    base_effect = _feature_effects(base).set_index("feature")["absolute_effect"]
    rows: list[dict[str, Any]] = []
    for repeat in range(repeats):
        indices = rng.integers(0, len(x_train), len(x_train))
        sampled_x = x_train.iloc[indices]
        sampled_y = y_train.iloc[indices]
        if sampled_y.nunique() < 2 and isinstance(base.named_steps["model"], LogisticRegression):
            continue
        fitted = clone(base_pipeline).fit(sampled_x, sampled_y)
        effect = _feature_effects(fitted).set_index("feature")["absolute_effect"]
        common = base_effect.index.intersection(effect.index)
        correlation = np.nan
        if len(common) >= 2:
            correlation = float(spearmanr(base_effect.loc[common], effect.loc[common]).statistic)
        top_base = set(base_effect.nlargest(min(10, len(base_effect))).index)
        top_repeat = set(effect.nlargest(min(10, len(effect))).index)
        overlap = len(top_base & top_repeat) / max(len(top_base | top_repeat), 1)
        rows.append(
            {
                "bootstrap_repeat": repeat + 1,
                "rank_correlation": correlation,
                "top10_jaccard": float(overlap),
                "features_compared": len(common),
            }
        )
    return pd.DataFrame(rows)


def _ood_scores(pipeline: Pipeline, x_train: pd.DataFrame, x_test: pd.DataFrame) -> pd.DataFrame:
    transformed_train = np.asarray(pipeline.named_steps["preprocessor"].transform(x_train), dtype=float)
    transformed_test = np.asarray(pipeline.named_steps["preprocessor"].transform(x_test), dtype=float)
    center = np.nanmedian(transformed_train, axis=0)
    mad = np.nanmedian(np.abs(transformed_train - center), axis=0)
    scale = np.where(mad > 1e-9, 1.4826 * mad, np.nanstd(transformed_train, axis=0))
    scale = np.where(scale > 1e-9, scale, 1.0)
    train_distance = np.sqrt(np.mean(((transformed_train - center) / scale) ** 2, axis=1))
    test_distance = np.sqrt(np.mean(((transformed_test - center) / scale) ** 2, axis=1))
    threshold = float(np.quantile(train_distance, 0.99)) if len(train_distance) else np.inf
    return pd.DataFrame(
        {
            "row": np.arange(len(test_distance)),
            "robust_ood_score": test_distance,
            "ood_threshold_99pct_train": threshold,
            "is_ood": test_distance > threshold,
        }
    )


def _counterfactuals(
    pipeline: Pipeline,
    x_test: pd.DataFrame,
    probability: np.ndarray,
    max_rows: int = 25,
) -> pd.DataFrame:
    model = pipeline.named_steps["model"]
    if not isinstance(model, LogisticRegression):
        return pd.DataFrame()
    transformed = np.asarray(pipeline.named_steps["preprocessor"].transform(x_test), dtype=float)
    coef = np.asarray(model.coef_[0], dtype=float)
    norm_sq = float(np.dot(coef, coef))
    if norm_sq <= 1e-12:
        return pd.DataFrame()
    names = _transformed_feature_names(pipeline)
    logit = transformed @ coef + float(model.intercept_[0])
    rows: list[dict[str, Any]] = []
    uncertain = np.argsort(np.abs(probability - 0.5))[: min(max_rows, len(probability))]
    for row_index in uncertain:
        delta = (-logit[row_index]) * coef / norm_sq
        changed = np.argsort(np.abs(delta))[::-1][:3]
        changes = [f"{names[index]}:{delta[index]:+.3f}" for index in changed if index < len(names)]
        rows.append(
            {
                "test_row": int(row_index),
                "current_probability": float(probability[row_index]),
                "linear_boundary_distance": float(abs(logit[row_index]) / np.sqrt(norm_sq)),
                "suggested_standardized_changes": "; ".join(changes),
                "status": "local_linear_candidate_not_actionable_without_domain_review",
            }
        )
    return pd.DataFrame(rows)


def run_assurance_suite(
    frame: pd.DataFrame,
    *,
    target_column: str,
    group_column: str | None = None,
    task: Task | None = None,
    test_size: float = 0.25,
    random_state: int = 42,
    stability_repeats: int = 8,
) -> AssuranceResult:
    if target_column not in frame.columns:
        raise ValueError(f"Target column not found: {target_column}")
    working = frame.dropna(subset=[target_column]).reset_index(drop=True).copy()
    if len(working) < 20:
        raise ValueError("At least 20 labelled rows are required for a defensible assurance split.")
    task = task or infer_task(working[target_column])
    feature_columns = _feature_columns(working, target_column, group_column)
    if not feature_columns:
        raise ValueError("No predictor columns remain after excluding target/group columns.")
    x = working[feature_columns].copy()
    label_mapping: dict[str, int] | None = None
    if task == "classification":
        y, label_mapping = _binary_target(working[target_column])
        stratify = y
    else:
        y = pd.to_numeric(working[target_column], errors="coerce")
        usable = y.notna()
        x = x.loc[usable].reset_index(drop=True)
        working = working.loc[usable].reset_index(drop=True)
        y = y.loc[usable].reset_index(drop=True)
        stratify = None
    indices = np.arange(len(working))
    train_idx, test_idx = train_test_split(
        indices,
        test_size=test_size,
        random_state=random_state,
        stratify=stratify if task == "classification" and pd.Series(stratify).value_counts().min() >= 2 else None,
    )
    x_train, x_test = x.iloc[train_idx].copy(), x.iloc[test_idx].copy()
    y_train, y_test = y.iloc[train_idx].copy(), y.iloc[test_idx].copy()
    pipeline = _build_pipeline(x_train, task, random_state).fit(x_train, y_train)
    if task == "classification":
        prediction = pipeline.predict_proba(x_test)[:, 1]
        metric_values = _classification_metrics(y_test.to_numpy(int), prediction)
        calibration = calibration_table(y_test.to_numpy(int), prediction)
    else:
        prediction = pipeline.predict(x_test)
        metric_values = _regression_metrics(y_test.to_numpy(float), prediction)
        calibration = pd.DataFrame()
    metrics = pd.DataFrame([{"split": "held_out_test", **metric_values}])
    groups = working.iloc[test_idx][group_column] if group_column and group_column in working.columns else None
    subgroup = _subgroup_audit(task, y_test.to_numpy(), np.asarray(prediction), groups)
    ood = _ood_scores(pipeline, x_train, x_test)
    stability = _explanation_stability(
        _build_pipeline(x_train, task, random_state),
        x_train,
        y_train,
        repeats=max(3, int(stability_repeats)),
        random_state=random_state,
    )
    effects = _feature_effects(pipeline)
    counterfactuals = _counterfactuals(pipeline, x_test, np.asarray(prediction)) if task == "classification" else pd.DataFrame()

    blockers: list[str] = []
    if task == "classification":
        ece = float(calibration.attrs.get("expected_calibration_error", np.nan))
        if np.isfinite(ece) and ece > 0.10:
            blockers.append(f"Expected calibration error is {ece:.3f} (>0.10)")
    if not subgroup.empty and "max_group_disparity" in subgroup.columns:
        disparity = float(subgroup["max_group_disparity"].dropna().max())
        if disparity > 0.15:
            blockers.append(f"Subgroup performance disparity is {disparity:.3f} (>0.15)")
    if not ood.empty and float(ood["is_ood"].mean()) > 0.10:
        blockers.append("More than 10% of held-out rows are outside the training distribution")
    if not stability.empty and float(stability["top10_jaccard"].median()) < 0.50:
        blockers.append("Feature explanation top-10 overlap is below 0.50")
    blockers.extend(
        [
            "Independent external validation cohort not attached",
            "Explanations describe model behaviour and do not establish biological causality",
            "Counterfactual suggestions require feasibility and safety review",
        ]
    )
    release_gate = {
        "assurance_review_ready": True,
        "production_release_ready": False,
        "blockers": blockers,
        "boundary": "Model explanations are conditional on the fitted model, data and preprocessing; they do not establish causality or clinical evidence.",
    }
    digest = pd.util.hash_pandas_object(working.astype("string").fillna(""), index=True).values.tobytes()
    manifest = {
        "schema": "biointel.step121.model_assurance.v1",
        "task": task,
        "rows": len(working),
        "features": feature_columns,
        "target": target_column,
        "group": group_column,
        "test_size": test_size,
        "random_state": random_state,
        "label_mapping": label_mapping,
        "input_sha256": sha256(digest).hexdigest(),
        "model": type(pipeline.named_steps["model"]).__name__,
        "production_release_ready": False,
    }
    return AssuranceResult(
        task=task,
        metrics=metrics,
        calibration=calibration,
        subgroup_audit=subgroup,
        ood_scores=ood,
        explanation_stability=stability,
        counterfactuals=counterfactuals,
        feature_effects=effects,
        release_gate=release_gate,
        manifest=manifest,
    )
