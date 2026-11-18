from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd
from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator, rdFMCS
from rdkit.Chem.Scaffolds import MurckoScaffold

from biointel.chemistry.standardization import standardize_molecule


@dataclass(frozen=True)
class PairSimilarity:
    tanimoto: float
    same_scaffold: bool
    first_scaffold: str
    second_scaffold: str
    mcs_smarts: str
    mcs_atoms: int
    mcs_bonds: int
    timed_out: bool


def _fp(mol: Chem.Mol, *, radius: int = 2, n_bits: int = 2048):
    return rdFingerprintGenerator.GetMorganGenerator(
        radius=radius,
        fpSize=n_bits,
        includeChirality=True,
    ).GetFingerprint(mol)


def compare_molecules(
    first_smiles: str,
    second_smiles: str,
    *,
    radius: int = 2,
    n_bits: int = 2048,
    mcs_timeout_seconds: int = 3,
) -> PairSimilarity:
    first, _ = standardize_molecule(first_smiles)
    second, _ = standardize_molecule(second_smiles)
    first_fp = _fp(first, radius=radius, n_bits=n_bits)
    second_fp = _fp(second, radius=radius, n_bits=n_bits)
    tanimoto = float(DataStructs.TanimotoSimilarity(first_fp, second_fp))
    first_scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=first, includeChirality=True)
    second_scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=second, includeChirality=True)
    mcs = rdFMCS.FindMCS(
        [first, second],
        timeout=max(1, int(mcs_timeout_seconds)),
        ringMatchesRingOnly=True,
        completeRingsOnly=True,
        matchChiralTag=True,
    )
    return PairSimilarity(
        tanimoto=round(tanimoto, 6),
        same_scaffold=bool(first_scaffold and first_scaffold == second_scaffold),
        first_scaffold=first_scaffold,
        second_scaffold=second_scaffold,
        mcs_smarts=mcs.smartsString,
        mcs_atoms=int(mcs.numAtoms),
        mcs_bonds=int(mcs.numBonds),
        timed_out=bool(mcs.canceled),
    )


def similarity_search(
    query_smiles: str,
    rows: Iterable[dict[str, object]] | pd.DataFrame,
    *,
    smiles_column: str = "smiles",
    name_column: str = "name",
    top_n: int = 20,
    radius: int = 2,
    n_bits: int = 2048,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    query_mol, query_std = standardize_molecule(query_smiles)
    query_fp = _fp(query_mol, radius=radius, n_bits=n_bits)
    query_scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=query_mol, includeChirality=True)
    records = rows.to_dict("records") if isinstance(rows, pd.DataFrame) else list(rows)
    hits: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for index, row in enumerate(records):
        raw_smiles = str(row.get(smiles_column, "")).strip()
        name = str(row.get(name_column, f"row_{index + 1}"))
        try:
            mol, std = standardize_molecule(raw_smiles)
            fp = _fp(mol, radius=radius, n_bits=n_bits)
            similarity = float(DataStructs.TanimotoSimilarity(query_fp, fp))
            scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=True)
            hits.append(
                {
                    "name": name,
                    "input_smiles": raw_smiles,
                    "standardized_smiles": std.standardized_smiles,
                    "inchikey": std.inchikey,
                    "tanimoto": round(similarity, 6),
                    "same_scaffold": bool(query_scaffold and scaffold == query_scaffold),
                    "scaffold_smiles": scaffold,
                    "exact_structure": std.standardized_smiles == query_std.standardized_smiles,
                }
            )
        except Exception as exc:
            failures.append({"row": index + 1, "name": name, "input_smiles": raw_smiles, "error": str(exc)})
    result = pd.DataFrame(hits)
    if not result.empty:
        result = result.sort_values(["tanimoto", "same_scaffold"], ascending=[False, False]).head(max(1, int(top_n))).reset_index(drop=True)
    return result, pd.DataFrame(failures)


def greedy_diverse_subset(
    rows: pd.DataFrame,
    *,
    smiles_column: str = "standardized_smiles",
    size: int = 10,
    radius: int = 2,
    n_bits: int = 2048,
) -> pd.DataFrame:
    if rows.empty:
        return rows.copy()
    valid: list[tuple[int, object]] = []
    for idx, value in rows[smiles_column].items():
        try:
            mol, _ = standardize_molecule(str(value))
            valid.append((idx, _fp(mol, radius=radius, n_bits=n_bits)))
        except Exception:
            continue
    if not valid:
        return rows.iloc[0:0].copy()
    selected = [valid[0]]
    remaining = valid[1:]
    while remaining and len(selected) < min(size, len(valid)):
        next_item = max(
            remaining,
            key=lambda candidate: min(
                1.0 - float(DataStructs.TanimotoSimilarity(candidate[1], chosen[1]))
                for chosen in selected
            ),
        )
        selected.append(next_item)
        remaining.remove(next_item)
    return rows.loc[[idx for idx, _ in selected]].reset_index(drop=True)
