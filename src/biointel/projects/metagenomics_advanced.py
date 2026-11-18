from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import t as t_distribution
from sklearn.manifold import MDS


@dataclass(frozen=True)
class RestrictedPermanovaResult:
    pseudo_f: float
    r_squared: float
    permutation_p_value: float
    permutations: int
    strata_column: str | None
    permutable_units: int


def multiplicative_zero_replacement(
    relative_frame: pd.DataFrame,
    *,
    taxon_column: str = "taxon",
    delta_fraction: float = 0.65,
) -> pd.DataFrame:
    if taxon_column not in relative_frame.columns:
        raise ValueError("Taxon column is missing.")
    values = relative_frame.drop(columns=[taxon_column]).apply(pd.to_numeric, errors="raise").to_numpy(float)
    if np.any(values < 0):
        raise ValueError("Compositional values cannot be negative.")
    output = np.zeros_like(values, dtype=float)
    for column in range(values.shape[1]):
        vector = values[:, column]
        total = vector.sum()
        if total <= 0:
            raise ValueError("Every sample must have positive total abundance.")
        composition = vector / total
        zero_mask = composition == 0
        zero_count = int(zero_mask.sum())
        if zero_count == 0:
            output[:, column] = composition
            continue
        positive = composition[~zero_mask]
        replacement = min(float(positive.min()) * delta_fraction, 1 / (2 * len(composition)))
        output[zero_mask, column] = replacement
        scale = 1 - replacement * zero_count
        output[~zero_mask, column] = composition[~zero_mask] * scale / composition[~zero_mask].sum()
    return pd.DataFrame({taxon_column: relative_frame[taxon_column].astype(str), **{column: output[:, index] for index, column in enumerate(relative_frame.columns[1:])}})


def clr_transform_robust(relative_frame: pd.DataFrame, *, taxon_column: str = "taxon") -> pd.DataFrame:
    replaced = multiplicative_zero_replacement(relative_frame, taxon_column=taxon_column)
    values = replaced.drop(columns=[taxon_column]).to_numpy(float)
    log_values = np.log(values)
    clr = log_values - log_values.mean(axis=0, keepdims=True)
    return pd.DataFrame(clr, index=replaced[taxon_column].astype(str), columns=replaced.columns[1:])


def nmds_ordination(distance: pd.DataFrame, *, random_state: int = 42, dimensions: int = 2) -> tuple[pd.DataFrame, dict[str, float]]:
    if distance.shape[0] < 3 or distance.shape[0] != distance.shape[1]:
        raise ValueError("NMDS requires a square distance matrix with at least three samples.")
    model = MDS(
        n_components=dimensions,
        metric_mds=False,
        metric="precomputed",
        init="random",
        random_state=random_state,
        n_init=8,
        max_iter=500,
        eps=1e-6,
        normalized_stress="auto",
    )
    coordinates = model.fit_transform(distance.to_numpy(float))
    columns = [f"NMDS{index + 1}" for index in range(dimensions)]
    frame = pd.DataFrame(coordinates, columns=columns)
    frame.insert(0, "sample", distance.index.astype(str))
    return frame, {"stress": float(model.stress_), "iterations": int(model.n_iter_)}


def _pseudo_f(distance_values: np.ndarray, groups: np.ndarray) -> tuple[float, float]:
    unique_groups = np.unique(groups)
    n = len(groups)
    if len(unique_groups) < 2 or n <= len(unique_groups):
        raise ValueError("PERMANOVA requires at least two groups and residual degrees of freedom.")
    squared = np.square(distance_values)
    total_ss = squared.sum() / (2 * n)
    within_ss = 0.0
    for group in unique_groups:
        indices = np.where(groups == group)[0]
        if len(indices) > 1:
            within_ss += squared[np.ix_(indices, indices)].sum() / (2 * len(indices))
    between_ss = max(total_ss - within_ss, 0.0)
    df_between = len(unique_groups) - 1
    df_within = n - len(unique_groups)
    pseudo_f = (between_ss / df_between) / (within_ss / df_within) if within_ss > 0 else np.inf
    r_squared = between_ss / total_ss if total_ss > 0 else 0.0
    return float(pseudo_f), float(r_squared)


