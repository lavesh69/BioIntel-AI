from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import sparse, stats
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from .ingestion import format_support_table

BOUNDARY = (
    "Internal research-software analysis only. Outputs do not establish clinical, "
    "regulatory, wet-lab or external scientific validity."
)


def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Input must be a pandas DataFrame.")
    if frame.empty:
        raise ValueError("Input table is empty.")
    output = frame.copy()
    output.columns = [re.sub(r"[^a-z0-9]+", "_", str(column).strip().lower()).strip("_") for column in output.columns]
    return output


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def genomic_cohort_qc(data: pd.DataFrame) -> dict[str, Any]:
    frame = _normalise(data)
    sample_col = next((column for column in ("sample_id", "sample", "subject_id", "id") if column in frame), None)
    if sample_col is None:
        raise ValueError("Cohort metadata requires a sample identifier column.")
    duplicate = frame[sample_col].astype(str).duplicated(keep=False)
    build_col = next((column for column in ("genome_build", "assembly", "reference_build", "build") if column in frame), None)
    builds = frame[build_col].fillna("unknown").astype(str).str.strip() if build_col else pd.Series(["unknown"] * len(frame))
    batch_col = next((column for column in ("batch", "site", "sequencing_batch", "center") if column in frame), None)
    group_col = next((column for column in ("group", "condition", "phenotype", "case_control") if column in frame), None)
    confounding = pd.DataFrame()
    if batch_col and group_col:
        table = pd.crosstab(frame[batch_col].fillna("[missing]"), frame[group_col].fillna("[missing]"))
        expected = np.outer(table.sum(axis=1), table.sum(axis=0)) / max(table.to_numpy().sum(), 1)
        observed = table.to_numpy(dtype=float)
        mask = expected > 0
        chi2 = float(np.sum(((observed - expected) ** 2)[mask] / expected[mask]))
        total = float(observed.sum())
        denom = max(min(table.shape[0] - 1, table.shape[1] - 1), 1)
        cramers_v = math.sqrt(max(0.0, chi2 / max(total * denom, 1e-12)))
        confounding = table.reset_index()
    else:
        cramers_v = np.nan
    sex_col = next((column for column in ("reported_sex", "sex", "gender") if column in frame), None)
    inferred_col = next((column for column in ("inferred_sex", "genetic_sex") if column in frame), None)
    sex_mismatch = pd.Series(False, index=frame.index)
    if sex_col and inferred_col:
        left = frame[sex_col].astype(str).str.upper().str[0]
        right = frame[inferred_col].astype(str).str.upper().str[0]
        sex_mismatch = left.ne(right) & left.isin(["M", "F"]) & right.isin(["M", "F"])
    relatedness_col = next((column for column in ("relatedness", "kinship", "pi_hat") if column in frame), None)
    high_relatedness = _numeric(frame[relatedness_col]).fillna(0) > 0.185 if relatedness_col else pd.Series(False, index=frame.index)
    missing = frame.isna().mean(axis=1)
    sample_qc = pd.DataFrame(
        {
            "sample_id": frame[sample_col].astype(str),
            "duplicate_sample_id": duplicate,
            "row_missing_fraction": missing,
            "sex_mismatch_candidate": sex_mismatch,
            "high_relatedness_candidate": high_relatedness,
            "genome_build": builds,
        }
    )
    flags = sample_qc[["duplicate_sample_id", "sex_mismatch_candidate", "high_relatedness_candidate"]].sum(axis=1) + (sample_qc["row_missing_fraction"] > 0.25)
    sample_qc["review_flag_count"] = flags.astype(int)
    contig_col = next((column for column in ("contig", "chromosome", "chrom") if column in frame), None)
    contig_style = "not supplied"
    if contig_col:
        values = frame[contig_col].dropna().astype(str)
        if len(values):
            has_chr = values.str.lower().str.startswith("chr").mean()
            contig_style = "chr-prefixed" if has_chr > 0.8 else "unprefixed" if has_chr < 0.2 else "mixed"
    return {
        "sample_qc": sample_qc.sort_values(["review_flag_count", "sample_id"], ascending=[False, True]).reset_index(drop=True),
        "batch_group_table": confounding,
        "summary": {
            "samples": int(len(frame)),
            "unique_sample_ids": int(frame[sample_col].astype(str).nunique()),
            "duplicate_rows": int(duplicate.sum()),
            "builds": sorted(set(builds)),
            "mixed_builds": len(set(builds)) > 1,
            "contig_style": contig_style,
            "batch_group_cramers_v": float(cramers_v) if math.isfinite(cramers_v) else None,
            "samples_with_flags": int((sample_qc["review_flag_count"] > 0).sum()),
        },
        "scientific_boundary": BOUNDARY,
    }


