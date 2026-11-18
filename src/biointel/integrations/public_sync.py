from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin
from uuid import uuid4

from biointel.database.core import connect, transaction
from biointel.integrations.http_client import Transport, default_transport, get_json, get_text
from biointel.internet.download_registry import initialize_download_registry, register_download


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class SyncResult:
    run_id: str
    provider: str
    status: str
    records: int
    output_path: str
    sha256: str
    started_at_utc: str
    completed_at_utc: str
    scope: str
    warnings: tuple[str, ...]


SYNC_SCHEMA = """
CREATE TABLE IF NOT EXISTS scientific_sync_runs(
    run_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    status TEXT NOT NULL,
    query_json TEXT NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0,
    output_relative_path TEXT,
    output_sha256 TEXT,
    scope TEXT NOT NULL,
    warning_json TEXT NOT NULL DEFAULT '[]',
    started_at_utc TEXT NOT NULL,
    completed_at_utc TEXT,
    error TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS scientific_sync_records(
    run_id TEXT NOT NULL,
    provider_record_id TEXT NOT NULL,
    record_type TEXT NOT NULL,
    normalized_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY(run_id, provider_record_id, record_type),
    FOREIGN KEY(run_id) REFERENCES scientific_sync_runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_scientific_sync_provider_time
    ON scientific_sync_runs(provider, started_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_scientific_sync_record_type
    ON scientific_sync_records(record_type);
"""


def initialize_sync_registry(path: str | Path) -> None:
    initialize_download_registry(path)
    with transaction(path) as connection:
        connection.executescript(SYNC_SCHEMA)


def _start_run(path: Path, provider: str, query: dict[str, Any], scope: str) -> tuple[str, str]:
    initialize_sync_registry(path)
    run_id = "sync-" + uuid4().hex
    started = _utc_now()
    with transaction(path) as connection:
        connection.execute(
            """
            INSERT INTO scientific_sync_runs(
                run_id, provider, status, query_json, scope, started_at_utc
            ) VALUES (?, ?, 'running', ?, ?, ?)
            """,
            (run_id, provider, json.dumps(query, sort_keys=True, default=str), scope, started),
        )
    return run_id, started


def _finish_run(
    registry: Path,
    *,
    run_id: str,
    status: str,
    records: list[dict[str, Any]],
    record_type: str,
    output_relative_path: str,
    output_sha256: str,
    warnings: list[str],
    error: str = "",
) -> str:
    completed = _utc_now()
    with transaction(registry) as connection:
        for record in records:
            provider_id = str(
                record.get("activity_id")
                or record.get("primaryAccession")
                or record.get("accession")
                or record.get("rcsb_id")
                or record.get("uid")
                or hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()[:24]
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO scientific_sync_records(
                    run_id, provider_record_id, record_type, normalized_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, provider_id, record_type, json.dumps(record, sort_keys=True, default=str), completed),
            )
        connection.execute(
            """
            UPDATE scientific_sync_runs
            SET status=?, record_count=?, output_relative_path=?, output_sha256=?,
                warning_json=?, completed_at_utc=?, error=?
            WHERE run_id=?
            """,
            (
                status,
                len(records),
                output_relative_path,
                output_sha256,
                json.dumps(warnings),
                completed,
                error[:4000],
                run_id,
            ),
        )
    return completed


def _write_csv(root: Path, provider: str, run_id: str, records: list[dict[str, Any]]) -> tuple[Path, str]:
    directory = root / "data" / "public_reference" / "synced" / provider.lower()
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f"{run_id}.csv"
    if records:
        columns = sorted({key for row in records for key in row})
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(records)
    else:
        output.write_text("", encoding="utf-8")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return output, digest