def restricted_permanova(
    distance: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    group_column: str = "group",
    strata_column: str | None = None,
    permutations: int = 999,
    random_state: int = 42,
) -> RestrictedPermanovaResult:
    if "sample" not in metadata.columns or group_column not in metadata.columns:
        raise ValueError("Metadata requires sample and group columns.")
    aligned = metadata.set_index(metadata["sample"].astype(str)).reindex(distance.index.astype(str))
    if aligned[group_column].isna().any():
        raise ValueError("Metadata does not cover every distance-matrix sample.")
    groups = aligned[group_column].astype(str).to_numpy()
    observed, r_squared = _pseudo_f(distance.to_numpy(float), groups)
    rng = np.random.default_rng(random_state)
    exceed = 0
    if strata_column and strata_column in aligned.columns:
        strata = aligned[strata_column].astype(str).to_numpy()
        units = len(np.unique(strata))
        strata_indices = [np.where(strata == value)[0] for value in np.unique(strata)]
        for _ in range(permutations):
            permuted = groups.copy()
            for indices in strata_indices:
                permuted[indices] = rng.permutation(permuted[indices])
            statistic, _ = _pseudo_f(distance.to_numpy(float), permuted)
            exceed += int(statistic >= observed)
    else:
        units = len(groups)
        for _ in range(permutations):
            statistic, _ = _pseudo_f(distance.to_numpy(float), rng.permutation(groups))
            exceed += int(statistic >= observed)
    return RestrictedPermanovaResult(
        pseudo_f=observed,
        r_squared=r_squared,
        permutation_p_value=(exceed + 1) / (permutations + 1),
        permutations=permutations,
        strata_column=strata_column if strata_column in aligned.columns else None,
        permutable_units=units,
    )


def contamination_screen(
    relative_frame: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    taxon_column: str = "taxon",
    control_column: str = "sample_type",
    negative_labels: tuple[str, ...] = ("negative", "blank", "ntc", "control"),
    prevalence_ratio_threshold: float = 1.5,
) -> pd.DataFrame:
    if control_column not in metadata.columns:
        return pd.DataFrame(columns=["taxon", "negative_prevalence", "biological_prevalence", "negative_mean_abundance", "biological_mean_abundance", "contaminant_flag"])
    meta = metadata.set_index(metadata["sample"].astype(str))
    samples = [column for column in relative_frame.columns if column != taxon_column and column in meta.index]
    negative = [sample for sample in samples if str(meta.loc[sample, control_column]).lower() in negative_labels]
    biological = [sample for sample in samples if sample not in negative]
    if not negative or not biological:
        return pd.DataFrame(columns=["taxon", "negative_prevalence", "biological_prevalence", "negative_mean_abundance", "biological_mean_abundance", "contaminant_flag"])
    rows = []
    for _, row in relative_frame.iterrows():
        neg_values = pd.to_numeric(row[negative], errors="coerce").fillna(0).to_numpy(float)
        bio_values = pd.to_numeric(row[biological], errors="coerce").fillna(0).to_numpy(float)
        negative_prevalence = float((neg_values > 0).mean())
        biological_prevalence = float((bio_values > 0).mean())
        negative_mean = float(neg_values.mean())
        biological_mean = float(bio_values.mean())
        prevalence_ratio = negative_prevalence / max(biological_prevalence, 1 / max(len(biological), 1))
        flag = prevalence_ratio >= prevalence_ratio_threshold and negative_mean >= biological_mean
        rows.append({
            "taxon": str(row[taxon_column]),
            "negative_prevalence": negative_prevalence,
            "biological_prevalence": biological_prevalence,
            "negative_mean_abundance": negative_mean,
            "biological_mean_abundance": biological_mean,
            "prevalence_ratio": prevalence_ratio,
            "contaminant_flag": bool(flag),
        })
    return pd.DataFrame(rows).sort_values(["contaminant_flag", "prevalence_ratio"], ascending=[False, False]).reset_index(drop=True)


