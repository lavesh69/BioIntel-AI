from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

_VALUE_PATTERN = re.compile(
    r"^\s*(?P<relation><=|>=|≤|≥|<|>|~|≈)?\s*"
    r"(?P<value>[0-9][0-9,]*(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)"
)

_ALIASES = {
    "smiles": ("Ligand SMILES", "SMILES", "Canonical SMILES"),
    "sequence": ("BindingDB Target Chain  Sequence", "Target Sequence", "Sequence"),
    "target_name": ("Target Name Assigned by Curator or DataSource", "Target Name"),
    "uniprot": ("UniProt (SwissProt) Primary ID of Target Chain", "UniProt ID"),
    "organism": ("Target Source Organism According to Curator or DataSource", "Organism"),
    "assay_id": ("BindingDB Reactant_set_id", "Reactant_set_id"),
    "publication_id": ("PubMed ID", "PMID", "DOI"),
    "ki": ("Ki (nM)",),
    "kd": ("Kd (nM)",),
    "ic50": ("IC50 (nM)",),
    "ec50": ("EC50 (nM)",),
}

@dataclass(frozen=True)
class BindingDBLoadResult:
    rows_read: int
    records_emitted: int
    rejected_records: int
    source_path: str

def parse_activity_cell(value: object) -> tuple[str, float] | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    match = _VALUE_PATTERN.match(str(value))
    if not match:
        return None
    relation = match.group("relation") or "="
    numeric = float(match.group("value").replace(",", ""))
    return relation, numeric

def _column(frame: pd.DataFrame, key: str) -> str | None:
    for candidate in _ALIASES[key]:
        if candidate in frame.columns:
            return candidate
    return None

def bindingdb_to_activity_frame(path: str | Path, *, chunksize: int | None = None) -> pd.DataFrame:
    source = Path(path).resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    reader: Any = pd.read_csv(source, sep="\t", dtype=str, low_memory=False, chunksize=chunksize)
    chunks = reader if chunksize else [reader]
    output: list[dict[str, Any]] = []
    for chunk in chunks:
        smiles_col, sequence_col = _column(chunk, "smiles"), _column(chunk, "sequence")
        if not smiles_col or not sequence_col:
            raise ValueError("BindingDB file does not contain a recognised SMILES and target-sequence column.")
        optional = {key: _column(chunk, key) for key in ("target_name","uniprot","organism","assay_id","publication_id")}
        endpoints = [(name.upper(), _column(chunk, name)) for name in ("ki","kd","ic50","ec50")]
        for _, row in chunk.iterrows():
            for activity_type, activity_col in endpoints:
                if not activity_col:
                    continue
                parsed = parse_activity_cell(row.get(activity_col))
                if not parsed:
                    continue
                relation, numeric = parsed
                output.append({
                    "canonical_smiles": row.get(smiles_col),
                    "protein_sequence": row.get(sequence_col),
                    "standard_value": numeric,
                    "standard_units": "nM",
                    "standard_relation": relation,
                    "activity_type": activity_type,
                    "target_name": row.get(optional["target_name"]) if optional["target_name"] else None,
                    "uniprot_accession": row.get(optional["uniprot"]) if optional["uniprot"] else None,
                    "organism": row.get(optional["organism"]) if optional["organism"] else None,
                    "assay_id": row.get(optional["assay_id"]) if optional["assay_id"] else None,
                    "publication_id": row.get(optional["publication_id"]) if optional["publication_id"] else None,
                    "source_record_id": row.get(optional["assay_id"]) if optional["assay_id"] else None,
                    "source_database": "bindingdb",
                })
    return pd.DataFrame(output)

def bindingdb_load_summary(path: str | Path) -> BindingDBLoadResult:
    frame = bindingdb_to_activity_frame(path)
    return BindingDBLoadResult(0, len(frame), 0, str(Path(path).resolve()))
