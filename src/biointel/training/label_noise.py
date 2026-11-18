from __future__ import annotations

import pandas as pd


def detect_label_noise(
    dataframe: pd.DataFrame,
    *,
    label_column: str = "interaction_label",
    probability_column: str = "positive_probability",
    drug_column: str = "canonical_smiles",
    target_column: str = "protein_sequence",
    high_confidence: float = 0.90,
) -> pd.DataFrame:
    """Flag duplicate conflicts and high-confidence model/label disagreement."""

    required = {label_column, drug_column, target_column}
    missing = required - set(dataframe.columns)
    if missing:
        raise ValueError("Missing label-noise columns: " + ", ".join(sorted(missing)))
    source = dataframe.copy().reset_index(drop=True)
    source[label_column] = pd.to_numeric(source[label_column], errors="coerce")
    group_columns = [drug_column, target_column]
    conflicting_groups = (
        source.groupby(group_columns, dropna=False)[label_column].nunique(dropna=True) > 1
    )
    conflict_keys = set(conflicting_groups[conflicting_groups].index.tolist())
    source["duplicate_conflict"] = [
        tuple(values) in conflict_keys
        for values in source[group_columns].itertuples(index=False, name=None)
    ]
    source["model_disagreement"] = False
    if probability_column in source.columns:
        probability = pd.to_numeric(source[probability_column], errors="coerce")
        label = source[label_column]
        source["model_disagreement"] = (
            ((label == 1) & (probability <= 1.0 - high_confidence))
            | ((label == 0) & (probability >= high_confidence))
        ).fillna(False)
    source["noise_score"] = (
        source["duplicate_conflict"].astype(float) * 0.60
        + source["model_disagreement"].astype(float) * 0.40
    )
    return (
        source[source["noise_score"] > 0]
        .sort_values("noise_score", ascending=False)
        .reset_index(drop=True)
    )
