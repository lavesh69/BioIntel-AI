from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlencode, urljoin

import pandas as pd

from biointel.chemistry.standardization import standardize_molecule
from biointel.data.curation import normalize_relation
from biointel.dti.activity import standardize_activity
from biointel.integrations.http_client import Transport, default_transport, get_json
from biointel.integrations.uniprot import fetch_uniprot_fasta

CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data/"
SUPPORTED_TYPES = {"KD", "KI", "IC50", "EC50"}
MULTI_COMPONENT_POLICIES = {"block", "select", "first_with_warning"}


@dataclass(frozen=True)
class ChEMBLActivityQuery:
    target_chembl_id: str
    activity_type: str = "IC50"
    task_type: str = "regression"
    classification_threshold_nm: float = 1000.0
    max_records: int = 1000
    require_exact_relation: bool = True
    resolve_missing_smiles: bool = True
    protein_sequence_override: str | None = None
    multi_component_policy: str = "block"
    selected_uniprot_accession: str | None = None
    aggregate_replicates: bool = True
    conflict_threshold_log_units: float = 1.0
    include_assay_context: bool = True


@dataclass(frozen=True)
class ChEMBLDatasetResult:
    dataset: pd.DataFrame
    rejected: pd.DataFrame
    metadata: dict[str, object]


def _normalize(query: ChEMBLActivityQuery) -> ChEMBLActivityQuery:
    target = query.target_chembl_id.strip().upper()
    if not target.startswith("CHEMBL") or not target[6:].isdigit():
        raise ValueError("Target identifier must look like CHEMBL204.")
    activity_type = query.activity_type.strip().upper()
    if activity_type not in SUPPORTED_TYPES:
        raise ValueError("Activity type must be Kd, Ki, IC50 or EC50.")
    if query.task_type not in {"classification", "regression"}:
        raise ValueError("task_type must be classification or regression")
    if not 1 <= query.max_records <= 10000:
        raise ValueError("max_records must be between 1 and 10,000.")
    policy = query.multi_component_policy.strip().lower()
    if policy not in MULTI_COMPONENT_POLICIES:
        raise ValueError(
            "multi_component_policy must be block, select or first_with_warning"
        )
    if float(query.conflict_threshold_log_units) <= 0:
        raise ValueError("conflict_threshold_log_units must be positive")
    return ChEMBLActivityQuery(
        target_chembl_id=target,
        activity_type=activity_type,
        task_type=query.task_type,
        classification_threshold_nm=float(query.classification_threshold_nm),
        max_records=int(query.max_records),
        require_exact_relation=bool(query.require_exact_relation),
        resolve_missing_smiles=bool(query.resolve_missing_smiles),
        protein_sequence_override=(
            query.protein_sequence_override.strip().upper()
            if query.protein_sequence_override
            else None
        ),
        multi_component_policy=policy,
        selected_uniprot_accession=(
            query.selected_uniprot_accession.strip().upper()
            if query.selected_uniprot_accession
            else None
        ),
        aggregate_replicates=bool(query.aggregate_replicates),
        conflict_threshold_log_units=float(query.conflict_threshold_log_units),
        include_assay_context=bool(query.include_assay_context),
    )


