from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import sparse


@dataclass(frozen=True)
class GraphClusteringResult:
    embedding: pd.DataFrame
    neighbor_edges: pd.DataFrame
    metrics: dict[str, float | int | str]


def parse_h5ad_bytes(
    payload: bytes,
    *,
    maximum_cells: int = 100_000,
    maximum_genes: int = 75_000,
    maximum_dense_elements: int = 12_000_000,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Read a safe H5AD payload and return a genes-by-cells count matrix plus cell metadata.

    The interactive workbench ultimately uses a pandas matrix. Large sparse studies are
    rejected before densification with an actionable message rather than exhausting RAM.
    """

    if not payload:
        raise ValueError("H5AD payload is empty.")
    try:
        import anndata as ad
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("H5AD support requires the 'anndata' package.") from exc

    with NamedTemporaryFile(suffix=".h5ad", delete=False) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    try:
        data = ad.read_h5ad(temp_path, backed="r")
        cells, genes = int(data.n_obs), int(data.n_vars)
        if cells < 6:
            raise ValueError("H5AD must contain at least six cells.")
        if cells > int(maximum_cells) or genes > int(maximum_genes):
            raise ValueError(
                f"H5AD contains {cells:,} cells × {genes:,} genes; this exceeds the interactive safety limit."
            )
        if cells * genes > int(maximum_dense_elements):
            raise ValueError(
                f"H5AD contains {genes:,} genes × {cells:,} cells. Use the packaged sparse/CLI workflow "
                "or reduce the study before opening it in the interactive page."
            )
        obs_names = pd.Index(data.obs_names.astype(str)).str.strip()
        var_names = pd.Index(data.var_names.astype(str)).str.strip()
        if obs_names.has_duplicates or (obs_names == "").any():
            raise ValueError("H5AD cell identifiers must be non-empty and unique.")
        if (var_names == "").any():
            raise ValueError("H5AD gene identifiers must be non-empty.")
        # Prefer an explicit counts layer; otherwise use X and report the selected source.
        source = "counts" if "counts" in data.layers else "X"
        matrix = data.layers["counts"] if source == "counts" else data.X
        matrix = matrix[:]
        if sparse.issparse(matrix):
            matrix = matrix.tocsr()
            if matrix.nnz and float(matrix.data.min()) < 0:
                raise ValueError("H5AD count layer contains negative values.")
            dense = matrix.toarray()
        else:
            dense = np.asarray(matrix, dtype=float)
            if np.nanmin(dense) < 0:
                raise ValueError("H5AD count layer contains negative values.")
        if not np.isfinite(dense).all():
            raise ValueError("H5AD count layer contains non-finite values.")

        # Make duplicate gene symbols explicit and deterministic.
        unique_genes: list[str] = []
        seen: dict[str, int] = {}
        for gene in var_names:
            base = str(gene) or "unnamed_gene"
            seen[base] = seen.get(base, 0) + 1
            unique_genes.append(base if seen[base] == 1 else f"{base}__{seen[base]}")
        counts = pd.DataFrame(dense.T, columns=obs_names)
        counts.insert(0, "gene", unique_genes)

        metadata = data.obs.copy().reset_index(names="cell")
        metadata["cell"] = metadata["cell"].astype(str)
        metadata = metadata.loc[
            :, [column for column in metadata.columns if not str(column).startswith("_")]
        ]
        audit = {
            "cells": cells,
            "genes": genes,
            "matrix_source": source,
            "sparse_input": bool(sparse.issparse(matrix)),
            "metadata_columns": [str(column) for column in metadata.columns],
            "duplicate_gene_symbols_renamed": int(
                sum(value - 1 for value in seen.values() if value > 1)
            ),
        }
        return counts, metadata, audit
    finally:
        temp_path.unlink(missing_ok=True)


def _selected_matrix(normalized: pd.DataFrame, variable_genes: pd.DataFrame) -> pd.DataFrame:
    selected = variable_genes.loc[variable_genes["highly_variable"], "gene"].astype(str).tolist()
    selected = [gene for gene in selected if gene in set(normalized["gene"].astype(str))]
    if len(selected) < 10:
        raise ValueError("At least ten variable genes are required for graph clustering.")
    return normalized.set_index("gene").loc[selected].T.astype(float)


def graph_cluster_cells(
    normalized: pd.DataFrame,
    variable_genes: pd.DataFrame,
    *,
    neighbors: int = 15,
    resolution: float = 1.0,
    random_state: int = 42,
    minimum_clusters: int = 2,
    compute_umap: bool = True,
) -> GraphClusteringResult:
    from sklearn.decomposition import PCA
    from sklearn.metrics import silhouette_score
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler

    """PCA → kNN graph → Leiden communities → UMAP/PCA embedding."""

    matrix = _selected_matrix(normalized, variable_genes)
    if len(matrix) < 8:
        raise ValueError("At least eight retained cells are required for graph clustering.")
    scaled = StandardScaler().fit_transform(matrix)
    components = max(2, min(30, scaled.shape[0] - 1, scaled.shape[1]))
    scores = PCA(n_components=components, random_state=random_state).fit_transform(scaled)
    compact = scores[:, : min(20, scores.shape[1])]
    k = max(3, min(int(neighbors), len(matrix) - 1))
    nn = NearestNeighbors(n_neighbors=k + 1, metric="euclidean").fit(compact)
    distances, indices = nn.kneighbors(compact)

    edge_weights: dict[tuple[int, int], float] = {}
    positive_distances = distances[:, 1:][distances[:, 1:] > 0]
    scale = float(np.median(positive_distances)) if positive_distances.size else 1.0
    scale = max(scale, 1e-9)
    for source in range(len(matrix)):
        for distance, target in zip(distances[source, 1:], indices[source, 1:], strict=True):
            left, right = sorted((int(source), int(target)))
            weight = float(np.exp(-float(distance) / scale))
            edge_weights[(left, right)] = max(weight, edge_weights.get((left, right), 0.0))

    edges = list(edge_weights)
    try:
        import igraph as ig
        import leidenalg

        graph = ig.Graph(n=len(matrix), edges=edges, directed=False)
        weights = [edge_weights[edge] for edge in edges]
        partition = leidenalg.find_partition(
            graph,
            leidenalg.RBConfigurationVertexPartition,
            weights=weights,
            resolution_parameter=float(resolution),
            seed=int(random_state),
        )
        labels = np.asarray(partition.membership, dtype=int)
        method = "Leiden graph"
    except ImportError:
        # Keep the packaged local workflow functional on minimal installations.
        # The fallback is explicitly labelled and never presented as Leiden.
        from sklearn.cluster import KMeans

        estimated_clusters = max(
            int(minimum_clusters),
            min(max(2, int(round(float(resolution) * 3))), max(2, int(np.sqrt(len(matrix))))),
        )
        labels = KMeans(
            n_clusters=estimated_clusters,
            n_init=20,
            random_state=random_state,
        ).fit_predict(compact)
        method = "kNN/PCA with deterministic KMeans fallback (Leiden unavailable)"
    if len(np.unique(labels)) < int(minimum_clusters):
        # A transparent deterministic fallback prevents a single-community result from
        # masquerading as meaningful heterogeneity at very low resolutions.
        from sklearn.cluster import KMeans

        labels = KMeans(
            n_clusters=int(minimum_clusters), n_init=20, random_state=random_state
        ).fit_predict(compact)
        method += " · minimum-cluster safeguard"

    if compute_umap:
        try:
            import umap

            reducer = umap.UMAP(
                n_neighbors=k,
                min_dist=0.25,
                metric="euclidean",
                random_state=int(random_state),
                n_components=2,
                low_memory=True,
            )
            manifold = reducer.fit_transform(compact)
            umap_method = "UMAP"
        except Exception:  # pragma: no cover - robust fallback for limited environments
            manifold = compact[:, :2]
            umap_method = "PCA fallback"
    else:
        from sklearn.manifold import SpectralEmbedding

        manifold = SpectralEmbedding(
            n_components=2,
            n_neighbors=k,
            affinity="nearest_neighbors",
            random_state=int(random_state),
        ).fit_transform(compact)
        umap_method = "Fast graph spectral embedding"

    embedding = pd.DataFrame(
        {
            "cell": matrix.index.astype(str),
            "PC1": scores[:, 0],
            "PC2": scores[:, 1],
            "UMAP1": manifold[:, 0],
            "UMAP2": manifold[:, 1],
            "cluster": [f"Cluster {value + 1}" for value in labels],
        }
    )
    if scores.shape[1] > 2:
        embedding["PC3"] = scores[:, 2]
    silhouette = float(silhouette_score(compact, labels)) if len(np.unique(labels)) > 1 else 0.0
    edge_frame = pd.DataFrame(
        [
            {
                "source_cell": str(matrix.index[left]),
                "target_cell": str(matrix.index[right]),
                "weight": float(weight),
            }
            for (left, right), weight in edge_weights.items()
        ]
    )
    metrics: dict[str, float | int | str] = {
        "method": method,
        "embedding_method": umap_method,
        "clusters": int(len(np.unique(labels))),
        "neighbors": int(k),
        "resolution": float(resolution),
        "silhouette": silhouette,
        "graph_edges": int(len(edge_frame)),
    }
    return GraphClusteringResult(embedding, edge_frame, metrics)


def simulated_doublet_scores(
    normalized: pd.DataFrame,
    variable_genes: pd.DataFrame,
    *,
    simulated_ratio: float = 1.5,
    neighbors: int = 25,
    random_state: int = 42,
) -> pd.DataFrame:
    from sklearn.decomposition import PCA
    from sklearn.neighbors import NearestNeighbors
    from sklearn.preprocessing import StandardScaler

    """Scrublet-inspired local simulation screen without claiming Scrublet equivalence."""

    matrix = _selected_matrix(normalized, variable_genes)
    values = matrix.to_numpy(dtype=float)
    rng = np.random.default_rng(int(random_state))
    simulated_count = max(len(matrix), int(round(len(matrix) * float(simulated_ratio))))
    left = rng.integers(0, len(matrix), size=simulated_count)
    right = rng.integers(0, len(matrix), size=simulated_count)
    simulated = 0.5 * (values[left] + values[right])
    combined = np.vstack([values, simulated])
    scaled = StandardScaler().fit_transform(combined)
    components = max(2, min(25, scaled.shape[0] - 1, scaled.shape[1]))
    compact = PCA(n_components=components, random_state=random_state).fit_transform(scaled)
    k = max(5, min(int(neighbors), len(combined) - 1))
    indices = (
        NearestNeighbors(n_neighbors=k + 1).fit(compact).kneighbors(return_distance=False)[:, 1:]
    )
    simulated_mask = np.arange(len(combined)) >= len(matrix)
    scores = simulated_mask[indices[: len(matrix)]].mean(axis=1)
    threshold = (
        float(np.quantile(scores, 0.95))
        if len(scores) >= 20
        else float(np.mean(scores) + 2 * np.std(scores))
    )
    threshold = max(threshold, 0.25)
    return pd.DataFrame(
        {
            "cell": matrix.index.astype(str),
            "simulated_doublet_score": scores,
            "simulated_doublet_flag": scores >= threshold,
            "decision_threshold": threshold,
        }
    )


def ambient_rna_audit(
    filtered_counts: pd.DataFrame, *, low_count_quantile: float = 0.1
) -> tuple[pd.DataFrame, pd.DataFrame]:
    matrix = filtered_counts.set_index("gene").astype(float)
    totals = matrix.sum(axis=0)
    cutoff = float(totals.quantile(float(low_count_quantile)))
    low_cells = totals[totals <= cutoff].index.tolist()
    if not low_cells:
        low_cells = totals.nsmallest(max(1, int(np.ceil(len(totals) * 0.1)))).index.tolist()
    ambient = matrix[low_cells].sum(axis=1)
    ambient = ambient / max(float(ambient.sum()), 1.0)
    rows = []
    for cell in matrix.columns:
        profile = matrix[cell] / max(float(matrix[cell].sum()), 1.0)
        correlation = (
            float(np.corrcoef(profile, ambient)[0, 1])
            if profile.std() > 0 and ambient.std() > 0
            else 0.0
        )
        top_ambient = ambient.nlargest(min(50, len(ambient))).index
        fraction = float(profile.loc[top_ambient].sum())
        rows.append(
            {
                "cell": str(cell),
                "ambient_profile_correlation": correlation,
                "top_ambient_gene_fraction": fraction,
                "ambient_review_flag": bool(correlation >= 0.85 and fraction >= 0.45),
            }
        )
    ambient_genes = pd.DataFrame(
        {
            "gene": ambient.index.astype(str),
            "ambient_fraction": ambient.values,
        }
    ).sort_values("ambient_fraction", ascending=False)
    return pd.DataFrame(rows), ambient_genes


S_PHASE_MARKERS = ("MCM5", "PCNA", "TYMS", "FEN1", "MCM2", "MCM4", "RRM1", "UNG", "GINS2", "MCM6")
G2M_MARKERS = (
    "HMGB2",
    "CDK1",
    "NUSAP1",
    "UBE2C",
    "BIRC5",
    "TPX2",
    "TOP2A",
    "NDC80",
    "CKS2",
    "NUF2",
)


def cell_cycle_scores(normalized: pd.DataFrame) -> pd.DataFrame:
    matrix = normalized.set_index("gene")
    upper_map = {str(gene).upper(): str(gene) for gene in matrix.index}
    s_genes = [upper_map[gene] for gene in S_PHASE_MARKERS if gene in upper_map]
    g2m_genes = [upper_map[gene] for gene in G2M_MARKERS if gene in upper_map]
    s_score = matrix.loc[s_genes].mean(axis=0) if s_genes else pd.Series(0.0, index=matrix.columns)
    g2m_score = (
        matrix.loc[g2m_genes].mean(axis=0) if g2m_genes else pd.Series(0.0, index=matrix.columns)
    )
    phase = np.where(
        (s_score <= 0) & (g2m_score <= 0), "Unresolved", np.where(s_score >= g2m_score, "S", "G2M")
    )
    return pd.DataFrame(
        {
            "cell": matrix.columns.astype(str),
            "s_phase_score": s_score.values,
            "g2m_phase_score": g2m_score.values,
            "cell_cycle_phase": phase,
            "s_markers_available": len(s_genes),
            "g2m_markers_available": len(g2m_genes),
        }
    )


def batch_residualized_embedding(
    normalized: pd.DataFrame,
    variable_genes: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    batch_column: str = "batch",
    random_state: int = 42,
) -> pd.DataFrame:
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    matrix = _selected_matrix(normalized, variable_genes)
    meta = metadata.copy()
    if "cell" not in meta.columns or batch_column not in meta.columns:
        raise ValueError(f"Metadata requires cell and {batch_column} columns.")
    if meta["cell"].astype(str).duplicated().any():
        raise ValueError("Metadata cell identifiers must be unique.")
    meta["cell"] = meta["cell"].astype(str)
    meta = meta.set_index("cell").reindex(matrix.index)
    if meta[batch_column].isna().any():
        raise ValueError("Every retained cell requires a batch value for batch residualization.")
    scaled = StandardScaler().fit_transform(matrix)
    components = max(2, min(25, scaled.shape[0] - 1, scaled.shape[1]))
    pcs = PCA(n_components=components, random_state=random_state).fit_transform(scaled)
    design = pd.get_dummies(meta[batch_column].astype(str), drop_first=False, dtype=float)
    design.insert(0, "intercept", 1.0)
    projection = design.to_numpy() @ np.linalg.pinv(design.to_numpy())
    corrected = pcs - projection @ pcs
    return pd.DataFrame(
        {
            "cell": matrix.index.astype(str),
            "batch_corrected_PC1": corrected[:, 0],
            "batch_corrected_PC2": corrected[:, 1],
            "batch": meta[batch_column].astype(str).values,
        }
    )


DEFAULT_LIGAND_RECEPTOR_PAIRS = pd.DataFrame(
    [
        ("CXCL12", "CXCR4"),
        ("CCL5", "CCR5"),
        ("CCL2", "CCR2"),
        ("IL6", "IL6R"),
        ("TNF", "TNFRSF1A"),
        ("TGFB1", "TGFBR1"),
        ("VEGFA", "KDR"),
        ("EGF", "EGFR"),
        ("PDGFA", "PDGFRA"),
        ("JAG1", "NOTCH1"),
        ("DLL4", "NOTCH1"),
        ("CD40LG", "CD40"),
        ("IFNG", "IFNGR1"),
        ("CSF1", "CSF1R"),
        ("KITLG", "KIT"),
        ("HGF", "MET"),
    ],
    columns=["ligand", "receptor"],
)


def ligand_receptor_screen(
    normalized: pd.DataFrame,
    embedding: pd.DataFrame,
    pairs: pd.DataFrame | None = None,
    *,
    minimum_mean_expression: float = 0.1,
) -> pd.DataFrame:
    pairs = DEFAULT_LIGAND_RECEPTOR_PAIRS.copy() if pairs is None else pairs.copy()
    if not {"ligand", "receptor"}.issubset(pairs.columns):
        raise ValueError("Ligand-receptor table requires ligand and receptor columns.")
    matrix = normalized.set_index("gene")
    upper_map = {str(gene).upper(): str(gene) for gene in matrix.index}
    cluster_map = embedding.set_index("cell")["cluster"]
    cluster_means = {
        cluster: matrix[cluster_map[cluster_map == cluster].index].mean(axis=1)
        for cluster in sorted(cluster_map.unique())
    }
    rows: list[dict[str, object]] = []
    for ligand, receptor in pairs[["ligand", "receptor"]].itertuples(index=False, name=None):
        ligand_key, receptor_key = str(ligand).upper(), str(receptor).upper()
        if ligand_key not in upper_map or receptor_key not in upper_map:
            continue
        ligand_gene, receptor_gene = upper_map[ligand_key], upper_map[receptor_key]
        for sender, sender_mean in cluster_means.items():
            ligand_expression = float(sender_mean.loc[ligand_gene])
            if ligand_expression < minimum_mean_expression:
                continue
            for receiver, receiver_mean in cluster_means.items():
                receptor_expression = float(receiver_mean.loc[receptor_gene])
                score = float(np.sqrt(max(ligand_expression, 0) * max(receptor_expression, 0)))
                if receptor_expression >= minimum_mean_expression:
                    rows.append(
                        {
                            "sender_cluster": sender,
                            "receiver_cluster": receiver,
                            "ligand": ligand_gene,
                            "receptor": receptor_gene,
                            "ligand_mean": ligand_expression,
                            "receptor_mean": receptor_expression,
                            "interaction_score": score,
                        }
                    )
    return (
        pd.DataFrame(rows).sort_values("interaction_score", ascending=False).reset_index(drop=True)
        if rows
        else pd.DataFrame(
            columns=[
                "sender_cluster",
                "receiver_cluster",
                "ligand",
                "receptor",
                "ligand_mean",
                "receptor_mean",
                "interaction_score",
            ]
        )
    )


def graph_cluster_stability(
    normalized: pd.DataFrame,
    variable_genes: pd.DataFrame,
    *,
    neighbors: int = 15,
    resolution: float = 1.0,
    random_seeds: Iterable[int] = (11, 23, 37),
) -> pd.DataFrame:
    from sklearn.metrics import adjusted_rand_score

    runs: list[tuple[int, pd.Series]] = []
    for seed in random_seeds:
        result = graph_cluster_cells(
            normalized,
            variable_genes,
            neighbors=int(neighbors),
            resolution=float(resolution),
            random_state=int(seed),
            compute_umap=False,
        )
        runs.append((int(seed), result.embedding.set_index("cell")["cluster"]))
    reference_seed, reference = runs[0]
    return pd.DataFrame(
        [
            {
                "reference_seed": reference_seed,
                "comparison_seed": seed,
                "adjusted_rand_index": float(
                    adjusted_rand_score(reference.loc[labels.index], labels)
                ),
                "cells_compared": int(len(labels)),
                "method": "Leiden graph",
            }
            for seed, labels in runs
        ]
    )
