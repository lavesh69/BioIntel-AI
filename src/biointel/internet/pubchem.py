from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from biointel.internet.downloader import (
    InternetDownloadError,
    fetch_public_json,
)
from biointel.internet.network_policy import InternetPolicy

PUBCHEM_HOSTS = {
    "pubchem.ncbi.nlm.nih.gov",
    "www.ncbi.nlm.nih.gov",
}


@dataclass(frozen=True)
class PubChemCompound:
    cid: int
    title: str
    canonical_smiles: str
    isomeric_smiles: str | None
    iupac_name: str | None
    molecular_formula: str | None
    molecular_weight: float | None
    xlogp: float | None
    inchikey: str | None
    query_name: str
    source_url: str


def _first_property(payload: dict[str, object]) -> dict[str, object]:
    table = payload.get("PropertyTable")
    if not isinstance(table, dict):
        raise InternetDownloadError("PubChem returned an unexpected property response.")
    properties = table.get("Properties")
    if not isinstance(properties, list) or not properties:
        raise InternetDownloadError("PubChem did not return a compound for that name.")
    first = properties[0]
    if not isinstance(first, dict):
        raise InternetDownloadError("PubChem returned an invalid compound record.")
    return first


def fetch_pubchem_compound_by_name(
    name: str,
    *,
    policy: InternetPolicy | None = None,
) -> PubChemCompound:
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Enter a compound or drug name.")
    encoded = quote(cleaned, safe="")
    properties = (
        "Title,CanonicalSMILES,IsomericSMILES,IUPACName,"
        "MolecularFormula,MolecularWeight,XLogP,InChIKey"
    )
    url = (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
        f"{encoded}/property/{properties}/JSON"
    )
    payload, _ = fetch_public_json(
        url,
        policy=policy,
        allowed_hosts=PUBCHEM_HOSTS,
        max_bytes=6 * 1024 * 1024,
    )
    row = _first_property(payload)
    canonical = str(
        row.get("CanonicalSMILES") or row.get("ConnectivitySMILES") or row.get("SMILES") or ""
    ).strip()
    if not canonical:
        raise InternetDownloadError("PubChem record did not include a usable SMILES string.")

    def optional_float(value: object) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    cid = int(row.get("CID") or 0)
    return PubChemCompound(
        cid=cid,
        title=str(row.get("Title") or cleaned),
        canonical_smiles=canonical,
        isomeric_smiles=(
            str(row.get("IsomericSMILES") or row.get("SMILES"))
            if row.get("IsomericSMILES") or row.get("SMILES")
            else None
        ),
        iupac_name=(str(row.get("IUPACName")) if row.get("IUPACName") else None),
        molecular_formula=(
            str(row.get("MolecularFormula")) if row.get("MolecularFormula") else None
        ),
        molecular_weight=optional_float(row.get("MolecularWeight")),
        xlogp=optional_float(row.get("XLogP")),
        inchikey=(str(row.get("InChIKey")) if row.get("InChIKey") else None),
        query_name=cleaned,
        source_url=(
            f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
            if cid
            else "https://pubchem.ncbi.nlm.nih.gov/"
        ),
    )
