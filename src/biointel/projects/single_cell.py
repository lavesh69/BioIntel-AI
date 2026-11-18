from __future__ import annotations

from dataclasses import dataclass
from gzip import GzipFile
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SingleCellResult:
    qc: pd.DataFrame
    filtered_counts: pd.DataFrame
    normalized: pd.DataFrame
    variable_genes: pd.DataFrame
    embedding: pd.DataFrame
    markers: pd.DataFrame
    summary: dict[str, float | int]


def _read_zip_member(archive: ZipFile, name: str) -> bytes:
    raw = archive.read(name)
    return GzipFile(fileobj=BytesIO(raw)).read() if name.lower().endswith(".gz") else raw


def parse_10x_mtx_bundle(
    payload: bytes,
    *,
    maximum_dense_cells: int = 2_000_000,
    maximum_member_count: int = 100,
    maximum_uncompressed_bytes: int = 512 * 1024 * 1024,
    maximum_compression_ratio: float = 250.0,
) -> pd.DataFrame:
    """Parse a safe 10x Matrix Market ZIP into the genes-by-cells table used by the UI.

    The interactive workbench is dense by design, so bundles whose gene-by-cell product
    exceeds ``maximum_dense_cells`` are rejected with an actionable message rather than
    silently exhausting memory. Large studies should use a sparse H5AD/Scanpy workflow.
    """

    if not payload:
        raise ValueError("10x bundle is empty.")
    try:
        archive = ZipFile(BytesIO(payload))
    except BadZipFile as exc:
        raise ValueError("10x input must be a valid ZIP archive.") from exc
    with archive:
        members = archive.infolist()
        if len(members) > int(maximum_member_count):
            raise ValueError(
                f"10x ZIP contains {len(members):,} members; the interactive limit is {int(maximum_member_count):,}."
            )
        total_uncompressed = sum(max(0, int(member.file_size)) for member in members)
        if total_uncompressed > int(maximum_uncompressed_bytes):
            raise ValueError(
                f"10x ZIP expands to {total_uncompressed / (1024 * 1024):.1f} MB, exceeding the safe interactive limit."
            )
        for member in members:
            compressed = max(1, int(member.compress_size))
            ratio = float(member.file_size) / compressed
            if member.file_size > 1024 * 1024 and ratio > float(maximum_compression_ratio):
                raise ValueError("10x ZIP contains a suspiciously compressed member.")

        safe_names: list[str] = []
        for member in archive.namelist():
            path = PurePosixPath(member)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("10x ZIP contains an unsafe path.")
            if not member.endswith("/"):
                safe_names.append(member)
        lowered = {name.lower(): name for name in safe_names}

        def find_one(candidates: tuple[str, ...]) -> str:
            matches = [
                original
                for lower, original in lowered.items()
                if any(lower.endswith(candidate) for candidate in candidates)
            ]
            if len(matches) != 1:
                raise ValueError(
                    "10x ZIP must contain exactly one matching file for: " + ", ".join(candidates)
                )
            return matches[0]

        matrix_name = find_one(("matrix.mtx", "matrix.mtx.gz"))
        feature_name = find_one(("features.tsv", "features.tsv.gz", "genes.tsv", "genes.tsv.gz"))
        barcode_name = find_one(("barcodes.tsv", "barcodes.tsv.gz"))

        from scipy.io import mmread

        matrix_bytes = _read_zip_member(archive, matrix_name)
        matrix = mmread(BytesIO(matrix_bytes)).tocsr()
        feature_lines = _read_zip_member(archive, feature_name).decode("utf-8-sig", errors="replace").splitlines()
        barcode_lines = _read_zip_member(archive, barcode_name).decode("utf-8-sig", errors="replace").splitlines()
        features = [line.split("\t") for line in feature_lines if line.strip()]
        barcodes = [line.split("\t")[0].strip() for line in barcode_lines if line.strip()]
        if not features or not barcodes:
            raise ValueError("10x ZIP contains empty feature or barcode files.")
        genes = [
            (parts[1].strip() if len(parts) > 1 and parts[1].strip() else parts[0].strip())
            for parts in features
        ]
        if matrix.shape == (len(barcodes), len(genes)):
            matrix = matrix.T.tocsr()
        if matrix.shape != (len(genes), len(barcodes)):
            raise ValueError(
                f"10x matrix shape {matrix.shape} does not match {len(genes)} features and {len(barcodes)} barcodes."
            )
        dense_cells = int(matrix.shape[0] * matrix.shape[1])
        if dense_cells > int(maximum_dense_cells):
            raise ValueError(
                f"10x bundle contains {matrix.shape[0]:,} genes × {matrix.shape[1]:,} cells. "
                "This exceeds the dense interactive limit; use the sparse Scanpy/H5AD workflow."
            )
        if len(set(barcodes)) != len(barcodes):
            raise ValueError("10x barcodes must be unique.")
        unique_genes: list[str] = []
        seen: dict[str, int] = {}
        for gene in genes:
            base = gene or "unnamed_gene"
            seen[base] = seen.get(base, 0) + 1
            unique_genes.append(base if seen[base] == 1 else f"{base}__{seen[base]}")
        frame = pd.DataFrame.sparse.from_spmatrix(matrix, index=unique_genes, columns=barcodes)
        frame = frame.sparse.to_dense().reset_index(names="gene")
        return validate_count_matrix(frame)


