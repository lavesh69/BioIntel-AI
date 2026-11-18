from __future__ import annotations

from collections import defaultdict, deque
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import shutil
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import stats
from scipy.integrate import solve_ivp
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import pairwise_distances
from sklearn.preprocessing import StandardScaler

from .common import (
    _normalise_identifier, _numeric, _safe_run, _split_tokens,
    hardware_profile, runtime_capability_scan, stable_frame_hash, stable_payload_hash,
)

# ---------------------------------------------------------------------------
# Pangenome and graph genomics
# ---------------------------------------------------------------------------


def graph_components(nodes: pd.DataFrame, edges: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    node_values = [str(value) for value in nodes.get("node", pd.Series(dtype=str)).tolist()]
    adjacency: dict[str, set[str]] = {node: set() for node in node_values}
    for row in edges.itertuples(index=False):
        source = str(getattr(row, "source", ""))
        target = str(getattr(row, "target", ""))
        if source:
            adjacency.setdefault(source, set()).add(target)
        if target:
            adjacency.setdefault(target, set()).add(source)
    visited: set[str] = set()
    records: list[dict[str, Any]] = []
    component_id = 0
    for root in sorted(adjacency):
        if root in visited:
            continue
        component_id += 1
        queue = deque([root])
        visited.add(root)
        members: list[str] = []
        while queue:
            current = queue.popleft()
            members.append(current)
            for neighbour in sorted(adjacency.get(current, set())):
                if neighbour and neighbour not in visited:
                    visited.add(neighbour)
                    queue.append(neighbour)
        for member in members:
            records.append({"node": member, "component": component_id, "component_size": len(members)})
    table = pd.DataFrame(records)
    report = {
        "components": int(table["component"].nunique()) if not table.empty else 0,
        "largest_component_nodes": int(table["component_size"].max()) if not table.empty else 0,
        "singleton_components": int((table.groupby("component")["node"].count() == 1).sum()) if not table.empty else 0,
        "connected": bool(table["component"].nunique() <= 1) if not table.empty else False,
    }
    report["graph_sha256"] = stable_payload_hash({"nodes": sorted(adjacency), "edges": sorted((str(a), str(b)) for a, b in zip(edges.get("source", []), edges.get("target", [])))})
    return table.sort_values(["component_size", "component", "node"], ascending=[False, True, True]), report


def graph_path_genotypes(paths: pd.DataFrame, bubbles: pd.DataFrame) -> pd.DataFrame:
    if paths.empty or bubbles.empty or "nodes" not in paths:
        return pd.DataFrame()
    path_sets = {str(row.path): set(_split_tokens(row.nodes)) for row in paths.itertuples(index=False)}
    rows: list[dict[str, Any]] = []
    for bubble in bubbles.itertuples(index=False):
        start = str(getattr(bubble, "start", ""))
        end = str(getattr(bubble, "end", ""))
        roots = _split_tokens(getattr(bubble, "branch_roots", ""))
        bubble_id = f"{start}>{end}"
        for path_name, members in path_sets.items():
            present = [root for root in roots if root in members]
            genotype = "0/0" if len(present) == 0 else "1/1" if len(present) == 1 else "1/2"
            rows.append({
                "bubble_id": bubble_id,
                "path": path_name,
                "branch_roots": ",".join(roots),
                "observed_branches": ",".join(present),
                "screening_genotype": genotype,
                "review_flag": "Ambiguous multi-branch path" if len(present) > 1 else "",
            })
    return pd.DataFrame(rows)


def graph_gene_presence(paths: pd.DataFrame, annotations: pd.DataFrame) -> pd.DataFrame:
    required = {"node", "gene"}
    if paths.empty or annotations.empty or not required.issubset(annotations.columns):
        return pd.DataFrame()
    annotation = annotations.copy()
    annotation["node"] = annotation["node"].astype(str)
    node_genes = annotation.groupby("node")["gene"].apply(lambda values: sorted({str(v) for v in values if str(v)})).to_dict()
    records: list[dict[str, Any]] = []
    all_genes = sorted({gene for genes in node_genes.values() for gene in genes})
    for row in paths.itertuples(index=False):
        path_nodes = _split_tokens(getattr(row, "nodes", ""))
        observed = {gene for node in path_nodes for gene in node_genes.get(node, [])}
        record = {"path": str(getattr(row, "path", ""))}
        record.update({gene: int(gene in observed) for gene in all_genes})
        records.append(record)
    return pd.DataFrame(records)


def graph_release_diff(current_nodes: pd.DataFrame, current_edges: pd.DataFrame, candidate_nodes: pd.DataFrame, candidate_edges: pd.DataFrame) -> dict[str, Any]:
    current_node_set = set(current_nodes.get("node", pd.Series(dtype=str)).astype(str))
    candidate_node_set = set(candidate_nodes.get("node", pd.Series(dtype=str)).astype(str))
    current_edge_set = set(zip(current_edges.get("source", pd.Series(dtype=str)).astype(str), current_edges.get("target", pd.Series(dtype=str)).astype(str)))
    candidate_edge_set = set(zip(candidate_edges.get("source", pd.Series(dtype=str)).astype(str), candidate_edges.get("target", pd.Series(dtype=str)).astype(str)))
    report = {
        "nodes_added": sorted(candidate_node_set - current_node_set),
        "nodes_removed": sorted(current_node_set - candidate_node_set),
        "edges_added": sorted(candidate_edge_set - current_edge_set),
        "edges_removed": sorted(current_edge_set - candidate_edge_set),
    }
    report["breaking_change"] = bool(report["nodes_removed"] or report["edges_removed"])
    report["diff_sha256"] = stable_payload_hash(report)
    return report
# ---------------------------------------------------------------------------
# Long-read assembly and T2T
# ---------------------------------------------------------------------------


def assembly_contamination_screen(contigs: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if contigs.empty:
        return pd.DataFrame(), {"contigs": 0, "review": 0}
    frame = contigs.copy()
    length_column = next((column for column in ("length", "len", "size") if column in frame.columns), None)
    gc_column = next((column for column in ("gc", "gc_percent", "gc_content") if column in frame.columns), None)
    if length_column is None:
        frame["length"] = 0
        length_column = "length"
    length = _numeric(frame[length_column])
    log_length = np.log10(np.maximum(length, 1))
    if gc_column is not None:
        gc = _numeric(frame[gc_column])
        if gc.max() <= 1.0:
            gc = gc * 100.0
    else:
        gc = pd.Series(np.nan, index=frame.index)
    def robust_z(values: pd.Series) -> pd.Series:
        valid = values.dropna()
        if valid.empty:
            return pd.Series(0.0, index=values.index)
        median = float(valid.median())
        mad = float(np.median(np.abs(valid - median)))
        if mad <= 1e-12:
            std = float(valid.std(ddof=0))
            return (values - median) / std if std > 1e-12 else pd.Series(0.0, index=values.index)
        return 0.6745 * (values - median) / mad
    frame["length_robust_z"] = robust_z(pd.Series(log_length, index=frame.index)).fillna(0.0)
    frame["gc_robust_z"] = robust_z(pd.Series(gc, index=frame.index)).fillna(0.0)
    frame["composition_outlier"] = (frame["gc_robust_z"].abs() >= 3.5) | (frame["length_robust_z"].abs() >= 4.0)
    frame["review_reason"] = np.where(frame["composition_outlier"], "Composition/length outlier; confirm with taxonomic classification", "")
    report = {
        "contigs": len(frame),
        "review": int(frame["composition_outlier"].sum()),
        "review_fraction": float(frame["composition_outlier"].mean()),
        "boundary": "Statistical outlier screening is not taxonomic contamination identification.",
        "contig_table_sha256": stable_frame_hash(frame),
    }
    return frame, report


def assembly_iteration_compare(iterations: pd.DataFrame) -> pd.DataFrame:
    if iterations.empty:
        return pd.DataFrame()
    frame = iterations.copy()
    aliases = {
        "iteration": ("iteration", "round", "stage"),
        "n50": ("n50", "contig_n50"),
        "busco_complete": ("busco_complete", "busco", "completeness"),
        "qv": ("qv", "merqury_qv"),
        "errors": ("errors", "mismatches", "error_count"),
    }
    for target, candidates in aliases.items():
        source = next((column for column in candidates if column in frame.columns), None)
        if source is not None and target not in frame:
            frame[target] = frame[source]
    if "iteration" not in frame:
        frame["iteration"] = np.arange(1, len(frame) + 1)
    for column in ("n50", "busco_complete", "qv", "errors"):
        if column not in frame:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.sort_values("iteration").reset_index(drop=True)
    for column in ("n50", "busco_complete", "qv"):
        frame[f"delta_{column}"] = frame[column].diff()
    frame["delta_errors"] = -frame["errors"].diff()
    benefits = frame[["delta_n50", "delta_busco_complete", "delta_qv", "delta_errors"]].fillna(0.0)
    scale = benefits.abs().replace(0, np.nan).median().replace(0, 1).fillna(1)
    frame["marginal_gain_score"] = (benefits / scale).sum(axis=1)
    frame["diminishing_returns"] = frame["marginal_gain_score"].rolling(2).mean().fillna(frame["marginal_gain_score"]) < 0.25
    return frame


def assembly_storage_guard(genome_size_mb: float, coverage: float, platform_name: str, free_disk_gb: float | None) -> dict[str, Any]:
    genome_size_mb = max(float(genome_size_mb), 0.01)
    coverage = max(float(coverage), 1.0)
    raw_gb = genome_size_mb * coverage / 1000.0
    multiplier = 12.0 if "Nanopore" in platform_name else 9.0 if "HiFi" in platform_name else 14.0
    recommended_gb = max(10.0, raw_gb * multiplier)
    report = {
        "estimated_raw_reads_gb": round(raw_gb, 2),
        "recommended_workspace_gb": round(recommended_gb, 2),
        "free_disk_gb": free_disk_gb,
        "passes_disk_guard": bool(free_disk_gb is None or free_disk_gb >= recommended_gb * 1.15),
        "assumption": "Includes temporary indexes, overlaps, polishing intermediates and a 15% safety margin.",
    }
    report["plan_sha256"] = stable_payload_hash(report)
    return report


def assembly_tool_plan(platform_name: str, hybrid_polish: bool, phased: bool) -> pd.DataFrame:
    rows = [
        {"stage": 1, "purpose": "Input QC", "preferred_tools": "NanoPlot/FastQC/SeqKit", "required": True},
        {"stage": 2, "purpose": "Primary assembly", "preferred_tools": "hifiasm" if "HiFi" in platform_name else "Flye/Canu", "required": True},
        {"stage": 3, "purpose": "Consensus polishing", "preferred_tools": "GCpp" if "HiFi" in platform_name else "Racon + Medaka", "required": True},
        {"stage": 4, "purpose": "Short-read polishing", "preferred_tools": "NextPolish/Pilon", "required": bool(hybrid_polish)},
        {"stage": 5, "purpose": "Haplotype cleanup", "preferred_tools": "purge_dups + phasing QC", "required": bool(phased)},
        {"stage": 6, "purpose": "Completeness/QV", "preferred_tools": "BUSCO + QUAST + Merqury", "required": True},
        {"stage": 7, "purpose": "T2T structure", "preferred_tools": "telomere/centromere/rDNA repeat audit", "required": True},
    ]
    return pd.DataFrame(rows)
# ---------------------------------------------------------------------------
# Pathogen outbreak genomics
# ---------------------------------------------------------------------------


ORGANISM_PROFILES: dict[str, dict[str, Any]] = {
    "SARS-CoV-2": {"screening_distance": 3, "time_window_days": 14, "recombination_review": True},
    "Mycobacterium tuberculosis": {"screening_distance": 5, "time_window_days": 365, "recombination_review": False},
    "Salmonella enterica": {"screening_distance": 10, "time_window_days": 60, "recombination_review": True},
    "Escherichia coli": {"screening_distance": 10, "time_window_days": 60, "recombination_review": True},
    "Klebsiella pneumoniae": {"screening_distance": 15, "time_window_days": 90, "recombination_review": True},
}


def outbreak_temporal_signal(samples: pd.DataFrame, distances: pd.DataFrame) -> dict[str, Any]:
    if samples.empty or distances.empty or "sample_id" not in samples or "collection_date" not in samples:
        return {"pairs": 0, "temporal_signal": None, "status": "Insufficient metadata"}
    metadata = samples.copy()
    metadata["sample_id"] = metadata["sample_id"].astype(str)
    metadata["collection_date"] = pd.to_datetime(metadata["collection_date"], errors="coerce")
    dates = metadata.set_index("sample_id")["collection_date"]
    records: list[tuple[float, float]] = []
    common = [sample for sample in distances.index.astype(str) if sample in dates.index]
    matrix = distances.copy()
    matrix.index = matrix.index.astype(str)
    matrix.columns = matrix.columns.astype(str)
    for i, left in enumerate(common):
        for right in common[i + 1:]:
            if right not in matrix.columns or left not in matrix.index:
                continue
            genetic = pd.to_numeric(pd.Series([matrix.loc[left, right]]), errors="coerce").iloc[0]
            if pd.isna(genetic) or pd.isna(dates[left]) or pd.isna(dates[right]):
                continue
            days = abs((dates[left] - dates[right]).days)
            records.append((float(days), float(genetic)))
    if len(records) < 4:
        return {"pairs": len(records), "temporal_signal": None, "status": "At least four dated pairs required"}
    days = np.asarray([row[0] for row in records])
    genetic = np.asarray([row[1] for row in records])
    correlation, p_value = stats.spearmanr(days, genetic)
    return {
        "pairs": len(records),
        "spearman_time_distance": float(correlation) if np.isfinite(correlation) else None,
        "p_value": float(p_value) if np.isfinite(p_value) else None,
        "status": "Temporal signal observed" if np.isfinite(correlation) and correlation > 0.25 and p_value < 0.05 else "Weak/uncertain temporal signal",
        "boundary": "This is a screening correlation, not a calibrated molecular-clock analysis.",
    }


def outbreak_case_audit(samples: pd.DataFrame, organism: str) -> pd.DataFrame:
    profile = ORGANISM_PROFILES.get(organism, {"screening_distance": 10, "time_window_days": 60, "recombination_review": True})
    fields = {
        "sample_id": "Required",
        "collection_date": "Required",
        "location": "Recommended",
        "patient_id": "Recommended and de-identified",
        "specimen_type": "Recommended",
        "onset_date": "Recommended",
        "ward": "Recommended for healthcare outbreaks",
        "latitude": "Optional",
        "longitude": "Optional",
    }
    rows = []
    for field, expectation in fields.items():
        present = field in samples and samples[field].notna().any()
        rows.append({"field": field, "expectation": expectation, "present": present, "status": "Pass" if present else "Review"})
    rows.append({"field": "organism_profile", "expectation": organism, "present": True, "status": f"Screening distance {profile['screening_distance']}"})
    return pd.DataFrame(rows)


def outbreak_geospatial_summary(samples: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if samples.empty or not {"latitude", "longitude"}.issubset(samples.columns):
        return pd.DataFrame(), {"mapped_samples": 0, "status": "Latitude/longitude unavailable"}
    frame = samples.copy()
    frame["latitude"] = pd.to_numeric(frame["latitude"], errors="coerce")
    frame["longitude"] = pd.to_numeric(frame["longitude"], errors="coerce")
    valid = frame[frame["latitude"].between(-90, 90) & frame["longitude"].between(-180, 180)].copy()
    if valid.empty:
        return valid, {"mapped_samples": 0, "status": "No valid coordinates"}
    valid["coordinate_rounding"] = valid["latitude"].round(3).astype(str) + "," + valid["longitude"].round(3).astype(str)
    report = {
        "mapped_samples": len(valid),
        "unique_locations": int(valid["coordinate_rounding"].nunique()),
        "latitude_range": [float(valid["latitude"].min()), float(valid["latitude"].max())],
        "longitude_range": [float(valid["longitude"].min()), float(valid["longitude"].max())],
        "privacy_note": "Use appropriately de-identified or aggregated coordinates for human outbreak data.",
    }
    return valid, report
# ---------------------------------------------------------------------------
# Rare disease interpretation support
# ---------------------------------------------------------------------------


HPO_SYNONYMS = {
    "seizure": "HP:0001250",
    "seizures": "HP:0001250",
    "hypotonia": "HP:0001252",
    "developmental delay": "HP:0001263",
    "intellectual disability": "HP:0001249",
    "microcephaly": "HP:0000252",
    "ataxia": "HP:0001251",
}


def phenotype_semantic_screen(patient_terms: Sequence[str], gene_phenotypes: pd.DataFrame) -> pd.DataFrame:
    if gene_phenotypes.empty or "gene" not in gene_phenotypes:
        return pd.DataFrame()
    patient = {_normalise_hpo(term) for term in patient_terms if str(term).strip()}
    rows = []
    phenotype_column = next((column for column in ("hpo_terms", "phenotypes", "hpo", "terms") if column in gene_phenotypes), None)
    if phenotype_column is None:
        return pd.DataFrame()
    for row in gene_phenotypes.itertuples(index=False):
        gene = str(getattr(row, "gene"))
        raw = getattr(row, phenotype_column)
        terms = {_normalise_hpo(term) for term in re.split(r"[,;|]", str(raw)) if term.strip()}
        intersection = patient & terms
        union = patient | terms
        score = len(intersection) / len(union) if union else 0.0
        recall = len(intersection) / len(patient) if patient else 0.0
        rows.append({
            "gene": gene,
            "matching_terms": ",".join(sorted(intersection)),
            "gene_term_count": len(terms),
            "jaccard_similarity": score,
            "patient_term_recall": recall,
            "review_priority": "High" if recall >= 0.5 and score >= 0.25 else "Moderate" if intersection else "Low",
        })
    return pd.DataFrame(rows).sort_values(["patient_term_recall", "jaccard_similarity"], ascending=False)


def _normalise_hpo(term: str) -> str:
    value = str(term).strip()
    if re.fullmatch(r"HP:\d{7}", value.upper()):
        return value.upper()
    return HPO_SYNONYMS.get(value.lower(), value.lower())


def inheritance_model_screen(variants: pd.DataFrame, proband_sex: str = "Unknown") -> pd.DataFrame:
    if variants.empty:
        return pd.DataFrame()
    frame = variants.copy()
    gene_column = next((column for column in ("gene", "symbol", "gene_symbol") if column in frame), None)
    zygosity_column = next((column for column in ("zygosity", "genotype", "gt") if column in frame), None)
    chromosome_column = next((column for column in ("chrom", "chromosome", "chr") if column in frame), None)
    if gene_column is None:
        frame["gene"] = "Unknown"
        gene_column = "gene"
    if zygosity_column is None:
        frame["zygosity"] = "unknown"
        zygosity_column = "zygosity"
    if chromosome_column is None:
        frame["chromosome"] = ""
        chromosome_column = "chromosome"
    frame["gene"] = frame[gene_column].astype(str)
    frame["zygosity_norm"] = frame[zygosity_column].astype(str).str.lower()
    frame["chromosome_norm"] = frame[chromosome_column].astype(str).str.upper().str.replace("CHR", "", regex=False)
    rows = []
    for gene, group in frame.groupby("gene"):
        heterozygous = group["zygosity_norm"].str.contains("het|0/1|1/0", regex=True).sum()
        homozygous = group["zygosity_norm"].str.contains("hom|1/1", regex=True).sum()
        x_linked = bool((group["chromosome_norm"] == "X").any())
        models = []
        if homozygous:
            models.append("Autosomal recessive homozygous candidate")
        if heterozygous >= 2:
            models.append("Compound-heterozygous candidate; phase required")
        if heterozygous >= 1:
            models.append("Dominant/de-novo candidate; parental evidence required")
        if x_linked and proband_sex.lower().startswith("m"):
            models.append("X-linked candidate")
        rows.append({
            "gene": gene,
            "variant_count": len(group),
            "heterozygous_count": int(heterozygous),
            "homozygous_count": int(homozygous),
            "candidate_models": "; ".join(models) if models else "No model inferred",
            "review_flag": "Phase/segregation required" if heterozygous >= 2 else "",
        })
    return pd.DataFrame(rows).sort_values("variant_count", ascending=False)


def acmg_points_assistance(criteria: Sequence[str]) -> dict[str, Any]:
    weights = {
        "PVS1": 8,
        "PS1": 4, "PS2": 4, "PS3": 4, "PS4": 4,
        "PM1": 2, "PM2": 2, "PM3": 2, "PM4": 2, "PM5": 2, "PM6": 2,
        "PP1": 1, "PP2": 1, "PP3": 1, "PP4": 1, "PP5": 1,
        "BA1": -8,
        "BS1": -4, "BS2": -4, "BS3": -4, "BS4": -4,
        "BP1": -1, "BP2": -1, "BP3": -1, "BP4": -1, "BP5": -1, "BP6": -1, "BP7": -1,
    }
    normalized = [str(value).strip().upper() for value in criteria if str(value).strip()]
    unknown = sorted(set(normalized) - set(weights))
    score = sum(weights.get(value, 0) for value in normalized)
    if score >= 10:
        label = "Pathogenic-supporting point range"
    elif score >= 6:
        label = "Likely-pathogenic-supporting point range"
    elif score <= -7:
        label = "Benign-supporting point range"
    elif score <= -3:
        label = "Likely-benign-supporting point range"
    else:
        label = "Uncertain point range"
    report = {
        "criteria": normalized,
        "unknown_criteria": unknown,
        "point_score": score,
        "screening_label": label,
        "review_required": True,
        "boundary": "Decision support only. Criterion strength, disease mechanism, transcript context and expert review remain mandatory.",
    }
    report["assessment_sha256"] = stable_payload_hash(report)
    return report


def variant_normalisation_audit(variants: pd.DataFrame) -> pd.DataFrame:
    if variants.empty:
        return pd.DataFrame()
    frame = variants.copy()
    aliases = {
        "chrom": ("chrom", "chromosome", "chr"),
        "pos": ("pos", "position", "start"),
        "ref": ("ref", "reference"),
        "alt": ("alt", "alternate"),
        "build": ("build", "genome_build", "assembly"),
        "transcript": ("transcript", "transcript_id", "mane_transcript"),
        "hgvs": ("hgvs", "hgvsc", "hgvsp"),
    }
    for target, candidates in aliases.items():
        source = next((candidate for candidate in candidates if candidate in frame), None)
        frame[target] = frame[source] if source else ""
    frame["pos_numeric"] = pd.to_numeric(frame["pos"], errors="coerce")
    frame["alleles_valid"] = frame["ref"].astype(str).str.fullmatch(r"[ACGTN]+", na=False) & frame["alt"].astype(str).str.fullmatch(r"[ACGTN,*<>\[\]]+", na=False)
    frame["build_declared"] = frame["build"].astype(str).str.len() > 0
    frame["transcript_declared"] = frame["transcript"].astype(str).str.len() > 0
    frame["hgvs_declared"] = frame["hgvs"].astype(str).str.len() > 0
    frame["normalisation_status"] = np.select(
        [frame["pos_numeric"].isna(), ~frame["alleles_valid"], ~frame["build_declared"]],
        ["Invalid/missing coordinate", "Allele requires review", "Genome build missing"],
        default="Screening format valid",
    )
    frame["boundary"] = "Left alignment, reference validation, liftover and HGVS validation require a reference genome/transcript service."
    return frame
