from __future__ import annotations

from dataclasses import dataclass
from math import erf, sqrt
from typing import Mapping

import numpy as np
import pandas as pd

from biointel.transcriptomics.expression import _fdr_bh, validate_count_matrix


@dataclass(frozen=True)
class DesignAudit:
    samples: int
    parameters: int
    rank: int
    residual_degrees_freedom: int
    full_rank: bool
    groups: dict[str, int]
    batches: dict[str, int]


def _normal_p_value(z: float) -> float:
    return max(0.0, min(1.0, 1.0 - erf(abs(float(z)) / sqrt(2.0))))


def build_design_matrix(
    samples: list[str],
    groups: Mapping[str, str],
    *,
    reference_group: str,
    comparison_group: str,
    batches: Mapping[str, str] | None = None,
    covariates: pd.DataFrame | None = None,
) -> tuple[np.ndarray, list[str], DesignAudit]:
    if reference_group == comparison_group:
        raise ValueError("Reference and comparison groups must differ.")
    selected = [
        sample
        for sample in samples
        if str(groups.get(sample, "")) in {reference_group, comparison_group}
    ]
    if len(selected) < 4:
        raise ValueError("At least four selected samples are required.")
    group_counts = pd.Series([str(groups[sample]) for sample in selected]).value_counts().to_dict()
    if min(group_counts.get(reference_group, 0), group_counts.get(comparison_group, 0)) < 2:
        raise ValueError("Each comparison group requires at least two samples.")
    columns = [
        np.ones(len(selected)),
        np.array([1.0 if str(groups[sample]) == comparison_group else 0.0 for sample in selected]),
    ]
    names = ["intercept", f"group[{comparison_group}_vs_{reference_group}]"]
    batch_counts: dict[str, int] = {}
    if batches:
        labels = [str(batches.get(sample, "")) for sample in selected]
        batch_counts = pd.Series(labels).value_counts().to_dict()
        levels = list(dict.fromkeys(labels))
        for level in levels[1:]:
            columns.append(np.array([1.0 if value == level else 0.0 for value in labels]))
            names.append(f"batch[{level}]")
    if covariates is not None and not covariates.empty:
        if "sample" not in covariates.columns:
            raise ValueError("Covariate table requires a sample column.")
        indexed = covariates.set_index("sample")
        missing = [sample for sample in selected if sample not in indexed.index]
        if missing:
            raise ValueError("Covariates are missing selected samples: " + ", ".join(missing[:8]))
        for column in indexed.columns:
            values = pd.to_numeric(indexed.loc[selected, column], errors="coerce")
            if values.isna().any():
                raise ValueError(f"Covariate {column!r} contains missing/non-numeric values.")
            standard = values.std(ddof=0)
            scaled = (values - values.mean()) / (standard if standard > 0 else 1.0)
            columns.append(scaled.to_numpy(float))
            names.append(f"covariate[{column}]")
    design = np.column_stack(columns)
    rank = int(np.linalg.matrix_rank(design))
    audit = DesignAudit(
        samples=len(selected),
        parameters=design.shape[1],
        rank=rank,
        residual_degrees_freedom=len(selected) - rank,
        full_rank=rank == design.shape[1],
        groups={str(key): int(value) for key, value in group_counts.items()},
        batches={str(key): int(value) for key, value in batch_counts.items()},
    )
    if not audit.full_rank or audit.residual_degrees_freedom < 1:
        raise ValueError(
            "The experimental design is rank-deficient or has no residual degrees of freedom."
        )
    return design, selected, audit


def _fit_nb_gene(
    y: np.ndarray,
    design: np.ndarray,
    offset: np.ndarray,
    *,
    maximum_iterations: int = 50,
) -> tuple[np.ndarray, np.ndarray, float, bool]:
    mean = float(np.mean(y))
    variance = float(np.var(y, ddof=1)) if len(y) > 1 else mean
    dispersion = max((variance - mean) / max(mean * mean, 1e-8), 1e-8)
    beta = np.zeros(design.shape[1], dtype=float)
    beta[0] = np.log(max(mean, 1e-8)) - float(np.mean(offset))
    converged = False
    covariance = np.eye(design.shape[1]) * np.nan
    for _ in range(maximum_iterations):
        eta = np.clip(design @ beta + offset, -20, 20)
        mu = np.exp(eta)
        variance_mu = mu + dispersion * mu * mu
        weights = np.maximum(mu * mu / np.maximum(variance_mu, 1e-12), 1e-8)
        working = eta + (y - mu) / np.maximum(mu, 1e-8) - offset
        xtw = design.T * weights
        information = xtw @ design
        inverse = np.linalg.pinv(information)
        updated = inverse @ xtw @ working
        if not np.all(np.isfinite(updated)) or not np.all(np.isfinite(inverse)):
            break
        covariance = inverse
        if np.max(np.abs(updated - beta)) < 1e-7:
            beta = updated
            converged = True
            break
        beta = updated
    return beta, covariance, dispersion, converged


