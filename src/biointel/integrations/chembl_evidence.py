from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests


@dataclass(frozen=True)
class ChEMBLEvidenceClient:
    timeout_seconds: float = 30.0
    base_url: str = "https://www.ebi.ac.uk/chembl/api/data"

    def _get_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        response = requests.get(
            f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}",
            params={**params, "format": "json"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def activity_page(self, *, limit: int = 1000, offset: int = 0, target_chembl_id: str | None = None, molecule_chembl_id: str | None = None, standard_type: list[str] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": min(max(int(limit), 1), 1000), "offset": max(int(offset), 0)}
        if target_chembl_id:
            params["target_chembl_id"] = target_chembl_id
        if molecule_chembl_id:
            params["molecule_chembl_id"] = molecule_chembl_id
        if standard_type:
            params["standard_type__in"] = ",".join(standard_type)
        return self._get_json("activity", params)

    def molecule(self, molecule_chembl_id: str) -> dict[str, Any]:
        return self._get_json(f"molecule/{molecule_chembl_id}", {})

    def target(self, target_chembl_id: str) -> dict[str, Any]:
        return self._get_json(f"target/{target_chembl_id}", {})

    def assay(self, assay_chembl_id: str) -> dict[str, Any]:
        return self._get_json(f"assay/{assay_chembl_id}", {})

    def iter_activities(self, *, maximum_rows: int = 10000, **filters: Any):
        offset = 0
        emitted = 0
        while emitted < maximum_rows:
            page = self.activity_page(limit=min(1000, maximum_rows - emitted), offset=offset, **filters)
            rows = page.get("activities", [])
            if not rows:
                break
            for row in rows:
                yield row
                emitted += 1
                if emitted >= maximum_rows:
                    break
            next_url = page.get("page_meta", {}).get("next")
            if not next_url:
                break
            offset += len(rows)

def chembl_activities_to_frame(activities: list[dict[str, Any]], *, molecule_smiles: dict[str, str] | None = None, target_sequences: dict[str, str] | None = None) -> pd.DataFrame:
    molecule_smiles = molecule_smiles or {}
    target_sequences = target_sequences or {}
    records = []
    for item in activities:
        molecule_id = item.get("molecule_chembl_id")
        target_id = item.get("target_chembl_id")
        smiles = item.get("canonical_smiles") or molecule_smiles.get(str(molecule_id))
        sequence = item.get("protein_sequence") or target_sequences.get(str(target_id))
        records.append({
            "canonical_smiles": smiles,
            "protein_sequence": sequence,
            "standard_value": item.get("standard_value"),
            "standard_units": item.get("standard_units"),
            "standard_relation": item.get("standard_relation") or "=",
            "activity_type": item.get("standard_type"),
            "assay_id": item.get("assay_chembl_id"),
            "source_record_id": item.get("activity_id"),
            "publication_id": item.get("document_chembl_id"),
            "target_chembl_id": target_id,
            "molecule_chembl_id": molecule_id,
            "target_name": item.get("target_pref_name"),
            "organism": item.get("target_organism"),
            "confidence_score": item.get("confidence_score"),
            "source_database": "chembl",
        })
    return pd.DataFrame(records)


def download_activity_evidence(
    *,
    target_chembl_id: str | None = None,
    molecule_chembl_id: str | None = None,
    maximum_rows: int = 500,
    activity_types: list[str] | None = None,
    client: ChEMBLEvidenceClient | None = None,
) -> pd.DataFrame:
    active = client or ChEMBLEvidenceClient()
    activities = list(active.iter_activities(
        maximum_rows=maximum_rows,
        target_chembl_id=target_chembl_id,
        molecule_chembl_id=molecule_chembl_id,
        standard_type=activity_types or ["Ki", "Kd", "IC50", "EC50"],
    ))
    molecule_map: dict[str, str] = {}
    target_map: dict[str, str] = {}
    accession_map: dict[str, str] = {}
    organism_map: dict[str, str] = {}
    from biointel.integrations.uniprot import UniProtClient
    uniprot = UniProtClient(timeout_seconds=active.timeout_seconds)
    for item in activities:
        molecule_id = str(item.get("molecule_chembl_id") or "")
        if molecule_id and molecule_id not in molecule_map:
            try:
                molecule = active.molecule(molecule_id)
                molecule_map[molecule_id] = (
                    molecule.get("molecule_structures", {}) or {}
                ).get("canonical_smiles") or ""
            except Exception:
                molecule_map[molecule_id] = ""
        target_id = str(item.get("target_chembl_id") or "")
        if target_id and target_id not in target_map:
            try:
                target = active.target(target_id)
                components = target.get("target_components", []) or []
                accession = next(
                    (str(component.get("accession")) for component in components if component.get("accession")),
                    "",
                )
                accession_map[target_id] = accession
                organism_map[target_id] = str(target.get("organism") or "")
                target_map[target_id] = uniprot.target(accession).sequence if accession else ""
            except Exception:
                target_map[target_id] = ""
    frame = chembl_activities_to_frame(
        activities,
        molecule_smiles=molecule_map,
        target_sequences=target_map,
    )
    if not frame.empty:
        frame["uniprot_accession"] = frame["target_chembl_id"].astype(str).map(accession_map)
        frame["organism"] = frame["target_chembl_id"].astype(str).map(organism_map).fillna(frame["organism"])
    return frame
