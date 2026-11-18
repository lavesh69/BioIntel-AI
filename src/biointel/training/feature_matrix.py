from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from biointel.dti.drug_features import (
    DrugFeatureSet,
    extract_drug_features,
)
from biointel.dti.feature_combiner import (
    CombinedFeatureSet,
    FeatureSchema,
)
from biointel.dti.protein_features import (
    ProteinFeatureSet,
    extract_protein_features,
)


@dataclass(frozen=True)
class FeatureMatrixResult:
    """Feature matrix plus row-level extraction failures."""

    matrix: np.ndarray
    target: np.ndarray
    valid_rows: pd.DataFrame
    errors: pd.DataFrame
    feature_names: tuple[str, ...]
    example_features: CombinedFeatureSet
    cache_summary: dict[str, int]


def _feature_hash(names: tuple[str, ...]) -> str:
    return hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()


def _combine_cached(
    drug: DrugFeatureSet,
    protein: ProteinFeatureSet,
    radius: int,
    n_bits: int,
    use_chirality: bool,
    include_dipeptides: bool,
) -> CombinedFeatureSet:
    names = drug.names + protein.names
    values = np.concatenate([drug.values, protein.values]).astype(np.float32, copy=False)
    schema = FeatureSchema(
        schema_version="2.0.0",
        feature_count=len(names),
        feature_hash=_feature_hash(names),
        fingerprint_radius=radius,
        fingerprint_bits=n_bits,
        use_chirality=use_chirality,
        include_dipeptides=include_dipeptides,
        drug_feature_count=len(drug.names),
        protein_feature_count=len(protein.names),
    )
    return CombinedFeatureSet(
        values=values,
        names=names,
        drug=drug,
        protein=protein,
        schema=schema,
    )


def _row_number(
    index: object,
    fallback: int,
) -> int:
    try:
        return int(index) + 2
    except (TypeError, ValueError):
        return fallback + 2


def build_feature_matrix(
    dataframe: pd.DataFrame,
    target_column: str,
    radius: int = 2,
    n_bits: int = 2048,
    use_chirality: bool = True,
    include_dipeptides: bool = False,
) -> FeatureMatrixResult:
    """Build a memory-efficient matrix with unique-entity extraction.

    Drug and protein features are calculated once per unique entity. Pair
    rows are assembled by indexed NumPy operations rather than repeated
    Python concatenation. The returned matrix uses float32 to halve memory.
    """

    required = {
        "canonical_smiles",
        "protein_sequence",
        target_column,
    }
    missing = required - set(dataframe.columns)
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))

    smiles = dataframe["canonical_smiles"].astype(str).str.strip()
    sequences = (
        dataframe["protein_sequence"].astype(str).str.replace(r"\s+", "", regex=True).str.upper()
    )
    target_numeric = pd.to_numeric(
        dataframe[target_column],
        errors="coerce",
    ).to_numpy(dtype=float)

    drug_cache: dict[str, DrugFeatureSet] = {}
    protein_cache: dict[str, ProteinFeatureSet] = {}
    drug_errors: dict[str, str] = {}
    protein_errors: dict[str, str] = {}

    for value in pd.unique(smiles):
        try:
            drug_cache[value] = extract_drug_features(
                value,
                radius=radius,
                n_bits=n_bits,
                use_chirality=use_chirality,
            )
        except Exception as exc:
            drug_errors[value] = str(exc)

    for value in pd.unique(sequences):
        try:
            protein_cache[value] = extract_protein_features(
                value,
                include_dipeptides=include_dipeptides,
            )
        except Exception as exc:
            protein_errors[value] = str(exc)

    valid_mask = np.isfinite(target_numeric)
    valid_mask &= smiles.isin(drug_cache).to_numpy()
    valid_mask &= sequences.isin(protein_cache).to_numpy()

    errors: list[dict[str, object]] = []
    invalid_positions = np.flatnonzero(~valid_mask)
    for position in invalid_positions:
        messages: list[str] = []
        smiles_value = smiles.iloc[position]
        sequence_value = sequences.iloc[position]
        if not np.isfinite(target_numeric[position]):
            messages.append(f"{target_column} must be finite")
        if smiles_value in drug_errors:
            messages.append(f"Drug feature error: " f"{drug_errors[smiles_value]}")
        if sequence_value in protein_errors:
            messages.append("Protein feature error: " f"{protein_errors[sequence_value]}")
        errors.append(
            {
                "row": _row_number(
                    dataframe.index[position],
                    position,
                ),
                "error": "; ".join(messages) or "Feature extraction failed.",
            }
        )

    valid_positions = np.flatnonzero(valid_mask)
    if len(valid_positions) == 0:
        raise ValueError("No valid rows were available for feature extraction.")

    used_smiles = list(dict.fromkeys(smiles.iloc[valid_positions]))
    used_sequences = list(dict.fromkeys(sequences.iloc[valid_positions]))
    drug_index = {value: index for index, value in enumerate(used_smiles)}
    protein_index = {value: index for index, value in enumerate(used_sequences)}

    first_drug = drug_cache[used_smiles[0]]
    first_protein = protein_cache[used_sequences[0]]
    example = _combine_cached(
        first_drug,
        first_protein,
        radius=radius,
        n_bits=n_bits,
        use_chirality=use_chirality,
        include_dipeptides=include_dipeptides,
    )

    drug_matrix = np.vstack([drug_cache[value].values for value in used_smiles]).astype(
        np.float32, copy=False
    )
    protein_matrix = np.vstack([protein_cache[value].values for value in used_sequences]).astype(
        np.float32, copy=False
    )

    valid_smiles = smiles.iloc[valid_positions]
    valid_sequences = sequences.iloc[valid_positions]
    drug_rows = valid_smiles.map(drug_index).to_numpy(dtype=np.int32)
    protein_rows = valid_sequences.map(protein_index).to_numpy(dtype=np.int32)

    drug_width = drug_matrix.shape[1]
    protein_width = protein_matrix.shape[1]
    matrix = np.empty(
        (
            len(valid_positions),
            drug_width + protein_width,
        ),
        dtype=np.float32,
    )
    matrix[:, :drug_width] = drug_matrix[drug_rows]
    matrix[:, drug_width:] = protein_matrix[protein_rows]

    if not np.isfinite(matrix).all():
        raise ValueError("Feature matrix contains non-finite values.")

    valid_rows = dataframe.iloc[valid_positions].reset_index(drop=True)
    target = target_numeric[valid_positions].astype(float, copy=False)

    return FeatureMatrixResult(
        matrix=matrix,
        target=target,
        valid_rows=valid_rows,
        errors=pd.DataFrame(
            errors,
            columns=["row", "error"],
        ),
        feature_names=example.names,
        example_features=example,
        cache_summary={
            "unique_drugs": len(used_smiles),
            "unique_targets": len(used_sequences),
            "drug_cache_hits": (len(valid_positions) - len(used_smiles)),
            "protein_cache_hits": (len(valid_positions) - len(used_sequences)),
            "rows_processed": len(valid_positions),
            "feature_count": matrix.shape[1],
            "matrix_bytes": int(matrix.nbytes),
            "matrix_dtype": str(matrix.dtype),
        },
    )