def _target_sequence(
    target_id: str,
    override: str | None,
    timeout: float,
    transport: Transport,
    *,
    multi_component_policy: str,
    selected_accession: str | None,
):
    if override:
        return override, None, {"sequence_source": "user_override", "target_component_count": 0}
    payload = get_json(
        f"{CHEMBL_BASE}target/{target_id}.json", timeout=timeout, transport=transport
    )
    components = payload.get("target_components") or []
    accessions = [
        str(item.get("accession")).strip().upper()
        for item in components
        if isinstance(item, dict) and item.get("accession")
    ]
    accessions = list(dict.fromkeys(accessions))
    if not accessions:
        raise ValueError(
            "ChEMBL target did not provide a UniProt accession. Provide a sequence override."
        )
    if len(accessions) > 1:
        if multi_component_policy == "block":
            raise ValueError(
                "Multi-component ChEMBL target detected. Select a specific UniProt component, "
                "provide a sequence override, or explicitly choose first_with_warning."
            )
        if multi_component_policy == "select":
            if not selected_accession or selected_accession not in accessions:
                raise ValueError(
                    "selected_uniprot_accession must match one of: " + ", ".join(accessions)
                )
            accession = selected_accession
        else:
            accession = accessions[0]
    else:
        accession = accessions[0]
    fasta = fetch_uniprot_fasta(accession, timeout=timeout, transport=transport)
    return (
        fasta.sequence,
        accession,
        {
            "sequence_source": "UniProt",
            "uniprot_accession": accession,
            "target_pref_name": payload.get("pref_name"),
            "target_type": payload.get("target_type"),
            "organism": payload.get("organism"),
            "target_component_count": len(accessions),
            "target_components": accessions,
            "multi_component_warning": len(accessions) > 1,
            "multi_component_policy": multi_component_policy,
        },
    )


def _molecule_smiles(
    molecule_id: str,
    cache: dict[str, str | None],
    timeout: float,
    transport: Transport,
):
    if molecule_id in cache:
        return cache[molecule_id]
    payload = get_json(
        f"{CHEMBL_BASE}molecule/{molecule_id}.json", timeout=timeout, transport=transport
    )
    structures = payload.get("molecule_structures") or {}
    smiles = structures.get("canonical_smiles") if isinstance(structures, dict) else None
    cache[molecule_id] = str(smiles) if smiles else None
    return cache[molecule_id]


def _pactivity(record: dict[str, object], activity_type: str) -> float:
    if record.get("pchembl_value") not in (None, ""):
        value = float(record["pchembl_value"])
        if not -5 <= value <= 20:
            raise ValueError("pChEMBL outside sanity range.")
        return value
    if record.get("standard_value") in (None, "") or record.get("standard_units") in (None, ""):
        raise ValueError("No pChEMBL or convertible standard value.")
    return standardize_activity(
        activity_type, float(record["standard_value"]), str(record["standard_units"])
    ).p_activity


def _classification_from_censored_value(
    p_activity: float,
    relation: str,
    threshold_p: float,
) -> tuple[int, float | None, float | None]:
    normalized = normalize_relation(relation)
    if normalized == "=":
        return int(p_activity >= threshold_p), p_activity, p_activity
    if normalized in {"<", "<="}:
        if p_activity >= threshold_p:
            return 1, p_activity, None
        raise ValueError("Censored measurement crosses the classification threshold.")
    if normalized in {">", ">="}:
        if p_activity < threshold_p:
            return 0, None, p_activity
        raise ValueError("Censored measurement crosses the classification threshold.")
    raise ValueError("Approximate activity relations are not release-safe.")


def _context(raw: dict[str, object]) -> dict[str, object]:
    return {
        "assay_type": raw.get("assay_type"),
        "assay_description": raw.get("assay_description"),
        "assay_organism": raw.get("assay_organism"),
        "assay_tissue": raw.get("assay_tissue"),
        "assay_cell_type": raw.get("assay_cell_type"),
        "bao_format": raw.get("bao_format"),
        "target_organism": raw.get("target_organism"),
        "confidence_score": raw.get("confidence_score"),
        "document_year": raw.get("document_year"),
        "src_id": raw.get("src_id"),
        "activity_comment": raw.get("activity_comment"),
        "data_validity_comment": raw.get("data_validity_comment"),
        "potential_duplicate": raw.get("potential_duplicate"),
    }