def negative_binomial_de(
    frame: pd.DataFrame,
    groups: Mapping[str, str],
    *,
    gene_column: str = "gene",
    reference_group: str,
    comparison_group: str,
    batches: Mapping[str, str] | None = None,
    covariates: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, DesignAudit]:
    genes, counts = validate_count_matrix(frame, gene_column)
    if not np.allclose(counts.to_numpy(), np.round(counts.to_numpy())):
        raise ValueError("Negative-binomial analysis requires integer-like raw counts.")
    design, selected, audit = build_design_matrix(
        counts.columns.tolist(),
        groups,
        reference_group=reference_group,
        comparison_group=comparison_group,
        batches=batches,
        covariates=covariates,
    )
    selected_counts = counts[selected].to_numpy(float)
    libraries = selected_counts.sum(axis=0)
    if (libraries <= 0).any():
        raise ValueError("Every selected sample must have a positive library size.")
    geometric_library = float(np.exp(np.mean(np.log(libraries))))
    offset = np.log(libraries / geometric_library)
    rows = []
    for gene, y in zip(genes, selected_counts):
        beta, covariance, dispersion, converged = _fit_nb_gene(y, design, offset)
        standard_error = (
            sqrt(max(float(covariance[1, 1]), 0.0)) if covariance.size else float("nan")
        )
        statistic = float(beta[1] / standard_error) if standard_error > 0 else 0.0
        p_value = _normal_p_value(statistic)
        rows.append(
            {
                "gene": gene,
                "base_mean": float(np.mean(y)),
                "log2_fold_change": float(beta[1] / np.log(2)),
                "standard_error": standard_error / np.log(2)
                if np.isfinite(standard_error)
                else np.nan,
                "wald_statistic": statistic,
                "p_value": p_value,
                "dispersion": dispersion,
                "converged": converged,
                "method": "negative-binomial GLM with library-size offset",
            }
        )
    result = pd.DataFrame(rows)
    result["fdr_bh"] = _fdr_bh(result["p_value"].to_numpy(float))
    return result.sort_values(["fdr_bh", "p_value"]).reset_index(drop=True), audit


def sample_diagnostics(
    frame: pd.DataFrame,
    *,
    gene_column: str = "gene",
    log_transform: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    _, counts = validate_count_matrix(frame, gene_column)
    values = np.log2(counts + 1.0) if log_transform else counts.astype(float)
    correlation = values.corr(method="pearson")
    sample_matrix = values.T.to_numpy(dtype=float)
    squared_norms = np.einsum("ij,ij->i", sample_matrix, sample_matrix)
    squared_distances = (
        squared_norms[:, None] + squared_norms[None, :] - 2.0 * (sample_matrix @ sample_matrix.T)
    )
    np.maximum(squared_distances, 0.0, out=squared_distances)
    distance = pd.DataFrame(
        np.sqrt(squared_distances), index=values.columns, columns=values.columns
    )
    components = min(3, len(values.columns), len(values))
    scores = PCA(n_components=components, random_state=42).fit_transform(
        StandardScaler().fit_transform(values.T)
    )
    diagnostics = pd.DataFrame({"sample": values.columns})
    diagnostics["library_size"] = counts.sum(axis=0).to_numpy(float)
    diagnostics["detected_genes"] = (counts > 0).sum(axis=0).to_numpy(int)
    for index in range(components):
        diagnostics[f"PC{index + 1}"] = scores[:, index]
    robust_columns = ["library_size", "detected_genes", *[f"PC{i + 1}" for i in range(components)]]
    flags = np.zeros(len(diagnostics), dtype=int)
    for column in robust_columns:
        values_column = diagnostics[column].to_numpy(float)
        median = np.median(values_column)
        mad = np.median(np.abs(values_column - median))
        if mad > 0:
            flags += (np.abs(values_column - median) / (1.4826 * mad) > 3.5).astype(int)
    diagnostics["outlier_flag_count"] = flags
    diagnostics["review_sample"] = flags > 0
    return diagnostics, correlation, distance


def residualize_batch(
    frame: pd.DataFrame,
    batches: Mapping[str, str],
    *,
    gene_column: str = "gene",
    values_are_log2: bool = True,
) -> pd.DataFrame:
    genes, values = validate_count_matrix(frame, gene_column)
    matrix = values.astype(float) if values_are_log2 else np.log2(values + 1.0)
    labels = [str(batches.get(sample, "")) for sample in matrix.columns]
    levels = list(dict.fromkeys(labels))
    if len(levels) < 2:
        return pd.concat([genes.rename(gene_column), matrix], axis=1)
    design = np.column_stack(
        [
            np.ones(len(labels)),
            *[
                np.array([1.0 if value == level else 0.0 for value in labels])
                for level in levels[1:]
            ],
        ]
    )
    response = matrix.to_numpy(float).T
    beta = np.linalg.pinv(design) @ response
    batch_effect = design[:, 1:] @ beta[1:] if design.shape[1] > 1 else 0.0
    corrected = response - batch_effect
    corrected += np.mean(response, axis=0) - np.mean(corrected, axis=0)
    output = pd.DataFrame(corrected.T, columns=matrix.columns)
    return pd.concat([genes.rename(gene_column).reset_index(drop=True), output], axis=1)


def ma_plot_table(results: pd.DataFrame) -> pd.DataFrame:
    required = {"base_mean", "log2_fold_change"}
    if not required.issubset(results.columns):
        raise ValueError("Results require base_mean and log2_fold_change columns.")
    output = results.copy()
    output["mean_expression_log10"] = np.log10(
        pd.to_numeric(output["base_mean"], errors="coerce").clip(lower=1e-8)
    )
    return output
