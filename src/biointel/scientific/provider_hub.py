from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

OFFICIAL_PROVIDERS: dict[str, dict[str, str]] = {
    "chembl": {"host": "www.ebi.ac.uk", "base_url": "https://www.ebi.ac.uk/chembl/api/data", "licence": "ChEMBL terms / CC BY-SA-compatible data terms"},
    "uniprot": {"host": "rest.uniprot.org", "base_url": "https://rest.uniprot.org", "licence": "UniProt terms"},
    "pubchem": {"host": "pubchem.ncbi.nlm.nih.gov", "base_url": "https://pubchem.ncbi.nlm.nih.gov/rest/pug", "licence": "US Government public data"},
    "rcsb": {"host": "data.rcsb.org", "base_url": "https://data.rcsb.org/rest/v1", "licence": "RCSB PDB usage policy"},
    "clinicaltrials": {"host": "clinicaltrials.gov", "base_url": "https://clinicaltrials.gov/api/v2", "licence": "ClinicalTrials.gov terms"},
    "clinvar": {"host": "eutils.ncbi.nlm.nih.gov", "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils", "licence": "NCBI public data"},
    "geo": {"host": "eutils.ncbi.nlm.nih.gov", "base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils", "licence": "NCBI public data"},
    "bindingdb": {"host": "www.bindingdb.org", "base_url": "https://www.bindingdb.org", "licence": "BindingDB terms"},
    "uci": {"host": "archive.ics.uci.edu", "base_url": "https://archive.ics.uci.edu", "licence": "CC BY 4.0 for the WDBC dataset"},
}


@dataclass(frozen=True)
class ProviderSnapshot:
    provider: str
    url: str
    retrieved_at: str
    status_code: int
    content_type: str
    etag: str | None
    last_modified: str | None
    sha256: str
    bytes: int
    local_path: str


class ProviderHub:
    def __init__(self, cache_directory: str | Path, *, timeout_seconds: float = 45.0, retries: int = 3):
        self.cache_directory = Path(cache_directory).resolve()
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = float(timeout_seconds)
        self.retries = max(1, int(retries))
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "BioIntel-AI/3.8 scientific-evidence-sync"})

    @staticmethod
    def validate_url(provider: str, url: str) -> None:
        if provider not in OFFICIAL_PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != OFFICIAL_PROVIDERS[provider]["host"]:
            raise ValueError(f"URL is outside the official {provider} host allowlist.")

    def get_json(self, provider: str, url: str, *, params: dict[str, Any] | None = None) -> tuple[Any, ProviderSnapshot]:
        self.validate_url(provider, url)
        response = None
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout_seconds)
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(0.5 * (2 ** attempt))
        if response is None:
            raise RuntimeError(f"Provider request failed: {last_error}")
        body = response.content
        digest = hashlib.sha256(body).hexdigest()
        provider_dir = self.cache_directory / provider
        provider_dir.mkdir(parents=True, exist_ok=True)
        target = provider_dir / f"{digest}.json"
        target.write_bytes(body)
        snapshot = ProviderSnapshot(
            provider=provider,
            url=response.url,
            retrieved_at=datetime.now(UTC).isoformat(),
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            sha256=digest,
            bytes=len(body),
            local_path=str(target),
        )
        manifest = target.with_suffix(".manifest.json")
        manifest.write_text(json.dumps(snapshot.__dict__, indent=2, sort_keys=True), encoding="utf-8")
        return response.json(), snapshot

    def chembl_activity(self, **filters: Any):
        params = {"format": "json", "limit": min(int(filters.pop("limit", 1000)), 1000), **filters}
        return self.get_json("chembl", f"{OFFICIAL_PROVIDERS['chembl']['base_url']}/activity.json", params=params)

    def uniprot_search(self, query: str, *, size: int = 500):
        return self.get_json("uniprot", f"{OFFICIAL_PROVIDERS['uniprot']['base_url']}/uniprotkb/search", params={"query": query, "format": "json", "size": min(size, 500)})

    def clinical_trials(self, query: str, *, page_size: int = 100):
        return self.get_json("clinicaltrials", f"{OFFICIAL_PROVIDERS['clinicaltrials']['base_url']}/studies", params={"query.term": query, "pageSize": min(page_size, 1000), "format": "json"})

    def rcsb_entry(self, pdb_id: str):
        return self.get_json("rcsb", f"{OFFICIAL_PROVIDERS['rcsb']['base_url']}/core/entry/{pdb_id.upper()}")