def _aggregate(
    dataset: pd.DataFrame,
    *,
    task_type: str,
    threshold_p: float,
    conflict_threshold: float,
) -> pd.DataFrame:
    if dataset.empty:
        return dataset
    groups = []
    keys = ["inchikey", "target_id", "activity_type", "uniprot_accession"]
    for _, group in dataset.groupby(keys, dropna=False, sort=True):
        values = pd.to_numeric(group["p_activity"], errors="coerce").dropna()
        if values.empty:
            continue
        median = float(values.median())
        activity_range = float(values.max() - values.min())
        first = group.iloc[0]
        assay_ids = sorted({str(value) for value in group["assay_id"].dropna()})
        document_ids = sorted({str(value) for value in group["document_id"].dropna()})
        row = {
            "drug_id": first["drug_id"],
            "canonical_smiles": first["canonical_smiles"],
            "standardized_smiles": first["standardized_smiles"],
            "inchikey": first["inchikey"],
            "target_id": first["target_id"],
            "protein_sequence": first["protein_sequence"],
            "p_activity": round(median, 6),
            "activity_type": first["activity_type"],
            "activity_value": None,
            "activity_unit": "pActivity",
            "source": "ChEMBL",
            "assay_id": ";".join(assay_ids),
            "document_id": ";".join(document_ids),
            "activity_id": ";".join(sorted({str(value) for value in group["activity_id"].dropna()})),
            "standard_relation": "aggregated",
            "uniprot_accession": first["uniprot_accession"],
            "replicate_count": int(len(group)),
            "p_activity_min": round(float(values.min()), 6),
            "p_activity_max": round(float(values.max()), 6),
            "p_activity_std": round(float(values.std(ddof=1)), 6) if len(values) > 1 else 0.0,
            "activity_range": round(activity_range, 6),
            "conflicting_measurements": bool(activity_range >= conflict_threshold),
            "assay_count": len(assay_ids),
            "document_count": len(document_ids),
            "assay_context_json": json.dumps(
                group["assay_context"].tolist(), sort_keys=True, default=str
            ),
        }
        if task_type == "classification":
            row["label"] = int(median >= threshold_p)
        groups.append(row)
    return pd.DataFrame(groups)