def validate_count_matrix(frame: pd.DataFrame, *, gene_column: str = "gene") -> pd.DataFrame:
    if gene_column not in frame.columns:
        raise ValueError(f"Count matrix must include a '{gene_column}' column.")
    counts = frame.copy()
    counts[gene_column] = counts[gene_column].astype(str).str.strip()
    if (counts[gene_column] == "").any() or counts[gene_column].duplicated().any():
        raise ValueError("Gene identifiers must be non-empty and unique.")
    cell_columns = [str(column).strip() for column in counts.columns if column != gene_column]
    if len(cell_columns) < 6:
        raise ValueError("At least six cells are required for single-cell analysis.")
    if any(not column for column in cell_columns) or len(set(cell_columns)) != len(cell_columns):
        raise ValueError("Cell identifiers must be non-empty and unique.")
    numeric = counts.drop(columns=[gene_column]).copy()
    numeric.columns = cell_columns
    numeric = numeric.apply(pd.to_numeric, errors="coerce")
    values = numeric.to_numpy(dtype=float)
    if numeric.isna().any().any() or not np.all(np.isfinite(values)):
        raise ValueError("All expression values must be numeric and finite.")
    if (values < 0).any():
        raise ValueError("Count values cannot be negative.")
    if float(values.sum()) <= 0:
        raise ValueError("Count matrix contains no reads/UMIs.")
    empty_cells = numeric.columns[numeric.sum(axis=0) <= 0].tolist()
    if empty_cells:
        raise ValueError("Cells with zero total counts must be removed: " + ", ".join(empty_cells[:8]))
    counts[cell_columns] = numeric.astype(float)
    return counts


def cell_qc(frame: pd.DataFrame, *, gene_column: str = "gene") -> pd.DataFrame:
    counts = validate_count_matrix(frame, gene_column=gene_column)
    matrix = counts.set_index(gene_column)
    totals = matrix.sum(axis=0)
    detected = (matrix > 0).sum(axis=0)
    mitochondrial_mask = matrix.index.to_series().str.upper().str.startswith(("MT-", "MT_", "MITO"))
    mitochondrial = matrix.loc[mitochondrial_mask].sum(axis=0) if mitochondrial_mask.any() else pd.Series(0.0, index=matrix.columns)
    ribosomal_mask = matrix.index.to_series().str.upper().str.startswith(("RPL", "RPS"))
    ribosomal = matrix.loc[ribosomal_mask].sum(axis=0) if ribosomal_mask.any() else pd.Series(0.0, index=matrix.columns)
    qc = pd.DataFrame(
        {
            "cell": matrix.columns,
            "total_counts": totals.values,
            "detected_genes": detected.values,
            "mitochondrial_percent": (mitochondrial / totals.replace(0, np.nan) * 100).fillna(0).values,
            "ribosomal_percent": (ribosomal / totals.replace(0, np.nan) * 100).fillna(0).values,
        }
    )
    qc["log10_counts"] = np.log10(qc["total_counts"].clip(lower=1))
    return qc


def normalize_log1p(frame: pd.DataFrame, *, gene_column: str = "gene", scale_factor: float = 10_000.0) -> pd.DataFrame:
    counts = validate_count_matrix(frame, gene_column=gene_column)
    matrix = counts.set_index(gene_column)
    normalized = matrix.divide(matrix.sum(axis=0).replace(0, np.nan), axis=1) * scale_factor
    normalized = np.log1p(normalized.fillna(0))
    return normalized.reset_index()