def covariate_adjusted_clr_association(
    relative_frame: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    group_column: str = "group",
    reference_group: str,
    comparison_group: str,
    covariates: list[str] | None = None,
    taxon_column: str = "taxon",
) -> pd.DataFrame:
    clr = clr_transform_robust(relative_frame, taxon_column=taxon_column)
    meta = metadata.copy()
    meta["sample"] = meta["sample"].astype(str)
    meta = meta[meta[group_column].astype(str).isin([str(reference_group), str(comparison_group)])].set_index("sample")
    samples = [sample for sample in clr.columns if sample in meta.index]
    if len(samples) < 4:
        raise ValueError("Covariate-adjusted association requires at least four matched samples.")
    meta = meta.loc[samples]
    design = pd.DataFrame({"intercept": 1.0, "group_effect": (meta[group_column].astype(str) == str(comparison_group)).astype(float)}, index=samples)
    for covariate in covariates or []:
        if covariate not in meta.columns:
            continue
        numeric = pd.to_numeric(meta[covariate], errors="coerce")
        if numeric.notna().sum() == len(numeric) and numeric.nunique() > 1:
            design[covariate] = (numeric - numeric.mean()) / max(numeric.std(ddof=0), 1e-12)
        else:
            dummies = pd.get_dummies(meta[covariate].astype(str), prefix=covariate, drop_first=True, dtype=float)
            design = pd.concat([design, dummies], axis=1)
    x = design.to_numpy(float)
    if np.linalg.matrix_rank(x) < x.shape[1]:
        raise ValueError("Design matrix is rank deficient; remove redundant covariates.")
    inverse = np.linalg.inv(x.T @ x)
    rows = []
    for taxon, values in clr[samples].iterrows():
        y = values.to_numpy(float)
        beta = inverse @ x.T @ y
        residual = y - x @ beta
        df = len(y) - x.shape[1]
        variance = float(residual @ residual / df) if df > 0 else np.nan
        standard_error = float(np.sqrt(max(variance * inverse[1, 1], 0))) if df > 0 else np.nan
        t_statistic = float(beta[1] / standard_error) if standard_error > 0 else np.nan
        p_value = float(2 * t_distribution.sf(abs(t_statistic), df)) if np.isfinite(t_statistic) and df > 0 else 1.0
        rows.append({"taxon": str(taxon), "clr_group_effect": float(beta[1]), "standard_error": standard_error, "t_statistic": t_statistic, "p_value": p_value, "residual_df": df, "covariates": ", ".join(covariates or [])})
    output = pd.DataFrame(rows)
    order = output["p_value"].sort_values().index
    ranked = output.loc[order, "p_value"].to_numpy(float)
    adjusted = np.minimum.accumulate((ranked * len(ranked) / np.arange(1, len(ranked) + 1))[::-1])[::-1]
    output.loc[order, "fdr_q_value"] = np.clip(adjusted, 0, 1)
    output["screening_significant"] = output["fdr_q_value"] <= 0.05
    return output.sort_values(["fdr_q_value", "p_value"]).reset_index(drop=True)


def longitudinal_alpha_change(
    alpha: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    metric: str = "shannon",
    subject_column: str = "subject",
    time_column: str = "timepoint",
) -> pd.DataFrame:
    if subject_column not in metadata.columns or time_column not in metadata.columns:
        return pd.DataFrame()
    merged = alpha.merge(metadata[["sample", subject_column, time_column]], on="sample", how="inner")
    merged[time_column] = pd.to_numeric(merged[time_column], errors="coerce")
    merged = merged.dropna(subset=[time_column, metric])
    rows = []
    for subject, part in merged.groupby(subject_column):
        part = part.sort_values(time_column)
        if len(part) < 2:
            continue
        slope, intercept = np.polyfit(part[time_column].to_numpy(float), part[metric].to_numpy(float), 1)
        rows.append({"subject": str(subject), "observations": len(part), "alpha_slope": float(slope), "intercept": float(intercept), "start_value": float(part.iloc[0][metric]), "end_value": float(part.iloc[-1][metric])})
    return pd.DataFrame(rows)


