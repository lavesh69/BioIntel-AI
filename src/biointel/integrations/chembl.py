from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

from biointel.integrations.http_client import (
    Transport,
    default_transport,
    get_json,
)

CHEMBL_ID = re.compile(r"^CHEMBL\d+$")


@dataclass(frozen=True)
class ChEMBLMolecule:
    chembl_id: str
    preferred_name: str | None
    molecule_type: str | None
    max_phase: int | None
    canonical_smiles: str | None
    source_url: str


@dataclass(frozen=True)
class ChEMBLTarget:
    chembl_id: str
    preferred_name: str | None
    target_type: str | None
    organism: str | None
    source_url: str


def _normalize_id(value: str) -> str:
    normalized = value.strip().upper()
    if not CHEMBL_ID.fullmatch(normalized):
        raise ValueError("ChEMBL identifier must look like CHEMBL25 or CHEMBL204.")
    return normalized


def fetch_chembl_molecule(
    chembl_id: str,
    timeout: float = 15.0,
    transport: Transport = default_transport,
) -> ChEMBLMolecule:
    normalized = _normalize_id(chembl_id)
    url = "https://www.ebi.ac.uk/chembl/api/data/molecule/" f"{quote(normalized, safe='')}.json"
    payload = get_json(url, timeout=timeout, transport=transport)
    structures = payload.get("molecule_structures") or {}
    canonical_smiles = structures.get("canonical_smiles") if isinstance(structures, dict) else None
    max_phase = payload.get("max_phase")
    return ChEMBLMolecule(
        chembl_id=normalized,
        preferred_name=payload.get("pref_name"),
        molecule_type=payload.get("molecule_type"),
        max_phase=int(max_phase) if isinstance(max_phase, (int, float)) else None,
        canonical_smiles=canonical_smiles,
        source_url=url,
    )


def fetch_chembl_target(
    chembl_id: str,
    timeout: float = 15.0,
    transport: Transport = default_transport,
) -> ChEMBLTarget:
    normalized = _normalize_id(chembl_id)
    url = "https://www.ebi.ac.uk/chembl/api/data/target/" f"{quote(normalized, safe='')}.json"
    payload = get_json(url, timeout=timeout, transport=transport)
    return ChEMBLTarget(
        chembl_id=normalized,
        preferred_name=payload.get("pref_name"),
        target_type=payload.get("target_type"),
        organism=payload.get("organism"),
        source_url=url,
    )
