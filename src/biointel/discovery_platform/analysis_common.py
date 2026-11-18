from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd
from scipy import stats

from .models import PlatformValidationError


def require_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise PlatformValidationError("Missing required columns: " + ", ".join(missing))


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def bh_fdr(values: pd.Series | np.ndarray) -> np.ndarray:
    raw = np.asarray(values, dtype=float)
    output = np.full(raw.shape, np.nan)
    valid = np.flatnonzero(np.isfinite(raw))
    if not len(valid):
        return output
    order = valid[np.argsort(raw[valid])]
    ranked = raw[order] * len(valid) / np.arange(1, len(valid) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    output[order] = np.clip(ranked, 0, 1)
    return output


def standardized_effect(first: np.ndarray, second: np.ndarray) -> float | None:
    first = first[np.isfinite(first)]
    second = second[np.isfinite(second)]
    if len(first) < 2 or len(second) < 2:
        return None
    pooled = np.sqrt(
        ((len(first) - 1) * np.var(first, ddof=1) + (len(second) - 1) * np.var(second, ddof=1))
        / max(1, len(first) + len(second) - 2)
    )
    return float((np.mean(second) - np.mean(first)) / pooled) if pooled > 0 else None


def sequencing_quality(
    frame: pd.DataFrame, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    require_columns(frame, ("sample_id", "mean_quality", "reads", "gc_percent"))
    data = frame.copy()
    thresholds = {
        "minimum_quality": float(parameters.get("minimum_quality", 28)),
        "minimum_reads": int(parameters.get("minimum_reads", 100_000)),
        "maximum_duplication_percent": float(parameters.get("maximum_duplication_percent", 50)),
        "maximum_adapter_percent": float(parameters.get("maximum_adapter_percent", 10)),
        "maximum_contamination_percent": float(parameters.get("maximum_contamination_percent", 5)),
    }
    for column in (
        "mean_quality", "reads", "gc_percent", "duplication_percent",
        "adapter_percent", "contamination_percent",
    ):
        if column in data:
            data[column] = numeric(data[column])
    data["quality_pass"] = data["mean_quality"] >= thresholds["minimum_quality"]
    data["depth_pass"] = data["reads"] >= thresholds["minimum_reads"]
    data["duplication_pass"] = (
        data.get("duplication_percent", pd.Series(0.0, index=data.index))
        <= thresholds["maximum_duplication_percent"]
    )
    data["adapter_pass"] = (
        data.get("adapter_percent", pd.Series(0.0, index=data.index))
        <= thresholds["maximum_adapter_percent"]
    )
    data["contamination_pass"] = (
        data.get("contamination_percent", pd.Series(0.0, index=data.index))
        <= thresholds["maximum_contamination_percent"]
    )
    checks = [
        "quality_pass", "depth_pass", "duplication_pass", "adapter_pass",
        "contamination_pass",
    ]
    data["failed_checks"] = (~data[checks]).sum(axis=1)
    data["qc_status"] = np.select(
        [data["failed_checks"] == 0, data["failed_checks"] <= 2],
        ["Pass", "Review"],
        default="Fail",
    )
    data["recommendation"] = np.select(
        [
            ~data["contamination_pass"],
            ~data["adapter_pass"] & data["quality_pass"],
            ~data["depth_pass"],
            data["qc_status"].eq("Pass"),
        ],
        [
            "Review contamination and consider sample exclusion",
            "Compare trimming against the untrimmed library",
            "Assess resequencing or exclude from depth-sensitive analyses",
            "Proceed with documented QC thresholds",
        ],
        default="Review all failed QC dimensions before rescue",
    )
    return {
        "sample_qc": data.to_dict(orient="records"),
        "summary": {
            "samples": len(data),
            "pass": int(data["qc_status"].eq("Pass").sum()),
            "review": int(data["qc_status"].eq("Review").sum()),
            "fail": int(data["qc_status"].eq("Fail").sum()),
        },
        "thresholds": thresholds,
        "scientific_boundary": "QC recommendations are rule-based and require operator review.",
    }


def alignment_mapping(
    frame: pd.DataFrame, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    require_columns(frame, ("sample_id", "total_reads", "mapped_reads", "reference_build"))
    data = frame.copy()
    for column in ("total_reads", "mapped_reads", "properly_paired", "coverage", "junction_support"):
        if column in data:
            data[column] = numeric(data[column])
    data["mapping_rate"] = data["mapped_reads"] / data["total_reads"].replace(0, np.nan)
    data["proper_pair_rate"] = (
        data.get("properly_paired", pd.Series(np.nan, index=data.index))
        / data["total_reads"].replace(0, np.nan)
    )
    minimum_mapping = float(parameters.get("minimum_mapping_rate", 0.8))
    minimum_coverage = float(parameters.get("minimum_coverage", 10))
    minimum_junction = float(parameters.get("minimum_junction_support", 0))
    expected_reference = str(parameters.get("reference_build", "")).strip()
    data["mapping_pass"] = data["mapping_rate"] >= minimum_mapping
    data["coverage_pass"] = (
        data.get("coverage", pd.Series(minimum_coverage, index=data.index)) >= minimum_coverage
    )
    data["junction_pass"] = (
        data.get("junction_support", pd.Series(minimum_junction, index=data.index))
        >= minimum_junction
    )
    data["reference_pass"] = (
        data["reference_build"].astype(str).eq(expected_reference)
        if expected_reference
        else True
    )
    data["qc_status"] = np.where(
        data[["mapping_pass", "coverage_pass", "junction_pass", "reference_pass"]].all(axis=1),
        "Pass",
        "Review",
    )
    references = sorted(data["reference_build"].astype(str).dropna().unique())
    return {
        "sample_qc": data.to_dict(orient="records"),
        "reference_compatibility": {
            "observed": references,
            "expected": expected_reference or "Not supplied",
            "consistent": len(references) == 1 and (not expected_reference or references[0] == expected_reference),
        },
        "summary": {
            "median_mapping_rate": float(data["mapping_rate"].median()),
            "samples_for_review": int(data["qc_status"].eq("Review").sum()),
        },
    }


def differential_expression(
    frame: pd.DataFrame, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    require_columns(frame, ("feature_id", "sample_id", "group", "value"))
    data = frame.copy()
    data["value"] = numeric(data["value"])
    data = data.dropna(subset=["feature_id", "sample_id", "group", "value"])
    groups = list(dict.fromkeys(data["group"].astype(str)))
    if len(groups) != 2:
        raise PlatformValidationError("Differential expression currently requires exactly two groups")
    minimum_replicates = int(parameters.get("minimum_replicates", 3))
    counts = data.groupby("group")["sample_id"].nunique()
    if (counts < minimum_replicates).any():
        raise PlatformValidationError(
            f"Each group requires at least {minimum_replicates} independent samples"
        )
    pseudocount = float(parameters.get("pseudocount", 1.0))
    records = []
    for feature_id, subset in data.groupby("feature_id", sort=False):
        first = subset.loc[subset["group"].astype(str) == groups[0], "value"].to_numpy(float)
        second = subset.loc[subset["group"].astype(str) == groups[1], "value"].to_numpy(float)
        if len(first) < minimum_replicates or len(second) < minimum_replicates:
            continue
        test = stats.ttest_ind(second, first, equal_var=False, nan_policy="omit")
        records.append(
            {
                "feature_id": str(feature_id),
                "group_a": groups[0], "group_b": groups[1],
                "mean_a": float(np.mean(first)), "mean_b": float(np.mean(second)),
                "log2_fold_change": float(
                    np.log2((np.mean(second) + pseudocount) / (np.mean(first) + pseudocount))
                ),
                "p_value": float(test.pvalue) if np.isfinite(test.pvalue) else None,
                "standardized_effect": standardized_effect(first, second),
                "replicates_a": len(first), "replicates_b": len(second),
            }
        )
    result = pd.DataFrame(records)
    if result.empty:
        raise PlatformValidationError("No features had enough finite replicate values")
    result["fdr"] = bh_fdr(result["p_value"])
    alpha = float(parameters.get("fdr", 0.05))
    minimum_effect = float(parameters.get("minimum_abs_log2fc", 1.0))
    result["significant"] = (
        (result["fdr"] <= alpha)
        & (result["log2_fold_change"].abs() >= minimum_effect)
    )
    result = result.sort_values(["fdr", "log2_fold_change"], ascending=[True, False])
    return {
        "contrast": {"group_a": groups[0], "group_b": groups[1]},
        "results": result.to_dict(orient="records"),
        "summary": {
            "features_tested": len(result),
            "significant": int(result["significant"].sum()),
            "fdr_threshold": alpha,
            "minimum_abs_log2fc": minimum_effect,
        },
        "method": "Welch t-test with Benjamini-Hochberg FDR; use DESeq2/edgeR/limma adapters for count-model inference.",
    }


def biomarker_discovery(
    frame: pd.DataFrame, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    from sklearn.calibration import calibration_curve
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (
        average_precision_score,
        brier_score_loss,
        confusion_matrix,
        roc_auc_score,
    )
    from sklearn.model_selection import GridSearchCV, StratifiedKFold
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    label_column = str(parameters.get("label_column", "label"))
    require_columns(frame, (label_column,))
    data = frame.copy().dropna(subset=[label_column])
    y_raw = data.pop(label_column)
    if y_raw.nunique() != 2:
        raise PlatformValidationError("Biomarker discovery requires a binary outcome")
    y = pd.Categorical(y_raw).codes
    numeric_columns = [
        column
        for column in data.columns
        if pd.api.types.is_numeric_dtype(data[column])
        and not pd.api.types.is_bool_dtype(data[column])
    ]
    if not numeric_columns:
        raise PlatformValidationError("At least one numeric biomarker feature is required")
    x = data[numeric_columns].apply(pd.to_numeric, errors="coerce")
    class_counts = np.bincount(y)
    outer_splits = min(int(parameters.get("outer_folds", 5)), int(class_counts.min()))
    if outer_splits < 3:
        raise PlatformValidationError("Nested CV requires at least three samples in each class")
    seed = int(parameters.get("seed", 42))
    outer = StratifiedKFold(n_splits=outer_splits, shuffle=True, random_state=seed)
    predictions = np.full(len(x), np.nan)
    coefficients = []
    fold_rows = []
    for fold, (train_index, test_index) in enumerate(outer.split(x, y), 1):
        inner_counts = np.bincount(y[train_index])
        inner_splits = min(3, int(inner_counts.min()))
        pipeline = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        l1_ratio=1.0, solver="liblinear", max_iter=2000,
                        random_state=seed + fold,
                    ),
                ),
            ]
        )
        search = GridSearchCV(
            pipeline,
            {"model__C": [0.01, 0.1, 1.0, 10.0]},
            scoring="roc_auc",
            cv=StratifiedKFold(
                n_splits=inner_splits, shuffle=True, random_state=seed + fold
            ),
            n_jobs=1,
        )
        search.fit(x.iloc[train_index], y[train_index])
        probability = search.predict_proba(x.iloc[test_index])[:, 1]
        predictions[test_index] = probability
        coefficients.append(search.best_estimator_["model"].coef_[0])
        fold_rows.append(
            {
                "fold": fold, "test_rows": len(test_index),
                "best_c": float(search.best_params_["model__C"]),
                "roc_auc": float(roc_auc_score(y[test_index], probability))
                if len(np.unique(y[test_index])) == 2 else None,
            }
        )
    threshold = float(parameters.get("threshold", 0.5))
    predicted = (predictions >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    coefficient_frame = pd.DataFrame(coefficients, columns=numeric_columns)
    stability = (coefficient_frame.abs() > 1e-8).mean().sort_values(ascending=False)
    fraction_positive, mean_predicted = calibration_curve(
        y, predictions, n_bins=min(10, max(3, len(y) // 10)), strategy="quantile"
    )
    decision_curve = []
    for decision_threshold in (0.2, 0.5, 0.8):
        classified = predictions >= decision_threshold
        true_positive = int(((y == 1) & classified).sum())
        false_positive = int(((y == 0) & classified).sum())
        net_benefit = true_positive / len(y) - false_positive / len(y) * (
            decision_threshold / (1 - decision_threshold)
        )
        decision_curve.append(
            {"threshold": decision_threshold, "net_benefit": float(net_benefit)}
        )
    return {
        "metrics": {
            "roc_auc": float(roc_auc_score(y, predictions)),
            "pr_auc": float(average_precision_score(y, predictions)),
            "brier_score": float(brier_score_loss(y, predictions)),
            "sensitivity": tp / max(1, tp + fn),
            "specificity": tn / max(1, tn + fp),
            "threshold": threshold,
        },
        "folds": fold_rows,
        "feature_stability": [
            {
                "feature": feature, "selection_frequency": float(value),
                "median_coefficient": float(coefficient_frame[feature].median()),
            }
            for feature, value in stability.items()
        ],
        "calibration": [
            {"mean_prediction": float(pred), "observed_fraction": float(obs)}
            for pred, obs in zip(mean_predicted, fraction_positive)
        ],
        "decision_curve": decision_curve,
        "external_validation": "Not performed; a separate independent dataset is required.",
        "method": "Leakage-safe nested stratified CV with fold-local imputation, scaling, tuning, and sparse logistic regression.",
    }


def variant_prioritization(
    frame: pd.DataFrame, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    require_columns(frame, ("variant_id", "allele_frequency", "consequence"))
    data = frame.copy()
    for column in ("allele_frequency", "cadd", "revel", "spliceai", "phenotype_similarity"):
        if column in data:
            data[column] = numeric(data[column])
    weights = {
        "rarity": float(parameters.get("rarity_weight", 0.25)),
        "consequence": float(parameters.get("consequence_weight", 0.20)),
        "cadd": float(parameters.get("cadd_weight", 0.15)),
        "revel": float(parameters.get("revel_weight", 0.10)),
        "spliceai": float(parameters.get("spliceai_weight", 0.10)),
        "phenotype": float(parameters.get("phenotype_weight", 0.15)),
        "inheritance": float(parameters.get("inheritance_weight", 0.05)),
    }
    total = sum(weights.values())
    weights = {key: value / total for key, value in weights.items()}
    consequence_score = {
        "stop_gained": 1.0, "frameshift_variant": 1.0,
        "splice_acceptor_variant": 0.95, "splice_donor_variant": 0.95,
        "missense_variant": 0.65, "inframe_deletion": 0.60,
        "synonymous_variant": 0.10, "intron_variant": 0.05,
    }
    rarity = 1 - np.clip(data["allele_frequency"].fillna(1.0) / 0.01, 0, 1)
    components = pd.DataFrame(index=data.index)
    components["rarity"] = rarity
    components["consequence"] = (
        data["consequence"].astype(str).map(consequence_score).fillna(0.2)
    )
    zeroes = pd.Series(0.0, index=data.index)
    components["cadd"] = np.clip(data.get("cadd", zeroes).fillna(0) / 40, 0, 1)
    components["revel"] = np.clip(data.get("revel", zeroes).fillna(0), 0, 1)
    components["spliceai"] = np.clip(data.get("spliceai", zeroes).fillna(0), 0, 1)
    components["phenotype"] = np.clip(
        data.get("phenotype_similarity", zeroes).fillna(0), 0, 1
    )
    inheritance = data.get(
        "inheritance_match", pd.Series(False, index=data.index)
    )
    components["inheritance"] = inheritance.astype(bool).astype(float)
    data["priority_score"] = sum(components[key] * weights[key] for key in weights)
    data["missing_evidence"] = [
        [
            key
            for key, source_column in {
                "cadd": "cadd", "revel": "revel", "spliceai": "spliceai",
                "phenotype": "phenotype_similarity", "inheritance": "inheritance_match",
            }.items()
            if source_column not in data.columns or pd.isna(data.loc[index, source_column])
        ]
        for index in data.index
    ]
    data = data.sort_values("priority_score", ascending=False)
    return {
        "ranked_variants": data.to_dict(orient="records"),
        "weights": weights,
        "scientific_boundary": (
            "This is transparent research prioritization, not an ACMG classification. "
            "ClinVar/gnomAD/HPO and segregation evidence require verified adapters and human review."
        ),
    }


def pathway_enrichment(
    frame: pd.DataFrame, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    require_columns(frame, ("pathway", "gene", "selected", "in_background"))
    data = frame.copy()
    data["selected"] = data["selected"].astype(bool)
    data["in_background"] = data["in_background"].astype(bool)
    background = set(data.loc[data["in_background"], "gene"].astype(str))
    selected = set(data.loc[data["selected"], "gene"].astype(str))
    if not selected:
        raise PlatformValidationError("At least one selected gene is required")
    if not selected.issubset(background):
        raise PlatformValidationError("Selected genes must be contained in the background universe")
    records = []
    for pathway, subset in data.groupby("pathway", sort=False):
        pathway_genes = set(subset.loc[subset["in_background"], "gene"].astype(str))
        overlap = selected & pathway_genes
        p_value = stats.hypergeom.sf(
            len(overlap) - 1, len(background), len(pathway_genes), len(selected)
        )
        records.append(
            {
                "pathway": str(pathway), "overlap": len(overlap),
                "pathway_size": len(pathway_genes),
                "selected_size": len(selected), "background_size": len(background),
                "p_value": float(p_value),
                "leading_edge": sorted(overlap),
            }
        )
    result = pd.DataFrame(records)
    result["fdr"] = bh_fdr(result["p_value"])
    result["significant"] = result["fdr"] <= float(parameters.get("fdr", 0.05))
    result = result.sort_values(["fdr", "overlap"], ascending=[True, False])
    return {
        "results": result.to_dict(orient="records"),
        "background_validated": True,
        "method": "One-sided hypergeometric over-representation analysis with BH-FDR.",
    }