def highly_variable_genes(normalized: pd.DataFrame, *, gene_column: str = "gene", top_n: int = 500) -> pd.DataFrame:
    matrix = normalized.set_index(gene_column)
    mean = matrix.mean(axis=1)
    variance = matrix.var(axis=1, ddof=1)
    dispersion = variance / mean.replace(0, np.nan)
    result = pd.DataFrame(
        {
            "gene": matrix.index,
            "mean_expression": mean.values,
            "variance": variance.values,
            "dispersion": dispersion.replace([np.inf, -np.inf], np.nan).fillna(0).values,
        }
    )
    top_n = max(10, min(int(top_n), len(result)))
    result = result.sort_values(["dispersion", "variance"], ascending=False).reset_index(drop=True)
    result["highly_variable"] = False
    result.loc[: top_n - 1, "highly_variable"] = True
    return result


def cluster_cells(
    normalized: pd.DataFrame,
    variable_genes: pd.DataFrame,
    *,
    n_clusters: int = 4,
    random_state: int = 42,
    gene_column: str = "gene",
) -> tuple[pd.DataFrame, dict[str, float]]:
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    selected = variable_genes.loc[variable_genes["highly_variable"], "gene"].astype(str).tolist()
    if not selected:
        raise ValueError("No highly variable genes are available for clustering.")
    matrix = normalized.set_index(gene_column).loc[selected].T
    matrix = matrix.loc[:, matrix.std(axis=0, ddof=0) > 1e-12]
    if matrix.shape[1] < 2:
        raise ValueError("Clustering requires at least two variable, non-constant genes.")
    if len(matrix) < n_clusters * 2:
        raise ValueError("Use fewer clusters or provide more cells.")
    standardized = StandardScaler().fit_transform(matrix)
    components = max(2, min(20, standardized.shape[0] - 1, standardized.shape[1]))
    pca = PCA(n_components=components, random_state=random_state)
    scores = pca.fit_transform(standardized)
    model = KMeans(n_clusters=n_clusters, n_init=20, random_state=random_state)
    labels = model.fit_predict(scores[:, : min(10, scores.shape[1])])
    embedding = pd.DataFrame(
        {
            "cell": matrix.index,
            "PC1": scores[:, 0],
            "PC2": scores[:, 1],
            "cluster": [f"Cluster {label + 1}" for label in labels],
        }
    )
    if scores.shape[1] > 2:
        embedding["PC3"] = scores[:, 2]
    silhouette = float(silhouette_score(scores[:, : min(10, scores.shape[1])], labels)) if len(set(labels)) > 1 else 0.0
    metrics = {
        "variance_pc1": float(pca.explained_variance_ratio_[0]),
        "variance_pc2": float(pca.explained_variance_ratio_[1]),
        "silhouette": silhouette,
    }
    return embedding, metrics


