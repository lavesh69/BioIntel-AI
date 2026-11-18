from __future__ import annotations

"""Research-grade, dependency-light upgrades for the Step 99 innovation modules.

The functions in this module intentionally avoid claiming that external tools,
clinical databases, or wet-lab evidence are present.  They add stronger local
quality control, transparent heuristics, resource planning, provenance, and
validation utilities that work with the base BioIntel installation.
"""

from collections import defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import StratifiedKFold
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _frame_sha256(frame: pd.DataFrame) -> str:
    payload = frame.sort_index(axis=1).to_csv(index=False, lineterminator="\n").encode("utf-8")
    return sha256(payload).hexdigest()


def _safe_numeric(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(default)


def _bh_adjust(p_values: Sequence[float]) -> np.ndarray:
    p = np.asarray(p_values, dtype=float)
    p = np.where(np.isfinite(p), np.clip(p, 0.0, 1.0), 1.0)
    order = np.argsort(p)
    ranked = p[order]
    out = np.empty(len(p), dtype=float)
    running = 1.0
    for idx in range(len(ranked) - 1, -1, -1):
        running = min(running, ranked[idx] * len(ranked) / (idx + 1))
        out[idx] = running
    adjusted = np.empty(len(p), dtype=float)
    adjusted[order] = np.clip(out, 0.0, 1.0)
    return adjusted


def _split_nodes(value: Any) -> list[str]:
    return [token.strip().rstrip("+-") for token in str(value or "").split(",") if token.strip()]


# ---------------------------------------------------------------------------
# 1. Pangenome / graph genomics
# ---------------------------------------------------------------------------


def pangenome_path_presence(paths: pd.DataFrame) -> pd.DataFrame:
    """Return a path-by-node binary matrix with stable ordering."""
    if paths.empty or "path" not in paths or "nodes" not in paths:
        return pd.DataFrame()
    node_names = sorted({node for value in paths["nodes"] for node in _split_nodes(value)})
    rows: list[dict[str, Any]] = []
    for row in paths.itertuples(index=False):
        members = set(_split_nodes(getattr(row, "nodes")))
        record = {"path": str(getattr(row, "path"))}
        record.update({node: int(node in members) for node in node_names})
        rows.append(record)
    return pd.DataFrame(rows)


def pangenome_core_accessory(paths: pd.DataFrame, nodes: pd.DataFrame) -> pd.DataFrame:
    presence = pangenome_path_presence(paths)
    base = nodes[[column for column in ["node", "length", "gc"] if column in nodes]].copy()
    if base.empty:
        return pd.DataFrame(columns=["node", "path_prevalence", "class"])
    base["node"] = base["node"].astype(str)
    if presence.empty:
        base["path_count"] = 0
        base["path_prevalence"] = 0.0
    else:
        path_count = len(presence)
        sums = presence.drop(columns=["path"], errors="ignore").sum(axis=0)
        base["path_count"] = base["node"].map(sums).fillna(0).astype(int)
        base["path_prevalence"] = base["path_count"] / max(1, path_count)
    base["class"] = pd.cut(
        base["path_prevalence"],
        bins=[-0.001, 0.15, 0.95, 1.001],
        labels=["Rare", "Accessory", "Core"],
    ).astype(str)
    base["review_flag"] = np.where(base["path_prevalence"] == 0, "Not represented by any path", "")
    return base.sort_values(["path_prevalence", "node"], ascending=[False, True]).reset_index(drop=True)


def pangenome_graph_integrity(nodes: pd.DataFrame, edges: pd.DataFrame, paths: pd.DataFrame) -> pd.DataFrame:
    findings: list[dict[str, Any]] = []
    node_ids = set(nodes.get("node", pd.Series(dtype=str)).astype(str))
    referenced = set(edges.get("source", pd.Series(dtype=str)).astype(str)) | set(edges.get("target", pd.Series(dtype=str)).astype(str))
    path_nodes = {node for value in paths.get("nodes", pd.Series(dtype=str)) for node in _split_nodes(value)}
    orphan = sorted(node_ids - referenced - path_nodes)
    missing_edge = sorted(referenced - node_ids)
    missing_path = sorted(path_nodes - node_ids)
    duplicated_paths = paths[paths.get("nodes", pd.Series(dtype=str)).astype(str).duplicated(keep=False)] if not paths.empty and "nodes" in paths else pd.DataFrame()
    sequence_missing = nodes[_safe_numeric(nodes.get("length", pd.Series(dtype=float))) <= 0] if not nodes.empty else pd.DataFrame()

    def add(severity: str, category: str, count: int, detail: str) -> None:
        findings.append({"severity": severity, "category": category, "count": int(count), "detail": detail})

    add("warning" if orphan else "pass", "Orphan segments", len(orphan), ", ".join(orphan[:10]) or "None")
    add("error" if missing_edge else "pass", "Edges referencing absent segments", len(missing_edge), ", ".join(missing_edge[:10]) or "None")
    add("error" if missing_path else "pass", "Paths referencing absent segments", len(missing_path), ", ".join(missing_path[:10]) or "None")
    add("warning" if len(duplicated_paths) else "pass", "Duplicate path definitions", len(duplicated_paths), "Review paths with identical segment walks" if len(duplicated_paths) else "None")
    add("warning" if len(sequence_missing) else "pass", "Segments without resolved length", len(sequence_missing), "Provide sequence or LN tag" if len(sequence_missing) else "None")
    return pd.DataFrame(findings)


def pangenome_bubble_support(bubbles: pd.DataFrame, paths: pd.DataFrame) -> pd.DataFrame:
    if bubbles.empty:
        return pd.DataFrame(columns=["start", "end", "paths_supporting_any_branch", "branch_support_entropy"])
    path_sets = {str(row.path): set(_split_nodes(row.nodes)) for row in paths.itertuples(index=False)} if not paths.empty else {}
    rows: list[dict[str, Any]] = []
    for bubble in bubbles.itertuples(index=False):
        roots = [token for token in str(getattr(bubble, "branch_roots", "")).split(",") if token]
        counts = {root: sum(root in members for members in path_sets.values()) for root in roots}
        total = sum(counts.values())
        probs = [count / total for count in counts.values() if total and count]
        entropy = -sum(value * math.log2(value) for value in probs) if probs else 0.0
        rows.append({
            "start": str(getattr(bubble, "start")),
            "end": str(getattr(bubble, "end")),
            "branch_count": len(roots),
            "paths_supporting_any_branch": sum(any(root in members for root in roots) for members in path_sets.values()),
            "branch_support_entropy": entropy,
            "branch_support": json.dumps(counts, sort_keys=True),
            "review_priority": "High" if total == 0 or len([c for c in counts.values() if c]) < 2 else "Moderate" if entropy < 0.5 else "Routine",
        })
    return pd.DataFrame(rows)


def pangenome_resource_estimate(nodes: int, edges: int, paths: int, sequence_bp: int, target_samples: int) -> dict[str, Any]:
    target_samples = max(1, int(target_samples))
    scale = max(1.0, target_samples / max(1, paths))
    graph_gb = max(0.05, sequence_bp * scale / 1e9)
    ram_gb = max(4.0, graph_gb * 6.0 + nodes * scale / 2_000_000 + edges * scale / 1_000_000)
    disk_gb = max(2.0, graph_gb * 12.0)
    cpu_hours = max(0.2, (nodes + edges) * scale / 1_000_000 * 2.0)
    return {
        "target_samples": target_samples,
        "estimated_graph_gb": round(graph_gb, 3),
        "recommended_ram_gb": int(math.ceil(ram_gb / 2) * 2),
        "recommended_disk_gb": int(math.ceil(disk_gb)),
        "estimated_cpu_hours": round(cpu_hours, 2),
        "execution_mode": "Distributed/cluster recommended" if ram_gb > 64 or target_samples > 500 else "Workstation" if ram_gb > 16 else "Desktop",
        "assumption": "Linear cohort scaling estimate; real graph complexity and sequence redundancy can change requirements substantially.",
    }


# ---------------------------------------------------------------------------
# 2. Long-read assembly and T2T
# ---------------------------------------------------------------------------


PLATFORM_THRESHOLDS: dict[str, dict[str, float]] = {
    "Oxford Nanopore": {"mean_q": 12.0, "n50": 10_000, "q20": 0.20, "coverage": 30.0},
    "PacBio HiFi": {"mean_q": 25.0, "n50": 10_000, "q20": 0.85, "coverage": 20.0},
    "PacBio CLR": {"mean_q": 10.0, "n50": 12_000, "q20": 0.10, "coverage": 30.0},
}


def long_read_platform_qc(reads: pd.DataFrame, metrics: Mapping[str, Any], platform: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    thresholds = PLATFORM_THRESHOLDS.get(platform, PLATFORM_THRESHOLDS["Oxford Nanopore"])
    checks = [
        ("Mean read quality", float(metrics.get("mean_q", 0.0)), thresholds["mean_q"], ">="),
        ("Read N50", float(metrics.get("n50", 0.0)), thresholds["n50"], ">="),
        ("Q20 base fraction", float(metrics.get("q20_base_fraction", 0.0)), thresholds["q20"], ">="),
        ("Estimated coverage", float(metrics.get("estimated_coverage", 0.0) or 0.0), thresholds["coverage"], ">="),
    ]
    rows = []
    for metric, observed, threshold, operator in checks:
        passed = observed >= threshold
        rows.append({"metric": metric, "observed": observed, "threshold": threshold, "operator": operator, "status": "Pass" if passed else "Review"})
    frame = pd.DataFrame(rows)
    lengths = _safe_numeric(reads.get("length", pd.Series(dtype=float)))
    qualities = _safe_numeric(reads.get("mean_q", pd.Series(dtype=float)))
    summary = {
        "platform": platform,
        "checks_passed": int((frame["status"] == "Pass").sum()),
        "checks_total": len(frame),
        "pass_fraction": float((frame["status"] == "Pass").mean()),
        "ultralong_fraction_100kb": float((lengths >= 100_000).mean()) if len(lengths) else 0.0,
        "low_quality_fraction": float((qualities < thresholds["mean_q"]).mean()) if len(qualities) else 0.0,
        "read_table_sha256": _frame_sha256(reads) if not reads.empty else "",
    }
    return frame, summary


def long_read_resource_plan(genome_size_mb: float, coverage: float, platform: str, genome_type: str, threads: int = 8) -> pd.DataFrame:
    genome_size_mb = max(0.001, float(genome_size_mb))
    coverage = max(1.0, float(coverage))
    complexity = 1.0
    if "Plant" in genome_type:
        complexity = 2.2
    elif "Human" in genome_type:
        complexity = 2.8
    elif "Metagenome" in genome_type:
        complexity = 3.5
    elif "Fungal" in genome_type:
        complexity = 1.5
    raw_gb = genome_size_mb * coverage / 1000
    assembler = "hifiasm" if "HiFi" in platform else "Flye" if "Nanopore" in platform else "Canu"
    stages = [
        ("Read QC", "FastQC/NanoPlot", max(2, threads // 2), max(4, raw_gb * 0.5), max(2, raw_gb * 2), max(0.1, raw_gb / 10)),
        ("Assembly", assembler, threads, max(8, genome_size_mb / 40 * complexity), max(10, raw_gb * 5), max(0.25, genome_size_mb / 250 * complexity)),
        ("Polishing", "Racon/Medaka/GCpp", threads, max(8, genome_size_mb / 80 * complexity), max(8, raw_gb * 4), max(0.2, genome_size_mb / 350 * complexity)),
        ("Completeness", "QUAST/BUSCO/Merqury", max(2, threads // 2), max(8, genome_size_mb / 150), max(8, genome_size_mb / 40), max(0.2, genome_size_mb / 500)),
    ]
    return pd.DataFrame([
        {"stage": stage, "recommended_tool": tool, "cpu_threads": int(cpu), "ram_gb": round(ram, 1), "disk_gb": round(disk, 1), "estimated_hours": round(hours, 2)}
        for stage, tool, cpu, ram, disk, hours in stages
    ])


def polishing_workflow(platform: str, hybrid_short_reads: bool) -> pd.DataFrame:
    if "HiFi" in platform:
        rows = [
            (1, "Primary consensus", "hifiasm consensus", "HiFi reads", True),
            (2, "Read-backed validation", "minimap2 + samtools", "HiFi reads", True),
            (3, "K-mer validation", "Merqury", "Independent Illumina/HiFi k-mers", False),
        ]
    elif "Nanopore" in platform:
        rows = [
            (1, "Long-read consensus", "Racon", "ONT reads", True),
            (2, "Neural polishing", "Medaka", "Chemistry-compatible model", True),
            (3, "Short-read polish", "Pilon/NextPolish", "Illumina reads", hybrid_short_reads),
        ]
    else:
        rows = [
            (1, "Long-read consensus", "Arrow/GCpp", "PacBio subreads", True),
            (2, "Assembly validation", "pbmm2 + samtools", "CLR reads", True),
            (3, "Short-read polish", "Pilon/NextPolish", "Illumina reads", hybrid_short_reads),
        ]
    return pd.DataFrame(rows, columns=["order", "stage", "tool", "input", "recommended"])


def t2t_completeness_audit(contigs: pd.DataFrame, summary: Mapping[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = contigs.copy()
    if frame.empty:
        return frame, {"t2t_readiness_score": 0.0, "status": "No contigs"}
    length = _safe_numeric(frame.get("length", pd.Series(dtype=float)))
    n_per = _safe_numeric(frame.get("n_per_100kb", pd.Series(dtype=float)))
    left = _safe_numeric(frame.get("left_telomere_hits", pd.Series(dtype=float)))
    right = _safe_numeric(frame.get("right_telomere_hits", pd.Series(dtype=float)))
    frame["telomere_state"] = np.select(
        [(left > 0) & (right > 0), (left > 0) | (right > 0)],
        ["Both ends", "One end"],
        default="No signal",
    )
    frame["gap_state"] = np.where(n_per == 0, "Gap-free by N audit", "Contains ambiguous bases")
    frame["chromosome_candidate"] = (frame["telomere_state"] == "Both ends") & (frame["gap_state"] == "Gap-free by N audit")
    weighted_n = float(np.average(n_per, weights=length)) if length.sum() else float(n_per.mean())
    completeness = min(100.0, 25.0 + 25.0 * (float(summary.get("n50", 0)) / max(1, float(summary.get("largest", 1)))) + 25.0 * (1 - min(1, weighted_n / 100)) + 25.0 * frame["chromosome_candidate"].mean())
    report = {
        "t2t_readiness_score": round(completeness, 1),
        "gap_free_contigs": int((n_per == 0).sum()),
        "two_end_telomere_contigs": int((frame["telomere_state"] == "Both ends").sum()),
        "chromosome_candidates": int(frame["chromosome_candidate"].sum()),
        "weighted_n_per_100kb": round(weighted_n, 3),
        "status": "Candidate complete chromosomes present" if frame["chromosome_candidate"].any() else "Further scaffolding/polishing required",
        "boundary": "Telomere motif and ambiguous-base checks are screening evidence, not a complete T2T validation.",
    }
    return frame, report


# ---------------------------------------------------------------------------
# 3. Protein design
# ---------------------------------------------------------------------------


AA_LIABILITY = {"C": 0.8, "M": 0.4, "W": 0.3, "P": 0.3, "N": 0.2, "Q": 0.15}


def protein_design_consensus(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    frame = candidates.copy()
    score_cols = [column for column in ["design_score", "stability_score", "solubility_score", "confidence"] if column in frame]
    for column in score_cols:
        values = _safe_numeric(frame[column])
        spread = values.max() - values.min()
        frame[f"{column}_scaled"] = (values - values.min()) / spread if spread > 0 else 0.5
    scaled = [f"{column}_scaled" for column in score_cols]
    frame["consensus_score"] = frame[scaled].mean(axis=1) if scaled else 0.0
    frame["method_support"] = (
        (frame.get("pareto_optimal", False).astype(bool).astype(int) if "pareto_optimal" in frame else 0)
        + (frame.get("risk_flag", "").astype(str).eq("conservative").astype(int) if "risk_flag" in frame else 0)
        + (frame["consensus_score"] >= frame["consensus_score"].quantile(0.75)).astype(int)
    )
    frame["review_priority"] = np.select(
        [frame["method_support"] >= 3, frame["method_support"] == 2],
        ["Top consensus", "Secondary"],
        default="Exploratory",
    )
    return frame.sort_values(["method_support", "consensus_score"], ascending=False).reset_index(drop=True)


def protein_sequence_developability(sequence: str) -> pd.DataFrame:
    sequence = re.sub(r"\s+", "", sequence.upper())
    if not sequence:
        raise ValueError("Protein sequence is empty.")
    windows: list[dict[str, Any]] = []
    window = min(15, max(5, len(sequence) // 20 or 5))
    hydrophobic = set("AVILMFWY")
    charged = set("DEKR")
    for start in range(0, len(sequence) - window + 1):
        fragment = sequence[start:start + window]
        hydro = sum(aa in hydrophobic for aa in fragment) / window
        charge = sum(aa in charged for aa in fragment) / window
        liability = sum(AA_LIABILITY.get(aa, 0.0) for aa in fragment)
        risk = 0.55 * hydro + 0.25 * max(0, 0.25 - charge) + 0.20 * min(1, liability / 3)
        windows.append({"start": start + 1, "end": start + window, "fragment": fragment, "hydrophobic_fraction": hydro, "charged_fraction": charge, "liability_score": liability, "developability_risk": risk})
    frame = pd.DataFrame(windows)
    frame["risk_class"] = pd.cut(frame["developability_risk"], [-0.001, 0.35, 0.55, 1.01], labels=["Low", "Moderate", "High"]).astype(str)
    return frame.sort_values("developability_risk", ascending=False).reset_index(drop=True)


def protein_pair_designs(sequence: str, candidates: pd.DataFrame, max_pairs: int = 100) -> pd.DataFrame:
    if candidates.empty or "mutation" not in candidates:
        return pd.DataFrame()
    top = protein_design_consensus(candidates).head(30)
    rows: list[dict[str, Any]] = []
    for i, left in top.iterrows():
        for _, right in top.iloc[i + 1:].iterrows():
            pos_left = int(re.findall(r"\d+", str(left["mutation"]))[0])
            pos_right = int(re.findall(r"\d+", str(right["mutation"]))[0])
            if pos_left == pos_right:
                continue
            separation = abs(pos_left - pos_right)
            compatibility = (float(left.get("consensus_score", 0)) + float(right.get("consensus_score", 0))) / 2
            epistasis_risk = 0.35 if separation <= 3 else 0.15 if separation <= 10 else 0.05
            rows.append({
                "mutation_1": left["mutation"],
                "mutation_2": right["mutation"],
                "position_separation": separation,
                "pair_score": compatibility - epistasis_risk,
                "epistasis_risk": "High" if epistasis_risk >= 0.3 else "Moderate" if epistasis_risk >= 0.1 else "Low",
                "requires_structure_review": separation <= 10,
            })
    return pd.DataFrame(rows).sort_values("pair_score", ascending=False).head(max_pairs).reset_index(drop=True) if rows else pd.DataFrame()


def protein_design_validation_plan(objective: str, candidate_count: int) -> pd.DataFrame:
    objectives = {
        "Balanced developability": ["Expression yield", "Solubility", "Thermal stability", "Activity/binding"],
        "Stability first": ["DSF/Tm", "Aggregation onset", "Activity retention", "Expression yield"],
        "Solubility first": ["Soluble expression", "SEC aggregation", "Activity/binding", "Thermal stability"],
        "Binding-site exploration": ["Binding affinity", "Specificity counter-screen", "Activity", "Stability"],
    }
    assays = objectives.get(objective, objectives["Balanced developability"])
    rows = []
    for index, assay in enumerate(assays, start=1):
        rows.append({"stage": index, "assay": assay, "recommended_variants": min(candidate_count, 24 if index == 1 else 12 if index == 2 else 6), "decision_gate": "Advance only candidates meeting pre-registered acceptance criteria"})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. CRISPR screens and Perturb-seq
# ---------------------------------------------------------------------------


def crispr_library_qc(counts: pd.DataFrame, control_columns: Sequence[str], treated_columns: Sequence[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {"guide", "gene"}
    missing = required - set(counts.columns)
    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
    columns = list(control_columns) + list(treated_columns)
    if not columns:
        raise ValueError("No count columns were selected.")
    matrix = counts[columns].apply(pd.to_numeric, errors="coerce").fillna(0).clip(lower=0)
    guide = counts[["guide", "gene"]].copy()
    guide["mean_count"] = matrix.mean(axis=1)
    guide["zero_fraction"] = (matrix == 0).mean(axis=1)
    guide["dropout_flag"] = guide["zero_fraction"] >= 0.5
    guide["low_count_flag"] = guide["mean_count"] < 30
    guide["library_cv"] = matrix.std(axis=1, ddof=1) / matrix.mean(axis=1).replace(0, np.nan)
    guide["qc_status"] = np.select(
        [guide["dropout_flag"], guide["low_count_flag"], guide["library_cv"].fillna(99) > 1.0],
        ["Dropout", "Low count", "High variability"],
        default="Pass",
    )
    correlations = matrix.corr(method="spearman")
    upper = correlations.where(np.triu(np.ones(correlations.shape), 1).astype(bool)).stack()
    metrics = {
        "guides": len(guide),
        "median_count": float(matrix.median().median()),
        "dropout_fraction": float(guide["dropout_flag"].mean()),
        "low_count_fraction": float(guide["low_count_flag"].mean()),
        "median_replicate_spearman": float(upper.median()) if len(upper) else np.nan,
        "count_table_sha256": _frame_sha256(counts),
    }
    return guide, metrics


def crispr_copy_number_adjustment(gene_results: pd.DataFrame, copy_number: pd.DataFrame | None) -> pd.DataFrame:
    result = gene_results.copy()
    if result.empty:
        return result
    if copy_number is None or copy_number.empty:
        result["copy_number"] = np.nan
        result["cn_adjusted_effect"] = result.get("median_log2_fc", np.nan)
        result["cn_bias_flag"] = False
        return result
    columns = {column.lower(): column for column in copy_number.columns}
    if "gene" not in columns:
        raise ValueError("Copy-number table requires a gene column.")
    value_col = next((columns[name] for name in ["copy_number", "cn", "log2_cn", "segment_mean"] if name in columns), None)
    if not value_col:
        raise ValueError("Copy-number table requires copy_number, cn, log2_cn, or segment_mean.")
    cn = copy_number[[columns["gene"], value_col]].copy()
    cn.columns = ["gene", "copy_number"]
    cn["copy_number"] = _safe_numeric(cn["copy_number"], default=2.0)
    result = result.merge(cn, on="gene", how="left")
    effect = _safe_numeric(result.get("median_log2_fc", pd.Series(index=result.index, dtype=float)))
    amplification = (result["copy_number"].fillna(2.0) - 2.0).clip(lower=0)
    result["cn_adjusted_effect"] = effect + 0.12 * amplification
    result["cn_bias_flag"] = amplification >= 3
    return result


def perturbseq_cell_qc(expression: pd.DataFrame, labels: Sequence[str], guide_confidence: Sequence[float] | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    numeric = expression.apply(pd.to_numeric, errors="coerce").fillna(0)
    library = numeric.abs().sum(axis=1)
    detected = (numeric != 0).sum(axis=1)
    median_library = float(library.median()) if len(library) else 0.0
    mad = float(np.median(np.abs(library - median_library))) if len(library) else 0.0
    high_cut = median_library + 4 * max(mad, 1.0)
    low_cut = max(0.0, median_library - 4 * max(mad, 1.0))
    frame = pd.DataFrame({
        "cell": [str(idx) for idx in expression.index],
        "perturbation": pd.Series(labels, index=expression.index).astype(str).values,
        "library_size": library.values,
        "detected_features": detected.values,
    })
    if guide_confidence is not None:
        confidence = pd.to_numeric(pd.Series(guide_confidence), errors="coerce").fillna(0.0)
        if len(confidence) != len(frame):
            raise ValueError("Guide-confidence length must match the number of cells.")
        frame["guide_confidence"] = confidence.values
    else:
        frame["guide_confidence"] = 1.0
    frame["doublet_candidate"] = frame["library_size"] > high_cut
    frame["low_complexity"] = (frame["library_size"] < low_cut) | (frame["detected_features"] < max(2, numeric.shape[1] * 0.05))
    frame["guide_assignment_review"] = frame["guide_confidence"] < 0.8
    frame["qc_status"] = np.select(
        [frame["doublet_candidate"], frame["low_complexity"], frame["guide_assignment_review"]],
        ["Doublet candidate", "Low complexity", "Guide review"],
        default="Pass",
    )
    return frame, {
        "cells": len(frame),
        "pass_fraction": float((frame["qc_status"] == "Pass").mean()),
        "doublet_candidate_fraction": float(frame["doublet_candidate"].mean()),
        "low_complexity_fraction": float(frame["low_complexity"].mean()),
        "guide_review_fraction": float(frame["guide_assignment_review"].mean()),
    }


def crispr_design_matrix(metadata: pd.DataFrame, outcome_column: str, covariates: Sequence[str]) -> pd.DataFrame:
    columns = [outcome_column] + [column for column in covariates if column != outcome_column]
    missing = [column for column in columns if column not in metadata]
    if missing:
        raise ValueError(f"Missing metadata columns: {', '.join(missing)}")
    data = metadata[columns].copy()
    categorical = [column for column in data.columns if not pd.api.types.is_numeric_dtype(data[column])]
    encoded = pd.get_dummies(data, columns=categorical, drop_first=True, dtype=float)
    encoded.insert(0, "intercept", 1.0)
    return encoded


# ---------------------------------------------------------------------------
# 5. Pathogen outbreak genomics
# ---------------------------------------------------------------------------


OUTBREAK_PROFILES = {
    "Generic exploratory": {"snp": 12, "days": 30, "km": 50, "note": "Screening only; configure organism-specific evidence."},
    "SARS-CoV-2": {"snp": 3, "days": 21, "km": 100, "note": "Requires lineage, sampling density, and epidemiology review."},
    "Mycobacterium tuberculosis": {"snp": 5, "days": 365, "km": 250, "note": "Thresholds vary by setting and analytical pipeline."},
    "Listeria monocytogenes": {"snp": 10, "days": 90, "km": 500, "note": "Use cgMLST/wgMLST and public-health laboratory guidance."},
    "Salmonella enterica": {"snp": 10, "days": 60, "km": 500, "note": "Interpret with serotype, source, and outbreak context."},
}


def outbreak_profile(name: str) -> dict[str, Any]:
    return dict(OUTBREAK_PROFILES.get(name, OUTBREAK_PROFILES["Generic exploratory"]))


def outbreak_epidemiology_audit(samples: pd.DataFrame, links: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if links.empty:
        return links.copy(), {"links": 0, "high_priority": 0}
    metadata = samples.copy()
    metadata["sample_id"] = metadata["sample_id"].astype(str)
    date_map = pd.to_datetime(metadata.set_index("sample_id").get("collection_date"), errors="coerce")
    location_map = metadata.set_index("sample_id").get("location", pd.Series(dtype=str)).astype(str)
    table = links.copy()
    table["source_date"] = table["source"].astype(str).map(date_map)
    table["target_date"] = table["target"].astype(str).map(date_map)
    table["source_location"] = table["source"].astype(str).map(location_map)
    table["target_location"] = table["target"].astype(str).map(location_map)
    table["same_location"] = table["source_location"] == table["target_location"]
    table["sampling_order"] = np.where(table["source_date"] <= table["target_date"], "source_before_target", "target_before_source")
    snp = _safe_numeric(table.get("snp_distance", pd.Series(index=table.index, dtype=float)))
    days = _safe_numeric(table.get("days_apart", pd.Series(index=table.index, dtype=float)))
    km = _safe_numeric(table.get("distance_km", pd.Series(index=table.index, dtype=float)))
    table["epidemiology_score"] = np.exp(-snp / 10) * np.exp(-days / 45) * np.exp(-km / 100) * np.where(table["same_location"], 1.25, 1.0)
    table["review_priority"] = pd.cut(table["epidemiology_score"], [-0.001, 0.2, 0.5, 1.5], labels=["Low", "Moderate", "High"]).astype(str)
    return table.sort_values("epidemiology_score", ascending=False).reset_index(drop=True), {
        "links": len(table),
        "high_priority": int((table["review_priority"] == "High").sum()),
        "same_location_fraction": float(table["same_location"].mean()),
        "median_epidemiology_score": float(table["epidemiology_score"].median()),
    }


def outbreak_recombination_screen(distances: pd.DataFrame) -> pd.DataFrame:
    matrix = distances.apply(pd.to_numeric, errors="coerce")
    if matrix.empty:
        return pd.DataFrame()
    rows = []
    for sample in matrix.index.astype(str):
        values = matrix.loc[sample].drop(labels=[sample], errors="ignore").dropna()
        if values.empty:
            continue
        median = float(values.median())
        mad = float(np.median(np.abs(values - median)))
        z = float((values.max() - median) / max(1e-9, 1.4826 * mad)) if mad else 0.0
        rows.append({"sample_id": sample, "median_distance": median, "max_distance": float(values.max()), "robust_outlier_score": z, "recombination_or_contamination_review": z >= 6})
    return pd.DataFrame(rows).sort_values("robust_outlier_score", ascending=False).reset_index(drop=True)


def outbreak_reporting_checklist(profile_name: str) -> pd.DataFrame:
    profile = outbreak_profile(profile_name)
    rows = [
        ("Sequence quality", "Read/assembly QC, contamination, depth and mixed infection reviewed"),
        ("Reference and masking", "Reference, masking, recombination and repeat handling documented"),
        ("Distance method", "SNP/cgMLST distance calculation and software versions recorded"),
        ("Threshold", f"Provisional threshold documented; profile default {profile['snp']} SNPs is not universal"),
        ("Epidemiology", "Dates, locations, contacts and sampling completeness reviewed"),
        ("AMR/virulence", "Database release, coverage and identity thresholds recorded"),
        ("Conclusion", "Cluster priority kept separate from proof of transmission"),
    ]
    return pd.DataFrame(rows, columns=["gate", "required_review"])


# ---------------------------------------------------------------------------
# 6. Synthetic biology / circuit design
# ---------------------------------------------------------------------------


def simulate_genetic_circuit(
    duration: float = 24.0,
    steps: int = 240,
    production_rate: float = 1.5,
    degradation_rate: float = 0.2,
    hill_coefficient: float = 2.0,
    repression_k: float = 1.0,
    input_signal: float = 1.0,
    initial_expression: float = 0.0,
) -> pd.DataFrame:
    if duration <= 0 or steps < 10:
        raise ValueError("Duration must be positive and at least 10 simulation steps are required.")
    dt = duration / steps
    value = max(0.0, float(initial_expression))
    rows = []
    for index in range(steps + 1):
        time = index * dt
        repression = 1.0 / (1.0 + (value / max(repression_k, 1e-9)) ** max(hill_coefficient, 0.1))
        production = max(0.0, production_rate) * max(0.0, input_signal) * repression
        derivative = production - max(0.0, degradation_rate) * value
        rows.append({"time": time, "expression": value, "production": production, "degradation": degradation_rate * value, "derivative": derivative})
        value = max(0.0, value + dt * derivative)
    return pd.DataFrame(rows)


def construct_manufacturability(sequence: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    seq = re.sub(r"[^ACGTN]", "", sequence.upper())
    if not seq:
        raise ValueError("DNA construct sequence is empty.")
    motifs = {
        "Long homopolymer": r"A{9,}|C{9,}|G{9,}|T{9,}",
        "BsaI site": r"GGTCTC|GAGACC",
        "BsmBI site": r"CGTCTC|GAGACG",
        "EcoRI site": r"GAATTC",
        "BamHI site": r"GGATCC",
        "Potential bacterial terminator": r"G{4,}.{4,20}C{4,}T{4,}",
    }
    findings: list[dict[str, Any]] = []
    for label, pattern in motifs.items():
        for match in re.finditer(pattern, seq):
            findings.append({"finding": label, "start": match.start() + 1, "end": match.end(), "sequence": match.group(), "severity": "High" if label in {"Long homopolymer", "BsaI site", "BsmBI site"} else "Moderate"})
    gc = 100 * (seq.count("G") + seq.count("C")) / len(seq)
    for start in range(0, max(1, len(seq) - 50 + 1), 10):
        fragment = seq[start:start + 50]
        if len(fragment) < 20:
            continue
        local_gc = 100 * (fragment.count("G") + fragment.count("C")) / len(fragment)
        if local_gc < 20 or local_gc > 80:
            findings.append({"finding": "Extreme local GC", "start": start + 1, "end": start + len(fragment), "sequence": fragment[:15] + "…", "severity": "Moderate"})
    frame = pd.DataFrame(findings, columns=["finding", "start", "end", "sequence", "severity"])
    score = max(0.0, 100.0 - 12 * int((frame["severity"] == "High").sum()) - 5 * int((frame["severity"] == "Moderate").sum()) - max(0, abs(gc - 50) - 20)) if not frame.empty else max(0.0, 100.0 - max(0, abs(gc - 50) - 20))
    return frame, {"length_bp": len(seq), "gc_percent": gc, "findings": len(frame), "manufacturability_score": round(score, 1), "sequence_sha256": sha256(seq.encode()).hexdigest()}


def chassis_burden_estimate(parts: pd.DataFrame, chassis: str, copy_number: int = 20) -> dict[str, Any]:
    expression = _safe_numeric(parts.get("strength", pd.Series(np.ones(len(parts)), index=parts.index)), default=1.0).clip(lower=0)
    coding_bp = _safe_numeric(parts.get("length", pd.Series(np.full(len(parts), 500), index=parts.index)), default=500).clip(lower=0)
    chassis_factor = {"E. coli": 1.0, "Yeast": 1.25, "Mammalian": 1.7, "Plant": 1.8, "Cell-free": 0.7}.get(chassis, 1.0)
    raw = float((expression * coding_bp / 1000).sum()) * max(1, copy_number) / 20 * chassis_factor
    burden = min(100.0, 12.5 * raw)
    return {"chassis": chassis, "copy_number": copy_number, "burden_score": round(burden, 1), "risk": "High" if burden >= 70 else "Moderate" if burden >= 35 else "Low", "recommendation": "Reduce copy number, promoter/RBS strength, or expression duration" if burden >= 35 else "No major burden flag from this screening model"}


def sbol_like_document(name: str, sequence: str, parts: pd.DataFrame, chassis: str) -> dict[str, Any]:
    return {
        "schema": "biointel.sbol3-lite.v1",
        "displayId": re.sub(r"\W+", "_", name).strip("_") or "construct",
        "type": "DNA",
        "chassis": chassis,
        "sequence": re.sub(r"[^ACGTN]", "", sequence.upper()),
        "features": parts.fillna("").to_dict(orient="records"),
        "boundary": "SBOL3-compatible concepts only; validate with a full SBOL library before repository submission.",
    }


# ---------------------------------------------------------------------------
# 7. Rare disease interpretation
# ---------------------------------------------------------------------------


HPO_SYNONYMS = {
    "seizure": {"HP:0001250", "seizures", "epilepsy"},
    "developmental delay": {"HP:0001263", "global developmental delay", "delayed development"},
    "intellectual disability": {"HP:0001249", "cognitive impairment"},
    "hypotonia": {"HP:0001252", "low muscle tone"},
    "ataxia": {"HP:0001251", "incoordination"},
    "microcephaly": {"HP:0000252", "small head"},
    "cardiomyopathy": {"HP:0001638", "heart muscle disease"},
}


def normalize_hpo_terms(terms: Sequence[str]) -> pd.DataFrame:
    rows = []
    for raw in terms:
        value = raw.strip()
        lower = value.lower()
        canonical = next((name for name, synonyms in HPO_SYNONYMS.items() if lower == name or lower in {item.lower() for item in synonyms}), value)
        identifier = next((item for item in HPO_SYNONYMS.get(canonical, set()) if item.startswith("HP:")), "")
        rows.append({"input": value, "canonical_term": canonical, "hpo_id": identifier, "normalized": bool(identifier)})
    return pd.DataFrame(rows)


def phenotype_gene_similarity(hpo_terms: Sequence[str], gene_phenotypes: pd.DataFrame) -> pd.DataFrame:
    if gene_phenotypes.empty or not {"gene", "phenotype"}.issubset(gene_phenotypes.columns):
        return pd.DataFrame(columns=["gene", "phenotype_similarity", "matched_terms"])
    query = {term.lower() for term in normalize_hpo_terms(hpo_terms)["canonical_term"].astype(str)}
    rows = []
    for gene, group in gene_phenotypes.groupby("gene"):
        terms = {str(value).lower() for value in group["phenotype"]}
        intersection = query & terms
        union = query | terms
        rows.append({"gene": str(gene), "phenotype_similarity": len(intersection) / max(1, len(union)), "matched_terms": ", ".join(sorted(intersection)), "gene_phenotype_terms": len(terms)})
    return pd.DataFrame(rows).sort_values("phenotype_similarity", ascending=False).reset_index(drop=True)


def formal_acmg_assistance(row: Mapping[str, Any]) -> dict[str, Any]:
    criteria: list[tuple[str, str]] = []
    af = float(row.get("gnomad_af", 0.0) or 0.0)
    consequence = str(row.get("consequence", "")).lower()
    clinvar = str(row.get("clinvar", "")).lower()
    de_novo = bool(row.get("is_de_novo", False))
    segregation = str(row.get("segregation", "")).lower()
    if af >= 0.05:
        criteria.append(("BA1", "stand-alone benign"))
    elif af >= 0.01:
        criteria.append(("BS1", "strong benign"))
    elif af <= 1e-5:
        criteria.append(("PM2_supporting", "supporting pathogenic"))
    if any(token in consequence for token in ["stop_gained", "frameshift", "splice_acceptor", "splice_donor"]):
        criteria.append(("PVS1_candidate", "very strong candidate; gene mechanism review required"))
    if "pathogenic" in clinvar and "conflict" not in clinvar:
        criteria.append(("PP5_review_only", "external assertion; inspect primary evidence"))
    if "benign" in clinvar and "pathogenic" not in clinvar:
        criteria.append(("BP6_review_only", "external benign assertion; inspect primary evidence"))
    if de_novo:
        criteria.append(("PS2_candidate", "de novo candidate; parentage and mosaicism confirmation required"))
    if any(token in segregation for token in ["consistent", "segregates"]):
        criteria.append(("PP1_candidate", "segregation evidence candidate"))
    return {
        "criteria": "; ".join(code for code, _ in criteria),
        "criteria_notes": "; ".join(note for _, note in criteria),
        "pathogenic_strength_count": sum("pathogenic" in strength or "very strong" in strength for _, strength in criteria),
        "benign_strength_count": sum("benign" in strength for _, strength in criteria),
        "classification_boundary": "Review assistance only; no automated ACMG/AMP classification is issued.",
    }


def variant_spectrum_audit(variants: pd.DataFrame) -> pd.DataFrame:
    consequence = variants.get("consequence", pd.Series("unknown", index=variants.index)).astype(str).str.lower()
    type_series = variants.get("variant_type", pd.Series("SNV/indel", index=variants.index)).astype(str)
    category = np.select(
        [type_series.str.contains("cnv|copy", case=False, regex=True), type_series.str.contains("sv|struct", case=False, regex=True), type_series.str.contains("mito|mt", case=False, regex=True), consequence.str.contains("repeat"), consequence.str.contains("splice")],
        ["CNV", "Structural variant", "Mitochondrial", "Repeat expansion", "Splicing"],
        default="SNV/indel",
    )
    counts = pd.Series(category).value_counts().rename_axis("variant_class").reset_index(name="count")
    expected = ["SNV/indel", "CNV", "Structural variant", "Mitochondrial", "Repeat expansion", "Splicing"]
    counts = pd.DataFrame({"variant_class": expected}).merge(counts, on="variant_class", how="left").fillna({"count": 0})
    counts["count"] = counts["count"].astype(int)
    counts["coverage_status"] = np.where(counts["count"] > 0, "Represented", "Not represented in current input")
    return counts


def rare_disease_reanalysis_plan(case_id: str, databases: Mapping[str, str], months: int = 12) -> dict[str, Any]:
    payload = {"case_id": case_id, "reanalysis_interval_months": int(months), "database_releases": dict(databases), "required_actions": ["Refresh ClinVar/gnomAD/ClinGen evidence", "Re-run phenotype-driven ranking", "Review newly established gene-disease relationships", "Reassess VUS and unresolved inheritance", "Document changes and reviewer sign-off"]}
    payload["snapshot_sha256"] = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload


# ---------------------------------------------------------------------------
# 8. Biomedical knowledge graph / evidence retrieval
# ---------------------------------------------------------------------------


def normalize_biomedical_entities(nodes: pd.DataFrame) -> pd.DataFrame:
    if nodes.empty or "node" not in nodes:
        return nodes.copy()
    frame = nodes.copy()
    frame["node"] = frame["node"].astype(str).str.strip()
    frame["type"] = frame.get("type", "Entity").astype(str).str.strip().str.title()
    frame["normalized_key"] = frame["type"].str.lower() + ":" + frame["node"].str.lower().str.replace(r"[^a-z0-9]+", "_", regex=True).str.strip("_")
    frame["duplicate_normalized_key"] = frame["normalized_key"].duplicated(keep=False)
    return frame


def score_evidence_edges(edges: pd.DataFrame) -> pd.DataFrame:
    if edges.empty:
        return edges.copy()
    frame = edges.copy()
    base = _safe_numeric(frame.get("evidence_score", pd.Series(0.5, index=frame.index)), default=0.5).clip(0, 1)
    evidence_type = frame.get("evidence_type", "unspecified").astype(str).str.lower()
    citation = frame.get("citation", "").astype(str)
    direction = frame.get("direction", "unknown").astype(str).str.lower()
    type_weight = np.select(
        [evidence_type.str.contains("meta|systematic"), evidence_type.str.contains("clinical|cohort"), evidence_type.str.contains("experimental|assay"), evidence_type.str.contains("database|curated")],
        [1.0, 0.9, 0.85, 0.75],
        default=0.55,
    )
    citation_weight = np.where(citation.str.len() >= 8, 1.0, 0.65)
    direction_weight = np.where(direction.isin(["positive", "negative", "supports", "contradicts", "increases", "decreases"]), 1.0, 0.8)
    frame["evidence_quality_score"] = (0.55 * base + 0.25 * type_weight + 0.12 * citation_weight + 0.08 * direction_weight).clip(0, 1)
    frame["review_status"] = pd.cut(frame["evidence_quality_score"], [-0.001, 0.55, 0.75, 1.001], labels=["Low evidence", "Moderate", "Strong"]).astype(str)
    frame["edge_key"] = frame.get("source", "").astype(str) + "|" + frame.get("relation", "").astype(str) + "|" + frame.get("target", "").astype(str)
    return frame.sort_values("evidence_quality_score", ascending=False).reset_index(drop=True)


def exact_evidence_retrieval(query: str, documents: pd.DataFrame, top_k: int = 8) -> pd.DataFrame:
    if documents.empty or not query.strip():
        return pd.DataFrame(columns=["document_id", "score", "text", "citation", "sha256"])
    text_col = next((column for column in ["text", "content", "abstract", "snippet"] if column in documents), None)
    if text_col is None:
        raise ValueError("Documents require text, content, abstract, or snippet column.")
    corpus = documents[text_col].fillna("").astype(str).tolist()
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    matrix = vectorizer.fit_transform(corpus + [query])
    scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
    order = np.argsort(scores)[::-1][: max(1, top_k)]
    rows = []
    for idx in order:
        text = corpus[idx]
        identifier = str(documents.iloc[idx].get("document_id", documents.index[idx]))
        citation = str(documents.iloc[idx].get("citation", identifier))
        rows.append({"document_id": identifier, "score": float(scores[idx]), "text": text, "citation": citation, "sha256": sha256(text.encode()).hexdigest()})
    return pd.DataFrame(rows)


def claim_evidence_bundle(query: str, retrieval: pd.DataFrame) -> dict[str, Any]:
    claims = []
    for row in retrieval.itertuples(index=False):
        sentences = re.split(r"(?<=[.!?])\s+", str(row.text))
        excerpt = max(sentences, key=len) if sentences else str(row.text)
        claims.append({"excerpt": excerpt[:500], "citation": row.citation, "document_sha256": row.sha256, "relevance": row.score})
    payload = {"query": query, "claims": claims, "unsupported_conclusion_blocked": len(claims) == 0, "boundary": "Retrieved excerpts support review; they do not establish causal truth automatically."}
    payload["bundle_sha256"] = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload


# ---------------------------------------------------------------------------
# 9. Multi-omics biomarkers
# ---------------------------------------------------------------------------


def harmonize_multiomics_columns(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = frame.copy()
    mapping_rows = []
    used: set[str] = set()
    for column in data.columns:
        normalized = re.sub(r"[^a-z0-9]+", "_", str(column).lower()).strip("_")
        if normalized in {"sample", "sampleid", "id"}:
            normalized = "sample_id"
        candidate = normalized or "feature"
        suffix = 2
        while candidate in used:
            candidate = f"{normalized}_{suffix}"
            suffix += 1
        used.add(candidate)
        layer = candidate.split("_", 1)[0] if "_" in candidate else "unspecified"
        mapping_rows.append({"original": str(column), "harmonized": candidate, "omics_layer": layer, "changed": candidate != str(column)})
    data.columns = [row["harmonized"] for row in mapping_rows]
    return data, pd.DataFrame(mapping_rows)


def multiomics_missingness(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows = []
    for column in frame.columns:
        missing = int(frame[column].isna().sum())
        rows.append({"feature": column, "missing_count": missing, "missing_fraction": missing / max(1, len(frame)), "recommended_action": "Exclude/review" if missing / max(1, len(frame)) > 0.4 else "Multiple imputation" if missing else "None"})
    table = pd.DataFrame(rows).sort_values("missing_fraction", ascending=False)
    return table, {"samples": len(frame), "features": len(frame.columns), "cells_missing_fraction": float(frame.isna().mean().mean()), "features_over_40pct_missing": int((table["missing_fraction"] > 0.4).sum())}


def biomarker_selection_stability(frame: pd.DataFrame, outcome_column: str, feature_columns: Sequence[str], iterations: int = 50, seed: int = 99) -> pd.DataFrame:
    data = frame[[outcome_column] + list(feature_columns)].copy()
    y = pd.to_numeric(data[outcome_column], errors="coerce")
    valid = y.isin([0, 1])
    X = data.loc[valid, feature_columns].apply(pd.to_numeric, errors="coerce")
    yv = y.loc[valid].astype(int).to_numpy()
    if len(np.unique(yv)) < 2 or len(yv) < 20:
        raise ValueError("Selection stability requires at least 20 samples and both outcome classes.")
    rng = np.random.default_rng(seed)
    selected = defaultdict(int)
    coefficient_values: dict[str, list[float]] = defaultdict(list)
    for _ in range(max(10, int(iterations))):
        idx = rng.integers(0, len(X), size=len(X))
        if len(np.unique(yv[idx])) < 2:
            continue
        model = Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("model", LogisticRegression(solver="saga", l1_ratio=1.0, C=0.2, max_iter=2000))])
        model.fit(X.iloc[idx], yv[idx])
        coefficients = model.named_steps["model"].coef_[0]
        for feature, coefficient in zip(feature_columns, coefficients):
            coefficient_values[feature].append(float(coefficient))
            if abs(coefficient) > 1e-8:
                selected[feature] += 1
    rows = []
    completed = max((len(values) for values in coefficient_values.values()), default=1)
    for feature in feature_columns:
        values = coefficient_values.get(feature, [0.0])
        rows.append({"feature": feature, "selection_frequency": selected[feature] / completed, "median_coefficient": float(np.median(values)), "coefficient_iqr": float(np.quantile(values, 0.75) - np.quantile(values, 0.25)), "stability_class": "Stable" if selected[feature] / completed >= 0.7 else "Moderate" if selected[feature] / completed >= 0.4 else "Unstable"})
    return pd.DataFrame(rows).sort_values(["selection_frequency", "median_coefficient"], ascending=[False, False]).reset_index(drop=True)


def decision_curve_analysis(y_true: Sequence[int], probabilities: Sequence[float], thresholds: Sequence[float] | None = None) -> pd.DataFrame:
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(probabilities, dtype=float)
    if thresholds is None:
        thresholds = np.linspace(0.05, 0.90, 18)
    prevalence = y.mean()
    rows = []
    n = len(y)
    for threshold in thresholds:
        prediction = p >= threshold
        tp = int(((prediction == 1) & (y == 1)).sum())
        fp = int(((prediction == 1) & (y == 0)).sum())
        weight = threshold / max(1e-9, 1 - threshold)
        net_benefit = tp / n - fp / n * weight
        treat_all = prevalence - (1 - prevalence) * weight
        rows.append({"threshold": float(threshold), "model_net_benefit": float(net_benefit), "treat_all_net_benefit": float(treat_all), "treat_none_net_benefit": 0.0})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 10. Visual workflows and marketplace
# ---------------------------------------------------------------------------


BLOCK_IO = {
    "FASTQ QC": ({"FASTQ"}, {"QC report", "Filtered FASTQ"}),
    "Read trimming": ({"FASTQ", "Filtered FASTQ"}, {"Filtered FASTQ"}),
    "Genome assembly": ({"FASTQ", "Filtered FASTQ"}, {"FASTA", "GFA"}),
    "Assembly review": ({"FASTA"}, {"Assembly QC report"}),
    "Variant analysis": ({"VCF", "FASTA"}, {"Variant table"}),
    "Protein analysis": ({"FASTA", "Protein FASTA"}, {"Protein table"}),
    "Multi-omics integration": ({"Omics table"}, {"Integrated omics table"}),
    "Report generation": ({"Any"}, {"Report"}),
}


def workflow_schema_audit(dag: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    data = dag.copy()
    produced: dict[str, set[str]] = {}
    rows = []
    for row in data.itertuples(index=False):
        block = str(row.block)
        inputs, outputs = BLOCK_IO.get(block, ({"Any"}, {"Any"}))
        dependencies = [token.strip() for token in str(row.depends_on).split(",") if token.strip()]
        available = set().union(*(produced.get(dep, set()) for dep in dependencies)) if dependencies else {"User input", "Any"}
        compatible = bool("Any" in inputs or "Any" in available or inputs & available or not dependencies)
        rows.append({"id": str(row.id), "block": block, "required_inputs": ", ".join(sorted(inputs)), "available_from_dependencies": ", ".join(sorted(available)), "outputs": ", ".join(sorted(outputs)), "schema_status": "Compatible" if compatible else "Mismatch"})
        produced[str(row.id)] = outputs
    audit = pd.DataFrame(rows)
    return audit, {"steps": len(audit), "compatible": int((audit["schema_status"] == "Compatible").sum()), "mismatches": int((audit["schema_status"] == "Mismatch").sum()), "valid": bool((audit["schema_status"] == "Compatible").all())}


def workflow_critical_path(dag: pd.DataFrame, block_specs: Mapping[str, Mapping[str, Any]]) -> tuple[pd.DataFrame, dict[str, Any]]:
    data = dag.copy()
    durations = {str(row.id): float(block_specs.get(str(row.block), {}).get("minutes", 1.0)) for row in data.itertuples(index=False)}
    dependencies = {str(row.id): [token.strip() for token in str(row.depends_on).split(",") if token.strip()] for row in data.itertuples(index=False)}
    remaining = set(dependencies)
    earliest_finish: dict[str, float] = {}
    predecessor: dict[str, str | None] = {}
    while remaining:
        progressed = False
        for node in list(remaining):
            deps = dependencies[node]
            if all(dep in earliest_finish for dep in deps):
                if deps:
                    parent = max(deps, key=lambda dep: earliest_finish[dep])
                    start = earliest_finish[parent]
                    predecessor[node] = parent
                else:
                    start = 0.0
                    predecessor[node] = None
                earliest_finish[node] = start + durations[node]
                remaining.remove(node)
                progressed = True
        if not progressed:
            raise ValueError("Workflow contains a cycle or unresolved dependency.")
    end = max(earliest_finish, key=earliest_finish.get) if earliest_finish else None
    critical: set[str] = set()
    while end is not None:
        critical.add(end)
        end = predecessor[end]
    table = pd.DataFrame([{"id": node, "duration_minutes": durations[node], "earliest_finish_minutes": earliest_finish[node], "critical_path": node in critical} for node in earliest_finish])
    return table.sort_values("earliest_finish_minutes").reset_index(drop=True), {"critical_path_minutes": max(earliest_finish.values(), default=0.0), "critical_steps": len(critical), "parallelism_opportunity": max(0, len(table) - len(critical))}


def marketplace_trust_score(metadata: pd.DataFrame) -> pd.DataFrame:
    if metadata.empty:
        return metadata.copy()
    frame = metadata.copy()
    bool_columns = ["signed", "tests_passed", "container_pinned", "license_declared", "example_data", "security_scanned"]
    for column in bool_columns:
        if column not in frame:
            frame[column] = False
        frame[column] = frame[column].astype(bool)
    frame["trust_score"] = 100 * (
        0.25 * frame["signed"].astype(float)
        + 0.20 * frame["tests_passed"].astype(float)
        + 0.15 * frame["container_pinned"].astype(float)
        + 0.15 * frame["license_declared"].astype(float)
        + 0.10 * frame["example_data"].astype(float)
        + 0.15 * frame["security_scanned"].astype(float)
    )
    frame["trust_tier"] = pd.cut(frame["trust_score"], [-0.1, 49, 79, 100.1], labels=["Experimental", "Reviewed", "Verified"]).astype(str)
    return frame.sort_values("trust_score", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 11. Innovation hub readiness
# ---------------------------------------------------------------------------


MODULE_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "Innovation Modules Hub": {"tools": [], "gpu": False, "internet": False, "maturity": "Production UI"},
    "Pangenome & Variation Graph Studio": {"tools": ["odgi", "vg", "minigraph"], "gpu": False, "internet": False, "maturity": "Research-ready"},
    "Long-Read Assembly & T2T Studio": {"tools": ["flye", "hifiasm", "quast", "busco"], "gpu": False, "internet": False, "maturity": "Research-ready"},
    "AI Protein Design & Mutation Engineering Lab": {"tools": ["proteinmpnn", "rfdiffusion", "colabfold_batch"], "gpu": True, "internet": False, "maturity": "Experimental"},
    "CRISPR Screen & Perturb-seq Analytics": {"tools": ["mageck"], "gpu": False, "internet": False, "maturity": "Research-ready"},
    "Pathogen Outbreak Genomics Command Center": {"tools": ["mash", "iqtree", "amrfinderplus"], "gpu": False, "internet": False, "maturity": "Research-ready"},
    "Synthetic Biology & Genetic Circuit Designer": {"tools": [], "gpu": False, "internet": False, "maturity": "Research-ready"},
    "Rare Disease Genome Interpretation Board": {"tools": ["bcftools", "vep", "snpeff"], "gpu": False, "internet": True, "maturity": "Research support only"},
    "Biomedical Knowledge Graph & Evidence Copilot": {"tools": [], "gpu": False, "internet": False, "maturity": "Research-ready"},
    "Multi-Omics Biomarker Discovery Studio": {"tools": [], "gpu": False, "internet": False, "maturity": "Research-ready"},
    "Visual Workflow Builder & Pipeline Marketplace": {"tools": [], "gpu": False, "internet": False, "maturity": "Research-ready"},
}


def innovation_readiness(tool_status: Mapping[str, bool]) -> pd.DataFrame:
    rows = []
    for module, requirement in MODULE_REQUIREMENTS.items():
        tools = requirement["tools"]
        present = [tool for tool in tools if tool_status.get(tool, False)]
        fraction = len(present) / max(1, len(tools)) if tools else 1.0
        if not tools:
            status = "Ready"
        elif fraction == 1:
            status = "Ready"
        elif fraction > 0:
            status = "Partially ready"
        else:
            status = "External tools missing"
        rows.append({
            "module": module,
            "status": status,
            "maturity": requirement["maturity"],
            "tools_required": ", ".join(tools) or "None",
            "tools_detected": ", ".join(present) or "None",
            "tool_readiness": fraction,
            "gpu_required": bool(requirement["gpu"]),
            "internet_may_be_required": bool(requirement["internet"]),
        })
    return pd.DataFrame(rows)


def innovation_recommendations(readiness: pd.DataFrame, role: str, has_gpu: bool, prefers_offline: bool) -> pd.DataFrame:
    frame = readiness.copy()
    role_boost = {
        "Bioinformatician": ["Pangenome", "Long-Read", "Outbreak", "Rare Disease"],
        "Drug discovery scientist": ["Protein Design", "Knowledge Graph", "Multi-Omics"],
        "Wet-lab scientist": ["CRISPR", "Synthetic Biology", "Multi-Omics"],
        "Platform engineer": ["Visual Workflow", "Innovation"],
    }
    keywords = role_boost.get(role, [])
    frame["recommendation_score"] = frame["tool_readiness"] * 60
    frame["recommendation_score"] += frame["module"].apply(lambda name: 25 if any(keyword in name for keyword in keywords) else 0)
    frame["recommendation_score"] -= np.where(frame["gpu_required"] & (not has_gpu), 20, 0)
    frame["recommendation_score"] -= np.where(frame["internet_may_be_required"] & prefers_offline, 10, 0)
    frame["why"] = frame.apply(lambda row: f"{row['status']}; maturity={row['maturity']}" + ("; GPU unavailable" if row["gpu_required"] and not has_gpu else ""), axis=1)
    return frame.sort_values("recommendation_score", ascending=False).reset_index(drop=True)
