from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from scipy import ndimage, signal, stats
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    adjusted_rand_score,
    brier_score_loss,
    roc_auc_score,
    silhouette_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict, permutation_test_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

BOUNDARY = (
    "Research-software output only. It is not a diagnosis, treatment recommendation, "
    "medical-device result, clinical classification or regulatory validation."
)


def _normalise_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Input must be a pandas DataFrame.")
    if frame.empty:
        raise ValueError("Input table is empty.")
    output = frame.copy()
    output.columns = [re.sub(r"[^a-z0-9]+", "_", str(column).strip().lower()).strip("_") for column in output.columns]
    return output


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _require(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(missing))


def eeg_meg_research_pipeline(
    data: pd.DataFrame,
    *,
    sampling_rate: float,
    time_col: str | None = None,
    reference: str = "average",
    bandpass: tuple[float, float] = (1.0, 45.0),
    notch_hz: float | None = 50.0,
    epoch_seconds: float = 2.0,
) -> dict[str, Any]:
    frame = _normalise_columns(data)
    if sampling_rate <= 1:
        raise ValueError("Sampling rate must be greater than 1 Hz.")
    if epoch_seconds <= 0:
        raise ValueError("Epoch duration must be positive.")
    time_key = re.sub(r"[^a-z0-9]+", "_", str(time_col or "").lower()).strip("_") or None
    numeric_columns = [column for column in frame.columns if column != time_key and pd.api.types.is_numeric_dtype(frame[column])]
    if len(numeric_columns) < 1:
        numeric_columns = [column for column in frame.columns if column != time_key and _numeric(frame[column]).notna().sum() >= max(10, len(frame) // 2)]
    if not numeric_columns:
        raise ValueError("No numeric signal channels were found.")
    if len(frame) < max(32, int(sampling_rate * 2)):
        raise ValueError("Signal is too short; provide at least two seconds of valid data.")
    matrix = frame[numeric_columns].apply(_numeric).interpolate(limit_direction="both").to_numpy(dtype=float)
    matrix = signal.detrend(matrix, axis=0, type="linear")
    channel_sd = np.nanstd(matrix, axis=0)
    median_sd = float(np.nanmedian(channel_sd))
    mad_sd = float(np.nanmedian(np.abs(channel_sd - median_sd))) or 1e-12
    flat = channel_sd < max(1e-10, median_sd * 0.01)
    noisy = np.abs(channel_sd - median_sd) / (1.4826 * mad_sd) > 5.0
    bad = flat | noisy | ~np.isfinite(channel_sd)
    if notch_hz is not None and 0 < notch_hz < sampling_rate / 2:
        b_notch, a_notch = signal.iirnotch(notch_hz, 30.0, sampling_rate)
        matrix = signal.filtfilt(b_notch, a_notch, matrix, axis=0, padlen=min(len(matrix) - 1, 3 * max(len(a_notch), len(b_notch))))
    low, high = bandpass
    high = min(float(high), sampling_rate / 2 - 0.01)
    if not 0 < low < high:
        raise ValueError("Band-pass limits must satisfy 0 < low < high < Nyquist.")
    sos = signal.butter(4, [low, high], btype="bandpass", fs=sampling_rate, output="sos")
    matrix = signal.sosfiltfilt(sos, matrix, axis=0, padlen=min(len(matrix) - 1, 3 * (2 * len(sos) + 1)))
    if reference == "average" and matrix.shape[1] > 1:
        good_indices = np.where(~bad)[0]
        reference_indices = good_indices if len(good_indices) else np.arange(matrix.shape[1])
        matrix = matrix - np.nanmean(matrix[:, reference_indices], axis=1, keepdims=True)
    elif reference not in {"none", "average"}:
        if reference not in numeric_columns:
            raise ValueError(f"Reference channel '{reference}' was not found.")
        ref_index = numeric_columns.index(reference)
        matrix = matrix - matrix[:, [ref_index]]
    nperseg = min(len(matrix), max(64, int(sampling_rate * 4)))
    frequencies, psd = signal.welch(matrix, fs=sampling_rate, axis=0, nperseg=nperseg)
    bands = {
        "delta": (1.0, 4.0),
        "theta": (4.0, 8.0),
        "alpha": (8.0, 13.0),
        "beta": (13.0, 30.0),
        "gamma": (30.0, min(45.0, sampling_rate / 2 - 0.01)),
    }
    band_rows: list[dict[str, Any]] = []
    for channel_index, channel in enumerate(numeric_columns):
        total_mask = (frequencies >= low) & (frequencies <= high)
        total_power = float(np.trapezoid(psd[total_mask, channel_index], frequencies[total_mask])) if total_mask.any() else np.nan
        for band, (band_low, band_high) in bands.items():
            mask = (frequencies >= band_low) & (frequencies < band_high)
            power = float(np.trapezoid(psd[mask, channel_index], frequencies[mask])) if mask.any() else 0.0
            band_rows.append(
                {
                    "channel": channel,
                    "band": band,
                    "absolute_power": power,
                    "relative_power": power / total_power if total_power and math.isfinite(total_power) else np.nan,
                }
            )
    derivative = np.diff(matrix, axis=0, prepend=matrix[[0]])
    channel_scale = np.nanmedian(np.abs(matrix - np.nanmedian(matrix, axis=0)), axis=0) * 1.4826 + 1e-12
    derivative_scale = np.nanmedian(np.abs(derivative - np.nanmedian(derivative, axis=0)), axis=0) * 1.4826 + 1e-12
    amplitude_z = np.nanmax(np.abs(matrix) / channel_scale, axis=1)
    derivative_z = np.nanmax(np.abs(derivative) / derivative_scale, axis=1)
    event_mask = (amplitude_z > 8.0) | (derivative_z > 10.0)
    event_indices = np.where(event_mask)[0]
    events = pd.DataFrame(
        {
            "sample_index": event_indices,
            "time_seconds": event_indices / sampling_rate,
            "max_amplitude_robust_z": amplitude_z[event_indices],
            "max_derivative_robust_z": derivative_z[event_indices],
            "event_type": np.where(amplitude_z[event_indices] > 8.0, "high_amplitude", "high_derivative"),
        }
    )
    epoch_samples = max(1, int(round(epoch_seconds * sampling_rate)))
    epoch_rows = []
    for start in range(0, len(matrix), epoch_samples):
        stop = min(len(matrix), start + epoch_samples)
        if stop - start < epoch_samples // 2:
            continue
        block = matrix[start:stop]
        epoch_rows.append(
            {
                "epoch": len(epoch_rows) + 1,
                "start_seconds": start / sampling_rate,
                "end_seconds": stop / sampling_rate,
                "rms": float(np.sqrt(np.nanmean(block**2))),
                "peak_to_peak": float(np.nanmax(block) - np.nanmin(block)),
                "artifact_fraction": float(event_mask[start:stop].mean()),
            }
        )
    processed_preview = pd.DataFrame(matrix[: min(len(matrix), 5000)], columns=numeric_columns)
    if time_key and time_key in frame:
        processed_preview.insert(0, time_key, frame[time_key].iloc[: len(processed_preview)].to_numpy())
    channel_qc = pd.DataFrame(
        {
            "channel": numeric_columns,
            "standard_deviation_before_filter": channel_sd,
            "flat_channel": flat,
            "variance_outlier": noisy,
            "bad_channel_candidate": bad,
        }
    )
    return {
        "processed_preview": processed_preview,
        "channel_qc": channel_qc,
        "band_power": pd.DataFrame(band_rows),
        "candidate_artifacts": events,
        "epoch_summary": pd.DataFrame(epoch_rows),
        "metrics": {
            "samples": int(len(matrix)),
            "channels": int(matrix.shape[1]),
            "sampling_rate_hz": float(sampling_rate),
            "bad_channel_candidates": int(bad.sum()),
            "candidate_artifact_samples": int(event_mask.sum()),
            "reference": reference,
            "bandpass_hz": [float(low), float(high)],
            "notch_hz": notch_hz,
        },
        "scientific_boundary": BOUNDARY + " Candidate events and bad channels require expert review.",
    }


def neuroimaging_volume_workflow(
    volume: np.ndarray,
    *,
    affine: np.ndarray | None = None,
    voxel_spacing_mm: Sequence[float] | None = None,
    threshold: float | None = None,
    atlas: np.ndarray | None = None,
) -> dict[str, Any]:
    array = np.asarray(volume)
    if array.ndim not in {3, 4}:
        raise ValueError("Neuroimaging volume must be 3D or 4D.")
    if array.ndim == 4:
        temporal_variance = np.nanvar(array.astype(float), axis=3)
        image = np.nanmean(array.astype(float), axis=3)
    else:
        image = array.astype(float)
        temporal_variance = None
    if min(image.shape) < 2:
        raise ValueError("Volume dimensions are too small for analysis.")
    finite = np.isfinite(image)
    if not finite.any():
        raise ValueError("Volume contains no finite intensities.")
    values = image[finite]
    threshold = float(np.nanpercentile(values, 90)) if threshold is None else float(threshold)
    mask = finite & (image >= threshold)
    labels, component_count = ndimage.label(mask)
    component_sizes = np.bincount(labels.ravel())[1:] if component_count else np.array([], dtype=int)
    spacing = tuple(float(value) for value in (voxel_spacing_mm or (1.0, 1.0, 1.0)))
    if len(spacing) != 3 or any(value <= 0 for value in spacing):
        raise ValueError("Voxel spacing must contain three positive values.")
    voxel_volume = float(np.prod(spacing))
    orientation = "unknown"
    determinant = None
    if affine is not None:
        affine_array = np.asarray(affine, dtype=float)
        if affine_array.shape != (4, 4):
            raise ValueError("Affine matrix must be 4×4.")
        determinant = float(np.linalg.det(affine_array[:3, :3]))
        axes = np.argmax(np.abs(affine_array[:3, :3]), axis=0)
        axis_names = np.array(["LR", "AP", "SI"])
        signs = np.sign(affine_array[axes, np.arange(3)])
        orientation = "-".join(f"{axis_names[axis]}{'+' if sign >= 0 else '-'}" for axis, sign in zip(axes, signs))
    mid = tuple(size // 2 for size in image.shape)
    axial = pd.DataFrame(image[:, :, mid[2]])
    coronal = pd.DataFrame(image[:, mid[1], :])
    sagittal = pd.DataFrame(image[mid[0], :, :])
    slice_rows = []
    for axis, size in enumerate(image.shape):
        for index in range(size):
            plane = np.take(image, index, axis=axis)
            slice_rows.append(
                {
                    "axis": axis,
                    "slice_index": index,
                    "mean_intensity": float(np.nanmean(plane)),
                    "standard_deviation": float(np.nanstd(plane)),
                    "threshold_voxels": int(np.sum(plane >= threshold)),
                }
            )
    roi_summary = pd.DataFrame()
    if atlas is not None:
        atlas_array = np.asarray(atlas)
        if atlas_array.shape != image.shape:
            raise ValueError("Atlas shape must match the imaging volume.")
        rows = []
        for roi in sorted(value for value in np.unique(atlas_array) if value != 0):
            roi_mask = atlas_array == roi
            roi_values = image[roi_mask & finite]
            rows.append(
                {
                    "roi": int(roi) if float(roi).is_integer() else float(roi),
                    "voxels": int(roi_mask.sum()),
                    "volume_mm3": float(roi_mask.sum() * voxel_volume),
                    "mean_intensity": float(np.nanmean(roi_values)) if len(roi_values) else np.nan,
                    "threshold_fraction": float(np.mean(image[roi_mask] >= threshold)) if roi_mask.any() else np.nan,
                }
            )
        roi_summary = pd.DataFrame(rows)
    components = pd.DataFrame(
        {
            "component": np.arange(1, len(component_sizes) + 1),
            "voxels": component_sizes,
            "volume_mm3": component_sizes * voxel_volume,
        }
    ).sort_values("voxels", ascending=False) if len(component_sizes) else pd.DataFrame(columns=["component", "voxels", "volume_mm3"])
    metrics = {
        "shape": tuple(int(value) for value in array.shape),
        "finite_fraction": float(finite.mean()),
        "intensity_p01": float(np.nanpercentile(values, 1)),
        "intensity_p50": float(np.nanpercentile(values, 50)),
        "intensity_p99": float(np.nanpercentile(values, 99)),
        "threshold": threshold,
        "threshold_voxels": int(mask.sum()),
        "threshold_volume_mm3": float(mask.sum() * voxel_volume),
        "connected_components": int(component_count),
        "voxel_spacing_mm": spacing,
        "orientation_proxy": orientation,
        "affine_determinant": determinant,
    }
    if temporal_variance is not None:
        metrics["temporal_variance_mean"] = float(np.nanmean(temporal_variance))
        metrics["timepoints"] = int(array.shape[3])
    return {
        "metrics": metrics,
        "slice_summary": pd.DataFrame(slice_rows),
        "components": components,
        "roi_summary": roi_summary,
        "axial_mid_slice": axial,
        "coronal_mid_slice": coronal,
        "sagittal_mid_slice": sagittal,
        "scientific_boundary": BOUNDARY + " Registration, segmentation and atlas labels require qualified preprocessing.",
    }


def connectome_community_analysis(
    matrix: pd.DataFrame | np.ndarray,
    *,
    threshold: float = 0.3,
    labels: Sequence[str] | None = None,
) -> dict[str, Any]:
    values = np.asarray(matrix, dtype=float)
    if values.ndim != 2 or values.shape[0] != values.shape[1]:
        raise ValueError("Connectivity matrix must be square.")
    if values.shape[0] < 3:
        raise ValueError("Connectivity matrix needs at least three nodes.")
    if not 0 <= threshold < 1:
        raise ValueError("Threshold must be between 0 and 1.")
    values = np.nan_to_num((values + values.T) / 2.0, nan=0.0)
    np.fill_diagonal(values, 0.0)
    names = list(labels or (list(matrix.index.astype(str)) if isinstance(matrix, pd.DataFrame) else [f"ROI_{i+1}" for i in range(len(values))]))
    adjacency = np.abs(values) >= threshold
    rows, cols = np.where(np.triu(adjacency, 1))
    edges = pd.DataFrame(
        {
            "source": [names[index] for index in rows],
            "target": [names[index] for index in cols],
            "weight": values[rows, cols],
            "absolute_weight": np.abs(values[rows, cols]),
        }
    )
    import igraph as ig

    graph = ig.Graph(n=len(values), edges=list(zip(rows.tolist(), cols.tolist())), directed=False)
    graph.vs["name"] = names
    if len(edges):
        graph.es["weight"] = edges["absolute_weight"].tolist()
        communities = graph.community_multilevel(weights=graph.es["weight"])
        membership = communities.membership
    else:
        membership = list(range(len(values)))
    degree = graph.degree()
    strength = graph.strength(weights=graph.es["weight"] if len(edges) else None)
    betweenness = graph.betweenness(weights=None)
    global_efficiency = 0.0
    distances = graph.distances()
    inverse = []
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            distance = distances[i][j]
            if math.isfinite(distance) and distance > 0:
                inverse.append(1.0 / distance)
    if inverse:
        global_efficiency = float(np.mean(inverse))
    vulnerability = []
    for node in range(len(values)):
        reduced = graph.copy()
        reduced.delete_vertices(node)
        reduced_distances = reduced.distances()
        inv = []
        for i in range(len(reduced_distances)):
            for j in range(i + 1, len(reduced_distances)):
                distance = reduced_distances[i][j]
                if math.isfinite(distance) and distance > 0:
                    inv.append(1.0 / distance)
        reduced_efficiency = float(np.mean(inv)) if inv else 0.0
        vulnerability.append(global_efficiency - reduced_efficiency)
    nodes = pd.DataFrame(
        {
            "node": names,
            "community": membership,
            "degree": degree,
            "strength": strength,
            "betweenness": betweenness,
            "efficiency_loss_if_removed": vulnerability,
        }
    ).sort_values(["efficiency_loss_if_removed", "strength"], ascending=False)
    return {
        "nodes": nodes.reset_index(drop=True),
        "edges": edges,
        "metrics": {
            "nodes": len(values),
            "edges": len(edges),
            "density": float(graph.density()),
            "communities": int(len(set(membership))),
            "global_efficiency_proxy": global_efficiency,
            "threshold": threshold,
        },
        "scientific_boundary": BOUNDARY + " Network results depend on parcellation and preprocessing choices.",
    }


def normalize_neuro_variants(
    data: pd.DataFrame,
    *,
    hpo_terms: Sequence[str] = (),
    genome_build: str | None = None,
) -> dict[str, Any]:
    frame = _normalise_columns(data)
    aliases = {
        "chrom": ("chrom", "chr", "chromosome"),
        "pos": ("pos", "position", "start"),
        "ref": ("ref", "reference"),
        "alt": ("alt", "alternate", "allele"),
    }
    detected: dict[str, str] = {}
    for key, options in aliases.items():
        detected[key] = next((option for option in options if option in frame.columns), "")
    if not all(detected.values()):
        raise ValueError("Variant table requires chromosome, position, reference and alternate columns.")
    rows = []
    for record in frame.to_dict(orient="records"):
        alternatives = str(record[detected["alt"]]).split(",")
        for alt in alternatives:
            item = dict(record)
            item["chrom"] = re.sub(r"^chr", "", str(record[detected["chrom"]]), flags=re.I).upper().replace("M", "MT")
            item["pos"] = pd.to_numeric(pd.Series([record[detected["pos"]]]), errors="coerce").iloc[0]
            item["ref"] = str(record[detected["ref"]]).upper().strip()
            item["alt"] = alt.upper().strip()
            rows.append(item)
    normalised = pd.DataFrame(rows)
    normalised = normalised.dropna(subset=["pos"]).copy()
    normalised["pos"] = normalised["pos"].astype(int)
    normalised["variant_key"] = normalised["chrom"].astype(str) + ":" + normalised["pos"].astype(str) + ":" + normalised["ref"] + ">" + normalised["alt"]
    build_column = next((column for column in ("genome_build", "build", "assembly") if column in normalised.columns), None)
    if genome_build:
        build = str(genome_build)
    elif build_column and normalised[build_column].notna().any():
        build = str(normalised[build_column].dropna().mode().iloc[0])
    else:
        build = "unknown"
    consequence_col = next((column for column in ("consequence", "effect", "annotation") if column in normalised.columns), None)
    clinvar_col = next((column for column in ("clinvar", "clinical_significance") if column in normalised.columns), None)
    af_col = next((column for column in ("gnomad_af", "af", "allele_frequency") if column in normalised.columns), None)
    phenotype_col = next((column for column in ("hpo", "phenotype", "phenotypes") if column in normalised.columns), None)
    inheritance_col = next((column for column in ("inheritance", "inheritance_model") if column in normalised.columns), None)
    score = np.zeros(len(normalised), dtype=float)
    reasons: list[list[str]] = [[] for _ in range(len(normalised))]
    if consequence_col:
        high_terms = ("stop_gained", "frameshift", "splice_acceptor", "splice_donor", "start_lost")
        moderate_terms = ("missense", "inframe", "protein_altering")
        for i, value in enumerate(normalised[consequence_col].fillna("").astype(str).str.lower()):
            if any(term in value for term in high_terms):
                score[i] += 3.0
                reasons[i].append("high-impact consequence")
            elif any(term in value for term in moderate_terms):
                score[i] += 1.5
                reasons[i].append("protein-altering consequence")
    if clinvar_col:
        for i, value in enumerate(normalised[clinvar_col].fillna("").astype(str).str.lower()):
            if "pathogenic" in value and "conflict" not in value:
                score[i] += 3.0
                reasons[i].append("uploaded ClinVar pathogenic label")
            elif "conflict" in value:
                reasons[i].append("conflicting uploaded clinical significance")
    if af_col:
        af = _numeric(normalised[af_col])
        rare = af.fillna(0) < 0.001
        score += rare.astype(float) * 1.5
        for i in np.where(rare.to_numpy())[0]:
            reasons[i].append("rare in uploaded population-frequency field")
        normalised["population_af_numeric"] = af
    terms = [str(term).lower().strip() for term in hpo_terms if str(term).strip()]
    if terms and phenotype_col:
        matches = normalised[phenotype_col].fillna("").astype(str).str.lower().apply(lambda text: sum(term in text for term in terms))
        score += np.minimum(matches.to_numpy(dtype=float), 3.0)
        for i in np.where(matches.to_numpy() > 0)[0]:
            reasons[i].append("phenotype/HPO text match")
    if inheritance_col:
        inherited = normalised[inheritance_col].fillna("").astype(str).str.lower()
        supported = inherited.str.contains("de novo|compound|recessive|dominant|x-linked", regex=True)
        score += supported.astype(float)
        for i in np.where(supported.to_numpy())[0]:
            reasons[i].append("uploaded inheritance context")
    normalised["research_priority_score"] = np.round(score, 3)
    normalised["priority_reasons"] = ["; ".join(items) if items else "insufficient uploaded evidence" for items in reasons]
    normalised["research_tier"] = pd.cut(
        normalised["research_priority_score"],
        bins=[-np.inf, 1.5, 4.0, np.inf],
        labels=["review", "moderate", "higher"],
    ).astype(str)
    duplicate_count = int(normalised.duplicated("variant_key").sum())
    return {
        "variants": normalised.sort_values(["research_priority_score", "variant_key"], ascending=[False, True]).reset_index(drop=True),
        "summary": {
            "input_rows": int(len(frame)),
            "normalised_alleles": int(len(normalised)),
            "multiallelic_expansion": int(len(normalised) - len(frame)),
            "duplicate_variant_keys": duplicate_count,
            "genome_build": build,
            "genome_build_resolved": build.lower() not in {"unknown", "", "none", "nan"},
        },
        "scientific_boundary": BOUNDARY + " ACMG/AMP classification and clinical sign-out are not performed.",
    }


def expression_atlas_analysis(
    data: pd.DataFrame,
    *,
    gene_col: str = "gene",
    region_col: str = "region",
    cell_col: str = "cell_type",
    value_col: str = "expression",
    condition_col: str | None = "condition",
) -> dict[str, Any]:
    frame = _normalise_columns(data)
    keys = [gene_col, region_col, cell_col, value_col]
    keys = [re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_") for key in keys]
    gene_col, region_col, cell_col, value_col = keys
    _require(frame, keys)
    condition_key = re.sub(r"[^a-z0-9]+", "_", str(condition_col or "").lower()).strip("_") or None
    frame[value_col] = _numeric(frame[value_col])
    frame = frame.dropna(subset=[gene_col, region_col, cell_col, value_col])
    if frame.empty:
        raise ValueError("No valid expression rows remain after numeric conversion.")
    grouped = frame.groupby([gene_col, region_col, cell_col], as_index=False)[value_col].mean()
    gene_total = grouped.groupby(gene_col)[value_col].transform("sum").replace(0, np.nan)
    grouped["fraction_of_gene_expression"] = grouped[value_col] / gene_total
    grouped["specificity_score"] = grouped.groupby(gene_col)[value_col].transform(lambda values: float(values.max()) / (float(values.mean()) + 1e-12))
    top_context = grouped.sort_values(value_col, ascending=False).groupby(gene_col, as_index=False).first()
    comparison = pd.DataFrame()
    if condition_key and condition_key in frame.columns and frame[condition_key].nunique(dropna=True) >= 2:
        condition_summary = frame.groupby([gene_col, condition_key], as_index=False)[value_col].mean()
        groups = condition_summary[condition_key].astype(str).drop_duplicates().tolist()[:2]
        pivot = condition_summary[condition_summary[condition_key].astype(str).isin(groups)].pivot(index=gene_col, columns=condition_key, values=value_col)
        if len(groups) == 2 and all(group in pivot.columns for group in groups):
            comparison = pivot.reset_index()
            comparison["log2_fold_change_proxy"] = np.log2((comparison[groups[1]] + 1e-9) / (comparison[groups[0]] + 1e-9))
    provenance_columns = [column for column in ("dataset", "dataset_version", "release", "license", "source") if column in frame.columns]
    provenance = frame[provenance_columns].drop_duplicates().reset_index(drop=True) if provenance_columns else pd.DataFrame(
        [{"state": "missing", "message": "Dataset release, licence and source metadata were not supplied."}]
    )
    return {
        "expression_profile": grouped.sort_values([gene_col, value_col], ascending=[True, False]).reset_index(drop=True),
        "top_context": top_context,
        "condition_comparison": comparison,
        "provenance": provenance,
        "summary": {
            "genes": int(frame[gene_col].nunique()),
            "regions": int(frame[region_col].nunique()),
            "cell_types": int(frame[cell_col].nunique()),
            "conditions": int(frame[condition_key].nunique()) if condition_key and condition_key in frame else 0,
            "provenance_fields": provenance_columns,
        },
        "scientific_boundary": BOUNDARY + " Atlas values are only as current and licensed as the supplied dataset.",
    }


def neuro_omics_biomarker_validation(
    data: pd.DataFrame,
    *,
    group_col: str = "group",
    id_col: str | None = "sample_id",
    covariates: Sequence[str] = (),
    folds: int = 5,
    permutations: int = 50,
    seed: int = 208,
) -> dict[str, Any]:
    frame = _normalise_columns(data)
    group_key = re.sub(r"[^a-z0-9]+", "_", group_col.lower()).strip("_")
    _require(frame, (group_key,))
    labels_raw = frame[group_key].astype(str)
    groups = labels_raw.dropna().unique().tolist()
    if len(groups) != 2:
        raise ValueError("Biomarker validation requires exactly two groups.")
    y = (labels_raw == groups[-1]).astype(int).to_numpy()
    covariate_keys = {re.sub(r"[^a-z0-9]+", "_", column.lower()).strip("_") for column in covariates}
    excluded = {group_key, re.sub(r"[^a-z0-9]+", "_", str(id_col or "").lower()).strip("_")} | covariate_keys
    features = [column for column in frame.columns if column not in excluded and _numeric(frame[column]).notna().sum() >= max(8, len(frame) // 2)]
    if len(features) < 2:
        raise ValueError("At least two numeric biomarker features are required.")
    X = frame[features].apply(_numeric)
    missingness = X.isna().mean()
    effect_rows = []
    for column in features:
        left = X.loc[y == 0, column].dropna()
        right = X.loc[y == 1, column].dropna()
        pooled = math.sqrt(max(0.0, ((len(left)-1)*left.var(ddof=1) + (len(right)-1)*right.var(ddof=1)) / max(len(left)+len(right)-2, 1))) if len(left) > 1 and len(right) > 1 else np.nan
        effect = float((right.mean() - left.mean()) / pooled) if pooled and math.isfinite(pooled) else np.nan
        values = X[column].fillna(X[column].median()).to_numpy(dtype=float)
        auc = float(roc_auc_score(y, values))
        auc = max(auc, 1.0 - auc)
        effect_rows.append({"feature": column, "cohens_d": effect, "univariate_auc": auc, "missing_fraction": float(missingness[column])})
    ranking = pd.DataFrame(effect_rows)
    ranking["priority"] = ranking["univariate_auc"] * (1 - ranking["missing_fraction"]) * ranking["cohens_d"].abs().fillna(0)
    ranking = ranking.sort_values(["priority", "feature"], ascending=[False, True]).reset_index(drop=True)
    selected = ranking.head(min(20, max(2, int(math.sqrt(len(features)) * 2))))["feature"].tolist()
    X_selected = X[selected]
    min_class = int(np.bincount(y).min())
    n_splits = max(2, min(int(folds), min_class))
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    model = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", LogisticRegression(max_iter=3000, class_weight="balanced", random_state=seed)),
        ]
    )
    probabilities = cross_val_predict(model, X_selected, y, cv=cv, method="predict_proba")[:, 1]
    auc = float(roc_auc_score(y, probabilities))
    brier = float(brier_score_loss(y, probabilities))
    permutation_score, permutation_scores, permutation_p = permutation_test_score(
        model,
        X_selected,
        y,
        scoring="roc_auc",
        cv=cv,
        n_permutations=max(10, min(int(permutations), 500)),
        random_state=seed,
        n_jobs=1,
    )
    calibration = pd.DataFrame({"observed": y, "probability": probabilities})
    calibration["bin"] = pd.qcut(calibration["probability"], q=min(10, len(calibration)), duplicates="drop")
    calibration_table = calibration.groupby("bin", observed=True).agg(
        mean_probability=("probability", "mean"),
        observed_fraction=("observed", "mean"),
        samples=("observed", "size"),
    ).reset_index(drop=True)
    sample_ids = frame.get(re.sub(r"[^a-z0-9]+", "_", str(id_col or "").lower()).strip("_"), pd.Series([f"sample_{i+1}" for i in range(len(frame))]))
    predictions = pd.DataFrame({"sample_id": sample_ids.astype(str), "group": labels_raw, "cross_validated_probability": probabilities})
    return {
        "feature_ranking": ranking,
        "selected_features": pd.DataFrame({"feature": selected}),
        "cross_validated_predictions": predictions,
        "calibration": calibration_table,
        "metrics": {
            "samples": len(frame),
            "features_considered": len(features),
            "selected_features": len(selected),
            "folds": n_splits,
            "cross_validated_auc": auc,
            "brier_score": brier,
            "permutation_auc": float(permutation_score),
            "permutation_pvalue": float(permutation_p),
            "permutation_null_mean": float(np.mean(permutation_scores)),
            "positive_group": groups[-1],
        },
        "scientific_boundary": BOUNDARY + " Cross-validation is internal and does not replace an independent cohort.",
    }


def precision_neurology_consensus(
    data: pd.DataFrame,
    *,
    id_col: str | None = "subject_id",
    cluster_range: Sequence[int] = (2, 3, 4, 5),
    repeats: int = 20,
    seed: int = 208,
) -> dict[str, Any]:
    frame = _normalise_columns(data)
    id_key = re.sub(r"[^a-z0-9]+", "_", str(id_col or "").lower()).strip("_")
    feature_columns = [column for column in frame.columns if column != id_key and _numeric(frame[column]).notna().sum() >= max(8, len(frame) // 2)]
    if len(feature_columns) < 2:
        raise ValueError("Consensus stratification requires at least two numeric features.")
    X = frame[feature_columns].apply(_numeric)
    pipeline = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())])
    Z = pipeline.fit_transform(X)
    valid_clusters = [int(k) for k in cluster_range if 2 <= int(k) < len(frame)]
    if not valid_clusters:
        raise ValueError("Cluster range is incompatible with the cohort size.")
    rows = []
    all_labels: dict[int, list[np.ndarray]] = {}
    # Limiting native BLAS/OpenMP pools prevents severe oversubscription on
    # Windows workstations and shared compute nodes while keeping results deterministic.
    with threadpool_limits(limits=1):
        for k in valid_clusters:
            runs = []
            silhouettes = []
            for run in range(max(5, min(int(repeats), 100))):
                labels = KMeans(n_clusters=k, n_init=10, random_state=seed + run).fit_predict(Z)
                runs.append(labels)
                silhouettes.append(float(silhouette_score(Z, labels)))
            pairwise = [adjusted_rand_score(runs[i], runs[j]) for i in range(len(runs)) for j in range(i + 1, len(runs))]
            rows.append(
                {
                    "clusters": k,
                    "mean_silhouette": float(np.mean(silhouettes)),
                    "silhouette_sd": float(np.std(silhouettes)),
                    "mean_pairwise_ari": float(np.mean(pairwise)) if pairwise else 1.0,
                }
            )
            all_labels[k] = runs
    evaluation = pd.DataFrame(rows)
    evaluation["selection_score"] = evaluation["mean_silhouette"] * 0.6 + evaluation["mean_pairwise_ari"] * 0.4
    best_k = int(evaluation.sort_values(["selection_score", "clusters"], ascending=[False, True]).iloc[0]["clusters"])
    runs = all_labels[best_k]
    agreement = np.zeros((len(frame), len(frame)), dtype=float)
    for labels in runs:
        agreement += labels[:, None] == labels[None, :]
    agreement /= len(runs)
    with threadpool_limits(limits=1):
        final_labels = KMeans(n_clusters=best_k, n_init=50, random_state=seed + 999).fit_predict(Z)
    pca = PCA(n_components=min(3, Z.shape[1], len(frame) - 1), random_state=seed)
    coordinates = pca.fit_transform(Z)
    subjects = frame.get(id_key, pd.Series([f"subject_{i+1}" for i in range(len(frame))])).astype(str)
    assignments = pd.DataFrame({"subject_id": subjects, "cluster": final_labels + 1})
    for index in range(coordinates.shape[1]):
        assignments[f"pc{index+1}"] = coordinates[:, index]
    assignments["mean_within_cluster_consensus"] = [
        float(np.mean(agreement[index, final_labels == final_labels[index]])) for index in range(len(frame))
    ]
    loadings = pd.DataFrame(pca.components_.T, index=feature_columns, columns=[f"pc{i+1}" for i in range(pca.components_.shape[0])]).reset_index(names="feature")
    return {
        "assignments": assignments,
        "cluster_evaluation": evaluation.sort_values("selection_score", ascending=False).reset_index(drop=True),
        "pca_loadings": loadings,
        "consensus_matrix": pd.DataFrame(agreement, index=subjects, columns=subjects),
        "metrics": {
            "subjects": len(frame),
            "features": len(feature_columns),
            "selected_clusters": best_k,
            "repeats": len(runs),
            "explained_variance": pca.explained_variance_ratio_.tolist(),
        },
        "scientific_boundary": BOUNDARY + " Clusters are exploratory and require external outcome validation.",
    }


def simulate_multicompartment_neuro_pk(
    *,
    dose_mg: float,
    dosing_interval_h: float = 24.0,
    doses: int = 1,
    bioavailability: float = 0.7,
    absorption_rate_h: float = 1.2,
    plasma_clearance_l_h: float = 4.0,
    plasma_volume_l: float = 40.0,
    brain_exchange_h: float = 0.3,
    brain_clearance_h: float = 0.12,
    brain_unbound_fraction: float = 0.1,
    target_kd_nm: float = 20.0,
    kon_nm_h: float = 0.02,
    koff_h: float | None = None,
    simulation_hours: float = 168.0,
    step_minutes: float = 5.0,
) -> dict[str, Any]:
    positive = {
        "dose_mg": dose_mg,
        "dosing_interval_h": dosing_interval_h,
        "doses": doses,
        "absorption_rate_h": absorption_rate_h,
        "plasma_clearance_l_h": plasma_clearance_l_h,
        "plasma_volume_l": plasma_volume_l,
        "brain_exchange_h": brain_exchange_h,
        "brain_clearance_h": brain_clearance_h,
        "target_kd_nm": target_kd_nm,
        "simulation_hours": simulation_hours,
        "step_minutes": step_minutes,
    }
    if any(float(value) <= 0 for value in positive.values()):
        raise ValueError("PK parameters must be positive.")
    if not 0 < bioavailability <= 1 or not 0 < brain_unbound_fraction <= 1:
        raise ValueError("Bioavailability and unbound fraction must be between 0 and 1.")
    dt = step_minutes / 60.0
    times = np.arange(0, simulation_hours + dt, dt)
    gut = plasma = brain = occupancy = 0.0
    koff = float(koff_h) if koff_h is not None else kon_nm_h * target_kd_nm
    dose_times = {round(index * dosing_interval_h / dt) for index in range(int(doses))}
    rows = []
    for index, time in enumerate(times):
        if index in dose_times:
            gut += dose_mg * bioavailability
        absorption = absorption_rate_h * gut
        elimination = plasma_clearance_l_h / plasma_volume_l * plasma
        exchange = brain_exchange_h * (plasma - brain)
        gut = max(0.0, gut + dt * (-absorption))
        plasma = max(0.0, plasma + dt * (absorption / plasma_volume_l - elimination - exchange))
        brain = max(0.0, brain + dt * (exchange - brain_clearance_h * brain))
        free_nm = brain * brain_unbound_fraction * 1000.0
        occupancy = float(np.clip(occupancy + dt * (kon_nm_h * free_nm * (1.0 - occupancy) - koff * occupancy), 0.0, 1.0))
        equilibrium = free_nm / (free_nm + target_kd_nm) if free_nm + target_kd_nm > 0 else 0.0
        rows.append(
            {
                "time_hours": float(time),
                "gut_amount_mg": gut,
                "plasma_concentration_mg_l": plasma,
                "brain_concentration_mg_l": brain,
                "free_brain_proxy_nm": free_nm,
                "kinetic_occupancy": occupancy,
                "equilibrium_occupancy": equilibrium,
            }
        )
    curve = pd.DataFrame(rows)
    return {
        "curve": curve,
        "metrics": {
            "peak_plasma_mg_l": float(curve["plasma_concentration_mg_l"].max()),
            "peak_brain_mg_l": float(curve["brain_concentration_mg_l"].max()),
            "peak_free_brain_proxy_nm": float(curve["free_brain_proxy_nm"].max()),
            "peak_kinetic_occupancy": float(curve["kinetic_occupancy"].max()),
            "occupancy_above_50_percent_hours": float((curve["kinetic_occupancy"] >= 0.5).sum() * dt),
            "doses": int(doses),
            "simulation_hours": simulation_hours,
        },
        "scientific_boundary": BOUNDARY + " Concentration conversion is a transparent proxy and requires compound-specific PK calibration.",
    }


def target_evidence_graph(data: pd.DataFrame) -> dict[str, Any]:
    frame = _normalise_columns(data)
    _require(frame, ("target", "disease"))
    evidence_col = next((column for column in ("evidence_score", "score", "confidence") if column in frame.columns), None)
    source_col = next((column for column in ("source", "publication", "database") if column in frame.columns), None)
    direction_col = next((column for column in ("direction", "effect_direction", "association") if column in frame.columns), None)
    frame["evidence_score_numeric"] = _numeric(frame[evidence_col]).clip(0, 1) if evidence_col else 0.5
    grouped = frame.groupby(["target", "disease"], as_index=False).agg(
        evidence_score=("evidence_score_numeric", "mean"),
        evidence_records=("evidence_score_numeric", "size"),
        sources=(source_col, lambda values: "; ".join(sorted(set(map(str, values.dropna()))))) if source_col else ("evidence_score_numeric", lambda values: "uploaded"),
    )
    if direction_col:
        direction = frame.groupby(["target", "disease"])[direction_col].apply(lambda values: set(str(value).lower() for value in values.dropna()))
        grouped["conflicting_direction"] = [len(direction.get((row.target, row.disease), set())) > 1 for row in grouped.itertuples()]
    else:
        grouped["conflicting_direction"] = False
    targets = pd.DataFrame({"node": sorted(frame["target"].astype(str).unique()), "node_type": "target"})
    diseases = pd.DataFrame({"node": sorted(frame["disease"].astype(str).unique()), "node_type": "disease"})
    nodes = pd.concat([targets, diseases], ignore_index=True)
    edges = grouped.rename(columns={"target": "source", "disease": "target"})
    return {
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "targets": int(frame["target"].nunique()),
            "diseases": int(frame["disease"].nunique()),
            "edges": int(len(edges)),
            "conflicting_edges": int(edges["conflicting_direction"].sum()),
        },
        "scientific_boundary": BOUNDARY + " Evidence scores reflect supplied records and their provenance only.",
    }


_PHASE_MAP = {
    "phase 1": "Phase 1", "phase i": "Phase 1", "1": "Phase 1",
    "phase 2": "Phase 2", "phase ii": "Phase 2", "2": "Phase 2",
    "phase 3": "Phase 3", "phase iii": "Phase 3", "3": "Phase 3",
    "phase 4": "Phase 4", "phase iv": "Phase 4", "4": "Phase 4",
    "early phase 1": "Early Phase 1", "n/a": "Not Applicable",
}
_STATUS_MAP = {
    "recruiting": "Recruiting", "active not recruiting": "Active, not recruiting",
    "active, not recruiting": "Active, not recruiting", "completed": "Completed",
    "terminated": "Terminated", "withdrawn": "Withdrawn", "suspended": "Suspended",
    "not yet recruiting": "Not yet recruiting", "unknown": "Unknown",
}


def normalize_trial_portfolio(data: pd.DataFrame) -> dict[str, Any]:
    frame = _normalise_columns(data)
    trial_col = next((column for column in ("trial_id", "nct_id", "study_id", "id") if column in frame.columns), None)
    if trial_col is None:
        raise ValueError("Trial table requires a trial identifier column.")
    frame["trial_id_normalized"] = frame[trial_col].astype(str).str.strip().str.upper()
    if "phase" in frame:
        raw = frame["phase"].fillna("unknown").astype(str).str.lower().str.strip()
        frame["phase_normalized"] = raw.map(_PHASE_MAP).fillna(frame["phase"].astype(str).str.strip())
    else:
        frame["phase_normalized"] = "Unknown"
    status_col = next((column for column in ("status", "overall_status", "recruitment_status") if column in frame.columns), None)
    if status_col:
        raw_status = frame[status_col].fillna("unknown").astype(str).str.lower().str.strip()
        frame["status_normalized"] = raw_status.map(_STATUS_MAP).fillna(frame[status_col].astype(str).str.strip())
    else:
        frame["status_normalized"] = "Unknown"
    duplicate_mask = frame.duplicated("trial_id_normalized", keep=False)
    frame["duplicate_trial_id"] = duplicate_mask
    endpoint_col = next((column for column in ("primary_endpoint", "endpoint", "outcome") if column in frame.columns), None)
    frame["endpoint_available"] = frame[endpoint_col].notna() & frame[endpoint_col].astype(str).str.strip().ne("") if endpoint_col else False
    last_update_col = next((column for column in ("last_update", "updated_at", "last_refresh") if column in frame.columns), None)
    if last_update_col:
        dates = pd.to_datetime(frame[last_update_col], errors="coerce", utc=True)
        frame["last_update_parsed"] = dates
        stale = dates.notna() & ((pd.Timestamp.now(tz="UTC") - dates).dt.days > 365)
        frame["stale_over_one_year"] = stale
    else:
        frame["stale_over_one_year"] = True
    landscape = frame.groupby(["phase_normalized", "status_normalized"], as_index=False).size().rename(columns={"size": "trials"})
    return {
        "trials": frame.sort_values(["duplicate_trial_id", "trial_id_normalized"], ascending=[False, True]).reset_index(drop=True),
        "landscape": landscape,
        "summary": {
            "rows": len(frame),
            "unique_trials": int(frame["trial_id_normalized"].nunique()),
            "duplicate_rows": int(duplicate_mask.sum()),
            "endpoint_coverage": float(frame["endpoint_available"].mean()),
            "stale_fraction": float(frame["stale_over_one_year"].mean()),
        },
        "scientific_boundary": BOUNDARY + " Completeness and currency depend on the uploaded or approved provider data.",
    }


def neuro_oncology_board(data: pd.DataFrame) -> dict[str, Any]:
    frame = _normalise_columns(data)
    _require(frame, ("sample_id", "marker", "value"))
    frame["value"] = _numeric(frame["value"])
    frame = frame.dropna(subset=["value"])
    if frame.empty:
        raise ValueError("No valid molecular measurements were found.")
    marker_summary = frame.groupby("marker", as_index=False).agg(samples=("sample_id", "nunique"), mean_value=("value", "mean"), sd_value=("value", "std"))
    wide = frame.pivot_table(index="sample_id", columns="marker", values="value", aggfunc="mean")
    z = (wide - wide.mean()) / wide.std(ddof=1).replace(0, np.nan)
    burden = z.abs().mean(axis=1, skipna=True)
    sample_summary = pd.DataFrame({"sample_id": wide.index.astype(str), "multi_marker_deviation": burden}).reset_index(drop=True)
    return {"sample_summary": sample_summary.sort_values("multi_marker_deviation", ascending=False), "marker_summary": marker_summary, "scientific_boundary": BOUNDARY + " Molecular deviation is not a tumour diagnosis or treatment recommendation."}


def epilepsy_diary_analysis(data: pd.DataFrame) -> dict[str, Any]:
    frame = _normalise_columns(data)
    _require(frame, ("date", "event_count"))
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["event_count"] = _numeric(frame["event_count"])
    frame = frame.dropna(subset=["date", "event_count"]).sort_values("date")
    if len(frame) < 7:
        raise ValueError("At least seven daily records are required.")
    frame["rolling_7d_events"] = frame["event_count"].rolling(7, min_periods=1).sum()
    correlations = []
    for candidate in ("sleep_hours", "medication_adherence", "stress_score"):
        if candidate in frame:
            values = _numeric(frame[candidate])
            valid = values.notna() & frame["event_count"].notna()
            coefficient = float(stats.spearmanr(values[valid], frame.loc[valid, "event_count"]).statistic) if valid.sum() >= 4 else np.nan
            correlations.append({"factor": candidate, "spearman_correlation": coefficient, "observations": int(valid.sum())})
    return {"daily_timeline": frame, "factor_correlations": pd.DataFrame(correlations), "summary": {"days": len(frame), "total_events": float(frame["event_count"].sum()), "event_free_days": int((frame["event_count"] == 0).sum())}, "scientific_boundary": BOUNDARY + " Diary correlations do not identify seizure cause or treatment effect."}


def movement_disorder_quantification(data: pd.DataFrame, *, sampling_rate: float = 50.0) -> dict[str, Any]:
    frame = _normalise_columns(data)
    axes = [column for column in ("accel_x", "accel_y", "accel_z") if column in frame]
    if len(axes) < 1:
        raise ValueError("Movement analysis requires accel_x, accel_y or accel_z.")
    matrix = frame[axes].apply(_numeric).interpolate(limit_direction="both").to_numpy(float)
    magnitude = np.linalg.norm(matrix, axis=1)
    frequencies, psd = signal.welch(magnitude, fs=sampling_rate, nperseg=min(len(magnitude), max(32, int(sampling_rate * 4))))
    tremor_mask = (frequencies >= 3) & (frequencies <= 12)
    tremor_power = float(np.trapezoid(psd[tremor_mask], frequencies[tremor_mask])) if tremor_mask.any() else 0.0
    peaks, _ = signal.find_peaks(magnitude, distance=max(1, int(sampling_rate * 0.25)), prominence=np.nanstd(magnitude) * 0.25)
    intervals = np.diff(peaks) / sampling_rate if len(peaks) > 1 else np.array([])
    return {"signal_summary": pd.DataFrame({"metric": ["mean_magnitude", "sd_magnitude", "tremor_band_power", "candidate_steps", "step_interval_cv"], "value": [float(np.mean(magnitude)), float(np.std(magnitude)), tremor_power, len(peaks), float(np.std(intervals)/np.mean(intervals)) if len(intervals) and np.mean(intervals) else np.nan]}), "candidate_steps": pd.DataFrame({"sample_index": peaks, "time_seconds": peaks / sampling_rate, "magnitude": magnitude[peaks]}), "scientific_boundary": BOUNDARY + " Movement features are research measurements, not a Parkinsonian diagnosis."}


def autonomic_hrv_analysis(data: pd.DataFrame) -> dict[str, Any]:
    frame = _normalise_columns(data)
    rr_col = next((column for column in ("rr_ms", "rr_interval_ms", "ibi_ms") if column in frame), None)
    if rr_col is None:
        raise ValueError("HRV analysis requires RR intervals in milliseconds.")
    rr = _numeric(frame[rr_col]).dropna()
    rr = rr[(rr >= 300) & (rr <= 2000)]
    if len(rr) < 20:
        raise ValueError("At least 20 plausible RR intervals are required.")
    diff = np.diff(rr)
    metrics = {
        "beats": int(len(rr)),
        "mean_rr_ms": float(rr.mean()),
        "sdnn_ms": float(rr.std(ddof=1)),
        "rmssd_ms": float(np.sqrt(np.mean(diff**2))),
        "pnn50": float(np.mean(np.abs(diff) > 50)),
        "mean_heart_rate_bpm": float(60000 / rr.mean()),
    }
    posture = pd.DataFrame()
    if "posture" in frame:
        temp = frame.assign(rr_numeric=_numeric(frame[rr_col])).dropna(subset=["rr_numeric"])
        posture = temp.groupby("posture", as_index=False).agg(mean_rr_ms=("rr_numeric", "mean"), sdnn_ms=("rr_numeric", "std"), beats=("rr_numeric", "size"))
    return {"metrics": metrics, "posture_summary": posture, "scientific_boundary": BOUNDARY + " HRV metrics require controlled acquisition and are not an autonomic diagnosis."}


def speech_language_biomarker_analysis(data: pd.DataFrame) -> dict[str, Any]:
    frame = _normalise_columns(data)
    id_col = next((column for column in ("sample_id", "subject_id", "recording_id") if column in frame), None)
    numeric = frame.select_dtypes(include=[np.number]).copy()
    if numeric.shape[1] < 2:
        for column in frame.columns:
            converted = _numeric(frame[column])
            if converted.notna().sum() >= max(5, len(frame)//2):
                numeric[column] = converted
    if numeric.shape[1] < 2:
        raise ValueError("Provide at least two acoustic or language numeric features.")
    z = (numeric - numeric.mean()) / numeric.std(ddof=1).replace(0, np.nan)
    deviation = z.abs().mean(axis=1, skipna=True)
    result = pd.DataFrame({"sample_id": frame[id_col].astype(str) if id_col else [f"sample_{i+1}" for i in range(len(frame))], "feature_deviation": deviation, "available_features": numeric.notna().sum(axis=1)})
    feature_qc = pd.DataFrame({"feature": numeric.columns, "missing_fraction": numeric.isna().mean().values, "mean": numeric.mean().values, "standard_deviation": numeric.std(ddof=1).values})
    return {"sample_summary": result.sort_values("feature_deviation", ascending=False), "feature_qc": feature_qc, "scientific_boundary": BOUNDARY + " Speech/language features do not establish cognitive or neurological impairment."}


def multimodal_neurodegeneration_progression(data: pd.DataFrame) -> dict[str, Any]:
    frame = _normalise_columns(data)
    _require(frame, ("subject_id", "time_months"))
    frame["time_months"] = _numeric(frame["time_months"])
    features = [column for column in frame.columns if column not in {"subject_id", "time_months"} and _numeric(frame[column]).notna().sum() >= 4]
    if len(features) < 2:
        raise ValueError("At least two longitudinal modalities are required.")
    for column in features:
        frame[column] = _numeric(frame[column])
    rows = []
    for subject, group in frame.groupby("subject_id"):
        group = group.sort_values("time_months")
        row: dict[str, Any] = {"subject_id": subject, "visits": len(group)}
        slopes = []
        for feature in features:
            valid = group[["time_months", feature]].dropna()
            slope = float(np.polyfit(valid["time_months"], valid[feature], 1)[0] * 12) if len(valid) >= 2 and valid["time_months"].nunique() > 1 else np.nan
            row[f"{feature}_annual_slope"] = slope
            if math.isfinite(slope):
                slopes.append(abs(slope))
        row["multimodal_change_burden"] = float(np.mean(slopes)) if slopes else np.nan
        rows.append(row)
    return {"subject_progression": pd.DataFrame(rows).sort_values("multimodal_change_burden", ascending=False), "features": pd.DataFrame({"modality_feature": features}), "scientific_boundary": BOUNDARY + " Progression burden is scale-dependent and requires validated modality harmonisation."}


def neuropathology_image_analysis(image: np.ndarray) -> dict[str, Any]:
    array = np.asarray(image)
    if array.ndim == 3:
        gray = np.mean(array[..., :3], axis=2)
    elif array.ndim == 2:
        gray = array.astype(float)
    else:
        raise ValueError("Histology input must be a 2D grayscale or RGB image.")
    gray = gray.astype(float)
    finite = np.isfinite(gray)
    if not finite.any():
        raise ValueError("Image contains no finite pixels.")
    normalized = (gray - np.nanmin(gray)) / (np.nanmax(gray) - np.nanmin(gray) + 1e-12)
    threshold = float(np.nanpercentile(normalized, 65))
    mask = normalized <= threshold
    mask = ndimage.binary_opening(mask, iterations=1)
    labels, count = ndimage.label(mask)
    objects = ndimage.find_objects(labels)
    rows = []
    for index, slices in enumerate(objects, start=1):
        if slices is None:
            continue
        region = labels[slices] == index
        area = int(region.sum())
        if area < 5:
            continue
        rows.append({"object_id": index, "area_pixels": area, "bbox_height": slices[0].stop-slices[0].start, "bbox_width": slices[1].stop-slices[1].start})
    return {"objects": pd.DataFrame(rows), "metrics": {"image_shape": tuple(array.shape), "candidate_objects": len(rows), "candidate_area_fraction": float(mask.mean()), "threshold": threshold}, "scientific_boundary": BOUNDARY + " Candidate objects require stain-specific segmentation validation and pathology review."}


def neurocritical_care_trends(data: pd.DataFrame) -> dict[str, Any]:
    frame = _normalise_columns(data)
    _require(frame, ("timestamp",))
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    numeric = [column for column in frame.columns if column != "timestamp" and _numeric(frame[column]).notna().sum() >= 6]
    if not numeric:
        raise ValueError("No numeric physiological or neurological trend columns were found.")
    frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp")
    rows = []
    alerts = []
    for column in numeric:
        values = _numeric(frame[column]).interpolate(limit_direction="both")
        elapsed = (frame["timestamp"] - frame["timestamp"].iloc[0]).dt.total_seconds() / 3600
        slope = float(np.polyfit(elapsed, values, 1)[0]) if elapsed.nunique() > 1 else 0.0
        robust_scale = float(np.nanmedian(np.abs(values - np.nanmedian(values))) * 1.4826) or 1e-12
        jumps = np.abs(np.diff(values, prepend=values.iloc[0])) / robust_scale
        rows.append({"variable": column, "slope_per_hour": slope, "robust_scale": robust_scale, "candidate_change_points": int((jumps > 5).sum())})
        for index in np.where(jumps > 5)[0]:
            alerts.append({"timestamp": frame["timestamp"].iloc[index], "variable": column, "robust_jump_z": float(jumps[index]), "value": float(values.iloc[index])})
    return {"trend_summary": pd.DataFrame(rows), "candidate_change_points": pd.DataFrame(alerts), "timeline": frame[["timestamp", *numeric]], "scientific_boundary": BOUNDARY + " Trend flags are not bedside alarms and must not drive clinical care."}


NEURO_V208_FEATURES: tuple[tuple[str, str, str], ...] = (
    ("advanced_eeg_meg", "Advanced EEG/MEG Preprocessing & Review", "Filtering, referencing, channel QC, epoch summaries and candidate artifacts."),
    ("advanced_neuroimaging", "Advanced Neuroimaging & Connectome Review", "Volume QC, orthogonal slices, ROI summaries and community analysis."),
    ("advanced_neurogenetics", "Advanced Neurogenetics Evidence Workbench", "Variant normalization, build checks, phenotype context and transparent prioritization."),
    ("advanced_expression_atlas", "Versioned Brain Expression Atlas Workbench", "Region/cell specificity, condition comparison and provenance review."),
    ("advanced_neuro_omics", "Leakage-Aware Neuro-Omics Validation", "Cross-validation, permutation testing, calibration and locked feature ranking."),
    ("advanced_precision_neurology", "Consensus Precision Neurology", "Cluster stability, consensus matrices, PCA and external-validation boundaries."),
    ("advanced_neuro_pk", "Multi-Compartment Neuro-PK & Kinetic Occupancy", "Repeated dosing, brain exchange and time-dependent occupancy."),
    ("advanced_target_evidence", "CNS Target Evidence Graph", "Evidence-weighted target-disease graph with conflict review."),
    ("advanced_trial_intelligence", "Normalized CNS Trial Intelligence", "Trial IDs, phase/status normalization, endpoint coverage and staleness."),
    ("neuro_oncology", "Neuro-Oncology Molecular Research Board", "Multi-marker molecular deviation and sample review."),
    ("epilepsy_diary", "Epilepsy Event & Diary Research Lab", "Daily event trends and transparent factor correlations."),
    ("movement_disorders", "Movement Disorder Quantification Studio", "Tremor-band power, movement variability and candidate steps."),
    ("autonomic_hrv", "Autonomic Neurophysiology & HRV Lab", "Time-domain HRV and posture summaries."),
    ("speech_language", "Speech, Voice & Language Biomarker Studio", "Acoustic/language feature QC and multivariate deviation."),
    ("neurodegeneration_progression", "Multimodal Neurodegeneration Progression Studio", "Longitudinal slopes across imaging, fluid, cognitive and digital markers."),
    ("neuropathology", "Neuropathology & Brain Histology Analytics", "Image QC and candidate object quantification."),
    ("neurocritical_care", "Neurocritical Care Trend Analytics", "Longitudinal trend slopes and candidate change points."),
)
