from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from biointel.training.scaffold import murcko_scaffold_smiles


@dataclass(frozen=True)
class BiasReport:
    rows: int
    unique_drugs: int
    unique_targets: int
    unique_scaffolds: int
    top_drug_fraction: float
    top_target_fraction: float
    top_scaffold_fraction: float
    source_concentration: float | None
    activity_balance: dict[str, int]
    warnings: tuple[str, ...]


def _top_fraction(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    return float(series.value_counts(dropna=False).iloc[0] / len(series))


def analyze_dataset_bias(
    dataframe: pd.DataFrame,
    *,
    drug_column: str = "compound_inchikey",
    target_column: str = "target_sequence_sha256",
    smiles_column: str = "canonical_smiles",
) -> BiasReport:
    if dataframe.empty:
        return BiasReport(0, 0, 0, 0, 0.0, 0.0, 0.0, None, {}, ("Dataset is empty.",))
    drugs = (
        dataframe[drug_column].astype(str)
        if drug_column in dataframe
        else dataframe[smiles_column].astype(str)
    )
    targets = (
        dataframe[target_column].astype(str)
        if target_column in dataframe
        else dataframe.get("target_id", pd.Series(["unknown"] * len(dataframe))).astype(str)
    )
    scaffolds = dataframe[smiles_column].astype(str).map(murcko_scaffold_smiles)
    top_drug = _top_fraction(drugs)
    top_target = _top_fraction(targets)
    top_scaffold = _top_fraction(scaffolds)
    source_fraction = (
        _top_fraction(dataframe["source_database"].astype(str))
        if "source_database" in dataframe
        else None
    )
    states = (
        dataframe["activity_state"].astype(str).value_counts().to_dict()
        if "activity_state" in dataframe
        else {}
    )
    warnings: list[str] = []
    if top_drug > 0.10:
        warnings.append("A single compound contributes more than 10% of rows.")
    if top_target > 0.15:
        warnings.append("A single target contributes more than 15% of rows.")
    if top_scaffold > 0.20:
        warnings.append("A single scaffold contributes more than 20% of rows.")
    if source_fraction is not None and source_fraction > 0.80:
        warnings.append("More than 80% of rows originate from one source database.")
    if states and min(states.values()) / max(sum(states.values()), 1) < 0.10:
        warnings.append("Activity labels are strongly imbalanced.")
    return BiasReport(
        rows=len(dataframe),
        unique_drugs=int(drugs.nunique()),
        unique_targets=int(targets.nunique()),
        unique_scaffolds=int(scaffolds.nunique()),
        top_drug_fraction=top_drug,
        top_target_fraction=top_target,
        top_scaffold_fraction=top_scaffold,
        source_concentration=source_fraction,
        activity_balance={str(k): int(v) for k, v in states.items()},
        warnings=tuple(warnings),
    )
