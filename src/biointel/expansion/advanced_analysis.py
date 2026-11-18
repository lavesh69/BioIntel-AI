from __future__ import annotations

import hashlib

import math
import re
from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial import cKDTree
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def bh_adjust(p_values: Iterable[float]) -> np.ndarray:
    values = np.asarray(list(p_values), dtype=float)
    adjusted = np.full(values.shape, np.nan, dtype=float)
    valid = np.isfinite(values)
    if not valid.any():
        return adjusted
    pv = values[valid]
    order = np.argsort(pv)
    ranked = pv[order]
    n = len(ranked)
    corrected = ranked * n / np.arange(1, n + 1)
    corrected = np.minimum.accumulate(corrected[::-1])[::-1]
    corrected = np.clip(corrected, 0, 1)
    restored = np.empty_like(corrected)
    restored[order] = corrected
    adjusted[valid] = restored
    return adjusted


def cohen_d(a: pd.Series | np.ndarray, b: pd.Series | np.ndarray) -> float:
    x = np.asarray(pd.to_numeric(pd.Series(a), errors="coerce").dropna(), dtype=float)
    y = np.asarray(pd.to_numeric(pd.Series(b), errors="coerce").dropna(), dtype=float)
    if len(x) < 2 or len(y) < 2:
        return float("nan")
    pooled_num = (len(x) - 1) * np.var(x, ddof=1) + (len(y) - 1) * np.var(y, ddof=1)
    pooled_den = len(x) + len(y) - 2
    if pooled_den <= 0:
        return float("nan")
    pooled = math.sqrt(max(pooled_num / pooled_den, 0.0))
    return float((np.mean(y) - np.mean(x)) / pooled) if pooled > 0 else 0.0


def welch_p(a: pd.Series | np.ndarray, b: pd.Series | np.ndarray) -> float:
    x = numeric(pd.Series(a)).dropna()
    y = numeric(pd.Series(b)).dropna()
    if len(x) < 2 or len(y) < 2:
        return float("nan")
    return float(stats.ttest_ind(x, y, equal_var=False, nan_policy="omit").pvalue)


def _parse_region(value: Any) -> tuple[str | None, float | None, float | None]:
    match = re.match(r"^([^:]+):(\d+)-(\d+)$", str(value).strip())
    if not match:
        return None, None, None
    return match.group(1), float(match.group(2)), float(match.group(3))


def _sequence_entropy(sequence: str) -> float:
    seq = str(sequence).upper()
    if not seq:
        return 0.0
    counts = np.array([seq.count(base) for base in set(seq)], dtype=float)
    probs = counts / counts.sum()
    return float(-(probs * np.log2(probs + 1e-12)).sum())


def _longest_homopolymer(sequence: str) -> int:
    seq = str(sequence).upper()
    if not seq:
        return 0
    longest = current = 1
    for left, right in zip(seq, seq[1:]):
        current = current + 1 if left == right else 1
        longest = max(longest, current)
    return longest


