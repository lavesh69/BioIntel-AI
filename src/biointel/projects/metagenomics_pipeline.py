from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MetagenomicsResult:
    qc: pd.DataFrame
    filtered_counts: pd.DataFrame
    relative_abundance: pd.DataFrame
    alpha_diversity: pd.DataFrame
    distance_matrix: pd.DataFrame
    ordination: pd.DataFrame
    differential_taxa: pd.DataFrame
    summary: dict[str, float | int]


def validate_abundance_table(frame: pd.DataFrame, *, taxon_column: str = "taxon") -> pd.DataFrame:
    if taxon_column not in frame.columns:
        raise ValueError(f"Abundance table must include a '{taxon_column}' column.")
    cleaned = frame.copy()
    cleaned[taxon_column] = cleaned[taxon_column].astype(str).str.strip()
    if (cleaned[taxon_column] == "").any() or cleaned[taxon_column].duplicated().any():
        raise ValueError("Taxon names must be non-empty and unique.")
    sample_columns = [column for column in cleaned.columns if column != taxon_column]
    if len(sample_columns) < 4:
        raise ValueError("At least four samples are required.")
    numeric = cleaned[sample_columns].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        raise ValueError("All abundance values must be numeric.")
    if (numeric < 0).any().any():
        raise ValueError("Abundance values cannot be negative.")
    if (numeric.sum(axis=0) <= 0).any():
        raise ValueError("Every sample must contain at least one count.")
    cleaned[sample_columns] = numeric.astype(float)
    return cleaned