def single_cell_qc(
    matrix: pd.DataFrame | np.ndarray | sparse.spmatrix,
    *,
    gene_names: Sequence[str] | None = None,
    cell_ids: Sequence[str] | None = None,
    mitochondrial_prefixes: Sequence[str] = ("MT-", "mt-"),
) -> dict[str, Any]:
    if isinstance(matrix, pd.DataFrame):
        values = matrix.to_numpy(dtype=float)
        genes = list(gene_names or matrix.columns.astype(str))
        cells = list(cell_ids or matrix.index.astype(str))
    elif sparse.issparse(matrix):
        values = matrix.tocsr()
        genes = list(gene_names or [f"gene_{i+1}" for i in range(values.shape[1])])
        cells = list(cell_ids or [f"cell_{i+1}" for i in range(values.shape[0])])
    else:
        values = np.asarray(matrix, dtype=float)
        genes = list(gene_names or [f"gene_{i+1}" for i in range(values.shape[1])])
        cells = list(cell_ids or [f"cell_{i+1}" for i in range(values.shape[0])])
    if len(values.shape) != 2 or values.shape[0] < 2 or values.shape[1] < 2:
        raise ValueError("Single-cell matrix must be two-dimensional with at least two cells and genes.")
    if len(genes) != values.shape[1] or len(cells) != values.shape[0]:
        raise ValueError("Gene and cell identifiers must match matrix dimensions.")
    if sparse.issparse(values):
        library = np.asarray(values.sum(axis=1)).ravel()
        detected = np.diff(values.indptr)
        negative = int((values.data < 0).sum())
        zero_fraction = 1.0 - values.nnz / (values.shape[0] * values.shape[1])
        mito_indices = [i for i, gene in enumerate(genes) if any(str(gene).startswith(prefix) for prefix in mitochondrial_prefixes)]
        mito = np.asarray(values[:, mito_indices].sum(axis=1)).ravel() if mito_indices else np.zeros(values.shape[0])
    else:
        finite_values = np.nan_to_num(values, nan=0.0)
        library = finite_values.sum(axis=1)
        detected = (finite_values > 0).sum(axis=1)
        negative = int((finite_values < 0).sum())
        zero_fraction = float((finite_values == 0).mean())
        mito_indices = [i for i, gene in enumerate(genes) if any(str(gene).startswith(prefix) for prefix in mitochondrial_prefixes)]
        mito = finite_values[:, mito_indices].sum(axis=1) if mito_indices else np.zeros(values.shape[0])
    mito_fraction = mito / np.where(library > 0, library, np.nan)
    log_library = np.log1p(library)
    lib_z = (log_library - np.nanmedian(log_library)) / (np.nanmedian(np.abs(log_library - np.nanmedian(log_library))) * 1.4826 + 1e-12)
    genes_z = (detected - np.nanmedian(detected)) / (np.nanmedian(np.abs(detected - np.nanmedian(detected))) * 1.4826 + 1e-12)
    doublet_proxy = (lib_z > 3.5) & (genes_z > 3.5)
    low_quality = (lib_z < -3.5) | (genes_z < -3.5) | (mito_fraction > 0.25)
    cell_qc = pd.DataFrame(
        {
            "cell_id": cells,
            "library_size": library,
            "detected_genes": detected,
            "mitochondrial_fraction": mito_fraction,
            "doublet_proxy": doublet_proxy,
            "low_quality_candidate": low_quality,
        }
    )
    gene_detected = np.asarray((values > 0).sum(axis=0)).ravel() if sparse.issparse(values) else (np.nan_to_num(values, nan=0.0) > 0).sum(axis=0)
    gene_qc = pd.DataFrame({"gene": genes, "detected_cells": gene_detected, "detected_fraction": gene_detected / values.shape[0]})
    return {
        "cell_qc": cell_qc.sort_values(["low_quality_candidate", "doublet_proxy", "library_size"], ascending=[False, False, True]),
        "gene_qc": gene_qc.sort_values("detected_cells", ascending=False),
        "summary": {
            "cells": int(values.shape[0]),
            "genes": int(values.shape[1]),
            "negative_values": negative,
            "zero_fraction": float(zero_fraction),
            "mitochondrial_genes_detected": len(mito_indices),
            "low_quality_candidates": int(low_quality.sum()),
            "doublet_candidates": int(doublet_proxy.sum()),
            "sparse_input": bool(sparse.issparse(values)),
        },
        "scientific_boundary": BOUNDARY + " QC thresholds are transparent defaults and require protocol-specific review.",
    }


