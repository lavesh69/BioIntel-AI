from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit


@dataclass(frozen=True)
class SplitResult:
    train_indices: np.ndarray
    validation_indices: np.ndarray
    test_indices: np.ndarray
    summary: dict[str, object]


def _validate_fractions(test_fraction: float, validation_fraction: float) -> None:
    if not 0.05 <= test_fraction <= 0.40:
        raise ValueError("test_fraction must be between 0.05 and 0.40")
    if not 0.05 <= validation_fraction <= 0.30:
        raise ValueError("validation_fraction must be between 0.05 and 0.30")
    if test_fraction + validation_fraction >= 0.60:
        raise ValueError("test_fraction + validation_fraction must be below 0.60")


def temporal_split_indices(
    dataframe: pd.DataFrame,
    date_column: str,
    *,
    test_fraction: float = 0.20,
    validation_fraction: float = 0.15,
) -> SplitResult:
    _validate_fractions(test_fraction, validation_fraction)
    if date_column not in dataframe.columns:
        raise ValueError(f"Missing temporal split column: {date_column}")
    parsed = pd.to_datetime(dataframe[date_column], errors="coerce", utc=True)
    if parsed.isna().any():
        raise ValueError("Temporal split column contains missing or invalid dates.")
    order = np.argsort(parsed.to_numpy())
    n_rows = len(order)
    if n_rows < 12:
        raise ValueError("At least 12 rows are required for a temporal split.")
    test_size = max(1, int(round(n_rows * test_fraction)))
    validation_size = max(1, int(round(n_rows * validation_fraction)))
    train_size = n_rows - test_size - validation_size
    if train_size < 2:
        raise ValueError("Temporal split leaves too few training rows.")
    train = order[:train_size]
    validation = order[train_size : train_size + validation_size]
    test = order[train_size + validation_size :]
    return SplitResult(
        train,
        validation,
        test,
        {
            "strategy": "temporal",
            "date_column": date_column,
            "train_rows": len(train),
            "validation_rows": len(validation),
            "test_rows": len(test),
            "train_latest": parsed.iloc[train].max().isoformat(),
            "validation_earliest": parsed.iloc[validation].min().isoformat(),
            "test_earliest": parsed.iloc[test].min().isoformat(),
            "chronological_order_preserved": bool(
                parsed.iloc[train].max() <= parsed.iloc[validation].min()
                and parsed.iloc[validation].max() <= parsed.iloc[test].min()
            ),
        },
    )


def cold_drug_target_split_indices(
    dataframe: pd.DataFrame,
    *,
    drug_column: str = "drug_id",
    target_column: str = "target_id",
    test_fraction: float = 0.20,
    validation_fraction: float = 0.15,
    random_seed: int = 42,
) -> SplitResult:
    _validate_fractions(test_fraction, validation_fraction)
    missing = {drug_column, target_column} - set(dataframe.columns)
    if missing:
        raise ValueError("Missing cold-split columns: " + ", ".join(sorted(missing)))
    if len(dataframe) < 12:
        raise ValueError("At least 12 rows are required for cold drug-target splitting.")

    drugs = dataframe[drug_column].astype(str)
    targets = dataframe[target_column].astype(str)
    unique_drugs = np.array(sorted(drugs.unique()))
    unique_targets = np.array(sorted(targets.unique()))
    if len(unique_drugs) < 5 or len(unique_targets) < 5:
        raise ValueError("Cold drug-target split requires at least five unique drugs and targets.")

    rng = np.random.default_rng(random_seed)
    rng.shuffle(unique_drugs)
    rng.shuffle(unique_targets)

    test_drug_count = max(1, int(round(len(unique_drugs) * test_fraction)))
    test_target_count = max(1, int(round(len(unique_targets) * test_fraction)))
    validation_drug_count = max(1, int(round(len(unique_drugs) * validation_fraction)))
    validation_target_count = max(1, int(round(len(unique_targets) * validation_fraction)))

    test_drugs = set(unique_drugs[:test_drug_count])
    validation_drugs = set(unique_drugs[test_drug_count : test_drug_count + validation_drug_count])
    test_targets = set(unique_targets[:test_target_count])
    validation_targets = set(
        unique_targets[test_target_count : test_target_count + validation_target_count]
    )

    test_mask = drugs.isin(test_drugs) & targets.isin(test_targets)
    validation_mask = drugs.isin(validation_drugs) & targets.isin(validation_targets)
    held_drugs = test_drugs | validation_drugs
    held_targets = test_targets | validation_targets
    train_mask = ~drugs.isin(held_drugs) & ~targets.isin(held_targets)

    train = np.flatnonzero(train_mask.to_numpy())
    validation = np.flatnonzero(validation_mask.to_numpy())
    test = np.flatnonzero(test_mask.to_numpy())
    if min(len(train), len(validation), len(test)) == 0:
        raise ValueError(
            "Cold split produced an empty partition. Increase dataset diversity or change seed."
        )

    return SplitResult(
        train,
        validation,
        test,
        {
            "strategy": "cold_drug_and_target",
            "train_rows": len(train),
            "validation_rows": len(validation),
            "test_rows": len(test),
            "train_unique_drugs": int(drugs.iloc[train].nunique()),
            "validation_unique_drugs": int(drugs.iloc[validation].nunique()),
            "test_unique_drugs": int(drugs.iloc[test].nunique()),
            "train_unique_targets": int(targets.iloc[train].nunique()),
            "validation_unique_targets": int(targets.iloc[validation].nunique()),
            "test_unique_targets": int(targets.iloc[test].nunique()),
            "excluded_cross_partition_rows": int(
                len(dataframe) - len(train) - len(validation) - len(test)
            ),
            "drug_overlap": False,
            "target_overlap": False,
        },
    )


