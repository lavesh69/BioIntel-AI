from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ExpressionSummary:
    genes: int
    samples: int
    total_counts: float
    zero_fraction: float
    minimum_library_size: float
    maximum_library_size: float
    median_library_size: float


def validate_count_matrix(
    frame: pd.DataFrame, gene_column: str = "gene"
) -> tuple[pd.Series, pd.DataFrame]:
    if gene_column not in frame.columns:
        raise ValueError(f"Missing gene column {gene_column!r}.")
    genes = frame[gene_column].astype(str).str.strip()
    if genes.eq("").any():
        raise ValueError("Gene identifiers cannot be empty.")
    if genes.duplicated().any():
        raise ValueError("Gene identifiers must be unique.")
    sample_columns = [str(column).strip() for column in frame.columns if column != gene_column]
    if len(sample_columns) < 2:
        raise ValueError("Expression matrix requires at least two sample columns.")
    if any(not column for column in sample_columns) or len(set(sample_columns)) != len(sample_columns):
        raise ValueError("Sample column names must be non-empty and unique.")
    counts = frame.drop(columns=[gene_column]).copy()
    counts.columns = sample_columns
    counts = counts.apply(pd.to_numeric, errors="coerce")
    values = counts.to_numpy(dtype=float)
    if counts.isna().any().any() or not np.all(np.isfinite(values)):
        raise ValueError("Expression matrix contains non-numeric, missing or non-finite values.")
    if (values < 0).any():
        raise ValueError("Expression counts cannot be negative.")
    zero_libraries = counts.columns[counts.sum(axis=0) <= 0].tolist()
    if zero_libraries:
        raise ValueError("Every sample requires positive total expression: " + ", ".join(zero_libraries[:8]))
    return genes, counts


def collapse_duplicate_genes(
    frame: pd.DataFrame,
    *,
    gene_column: str = "gene",
    method: str = "sum",
) -> tuple[pd.DataFrame, dict[str, int | str]]:
    """Collapse duplicate gene identifiers before validation using an explicit rule."""

    if gene_column not in frame.columns:
        raise ValueError(f"Missing gene column {gene_column!r}.")
    prepared = frame.copy()
    prepared[gene_column] = prepared[gene_column].astype(str).str.strip()
    if (prepared[gene_column] == "").any():
        raise ValueError("Gene identifiers cannot be empty.")
    value_columns = [column for column in prepared.columns if column != gene_column]
    prepared[value_columns] = prepared[value_columns].apply(pd.to_numeric, errors="coerce")
    if prepared[value_columns].isna().any().any():
        raise ValueError("Expression matrix contains non-numeric or missing values.")
    duplicate_rows = int(prepared[gene_column].duplicated(keep=False).sum())
    duplicate_ids = int(prepared.loc[prepared[gene_column].duplicated(keep=False), gene_column].nunique())
    normalized_method = str(method).strip().lower()
    if normalized_method not in {"sum", "mean", "max"}:
        raise ValueError("Duplicate-gene method must be sum, mean or max.")
    if duplicate_ids:
        grouped = prepared.groupby(gene_column, as_index=False, sort=False)[value_columns]
        collapsed = getattr(grouped, normalized_method)()
    else:
        collapsed = prepared.reset_index(drop=True)
    report: dict[str, int | str] = {
        "method": normalized_method,
        "input_rows": int(len(prepared)),
        "output_rows": int(len(collapsed)),
        "duplicate_rows": duplicate_rows,
        "duplicate_gene_ids": duplicate_ids,
    }
    return collapsed, report


def expression_summary(frame: pd.DataFrame, gene_column: str = "gene") -> ExpressionSummary:
    _, counts = validate_count_matrix(frame, gene_column)
    libraries = counts.sum(axis=0)
    return ExpressionSummary(
        len(counts),
        counts.shape[1],
        float(counts.to_numpy().sum()),
        round(float((counts == 0).to_numpy().mean()), 4),
        float(libraries.min()),
        float(libraries.max()),
        float(libraries.median()),
    )


def normalize_cpm(
    frame: pd.DataFrame, gene_column: str = "gene", log_transform: bool = True
) -> pd.DataFrame:
    genes, counts = validate_count_matrix(frame, gene_column)
    libraries = counts.sum(axis=0).replace(0, np.nan)
    normalized = counts.divide(libraries, axis=1) * 1_000_000
    if log_transform:
        normalized = np.log2(normalized + 1)
    return pd.concat([genes.rename(gene_column), normalized], axis=1)