def spatial_omics_qc(
    data: pd.DataFrame,
    *,
    x_col: str = "x",
    y_col: str = "y",
    value_col: str = "expression",
    region_col: str | None = "region",
    neighbour_count: int = 6,
) -> dict[str, Any]:
    frame = _normalise(data)
    keys = [x_col, y_col, value_col]
    keys = [re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_") for key in keys]
    x_col, y_col, value_col = keys
    missing = [key for key in keys if key not in frame]
    if missing:
        raise ValueError("Spatial table missing: " + ", ".join(missing))
    frame[x_col] = _numeric(frame[x_col])
    frame[y_col] = _numeric(frame[y_col])
    frame[value_col] = _numeric(frame[value_col])
    frame = frame.dropna(subset=keys)
    if len(frame) < 8:
        raise ValueError("At least eight spatial observations are required.")
    coords = frame[[x_col, y_col]].to_numpy(float)
    distances = np.sqrt(((coords[:, None, :] - coords[None, :, :]) ** 2).sum(axis=2))
    np.fill_diagonal(distances, np.inf)
    k = max(1, min(int(neighbour_count), len(frame) - 1))
    neighbours = np.argpartition(distances, kth=k - 1, axis=1)[:, :k]
    values = frame[value_col].to_numpy(float)
    centred = values - values.mean()
    numerator = sum(centred[i] * centred[j] for i in range(len(frame)) for j in neighbours[i])
    denominator = float(np.sum(centred**2))
    weights = len(frame) * k
    moran_i = float(len(frame) / weights * numerator / denominator) if denominator > 0 else np.nan
    local = []
    for i in range(len(frame)):
        neighbour_mean = float(np.mean(values[neighbours[i]]))
        local.append({"index": i, "x": coords[i, 0], "y": coords[i, 1], "value": values[i], "neighbour_mean": neighbour_mean, "local_difference": values[i] - neighbour_mean})
    region_key = re.sub(r"[^a-z0-9]+", "_", str(region_col or "").lower()).strip("_") or None
    region_summary = frame.groupby(region_key, as_index=False)[value_col].agg(["mean", "std", "count"]).reset_index() if region_key and region_key in frame else pd.DataFrame()
    return {
        "local_spatial_qc": pd.DataFrame(local),
        "region_summary": region_summary,
        "summary": {"observations": len(frame), "moran_i_proxy": moran_i, "neighbours": k, "coordinate_duplicates": int(frame.duplicated([x_col, y_col]).sum())},
        "scientific_boundary": BOUNDARY + " Spatial statistics depend on coordinate system and neighbourhood definition.",
    }


def multiomics_batch_qc(data: pd.DataFrame, *, batch_col: str | None = "batch", group_col: str | None = "group") -> dict[str, Any]:
    frame = _normalise(data)
    batch_key = re.sub(r"[^a-z0-9]+", "_", str(batch_col or "").lower()).strip("_") or None
    group_key = re.sub(r"[^a-z0-9]+", "_", str(group_col or "").lower()).strip("_") or None
    excluded = {key for key in (batch_key, group_key, "sample_id", "subject_id") if key}
    features = [column for column in frame.columns if column not in excluded and _numeric(frame[column]).notna().sum() >= max(8, len(frame) // 2)]
    if len(features) < 2:
        raise ValueError("Multi-omics QC requires at least two numeric features.")
    X = frame[features].apply(_numeric)
    imputed = SimpleImputer(strategy="median").fit_transform(X)
    scaled = StandardScaler().fit_transform(imputed)
    pca = PCA(n_components=min(5, scaled.shape[1], len(frame)-1), random_state=208)
    coords = pca.fit_transform(scaled)
    coordinate_frame = pd.DataFrame(coords, columns=[f"PC{i+1}" for i in range(coords.shape[1])])
    if batch_key and batch_key in frame:
        coordinate_frame["batch"] = frame[batch_key].astype(str).to_numpy()
    if group_key and group_key in frame:
        coordinate_frame["group"] = frame[group_key].astype(str).to_numpy()
    batch_effect = np.nan
    if batch_key and batch_key in frame and frame[batch_key].nunique() > 1:
        grand = coords.mean(axis=0)
        between = 0.0
        total = float(np.sum((coords - grand) ** 2))
        for _, indices in frame.groupby(batch_key).groups.items():
            subset = coords[list(indices)]
            between += len(subset) * float(np.sum((subset.mean(axis=0) - grand) ** 2))
        batch_effect = between / total if total > 0 else 0.0
    feature_qc = pd.DataFrame({"feature": features, "missing_fraction": X.isna().mean().values, "variance": X.var(ddof=1).values})
    return {
        "pca_coordinates": coordinate_frame,
        "feature_qc": feature_qc.sort_values(["missing_fraction", "variance"], ascending=[False, True]),
        "summary": {"samples": len(frame), "features": len(features), "batch_variance_fraction_proxy": float(batch_effect) if math.isfinite(batch_effect) else None, "explained_variance": pca.explained_variance_ratio_.tolist()},
        "scientific_boundary": BOUNDARY + " Batch-effect estimates are exploratory and do not replace platform-specific normalization.",
    }


def microbiome_contamination_qc(
    abundance: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    sample_col: str = "sample_id",
    control_col: str = "is_negative_control",
    prevalence_threshold: float = 0.5,
) -> dict[str, Any]:
    matrix = abundance.copy()
    if matrix.empty:
        raise ValueError("Abundance matrix is empty.")
    if sample_col in matrix.columns:
        matrix = matrix.set_index(sample_col)
    matrix = matrix.apply(pd.to_numeric, errors="coerce").fillna(0.0)
    meta = _normalise(metadata)
    sample_key = re.sub(r"[^a-z0-9]+", "_", sample_col.lower()).strip("_")
    control_key = re.sub(r"[^a-z0-9]+", "_", control_col.lower()).strip("_")
    if sample_key not in meta or control_key not in meta:
        raise ValueError("Metadata requires sample ID and negative-control columns.")
    meta = meta.set_index(sample_key).reindex(matrix.index.astype(str))
    controls = meta[control_key].fillna(False).astype(str).str.lower().isin({"true", "1", "yes", "control", "negative"})
    if controls.sum() < 1:
        raise ValueError("At least one negative control is required.")
    present = matrix > 0
    control_prevalence = present.loc[controls.values].mean(axis=0)
    sample_prevalence = present.loc[~controls.values].mean(axis=0) if (~controls).sum() else pd.Series(0.0, index=matrix.columns)
    candidate = (control_prevalence >= prevalence_threshold) & (control_prevalence >= sample_prevalence)
    taxa = pd.DataFrame({"feature": matrix.columns.astype(str), "control_prevalence": control_prevalence.values, "sample_prevalence": sample_prevalence.values, "contamination_candidate": candidate.values})
    sample_burden = matrix.loc[:, candidate].sum(axis=1) / matrix.sum(axis=1).replace(0, np.nan) if candidate.any() else pd.Series(0.0, index=matrix.index)
    sample_qc = pd.DataFrame({"sample_id": matrix.index.astype(str), "negative_control": controls.values, "candidate_contaminant_fraction": sample_burden.values})
    return {"feature_qc": taxa.sort_values(["contamination_candidate", "control_prevalence"], ascending=False), "sample_qc": sample_qc, "summary": {"samples": len(matrix), "negative_controls": int(controls.sum()), "features": matrix.shape[1], "candidate_contaminants": int(candidate.sum())}, "scientific_boundary": BOUNDARY + " Contamination calls require protocol-aware review and orthogonal evidence."}


def external_tool_readiness(tools: Sequence[str] | None = None, *, timeout_seconds: float = 4.0) -> pd.DataFrame:
    tools = tuple(tools or ("samtools", "bcftools", "plink2", "mafft", "iqtree2", "hmmscan", "kraken2", "fastqc", "multiqc", "fastp", "vep", "snpEff", "vg"))
    rows = []
    for tool in tools:
        executable = shutil.which(tool)
        version = None
        error = None
        if executable:
            candidates = ([executable, "--version"], [executable, "-version"], [executable, "version"])
            for command in candidates:
                try:
                    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
                    text = (completed.stdout or completed.stderr).strip().splitlines()
                    if text:
                        version = text[0][:240]
                        break
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
        rows.append({"tool": tool, "available": bool(executable), "path": executable, "version": version, "state": "ready" if executable else "optional service unavailable", "error": error})
    return pd.DataFrame(rows)


def build_reproducibility_manifest(
    *,
    inputs: Sequence[str | Path] = (),
    parameters: Mapping[str, Any] | None = None,
    references: Sequence[Mapping[str, Any]] = (),
    tools: Sequence[str] | None = None,
) -> dict[str, Any]:
    input_rows = []
    for item in inputs:
        path = Path(item).expanduser().resolve()
        if not path.is_file():
            input_rows.append({"path": str(path), "exists": False})
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
        input_rows.append({"path": str(path), "exists": True, "size_bytes": path.stat().st_size, "sha256": digest.hexdigest()})
    tool_table = external_tool_readiness(tools)
    return {
        "schema": "biointel.reproducibility.v208",
        "inputs": input_rows,
        "parameters": dict(parameters or {}),
        "references": [dict(record) for record in references],
        "tool_readiness": tool_table.to_dict(orient="records"),
        "format_capabilities": format_support_table().to_dict(orient="records"),
        "scientific_boundary": BOUNDARY,
    }


BIOINFORMATICS_V208_FEATURES: tuple[tuple[str, str, str], ...] = (
    ("format_readiness", "Native Format & Adapter Readiness", "Explicit native, optional-adapter and external-tool status for biomedical formats."),
    ("genomic_cohort_qc", "Genomic Cohort & Reference QC", "Build consistency, contig style, duplicates, relatedness and batch confounding."),
    ("single_cell_qc", "Large Sparse Single-Cell QC", "Library size, detected genes, mitochondrial burden, doublet and low-quality proxies."),
    ("spatial_qc", "Spatial Omics Neighbourhood QC", "Coordinate duplicates, neighbourhood statistics and Moran's-I proxy."),
    ("multiomics_qc", "Multi-Omics Batch & Missingness QC", "PCA, feature missingness and batch variance proxies."),
    ("microbiome_controls", "Microbiome Negative-Control Review", "Control prevalence and contamination-candidate review."),
    ("tool_readiness", "Specialist Tool Readiness", "Local executable discovery, versions and calm optional-unavailable states."),
    ("reproducibility", "Reproducibility Manifest Builder", "Input hashes, parameters, references, tools and format capabilities."),
)
