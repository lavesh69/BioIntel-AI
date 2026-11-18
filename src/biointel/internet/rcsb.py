from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

from biointel.internet.download_registry import DownloadRecord
from biointel.internet.downloader import (
    DownloadResult,
    download_public_file,
    fetch_public_json,
)
from biointel.internet.network_policy import InternetPolicy

RCSB_HOSTS = {"data.rcsb.org", "files.rcsb.org", "www.rcsb.org"}
PDB_ID = re.compile(r"^(?:[A-Za-z0-9]{4}|pdb_[A-Za-z0-9]{8})$")
FORMATS = {
    "PDBx/mmCIF": "cif",
    "Legacy PDB": "pdb",
    "Compressed mmCIF": "cif.gz",
    "Compressed PDB": "pdb.gz",
}


@dataclass(frozen=True)
class RCSBEntry:
    pdb_id: str
    title: str
    experimental_methods: tuple[str, ...]
    resolution_angstrom: float | None
    initial_release_date: str | None
    polymer_entity_count: int | None
    nonpolymer_entity_count: int | None
    deposited_atom_count: int | None
    source_url: str


def normalize_pdb_id(value: str) -> str:
    normalized = value.strip()
    if normalized.lower().startswith("pdb_"):
        normalized = "pdb_" + normalized[4:].upper()
    else:
        normalized = normalized.upper()
    if not PDB_ID.fullmatch(normalized):
        raise ValueError("PDB identifier must look like 4HHB or pdb_00006UV8.")
    return normalized


def fetch_rcsb_entry(
    pdb_id: str,
    *,
    policy: InternetPolicy | None = None,
) -> RCSBEntry:
    normalized = normalize_pdb_id(pdb_id)
    url = "https://data.rcsb.org/rest/v1/core/entry/" + quote(normalized, safe="_")
    payload, _ = fetch_public_json(
        url,
        policy=policy,
        allowed_hosts=RCSB_HOSTS,
        max_bytes=8 * 1024 * 1024,
    )
    struct = payload.get("struct") if isinstance(payload.get("struct"), dict) else {}
    experiments = payload.get("exptl") if isinstance(payload.get("exptl"), list) else []
    info = (
        payload.get("rcsb_entry_info") if isinstance(payload.get("rcsb_entry_info"), dict) else {}
    )
    accession = (
        payload.get("rcsb_accession_info")
        if isinstance(payload.get("rcsb_accession_info"), dict)
        else {}
    )
    resolution_values = info.get("resolution_combined")
    resolution = None
    if isinstance(resolution_values, list) and resolution_values:
        try:
            resolution = float(resolution_values[0])
        except (TypeError, ValueError):
            resolution = None
    methods = tuple(
        str(item.get("method"))
        for item in experiments
        if isinstance(item, dict) and item.get("method")
    )
    return RCSBEntry(
        pdb_id=normalized,
        title=str(struct.get("title") or "Title not provided"),
        experimental_methods=methods,
        resolution_angstrom=resolution,
        initial_release_date=(
            str(accession.get("initial_release_date"))
            if accession.get("initial_release_date")
            else None
        ),
        polymer_entity_count=(
            int(info["polymer_entity_count"])
            if isinstance(info.get("polymer_entity_count"), (int, float))
            else None
        ),
        nonpolymer_entity_count=(
            int(info["nonpolymer_entity_count"])
            if isinstance(info.get("nonpolymer_entity_count"), (int, float))
            else None
        ),
        deposited_atom_count=(
            int(info["deposited_atom_count"])
            if isinstance(info.get("deposited_atom_count"), (int, float))
            else None
        ),
        source_url=url,
    )


def rcsb_download_url(pdb_id: str, file_format: str) -> tuple[str, str]:
    normalized = normalize_pdb_id(pdb_id)
    normalized_format = file_format.strip().lower()
    if normalized_format not in {"cif", "pdb", "cif.gz", "pdb.gz"}:
        raise ValueError("Supported formats: cif, pdb, cif.gz and pdb.gz.")
    if normalized.startswith("pdb_") and normalized_format.startswith("pdb"):
        raise ValueError("Extended PDB identifiers must be downloaded as PDBx/mmCIF.")
    filename = f"{normalized}.{normalized_format}"
    return f"https://files.rcsb.org/download/{quote(filename, safe='._')}", filename


def download_rcsb_structure(
    pdb_id: str,
    file_format: str,
    *,
    project_root: str | Path,
    policy: InternetPolicy | None = None,
) -> tuple[DownloadResult, DownloadRecord]:
    normalized = normalize_pdb_id(pdb_id)
    url, filename = rcsb_download_url(normalized, file_format)
    root = Path(project_root).resolve()
    return download_public_file(
        url,
        root / "data" / "internet_downloads" / "rcsb_pdb",
        project_root=root,
        registry_path=runtime_database_path(root, "internet_downloads.sqlite3"),
        provider="RCSB PDB",
        resource_id=normalized,
        preferred_filename=filename,
        policy=policy,
        allowed_hosts=RCSB_HOSTS,
        notes="Official RCSB PDB structure download.",
    )


def batch_download_rcsb(
    pdb_ids: Iterable[str],
    file_format: str,
    *,
    project_root: str | Path,
    policy: InternetPolicy | None = None,
    max_entries: int = 50,
) -> list[dict[str, object]]:
    unique = list(dict.fromkeys(normalize_pdb_id(value) for value in pdb_ids if value.strip()))
    if not unique:
        raise ValueError("Provide at least one PDB identifier.")
    if len(unique) > max_entries:
        raise ValueError(f"Batch downloads are limited to {max_entries} PDB entries per run.")
    results: list[dict[str, object]] = []
    for pdb_id in unique:
        try:
            download, record = download_rcsb_structure(
                pdb_id,
                file_format,
                project_root=project_root,
                policy=policy,
            )
            results.append(
                {
                    "pdb_id": pdb_id,
                    "status": "completed",
                    "filename": download.filename,
                    "relative_path": download.relative_path,
                    "size_bytes": download.size_bytes,
                    "sha256": download.sha256,
                    "download_id": record.download_id,
                }
            )
        except Exception as exc:  # individual entries must not abort the whole batch
            results.append({"pdb_id": pdb_id, "status": "failed", "error": str(exc)})
    return results