def functional_profile_summary(
    frame: pd.DataFrame,
    *,
    feature_column: str = "feature",
    pathway_column: str = "pathway",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {feature_column, pathway_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("Functional profile requires feature and pathway columns.")
    sample_columns = [column for column in frame.columns if column not in required and pd.api.types.is_numeric_dtype(frame[column])]
    if not sample_columns:
        raise ValueError("Functional profile contains no numeric sample columns.")
    values = frame[sample_columns].apply(pd.to_numeric, errors="raise")
    if (values < 0).any().any():
        raise ValueError("Functional abundances cannot be negative.")
    feature = pd.concat([frame[[feature_column, pathway_column]].astype(str), values], axis=1)
    pathway = feature.groupby(pathway_column, as_index=False)[sample_columns].sum()
    totals = pathway[sample_columns].sum(axis=0).replace(0, np.nan)
    pathway_relative = pathway.copy()
    pathway_relative[sample_columns] = pathway[sample_columns].div(totals, axis=1).fillna(0)
    return feature, pathway_relative


def pcoa_diagnostics(distance: pd.DataFrame, *, dimensions: int = 5) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float | int | bool]]:
    """Classical PCoA with explicit negative-eigenvalue diagnostics.

    The routine preserves all eigenvalues for auditing and reports whether a
    Euclidean correction should be considered. Coordinates are returned only
    for positive axes because negative axes do not have real-valued scores.
    """
    matrix = distance.to_numpy(float)
    if matrix.shape[0] < 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("PCoA requires a square distance matrix with at least two samples.")
    if not np.allclose(matrix, matrix.T, atol=1e-8) or not np.allclose(np.diag(matrix), 0, atol=1e-8):
        raise ValueError("Distance matrix must be symmetric with a zero diagonal.")
    n = matrix.shape[0]
    centering = np.eye(n) - np.ones((n, n)) / n
    gram = -0.5 * centering @ np.square(matrix) @ centering
    eigenvalues, eigenvectors = np.linalg.eigh(gram)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]
    positive = eigenvalues > 1e-12
    positive_total = float(eigenvalues[positive].sum())
    negative_total = float(np.abs(eigenvalues[eigenvalues < -1e-12]).sum())
    axes = min(int(dimensions), int(positive.sum()))
    coordinates = eigenvectors[:, :axes] * np.sqrt(np.clip(eigenvalues[:axes], 0, None))
    coordinate_frame = pd.DataFrame(coordinates, columns=[f"PCoA{index + 1}" for index in range(axes)])
    coordinate_frame.insert(0, "sample", distance.index.astype(str))
    eigen_table = pd.DataFrame(
        {
            "axis": [f"Axis {index + 1}" for index in range(len(eigenvalues))],
            "eigenvalue": eigenvalues,
            "variance_percent": np.where(
                positive & (positive_total > 0),
                np.clip(eigenvalues, 0, None) / max(positive_total, 1e-12) * 100,
                0.0,
            ),
            "negative_axis": eigenvalues < -1e-12,
        }
    )
    diagnostics: dict[str, float | int | bool] = {
        "positive_axes": int(positive.sum()),
        "negative_axes": int((eigenvalues < -1e-12).sum()),
        "negative_eigenvalue_mass": negative_total,
        "negative_to_positive_ratio": negative_total / max(positive_total, 1e-12),
        "correction_recommended": bool(negative_total / max(positive_total, 1e-12) > 0.01),
    }
    return coordinate_frame, eigen_table, diagnostics


def _read_phylogenetic_tree(newick_text: str):
    from io import StringIO

    from Bio import Phylo

    if not str(newick_text).strip():
        raise ValueError("A Newick phylogenetic tree is required.")
    tree = Phylo.read(StringIO(str(newick_text).strip()), "newick")
    terminals = [str(node.name) for node in tree.get_terminals() if node.name]
    if len(terminals) != len(set(terminals)):
        raise ValueError("Phylogenetic tree contains duplicate terminal names.")
    if len(terminals) < 2:
        raise ValueError("Phylogenetic tree requires at least two named terminal taxa.")
    return tree


def _branch_descendant_taxa(tree) -> list[tuple[float, set[str]]]:
    branches: list[tuple[float, set[str]]] = []
    for clade in tree.find_clades(order="preorder"):
        if clade is tree.root:
            continue
        descendants = {str(node.name) for node in clade.get_terminals() if node.name}
        length = float(clade.branch_length if clade.branch_length is not None else 1.0)
        if length < 0:
            raise ValueError("Phylogenetic branch lengths cannot be negative.")
        branches.append((length, descendants))
    return branches


