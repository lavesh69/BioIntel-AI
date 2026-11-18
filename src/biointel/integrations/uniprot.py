from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import quote

import requests

from biointel.integrations.http_client import Transport, default_transport, get_text
from biointel.sequence.parser import parse_sequence_text

_ACCESSION = re.compile(r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?:-\d+)?$")



@dataclass(frozen=True)
class UniProtRecord:
    accession: str
    header: str
    sequence: str
    source_url: str


def fetch_uniprot_fasta(
    accession: str,
    timeout: float = 15.0,
    transport: Transport = default_transport,
) -> UniProtRecord:
    """Retrieve one UniProtKB entry as FASTA using the official REST endpoint."""

    normalized = accession.strip().upper()
    if not _ACCESSION.fullmatch(normalized):
        raise ValueError("Invalid UniProt accession.")
    url = "https://rest.uniprot.org/uniprotkb/" + f"{quote(normalized, safe='')}.fasta"
    parsed = parse_sequence_text(get_text(url, timeout=timeout, transport=transport))
    return UniProtRecord(
        accession=normalized,
        header=parsed.header,
        sequence=parsed.sequence,
        source_url=url,
    )


@dataclass(frozen=True)
class UniProtTarget:
    accession: str
    primary_accession: str
    entry_type: str | None
    protein_name: str | None
    gene_names: list[str]
    organism: str | None
    taxon_id: int | None
    sequence: str
    sequence_version: int | None
    isoform: str | None
    reviewed: bool

class UniProtClient:
    def __init__(self, timeout_seconds: float = 30.0, base_url: str = "https://rest.uniprot.org"):
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")

    def fetch_entry(self, accession: str) -> dict[str, Any]:
        normalized = accession.strip().upper()
        if not _ACCESSION.fullmatch(normalized):
            raise ValueError(f"Invalid UniProt accession: {accession!r}")
        response = requests.get(f"{self.base_url}/uniprotkb/{normalized}.json", timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def target(self, accession: str) -> UniProtTarget:
        payload = self.fetch_entry(accession)
        protein_description = payload.get("proteinDescription", {})
        name = (
            protein_description.get("recommendedName", {}).get("fullName", {}).get("value")
            or protein_description.get("submissionNames", [{}])[0].get("fullName", {}).get("value")
        )
        genes = []
        for gene in payload.get("genes", []):
            primary = gene.get("geneName", {}).get("value")
            if primary:
                genes.append(primary)
            genes.extend(item.get("value") for item in gene.get("synonyms", []) if item.get("value"))
        sequence = payload.get("sequence", {})
        accession_text = str(payload.get("primaryAccession") or accession).upper()
        isoform = accession.strip().upper().split("-", 1)[1] if "-" in accession.strip() else None
        entry_type = payload.get("entryType")
        return UniProtTarget(
            accession=accession.strip().upper(),
            primary_accession=accession_text,
            entry_type=entry_type,
            protein_name=name,
            gene_names=sorted(set(genes)),
            organism=payload.get("organism", {}).get("scientificName"),
            taxon_id=payload.get("organism", {}).get("taxonId"),
            sequence=str(sequence.get("value") or ""),
            sequence_version=sequence.get("version"),
            isoform=isoform,
            reviewed="reviewed" in str(entry_type or "").lower(),
        )

    def target_dict(self, accession: str) -> dict[str, Any]:
        return asdict(self.target(accession))