def median_ratio_normalize(frame: pd.DataFrame, gene_column: str = "gene") -> pd.DataFrame:
    genes, counts = validate_count_matrix(frame, gene_column)
    array = counts.to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        log_values = np.where(array > 0, np.log(array), np.nan)
        geometric = np.exp(np.nanmean(log_values, axis=1))
    valid = geometric > 0
    ratios = np.where(valid[:, None], array / geometric[:, None], np.nan)
    factors = np.nanmedian(ratios, axis=0)
    factors = np.where((factors > 0) & np.isfinite(factors), factors, 1)
    normalized = counts.divide(factors, axis=1)
    return pd.concat([genes.rename(gene_column), normalized], axis=1)


def filter_low_count_genes(
    frame: pd.DataFrame,
    *,
    gene_column: str = "gene",
    minimum_count: float = 10.0,
    minimum_samples: int = 2,
) -> pd.DataFrame:
    """Remove genes that do not reach a minimum count in enough samples."""
    genes, counts = validate_count_matrix(frame, gene_column)
    if minimum_count < 0 or minimum_samples < 1:
        raise ValueError("Low-count filter thresholds must be non-negative and use at least one sample.")
    keep = (counts >= float(minimum_count)).sum(axis=1) >= int(minimum_samples)
    if not bool(keep.any()):
        raise ValueError("No genes remain after low-count filtering. Relax the thresholds.")
    return pd.concat([genes.loc[keep].rename(gene_column), counts.loc[keep]], axis=1).reset_index(drop=True)


def _fdr_bh(p_values: np.ndarray) -> np.ndarray:
    p = np.asarray(p_values, dtype=float)
    p = np.where(np.isfinite(p), np.clip(p, 0, 1), 1.0)
    order = np.argsort(p)
    adjusted = np.empty_like(p)
    running = 1.0
    for rank, index in reversed(list(enumerate(order, 1))):
        running = min(running, p[index] * len(p) / rank)
        adjusted[index] = running
    return np.clip(adjusted, 0, 1)