def find_cluster_markers(
    normalized: pd.DataFrame,
    embedding: pd.DataFrame,
    *,
    gene_column: str = "gene",
    top_n_per_cluster: int = 12,
) -> pd.DataFrame:
    from scipy.stats import ttest_ind

    from biointel.projects.professional import benjamini_hochberg

    matrix = normalized.set_index(gene_column)
    cluster_map = embedding.set_index("cell")["cluster"]
    rows = []
    for cluster in sorted(cluster_map.unique()):
        in_cells = cluster_map[cluster_map == cluster].index.tolist()
        out_cells = cluster_map[cluster_map != cluster].index.tolist()
        in_mean = matrix[in_cells].mean(axis=1)
        out_mean = matrix[out_cells].mean(axis=1) if out_cells else pd.Series(0.0, index=matrix.index)
        log2_fc = (in_mean - out_mean) / np.log(2)
        pct_in = (matrix[in_cells] > 0).mean(axis=1)
        pct_out = (matrix[out_cells] > 0).mean(axis=1) if out_cells else pd.Series(0.0, index=matrix.index)
        score = log2_fc * (pct_in - pct_out).clip(lower=0)
        if out_cells:
            _, p_values = ttest_ind(
                matrix[in_cells].to_numpy(dtype=float),
                matrix[out_cells].to_numpy(dtype=float),
                axis=1,
                equal_var=False,
                nan_policy="omit",
            )
            p_values = np.nan_to_num(p_values, nan=1.0, posinf=1.0, neginf=1.0)
        else:
            p_values = np.ones(len(matrix), dtype=float)
        q_values = benjamini_hochberg(p_values)
        ranked = pd.DataFrame(
            {
                "cluster": cluster,
                "gene": matrix.index,
                "mean_in_cluster": in_mean.values,
                "mean_outside": out_mean.values,
                "log2_fold_change": log2_fc.values,
                "detected_in_percent": (pct_in * 100).values,
                "detected_out_percent": (pct_out * 100).values,
                "marker_score": score.values,
                "welch_p_value": p_values,
                "fdr_q_value": q_values,
            }
        ).sort_values(["fdr_q_value", "marker_score", "log2_fold_change"], ascending=[True, False, False])
        rows.append(ranked.head(top_n_per_cluster))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def run_single_cell_pipeline(
    frame: pd.DataFrame,
    *,
    min_counts: float = 300,
    min_genes: int = 100,
    max_mito_percent: float = 20.0,
    top_variable_genes: int = 500,
    n_clusters: int = 4,
    random_state: int = 42,
    exclude_doublets: bool = False,
) -> SingleCellResult:
    counts = validate_count_matrix(frame)
    qc = cell_qc(counts)
    doublets = estimate_doublet_scores(qc)
    qc = qc.merge(doublets[["cell", "doublet_score", "doublet_flag"]], on="cell", how="left")
    qc["pass_qc"] = (
        (qc["total_counts"] >= min_counts)
        & (qc["detected_genes"] >= min_genes)
        & (qc["mitochondrial_percent"] <= max_mito_percent)
    )
    if exclude_doublets:
        qc["pass_qc"] &= ~qc["doublet_flag"].fillna(False)
    passing_cells = qc.loc[qc["pass_qc"], "cell"].tolist()
    if len(passing_cells) < max(8, n_clusters * 2):
        raise ValueError("Too few cells pass QC. Relax thresholds or provide a larger matrix.")
    filtered = counts[["gene", *passing_cells]].copy()
    normalized = normalize_log1p(filtered)
    variable = highly_variable_genes(normalized, top_n=top_variable_genes)
    embedding, metrics = cluster_cells(
        normalized,
        variable,
        n_clusters=n_clusters,
        random_state=random_state,
    )
    markers = find_cluster_markers(normalized, embedding)
    summary: dict[str, float | int] = {
        "input_cells": len(qc),
        "retained_cells": len(passing_cells),
        "retention_percent": len(passing_cells) / len(qc) * 100,
        "genes": len(filtered),
        "clusters": int(embedding["cluster"].nunique()),
        "silhouette": metrics["silhouette"],
        "pc1_variance_percent": metrics["variance_pc1"] * 100,
        "pc2_variance_percent": metrics["variance_pc2"] * 100,
        "doublets_flagged": int(qc["doublet_flag"].sum()),
        "doublets_excluded": int((qc["doublet_flag"] & ~qc["pass_qc"]).sum()) if exclude_doublets else 0,
    }
    return SingleCellResult(qc, filtered, normalized, variable, embedding, markers, summary)


