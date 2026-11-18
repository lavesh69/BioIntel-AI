from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd
from scipy import stats

from .analysis_common import bh_fdr, differential_expression, numeric, require_columns
from .models import PlatformValidationError


def multi_omics(frame: pd.DataFrame, parameters: Mapping[str, Any]) -> dict[str, Any]:
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    require_columns(frame, ("sample_id", "layer", "feature_id", "value"))
    data = frame.copy()
    data["value"] = numeric(data["value"])
    data = data.dropna(subset=["sample_id", "layer", "feature_id", "value"])
    layers = list(dict.fromkeys(data["layer"].astype(str)))
    if len(layers) < 2:
        raise PlatformValidationError("Multi-omics integration requires at least two layers")
    matrices: dict[str, pd.DataFrame] = {}
    sample_sets = []
    for layer in layers:
        matrix = data.loc[data["layer"].astype(str) == layer].pivot_table(
            index="sample_id", columns="feature_id", values="value", aggfunc="mean"
        )
        matrices[layer] = matrix
        sample_sets.append(set(matrix.index.astype(str)))
    common_samples = sorted(set.intersection(*sample_sets))
    if len(common_samples) < 3:
        raise PlatformValidationError("At least three concordant samples are required across layers")
    maximum_features = int(parameters.get("maximum_features_per_layer", 500))
    standardized: dict[str, pd.DataFrame] = {}
    layer_qc = []
    first_components: dict[str, np.ndarray] = {}
    for layer, matrix in matrices.items():
        subset = matrix.loc[common_samples]
        variances = subset.var(axis=0, skipna=True).sort_values(ascending=False)
        selected = list(variances.head(maximum_features).index)
        subset = subset[selected]
        missing_fraction = float(subset.isna().mean().mean())
        subset = subset.fillna(subset.median()).fillna(0.0)
        scaled = StandardScaler().fit_transform(subset)
        standardized[layer] = pd.DataFrame(
            scaled,
            index=common_samples,
            columns=[f"{layer}:{column}" for column in subset.columns],
        )
        components = min(5, len(common_samples) - 1, max(1, len(selected)))
        pca = PCA(n_components=components, random_state=int(parameters.get("seed", 42)))
        scores = pca.fit_transform(scaled)
        first_components[layer] = scores[:, 0]
        layer_qc.append(
            {
                "layer": layer, "samples": len(subset), "features": len(selected),
                "missing_fraction": missing_fraction,
                "variance_explained": pca.explained_variance_ratio_.tolist(),
            }
        )
    integrated = pd.concat(standardized.values(), axis=1)
    n_components = min(
        int(parameters.get("latent_factors", 5)),
        len(common_samples) - 1,
        integrated.shape[1],
    )
    model = PCA(n_components=max(1, n_components), random_state=int(parameters.get("seed", 42)))
    latent = model.fit_transform(integrated)
    latent_rows = []
    for index, sample_id in enumerate(common_samples):
        row = {"sample_id": sample_id}
        row.update({f"factor_{offset + 1}": float(value) for offset, value in enumerate(latent[index])})
        latent_rows.append(row)
    concordance = []
    for left_index, left in enumerate(layers):
        for right in layers[left_index + 1 :]:
            correlation = stats.spearmanr(
                first_components[left], first_components[right], nan_policy="omit"
            ).statistic
            concordance.append(
                {
                    "layer_a": left, "layer_b": right,
                    "first_factor_spearman": float(correlation)
                    if np.isfinite(correlation) else None,
                }
            )
    ablation = []
    full_variance = float(model.explained_variance_ratio_.sum())
    for omitted in layers:
        reduced = pd.concat(
            [value for key, value in standardized.items() if key != omitted], axis=1
        )
        reduced_components = min(max(1, n_components), len(common_samples) - 1, reduced.shape[1])
        reduced_model = PCA(
            n_components=reduced_components, random_state=int(parameters.get("seed", 42))
        ).fit(reduced)
        ablation.append(
            {
                "omitted_layer": omitted,
                "explained_variance": float(reduced_model.explained_variance_ratio_.sum()),
                "delta_from_full": float(
                    reduced_model.explained_variance_ratio_.sum() - full_variance
                ),
            }
        )
    return {
        "sample_concordance": {
            "common_samples": common_samples,
            "layer_sample_counts": {
                layer: len(matrix.index) for layer, matrix in matrices.items()
            },
        },
        "layer_qc": layer_qc,
        "latent_factors": latent_rows,
        "latent_variance_explained": model.explained_variance_ratio_.tolist(),
        "cross_layer_concordance": concordance,
        "layer_ablation": ablation,
        "method": "Feature-wise scaling followed by joint PCA; this is actual latent integration, not side-by-side visualization.",
    }


