from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_fair_digital_object(
    *,
    persistent_identifier: str,
    title: str,
    description: str,
    creators: Iterable[dict[str, str]],
    files: Iterable[str | Path],
    license_id: str,
    version: str,
    keywords: Iterable[str],
    vocabularies: Iterable[str],
    qualified_references: Iterable[dict[str, str]] = (),
    access_url: str,
    access_rights: str = "restricted",
) -> dict[str, Any]:
    distributions = []
    for raw_path in files:
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        distributions.append(
            {
                "@type": "schema:DataDownload",
                "name": path.name,
                "contentSize": path.stat().st_size,
                "sha256": _sha256(path),
                "encodingFormat": path.suffix.lower().lstrip(".") or "application/octet-stream",
            }
        )
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    return {
        "@context": {
            "schema": "https://schema.org/",
            "prov": "http://www.w3.org/ns/prov#",
            "dct": "http://purl.org/dc/terms/",
        },
        "@id": persistent_identifier,
        "@type": "schema:Dataset",
        "persistent_identifier": persistent_identifier,
        "data_identifier": persistent_identifier,
        "title": title,
        "description": description,
        "creators": list(creators),
        "keywords": sorted(set(keywords)),
        "indexed": True,
        "index_name": "BioIntel FAIR Catalog",
        "access_protocol": "https",
        "access_url": access_url,
        "access_rights": access_rights,
        "authorization_documented": True,
        "metadata_persistence_policy": True,
        "tombstone_url": f"{access_url.rstrip('/')}/tombstone",
        "representation_language": "json-ld",
        "vocabularies": sorted(set(vocabularies)),
        "qualified_references": list(qualified_references),
        "publisher": "BioIntel AI",
        "version": version,
        "resource_type": "dataset",
        "distributions": distributions,
        "license": license_id,
        "provenance": {
            "source": persistent_identifier,
            "generated_at": generated_at,
            "agent": "BioIntel AI FAIR Digital Object Builder",
            "activity": "metadata packaging and checksum generation",
        },
        "community_standards": ["JSON-LD", "Schema.org Dataset", "PROV-O"],
        "schema_version": "1.0",
    }


def write_fair_digital_object(payload: dict[str, Any], output: str | Path) -> Path:
    path = Path(output).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path
