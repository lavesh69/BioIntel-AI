from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem.MolStandardize import rdMolStandardize

from biointel.data.assay_ontology import classify_assay
from biointel.dti.protein_features import clean_protein_sequence

_UNIT_TO_MOLAR = {
    "m":1.0,"molar":1.0,"mol/l":1.0,
    "mm":1e-3,"millimolar":1e-3,"mmol/l":1e-3,
    "um":1e-6,"µm":1e-6,"μm":1e-6,"micromolar":1e-6,"umol/l":1e-6,"µmol/l":1e-6,"μmol/l":1e-6,
    "nm":1e-9,"nanomolar":1e-9,"nmol/l":1e-9,
    "pm":1e-12,"picomolar":1e-12,"pmol/l":1e-12,
    "fm":1e-15,"femtomolar":1e-15,"fmol/l":1e-15,
}
_RELATION_ALIASES = {"":"=","=":"=","==":"=","EQ":"=","<":"<","≤":"<=","<=":"<=","=<":"<=","LT":"<",">":">","≥":">=",">=":">=","=>":">=","GT":">","~":"~","≈":"~"}

@dataclass(frozen=True)
class StandardizedCompound:
    input_smiles: str
    canonical_smiles: str
    inchikey: str
    formula: str
    fragment_count: int

@dataclass(frozen=True)
class StandardizedTarget:
    sequence: str
    sequence_sha256: str
    sequence_length: int
    uniprot_accession: str | None
    organism: str | None

@dataclass(frozen=True)
class ActivityValue:
    raw_value: float
    raw_unit: str
    molar_value: float
    p_activity: float
    relation: str
    censored: bool
    p_activity_lower_bound: float | None = None
    p_activity_upper_bound: float | None = None

@dataclass(frozen=True)
class CurationSummary:
    input_rows: int
    curated_rows: int
    invalid_rows: int
    exact_measurements: int
    censored_measurements: int
    duplicate_groups: int
    conflict_groups: int
    active_rows: int
    inactive_rows: int
    unknown_rows: int
    generated_at_utc: str
    publication_linked_rows: int = 0
    licensed_rows: int = 0
    review_pending_rows: int = 0

def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text and text.lower() not in {"nan","none","null"} else None

def normalize_relation(relation: object) -> str:
    cleaned = str(relation or "").strip().upper()
    if cleaned not in _RELATION_ALIASES:
        raise ValueError(f"Unsupported activity relation: {relation!r}.")
    return _RELATION_ALIASES[cleaned]

def normalize_activity_value(value: object, unit: object, relation: object = "=") -> ActivityValue:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValueError("Activity value must be a finite positive number.")
    normalized_unit = str(unit).strip().lower().replace(" ", "")
    if normalized_unit not in _UNIT_TO_MOLAR:
        raise ValueError(f"Unsupported activity unit {unit!r}. Supported units: M, mM, uM, nM, pM, fM.")
    rel = normalize_relation(relation)
    molar = numeric * _UNIT_TO_MOLAR[normalized_unit]
    p_activity = -math.log10(molar)
    lower = upper = None
    if rel == "=":
        lower = upper = p_activity
    elif rel in {"<","<="}:
        lower = p_activity
    elif rel in {">",">="}:
        upper = p_activity
    return ActivityValue(numeric, str(unit), molar, p_activity, rel, rel != "=", lower, upper)

def standardize_compound(smiles: object) -> StandardizedCompound:
    raw = str(smiles).strip()
    if not raw:
        raise ValueError("SMILES is empty.")
    mol = Chem.MolFromSmiles(raw)
    if mol is None:
        raise ValueError("SMILES could not be parsed by RDKit.")
    fragment_count = len(Chem.GetMolFrags(mol))
    parent = rdMolStandardize.FragmentParent(rdMolStandardize.Cleanup(mol))
    uncharged = rdMolStandardize.Uncharger().uncharge(parent)
    canonical_mol = rdMolStandardize.TautomerEnumerator().Canonicalize(uncharged)
    Chem.SanitizeMol(canonical_mol)
    canonical = Chem.MolToSmiles(canonical_mol, canonical=True, isomericSmiles=True)
    from rdkit.Chem import rdMolDescriptors
    return StandardizedCompound(raw, canonical, Chem.MolToInchiKey(canonical_mol), rdMolDescriptors.CalcMolFormula(canonical_mol), fragment_count)

