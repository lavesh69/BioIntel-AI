from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, mannwhitneyu, ttest_ind
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, cross_val_score
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

from biointel.neuro_cns.schemas import table_quality_report


def _bh_fdr(p_values: np.ndarray) -> np.ndarray:
    values = np.asarray(p_values, dtype=float)
    n = len(values)
    order = np.argsort(values)
    ranked = values[order]
    adjusted = np.empty(n, dtype=float)
    running = 1.0
    for position in range(n - 1, -1, -1):
        rank = position + 1
        candidate = ranked[position] * n / rank
        running = min(running, candidate)
        adjusted[order[position]] = min(1.0, running)
    return adjusted


def _batch_center(frame: pd.DataFrame, batches: pd.Series) -> pd.DataFrame:
    corrected = frame.copy()
    global_means = corrected.mean(axis=0)
    for batch in batches.dropna().unique():
        mask = batches == batch
        if int(mask.sum()) < 2:
            continue
        corrected.loc[mask] = corrected.loc[mask] - corrected.loc[mask].mean(axis=0) + global_means
    return corrected


def _bootstrap_effect_ci(a: np.ndarray, b: np.ndarray, rng: np.random.Generator, iterations: int) -> tuple[float, float, float]:
    effects: list[float] = []
    for _ in range(iterations):
        a_sample = rng.choice(a, size=len(a), replace=True)
        b_sample = rng.choice(b, size=len(b), replace=True)
        pooled = math.sqrt(max(((len(a_sample) - 1) * float(a_sample.var(ddof=1)) + (len(b_sample) - 1) * float(b_sample.var(ddof=1))) / max(len(a_sample) + len(b_sample) - 2, 1), 1e-12))
        effects.append(float((b_sample.mean() - a_sample.mean()) / pooled))
    values = np.asarray(effects, dtype=float)
    return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5)), float(np.mean(np.sign(values) == np.sign(np.median(values))))


def biomarker_discovery(
    frame: pd.DataFrame,
    group_column: str,
    *,
    batch_column: str | None = None,
    exclude_columns: Iterable[str] = (),
    minimum_non_missing_fraction: float = 0.70,
    bootstrap_iterations: int = 100,
    random_state: int = 42,
) -> pd.DataFrame:
    if group_column not in frame.columns:
        raise ValueError(f"Group column {group_column!r} is missing.")
    if not 0 < minimum_non_missing_fraction <= 1:
        raise ValueError("minimum_non_missing_fraction must be in (0, 1].")
    groups = frame[group_column].dropna().astype(str)
    unique = list(dict.fromkeys(groups.tolist()))
    if len(unique) != 2:
        raise ValueError("Exploratory biomarker ranking currently requires exactly two groups.")
    excluded = {group_column, *exclude_columns}
    if batch_column:
        excluded.add(batch_column)
    numeric = frame.drop(columns=list(excluded), errors="ignore").select_dtypes(include=[np.number]).copy()
    if numeric.empty:
        numeric = frame.drop(columns=list(excluded), errors="ignore").apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")
    non_missing = numeric.notna().mean(axis=0)
    numeric = numeric.loc[:, non_missing >= minimum_non_missing_fraction]
    if numeric.empty:
        raise ValueError("No numeric biomarker features passed the non-missing-data threshold.")
    if batch_column and batch_column in frame.columns:
        numeric = _batch_center(numeric, frame[batch_column].astype(str))
    labels = frame[group_column].astype(str)
    mask_a = labels == unique[0]
    mask_b = labels == unique[1]
    y_all = (labels == unique[1]).astype(int).to_numpy()
    rng = np.random.default_rng(random_state)
    rows: list[dict[str, Any]] = []
    for feature in numeric.columns:
        series = pd.to_numeric(numeric[feature], errors="coerce")
        a = series.loc[mask_a].dropna().to_numpy(float)
        b = series.loc[mask_b].dropna().to_numpy(float)
        if len(a) < 3 or len(b) < 3:
            continue
        mean_a, mean_b = float(a.mean()), float(b.mean())
        variance = ((len(a) - 1) * float(a.var(ddof=1)) + (len(b) - 1) * float(b.var(ddof=1))) / max(len(a) + len(b) - 2, 1)
        pooled = math.sqrt(max(variance, 1e-12))
        effect = (mean_b - mean_a) / pooled
        test = ttest_ind(a, b, equal_var=False, nan_policy="omit")
        try:
            mw_p = float(mannwhitneyu(a, b, alternative="two-sided").pvalue)
        except ValueError:
            mw_p = 1.0
        valid = series.notna().to_numpy()
        combined = series.to_numpy(float)[valid]
        y = y_all[valid]
        try:
            auc = float(roc_auc_score(y, combined))
            direction_adjusted_auc = max(auc, 1.0 - auc)
        except ValueError:
            direction_adjusted_auc = 0.5
        cv_auc = 0.5
        if len(np.unique(y)) == 2 and min(np.bincount(y)) >= 3:
            splits = min(5, int(min(np.bincount(y))))
            model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced", random_state=random_state))
            cv = StratifiedKFold(n_splits=splits, shuffle=True, random_state=random_state)
            try:
                cv_auc = float(np.mean(cross_val_score(model, combined.reshape(-1, 1), y, scoring="roc_auc", cv=cv)))
                cv_auc = max(cv_auc, 1.0 - cv_auc)
            except Exception:
                cv_auc = 0.5
        ci_low, ci_high, direction_stability = _bootstrap_effect_ci(a, b, rng, max(20, int(bootstrap_iterations)))
        rows.append({
            "feature": str(feature),
            f"mean_{unique[0]}": round(mean_a, 6),
            f"mean_{unique[1]}": round(mean_b, 6),
            "cohens_d": round(effect, 6),
            "effect_ci_95_low": round(ci_low, 6),
            "effect_ci_95_high": round(ci_high, 6),
            "effect_direction_stability": round(direction_stability, 6),
            "absolute_effect": round(abs(effect), 6),
            "univariate_auc": round(direction_adjusted_auc, 6),
            "cross_validated_auc": round(cv_auc, 6),
            "p_value_welch": float(test.pvalue) if math.isfinite(float(test.pvalue)) else 1.0,
            "p_value_mann_whitney": mw_p,
            "n_group_a": len(a),
            "n_group_b": len(b),
            "missing_fraction": round(float(series.isna().mean()), 6),
            "batch_centered": bool(batch_column and batch_column in frame.columns),
        })
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result["p_value"] = result[["p_value_welch", "p_value_mann_whitney"]].max(axis=1)
    result["fdr_bh"] = _bh_fdr(result["p_value"].to_numpy(float))
    result["exploratory_rank_score"] = (
        0.30 * result["absolute_effect"].clip(upper=3) / 3
        + 0.25 * ((result["cross_validated_auc"] - 0.5).clip(lower=0) / 0.5)
        + 0.15 * ((result["univariate_auc"] - 0.5).clip(lower=0) / 0.5)
        + 0.15 * (1.0 - result["fdr_bh"].clip(upper=1))
        + 0.15 * result["effect_direction_stability"].clip(0, 1)
    )
    quality = table_quality_report(frame)
    result["input_fingerprint_sha256"] = quality.fingerprint_sha256
    result["input_missing_fraction"] = quality.missing_fraction
    result["scientific_boundary"] = "Discovery-only ranking with internal cross-validation; independent cohort validation and leakage review required."
    return result.sort_values(["exploratory_rank_score", "fdr_bh"], ascending=[False, True], ignore_index=True)