def _expected_calibration_error(truth: np.ndarray, prediction: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    total = len(truth)
    if total == 0:
        return float("nan")
    ece = 0.0
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (prediction >= low) & (prediction < high if high < 1 else prediction <= high)
        if not mask.any():
            continue
        ece += mask.mean() * abs(prediction[mask].mean() - truth[mask].mean())
    return float(ece)


def _km_summary(time: pd.Series, event: pd.Series) -> tuple[pd.DataFrame, float]:
    frame = pd.DataFrame({"time": numeric(time), "event": numeric(event)}).dropna().sort_values("time")
    if frame.empty:
        return pd.DataFrame(columns=["time", "at_risk", "events", "survival"]), float("nan")
    at_risk = len(frame)
    survival = 1.0
    rows: list[dict[str, float]] = []
    for t, grp in frame.groupby("time"):
        events = int((grp["event"] > 0).sum())
        censored = len(grp) - events
        if at_risk > 0:
            survival *= 1 - events / at_risk
        rows.append({"time": float(t), "at_risk": int(at_risk), "events": events, "survival": float(survival)})
        at_risk -= events + censored
    curve = pd.DataFrame(rows)
    below = curve[curve["survival"] <= 0.5]
    median = float(below.iloc[0]["time"]) if not below.empty else float("nan")
    return curve, median


def _moran_i(x: np.ndarray, y: np.ndarray, values: np.ndarray, neighbours: int = 6) -> float:
    mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(values)
    x, y, values = x[mask], y[mask], values[mask]
    n = len(values)
    if n < 4 or np.nanstd(values) == 0:
        return float("nan")
    coords = np.column_stack((x, y))
    k = min(neighbours + 1, n)
    _, idx = cKDTree(coords).query(coords, k=k)
    centered = values - values.mean()
    denominator = float(np.sum(centered**2))
    numerator = 0.0
    weights = 0
    for i in range(n):
        for j in np.atleast_1d(idx[i])[1:]:
            numerator += centered[i] * centered[int(j)]
            weights += 1
    return float((n / max(weights, 1)) * numerator / denominator) if denominator > 0 else float("nan")


def enrich_analysis(
    data: pd.DataFrame,
    result: pd.DataFrame,
    secondary: pd.DataFrame | None,
    module_key: str,
    threshold: float,
) -> tuple[pd.DataFrame, pd.DataFrame | None, dict[str, Any], dict[str, pd.DataFrame]]:
    """Add deeper, deterministic analyses while preserving the Step 102 schema.

    Returns the enriched primary result, secondary summary, additional manifest
    metrics and named auxiliary result tables.
    """
    result = result.copy()
    extras: dict[str, pd.DataFrame] = {}
    metrics: dict[str, Any] = {"advanced_engine": "biointel.scientific_expansion.v2"}

    if module_key == "epigenomics_chromatin":
        work = data.copy()
        work["signal"] = numeric(work["signal"])
        work["methylation"] = numeric(work["methylation"])
        conditions = [x for x in work["condition"].dropna().astype(str).unique()]
        rows = []
        if len(conditions) >= 2:
            control, case = conditions[0], conditions[-1]
            for region, group in work.groupby("region"):
                a = group.loc[group["condition"].astype(str) == control, "signal"]
                b = group.loc[group["condition"].astype(str) == case, "signal"]
                ma = group.loc[group["condition"].astype(str) == control, "methylation"]
                mb = group.loc[group["condition"].astype(str) == case, "methylation"]
                chrom, start, end = _parse_region(region)
                rows.append({
                    "region": region,
                    "chrom": chrom,
                    "start": start,
                    "end": end,
                    "region_width": end - start if start is not None and end is not None else np.nan,
                    "control_condition": control,
                    "case_condition": case,
                    "control_mean": float(numeric(a).mean()),
                    "case_mean": float(numeric(b).mean()),
                    "log2_fold_change": float(np.log2((numeric(b).mean() + 1e-6) / (numeric(a).mean() + 1e-6))),
                    "cohen_d": cohen_d(a, b),
                    "p_value": welch_p(a, b),
                    "methylation_delta": float(numeric(mb).mean() - numeric(ma).mean()),
                    "control_replicates": int(numeric(a).notna().sum()),
                    "case_replicates": int(numeric(b).notna().sum()),
                })
            stats_table = pd.DataFrame(rows)
            stats_table["q_value"] = bh_adjust(stats_table["p_value"])
            stats_table["replicate_balance"] = stats_table[["control_replicates", "case_replicates"]].min(axis=1) / stats_table[["control_replicates", "case_replicates"]].max(axis=1).replace(0, np.nan)
            stats_table["significant"] = (stats_table["q_value"] <= 0.05) & (stats_table["log2_fold_change"].abs() >= math.log2(1.5))
            stats_table["priority_score_advanced"] = (
                stats_table["log2_fold_change"].abs().clip(0, 5) / 5
                * (1 - stats_table["q_value"].fillna(1))
                * stats_table["replicate_balance"].fillna(0)
            )
            result = stats_table.sort_values(["significant", "priority_score_advanced"], ascending=[False, False])
            extras["differential_statistics"] = stats_table
            metrics["fdr_significant_regions"] = int(stats_table["significant"].sum())

    elif module_key == "metabolomics_lipidomics":
        work = data.copy()
        work["intensity"] = numeric(work["intensity"])
        work["blank_intensity"] = numeric(work["blank_intensity"])
        work["log2_intensity"] = np.log2(work["intensity"].clip(lower=0) + 1)
        groups = [x for x in work["group"].dropna().astype(str).unique()]
        rows = []
        for feature, group in work.groupby("feature"):
            row: dict[str, Any] = {
                "feature": feature,
                "missing_rate": float(group["intensity"].isna().mean()),
                "mean_intensity": float(group["intensity"].mean()),
                "blank_ratio": float(group["blank_intensity"].mean() / max(group["intensity"].mean(), 1e-9)),
                "annotation_confidence": float(numeric(group["annotation_confidence"]).mean()),
                "cv": float(group["intensity"].std() / max(group["intensity"].mean(), 1e-9)),
            }
            if len(groups) >= 2:
                a = group.loc[group["group"].astype(str) == groups[0], "log2_intensity"]
                b = group.loc[group["group"].astype(str) == groups[-1], "log2_intensity"]
                row.update({
                    "reference_group": groups[0],
                    "comparison_group": groups[-1],
                    "log2_fold_change": float(numeric(b).mean() - numeric(a).mean()),
                    "cohen_d": cohen_d(a, b),
                    "p_value": welch_p(a, b),
                })
            rows.append(row)
        table = pd.DataFrame(rows)
        table["q_value"] = bh_adjust(table.get("p_value", pd.Series(np.nan, index=table.index)))
        table["qc_pass"] = (table["blank_ratio"] <= 0.2) & (table["cv"] <= 0.35) & (table["missing_rate"] <= 0.2)
        table["blank_contamination_flag"] = table["blank_ratio"] > 0.2
        table["identification_level"] = np.select(
            [
                table["annotation_confidence"] >= 0.95,
                table["annotation_confidence"] >= 0.80,
                table["annotation_confidence"] >= 0.60,
            ],
            [
                "Level 1 candidate: standard/orthogonal confirmation still required",
                "Level 2 candidate: probable structure",
                "Level 3 candidate: tentative class/formula",
            ],
            default="Level 4: unknown feature",
        )
        table["identification_release_blocked"] = table["annotation_confidence"] < 0.95
        table["significant"] = table["qc_pass"] & (table["q_value"] <= 0.05) & (table.get("log2_fold_change", 0).abs() >= math.log2(1.5))
        table["priority_score_advanced"] = (
            table.get("log2_fold_change", pd.Series(0, index=table.index)).abs().clip(0, 5) / 5
            * (1 - table["q_value"].fillna(1))
            * table["annotation_confidence"].clip(0, 1)
            * table["qc_pass"].astype(float)
        )
        table["result_scope"] = np.where(table["significant"], "Differential feature candidate", "QC/statistical screening only")
        result = table.sort_values(["significant", "priority_score_advanced"], ascending=[False, False])
        extras["feature_statistics"] = table
        extras["identification_evidence"] = table[["feature", "identification_level", "annotation_confidence", "blank_ratio", "cv", "missing_rate", "identification_release_blocked"]].copy()
        if {"injection_order", "sample_type"}.issubset(work.columns):
            drift_rows = []
            work["injection_order"] = numeric(work["injection_order"])
            qc_rows = work[work["sample_type"].astype(str).str.upper().isin({"QC", "POOLED_QC", "POOLED QC"})]
            for feature, group in qc_rows.groupby("feature"):
                valid = group[["injection_order", "log2_intensity"]].dropna()
                if len(valid) >= 4 and valid["injection_order"].nunique() >= 3:
                    slope, _, r_value, p_value, _ = stats.linregress(valid["injection_order"], valid["log2_intensity"])
                    drift_rows.append({"feature": feature, "qc_injections": len(valid), "drift_slope": slope, "drift_r": r_value, "drift_p_value": p_value, "drift_flag": abs(r_value) >= 0.7 and p_value <= 0.05})
            extras["qc_drift"] = pd.DataFrame(drift_rows)
            metrics["qc_drift_flags"] = int(extras["qc_drift"].get("drift_flag", pd.Series(dtype=bool)).sum()) if not extras["qc_drift"].empty else 0
        metrics["qc_pass_features"] = int(table["qc_pass"].sum())
        metrics["fdr_significant_features"] = int(table["significant"].sum())
        metrics["confirmed_identifications"] = 0

    elif module_key == "immunoinformatics_vaccine":
        result["peptide_length"] = result["peptide"].astype(str).str.len()
        result["hydrophobic_fraction"] = result["peptide"].astype(str).map(lambda s: sum(a in "AILMFWVY" for a in s) / max(len(s), 1))
        result["charged_fraction"] = result["peptide"].astype(str).map(lambda s: sum(a in "DEKR" for a in s) / max(len(s), 1))
        result["cysteine_count"] = result["peptide"].astype(str).str.count("C")
        result["manufacturability_flag"] = (result["hydrophobic_fraction"] > 0.65) | (result["cysteine_count"] >= 3) | result["peptide"].astype(str).map(lambda value: _longest_homopolymer(value) >= 3)
        promiscuity = result.groupby("peptide").agg(
            allele_count=("allele", "nunique"),
            mean_binding=("binding_score", "mean"),
            mean_immunogenicity=("immunogenicity", "mean"),
            max_toxicity=("toxicity_risk", "max"),
        ).reset_index()
        promiscuity["promiscuity_score"] = (
            (promiscuity["allele_count"] / max(promiscuity["allele_count"].max(), 1)) * 0.35
            + promiscuity["mean_binding"] * 0.3
            + promiscuity["mean_immunogenicity"] * 0.25
            + (1 - promiscuity["max_toxicity"].clip(0, 1)) * 0.1
        )
        extras["promiscuous_epitopes"] = promiscuity.sort_values("promiscuity_score", ascending=False)
        top_construct = promiscuity.sort_values("promiscuity_score", ascending=False).head(12)["peptide"].tolist()
        extras["multi_epitope_construct"] = pd.DataFrame({
            "order": range(1, len(top_construct) + 1),
            "peptide": top_construct,
            "linker": ["AAY" if i % 2 == 0 else "GPGPG" for i in range(len(top_construct))],
        })
        metrics["manufacturability_flags"] = int(result["manufacturability_flag"].sum())
        metrics["unique_epitopes"] = int(result["peptide"].nunique())

    elif module_key == "antibody_biologics":
        if "sequence" in result.columns:
            seq = result["sequence"].fillna("").astype(str).str.upper()
            result["sequence_length"] = seq.str.len()
            result["deamidation_motifs"] = seq.str.count(r"N[GST]")
            result["isomerization_motifs"] = seq.str.count(r"D[GSTP]")
            result["oxidation_sites"] = seq.str.count(r"[MW]")
            result["unpaired_cysteine_proxy"] = seq.str.count("C") % 2
            result["hydrophobic_fraction"] = seq.map(lambda s: sum(a in "AILMFWVY" for a in s) / max(len(s), 1))
            result["sequence_liability_total"] = result[["deamidation_motifs", "isomerization_motifs", "oxidation_sites", "unpaired_cysteine_proxy"]].sum(axis=1)
            result["developability_flag"] = result["developability_flag"] | (result["sequence_liability_total"] >= 5) | (result["hydrophobic_fraction"] > 0.48)
        # Pareto frontier for affinity/stability/humanness versus risks.
        cols = ["affinity", "stability", "humanness", "aggregation_risk", "liability_count"]
        matrix = result[cols].apply(numeric).to_numpy(dtype=float)
        maximize = np.column_stack((matrix[:, :3], -matrix[:, 3:]))
        pareto = np.ones(len(result), dtype=bool)
        for i in range(len(result)):
            if np.any(np.all(maximize >= maximize[i], axis=1) & np.any(maximize > maximize[i], axis=1)):
                pareto[i] = False
        result["pareto_optimal"] = pareto
        result = result.sort_values(["pareto_optimal", "developability_flag", "priority_score"], ascending=[False, True, False])
        metrics["pareto_variants"] = int(pareto.sum())

    elif module_key == "docking_dynamics":
        for column in ["docking_score", "rmsd", "hbond_occupancy", "strain_energy"]:
            result[column] = numeric(result[column])
        result["pose_quality_flag"] = (
            result["docking_score"].isna()
            | ((result["rmsd"].notna()) & (result["rmsd"] > 3.0))
            | ((result["strain_energy"].notna()) & (result["strain_energy"] > result["strain_energy"].quantile(0.9)))
        )
        result["redocking_validation_pass"] = result["rmsd"].notna() & (result["rmsd"] <= 2.0)
        result["evidence_tier"] = np.select(
            [
                result["redocking_validation_pass"] & ~result["pose_quality_flag"],
                result["docking_score"].notna() & ~result["pose_quality_flag"],
            ],
            ["Validated computational pose candidate", "Computational pose candidate"],
            default="Unvalidated structure/pose record",
        )
        result["experimental_affinity_confirmed"] = False
        result["result_scope"] = "Research prioritisation only; docking score is not binding-affinity evidence"
        consensus = result.groupby("ligand", as_index=False).agg(
            poses=("pose", "count"),
            best_docking=("docking_score", "min"),
            mean_docking=("docking_score", "mean"),
            median_rmsd=("rmsd", "median"),
            mean_hbond_occupancy=("hbond_occupancy", "mean"),
            best_priority=("priority_score", "max"),
            flagged_poses=("pose_quality_flag", "sum"),
            redocking_passes=("redocking_validation_pass", "sum"),
        )
        consensus["consensus_stability"] = (
            consensus["best_priority"].fillna(0) * 0.6
            + (1 - (consensus["median_rmsd"].fillna(5).clip(0, 5) / 5)) * 0.4
        )
        consensus["release_blocked"] = True
        consensus["next_required_evidence"] = "Independent pose review, assay validation, and preferably orthogonal binding evidence"
        extras["ligand_consensus"] = consensus.sort_values("consensus_stability", ascending=False)
        metrics["structure_only_imports"] = int((result.get("score_source", "") == "structure_import_only").sum()) if "score_source" in result else 0
        metrics["redocking_validation_passes"] = int(result["redocking_validation_pass"].sum())
        metrics["experimental_affinity_confirmed"] = 0

    elif module_key == "pharmacogenomics":
        result["variant_normalized"] = result["variant"].astype(str).str.strip().str.upper()
        result["curation_status"] = np.where(result["evidence_level"].astype(str).str.upper().isin(["A", "B", "C", "D"]), "Mapped evidence", "Uncurated variant")
        build_column = next((column for column in ("reference_build", "genome_build", "assembly") if column in result.columns), None)
        guideline_column = next((column for column in ("guideline_version", "cpic_version", "dpwg_version", "source_version") if column in result.columns), None)
        allele_column = next((column for column in ("star_allele", "diplotype", "haplotype") if column in result.columns), None)
        result["reference_build_present"] = result[build_column].notna() & result[build_column].astype(str).str.strip().ne("") if build_column else False
        result["guideline_version_present"] = result[guideline_column].notna() & result[guideline_column].astype(str).str.strip().ne("") if guideline_column else False
        result["allele_definition_present"] = result[allele_column].notna() & result[allele_column].astype(str).str.strip().ne("") if allele_column else False
        result["pgx_release_gate"] = np.where(
            (result["curation_status"] == "Mapped evidence") & result["reference_build_present"] & result["guideline_version_present"] & result["allele_definition_present"],
            "Manual clinical review still required",
            "Blocked: build, allele definition, guideline version, or curated evidence incomplete",
        )
        result["clinical_action_blocked"] = True
        result["research_note"] = np.where(
            result["curation_status"] == "Mapped evidence",
            "Review the versioned source guideline and independently confirm genotype, copy number, diplotype and phenotype.",
            "No curated interpretation is bundled; manual evidence curation required.",
        )
        metrics["uncurated_variants"] = int((result["curation_status"] == "Uncurated variant").sum())
        metrics["records_with_complete_version_context"] = int((result["reference_build_present"] & result["guideline_version_present"] & result["allele_definition_present"]).sum())
        metrics["clinical_actions_generated"] = 0

    elif module_key == "spatial_omics_pathology":
        work = data.copy()
        work["x"] = numeric(work["x"])
        work["y"] = numeric(work["y"])
        work["expression"] = numeric(work["expression"])
        rows = []
        for gene, group in work.groupby("gene"):
            rows.append({
                "gene": gene,
                "spots": len(group),
                "mean_expression": float(group["expression"].mean()),
                "moran_i": _moran_i(group["x"].to_numpy(), group["y"].to_numpy(), group["expression"].to_numpy()),
                "regions": int(group["region"].nunique()),
            })
        spatial_stats = pd.DataFrame(rows).sort_values("moran_i", ascending=False)
        extras["spatial_autocorrelation"] = spatial_stats
        region_stats = work.groupby(["gene", "region"], as_index=False).agg(mean_expression=("expression", "mean"), median_expression=("expression", "median"), spots=("spot", "count"))
        extras["region_expression"] = region_stats
        metrics["spatially_autocorrelated_genes"] = int((spatial_stats["moran_i"] > 0.2).sum()) if not spatial_stats.empty else 0

    elif module_key == "single_cell_trajectory":
        work = result.copy()
        work["pseudotime"] = numeric(work["pseudotime"])
        work["expression"] = numeric(work["expression"])
        trends = []
        for cluster, group in work.groupby("cluster"):
            valid = group[["pseudotime", "expression"]].dropna()
            if len(valid) >= 3:
                slope, intercept, r, p, _ = stats.linregress(valid["pseudotime"], valid["expression"])
            else:
                slope = intercept = r = p = np.nan
            trends.append({"cluster": cluster, "cells": len(group), "trajectory_slope": slope, "r_value": r, "p_value": p})
        trend_table = pd.DataFrame(trends)
        trend_table["q_value"] = bh_adjust(trend_table["p_value"])
        extras["trajectory_trends"] = trend_table.sort_values("q_value")
        network = work.groupby(["ligand", "receptor"], as_index=False).agg(cells=("cell", "nunique"), mean_score=("communication_score", "mean"), clusters=("cluster", "nunique"))
        network["network_priority"] = network["mean_score"] * np.log1p(network["cells"]) * (1 + 0.15 * network["clusters"])
        extras["communication_network"] = network.sort_values("network_priority", ascending=False)
        metrics["significant_trajectory_trends"] = int((trend_table["q_value"] <= 0.05).sum())

    elif module_key == "bioimage_microscopy":
        work = result.copy()
        # Images, not segmented objects, are the independent experimental units.
        image_level = work.groupby(["image_id", "condition"], as_index=False).agg(
            objects=("object_id", "count"),
            median_area=("area", "median"),
            mean_intensity=("intensity", "mean"),
            median_circularity=("circularity", "median"),
            flagged_objects=("quality_flag", "sum"),
        )
        image_level["flag_rate"] = image_level["flagged_objects"] / image_level["objects"].clip(lower=1)
        image_level["image_qc_flag"] = image_level["flag_rate"] > 0.2
        conditions = [x for x in image_level["condition"].dropna().astype(str).unique()]
        stats_rows = []
        if len(conditions) >= 2:
            for metric in ("median_area", "mean_intensity", "median_circularity"):
                a = image_level.loc[image_level["condition"].astype(str) == conditions[0], metric]
                b = image_level.loc[image_level["condition"].astype(str) == conditions[-1], metric]
                stats_rows.append({
                    "metric": metric,
                    "analysis_unit": "image",
                    "reference_condition": conditions[0],
                    "comparison_condition": conditions[-1],
                    "reference_images": int(numeric(a).notna().sum()),
                    "comparison_images": int(numeric(b).notna().sum()),
                    "reference_mean": float(numeric(a).mean()),
                    "comparison_mean": float(numeric(b).mean()),
                    "cohen_d": cohen_d(a, b),
                    "p_value": welch_p(a, b),
                    "replication_gate_pass": int(numeric(a).notna().sum()) >= 3 and int(numeric(b).notna().sum()) >= 3,
                })
        condition_statistics = pd.DataFrame(stats_rows)
        if not condition_statistics.empty:
            condition_statistics["q_value"] = bh_adjust(condition_statistics["p_value"])
            condition_statistics["inference_allowed"] = condition_statistics["replication_gate_pass"] & (condition_statistics["q_value"] <= 0.05)
        extras["condition_statistics"] = condition_statistics
        extras["image_qc"] = image_level.sort_values("flag_rate", ascending=False)
        extras["analysis_unit_audit"] = pd.DataFrame([{
            "analysis_unit": "image",
            "object_rows": len(work),
            "independent_images": int(image_level["image_id"].nunique()),
            "pseudoreplication_prevented": True,
            "release_note": "Object-level rows are summarized per image before inferential statistics.",
        }])
        metrics["image_qc_flags"] = int(image_level["image_qc_flag"].sum())
        metrics["independent_images"] = int(image_level["image_id"].nunique())
        metrics["replication_gate_failures"] = int((~condition_statistics.get("replication_gate_pass", pd.Series(dtype=bool))).sum()) if not condition_statistics.empty else 1

    elif module_key == "biostatistics_design":
        result["anticipated_observed_n"] = np.ceil(result["total_sample_size"] * (1 - numeric(result["dropout_rate"]))).astype(int)
        result["design_efficiency"] = numeric(result["effect_size"]).abs() * np.sqrt(result["anticipated_observed_n"] / numeric(result["groups"]).clip(lower=1))
        result["precision_95ci_halfwidth_proxy"] = 1.96 * np.sqrt(2 / result["n_per_group_with_dropout"].clip(lower=2))
        allocation_rows = []
        for _, row in result.iterrows():
            total = int(row["total_sample_size"])
            groups = max(2, int(row["groups"]))
            base, remainder = divmod(total, groups)
            for group_index in range(groups):
                allocation_rows.append({"design": row["design"], "group": f"Group {group_index + 1}", "planned_n": base + (1 if group_index < remainder else 0)})
        extras["allocation_plan"] = pd.DataFrame(allocation_rows)
        metrics["design_scenarios"] = int(len(result))

    elif module_key == "clinical_trial_biomarker":
        truth = numeric(result["response"]).fillna(0).astype(int).to_numpy()
        marker = numeric(result["biomarker"]).fillna(result["biomarker"].median()).to_numpy()
        try:
            auc = float(roc_auc_score(truth, marker)) if len(np.unique(truth)) > 1 else float("nan")
            fpr, tpr, thresholds = roc_curve(truth, marker)
            youden = tpr - fpr
            idx = int(np.nanargmax(youden))
            optimal = float(thresholds[idx])
            roc_table = pd.DataFrame({"threshold": thresholds, "sensitivity": tpr, "false_positive_rate": fpr, "specificity": 1 - fpr})
        except Exception:
            auc = optimal = float("nan")
            roc_table = pd.DataFrame()
        result["candidate_cutoff"] = optimal
        result["cutoff_group"] = np.where(numeric(result["biomarker"]) >= optimal, "High", "Low") if np.isfinite(optimal) else "Unknown"
        km_tables = []
        km_summary_rows = []
        for label, group in result.groupby(["arm", "cutoff_group"]):
            curve, median = _km_summary(group["time"], group["event"])
            arm, cutoff_group = label
            curve["arm"] = arm
            curve["biomarker_group"] = cutoff_group
            km_tables.append(curve)
            km_summary_rows.append({"arm": arm, "biomarker_group": cutoff_group, "patients": len(group), "median_survival": median, "response_rate": float(numeric(group["response"]).mean())})
        extras["roc_curve"] = roc_table
        extras["kaplan_meier_curve"] = pd.concat(km_tables, ignore_index=True) if km_tables else pd.DataFrame()
        extras["survival_summary"] = pd.DataFrame(km_summary_rows)
        metrics["biomarker_auc"] = auc
        metrics["candidate_cutoff"] = optimal

    elif module_key == "genome_editing_safety":
        seq = result["guide"].astype(str).str.upper()
        result["gc_content"] = seq.map(lambda s: (s.count("G") + s.count("C")) / max(len(s), 1))
        result["sequence_entropy"] = seq.map(_sequence_entropy)
        result["longest_homopolymer"] = seq.map(_longest_homopolymer)
        result["poly_t_termination_flag"] = seq.str.contains("TTTT")
        result["extreme_gc_flag"] = ~result["gc_content"].between(0.35, 0.70)
        result["low_complexity_flag"] = result["sequence_entropy"] < 1.5
        result["high_risk"] = result["high_risk"] | result[["poly_t_termination_flag", "extreme_gc_flag", "low_complexity_flag"]].any(axis=1)
        result["safety_score_advanced"] = result["safety_score"] * (1 - 0.18 * result[["poly_t_termination_flag", "extreme_gc_flag", "low_complexity_flag"]].sum(axis=1).clip(0, 3))
        result = result.sort_values(["high_risk", "safety_score_advanced"], ascending=[True, False])
        metrics["sequence_design_flags"] = int(result[["poly_t_termination_flag", "extreme_gc_flag", "low_complexity_flag"]].any(axis=1).sum())

    elif module_key == "proteogenomics_neoantigen":
        seq = result["peptide"].astype(str).str.upper()
        result["peptide_length"] = seq.str.len()
        result["hydrophobic_fraction"] = seq.map(lambda s: sum(a in "AILMFWVY" for a in s) / max(len(s), 1))
        result["manufacturability_flag"] = (result["hydrophobic_fraction"] > 0.7) | seq.map(lambda value: _longest_homopolymer(value) >= 3)
        result["spectral_fdr_proxy"] = 1 - numeric(result["spectral_score"]).clip(0, 1)
        result["multi_layer_support"] = result["multi_layer_support"] & ~result["manufacturability_flag"] & (result["spectral_fdr_proxy"] <= 0.05)
        result["priority_score_advanced"] = result["priority_score"] * (1 - result["spectral_fdr_proxy"]) * (~result["manufacturability_flag"]).astype(float)
        result = result.sort_values(["multi_layer_support", "priority_score_advanced"], ascending=[False, False])
        metrics["strict_multi_layer_candidates"] = int(result["multi_layer_support"].sum())

    elif module_key == "bioprocess_fermentation":
        batch_rows = []
        for batch, group in result.groupby("batch"):
            group = group.sort_values("time")
            t = numeric(group["time"])
            biomass = numeric(group["biomass"])
            product = numeric(group["product"])
            valid_b = pd.DataFrame({"t": t, "v": biomass}).dropna()
            valid_p = pd.DataFrame({"t": t, "v": product}).dropna()
            growth_slope = stats.linregress(valid_b["t"], np.log(valid_b["v"].clip(lower=1e-9))).slope if len(valid_b) >= 3 else np.nan
            product_slope = stats.linregress(valid_p["t"], valid_p["v"]).slope if len(valid_p) >= 3 else np.nan
            batch_rows.append({
                "batch": batch,
                "observations": len(group),
                "specific_growth_rate_proxy": growth_slope,
                "productivity_slope": product_slope,
                "terminal_biomass": float(biomass.iloc[-1]) if len(biomass) else np.nan,
                "terminal_product": float(product.iloc[-1]) if len(product) else np.nan,
                "max_yield": float(numeric(group["yield"]).max()),
                "deviation_rate": float(group["deviation_flag"].mean()),
            })
        batch_table = pd.DataFrame(batch_rows)
        if not batch_table.empty:
            batch_table["batch_performance_score"] = (
                batch_table["terminal_product"].rank(pct=True) * 0.45
                + batch_table["max_yield"].rank(pct=True) * 0.35
                + (1 - batch_table["deviation_rate"].rank(pct=True)) * 0.20
            )
        extras["batch_kinetics"] = batch_table.sort_values("batch_performance_score", ascending=False) if not batch_table.empty else batch_table
        metrics["batches_analysed"] = int(len(batch_table))

    elif module_key == "lims_eln_chain":
        work = result.copy()
        work["sample_id"] = work["sample_id"].astype(str).str.strip()
        work["parent_id"] = work["parent_id"].fillna("").astype(str).str.strip()
        work["location"] = work["location"].fillna("").astype(str).str.strip()

        duplicate_ids = work["sample_id"].duplicated(keep=False) | work["sample_id"].eq("")
        known = set(work.loc[~duplicate_ids, "sample_id"])
        missing_parent = work["parent_id"].ne("") & ~work["parent_id"].isin(known)
        self_parent = work["parent_id"].eq(work["sample_id"]) & work["parent_id"].ne("")
        parent_map = dict(zip(work["sample_id"], work["parent_id"]))

        cycle_samples: set[str] = set()
        lineage_depth: dict[str, int] = {}
        for sample_id in work["sample_id"]:
            seen: list[str] = []
            current = sample_id
            while current and current in parent_map:
                if current in seen:
                    cycle_samples.update(seen[seen.index(current):])
                    break
                seen.append(current)
                current = parent_map.get(current, "")
            lineage_depth[sample_id] = max(0, len(seen) - 1)

        work["duplicate_or_blank_sample_id"] = duplicate_ids
        work["orphan_parent"] = missing_parent
        work["missing_parent"] = missing_parent
        work["self_parent"] = self_parent
        work["lineage_cycle"] = work["sample_id"].isin(cycle_samples)
        work["lineage_depth"] = work["sample_id"].map(lineage_depth).fillna(0).astype(int)
        work["location_missing"] = work["location"].eq("")
        work["expiry_status"] = pd.cut(
            numeric(work["days_to_expiry"]),
            bins=[-np.inf, 0, 30, 90, np.inf],
            labels=["Expired", "Critical", "Watch", "Valid"],
        )
        work["custody_risk"] = (
            numeric(work["custody_risk"]).fillna(0)
            + work["orphan_parent"].astype(int) * 2
            + work["self_parent"].astype(int) * 3
            + work["lineage_cycle"].astype(int) * 3
            + work["duplicate_or_blank_sample_id"].astype(int) * 3
            + work["location_missing"].astype(int) * 2
        )
        work["alert"] = work["custody_risk"] >= max(2, round(threshold * 5))

        stable_columns = [
            c for c in [
                "sample_id", "parent_id", "status", "location", "days_to_expiry", "custody_risk"
            ] if c in work.columns
        ]
        work["record_sha256"] = work[stable_columns].astype(str).apply(
            lambda row: hashlib.sha256("|".join(row.values).encode("utf-8")).hexdigest(),
            axis=1,
        )
        work["release_blocked"] = work[[
            "duplicate_or_blank_sample_id", "missing_parent", "self_parent",
            "lineage_cycle", "location_missing"
        ]].any(axis=1)

        result = work
        lineage_columns = [
            "sample_id", "parent_id", "status", "location", "lineage_depth",
            "duplicate_or_blank_sample_id", "orphan_parent", "missing_parent",
            "self_parent", "lineage_cycle", "location_missing", "expiry_status",
            "record_sha256", "release_blocked"
        ]
        lineage = work[[c for c in lineage_columns if c in work.columns]].copy()
        lineage = lineage.sort_values(
            ["release_blocked", "lineage_cycle", "self_parent", "missing_parent"],
            ascending=False,
        )
        extras["lineage_integrity"] = lineage
        extras["sample_lineage_integrity"] = lineage.copy()

        roots = work.loc[work["parent_id"].eq(""), ["sample_id", "status", "location"]].copy()
        children: dict[str, list[str]] = {}
        for child, parent_id in zip(work["sample_id"], work["parent_id"]):
            if parent_id:
                children.setdefault(parent_id, []).append(child)

        def descendant_count(root: str) -> int:
            total = 0
            stack = list(children.get(root, []))
            visited: set[str] = set()
            while stack:
                node = stack.pop()
                if node in visited:
                    continue
                visited.add(node)
                total += 1
                stack.extend(children.get(node, []))
            return total

        roots["descendants"] = roots["sample_id"].map(descendant_count)
        extras["lineage_roots"] = roots

        metrics.update({
            "orphan_parent_records": int(missing_parent.sum()),
            "self_parent_records": int(self_parent.sum()),
            "duplicate_or_blank_sample_ids": int(duplicate_ids.sum()),
            "missing_parent_links": int(missing_parent.sum()),
            "lineage_cycle_samples": int(work["lineage_cycle"].sum()),
            "lineage_release_blocked_records": int(work["release_blocked"].sum()),
            "maximum_lineage_depth": int(work["lineage_depth"].max()) if len(work) else 0,
        })

    elif module_key == "causal_perturbation":
        result["weak_instrument"] = numeric(result["instrument_strength"]) < 10
        result["wald_ci_low"] = numeric(result["effect"]) - 1.96 * numeric(result["standard_error"])
        result["wald_ci_high"] = numeric(result["effect"]) + 1.96 * numeric(result["standard_error"])
        meta_rows = []
        for (exposure, outcome), group in result.groupby(["exposure", "outcome"]):
            variance = numeric(group["standard_error"]) ** 2
            weights = 1 / variance.replace(0, np.nan)
            valid = weights.notna() & numeric(group["effect"]).notna()
            if valid.any():
                estimate = float(np.average(numeric(group.loc[valid, "effect"]), weights=weights[valid]))
                se = float(math.sqrt(1 / weights[valid].sum()))
                q = float(np.sum(weights[valid] * (numeric(group.loc[valid, "effect"]) - estimate) ** 2))
            else:
                estimate = se = q = np.nan
            meta_rows.append({
                "exposure": exposure,
                "outcome": outcome,
                "instruments": int(len(group)),
                "ivw_effect": estimate,
                "ivw_se": se,
                "ci_low": estimate - 1.96 * se if np.isfinite(se) else np.nan,
                "ci_high": estimate + 1.96 * se if np.isfinite(se) else np.nan,
                "heterogeneity_q": q,
                "weak_instrument_rate": float(group["weak_instrument"].mean()),
            })
        extras["ivw_meta_analysis"] = pd.DataFrame(meta_rows).sort_values("weak_instrument_rate")
        metrics["weak_instruments"] = int(result["weak_instrument"].sum())

    elif module_key == "explainable_ai_assurance":
        truth = numeric(result["truth"]).fillna(0).astype(int).to_numpy()
        pred = numeric(result["prediction"]).clip(0, 1).fillna(0.5).to_numpy()
        cls = (pred >= 0.5).astype(int)
        metrics.update({
            "accuracy": float(accuracy_score(truth, cls)),
            "brier_score": float(brier_score_loss(truth, pred)),
            "expected_calibration_error": _expected_calibration_error(truth, pred),
            "roc_auc": float(roc_auc_score(truth, pred)) if len(np.unique(truth)) > 1 else float("nan"),
            "average_precision": float(average_precision_score(truth, pred)) if len(np.unique(truth)) > 1 else float("nan"),
        })
        cm = confusion_matrix(truth, cls, labels=[0, 1])
        extras["confusion_matrix"] = pd.DataFrame(cm, index=["Actual 0", "Actual 1"], columns=["Predicted 0", "Predicted 1"]).reset_index(names="actual")
        if len(np.unique(truth)) > 1:
            fpr, tpr, thresholds = roc_curve(truth, pred)
            extras["roc_curve"] = pd.DataFrame({"threshold": thresholds, "false_positive_rate": fpr, "true_positive_rate": tpr})
            precision, recall, pr_threshold = precision_recall_curve(truth, pred)
            extras["precision_recall_curve"] = pd.DataFrame({"threshold": np.append(pr_threshold, np.nan), "precision": precision, "recall": recall})
        subgroup = result.groupby("subgroup", as_index=False).agg(records=("sample", "count"), accuracy=("correct", "mean"), mean_prediction=("prediction", "mean"), outcome_rate=("truth", "mean"), mean_error=("absolute_error", "mean"))
        subgroup["accuracy_gap_from_best"] = subgroup["accuracy"].max() - subgroup["accuracy"]
        subgroup["selection_rate_gap"] = subgroup["mean_prediction"].max() - subgroup["mean_prediction"]
        extras["subgroup_assurance"] = subgroup.sort_values("accuracy")
        metrics["max_subgroup_accuracy_gap"] = float(subgroup["accuracy"].max() - subgroup["accuracy"].min()) if len(subgroup) else np.nan

    elif module_key == "multiomics_harmonization":
        work = result.copy()
        before = work.pivot_table(index="sample", columns="feature", values="value", aggfunc="mean").fillna(0)
        after = work.pivot_table(index="sample", columns="feature", values="harmonized_value", aggfunc="mean").fillna(0)
        sample_meta = work.drop_duplicates("sample").set_index("sample")
        common = before.index.intersection(sample_meta.index)
        before = before.loc[common]
        after = after.loc[common]
        sample_meta = sample_meta.loc[common]
        def pca_table(matrix: pd.DataFrame, label: str) -> pd.DataFrame:
            values = matrix.to_numpy(dtype=float)
            values = values - values.mean(axis=0, keepdims=True)
            if len(values) < 2 or values.shape[1] < 1:
                return pd.DataFrame()
            u, s, _ = np.linalg.svd(values, full_matrices=False)
            coords = u[:, :2] * s[:2]
            out = pd.DataFrame({"sample": matrix.index, "pc1": coords[:, 0], "pc2": coords[:, 1] if coords.shape[1] > 1 else 0, "stage": label})
            return out
        extras["pca_before_after"] = pd.concat([pca_table(before, "Before"), pca_table(after, "After")], ignore_index=True)
        batch_means_before = work.groupby(["feature", "batch"])["value"].mean().groupby("feature").std()
        batch_means_after = work.groupby(["feature", "batch"])["harmonized_value"].mean().groupby("feature").std()
        diagnostics = pd.DataFrame({"feature": batch_means_before.index, "between_batch_sd_before": batch_means_before.values, "between_batch_sd_after": batch_means_after.reindex(batch_means_before.index).values})
        diagnostics["batch_sd_reduction"] = 1 - diagnostics["between_batch_sd_after"] / diagnostics["between_batch_sd_before"].replace(0, np.nan)
        extras["batch_diagnostics"] = diagnostics.sort_values("batch_sd_reduction", ascending=False)
        metrics["median_batch_sd_reduction"] = float(diagnostics["batch_sd_reduction"].median())

    elif module_key == "glycomics_glycoproteomics":
        work = data.copy()
        work["abundance"] = numeric(work["abundance"])
        conditions = [x for x in work["condition"].dropna().astype(str).unique()]
        rows = []
        for (glycan, site), group in work.groupby(["glycan", "site"]):
            row: dict[str, Any] = {"glycan": glycan, "site": site, "records": len(group), "mean_confidence": float(numeric(group["confidence"]).mean())}
            if len(conditions) >= 2:
                a = group.loc[group["condition"].astype(str) == conditions[0], "abundance"]
                b = group.loc[group["condition"].astype(str) == conditions[-1], "abundance"]
                row.update({"log2_fold_change": float(np.log2((numeric(b).mean() + 1) / (numeric(a).mean() + 1))), "cohen_d": cohen_d(a, b), "p_value": welch_p(a, b)})
            rows.append(row)
        table = pd.DataFrame(rows)
        table["q_value"] = bh_adjust(table.get("p_value", pd.Series(np.nan, index=table.index)))
        table["localization_status"] = np.select(
            [table["mean_confidence"] >= 0.95, table["mean_confidence"] >= 0.80],
            ["High-confidence localized candidate", "Probable site candidate"],
            default="Ambiguous site/composition",
        )
        table["fdr_evidence_present"] = table["q_value"].notna()
        table["high_confidence_change"] = (table["q_value"] <= 0.05) & (table["mean_confidence"] >= threshold) & (table.get("log2_fold_change", 0).abs() >= math.log2(1.5))
        table["release_blocked"] = True
        table["next_required_evidence"] = np.where(
            table["high_confidence_change"],
            "Manual fragment-spectrum review, decoy/FDR validation and orthogonal site confirmation",
            "Improve localization, replicate support and spectrum-level evidence",
        )
        extras["site_resolved_statistics"] = table.sort_values(["high_confidence_change", "q_value"], ascending=[False, True])
        extras["glycan_evidence_gate"] = table[["glycan", "site", "localization_status", "fdr_evidence_present", "release_blocked", "next_required_evidence"]].copy()
        metrics["high_confidence_changes"] = int(table["high_confidence_change"].sum())
        metrics["externally_confirmed_glycosites"] = 0

    elif module_key == "one_health_environmental":
        result["date"] = pd.to_datetime(result["date"], errors="coerce")
        result["week"] = result["date"].dt.to_period("W").dt.start_time
        weekly = result.groupby(["location", "pathogen", "week"], as_index=False).agg(samples=("sample", "count"), reads=("read_count", "sum"), mean_amr=("amr_genes", "mean"))
        weekly = weekly.sort_values(["location", "pathogen", "week"])
        weekly["rolling_mean"] = weekly.groupby(["location", "pathogen"])["reads"].transform(lambda s: s.rolling(4, min_periods=2).mean())
        weekly["rolling_sd"] = weekly.groupby(["location", "pathogen"])["reads"].transform(lambda s: s.rolling(4, min_periods=2).std())
        weekly["outbreak_z"] = (weekly["reads"] - weekly["rolling_mean"]) / weekly["rolling_sd"].replace(0, np.nan)
        weekly["outbreak_alert"] = weekly["outbreak_z"] >= 2.5
        extras["weekly_outbreak_signals"] = weekly.sort_values(["outbreak_alert", "outbreak_z"], ascending=[False, False])
        host_diversity = result.groupby(["location", "pathogen"])["host"].nunique().reset_index(name="host_diversity")
        extras["cross_host_summary"] = host_diversity.sort_values("host_diversity", ascending=False)
        metrics["outbreak_signal_count"] = int(weekly["outbreak_alert"].sum())

    elif module_key == "synthetic_data_privacy":
        source = data.copy()
        synth = result.copy()
        quasi = [c for c in ("age", "category", "site") if c in synth.columns]
        sensitive = "diagnosis_group" if "diagnosis_group" in synth.columns else None
        grouped = synth.groupby(quasi, dropna=False)
        privacy_rows = []
        source_sensitive = source[sensitive].value_counts(normalize=True) if sensitive else pd.Series(dtype=float)
        for key, group in grouped:
            l_diversity = int(group[sensitive].nunique()) if sensitive else np.nan
            if sensitive:
                local = group[sensitive].value_counts(normalize=True).reindex(source_sensitive.index, fill_value=0)
                t_closeness = float(0.5 * np.abs(local - source_sensitive).sum())
            else:
                t_closeness = np.nan
            privacy_rows.append({"equivalence_class": str(key), "size": len(group), "l_diversity": l_diversity, "t_closeness": t_closeness})
        privacy = pd.DataFrame(privacy_rows)
        extras["privacy_equivalence_classes"] = privacy.sort_values(["size", "l_diversity"])
        utility_rows = []
        for column in [c for c in source.columns if pd.api.types.is_numeric_dtype(source[c]) or c in {"age", "measurement"}]:
            a = numeric(source[column]).dropna()
            b = numeric(synth[column]).dropna()
            if len(a) and len(b):
                ks = stats.ks_2samp(a, b)
                utility_rows.append({"column": column, "source_mean": float(a.mean()), "synthetic_mean": float(b.mean()), "mean_difference": float(b.mean() - a.mean()), "ks_statistic": float(ks.statistic), "ks_p_value": float(ks.pvalue)})
        extras["distribution_utility"] = pd.DataFrame(utility_rows)
        source_corr = source.select_dtypes(include=[np.number]).corr()
        synth_corr = synth.select_dtypes(include=[np.number]).corr().reindex(index=source_corr.index, columns=source_corr.columns)
        metrics.update({
            "k_anonymity_min": int(privacy["size"].min()) if not privacy.empty else 0,
            "l_diversity_min": int(privacy["l_diversity"].min()) if sensitive and not privacy.empty else None,
            "t_closeness_max": float(privacy["t_closeness"].max()) if sensitive and not privacy.empty else None,
            "correlation_mae": float(np.nanmean(np.abs(source_corr.to_numpy() - synth_corr.to_numpy()))) if source_corr.size else None,
        })

    return result, secondary, metrics, extras
