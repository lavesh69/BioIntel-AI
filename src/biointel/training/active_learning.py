from __future__ import annotations

import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator


def _fingerprints(smiles_values: list[str]):
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=1024)
    output = []
    for smiles in smiles_values:
        mol = Chem.MolFromSmiles(smiles)
        output.append(generator.GetFingerprint(mol) if mol is not None else None)
    return output


def prioritize_active_learning(
    predictions: pd.DataFrame,
    *,
    batch_size: int = 50,
    probability_column: str = "positive_probability",
    smiles_column: str = "canonical_smiles",
    uncertainty_weight: float = 0.70,
    diversity_weight: float = 0.30,
) -> pd.DataFrame:
    """Select uncertain and chemically diverse candidates for the next experiment."""

    required = {probability_column, smiles_column}
    missing = required - set(predictions.columns)
    if missing:
        raise ValueError("Missing active-learning columns: " + ", ".join(sorted(missing)))
    if not 1 <= batch_size <= len(predictions):
        raise ValueError("batch_size must be between 1 and the number of predictions")
    if uncertainty_weight < 0 or diversity_weight < 0:
        raise ValueError("Active-learning weights must be non-negative")
    total_weight = uncertainty_weight + diversity_weight
    if total_weight <= 0:
        raise ValueError("At least one active-learning weight must be positive")
    uncertainty_weight /= total_weight
    diversity_weight /= total_weight

    source = predictions.copy().reset_index(drop=True)
    probabilities = pd.to_numeric(source[probability_column], errors="coerce")
    source = source[probabilities.notna()].copy().reset_index(drop=True)
    probabilities = pd.to_numeric(source[probability_column], errors="coerce").to_numpy(float)
    source["uncertainty_score"] = 1.0 - np.abs(probabilities - 0.5) * 2.0
    fingerprints = _fingerprints(source[smiles_column].astype(str).tolist())

    selected: list[int] = []
    remaining = set(range(len(source)))
    while remaining and len(selected) < min(batch_size, len(source)):
        best_index = None
        best_score = -np.inf
        for index in remaining:
            fp = fingerprints[index]
            if not selected or fp is None:
                diversity = 1.0
            else:
                similarities = [
                    DataStructs.TanimotoSimilarity(fp, fingerprints[chosen])
                    for chosen in selected
                    if fingerprints[chosen] is not None
                ]
                diversity = 1.0 - max(similarities, default=0.0)
            score = (
                uncertainty_weight * float(source.loc[index, "uncertainty_score"])
                + diversity_weight * diversity
            )
            if score > best_score:
                best_score = score
                best_index = index
        if best_index is None:
            break
        selected.append(best_index)
        remaining.remove(best_index)
        source.loc[best_index, "diversity_score"] = (
            1.0
            if len(selected) == 1
            else (
                1.0
                - max(
                    [
                        DataStructs.TanimotoSimilarity(
                            fingerprints[best_index], fingerprints[chosen]
                        )
                        for chosen in selected[:-1]
                        if fingerprints[best_index] is not None and fingerprints[chosen] is not None
                    ],
                    default=0.0,
                )
            )
        )
        source.loc[best_index, "active_learning_score"] = best_score

    result = source.iloc[selected].copy()
    result.insert(0, "selection_rank", range(1, len(result) + 1))
    return result.reset_index(drop=True)