def single_cell(frame: pd.DataFrame, parameters: Mapping[str, Any]) -> dict[str, Any]:
    from sklearn.decomposition import PCA

    require_columns(frame, ("cell_id", "feature_id", "value"))
    data = frame.copy()
    data["value"] = numeric(data["value"])
    data = data.dropna(subset=["cell_id", "feature_id", "value"])
    data["detected"] = data["value"] > 0
    feature_names = data["feature_id"].astype(str)
    mitochondrial_prefix = str(parameters.get("mitochondrial_prefix", "MT-"))
    data["mitochondrial"] = feature_names.str.upper().str.startswith(
        mitochondrial_prefix.upper()
    )
    qc = data.groupby("cell_id").agg(
        total_counts=("value", "sum"),
        detected_features=("detected", "sum"),
    )
    mito = (
        data.loc[data["mitochondrial"]]
        .groupby("cell_id")["value"]
        .sum()
        .reindex(qc.index, fill_value=0)
    )
    qc["mitochondrial_percent"] = mito / qc["total_counts"].replace(0, np.nan) * 100
    median_features = float(qc["detected_features"].median())
    mad_features = float(
        np.median(np.abs(qc["detected_features"] - median_features))
    )
    median_counts = float(qc["total_counts"].median())
    mad_counts = float(np.median(np.abs(qc["total_counts"] - median_counts)))
    minimum_features = float(
        parameters.get("minimum_features", max(1, median_features - 3 * mad_features))
    )
    maximum_counts = float(
        parameters.get("maximum_counts", median_counts + 4 * mad_counts)
    )
    maximum_mito = float(parameters.get("maximum_mitochondrial_percent", 20))
    qc["low_feature_flag"] = qc["detected_features"] < minimum_features
    qc["high_count_doublet_proxy"] = qc["total_counts"] > maximum_counts
    qc["high_mitochondrial_flag"] = qc["mitochondrial_percent"] > maximum_mito
    qc["qc_status"] = np.where(
        qc[["low_feature_flag", "high_count_doublet_proxy", "high_mitochondrial_flag"]].any(axis=1),
        "Review",
        "Pass",
    )
    maximum_cells = min(int(parameters.get("maximum_cells", 5000)), 5000)
    maximum_features = min(int(parameters.get("maximum_features", 1000)), 2000)
    cells = list(qc.sort_values("total_counts", ascending=False).head(maximum_cells).index)
    variable = (
        data.loc[data["cell_id"].isin(cells)]
        .groupby("feature_id")["value"]
        .var()
        .sort_values(ascending=False)
        .head(maximum_features)
        .index
    )
    matrix = data.loc[
        data["cell_id"].isin(cells) & data["feature_id"].isin(variable)
    ].pivot_table(index="cell_id", columns="feature_id", values="value", fill_value=0)
    matrix = np.log1p(matrix)
    components = min(10, len(matrix) - 1, matrix.shape[1])
    embedding = []
    variance = []
    if components >= 2:
        pca = PCA(n_components=components, random_state=int(parameters.get("seed", 42)))
        scores = pca.fit_transform(matrix)
        variance = pca.explained_variance_ratio_.tolist()
        embedding = [
            {
                "cell_id": str(cell_id),
                **{f"PC{index + 1}": float(value) for index, value in enumerate(scores[row])},
            }
            for row, cell_id in enumerate(matrix.index)
        ]
    return {
        "cell_qc": qc.reset_index().to_dict(orient="records"),
        "adaptive_thresholds": {
            "minimum_features": minimum_features,
            "maximum_counts": maximum_counts,
            "maximum_mitochondrial_percent": maximum_mito,
        },
        "embedding": embedding,
        "variance_explained": variance,
        "scientific_boundary": (
            "High-count cells are doublet proxies only. Cell annotation, atlas mapping, "
            "trajectory, and communication claims require explicit configured adapters."
        ),
    }