def demo_single_cell_counts(
    *,
    genes: int = 700,
    cells: int = 180,
    clusters: int = 4,
    random_state: int = 23,
) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    gene_names = [f"GENE_{index + 1:04d}" for index in range(genes)]
    mitochondrial = [f"MT-GENE{index + 1}" for index in range(12)]
    ribosomal = [f"RPL{index + 1}" for index in range(18)]
    gene_names[: len(mitochondrial)] = mitochondrial
    gene_names[len(mitochondrial) : len(mitochondrial) + len(ribosomal)] = ribosomal
    assignments = np.arange(cells) % clusters
    base = rng.gamma(shape=0.8, scale=1.4, size=(genes, 1))
    matrix = np.zeros((genes, cells), dtype=int)
    marker_block = max(20, genes // (clusters * 8))
    for cell in range(cells):
        library = float(rng.lognormal(mean=7.2, sigma=0.32))
        rates = base[:, 0].copy()
        cluster = int(assignments[cell])
        start = 40 + cluster * marker_block
        rates[start : start + marker_block] *= 7.5
        if cell % 29 == 0:
            rates[:12] *= 8.0
            library *= 0.45
        probabilities = rates / rates.sum()
        matrix[:, cell] = rng.multinomial(max(200, int(library)), probabilities)
    frame = pd.DataFrame(matrix, columns=[f"CELL_{index + 1:04d}" for index in range(cells)])
    frame.insert(0, "gene", gene_names)
    return frame


def estimate_doublet_scores(qc: pd.DataFrame) -> pd.DataFrame:
    required = {"cell", "total_counts", "detected_genes"}
    if not required.issubset(qc.columns):
        raise ValueError("QC table requires cell, total_counts and detected_genes.")
    frame = qc.copy()
    for column in ("total_counts", "detected_genes"):
        median = float(frame[column].median())
        mad = float((frame[column] - median).abs().median()) or 1.0
        frame[f"{column}_robust_z"] = 0.6745 * (frame[column] - median) / mad
    frame["doublet_score"] = (
        0.55 * frame["total_counts_robust_z"].clip(lower=0)
        + 0.45 * frame["detected_genes_robust_z"].clip(lower=0)
    )
    frame["doublet_flag"] = frame["doublet_score"] >= 3.0
    return frame[["cell", "doublet_score", "doublet_flag", "total_counts_robust_z", "detected_genes_robust_z"]]


def cluster_stability(
    normalized: pd.DataFrame,
    variable_genes: pd.DataFrame,
    *,
    n_clusters: int,
    random_seeds: list[int] | tuple[int, ...] = (11, 23, 37, 53, 71),
) -> pd.DataFrame:
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.metrics import adjusted_rand_score
    from sklearn.preprocessing import StandardScaler

    selected = variable_genes.loc[variable_genes["highly_variable"], "gene"].astype(str).tolist()
    matrix = normalized.set_index("gene").loc[selected].T
    if len(matrix) < n_clusters * 2:
        raise ValueError("Use fewer clusters or provide more cells.")
    standardized = StandardScaler().fit_transform(matrix)
    components = max(2, min(15, standardized.shape[0] - 1, standardized.shape[1]))
    scores = PCA(n_components=components, random_state=int(random_seeds[0])).fit_transform(standardized)
    compact = scores[:, : min(10, scores.shape[1])]
    assignments: list[tuple[int, np.ndarray]] = []
    for seed in random_seeds:
        labels = KMeans(n_clusters=n_clusters, n_init=5, random_state=int(seed)).fit_predict(compact)
        assignments.append((int(seed), labels))
    reference_seed, reference = assignments[0]
    return pd.DataFrame(
        [
            {
                "reference_seed": reference_seed,
                "comparison_seed": seed,
                "adjusted_rand_index": float(adjusted_rand_score(reference, labels)),
                "cells_compared": len(reference),
            }
            for seed, labels in assignments
        ]
    )

def default_cell_type_markers() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("T cell-like", "GENE_0041"),
            ("T cell-like", "GENE_0042"),
            ("B cell-like", "GENE_0061"),
            ("B cell-like", "GENE_0062"),
            ("Myeloid-like", "GENE_0081"),
            ("Myeloid-like", "GENE_0082"),
            ("Stromal-like", "GENE_0101"),
            ("Stromal-like", "GENE_0102"),
        ],
        columns=["cell_type", "gene"],
    )


