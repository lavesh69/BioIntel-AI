from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests


@dataclass(frozen=True)
class PubChemBioAssayClient:
    timeout_seconds: float = 30.0
    base_url: str = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

    def _get_json(self, path: str) -> dict[str, Any]:
        response = requests.get(f"{self.base_url.rstrip('/')}/{path.lstrip('/')}", timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def assay_summary(self, aid: int | str) -> dict[str, Any]:
        return self._get_json(f"assay/aid/{int(aid)}/summary/JSON")

    def assay_description(self, aid: int | str) -> dict[str, Any]:
        return self._get_json(f"assay/aid/{int(aid)}/description/JSON")

    def active_cids(self, aid: int | str) -> list[int]:
        payload = self._get_json(f"assay/aid/{int(aid)}/cids/JSON?cids_type=active")
        return [int(value) for value in payload.get("IdentifierList", {}).get("CID", [])]

    def inactive_cids(self, aid: int | str) -> list[int]:
        payload = self._get_json(f"assay/aid/{int(aid)}/cids/JSON?cids_type=inactive")
        return [int(value) for value in payload.get("IdentifierList", {}).get("CID", [])]

    def compound_properties(self, cids: list[int], properties: str = "CanonicalSMILES,IsomericSMILES,InChIKey") -> pd.DataFrame:
        if not cids:
            return pd.DataFrame()
        cid_text = ",".join(map(str, cids))
        payload = self._get_json(f"compound/cid/{cid_text}/property/{properties}/JSON")
        return pd.DataFrame(payload.get("PropertyTable", {}).get("Properties", []))

def pubchem_activity_export_to_frame(dataframe: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "canonical_smiles": ("canonical_smiles","CanonicalSMILES","SMILES","PUBCHEM_OPENEYE_CAN_SMILES"),
        "protein_sequence": ("protein_sequence","Target Sequence","sequence"),
        "standard_value": ("standard_value","Activity Value","AC50","IC50","EC50"),
        "standard_units": ("standard_units","Activity Unit","Units"),
        "standard_relation": ("standard_relation","Activity Relation","Relation"),
        "activity_type": ("activity_type","Activity Type","Endpoint"),
        "assay_id": ("assay_id","AID","PUBCHEM_AID"),
        "source_record_id": ("source_record_id","CID","PUBCHEM_CID"),
        "publication_id": ("publication_id","PMID","DOI"),
        "uniprot_accession": ("uniprot_accession","UniProt"),
        "organism": ("organism","Organism"),
    }
    def find(key: str) -> str | None:
        return next((name for name in aliases[key] if name in dataframe.columns), None)
    required = {key: find(key) for key in ("canonical_smiles","protein_sequence","standard_value","standard_units")}
    if any(value is None for value in required.values()):
        raise ValueError("PubChem export must contain SMILES, protein sequence, activity value and units.")
    output = pd.DataFrame({
        "canonical_smiles": dataframe[required["canonical_smiles"]],
        "protein_sequence": dataframe[required["protein_sequence"]],
        "standard_value": dataframe[required["standard_value"]],
        "standard_units": dataframe[required["standard_units"]],
    })
    for key in ("standard_relation","activity_type","assay_id","source_record_id","publication_id","uniprot_accession","organism"):
        column = find(key)
        output[key] = dataframe[column] if column else ("=" if key == "standard_relation" else None)
    output["source_database"] = "pubchem_bioassay"
    return output
