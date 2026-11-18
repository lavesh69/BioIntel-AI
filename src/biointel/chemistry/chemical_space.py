from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import MACCSkeys, rdFingerprintGenerator
from rdkit.ML.Cluster import Butina
from sklearn.decomposition import PCA

from biointel.chemistry.standardization import standardize_molecule


@lru_cache(maxsize=8)
def _fingerprint_generator(kind: str):
    normalized = kind.strip().lower()
    if normalized == "morgan":
        return rdFingerprintGenerator.GetMorganGenerator(
            radius=2, fpSize=2048, includeChirality=True
        )
    if normalized in {"atom_pair", "atompair"}:
        return rdFingerprintGenerator.GetAtomPairGenerator(
            fpSize=2048, includeChirality=True
        )
    if normalized in {"torsion", "topological_torsion"}:
        return rdFingerprintGenerator.GetTopologicalTorsionGenerator(
            fpSize=2048, includeChirality=True
        )
    if normalized in {"maccs", "rdkit", "topological"}:
        return None
    raise ValueError(f"Unsupported fingerprint kind: {kind}")


def fingerprint(mol: Chem.Mol, kind: str = "Morgan"):
    normalized = kind.strip().lower()
    generator = _fingerprint_generator(normalized)
    if generator is not None:
        return generator.GetFingerprint(mol)
    if normalized == "maccs":
        return MACCSkeys.GenMACCSKeys(mol)
    return Chem.RDKFingerprint(mol, fpSize=2048)


def _validate_rows(
    rows: pd.DataFrame,
    *,
    smiles_column: str,
    id_column: str,
    extra_columns: tuple[str, ...] = (),
) -> tuple[list[str], list[str]]:
    required = [smiles_column, *extra_columns]
    missing = [column for column in required if column not in rows.columns]
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(missing))
    identifiers = (
        rows[id_column].astype(str).tolist()
        if id_column in rows.columns
        else [str(value) for value in rows.index]
    )
    if len(set(identifiers)) != len(identifiers):
        raise ValueError(f"Identifier column '{id_column}' must contain unique values")
    smiles_values = rows[smiles_column].astype(str).tolist()
    return identifiers, smiles_values


def _prepare_fingerprints(
    rows: pd.DataFrame,
    *,
    smiles_column: str,
    id_column: str,
    fingerprint_kind: str,
) -> tuple[list[str], list[object]]:
    identifiers, smiles_values = _validate_rows(
        rows, smiles_column=smiles_column, id_column=id_column
    )
    fingerprints: list[object] = []
    for identifier, smiles in zip(identifiers, smiles_values, strict=True):
        try:
            mol, _ = standardize_molecule(smiles)
        except Exception as exc:
            raise ValueError(f"Invalid molecule for '{identifier}': {exc}") from exc
        fingerprints.append(fingerprint(mol, fingerprint_kind))
    return identifiers, fingerprints


def similarity_matrix(
    rows: pd.DataFrame,
    *,
    smiles_column: str = "standardized_smiles",
    id_column: str = "compound_id",
    fingerprint_kind: str = "Morgan",
) -> pd.DataFrame:
    identifiers, fps = _prepare_fingerprints(
        rows,
        smiles_column=smiles_column,
        id_column=id_column,
        fingerprint_kind=fingerprint_kind,
    )
    count = len(fps)
    matrix = np.eye(count, dtype=np.float32)
    for index in range(1, count):
        similarities = DataStructs.BulkTanimotoSimilarity(fps[index], fps[:index])
        matrix[index, :index] = similarities
        matrix[:index, index] = similarities
    return pd.DataFrame(matrix, index=identifiers, columns=identifiers)


def consensus_similarity(
    first_smiles: str,
    second_smiles: str,
    *,
    fingerprint_kinds: tuple[str, ...] = (
        "Morgan",
        "MACCS",
        "RDKit",
        "AtomPair",
        "Torsion",
    ),
) -> dict[str, object]:
    if not fingerprint_kinds:
        raise ValueError("At least one fingerprint kind is required")
    first, _ = standardize_molecule(first_smiles)
    second, _ = standardize_molecule(second_smiles)
    values = {
        kind: round(
            float(
                DataStructs.TanimotoSimilarity(
                    fingerprint(first, kind), fingerprint(second, kind)
                )
            ),
            6,
        )
        for kind in fingerprint_kinds
    }
    numeric = np.fromiter(values.values(), dtype=float)
    return {
        "fingerprints": values,
        "consensus_mean": round(float(numeric.mean()), 6),
        "consensus_min": round(float(numeric.min()), 6),
        "consensus_max": round(float(numeric.max()), 6),
    }