def annotate_clusters_by_markers(
    normalized: pd.DataFrame,
    embedding: pd.DataFrame,
    marker_panel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not {"cell_type", "gene"}.issubset(marker_panel.columns):
        raise ValueError("Marker panel requires cell_type and gene columns.")
    matrix = normalized.set_index("gene")
    cluster_map = embedding.set_index("cell")["cluster"]
    rows = []
    for cluster in sorted(cluster_map.unique()):
        cells = cluster_map[cluster_map == cluster].index.tolist()
        for cell_type, group in marker_panel.groupby("cell_type"):
            genes = [gene for gene in group["gene"].astype(str) if gene in matrix.index]
            score = float(matrix.loc[genes, cells].mean().mean()) if genes else 0.0
            rows.append({"cluster": cluster, "cell_type": str(cell_type), "marker_genes_found": len(genes), "mean_marker_score": score})
    scores = pd.DataFrame(rows)
    if scores.empty:
        annotations = pd.DataFrame(columns=["cluster", "provisional_cell_type", "annotation_score", "annotation_margin"])
    else:
        annotation_rows = []
        for cluster, group in scores.groupby("cluster"):
            ranked = group.sort_values("mean_marker_score", ascending=False).reset_index(drop=True)
            best = ranked.iloc[0]
            second = float(ranked.iloc[1]["mean_marker_score"]) if len(ranked) > 1 else 0.0
            annotation_rows.append(
                {
                    "cluster": cluster,
                    "provisional_cell_type": best["cell_type"],
                    "annotation_score": float(best["mean_marker_score"]),
                    "annotation_margin": float(best["mean_marker_score"]) - second,
                    "annotation_status": "Review" if int(best["marker_genes_found"]) < 2 else "Provisional",
                }
            )
        annotations = pd.DataFrame(annotation_rows)
    return scores, annotations


def differential_expression_between_clusters(
    normalized: pd.DataFrame,
    embedding: pd.DataFrame,
    *,
    cluster_a: str,
    cluster_b: str,
    top_n: int = 100,
) -> pd.DataFrame:
    matrix = normalized.set_index("gene")
    mapping = embedding.set_index("cell")["cluster"]
    cells_a = mapping[mapping == cluster_a].index.tolist()
    cells_b = mapping[mapping == cluster_b].index.tolist()
    if not cells_a or not cells_b:
        raise ValueError("Both clusters need at least one cell.")
    mean_a = matrix[cells_a].mean(axis=1)
    mean_b = matrix[cells_b].mean(axis=1)
    pct_a = (matrix[cells_a] > 0).mean(axis=1)
    pct_b = (matrix[cells_b] > 0).mean(axis=1)
    difference = mean_b - mean_a
    result = pd.DataFrame(
        {
            "gene": matrix.index,
            f"mean_{cluster_a}": mean_a.values,
            f"mean_{cluster_b}": mean_b.values,
            "log_expression_difference": difference.values,
            f"detected_{cluster_a}_percent": (pct_a * 100).values,
            f"detected_{cluster_b}_percent": (pct_b * 100).values,
            "screening_score": (difference.abs() * (pct_b - pct_a).abs()).values,
        }
    )
    result["direction"] = np.where(result["log_expression_difference"] >= 0, f"Higher in {cluster_b}", f"Higher in {cluster_a}")
    return result.sort_values("screening_score", ascending=False).head(top_n).reset_index(drop=True)


def cluster_average_expression(
    normalized: pd.DataFrame,
    embedding: pd.DataFrame,
    genes: list[str],
) -> pd.DataFrame:
    matrix = normalized.set_index("gene")
    selected = [gene for gene in genes if gene in matrix.index]
    if not selected:
        return pd.DataFrame(columns=["gene"])
    mapping = embedding.set_index("cell")["cluster"]
    result = pd.DataFrame(index=selected)
    for cluster in sorted(mapping.unique()):
        result[cluster] = matrix.loc[selected, mapping[mapping == cluster].index].mean(axis=1)
    return result.reset_index(names="gene")


def batch_effect_audit(embedding: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    covariates = {"sample", "batch", "condition"}
    merged = embedding.copy() if covariates.intersection(embedding.columns) else embedding.merge(metadata, on="cell", how="left")
    rows = []
    for covariate in ("sample", "batch", "condition"):
        if covariate not in merged.columns or merged[covariate].nunique(dropna=True) < 2:
            continue
        for component in [column for column in merged.columns if column.startswith("PC")][:5]:
            overall = float(merged[component].mean())
            total = float(((merged[component] - overall) ** 2).sum())
            between = 0.0
            for _, group in merged.groupby(covariate, dropna=True):
                between += len(group) * float((group[component].mean() - overall) ** 2)
            rows.append({"covariate": covariate, "component": component, "variance_explained_eta_squared": between / max(total, 1e-12), "levels": int(merged[covariate].nunique(dropna=True))})
    return pd.DataFrame(rows)


def cluster_quality_metrics(embedding: pd.DataFrame) -> pd.DataFrame:
    from sklearn.metrics import davies_bouldin_score, silhouette_samples, silhouette_score

    components = [column for column in embedding.columns if column.startswith("PC")][:5]
    labels = embedding["cluster"].astype(str)
    if len(components) < 2 or labels.nunique() < 2 or len(embedding) <= labels.nunique():
        return pd.DataFrame()
    values = embedding[components].astype(float).to_numpy()
    sample_scores = silhouette_samples(values, labels)
    rows = []
    for cluster, indices in embedding.groupby("cluster").groups.items():
        scores = sample_scores[list(indices)]
        rows.append({"cluster": str(cluster), "cells": len(indices), "mean_silhouette": float(np.mean(scores)), "negative_silhouette_percent": 100 * float((scores < 0).mean()), "global_silhouette": float(silhouette_score(values, labels)), "davies_bouldin": float(davies_bouldin_score(values, labels))})
    return pd.DataFrame(rows)


def pseudobulk_expression(normalized: pd.DataFrame, embedding: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    gene_column = "gene"
    cells = [column for column in normalized.columns if column != gene_column]
    design = embedding[["cell", "cluster"]].merge(metadata, on="cell", how="left")
    records = []
    for (sample, cluster), group in design.groupby(["sample", "cluster"], dropna=False):
        selected = [cell for cell in group["cell"].astype(str) if cell in cells]
        if not selected:
            continue
        means = normalized.set_index(gene_column)[selected].mean(axis=1)
        for gene, expression in means.items():
            records.append({"sample": sample, "cluster": cluster, "gene": gene, "mean_log_expression": float(expression), "cells": len(selected)})
    return pd.DataFrame(records)


def pseudobulk_counts(counts: pd.DataFrame, embedding: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    """Aggregate raw counts by biological sample and cluster for downstream count models."""
    cleaned = validate_count_matrix(counts)
    cells = [column for column in cleaned.columns if column != "gene"]
    design = embedding[["cell", "cluster"]].merge(metadata, on="cell", how="left")
    if "sample" not in design.columns:
        raise ValueError("Cell metadata requires a sample column for pseudobulk aggregation.")
    records = []
    matrix = cleaned.set_index("gene")
    for (sample, cluster), group in design.groupby(["sample", "cluster"], dropna=False):
        selected = [cell for cell in group["cell"].astype(str) if cell in cells]
        if not selected:
            continue
        sums = matrix[selected].sum(axis=1)
        for gene, count in sums.items():
            records.append(
                {
                    "sample": sample,
                    "cluster": cluster,
                    "gene": gene,
                    "pseudobulk_raw_count": float(count),
                    "cells": len(selected),
                }
            )
    return pd.DataFrame(records)


def marker_specificity(markers: pd.DataFrame) -> pd.DataFrame:
    required = {"cluster", "gene", "marker_score"}
    if not required.issubset(markers.columns):
        raise ValueError("Marker table requires cluster, gene and marker_score.")
    pivot = markers.pivot_table(index="gene", columns="cluster", values="marker_score", aggfunc="max", fill_value=0.0)
    rows = []
    for gene, values in pivot.iterrows():
        ordered = values.sort_values(ascending=False)
        best = float(ordered.iloc[0]) if len(ordered) else 0.0
        second = float(ordered.iloc[1]) if len(ordered) > 1 else 0.0
        rows.append({"gene": gene, "best_cluster": str(ordered.index[0]) if len(ordered) else "", "best_marker_score": best, "second_best_score": second, "specificity_margin": best - second, "specificity_ratio": best / max(second, 1e-6)})
    return pd.DataFrame(rows).sort_values(["specificity_margin", "best_marker_score"], ascending=False).reset_index(drop=True)


def trajectory_screen(embedding: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    components = [column for column in embedding.columns if column.startswith("PC")][:3]
    if not components:
        return pd.DataFrame(), pd.DataFrame()
    axis = embedding[components[0]].astype(float)
    pseudotime = (axis - axis.min()) / max(float(axis.max() - axis.min()), 1e-12)
    cells = embedding[["cell", "cluster", *components]].copy()
    cells["screening_pseudotime"] = pseudotime
    centres = cells.groupby("cluster", as_index=False)[components + ["screening_pseudotime"]].mean().sort_values("screening_pseudotime")
    edges = []
    ordered = centres["cluster"].astype(str).tolist()
    for left, right in zip(ordered, ordered[1:]):
        edges.append({"source_cluster": left, "target_cluster": right, "direction": "increasing_PC1", "interpretation": "exploratory_geometry_only"})
    return cells, pd.DataFrame(edges)


def dropout_profile(counts: pd.DataFrame, *, gene_column: str = "gene") -> pd.DataFrame:
    cleaned = validate_count_matrix(counts, gene_column=gene_column)
    values = cleaned.drop(columns=[gene_column])
    return pd.DataFrame({"gene": cleaned[gene_column].astype(str), "mean_counts": values.mean(axis=1), "zero_fraction": (values == 0).mean(axis=1), "detected_cells": (values > 0).sum(axis=1)}).sort_values("mean_counts", ascending=False).reset_index(drop=True)
