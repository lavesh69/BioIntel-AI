from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from biointel.chemistry.smiles_validator import validate_smiles
from biointel.dti.protein_features import clean_protein_sequence

CLASSIFICATION_COLUMNS = {
    "canonical_smiles",
    "protein_sequence",
    "label",
}
REGRESSION_COLUMNS = {
    "canonical_smiles",
    "protein_sequence",
    "p_activity",
}


@dataclass(frozen=True)
class DatasetValidationReport:
    """Detailed, non-destructive DTI dataset validation report."""

    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    conflicting_groups: int
    errors: pd.DataFrame
    duplicates: pd.DataFrame
    conflicts: pd.DataFrame
    cleaned: pd.DataFrame
    summary: dict[str, object]


def _source_row(
    index: object,
    position: int,
) -> int | str:
    if isinstance(index, (int, np.integer)):
        return int(index) + 2
    return str(index) if index is not None else position + 2


def validate_dti_dataset(
    dataframe: pd.DataFrame,
    task: str = "classification",
    drop_exact_duplicates: bool = True,
) -> DatasetValidationReport:
    """Validate and audit a DTI dataset with unique-entity caching."""

    if task not in {"classification", "regression"}:
        raise ValueError("task must be classification or regression")

    required = CLASSIFICATION_COLUMNS if task == "classification" else REGRESSION_COLUMNS
    missing = required - set(dataframe.columns)
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))

    target_column = "label" if task == "classification" else "p_activity"
    raw_smiles = dataframe["canonical_smiles"]
    raw_proteins = dataframe["protein_sequence"]
    smiles_text = raw_smiles.fillna("").astype(str).str.strip()
    protein_text = (
        raw_proteins.fillna("").astype(str).str.replace(r"\s+", "", regex=True).str.upper()
    )
    target_numeric = pd.to_numeric(
        dataframe[target_column],
        errors="coerce",
    ).to_numpy(dtype=float)

    canonical_cache: dict[str, str] = {}
    smiles_errors: dict[str, str] = {}
    for value in pd.unique(smiles_text):
        if not value:
            continue
        try:
            canonical_cache[value] = validate_smiles(value).canonical_smiles
        except Exception as exc:
            smiles_errors[value] = str(exc)

    protein_cache: dict[str, str] = {}
    protein_errors: dict[str, str] = {}
    for value in pd.unique(protein_text):
        if not value:
            continue
        try:
            protein_cache[value] = clean_protein_sequence(value)
        except Exception as exc:
            protein_errors[value] = str(exc)

    smiles_valid = (smiles_text.ne("") & smiles_text.isin(canonical_cache)).to_numpy()
    protein_valid = (protein_text.ne("") & protein_text.isin(protein_cache)).to_numpy()
    target_valid = np.isfinite(target_numeric)
    if task == "classification":
        target_valid &= np.isin(
            target_numeric,
            (0.0, 1.0),
        )
    else:
        target_valid &= (target_numeric >= -5.0) & (target_numeric <= 20.0)

    valid_mask = smiles_valid & protein_valid & target_valid

    errors: list[dict[str, object]] = []
    for position in np.flatnonzero(~valid_mask):
        messages: list[str] = []
        smiles_value = smiles_text.iloc[position]
        protein_value = protein_text.iloc[position]

        if not smiles_value:
            messages.append("canonical_smiles is empty")
        elif smiles_value in smiles_errors:
            messages.append(smiles_errors[smiles_value])

        if not protein_value:
            messages.append("protein_sequence is empty")
        elif protein_value in protein_errors:
            messages.append(protein_errors[protein_value])

        if not np.isfinite(target_numeric[position]):
            messages.append(f"{target_column} must be finite")
        elif task == "classification" and (target_numeric[position] not in (0.0, 1.0)):
            messages.append("label must be exactly 0 or 1")
        elif task == "regression" and not (-5.0 <= target_numeric[position] <= 20.0):
            messages.append("p_activity is outside the supported " "sanity range [-5, 20]")

        errors.append(
            {
                "row": _source_row(
                    dataframe.index[position],
                    position,
                ),
                "error": "; ".join(messages) or "Row validation failed.",
            }
        )

    valid_positions = np.flatnonzero(valid_mask)
    validated = dataframe.iloc[valid_positions].copy()
    if len(validated):
        valid_smiles = smiles_text.iloc[valid_positions]
        valid_proteins = protein_text.iloc[valid_positions]
        validated["canonical_smiles"] = valid_smiles.map(canonical_cache).to_numpy()
        validated["protein_sequence"] = valid_proteins.map(protein_cache).to_numpy()
        if task == "classification":
            validated["label"] = target_numeric[valid_positions].astype(int)
        else:
            validated["p_activity"] = target_numeric[valid_positions].astype(float)
        validated["_source_row"] = [
            _source_row(
                dataframe.index[position],
                int(position),
            )
            for position in valid_positions
        ]

    key_columns = [
        "canonical_smiles",
        "protein_sequence",
    ]
    duplicates = pd.DataFrame()
    conflicts = pd.DataFrame()
    duplicate_rows = 0
    conflicting_groups = 0

    if not validated.empty:
        duplicate_mask = validated.duplicated(
            subset=key_columns + [target_column],
            keep="first",
        )
        duplicates = validated.loc[duplicate_mask].copy()
        duplicate_rows = int(duplicate_mask.sum())

        unique_targets = validated.groupby(
            key_columns,
            dropna=False,
            sort=False,
        )[target_column].nunique()
        conflict_keys = unique_targets[unique_targets > 1].reset_index()[key_columns]
        conflicting_groups = len(conflict_keys)

        if conflicting_groups:
            conflicts = validated.merge(
                conflict_keys,
                on=key_columns,
                how="inner",
            ).sort_values(key_columns)
            conflict_index = validated.merge(
                conflict_keys.assign(_conflict=True),
                on=key_columns,
                how="left",
            )["_conflict"].eq(True)
            validated = validated.loc[~conflict_index.to_numpy(dtype=bool)].copy()

        if drop_exact_duplicates:
            validated = validated.drop_duplicates(
                subset=key_columns + [target_column],
                keep="first",
            ).copy()

    cleaned = validated.reindex(columns=list(dataframe.columns)).reset_index(drop=True)
    errors_df = pd.DataFrame(
        errors,
        columns=["row", "error"],
    )

    summary = {
        "task": task,
        "original_rows": int(len(dataframe)),
        "valid_after_cleaning": int(len(cleaned)),
        "invalid_rows": int(len(errors_df)),
        "exact_duplicate_rows": duplicate_rows,
        "conflicting_pair_groups": conflicting_groups,
        "class_distribution": (
            cleaned["label"].value_counts().sort_index().to_dict()
            if task == "classification" and not cleaned.empty
            else None
        ),
        "p_activity_min": (
            float(cleaned["p_activity"].min())
            if task == "regression" and not cleaned.empty
            else None
        ),
        "p_activity_max": (
            float(cleaned["p_activity"].max())
            if task == "regression" and not cleaned.empty
            else None
        ),
        "unique_smiles_validated": len(canonical_cache),
        "unique_proteins_validated": len(protein_cache),
    }

    return DatasetValidationReport(
        total_rows=len(dataframe),
        valid_rows=len(cleaned),
        invalid_rows=len(errors_df),
        duplicate_rows=duplicate_rows,
        conflicting_groups=conflicting_groups,
        errors=errors_df,
        duplicates=duplicates,
        conflicts=conflicts,
        cleaned=cleaned,
        summary=summary,
    )
