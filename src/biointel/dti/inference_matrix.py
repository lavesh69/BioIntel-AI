from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from biointel.dti.drug_features import DrugFeatureSet, extract_drug_features
from biointel.dti.feature_cache import FeatureCache
from biointel.dti.feature_combiner import FeatureSchema
from biointel.dti.protein_features import ProteinFeatureSet, extract_protein_features


@dataclass(frozen=True)
class InferenceMatrixResult:
    matrix: np.ndarray
    valid_rows: pd.DataFrame
    errors: pd.DataFrame
    feature_names: tuple[str, ...]
    schema: FeatureSchema
    canonical_smiles: tuple[str, ...]
    protein_lengths: tuple[int, ...]
    cache_summary: dict[str, int | str | bool]


def _feature_hash(names: tuple[str, ...]) -> str:
    return hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()


def _worker_count(n_jobs: int | None) -> int:
    if n_jobs is None or n_jobs == 0:
        return min(max(os.cpu_count() or 1, 1), 8)
    return min(max(int(n_jobs), 1), 32)


def _parallel_map(
    values: list[str], function, workers: int
) -> tuple[dict[str, object], dict[str, str]]:
    output: dict[str, object] = {}
    errors: dict[str, str] = {}
    if workers == 1:
        for value in values:
            try:
                output[value] = function(value)
            except Exception as exc:
                errors[value] = str(exc)
        return output, errors
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="biointel-features") as pool:
        future_map = {pool.submit(function, value): value for value in values}
        for future in as_completed(future_map):
            value = future_map[future]
            try:
                output[value] = future.result()
            except Exception as exc:
                errors[value] = str(exc)
    return output, errors


