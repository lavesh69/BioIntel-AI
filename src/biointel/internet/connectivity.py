from __future__ import annotations

import time
from dataclasses import asdict

from biointel.internet.downloader import fetch_public_bytes
from biointel.internet.network_policy import (
    OFFICIAL_SCIENTIFIC_HOSTS,
    InternetPolicy,
    internet_policy_from_environment,
)

SERVICE_PROBES = {
    "RCSB PDB": (
        "https://data.rcsb.org/rest/v1/core/entry/4HHB",
        "application/json",
    ),
    "UniProt": (
        "https://rest.uniprot.org/uniprotkb/P69905.fasta",
        "text/plain",
    ),
    "ChEMBL": (
        "https://www.ebi.ac.uk/chembl/api/data/molecule/CHEMBL25.json",
        "application/json",
    ),
    "PubChem": (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/aspirin/property/Title,CanonicalSMILES/JSON",
        "application/json",
    ),
}


def internet_configuration() -> dict[str, object]:
    policy = internet_policy_from_environment()
    return {
        "policy": asdict(policy),
        "approved_scientific_hosts": sorted(OFFICIAL_SCIENTIFIC_HOSTS),
        "outbound_only": True,
        "localhost_server": True,
        "automatic_archive_extraction": False,
    }


def check_internet_services(*, policy: InternetPolicy | None = None) -> dict[str, object]:
    active = policy or internet_policy_from_environment()
    results: dict[str, object] = {}
    for name, (url, accept) in SERVICE_PROBES.items():
        started = time.perf_counter()
        try:
            body, metadata = fetch_public_bytes(
                url,
                policy=active,
                allowed_hosts=set(OFFICIAL_SCIENTIFIC_HOSTS),
                max_bytes=2 * 1024 * 1024,
                accept=accept,
            )
        except Exception as exc:
            results[name] = {
                "available": False,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "error": str(exc),
            }
        else:
            results[name] = {
                "available": True,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "bytes_received": len(body),
                "content_type": metadata.get("content_type"),
                "final_url": metadata.get("final_url"),
            }
    return {
        "configuration": internet_configuration(),
        "services": results,
        "available_count": sum(
            bool(value.get("available")) for value in results.values() if isinstance(value, dict)
        ),
    }