def normalize_abundance_input(
    frame: pd.DataFrame,
    *,
    taxon_column: str = "taxon",
    input_kind: str = "auto",
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Detect and normalize count, fractional, percent or continuous abundance tables."""

    validated = validate_abundance_table(frame, taxon_column=taxon_column)
    sample_columns = [column for column in validated.columns if column != taxon_column]
    matrix = validated[sample_columns].astype(float)
    totals = matrix.sum(axis=0)
    integer_fraction = float(np.isclose(matrix.to_numpy(), np.round(matrix.to_numpy()), atol=1e-8).mean())
    requested = str(input_kind).strip().lower().replace(" ", "_")
    if requested in {"auto", "auto_detect"}:
        if np.allclose(totals.to_numpy(), 1.0, rtol=0.05, atol=0.02):
            detected = "relative_fraction"
        elif np.allclose(totals.to_numpy(), 100.0, rtol=0.05, atol=2.0):
            detected = "relative_percent"
        elif integer_fraction >= 0.98:
            detected = "raw_counts"
        else:
            detected = "continuous_abundance"
    else:
        aliases = {
            "raw_counts": "raw_counts",
            "counts": "raw_counts",
            "relative_fraction": "relative_fraction",
            "fraction": "relative_fraction",
            "relative_percent": "relative_percent",
            "percent": "relative_percent",
            "continuous_abundance": "continuous_abundance",
            "continuous": "continuous_abundance",
        }
        if requested not in aliases:
            raise ValueError(f"Unsupported abundance input kind: {input_kind}")
        detected = aliases[requested]

    normalized = validated.copy()
    if detected == "relative_percent":
        normalized[sample_columns] = matrix / 100.0
    elif detected == "relative_fraction":
        normalized[sample_columns] = matrix
    if detected in {"relative_fraction", "relative_percent"}:
        renormalized = normalized[sample_columns].divide(
            normalized[sample_columns].sum(axis=0).replace(0, np.nan), axis=1
        )
        normalized[sample_columns] = renormalized.fillna(0.0)

    report: dict[str, object] = {
        "detected_input_kind": detected,
        "sample_count": len(sample_columns),
        "median_sample_total": float(totals.median()),
        "minimum_sample_total": float(totals.min()),
        "maximum_sample_total": float(totals.max()),
        "integer_value_fraction": integer_fraction,
        "supports_classical_rarefaction": detected == "raw_counts",
        "recommended_minimum_total": 10.0 if detected == "raw_counts" else 0.001,
    }
    return normalized, report


def sample_qc(frame: pd.DataFrame, *, taxon_column: str = "taxon") -> pd.DataFrame:
    abundance = validate_abundance_table(frame, taxon_column=taxon_column)
    matrix = abundance.set_index(taxon_column)
    totals = matrix.sum(axis=0)
    observed = (matrix > 0).sum(axis=0)
    dominant = matrix.max(axis=0) / totals.replace(0, np.nan)
    return pd.DataFrame(
        {
            "sample": matrix.columns,
            "total_reads": totals.values,
            "observed_taxa": observed.values,
            "dominant_taxon_percent": (dominant.fillna(0) * 100).values,
            "zero_fraction_percent": ((matrix == 0).mean(axis=0) * 100).values,
        }
    )


def filter_taxa(
    frame: pd.DataFrame,
    *,
    taxon_column: str = "taxon",
    minimum_prevalence_percent: float = 10.0,
    minimum_total_count: float = 10.0,
) -> pd.DataFrame:
    abundance = validate_abundance_table(frame, taxon_column=taxon_column)
    matrix = abundance.set_index(taxon_column)
    prevalence = (matrix > 0).mean(axis=1) * 100
    total = matrix.sum(axis=1)
    keep = (prevalence >= minimum_prevalence_percent) & (total >= minimum_total_count)
    filtered = matrix.loc[keep].copy()
    if filtered.empty:
        raise ValueError("No taxa remain after filtering. Relax prevalence or count thresholds.")
    return filtered.reset_index()


def relative_abundance(frame: pd.DataFrame, *, taxon_column: str = "taxon") -> pd.DataFrame:
    abundance = validate_abundance_table(frame, taxon_column=taxon_column)
    matrix = abundance.set_index(taxon_column)
    relative = matrix.divide(matrix.sum(axis=0).replace(0, np.nan), axis=1).fillna(0)
    return relative.reset_index()


def alpha_diversity(frame: pd.DataFrame, *, taxon_column: str = "taxon") -> pd.DataFrame:
    relative = relative_abundance(frame, taxon_column=taxon_column).set_index(taxon_column)
    rows = []
    for sample in relative.columns:
        values = relative[sample].to_numpy(dtype=float)
        positive = values[values > 0]
        shannon = float(-(positive * np.log(positive)).sum()) if positive.size else 0.0
        simpson = float(1.0 - np.square(positive).sum()) if positive.size else 0.0
        observed = int((values > 0).sum())
        evenness = shannon / np.log(observed) if observed > 1 else 0.0
        rows.append(
            {
                "sample": sample,
                "observed_taxa": observed,
                "shannon": shannon,
                "simpson": simpson,
                "pielou_evenness": float(evenness),
            }
        )
    return pd.DataFrame(rows)


def bray_curtis_distance(frame: pd.DataFrame, *, taxon_column: str = "taxon") -> pd.DataFrame:
    abundance = validate_abundance_table(frame, taxon_column=taxon_column)
    matrix = abundance.set_index(taxon_column).T.to_numpy(dtype=float)
    samples = [column for column in abundance.columns if column != taxon_column]
    distances = np.zeros((len(samples), len(samples)), dtype=float)
    for left in range(len(samples)):
        for right in range(left, len(samples)):
            denominator = float((matrix[left] + matrix[right]).sum())
            distance = float(np.abs(matrix[left] - matrix[right]).sum() / denominator) if denominator else 0.0
            distances[left, right] = distance
            distances[right, left] = distance
    return pd.DataFrame(distances, index=samples, columns=samples)


def pcoa(distance: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    values = distance.to_numpy(dtype=float)
    n = values.shape[0]
    centering = np.eye(n) - np.ones((n, n)) / n
    gram = -0.5 * centering @ np.square(values) @ centering
    eigenvalues, eigenvectors = np.linalg.eigh(gram)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]
    positive = eigenvalues > 1e-12
    positive_values = eigenvalues[positive]
    positive_vectors = eigenvectors[:, positive]
    if len(positive_values) < 2:
        coordinates = np.zeros((n, 2), dtype=float)
        explained = np.array([0.0, 0.0])
    else:
        coordinates = positive_vectors[:, :2] * np.sqrt(positive_values[:2])
        explained = positive_values[:2] / positive_values.sum()
    embedding = pd.DataFrame(
        {"sample": distance.index, "PCoA1": coordinates[:, 0], "PCoA2": coordinates[:, 1]}
    )
    return embedding, {"axis1_variance": float(explained[0]), "axis2_variance": float(explained[1])}


def differential_abundance_screen(
    relative_frame: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    taxon_column: str = "taxon",
    sample_column: str = "sample",
    group_column: str = "group",
    group_a: str,
    group_b: str,
    pseudocount: float = 1e-6,
) -> pd.DataFrame:
    if not {sample_column, group_column}.issubset(metadata.columns):
        raise ValueError("Metadata requires sample and group columns.")
    matrix = relative_frame.set_index(taxon_column)
    metadata_clean = metadata[[sample_column, group_column]].copy()
    metadata_clean[sample_column] = metadata_clean[sample_column].astype(str)
    metadata_clean[group_column] = metadata_clean[group_column].astype(str)
    samples_a = [sample for sample in metadata_clean.loc[metadata_clean[group_column] == group_a, sample_column] if sample in matrix.columns]
    samples_b = [sample for sample in metadata_clean.loc[metadata_clean[group_column] == group_b, sample_column] if sample in matrix.columns]
    if len(samples_a) < 2 or len(samples_b) < 2:
        raise ValueError("Each comparison group needs at least two matching samples.")
    mean_a = matrix[samples_a].mean(axis=1)
    mean_b = matrix[samples_b].mean(axis=1)
    log2_fc = np.log2((mean_b + pseudocount) / (mean_a + pseudocount))
    prevalence_a = (matrix[samples_a] > 0).mean(axis=1)
    prevalence_b = (matrix[samples_b] > 0).mean(axis=1)
    effect = log2_fc.abs() * (prevalence_a - prevalence_b).abs()
    result = pd.DataFrame(
        {
            "taxon": matrix.index,
            f"mean_{group_a}": mean_a.values,
            f"mean_{group_b}": mean_b.values,
            "log2_fold_change": log2_fc.values,
            f"prevalence_{group_a}_percent": (prevalence_a * 100).values,
            f"prevalence_{group_b}_percent": (prevalence_b * 100).values,
            "screening_effect_score": effect.values,
        }
    )
    result["direction"] = np.where(result["log2_fold_change"] >= 0, f"Higher in {group_b}", f"Higher in {group_a}")
    result["screening_flag"] = np.where(
        (result["log2_fold_change"].abs() >= 1.0) & (result["screening_effect_score"] >= 0.25),
        "Review",
        "Background",
    )
    return result.sort_values("screening_effect_score", ascending=False).reset_index(drop=True)


def run_metagenomics_pipeline(
    abundance_frame: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    minimum_prevalence_percent: float = 10.0,
    minimum_total_count: float = 10.0,
    group_a: str,
    group_b: str,
) -> MetagenomicsResult:
    if group_a == group_b:
        raise ValueError("group_a and group_b must be different.")
    required_metadata = {"sample", "group"}
    if not required_metadata.issubset(metadata.columns):
        raise ValueError("Metadata requires sample and group columns.")
    selected_metadata = metadata.copy()
    selected_metadata["sample"] = selected_metadata["sample"].astype(str).str.strip()
    selected_metadata["group"] = selected_metadata["group"].astype(str).str.strip()
    if selected_metadata["sample"].duplicated().any():
        duplicates = selected_metadata.loc[selected_metadata["sample"].duplicated(), "sample"].unique().tolist()
        raise ValueError(f"Metadata sample identifiers must be unique: {', '.join(duplicates[:5])}")
    selected_metadata = selected_metadata[selected_metadata["group"].isin([str(group_a), str(group_b)])].copy()
    if selected_metadata["group"].nunique() != 2:
        raise ValueError("Both selected comparison groups must be present in metadata.")
    validated = validate_abundance_table(abundance_frame)
    abundance_samples = {column for column in validated.columns if column != "taxon"}
    matched_sample_order = [sample for sample in selected_metadata["sample"] if sample in abundance_samples]
    matched_samples = set(matched_sample_order)
    group_counts = selected_metadata[selected_metadata["sample"].isin(matched_samples)].groupby("group")["sample"].nunique()
    if any(int(group_counts.get(group, 0)) < 2 for group in (str(group_a), str(group_b))):
        raise ValueError("Each selected group needs at least two samples present in the abundance table.")
    selected_metadata = selected_metadata[selected_metadata["sample"].isin(matched_samples)].copy()
    validated = validated[["taxon", *matched_sample_order]].copy()
    qc = sample_qc(validated)
    filtered = filter_taxa(
        validated,
        minimum_prevalence_percent=minimum_prevalence_percent,
        minimum_total_count=minimum_total_count,
    )
    relative = relative_abundance(filtered)
    alpha = alpha_diversity(filtered)
    distance = bray_curtis_distance(filtered)
    ordination, variance = pcoa(distance)
    ordination = ordination.merge(selected_metadata[["sample", "group"]], on="sample", how="left")
    differential = differential_abundance_screen(
        relative,
        selected_metadata,
        group_a=group_a,
        group_b=group_b,
    )
    summary: dict[str, float | int] = {
        "input_taxa": len(validated),
        "retained_taxa": len(filtered),
        "taxa_retention_percent": len(filtered) / max(len(validated), 1) * 100,
        "samples": len(qc),
        "median_reads": float(qc["total_reads"].median()),
        "median_shannon": float(alpha["shannon"].median()),
        "pcoa_axis1_variance_percent": variance["axis1_variance"] * 100,
        "pcoa_axis2_variance_percent": variance["axis2_variance"] * 100,
        "screening_taxa": int((differential["screening_flag"] == "Review").sum()),
    }
    return MetagenomicsResult(qc, filtered, relative, alpha, distance, ordination, differential, summary)


def demo_metagenomics_data(
    *,
    taxa: int = 90,
    samples_per_group: int = 8,
    random_state: int = 37,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(random_state)
    groups = ["Control"] * samples_per_group + ["Case"] * samples_per_group
    samples = [f"SAMPLE_{index + 1:02d}" for index in range(len(groups))]
    taxon_names = [f"Taxon_{index + 1:03d}" for index in range(taxa)]
    base = rng.dirichlet(np.linspace(0.25, 1.4, taxa))
    matrix = np.zeros((taxa, len(samples)), dtype=int)
    for sample_index, group in enumerate(groups):
        probabilities = base.copy()
        if group == "Case":
            probabilities[:8] *= 4.5
            probabilities[8:15] *= 0.28
        else:
            probabilities[15:22] *= 2.8
        probabilities = probabilities / probabilities.sum()
        depth = int(rng.integers(18_000, 65_000))
        matrix[:, sample_index] = rng.multinomial(depth, probabilities)
    abundance = pd.DataFrame(matrix, columns=samples)
    abundance.insert(0, "taxon", taxon_names)
    metadata = pd.DataFrame({"sample": samples, "group": groups, "batch": [f"Batch_{1 + index % 2}" for index in range(len(samples))]})
    return abundance, metadata


def taxon_prevalence(frame: pd.DataFrame, *, taxon_column: str = "taxon") -> pd.DataFrame:
    abundance = validate_abundance_table(frame, taxon_column=taxon_column)
    matrix = abundance.set_index(taxon_column)
    result = pd.DataFrame(
        {
            "taxon": matrix.index,
            "prevalence_percent": (matrix.gt(0).mean(axis=1) * 100).values,
            "total_count": matrix.sum(axis=1).values,
            "mean_relative_abundance_percent": (matrix.divide(matrix.sum(axis=0), axis=1).fillna(0).mean(axis=1) * 100).values,
        }
    )
    return result.sort_values(["prevalence_percent", "mean_relative_abundance_percent"], ascending=False).reset_index(drop=True)


def core_microbiome(
    relative_frame: pd.DataFrame,
    *,
    prevalence_threshold_percent: float = 75.0,
    abundance_threshold_percent: float = 0.1,
    taxon_column: str = "taxon",
) -> pd.DataFrame:
    relative = relative_frame.set_index(taxon_column)
    prevalence = (relative >= abundance_threshold_percent / 100).mean(axis=1) * 100
    mean_abundance = relative.mean(axis=1) * 100
    result = pd.DataFrame(
        {
            "taxon": relative.index,
            "prevalence_percent": prevalence.values,
            "mean_relative_abundance_percent": mean_abundance.values,
        }
    )
    result["core_member"] = result["prevalence_percent"] >= prevalence_threshold_percent
    return result.sort_values(["core_member", "mean_relative_abundance_percent"], ascending=False).reset_index(drop=True)


def composition_long(relative_frame: pd.DataFrame, metadata: pd.DataFrame, *, top_n: int = 15) -> pd.DataFrame:
    matrix = relative_frame.set_index("taxon")
    top = matrix.mean(axis=1).sort_values(ascending=False).head(top_n).index
    collapsed = matrix.loc[top].copy()
    other = matrix.drop(index=top, errors="ignore").sum(axis=0)
    if float(other.sum()) > 0:
        collapsed.loc["Other"] = other
    long = collapsed.reset_index().melt(id_vars="taxon", var_name="sample", value_name="relative_abundance")
    long["relative_abundance_percent"] = long["relative_abundance"] * 100
    return long.merge(metadata, on="sample", how="left")


def clr_transform(relative_frame: pd.DataFrame, *, pseudocount: float = 1e-6) -> pd.DataFrame:
    matrix = relative_frame.set_index("taxon").astype(float) + pseudocount
    log_values = np.log(matrix)
    clr = log_values.subtract(log_values.mean(axis=0), axis=1)
    return clr.reset_index()


def aitchison_distance(relative_frame: pd.DataFrame) -> pd.DataFrame:
    clr = clr_transform(relative_frame).set_index("taxon").T
    samples = list(clr.index)
    distances = np.zeros((len(samples), len(samples)), dtype=float)
    values = clr.to_numpy(dtype=float)
    for left in range(len(samples)):
        for right in range(left, len(samples)):
            distance = float(np.linalg.norm(values[left] - values[right]))
            distances[left, right] = distance
            distances[right, left] = distance
    return pd.DataFrame(distances, index=samples, columns=samples)


def permanova_screen(
    distance: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    group_column: str = "group",
    permutations: int = 199,
    random_state: int = 42,
) -> dict[str, float | int]:
    if not {"sample", group_column}.issubset(metadata.columns):
        raise ValueError(f"Metadata requires sample and {group_column} columns.")
    common = [sample for sample in distance.index if sample in set(metadata["sample"].astype(str))]
    if len(common) < 4:
        raise ValueError("At least four matching samples are required.")
    labels = metadata.set_index("sample").loc[common, group_column].astype(str).to_numpy()
    values = distance.loc[common, common].to_numpy(dtype=float)

    def pseudo_f(group_labels: np.ndarray) -> float:
        n = len(group_labels)
        groups = np.unique(group_labels)
        if len(groups) < 2 or len(groups) >= n:
            return 0.0
        total_ss = float(np.square(values[np.triu_indices(n, 1)]).sum() / n)
        within_ss = 0.0
        for group in groups:
            indices = np.where(group_labels == group)[0]
            if len(indices) <= 1:
                continue
            sub = values[np.ix_(indices, indices)]
            within_ss += float(np.square(sub[np.triu_indices(len(indices), 1)]).sum() / len(indices))
        between_ss = max(total_ss - within_ss, 0.0)
        return (between_ss / max(len(groups) - 1, 1)) / max(within_ss / max(n - len(groups), 1), 1e-12)

    observed = pseudo_f(labels)
    rng = np.random.default_rng(random_state)
    permuted = np.array([pseudo_f(rng.permutation(labels)) for _ in range(max(9, int(permutations)))])
    p_value = float((1 + (permuted >= observed).sum()) / (len(permuted) + 1))
    return {
        "pseudo_f": observed,
        "permutation_p_value": p_value,
        "permutations": len(permuted),
        "samples": len(common),
        "groups": len(np.unique(labels)),
    }


def rarefaction_curve(
    frame: pd.DataFrame,
    *,
    steps: int = 12,
    replicates: int = 8,
    random_state: int = 42,
) -> pd.DataFrame:
    abundance = validate_abundance_table(frame).set_index("taxon")
    minimum_depth = int(abundance.sum(axis=0).min())
    if minimum_depth < 10:
        raise ValueError("Sample depth is too low for rarefaction screening.")
    depths = np.unique(np.linspace(max(10, minimum_depth // steps), minimum_depth, steps).astype(int))
    rng = np.random.default_rng(random_state)
    rows = []
    for sample in abundance.columns:
        counts = abundance[sample].to_numpy(dtype=int)
        total = int(counts.sum())
        for depth in depths:
            observed = []
            if int(depth) > total:
                continue
            for _ in range(replicates):
                # Classical rarefaction samples reads without replacement.
                draw = rng.multivariate_hypergeometric(counts, int(depth))
                observed.append(int((draw > 0).sum()))
            rows.append(
                {
                    "sample": sample,
                    "sampling_depth": int(depth),
                    "mean_observed_taxa": float(np.mean(observed)),
                    "sd_observed_taxa": float(np.std(observed, ddof=1)) if len(observed) > 1 else 0.0,
                }
            )
    return pd.DataFrame(rows)


def alpha_group_summary(alpha: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    merged = alpha.merge(metadata, on="sample", how="left")
    if "group" not in merged.columns:
        raise ValueError("Metadata requires a group column.")
    return merged.groupby("group", as_index=False).agg(
        samples=("sample", "size"),
        mean_observed_taxa=("observed_taxa", "mean"),
        mean_shannon=("shannon", "mean"),
        sd_shannon=("shannon", "std"),
        mean_simpson=("simpson", "mean"),
        mean_evenness=("pielou_evenness", "mean"),
    ).fillna(0)


def sample_quality_flags(qc: pd.DataFrame) -> pd.DataFrame:
    frame = qc.copy()
    depth_floor = float(frame["total_reads"].median()) * 0.25
    frame["low_depth_flag"] = frame["total_reads"] < depth_floor
    frame["dominance_flag"] = frame["dominant_taxon_percent"] > 80
    frame["sparse_flag"] = frame["zero_fraction_percent"] > 90
    frame["qc_status"] = np.where(
        frame[["low_depth_flag", "dominance_flag", "sparse_flag"]].any(axis=1), "Review", "Pass"
    )
    return frame


def differential_abundance_permutation(
    relative_frame: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    group_column: str = "group",
    group_a: str | None = None,
    group_b: str | None = None,
    permutations: int = 499,
    random_state: int = 42,
) -> pd.DataFrame:
    from biointel.projects.professional import benjamini_hochberg

    samples = [column for column in relative_frame.columns if column != "taxon"]
    design = metadata.set_index("sample").reindex(samples)
    available_groups = design[group_column].dropna().astype(str).unique().tolist()
    if group_a is None or group_b is None:
        if len(available_groups) != 2:
            raise ValueError(
                "Select explicit reference and comparison groups when metadata contains more than two groups."
            )
        group_a, group_b = available_groups
    group_a = str(group_a)
    group_b = str(group_b)
    if group_a == group_b:
        raise ValueError("Reference and comparison groups must be different.")
    missing_groups = {group_a, group_b} - set(available_groups)
    if missing_groups:
        raise ValueError("Selected groups are absent from metadata: " + ", ".join(sorted(missing_groups)))
    labels = design[group_column].astype(str).to_numpy()
    left_mask = labels == group_a
    right_mask = labels == group_b
    if left_mask.sum() < 2 or right_mask.sum() < 2:
        raise ValueError("Each selected group requires at least two samples.")
    rng = np.random.default_rng(random_state)
    records = []
    values = relative_frame[samples].astype(float).to_numpy()
    observed = values[:, left_mask].mean(axis=1) - values[:, right_mask].mean(axis=1)
    exceed = np.zeros(len(relative_frame), dtype=int)
    for _ in range(max(int(permutations), 99)):
        shuffled = rng.permutation(labels)
        perm_left = shuffled == group_a
        perm_right = shuffled == group_b
        difference = values[:, perm_left].mean(axis=1) - values[:, perm_right].mean(axis=1)
        exceed += np.abs(difference) >= np.abs(observed)
    p_values = (exceed + 1) / (max(int(permutations), 99) + 1)
    q_values = benjamini_hochberg(p_values)
    for index, taxon in enumerate(relative_frame["taxon"].astype(str)):
        left_mean = float(values[index, left_mask].mean())
        right_mean = float(values[index, right_mask].mean())
        records.append({"taxon": taxon, "group_a": group_a, "group_b": group_b, "mean_group_a": left_mean, "mean_group_b": right_mean, "difference": left_mean - right_mean, "log2_fold_change": float(np.log2((left_mean + 1e-6) / (right_mean + 1e-6))), "permutation_p_value": float(p_values[index]), "fdr_q_value": float(q_values[index]), "screening_significant": bool(q_values[index] <= 0.1)})
    return pd.DataFrame(records).sort_values(["fdr_q_value", "log2_fold_change"], ascending=[True, False]).reset_index(drop=True)


def beta_dispersion(distance: pd.DataFrame, metadata: pd.DataFrame, *, group_column: str = "group") -> pd.DataFrame:
    matrix = distance.copy()
    if matrix.shape[0] != matrix.shape[1] or list(matrix.index.astype(str)) != list(matrix.columns.astype(str)):
        first = matrix.columns[0]
        candidate = matrix.set_index(first)
        if candidate.shape[0] == candidate.shape[1]:
            matrix = candidate
    matrix.index = matrix.index.astype(str)
    matrix.columns = matrix.columns.astype(str)
    sample_ids = matrix.index.tolist()
    design = metadata.set_index("sample").reindex(sample_ids)
    coordinates, _ = pcoa(matrix)
    coordinate_columns = [column for column in coordinates.columns if column.startswith("PCoA")]
    coordinate_frame = coordinates.set_index("sample")[coordinate_columns]
    rows = []
    for group, group_frame in design.groupby(group_column, dropna=False):
        members = [sample for sample in group_frame.index.astype(str) if sample in matrix.columns]
        if len(members) < 2:
            continue
        group_coordinates = coordinate_frame.loc[members].astype(float)
        centroid = group_coordinates.mean(axis=0)
        centroid_distance = np.sqrt(np.square(group_coordinates - centroid).sum(axis=1))
        for sample, value in centroid_distance.items():
            rows.append(
                {
                    "sample_id": sample,
                    group_column: group,
                    "distance_to_group_centroid": float(value),
                    # Backwards-compatible alias retained for existing reports and pages.
                    "distance_to_group_centroid_proxy": float(value),
                    "method": "PCoA coordinate distance to group centroid",
                }
            )
    return pd.DataFrame(rows)


def beta_dispersion_permutation_test(
    dispersion: pd.DataFrame,
    *,
    group_column: str = "group",
    permutations: int = 999,
    random_state: int = 42,
) -> dict[str, float | int]:
    """Permutation ANOVA screen for differences in distance-to-centroid dispersion."""
    required = {group_column, "distance_to_group_centroid"}
    if not required.issubset(dispersion.columns):
        raise ValueError("Dispersion table is missing group or centroid-distance columns.")
    frame = dispersion[[group_column, "distance_to_group_centroid"]].dropna().copy()
    groups = frame[group_column].astype(str).to_numpy()
    values = frame["distance_to_group_centroid"].astype(float).to_numpy()
    unique = np.unique(groups)
    if len(unique) < 2 or any((groups == group).sum() < 2 for group in unique):
        raise ValueError("Dispersion testing requires at least two groups with two samples each.")

    def f_statistic(labels: np.ndarray) -> float:
        grand = float(values.mean())
        between = sum((labels == group).sum() * (float(values[labels == group].mean()) - grand) ** 2 for group in np.unique(labels))
        within = sum(float(np.square(values[labels == group] - values[labels == group].mean()).sum()) for group in np.unique(labels))
        return (between / max(len(np.unique(labels)) - 1, 1)) / max(within / max(len(values) - len(np.unique(labels)), 1), 1e-12)

    observed = f_statistic(groups)
    rng = np.random.default_rng(random_state)
    permutation_count = max(int(permutations), 99)
    permuted = np.array([f_statistic(rng.permutation(groups)) for _ in range(permutation_count)])
    p_value = float((1 + int((permuted >= observed).sum())) / (permutation_count + 1))
    return {
        "f_statistic": float(observed),
        "permutation_p_value": p_value,
        "permutations": permutation_count,
        "samples": int(len(values)),
        "groups": int(len(unique)),
    }


def indicator_taxa(relative_frame: pd.DataFrame, metadata: pd.DataFrame, *, group_column: str = "group") -> pd.DataFrame:
    samples = [column for column in relative_frame.columns if column != "taxon"]
    design = metadata.set_index("sample").reindex(samples)
    groups = design[group_column].dropna().astype(str).unique().tolist()
    records = []
    for row in relative_frame.itertuples(index=False):
        values = pd.Series({sample: float(getattr(row, sample)) for sample in samples})
        group_means = {group: float(values[[sample for sample in samples if str(design.loc[sample, group_column]) == group]].mean()) for group in groups}
        group_prevalence = {group: float((values[[sample for sample in samples if str(design.loc[sample, group_column]) == group]] > 0).mean()) for group in groups}
        best = max(groups, key=lambda group: group_means[group] * group_prevalence[group]) if groups else ""
        score = group_means.get(best, 0.0) * group_prevalence.get(best, 0.0)
        records.append({"taxon": str(getattr(row, "taxon")), "indicator_group": best, "indicator_score": score, "mean_relative_abundance": group_means.get(best, 0.0), "prevalence": group_prevalence.get(best, 0.0)})
    return pd.DataFrame(records).sort_values("indicator_score", ascending=False).reset_index(drop=True)


def prevalence_sensitivity(
    frame: pd.DataFrame,
    *,
    taxon_column: str = "taxon",
    thresholds: tuple[float, ...] = (0.05, 0.1, 0.2, 0.3, 0.5),
) -> pd.DataFrame:
    cleaned = validate_abundance_table(frame, taxon_column=taxon_column)
    samples = [column for column in cleaned.columns if column != taxon_column]
    rows = []
    for threshold in thresholds:
        prevalence = (cleaned[samples] > 0).mean(axis=1)
        retained = cleaned[prevalence >= threshold]
        rows.append({"minimum_prevalence": threshold, "retained_taxa": len(retained), "removed_taxa": len(cleaned) - len(retained), "retained_total_counts_percent": 100 * float(retained[samples].sum().sum()) / max(float(cleaned[samples].sum().sum()), 1.0)})
    return pd.DataFrame(rows)


def leave_one_out_pcoa_stability(distance: pd.DataFrame) -> pd.DataFrame:
    matrix = distance.copy()
    if matrix.shape[0] != matrix.shape[1] or list(matrix.index.astype(str)) != list(matrix.columns.astype(str)):
        first = matrix.columns[0]
        candidate = matrix.set_index(first)
        if candidate.shape[0] == candidate.shape[1]:
            matrix = candidate
    matrix.index = matrix.index.astype(str)
    matrix.columns = matrix.columns.astype(str)
    full_coordinates, _ = pcoa(matrix)
    identifier = full_coordinates.columns[0]
    base = full_coordinates.set_index(identifier)[[column for column in full_coordinates.columns if column.startswith("PC")][:2]]
    rows = []
    for omitted in matrix.index.astype(str):
        remaining = [sample for sample in matrix.index.astype(str) if sample != omitted]
        subset = matrix.loc[remaining, remaining]
        try:
            coordinates, _ = pcoa(subset)
            current = coordinates.set_index(coordinates.columns[0])[[column for column in coordinates.columns if column.startswith("PC")][:2]]
            common = base.index.intersection(current.index)
            if len(common) < 3:
                continue
            left = base.loc[common].to_numpy()
            right = current.loc[common].to_numpy()
            left_dist = np.sqrt(((left[:, None, :] - left[None, :, :]) ** 2).sum(axis=2))
            right_dist = np.sqrt(((right[:, None, :] - right[None, :, :]) ** 2).sum(axis=2))
            correlation = float(np.corrcoef(left_dist.ravel(), right_dist.ravel())[0, 1])
            rows.append({"omitted_sample": omitted, "pairwise_geometry_correlation": correlation, "remaining_samples": len(common)})
        except Exception:
            continue
    return pd.DataFrame(rows)
