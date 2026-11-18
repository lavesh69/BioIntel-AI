from __future__ import annotations

from collections import Counter
from math import log

import numpy as np
import pandas as pd


def _clean_sequence(sequence: str) -> str:
    seq = "".join(sequence.split()).upper()
    if any(base not in "ACGTN" for base in seq):
        raise ValueError("Sequence contains unsupported symbols.")
    return seq


def kmer_profile(sequence: str, k: int = 4) -> dict[str, int]:
    seq = _clean_sequence(sequence)
    if k < 1 or k > 31:
        raise ValueError("k must be between 1 and 31.")
    if len(seq) < k:
        return {}
    return dict(Counter(seq[i : i + k] for i in range(len(seq) - k + 1) if "N" not in seq[i : i + k]))


def approximate_ani(sequence_a: str, sequence_b: str, k: int = 15) -> dict:
    cleaned_a = _clean_sequence(sequence_a)
    cleaned_b = _clean_sequence(sequence_b)
    if len(cleaned_a) < k or len(cleaned_b) < k:
        raise ValueError(f"Both sequences must contain at least {k} bases for this ANI proxy.")
    a_profile = kmer_profile(cleaned_a, k)
    b_profile = kmer_profile(cleaned_b, k)
    a, b = set(a_profile), set(b_profile)
    intersection = len(a & b)
    union = len(a | b)
    jaccard = intersection / union if union else 0
    containment_a = intersection / len(a) if a else 0
    containment_b = intersection / len(b) if b else 0
    mash_distance = -np.log(max(2 * jaccard / (1 + jaccard), 1e-15)) / k if jaccard else np.inf
    ani_proxy = max(0.0, 100 * (1 - mash_distance)) if np.isfinite(mash_distance) else 0.0
    return {
        "k": k,
        "shared_kmers": intersection,
        "union_kmers": union,
        "jaccard": round(jaccard, 6),
        "containment_a_in_b": round(containment_a, 6),
        "containment_b_in_a": round(containment_b, 6),
        "mash_distance_proxy": round(float(mash_distance), 6) if np.isfinite(mash_distance) else None,
        "ani_proxy_percent": round(ani_proxy, 3),
        "warning": "This is a MinHash-style k-mer screening proxy; use FastANI or whole-genome alignment for publication-grade ANI.",
    }


def validate_abundance_frame(
    frame: pd.DataFrame,
    *,
    taxon_column: str = "taxon",
    abundance_columns: list[str] | None = None,
) -> pd.DataFrame:
    if taxon_column not in frame.columns:
        raise ValueError("Taxon column is missing.")
    columns = abundance_columns or [column for column in frame.columns if column != taxon_column]
    if not columns:
        raise ValueError("Select at least one abundance sample.")
    normalized_names = [str(column).strip() for column in columns]
    if any(not name for name in normalized_names) or len(set(normalized_names)) != len(normalized_names):
        raise ValueError("Abundance sample names must be non-empty and unique.")
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError("Unknown sample columns: " + ", ".join(missing))
    output = frame[[taxon_column, *columns]].copy()
    if output[taxon_column].astype(str).str.strip().eq("").any():
        raise ValueError("Taxon identifiers cannot be empty.")
    if output[taxon_column].astype(str).duplicated().any():
        numeric = output[columns].apply(pd.to_numeric, errors="raise")
        output = pd.concat([output[[taxon_column]], numeric], axis=1).groupby(taxon_column, as_index=False)[columns].sum()
    output[columns] = output[columns].apply(pd.to_numeric, errors="raise")
    if not np.all(np.isfinite(output[columns].to_numpy(dtype=float))):
        raise ValueError("Abundance values must be finite.")
    if (output[columns] < 0).any().any():
        locations = np.argwhere(output[columns].to_numpy(float) < 0)
        first = locations[0]
        raise ValueError(f"Negative abundance detected for taxon '{output.iloc[first[0]][taxon_column]}' in sample '{columns[first[1]]}'.")
    if (output[columns].sum(axis=0) <= 0).any():
        invalid = output[columns].sum(axis=0)
        raise ValueError("Every selected sample must have positive total abundance: " + ", ".join(invalid[invalid <= 0].index))
    return output


def diversity_metrics(
    frame: pd.DataFrame, taxon_column: str = "taxon", abundance_columns: list[str] | None = None
) -> pd.DataFrame:
    data = validate_abundance_frame(frame, taxon_column=taxon_column, abundance_columns=abundance_columns)
    columns = [column for column in data.columns if column != taxon_column]
    rows = []
    for column in columns:
        values = data[column].astype(float)
        total = float(values.sum())
        p = (values / total)[values > 0]
        shannon = float(-(p * p.map(log)).sum()) if len(p) else 0
        simpson = float(1 - (p * p).sum()) if len(p) else 0
        observed = int((values > 0).sum())
        pielou = shannon / log(observed) if observed > 1 else 0.0
        rows.append({"sample": column, "observed_taxa": observed, "total_abundance": total, "shannon": round(shannon, 6), "simpson": round(simpson, 6), "pielou_evenness": round(pielou, 6)})
    return pd.DataFrame(rows)


def beta_diversity(
    frame: pd.DataFrame,
    *,
    taxon_column: str = "taxon",
    abundance_columns: list[str] | None = None,
    metric: str = "braycurtis",
) -> pd.DataFrame:
    from scipy.spatial.distance import pdist, squareform

    data = validate_abundance_frame(frame, taxon_column=taxon_column, abundance_columns=abundance_columns)
    columns = [column for column in data.columns if column != taxon_column]
    matrix = data[columns].to_numpy(float).T
    if metric == "jaccard":
        values = squareform(pdist(matrix > 0, metric="jaccard"))
    elif metric == "braycurtis":
        values = squareform(pdist(matrix, metric="braycurtis"))
    else:
        raise ValueError("Beta-diversity metric must be braycurtis or jaccard.")
    if not np.all(np.isfinite(values)):
        raise ValueError("Beta-diversity calculation produced non-finite distances.")
    np.fill_diagonal(values, 0.0)
    return pd.DataFrame(values, index=columns, columns=columns)