def biomarker_discovery_workflow(
    frame: pd.DataFrame,
    group_column: str,
    *,
    batch_column: str | None = None,
    covariate_columns: Iterable[str] = (),
    identifier_column: str | None = None,
    minimum_non_missing_fraction: float = 0.70,
    selected_feature_count: int = 10,
    bootstrap_iterations: int = 100,
    permutation_iterations: int = 20,
    random_state: int = 42,
) -> dict[str, Any]:
    """Run leakage-aware exploratory biomarker discovery and validation.

    Feature selection is performed inside each cross-validation fold. Results
    remain discovery evidence and are not an independently validated model.
    """
    covariates = [str(column) for column in covariate_columns if str(column) in frame.columns]
    ranking = biomarker_discovery(
        frame,
        group_column,
        batch_column=batch_column,
        exclude_columns=[column for column in [identifier_column, *covariates] if column],
        minimum_non_missing_fraction=minimum_non_missing_fraction,
        bootstrap_iterations=bootstrap_iterations,
        random_state=random_state,
    )
    if ranking.empty:
        return {
            "feature_ranking": ranking,
            "model_metrics": {},
            "calibration_table": pd.DataFrame(),
            "permutation_distribution": pd.DataFrame(),
            "batch_association": {},
            "missingness": pd.DataFrame(),
            "warnings": ["No features met the analysis requirements."],
            "scientific_boundary": "Discovery-only workflow; independent validation is required.",
        }

    working = frame.loc[frame[group_column].notna()].reset_index(drop=True).copy()
    labels = working[group_column].astype(str)
    classes = list(dict.fromkeys(labels.tolist()))
    if len(classes) != 2:
        raise ValueError("Exactly two non-missing groups are required.")
    y = (labels == classes[1]).astype(int).to_numpy()
    feature_names = [feature for feature in ranking["feature"].astype(str).tolist() if feature in working.columns]
    numeric = working[feature_names].apply(pd.to_numeric, errors="coerce")
    if numeric.shape[1] < 1:
        raise ValueError("No ranked numeric features are available for multivariate validation.")
    minimum_class = int(np.bincount(y).min())
    if minimum_class < 3:
        raise ValueError("At least three samples per group are required for cross-validation.")
    splits = min(5, minimum_class)
    selected = max(1, min(int(selected_feature_count), numeric.shape[1]))
    pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("feature_selection", SelectKBest(score_func=f_classif, k=selected)),
        ("model", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=random_state)),
    ])
    cv = StratifiedKFold(n_splits=splits, shuffle=True, random_state=random_state)
    probabilities = cross_val_predict(pipeline, numeric, y, cv=cv, method="predict_proba")[:, 1]
    auc = float(roc_auc_score(y, probabilities))
    brier = float(brier_score_loss(y, probabilities))
    direction_auc = max(auc, 1.0 - auc)

    calibration = pd.DataFrame({"observed": y, "predicted_probability": probabilities})
    bin_count = min(5, max(2, len(calibration) // 4))
    try:
        calibration["probability_bin"] = pd.qcut(calibration["predicted_probability"], q=bin_count, duplicates="drop")
        calibration_table = (
            calibration.groupby("probability_bin", observed=True)
            .agg(sample_count=("observed", "size"), mean_predicted_probability=("predicted_probability", "mean"), observed_positive_fraction=("observed", "mean"))
            .reset_index()
        )
        calibration_table["probability_bin"] = calibration_table["probability_bin"].astype(str)
    except ValueError:
        calibration_table = pd.DataFrame([{
            "probability_bin": "all",
            "sample_count": len(calibration),
            "mean_predicted_probability": float(calibration["predicted_probability"].mean()),
            "observed_positive_fraction": float(calibration["observed"].mean()),
        }])

    rng = np.random.default_rng(random_state)
    null_scores: list[float] = []
    for iteration in range(max(0, int(permutation_iterations))):
        permuted = rng.permutation(y)
        try:
            score = float(np.mean(cross_val_score(pipeline, numeric, permuted, scoring="roc_auc", cv=cv)))
            null_scores.append(max(score, 1.0 - score))
        except Exception:
            continue
    permutation_frame = pd.DataFrame({"iteration": np.arange(1, len(null_scores) + 1), "direction_adjusted_auc": null_scores})
    permutation_p = float((1 + sum(score >= direction_auc for score in null_scores)) / (len(null_scores) + 1)) if null_scores else None

    pipeline.fit(numeric, y)
    selector = pipeline.named_steps["feature_selection"]
    selected_mask = selector.get_support()
    selected_names = np.asarray(feature_names, dtype=object)[selected_mask].tolist()
    coefficients = pipeline.named_steps["model"].coef_[0]
    coefficient_table = pd.DataFrame({
        "feature": selected_names,
        "standardized_logistic_coefficient": coefficients,
        "absolute_coefficient": np.abs(coefficients),
    }).sort_values("absolute_coefficient", ascending=False, ignore_index=True)

    batch_association: dict[str, Any] = {}
    if batch_column and batch_column in working.columns:
        contingency = pd.crosstab(working[batch_column].fillna("Missing").astype(str), labels)
        if contingency.shape[0] >= 2 and contingency.shape[1] == 2:
            chi2, p_value, dof, _ = chi2_contingency(contingency)
            n = float(contingency.to_numpy().sum())
            denom = max(1.0, min(contingency.shape) - 1.0)
            cramers_v = math.sqrt(max(0.0, chi2 / max(n * denom, 1e-12)))
            batch_association = {
                "batch_column": batch_column,
                "chi_square": round(float(chi2), 6),
                "degrees_of_freedom": int(dof),
                "p_value": float(p_value),
                "cramers_v": round(float(cramers_v), 6),
                "confounding_warning": bool(p_value < 0.05 and cramers_v >= 0.20),
                "contingency_table": contingency,
            }

    missingness = numeric.isna().mean().rename("missing_fraction").reset_index().rename(columns={"index": "feature"})
    warnings: list[str] = []
    if len(working) < 30:
        warnings.append("Small sample size: multivariate estimates may be unstable.")
    if numeric.shape[1] >= len(working):
        warnings.append("Feature count is high relative to sample count.")
    if batch_association.get("confounding_warning"):
        warnings.append("Batch is associated with group; corrected and uncorrected sensitivity review is required.")
    if permutation_p is not None and permutation_p > 0.10:
        warnings.append("Cross-validated performance did not clearly exceed the permutation distribution.")
    if direction_auc < 0.65:
        warnings.append("Cross-validated discrimination is weak.")

    quality = table_quality_report(frame, identifier_column)
    return {
        "feature_ranking": ranking,
        "model_metrics": {
            "samples": int(len(working)),
            "candidate_features": int(numeric.shape[1]),
            "selected_features_per_fold": int(selected),
            "cross_validation_folds": int(splits),
            "direction_adjusted_roc_auc": round(float(direction_auc), 6),
            "brier_score": round(float(brier), 6),
            "permutation_p_value": round(float(permutation_p), 6) if permutation_p is not None else None,
            "input_fingerprint_sha256": quality.fingerprint_sha256,
        },
        "selected_feature_coefficients": coefficient_table,
        "calibration_table": calibration_table,
        "permutation_distribution": permutation_frame,
        "batch_association": batch_association,
        "missingness": missingness.sort_values("missing_fraction", ascending=False, ignore_index=True),
        "covariates_reserved_from_feature_selection": covariates,
        "warnings": warnings,
        "scientific_boundary": "Leakage-aware internal cross-validation and permutation testing only; independent cohort, pre-specified analysis and external validation remain required.",
    }
