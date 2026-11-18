from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold


@dataclass(frozen=True)
class LeakageAuditResult:
    train_rows: int
    test_rows: int
    exact_compound_overlap: int
    scaffold_overlap: int
    exact_target_overlap: int
    target_cluster_overlap: int
    pair_overlap: int
    passed: bool
    notes: list[str]

def _scaffold(smiles: object) -> str:
    mol = Chem.MolFromSmiles(str(smiles))
    if mol is None:
        return ""
    return MurckoScaffold.MurckoScaffoldSmiles(mol=mol, includeChirality=True)

def _clusters(sequences: pd.Series, identity_prefix: int = 30) -> pd.Series:
    return sequences.astype(str).str.upper().str.replace(r"[^A-Z]", "", regex=True).str[:max(1, identity_prefix)]

def audit_train_test_leakage(train: pd.DataFrame, test: pd.DataFrame, *, smiles_column: str = "canonical_smiles", sequence_column: str = "protein_sequence", target_cluster_column: str | None = None) -> LeakageAuditResult:
    for name, frame in (("train", train), ("test", test)):
        missing = {smiles_column, sequence_column} - set(frame.columns)
        if missing:
            raise ValueError(f"{name} is missing columns: {', '.join(sorted(missing))}")
    train_smiles = set(train[smiles_column].dropna().astype(str))
    test_smiles = set(test[smiles_column].dropna().astype(str))
    train_targets = set(train[sequence_column].dropna().astype(str))
    test_targets = set(test[sequence_column].dropna().astype(str))
    train_scaffolds = {_scaffold(value) for value in train_smiles} - {""}
    test_scaffolds = {_scaffold(value) for value in test_smiles} - {""}
    if target_cluster_column and target_cluster_column in train.columns and target_cluster_column in test.columns:
        train_clusters = set(train[target_cluster_column].dropna().astype(str))
        test_clusters = set(test[target_cluster_column].dropna().astype(str))
    else:
        train_clusters = set(_clusters(train[sequence_column]).dropna())
        test_clusters = set(_clusters(test[sequence_column]).dropna())
    train_pairs = set(zip(train[smiles_column].astype(str), train[sequence_column].astype(str)))
    test_pairs = set(zip(test[smiles_column].astype(str), test[sequence_column].astype(str)))
    counts = {
        "exact_compound_overlap": len(train_smiles & test_smiles),
        "scaffold_overlap": len(train_scaffolds & test_scaffolds),
        "exact_target_overlap": len(train_targets & test_targets),
        "target_cluster_overlap": len(train_clusters & test_clusters),
        "pair_overlap": len(train_pairs & test_pairs),
    }
    notes = [f"{key}={value}" for key, value in counts.items() if value]
    return LeakageAuditResult(
        len(train), len(test), **counts,
        passed=all(value == 0 for value in counts.values()),
        notes=notes or ["No exact compound, scaffold, target, target-cluster or pair overlap detected."],
    )

def leakage_audit_dict(result: LeakageAuditResult) -> dict[str, Any]:
    return asdict(result)