def _sequence_identity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    width = min(len(left), len(right))
    matches = sum(a == b for a, b in zip(left[:width], right[:width], strict=False))
    return matches / max(len(left), len(right))


def greedy_sequence_clusters(
    sequences: pd.Series,
    *,
    identity_threshold: float = 0.70,
    max_sequences: int = 5_000,
) -> np.ndarray:
    if not 0.0 < identity_threshold <= 1.0:
        raise ValueError("identity_threshold must be in (0, 1].")
    values = sequences.astype(str).str.replace(r"\s+", "", regex=True).str.upper().tolist()
    if len(values) > max_sequences:
        raise ValueError(
            f"Built-in exact clustering is limited to {max_sequences:,} sequences. "
            "Use MMseqs2/CD-HIT externally for larger datasets."
        )
    representatives: list[str] = []
    cluster_ids: list[int] = []
    for sequence in values:
        assigned: int | None = None
        for cluster_id, representative in enumerate(representatives):
            if _sequence_identity(sequence, representative) >= identity_threshold:
                assigned = cluster_id
                break
        if assigned is None:
            assigned = len(representatives)
            representatives.append(sequence)
        cluster_ids.append(assigned)
    return np.asarray(cluster_ids, dtype=np.int32)


def sequence_cluster_split_indices(
    dataframe: pd.DataFrame,
    *,
    sequence_column: str = "protein_sequence",
    identity_threshold: float = 0.70,
    test_fraction: float = 0.20,
    validation_fraction: float = 0.15,
    random_seed: int = 42,
) -> SplitResult:
    _validate_fractions(test_fraction, validation_fraction)
    if sequence_column not in dataframe.columns:
        raise ValueError(f"Missing protein sequence column: {sequence_column}")
    clusters = greedy_sequence_clusters(
        dataframe[sequence_column], identity_threshold=identity_threshold
    )
    if len(np.unique(clusters)) < 3:
        raise ValueError("Sequence clustering produced fewer than three clusters.")
    indices = np.arange(len(dataframe))
    first = GroupShuffleSplit(n_splits=1, test_size=test_fraction, random_state=random_seed)
    remaining_pos, test_pos = next(first.split(indices, groups=clusters))
    remaining = indices[remaining_pos]
    test = indices[test_pos]
    relative_validation = validation_fraction / (1.0 - test_fraction)
    second = GroupShuffleSplit(
        n_splits=1, test_size=relative_validation, random_state=random_seed + 1
    )
    train_pos, validation_pos = next(second.split(remaining, groups=clusters[remaining]))
    train = remaining[train_pos]
    validation = remaining[validation_pos]
    overlap = bool(
        set(clusters[train]) & set(clusters[validation])
        or set(clusters[train]) & set(clusters[test])
        or set(clusters[validation]) & set(clusters[test])
    )
    return SplitResult(
        train,
        validation,
        test,
        {
            "strategy": "protein_sequence_cluster",
            "identity_threshold": identity_threshold,
            "cluster_count": int(len(np.unique(clusters))),
            "train_rows": len(train),
            "validation_rows": len(validation),
            "test_rows": len(test),
            "cluster_overlap": overlap,
        },
    )