def build_chembl_activity_dataset(
    query: ChEMBLActivityQuery,
    timeout: float = 20.0,
    transport: Transport = default_transport,
) -> ChEMBLDatasetResult:
    q = _normalize(query)
    protein_sequence, accession, target_meta = _target_sequence(
        q.target_chembl_id,
        q.protein_sequence_override,
        timeout,
        transport,
        multi_component_policy=q.multi_component_policy,
        selected_accession=q.selected_uniprot_accession,
    )
    params = urlencode(
        {
            "target_chembl_id": q.target_chembl_id,
            "standard_type": q.activity_type,
            "limit": min(1000, q.max_records),
        }
    )
    next_url = f"{CHEMBL_BASE}activity.json?{params}"
    accepted: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    molecule_cache: dict[str, str | None] = {}
    fetched = 0
    page_count = 0
    threshold_p = standardize_activity(
        q.activity_type, q.classification_threshold_nm, "nM"
    ).p_activity
    while next_url and fetched < q.max_records:
        payload = get_json(next_url, timeout=timeout, transport=transport)
        page_count += 1
        activities = payload.get("activities") or []
        if not isinstance(activities, list):
            raise ValueError("ChEMBL response lacks activities list.")
        for raw in activities:
            if fetched >= q.max_records:
                break
            fetched += 1
            if not isinstance(raw, dict):
                rejected.append({"record": fetched, "reason": "Invalid activity object"})
                continue
            try:
                relation = normalize_relation(raw.get("standard_relation") or "=")
                if q.require_exact_relation and relation != "=":
                    raise ValueError(f"Non-exact relation: {relation}")
                if raw.get("data_validity_comment") not in (None, ""):
                    raise ValueError(f"Data validity comment: {raw.get('data_validity_comment')}")
                molecule_id = str(raw.get("molecule_chembl_id") or "").strip().upper()
                if not molecule_id:
                    raise ValueError("Missing molecule_chembl_id")
                smiles = raw.get("canonical_smiles")
                if not smiles and q.resolve_missing_smiles:
                    smiles = _molecule_smiles(molecule_id, molecule_cache, timeout, transport)
                if not smiles:
                    raise ValueError("Canonical SMILES unavailable.")
                _, standardized = standardize_molecule(str(smiles))
                p_act = _pactivity(raw, q.activity_type)
                label, p_lower, p_upper = _classification_from_censored_value(
                    p_act, relation, threshold_p
                )
                context = _context(raw) if q.include_assay_context else {}
                accepted.append(
                    {
                        "drug_id": molecule_id,
                        "canonical_smiles": str(smiles),
                        "standardized_smiles": standardized.standardized_smiles,
                        "inchikey": standardized.inchikey,
                        "target_id": q.target_chembl_id,
                        "protein_sequence": protein_sequence,
                        "activity_type": q.activity_type,
                        "activity_value": raw.get("standard_value"),
                        "activity_unit": raw.get("standard_units"),
                        "p_activity": p_act,
                        "label": label,
                        "p_activity_lower_bound": p_lower,
                        "p_activity_upper_bound": p_upper,
                        "source": "ChEMBL",
                        "assay_id": raw.get("assay_chembl_id"),
                        "document_id": raw.get("document_chembl_id"),
                        "activity_id": raw.get("activity_id"),
                        "standard_relation": relation,
                        "uniprot_accession": accession,
                        "assay_context": context,
                    }
                )
            except Exception as exc:
                rejected.append(
                    {
                        "record": fetched,
                        "activity_id": raw.get("activity_id"),
                        "molecule_chembl_id": raw.get("molecule_chembl_id"),
                        "reason": str(exc),
                    }
                )
        page_meta = payload.get("page_meta") or {}
        candidate = page_meta.get("next") if isinstance(page_meta, dict) else None
        next_url = urljoin(CHEMBL_BASE, str(candidate)) if candidate else None

    raw_dataset = pd.DataFrame(accepted)
    if not raw_dataset.empty:
        raw_dataset = raw_dataset.drop_duplicates(
            subset=["inchikey", "protein_sequence", "p_activity", "assay_id", "activity_id"]
        ).reset_index(drop=True)
    dataset = (
        _aggregate(
            raw_dataset,
            task_type=q.task_type,
            threshold_p=threshold_p,
            conflict_threshold=q.conflict_threshold_log_units,
        )
        if q.aggregate_replicates
        else raw_dataset
    )
    if not dataset.empty:
        preferred = [
            "drug_id",
            "canonical_smiles",
            "standardized_smiles",
            "inchikey",
            "target_id",
            "protein_sequence",
        ]
        preferred.append("label" if q.task_type == "classification" else "p_activity")
        preferred.extend(
            [
                "p_activity",
                "activity_type",
                "activity_value",
                "activity_unit",
                "source",
                "assay_id",
                "document_id",
                "activity_id",
                "standard_relation",
                "uniprot_accession",
                "replicate_count",
                "p_activity_min",
                "p_activity_max",
                "p_activity_std",
                "activity_range",
                "conflicting_measurements",
                "assay_count",
                "document_count",
                "assay_context_json",
                "assay_context",
            ]
        )
        dataset = dataset.reindex(columns=[column for column in preferred if column in dataset.columns])
    conflicts = int(dataset.get("conflicting_measurements", pd.Series(dtype=bool)).fillna(False).sum())
    metadata = {
        "target_chembl_id": q.target_chembl_id,
        "activity_type": q.activity_type,
        "task_type": q.task_type,
        "classification_threshold_nm": q.classification_threshold_nm,
        "fetched_records": fetched,
        "raw_accepted_rows": len(raw_dataset),
        "accepted_rows": len(dataset),
        "rejected_rows": len(rejected),
        "page_count": page_count,
        "pagination_complete": next_url is None,
        "require_exact_relation": q.require_exact_relation,
        "aggregate_replicates": q.aggregate_replicates,
        "conflict_threshold_log_units": q.conflict_threshold_log_units,
        "conflicting_groups": conflicts,
        "source": "ChEMBL REST API and UniProt REST API",
        "recommended_splits": [
            "compound-grouped",
            "scaffold",
            "protein-cluster/cold-target",
            "temporal/publication-aware",
        ],
        "random_split_warning": (
            "Random row splits can leak repeated compounds, assays or publications and are not recommended."
        ),
        **target_meta,
    }
    return ChEMBLDatasetResult(dataset, pd.DataFrame(rejected), metadata)