def sync_chembl_activities(
    project_root: str | Path,
    *,
    maximum_records: int = 1000,
    organism: str = "Homo sapiens",
    activity_types: tuple[str, ...] = ("IC50", "Ki", "Kd", "EC50"),
    transport: Transport = default_transport,
) -> SyncResult:
    root = Path(project_root).resolve()
    registry = runtime_database_path(root, "internet_downloads.sqlite3")
    maximum_records = min(max(int(maximum_records), 1), 10_000)
    query = {
        "target_organism": organism,
        "standard_type": list(activity_types),
        "standard_units": "nM",
        "maximum_records": maximum_records,
    }
    run_id, started = _start_run(registry, "ChEMBL", query, "public_reference_activity")
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    try:
        params = {
            "target_organism": organism,
            "standard_type__in": ",".join(activity_types),
            "standard_units": "nM",
            "limit": min(1000, maximum_records),
            "offset": 0,
            "format": "json",
        }
        url = "https://www.ebi.ac.uk/chembl/api/data/activity.json?" + urlencode(params)
        while url and len(records) < maximum_records:
            payload = get_json(url, timeout=45, transport=transport)
            activities = payload.get("activities", [])
            if not isinstance(activities, list):
                raise ValueError("ChEMBL response does not contain an activity list.")
            for row in activities:
                if not isinstance(row, dict):
                    continue
                records.append(
                    {
                        "activity_id": row.get("activity_id"),
                        "molecule_chembl_id": row.get("molecule_chembl_id"),
                        "target_chembl_id": row.get("target_chembl_id"),
                        "assay_chembl_id": row.get("assay_chembl_id"),
                        "document_chembl_id": row.get("document_chembl_id"),
                        "standard_type": row.get("standard_type"),
                        "standard_relation": row.get("standard_relation"),
                        "standard_value": row.get("standard_value"),
                        "standard_units": row.get("standard_units"),
                        "pchembl_value": row.get("pchembl_value"),
                        "target_organism": row.get("target_organism"),
                        "assay_type": row.get("assay_type"),
                        "data_validity_comment": row.get("data_validity_comment"),
                        "source_provider": "ChEMBL",
                        "scientific_scope": "public_reference_requires_curation",
                    }
                )
                if len(records) >= maximum_records:
                    break
            page_meta = payload.get("page_meta", {})
            next_value = page_meta.get("next") if isinstance(page_meta, dict) else None
            url = urljoin("https://www.ebi.ac.uk", str(next_value)) if next_value else ""
        output, digest = _write_csv(root, "chembl", run_id, records)
        relative = output.relative_to(root).as_posix()
        register_download(
            registry,
            provider="ChEMBL",
            resource_id=run_id,
            url="https://www.ebi.ac.uk/chembl/api/data/activity",
            filename=output.name,
            relative_path=relative,
            content_type="text/csv",
            size_bytes=output.stat().st_size,
            sha256=digest,
            notes="Paginated official ChEMBL activity API sync; public reference requiring evidence curation.",
        )
        completed = _finish_run(
            registry,
            run_id=run_id,
            status="completed",
            records=records,
            record_type="activity",
            output_relative_path=relative,
            output_sha256=digest,
            warnings=warnings,
        )
        return SyncResult(run_id, "ChEMBL", "completed", len(records), relative, digest, started, completed, "public_reference_requires_curation", tuple(warnings))
    except Exception as exc:
        completed = _finish_run(
            registry,
            run_id=run_id,
            status="failed",
            records=[],
            record_type="activity",
            output_relative_path="",
            output_sha256="",
            warnings=warnings,
            error=str(exc),
        )
        raise RuntimeError(f"ChEMBL synchronization failed: {exc}") from exc


def sync_uniprot_reviewed(
    project_root: str | Path,
    *,
    maximum_records: int = 1000,
    organism_id: int = 9606,
    transport: Transport = default_transport,
) -> SyncResult:
    root = Path(project_root).resolve()
    registry = runtime_database_path(root, "internet_downloads.sqlite3")
    maximum_records = min(max(int(maximum_records), 1), 5000)
    query = {"reviewed": True, "organism_id": organism_id, "maximum_records": maximum_records}
    run_id, started = _start_run(registry, "UniProt", query, "public_reference_protein")
    warnings: list[str] = []
    try:
        fields = "accession,id,protein_name,gene_names,organism_name,length,reviewed"
        url = "https://rest.uniprot.org/uniprotkb/search?" + urlencode(
            {
                "query": f"reviewed:true AND organism_id:{organism_id}",
                "format": "tsv",
                "fields": fields,
                "size": maximum_records,
            }
        )
        text = get_text(url, timeout=45, transport=transport)
        reader = csv.DictReader(StringIO(text), delimiter="\t")
        records = []
        for row in reader:
            records.append(
                {
                    "accession": row.get("Entry"),
                    "entry_name": row.get("Entry Name"),
                    "protein_name": row.get("Protein names"),
                    "gene_names": row.get("Gene Names"),
                    "organism": row.get("Organism"),
                    "length": row.get("Length"),
                    "reviewed": row.get("Reviewed"),
                    "source_provider": "UniProt",
                    "scientific_scope": "verified_public_reference",
                }
            )
        output, digest = _write_csv(root, "uniprot", run_id, records)
        relative = output.relative_to(root).as_posix()
        register_download(
            registry,
            provider="UniProt",
            resource_id=run_id,
            url="https://rest.uniprot.org/uniprotkb/search",
            filename=output.name,
            relative_path=relative,
            content_type="text/csv",
            size_bytes=output.stat().st_size,
            sha256=digest,
            notes="Official UniProt reviewed-protein metadata sync; public reference only.",
        )
        completed = _finish_run(
            registry,
            run_id=run_id,
            status="completed",
            records=records,
            record_type="protein",
            output_relative_path=relative,
            output_sha256=digest,
            warnings=warnings,
        )
        return SyncResult(run_id, "UniProt", "completed", len(records), relative, digest, started, completed, "verified_public_reference", tuple(warnings))
    except Exception as exc:
        _finish_run(registry, run_id=run_id, status="failed", records=[], record_type="protein", output_relative_path="", output_sha256="", warnings=warnings, error=str(exc))
        raise RuntimeError(f"UniProt synchronization failed: {exc}") from exc


def sync_status(project_root: str | Path, *, limit: int = 100) -> dict[str, Any]:
    registry = runtime_database_path(Path(project_root).resolve(), "internet_downloads.sqlite3")
    initialize_sync_registry(registry)
    with connect(registry, read_only=True) as connection:
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM scientific_sync_runs ORDER BY started_at_utc DESC LIMIT ?",
            (min(max(int(limit), 1), 1000),),
        ).fetchall()]
        counts = {str(row["provider"]): int(row["count"]) for row in connection.execute(
            "SELECT provider, COUNT(*) AS count FROM scientific_sync_runs GROUP BY provider"
        ).fetchall()}
        records = int(connection.execute("SELECT COUNT(*) FROM scientific_sync_records").fetchone()[0])
    return {"runs": rows, "provider_runs": counts, "normalized_records": records}