def faith_phylogenetic_diversity(
    abundance_frame: pd.DataFrame,
    newick_text: str,
    *,
    taxon_column: str = "taxon",
) -> pd.DataFrame:
    """Calculate Faith's phylogenetic diversity for each sample.

    Taxa absent from the tree are reported in the output and ignored rather
    than silently treated as zero-length branches.
    """
    if taxon_column not in abundance_frame.columns:
        raise ValueError("Taxon column is missing.")
    tree = _read_phylogenetic_tree(newick_text)
    tree_taxa = {str(node.name) for node in tree.get_terminals() if node.name}
    branches = _branch_descendant_taxa(tree)
    taxa = abundance_frame[taxon_column].astype(str)
    sample_columns = [column for column in abundance_frame.columns if column != taxon_column]
    values = abundance_frame[sample_columns].apply(pd.to_numeric, errors="raise")
    if (values < 0).any().any():
        raise ValueError("Abundance values cannot be negative.")
    rows = []
    for sample in sample_columns:
        present = set(taxa[values[sample].to_numpy(float) > 0]) & tree_taxa
        pd_value = sum(length for length, descendants in branches if descendants & present)
        rows.append(
            {
                "sample": str(sample),
                "faith_pd": float(pd_value),
                "observed_tree_taxa": len(present),
                "observed_input_taxa": int((values[sample] > 0).sum()),
                "unmatched_present_taxa": int(len(set(taxa[values[sample].to_numpy(float) > 0]) - tree_taxa)),
                "tree_coverage_percent": 100 * len(present) / max(int((values[sample] > 0).sum()), 1),
            }
        )
    return pd.DataFrame(rows)


def unifrac_distance(
    abundance_frame: pd.DataFrame,
    newick_text: str,
    *,
    taxon_column: str = "taxon",
    weighted: bool = False,
) -> pd.DataFrame:
    """Compute normalized unweighted or weighted UniFrac distances locally."""
    if taxon_column not in abundance_frame.columns:
        raise ValueError("Taxon column is missing.")
    tree = _read_phylogenetic_tree(newick_text)
    tree_taxa = {str(node.name) for node in tree.get_terminals() if node.name}
    branches = _branch_descendant_taxa(tree)
    samples = [column for column in abundance_frame.columns if column != taxon_column]
    values = abundance_frame[samples].apply(pd.to_numeric, errors="raise")
    if (values < 0).any().any():
        raise ValueError("Abundance values cannot be negative.")
    taxa = abundance_frame[taxon_column].astype(str).tolist()
    matched_indices = [index for index, taxon in enumerate(taxa) if taxon in tree_taxa]
    if not matched_indices:
        raise ValueError("No abundance-table taxa match the phylogenetic tree terminals.")
    matched_taxa = [taxa[index] for index in matched_indices]
    matrix = values.iloc[matched_indices].to_numpy(float)
    totals = matrix.sum(axis=0)
    if np.any(totals <= 0):
        raise ValueError("Every sample requires positive abundance among tree-matched taxa.")
    relative = matrix / totals
    taxon_to_index = {taxon: index for index, taxon in enumerate(matched_taxa)}
    branch_profiles = []
    branch_lengths = []
    for length, descendants in branches:
        indices = [taxon_to_index[taxon] for taxon in descendants if taxon in taxon_to_index]
        if not indices or length == 0:
            continue
        branch_profiles.append(relative[indices, :].sum(axis=0))
        branch_lengths.append(length)
    profiles = np.asarray(branch_profiles, dtype=float)
    lengths = np.asarray(branch_lengths, dtype=float)
    output = np.zeros((len(samples), len(samples)), dtype=float)
    for left in range(len(samples)):
        for right in range(left + 1, len(samples)):
            if weighted:
                numerator = float(np.sum(lengths * np.abs(profiles[:, left] - profiles[:, right])))
                denominator = float(np.sum(lengths * (profiles[:, left] + profiles[:, right])))
            else:
                left_present = profiles[:, left] > 0
                right_present = profiles[:, right] > 0
                numerator = float(np.sum(lengths[left_present ^ right_present]))
                denominator = float(np.sum(lengths[left_present | right_present]))
            value = numerator / denominator if denominator > 0 else 0.0
            output[left, right] = output[right, left] = value
    return pd.DataFrame(output, index=[str(sample) for sample in samples], columns=[str(sample) for sample in samples])