def standardize_target(sequence: object, uniprot_accession: object | None = None, organism: object | None = None) -> StandardizedTarget:
    cleaned = clean_protein_sequence(str(sequence))
    return StandardizedTarget(cleaned, hashlib.sha256(cleaned.encode()).hexdigest(), len(cleaned), (_optional_text(uniprot_accession) or "").upper() or None, _optional_text(organism))

def assay_quality_score(row: pd.Series | dict[str, Any]) -> float:
    get = row.get
    score = 0.30
    if normalize_relation(get("standard_relation", get("relation", "="))) == "=":
        score += 0.20
    confidence = pd.to_numeric(get("confidence_score", np.nan), errors="coerce")
    if pd.notna(confidence):
        score += 0.20 * min(max(float(confidence) / 9.0, 0.0), 1.0)
    replicates = pd.to_numeric(get("replicate_count", np.nan), errors="coerce")
    if pd.notna(replicates):
        score += 0.10 * min(max(float(replicates), 0.0) / 3.0, 1.0)
    for key, increment in (("assay_id",0.05),("publication_id",0.05),("source_database",0.05),("license_id",0.05)):
        if _optional_text(get(key)):
            score += increment
    return round(min(score, 1.0), 4)

def _activity_state(activity: ActivityValue, threshold: float) -> str:
    if activity.relation == "=":
        return "active" if activity.p_activity >= threshold else "inactive"
    if activity.p_activity_lower_bound is not None and activity.p_activity_lower_bound >= threshold:
        return "active"
    if activity.p_activity_upper_bound is not None and activity.p_activity_upper_bound < threshold:
        return "inactive"
    return "unknown"

def _evidence_key(record: dict[str, Any]) -> str:
    identity = "|".join(str(record.get(key) or "") for key in ("source_database","source_record_id","assay_id","compound_inchikey","target_sequence_sha256","activity_type","p_activity","activity_relation"))
    return hashlib.sha256(identity.encode()).hexdigest()