def differential_expression(
    frame: pd.DataFrame,
    groups: dict[str, str],
    *,
    gene_column: str = "gene",
    group_a: str | None = None,
    group_b: str | None = None,
    pseudocount: float = 1.0,
    values_are_log2: bool = False,
    batches: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Run a transparent two-group expression screen.

    The function supports either a Welch test (no batch supplied) or a batch-adjusted
    ordinary least-squares coefficient test. It remains an exploratory screen rather
    than a replacement for a count-aware RNA-seq method such as DESeq2 or edgeR.
    """
    genes, values = validate_count_matrix(frame, gene_column)
    labels = sorted({str(value) for value in groups.values()})
    if len(labels) < 2 and (group_a is None or group_b is None):
        raise ValueError("At least two groups are required.")
    group_a = str(group_a or labels[0])
    group_b = str(group_b or labels[1])
    if group_a == group_b:
        raise ValueError("Reference and comparison groups must be different.")
    selected_samples = [
        column for column in values.columns if str(groups.get(column, "")) in {group_a, group_b}
    ]
    a = [column for column in selected_samples if str(groups.get(column)) == group_a]
    b = [column for column in selected_samples if str(groups.get(column)) == group_b]
    if len(a) < 2 or len(b) < 2:
        raise ValueError("Each selected group requires at least two samples.")

    selected = values[selected_samples].astype(float)
    analysis_values = selected if values_are_log2 else np.log2(selected + float(pseudocount))
    mean_a = selected[a].mean(axis=1)
    mean_b = selected[b].mean(axis=1)
    if values_are_log2:
        log2_fold_change = analysis_values[b].mean(axis=1) - analysis_values[a].mean(axis=1)
    else:
        log2_fold_change = np.log2((mean_b + pseudocount) / (mean_a + pseudocount))

    usable_batches = None
    if batches:
        usable_batches = {sample: str(batches.get(sample, "")) for sample in selected_samples}
        if len(set(usable_batches.values())) < 2:
            usable_batches = None

    if usable_batches:
        sample_groups = np.array([1.0 if groups[sample] == group_b else 0.0 for sample in selected_samples])
        batch_labels = [usable_batches[sample] for sample in selected_samples]
        batch_levels = list(dict.fromkeys(batch_labels))
        design_columns = [np.ones(len(selected_samples)), sample_groups]
        for level in batch_levels[1:]:
            design_columns.append(np.array([1.0 if value == level else 0.0 for value in batch_labels]))
        design = np.column_stack(design_columns)
        if np.linalg.matrix_rank(design) < design.shape[1] or len(selected_samples) <= design.shape[1]:
            raise ValueError("The group and batch design is rank-deficient; revise sample assignments.")
        response = analysis_values.to_numpy(dtype=float).T
        inverse = np.linalg.pinv(design.T @ design)
        beta = inverse @ design.T @ response
        residual = response - design @ beta
        degrees_freedom = len(selected_samples) - design.shape[1]
        residual_variance = np.square(residual).sum(axis=0) / max(degrees_freedom, 1)
        standard_error = np.sqrt(np.maximum(residual_variance * inverse[1, 1], 0))
        statistic = np.divide(beta[1], standard_error, out=np.zeros_like(beta[1]), where=standard_error > 0)
        try:
            from scipy.stats import t as student_t

            p = 2 * student_t.sf(np.abs(statistic), df=max(degrees_freedom, 1))
        except Exception:
            p = np.array(
                [min(1.0, np.exp(-0.717 * abs(value) - 0.416 * value * value)) for value in statistic]
            )
        effect = pd.Series(beta[1], index=values.index)
        method = "batch-adjusted linear model on log2 scale"
        log2_fold_change = effect
    else:
        try:
            from scipy.stats import ttest_ind

            test = ttest_ind(
                analysis_values[b].to_numpy(float),
                analysis_values[a].to_numpy(float),
                axis=1,
                equal_var=False,
                nan_policy="omit",
            )
            statistic = np.asarray(test.statistic, dtype=float)
            p = np.asarray(test.pvalue, dtype=float)
            statistic = np.where(np.isfinite(statistic), statistic, 0.0)
            p = np.where(np.isfinite(p), p, 1.0)
            method = "Welch t-test on log2-normalized values"
        except Exception:
            var_a = analysis_values[a].var(axis=1, ddof=1)
            var_b = analysis_values[b].var(axis=1, ddof=1)
            se = np.sqrt(var_a / len(a) + var_b / len(b)).replace(0, np.nan)
            statistic = ((analysis_values[b].mean(axis=1) - analysis_values[a].mean(axis=1)) / se).fillna(0).to_numpy()
            p = np.array(
                [min(1.0, np.exp(-0.717 * abs(value) - 0.416 * value * value)) for value in statistic]
            )
            method = "normal-approximation screen on log2-normalized values"

    adjusted = _fdr_bh(np.asarray(p, dtype=float))
    return (
        pd.DataFrame(
            {
                "gene": genes,
                "mean_" + group_a: mean_a,
                "mean_" + group_b: mean_b,
                "log2_fold_change": np.asarray(log2_fold_change, dtype=float),
                "test_statistic": np.asarray(statistic, dtype=float),
                "p_value": np.asarray(p, dtype=float),
                "fdr_bh": adjusted,
                "test_method": method,
                "reference_group": group_a,
                "comparison_group": group_b,
                "batch_adjusted": bool(usable_batches),
            }
        )
        .sort_values("fdr_bh")
        .reset_index(drop=True)
    )

def pca_samples(
    frame: pd.DataFrame,
    gene_column: str = "gene",
    components: int = 2,
    *,
    values_are_log2: bool = False,
) -> pd.DataFrame:
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    _, counts = validate_count_matrix(frame, gene_column)
    matrix = counts.T if values_are_log2 else np.log2(counts.T + 1)
    n = min(components, matrix.shape[0], matrix.shape[1])
    transformed = PCA(n_components=n, random_state=42).fit_transform(
        StandardScaler().fit_transform(matrix)
    )
    output = pd.DataFrame(
        transformed, index=counts.columns, columns=[f"PC{i + 1}" for i in range(n)]
    )
    output.insert(0, "sample", output.index)
    return output.reset_index(drop=True)


def summary_dict(result):
    return asdict(result)