def build_inference_matrix(
    dataframe: pd.DataFrame,
    *,
    radius: int = 2,
    n_bits: int = 2048,
    use_chirality: bool = True,
    include_dipeptides: bool = False,
    n_jobs: int | None = 0,
    cache_path: str | Path | None = None,
) -> InferenceMatrixResult:
    required = {"canonical_smiles", "protein_sequence"}
    missing = required - set(dataframe.columns)
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))
    source = dataframe.copy().reset_index(drop=True)
    source["_source_position"] = np.arange(len(source), dtype=np.int64)
    source["_normalized_smiles"] = source["canonical_smiles"].fillna("").astype(str).str.strip()
    source["_normalized_sequence"] = (
        source["protein_sequence"]
        .fillna("")
        .astype(str)
        .str.replace(r"\s+", "", regex=True)
        .str.upper()
    )

    workers = _worker_count(n_jobs)
    persistent = FeatureCache(cache_path) if cache_path is not None else None
    unique_smiles = list(dict.fromkeys(source["_normalized_smiles"].tolist()))
    unique_sequences = list(dict.fromkeys(source["_normalized_sequence"].tolist()))
    drug_cache: dict[str, DrugFeatureSet] = {}
    protein_cache: dict[str, ProteinFeatureSet] = {}
    persistent_drug_hits = 0
    persistent_protein_hits = 0

    if persistent is not None:
        for value in unique_smiles:
            cached = persistent.get_drug(
                value, radius=radius, n_bits=n_bits, use_chirality=use_chirality
            )
            if cached is not None:
                drug_cache[value] = cached
                persistent_drug_hits += 1
        for value in unique_sequences:
            cached = persistent.get_protein(value, include_dipeptides=include_dipeptides)
            if cached is not None:
                protein_cache[value] = cached
                persistent_protein_hits += 1

    missing_smiles = [value for value in unique_smiles if value not in drug_cache]
    missing_sequences = [value for value in unique_sequences if value not in protein_cache]
    new_drugs, drug_errors = _parallel_map(
        missing_smiles,
        lambda value: extract_drug_features(value, radius, n_bits, use_chirality),
        workers,
    )
    new_proteins, protein_errors = _parallel_map(
        missing_sequences,
        lambda value: extract_protein_features(value, include_dipeptides),
        workers,
    )
    drug_cache.update(new_drugs)  # type: ignore[arg-type]
    protein_cache.update(new_proteins)  # type: ignore[arg-type]
    if persistent is not None:
        for value, feature in new_drugs.items():
            persistent.put_drug(value, feature)  # type: ignore[arg-type]
        for value, feature in new_proteins.items():
            persistent.put_protein(value, feature)  # type: ignore[arg-type]

    valid_mask = source["_normalized_smiles"].isin(drug_cache) & source[
        "_normalized_sequence"
    ].isin(protein_cache)
    error_rows: list[dict[str, object]] = []
    for _, row in source.loc[~valid_mask].iterrows():
        messages: list[str] = []
        smiles = row["_normalized_smiles"]
        sequence = row["_normalized_sequence"]
        if smiles in drug_errors:
            messages.append(f"Drug feature error: {drug_errors[smiles]}")
        if sequence in protein_errors:
            messages.append(f"Protein feature error: {protein_errors[sequence]}")
        error_rows.append(
            {
                "_source_position": int(row["_source_position"]),
                "sample_id": row.get("sample_id", int(row["_source_position"]) + 1),
                "canonical_smiles": row.get("canonical_smiles", ""),
                "error": "; ".join(messages) or "Feature extraction failed.",
            }
        )

    valid = source.loc[valid_mask].copy().reset_index(drop=True)
    if valid.empty:
        empty_schema = FeatureSchema(
            schema_version="2.0.0",
            feature_count=0,
            feature_hash=_feature_hash(tuple()),
            fingerprint_radius=radius,
            fingerprint_bits=n_bits,
            use_chirality=use_chirality,
            include_dipeptides=include_dipeptides,
            drug_feature_count=0,
            protein_feature_count=0,
        )
        return InferenceMatrixResult(
            np.empty((0, 0), dtype=np.float32),
            valid,
            pd.DataFrame(error_rows),
            tuple(),
            empty_schema,
            tuple(),
            tuple(),
            {
                "workers": workers,
                "persistent_cache": persistent is not None,
                "unique_drugs": len(unique_smiles),
                "unique_targets": len(unique_sequences),
                "persistent_drug_hits": persistent_drug_hits,
                "persistent_protein_hits": persistent_protein_hits,
            },
        )

    used_smiles = list(dict.fromkeys(valid["_normalized_smiles"].tolist()))
    used_sequences = list(dict.fromkeys(valid["_normalized_sequence"].tolist()))
    drug_index = {value: index for index, value in enumerate(used_smiles)}
    protein_index = {value: index for index, value in enumerate(used_sequences)}
    drug_matrix = np.vstack([drug_cache[value].values for value in used_smiles]).astype(
        np.float32, copy=False
    )
    protein_matrix = np.vstack([protein_cache[value].values for value in used_sequences]).astype(
        np.float32, copy=False
    )
    drug_rows = valid["_normalized_smiles"].map(drug_index).to_numpy(dtype=np.int32)
    protein_rows = valid["_normalized_sequence"].map(protein_index).to_numpy(dtype=np.int32)
    matrix = np.empty(
        (len(valid), drug_matrix.shape[1] + protein_matrix.shape[1]), dtype=np.float32
    )
    matrix[:, : drug_matrix.shape[1]] = drug_matrix[drug_rows]
    matrix[:, drug_matrix.shape[1] :] = protein_matrix[protein_rows]
    first_drug = drug_cache[used_smiles[0]]
    first_protein = protein_cache[used_sequences[0]]
    names = first_drug.names + first_protein.names
    schema = FeatureSchema(
        schema_version="2.0.0",
        feature_count=len(names),
        feature_hash=_feature_hash(names),
        fingerprint_radius=radius,
        fingerprint_bits=n_bits,
        use_chirality=use_chirality,
        include_dipeptides=include_dipeptides,
        drug_feature_count=len(first_drug.names),
        protein_feature_count=len(first_protein.names),
    )
    canonical = tuple(drug_cache[value].canonical_smiles for value in valid["_normalized_smiles"])
    lengths = tuple(
        int(protein_cache[value].sequence_length) for value in valid["_normalized_sequence"]
    )
    return InferenceMatrixResult(
        matrix=matrix,
        valid_rows=valid,
        errors=pd.DataFrame(
            error_rows,
            columns=["_source_position", "sample_id", "canonical_smiles", "error"],
        ),
        feature_names=names,
        schema=schema,
        canonical_smiles=canonical,
        protein_lengths=lengths,
        cache_summary={
            "workers": workers,
            "persistent_cache": persistent is not None,
            "unique_drugs": len(used_smiles),
            "unique_targets": len(used_sequences),
            "persistent_drug_hits": persistent_drug_hits,
            "persistent_protein_hits": persistent_protein_hits,
            "drug_reuse_hits": len(valid) - len(used_smiles),
            "protein_reuse_hits": len(valid) - len(used_sequences),
            "matrix_bytes": int(matrix.nbytes),
        },
    )