def butina_clusters(
    rows: pd.DataFrame,
    *,
    smiles_column: str = "standardized_smiles",
    id_column: str = "compound_id",
    fingerprint_kind: str = "Morgan",
    similarity_threshold: float = 0.65,
) -> pd.DataFrame:
    if not 0 < similarity_threshold < 1:
        raise ValueError("similarity_threshold must be between 0 and 1")
    ids, fps = _prepare_fingerprints(
        rows,
        smiles_column=smiles_column,
        id_column=id_column,
        fingerprint_kind=fingerprint_kind,
    )
    if not fps:
        return pd.DataFrame(columns=[id_column, "cluster_id", "cluster_size"])
    distances: list[float] = []
    for index in range(1, len(fps)):
        distances.extend(
            1.0 - value
            for value in DataStructs.BulkTanimotoSimilarity(fps[index], fps[:index])
        )
    clusters = Butina.ClusterData(
        distances,
        len(fps),
        1.0 - similarity_threshold,
        isDistData=True,
        reordering=True,
    )
    cluster_by_index: dict[int, int] = {}
    cluster_sizes: dict[int, int] = {}
    for cluster_id, members in enumerate(clusters, start=1):
        cluster_sizes[cluster_id] = len(members)
        for member in members:
            cluster_by_index[int(member)] = cluster_id
    assigned = [cluster_by_index[index] for index in range(len(ids))]
    return pd.DataFrame(
        {
            id_column: ids,
            "cluster_id": assigned,
            "cluster_size": [cluster_sizes[value] for value in assigned],
        }
    )


def chemical_space_embedding(
    rows: pd.DataFrame,
    *,
    smiles_column: str = "standardized_smiles",
    id_column: str = "compound_id",
    fingerprint_kind: str = "Morgan",
) -> pd.DataFrame:
    ids, fps = _prepare_fingerprints(
        rows,
        smiles_column=smiles_column,
        id_column=id_column,
        fingerprint_kind=fingerprint_kind,
    )
    if not fps:
        return pd.DataFrame(columns=[id_column, "PC1", "PC2", "variance_explained"])
    arrays: list[np.ndarray] = []
    for fp in fps:
        array = np.zeros((fp.GetNumBits(),), dtype=np.uint8)
        DataStructs.ConvertToNumpyArray(fp, array)
        arrays.append(array)
    matrix = np.vstack(arrays)
    if len(matrix) < 2:
        coords = np.zeros((len(matrix), 2), dtype=float)
        variance = [0.0, 0.0]
    else:
        pca = PCA(n_components=2, random_state=42)
        coords = pca.fit_transform(matrix)
        variance = [float(value) for value in pca.explained_variance_ratio_]
    return pd.DataFrame(
        {
            id_column: ids,
            "PC1": coords[:, 0],
            "PC2": coords[:, 1],
            "variance_explained": [variance] * len(ids),
        }
    )


def activity_cliffs(
    rows: pd.DataFrame,
    *,
    smiles_column: str = "standardized_smiles",
    id_column: str = "compound_id",
    activity_column: str = "p_activity",
    similarity_threshold: float = 0.8,
    activity_difference: float = 1.0,
) -> pd.DataFrame:
    if not 0 <= similarity_threshold <= 1:
        raise ValueError("similarity_threshold must be between 0 and 1")
    if activity_difference < 0:
        raise ValueError("activity_difference must be non-negative")
    ids, smiles_values = _validate_rows(
        rows,
        smiles_column=smiles_column,
        id_column=id_column,
        extra_columns=(activity_column,),
    )
    activities = pd.to_numeric(rows[activity_column], errors="coerce").to_numpy(dtype=float)
    if np.isnan(activities).any():
        bad = [ids[index] for index in np.flatnonzero(np.isnan(activities))]
        raise ValueError("Non-numeric activity for: " + ", ".join(bad[:10]))
    fps = []
    for identifier, smiles in zip(ids, smiles_values, strict=True):
        try:
            mol, _ = standardize_molecule(smiles)
        except Exception as exc:
            raise ValueError(f"Invalid molecule for '{identifier}': {exc}") from exc
        fps.append(fingerprint(mol, "Morgan"))

    records: list[dict[str, object]] = []
    for index in range(1, len(fps)):
        similarities = DataStructs.BulkTanimotoSimilarity(fps[index], fps[:index])
        deltas = np.abs(activities[index] - activities[:index])
        for other, (similarity, delta) in enumerate(zip(similarities, deltas, strict=True)):
            if similarity >= similarity_threshold and delta >= activity_difference:
                records.append(
                    {
                        "compound_a": ids[other],
                        "compound_b": ids[index],
                        "tanimoto": round(float(similarity), 6),
                        "activity_difference": round(float(delta), 6),
                    }
                )
    columns = ["compound_a", "compound_b", "tanimoto", "activity_difference"]
    if not records:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame.from_records(records, columns=columns).sort_values(
        ["activity_difference", "tanimoto"], ascending=False, ignore_index=True
    )