def proteomics(frame: pd.DataFrame, parameters: Mapping[str, Any]) -> dict[str, Any]:
    require_columns(frame, ("protein_id", "sample_id", "group", "intensity"))
    data = frame.copy()
    peptide_fdr = float(parameters.get("maximum_peptide_fdr", 0.01))
    protein_fdr = float(parameters.get("maximum_protein_fdr", 0.01))
    if "peptide_q_value" in data:
        data = data.loc[numeric(data["peptide_q_value"]) <= peptide_fdr]
    if "protein_q_value" in data:
        data = data.loc[numeric(data["protein_q_value"]) <= protein_fdr]
    if data.empty:
        raise PlatformValidationError("No protein measurements passed configured FDR")
    missingness = (
        data.assign(missing=numeric(data["intensity"]).isna())
        .groupby("protein_id")["missing"]
        .mean()
        .rename("missing_fraction")
    )
    differential_input = data.rename(
        columns={"protein_id": "feature_id", "intensity": "value"}
    )[["feature_id", "sample_id", "group", "value"]]
    differential = differential_expression(
        differential_input,
        {
            "minimum_replicates": parameters.get("minimum_replicates", 3),
            "pseudocount": parameters.get("pseudocount", 1.0),
            "fdr": parameters.get("fdr", 0.05),
            "minimum_abs_log2fc": parameters.get("minimum_abs_log2fc", 0.5),
        },
    )
    return {
        "identification_qc": {
            "rows_after_fdr": len(data),
            "proteins": int(data["protein_id"].nunique()),
            "maximum_peptide_fdr": peptide_fdr,
            "maximum_protein_fdr": protein_fdr,
        },
        "missingness": missingness.reset_index().to_dict(orient="records"),
        "differential_abundance": differential,
    }


def metabolomics(frame: pd.DataFrame, parameters: Mapping[str, Any]) -> dict[str, Any]:
    require_columns(frame, ("feature_id", "sample_id", "sample_type", "run_order", "intensity"))
    data = frame.copy()
    data["intensity"] = numeric(data["intensity"])
    data["run_order"] = numeric(data["run_order"])
    blank_label = str(parameters.get("blank_label", "blank")).lower()
    qc_label = str(parameters.get("qc_label", "qc")).lower()
    sample_type = data["sample_type"].astype(str).str.lower()
    blank_medians = (
        data.loc[sample_type.eq(blank_label)]
        .groupby("feature_id")["intensity"]
        .median()
    )
    data["blank_median"] = data["feature_id"].map(blank_medians).fillna(0)
    data["blank_corrected_intensity"] = (data["intensity"] - data["blank_median"]).clip(lower=0)
    sample_medians = (
        data.loc[~sample_type.isin({blank_label, qc_label})]
        .groupby("feature_id")["blank_corrected_intensity"]
        .median()
    )
    blank_ratio = blank_medians / sample_medians.replace(0, np.nan)
    maximum_blank_ratio = float(parameters.get("maximum_blank_ratio", 0.2))
    qc_rows = []
    for feature_id, subset in data.loc[sample_type.eq(qc_label)].groupby("feature_id"):
        values = subset["blank_corrected_intensity"].dropna().to_numpy(float)
        cv = float(np.std(values, ddof=1) / np.mean(values)) if len(values) > 1 and np.mean(values) else None
        drift_input = subset[
            ["run_order", "blank_corrected_intensity"]
        ].dropna()
        slope = (
            stats.linregress(drift_input["run_order"], drift_input["blank_corrected_intensity"]).slope
            if len(drift_input) >= 3 else np.nan
        )
        qc_rows.append(
            {
                "feature_id": str(feature_id), "qc_cv": cv,
                "drift_slope": float(slope) if np.isfinite(slope) else None,
                "blank_ratio": float(blank_ratio.get(feature_id))
                if np.isfinite(blank_ratio.get(feature_id, np.nan)) else None,
                "blank_pass": bool(blank_ratio.get(feature_id, np.inf) <= maximum_blank_ratio),
            }
        )
    return {
        "corrected_measurements": data.to_dict(orient="records"),
        "feature_qc": qc_rows,
        "summary": {
            "features": int(data["feature_id"].nunique()),
            "blank_ratio_threshold": maximum_blank_ratio,
            "features_with_qc": len(qc_rows),
        },
        "scientific_boundary": "Feature annotations remain unknown unless a verified MSI-level annotation is supplied.",
    }