def curate_activity_dataset(dataframe: pd.DataFrame, *, smiles_column: str = "canonical_smiles", sequence_column: str = "protein_sequence", value_column: str = "standard_value", unit_column: str = "standard_units", relation_column: str = "standard_relation", activity_type_column: str = "activity_type", active_threshold: float = 6.0, aggregate_duplicates: bool = True, conflict_spread_log_units: float = 1.0, source_database: str = "local_import") -> tuple[pd.DataFrame,pd.DataFrame,CurationSummary]:
    missing = {smiles_column,sequence_column,value_column,unit_column} - set(dataframe.columns)
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))
    curated, errors = [], []
    imported_at = datetime.now(UTC).isoformat(timespec="seconds")
    for position, (_, row) in enumerate(dataframe.iterrows()):
        try:
            compound = standardize_compound(row[smiles_column])
            target = standardize_target(row[sequence_column], row.get("uniprot_accession"), row.get("organism"))
            relation = row.get(relation_column, "=") if relation_column in row else "="
            activity = normalize_activity_value(row[value_column], row[unit_column], relation)
            activity_type = str(row.get(activity_type_column, "unspecified") or "unspecified").upper()
            source = _optional_text(row.get("source_database")) or source_database
            ontology = classify_assay(activity_type, row.get("assay_type"), row.get("assay_description"))
            record = row.to_dict()
            record.update({
                "source_row_number":position+2,"source_database":source,"imported_at_utc":imported_at,
                "input_smiles":compound.input_smiles,"canonical_smiles":compound.canonical_smiles,
                "compound_inchikey":compound.inchikey,"molecular_formula":compound.formula,
                "input_fragment_count":compound.fragment_count,"protein_sequence":target.sequence,
                "target_sequence_sha256":target.sequence_sha256,"target_sequence_length":target.sequence_length,
                "uniprot_accession":target.uniprot_accession,"organism":target.organism,
                "activity_type":activity_type,"activity_value_molar":activity.molar_value,
                "p_activity":activity.p_activity,"p_activity_lower_bound":activity.p_activity_lower_bound,
                "p_activity_upper_bound":activity.p_activity_upper_bound,"activity_relation":activity.relation,
                "is_censored":activity.censored,"activity_state":_activity_state(activity, active_threshold),
                "endpoint_family":ontology.endpoint_family,"assay_category":ontology.assay_category,
                "publication_id":_optional_text(row.get("publication_id", row.get("document_id"))),
                "license_id":_optional_text(row.get("license_id")),
                "review_status":_optional_text(row.get("review_status")) or "pending",
            })
            record["assay_quality_score"] = assay_quality_score(record)
            record["evidence_key"] = _evidence_key(record)
            curated.append(record)
        except Exception as exc:
            errors.append({"source_row_number":position+2,"error":str(exc),"input_smiles":row.get(smiles_column,""),"activity_value":row.get(value_column,""),"activity_unit":row.get(unit_column,"")})
    curated_df = pd.DataFrame(curated)
    errors_df = pd.DataFrame(errors, columns=["source_row_number","error","input_smiles","activity_value","activity_unit"])
    duplicate_groups = conflict_groups = 0
    if not curated_df.empty:
        groups = ["compound_inchikey","target_sequence_sha256","activity_type"]
        sizes = curated_df.groupby(groups, dropna=False).size()
        duplicate_groups = int((sizes > 1).sum())
        spreads = curated_df.groupby(groups, dropna=False)["p_activity"].agg(lambda values: float(values.max()-values.min()))
        conflicts = spreads >= float(conflict_spread_log_units)
        conflict_groups = int(conflicts.sum())
        keys = set(conflicts[conflicts].index.tolist())
        curated_df["conflict_flag"] = [tuple(values) in keys for values in curated_df[groups].itertuples(index=False, name=None)]
        curated_df["duplicate_count"] = curated_df.groupby(groups, dropna=False)["p_activity"].transform("size")
        if aggregate_duplicates:
            exact = curated_df[~curated_df["is_censored"]].copy()
            censored = curated_df[curated_df["is_censored"]].copy()
            if not exact.empty:
                aggregations: dict[str, Any] = {
                    "p_activity":"median","activity_value_molar":"median","assay_quality_score":"max",
                    "source_row_number":lambda values: ",".join(map(str, values)),
                    "source_database":lambda values: ",".join(sorted(set(map(str, values)))),
                    "duplicate_count":"max","conflict_flag":"max",
                }
                for column in exact.columns:
                    if column not in groups and column not in aggregations:
                        aggregations[column] = "first"
                exact = exact.groupby(groups, dropna=False, as_index=False).agg(aggregations)
                exact["activity_state"] = exact["p_activity"].map(lambda x: "active" if float(x) >= active_threshold else "inactive")
            curated_df = pd.concat([exact,censored], ignore_index=True, sort=False)
        curated_df = curated_df.sort_values(["assay_quality_score","p_activity"], ascending=[False,False]).reset_index(drop=True)
    states = curated_df.get("activity_state", pd.Series(dtype=str)).value_counts()
    summary = CurationSummary(
        len(dataframe),len(curated_df),len(errors_df),
        int((~curated_df["is_censored"]).sum()) if not curated_df.empty else 0,
        int(curated_df["is_censored"].sum()) if not curated_df.empty else 0,
        duplicate_groups,conflict_groups,int(states.get("active",0)),int(states.get("inactive",0)),int(states.get("unknown",0)),imported_at,
        int(curated_df.get("publication_id",pd.Series(dtype=object)).notna().sum()) if not curated_df.empty else 0,
        int(curated_df.get("license_id",pd.Series(dtype=object)).notna().sum()) if not curated_df.empty else 0,
        int((curated_df.get("review_status",pd.Series(dtype=str))=="pending").sum()) if not curated_df.empty else 0,
    )
    return curated_df, errors_df, summary

def curation_summary_dict(summary: CurationSummary) -> dict[str, Any]:
    return asdict(summary)