def microbiome(frame: pd.DataFrame, parameters: Mapping[str, Any]) -> dict[str, Any]:
    require_columns(frame, ("taxon_id", "sample_id", "group", "count"))
    data = frame.copy()
    data["count"] = numeric(data["count"]).fillna(0)
    negative = data.get(
        "is_negative_control", pd.Series(False, index=data.index)
    ).astype(bool)
    prevalence_negative = (
        data.loc[negative].assign(present=lambda value: value["count"] > 0)
        .groupby("taxon_id")["present"].mean()
    )
    prevalence_sample = (
        data.loc[~negative].assign(present=lambda value: value["count"] > 0)
        .groupby("taxon_id")["present"].mean()
    )
    contamination_ratio = prevalence_negative / prevalence_sample.replace(0, np.nan)
    threshold = float(parameters.get("contamination_prevalence_ratio", 0.5))
    contaminants = set(
        contamination_ratio.loc[contamination_ratio >= threshold].index.astype(str)
    )
    biological = data.loc[~negative & ~data["taxon_id"].astype(str).isin(contaminants)].copy()
    matrix = biological.pivot_table(
        index="sample_id", columns="taxon_id", values="count", fill_value=0, aggfunc="sum"
    )
    pseudocount = float(parameters.get("pseudocount", 0.5))
    log_values = np.log(matrix + pseudocount)
    clr = log_values.sub(log_values.mean(axis=1), axis=0)
    sample_groups = biological.groupby("sample_id")["group"].first().reindex(clr.index)
    groups = list(dict.fromkeys(sample_groups.astype(str)))
    differential_rows = []
    if len(groups) == 2:
        for taxon in clr.columns:
            first = clr.loc[sample_groups.astype(str).eq(groups[0]), taxon]
            second = clr.loc[sample_groups.astype(str).eq(groups[1]), taxon]
            if len(first) >= 2 and len(second) >= 2:
                test = stats.ttest_ind(second, first, equal_var=False)
                differential_rows.append(
                    {
                        "taxon_id": str(taxon),
                        "clr_difference": float(second.mean() - first.mean()),
                        "p_value": float(test.pvalue),
                    }
                )
    differential = pd.DataFrame(differential_rows)
    if not differential.empty:
        differential["fdr"] = bh_fdr(differential["p_value"])
        differential = differential.sort_values("fdr")
    return {
        "negative_control_prevalence": [
            {
                "taxon_id": str(taxon),
                "negative_prevalence": float(prevalence_negative.get(taxon, 0)),
                "sample_prevalence": float(prevalence_sample.get(taxon, 0)),
                "contamination_ratio": float(value) if np.isfinite(value) else None,
                "flagged": str(taxon) in contaminants,
            }
            for taxon, value in contamination_ratio.items()
        ],
        "clr_abundance": clr.reset_index().to_dict(orient="records"),
        "differential_abundance": differential.to_dict(orient="records"),
        "scientific_boundary": "Compositional CLR screening is exploratory; taxonomy and function confidence remain adapter-specific.",
    }


def structural_biology(frame: pd.DataFrame, parameters: Mapping[str, Any]) -> dict[str, Any]:
    require_columns(frame, ("residue_id",))
    data = frame.copy()
    for column in ("plddt", "pae", "disorder_probability", "pocket_score", "domain_coverage"):
        if column in data:
            data[column] = numeric(data[column])
    minimum_plddt = float(parameters.get("minimum_plddt", 70))
    maximum_pae = float(parameters.get("maximum_pae", 10))
    data["confidence_pass"] = (
        data.get("plddt", pd.Series(np.nan, index=data.index)) >= minimum_plddt
    )
    data["pae_pass"] = (
        data.get("pae", pd.Series(np.nan, index=data.index)) <= maximum_pae
    )
    data["disorder_flag"] = (
        data.get("disorder_probability", pd.Series(0.0, index=data.index)) >= 0.5
    )
    data["pocket_supported"] = (
        data.get("pocket_score", pd.Series(0.0, index=data.index))
        >= float(parameters.get("minimum_pocket_score", 0.5))
    )
    return {
        "residue_assessment": data.to_dict(orient="records"),
        "summary": {
            "residues": len(data),
            "high_confidence_fraction": float(data["confidence_pass"].mean()),
            "low_pae_fraction": float(data["pae_pass"].mean()),
            "disordered_fraction": float(data["disorder_flag"].mean()),
            "pocket_supported_residues": int(data["pocket_supported"].sum()),
        },
        "scientific_boundary": (
            "pLDDT/PAE are model confidence signals, not experimental structure validation. "
            "Docking and mutation-impact claims require configured engines and uncertainty review."
        ),
    }
