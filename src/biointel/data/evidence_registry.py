from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

import pandas as pd

from biointel.database.core import connect, database_health, execute_many_chunked, transaction

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS evidence_licenses (license_id TEXT PRIMARY KEY,license_name TEXT NOT NULL,license_version TEXT,license_url TEXT,commercial_use TEXT NOT NULL,redistribution TEXT NOT NULL,attribution_required INTEGER NOT NULL,notes TEXT NOT NULL,created_at_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence_sources (source_id TEXT PRIMARY KEY,source_name TEXT NOT NULL,source_release TEXT,homepage_url TEXT,license_id TEXT,retrieved_at_utc TEXT NOT NULL,source_sha256 TEXT,local_path TEXT,record_count INTEGER NOT NULL,metadata_json TEXT NOT NULL,FOREIGN KEY(license_id) REFERENCES evidence_licenses(license_id));
CREATE TABLE IF NOT EXISTS evidence_publications (publication_id TEXT PRIMARY KEY,pmid TEXT,doi TEXT,title TEXT,journal TEXT,publication_year INTEGER,source_url TEXT,metadata_json TEXT NOT NULL,created_at_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence_import_runs (run_id TEXT PRIMARY KEY,provider TEXT NOT NULL,source_release TEXT,status TEXT NOT NULL,started_at_utc TEXT NOT NULL,completed_at_utc TEXT,input_rows INTEGER NOT NULL,curated_rows INTEGER NOT NULL,rejected_rows INTEGER NOT NULL,source_sha256 TEXT,parameters_json TEXT NOT NULL,report_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dataset_evidence_links (link_id TEXT PRIMARY KEY,dataset_sha256 TEXT NOT NULL,evidence_key TEXT NOT NULL,source_id TEXT NOT NULL,publication_id TEXT,source_record_id TEXT,assay_id TEXT,license_id TEXT,evidence_quality REAL NOT NULL,review_status TEXT NOT NULL,notes TEXT NOT NULL,created_at_utc TEXT NOT NULL,UNIQUE(dataset_sha256,evidence_key),FOREIGN KEY(source_id) REFERENCES evidence_sources(source_id),FOREIGN KEY(publication_id) REFERENCES evidence_publications(publication_id),FOREIGN KEY(license_id) REFERENCES evidence_licenses(license_id));
CREATE TABLE IF NOT EXISTS evidence_reviews (review_id TEXT PRIMARY KEY,dataset_sha256 TEXT NOT NULL,evidence_key TEXT NOT NULL,decision TEXT NOT NULL,reviewer TEXT NOT NULL,comment TEXT NOT NULL,original_json TEXT NOT NULL,revised_json TEXT NOT NULL,created_at_utc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_evidence_sources_name_release ON evidence_sources(source_name,source_release);
CREATE INDEX IF NOT EXISTS idx_evidence_links_dataset_status ON dataset_evidence_links(dataset_sha256,review_status);
CREATE INDEX IF NOT EXISTS idx_evidence_links_source ON dataset_evidence_links(source_id,source_record_id);
CREATE INDEX IF NOT EXISTS idx_evidence_links_publication ON dataset_evidence_links(publication_id);
CREATE INDEX IF NOT EXISTS idx_reviews_dataset_decision ON evidence_reviews(dataset_sha256,decision);
CREATE INDEX IF NOT EXISTS idx_import_runs_provider_time ON evidence_import_runs(provider,started_at_utc DESC);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def initialize_evidence_registry(path: str | Path) -> Path:
    registry = Path(path).resolve()
    registry.parent.mkdir(parents=True, exist_ok=True)
    with connect(registry) as connection:
        connection.executescript(SCHEMA)
        connection.commit()
    return registry


@dataclass(frozen=True)
class EvidenceLicense:
    license_id: str
    license_name: str
    license_version: str | None
    license_url: str | None
    commercial_use: str
    redistribution: str
    attribution_required: bool
    notes: str
    created_at_utc: str


@dataclass(frozen=True)
class EvidenceSource:
    source_id: str
    source_name: str
    source_release: str | None
    homepage_url: str | None
    license_id: str | None
    retrieved_at_utc: str
    source_sha256: str | None
    local_path: str | None
    record_count: int
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ImportRun:
    run_id: str
    provider: str
    source_release: str | None
    status: str
    started_at_utc: str
    completed_at_utc: str | None
    input_rows: int
    curated_rows: int
    rejected_rows: int
    source_sha256: str | None
    parameters: dict[str, Any]
    report: dict[str, Any]


def register_license(
    registry_path: str | Path,
    *,
    license_id: str,
    license_name: str,
    license_version: str | None = None,
    license_url: str | None = None,
    commercial_use: str = "verify_terms",
    redistribution: str = "verify_terms",
    attribution_required: bool = True,
    notes: str = "",
) -> EvidenceLicense:
    record = EvidenceLicense(
        license_id.strip(),
        license_name.strip(),
        license_version,
        license_url,
        commercial_use,
        redistribution,
        bool(attribution_required),
        notes,
        utc_now(),
    )
    if not record.license_id or not record.license_name:
        raise ValueError("license_id and license_name are required")
    path = initialize_evidence_registry(registry_path)
    with transaction(path) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO evidence_licenses VALUES (?,?,?,?,?,?,?,?,?)",
            (
                record.license_id,
                record.license_name,
                record.license_version,
                record.license_url,
                record.commercial_use,
                record.redistribution,
                int(record.attribution_required),
                record.notes,
                record.created_at_utc,
            ),
        )
    return record


def register_source(
    registry_path: str | Path,
    *,
    source_name: str,
    source_release: str | None = None,
    homepage_url: str | None = None,
    license_id: str | None = None,
    source_sha256: str | None = None,
    local_path: str | None = None,
    record_count: int = 0,
    metadata: dict[str, Any] | None = None,
    source_id: str | None = None,
) -> EvidenceSource:
    if not source_name.strip():
        raise ValueError("source_name is required")
    identity = "|".join(
        [source_name.strip(), source_release or "", source_sha256 or "", local_path or ""]
    )
    record = EvidenceSource(
        source_id or hashlib.sha256(identity.encode()).hexdigest()[:24],
        source_name.strip(),
        source_release,
        homepage_url,
        license_id,
        utc_now(),
        source_sha256,
        local_path,
        max(0, int(record_count)),
        metadata or {},
    )
    path = initialize_evidence_registry(registry_path)
    with transaction(path) as connection:
        connection.execute(
            """INSERT OR REPLACE INTO evidence_sources(source_id,source_name,source_release,homepage_url,license_id,retrieved_at_utc,source_sha256,local_path,record_count,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                record.source_id,
                record.source_name,
                record.source_release,
                record.homepage_url,
                record.license_id,
                record.retrieved_at_utc,
                record.source_sha256,
                record.local_path,
                record.record_count,
                json.dumps(record.metadata, sort_keys=True, default=str),
            ),
        )
    return record


def register_publication(
    registry_path: str | Path,
    *,
    publication_id: str,
    pmid: str | None = None,
    doi: str | None = None,
    title: str | None = None,
    journal: str | None = None,
    publication_year: int | None = None,
    source_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    if not publication_id.strip():
        raise ValueError("publication_id is required")
    path = initialize_evidence_registry(registry_path)
    with transaction(path) as connection:
        connection.execute(
            """INSERT OR REPLACE INTO evidence_publications(publication_id,pmid,doi,title,journal,publication_year,source_url,metadata_json,created_at_utc) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                publication_id.strip(),
                pmid,
                doi,
                title,
                journal,
                int(publication_year) if publication_year else None,
                source_url,
                json.dumps(metadata or {}, sort_keys=True, default=str),
                utc_now(),
            ),
        )
    return publication_id.strip()


def start_import_run(
    registry_path: str | Path,
    *,
    provider: str,
    source_release: str | None = None,
    source_sha256: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> ImportRun:
    run = ImportRun(
        uuid4().hex,
        provider.strip(),
        source_release,
        "running",
        utc_now(),
        None,
        0,
        0,
        0,
        source_sha256,
        parameters or {},
        {},
    )
    path = initialize_evidence_registry(registry_path)
    with transaction(path) as connection:
        connection.execute(
            "INSERT INTO evidence_import_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                run.run_id,
                run.provider,
                run.source_release,
                run.status,
                run.started_at_utc,
                None,
                0,
                0,
                0,
                run.source_sha256,
                json.dumps(run.parameters, sort_keys=True, default=str),
                "{}",
            ),
        )
    return run


def complete_import_run(
    registry_path: str | Path,
    run_id: str,
    *,
    status: str,
    input_rows: int,
    curated_rows: int,
    rejected_rows: int,
    report: dict[str, Any] | None = None,
) -> None:
    path = initialize_evidence_registry(registry_path)
    with transaction(path) as connection:
        connection.execute(
            """UPDATE evidence_import_runs SET status=?,completed_at_utc=?,input_rows=?,curated_rows=?,rejected_rows=?,report_json=? WHERE run_id=?""",
            (
                status,
                utc_now(),
                int(input_rows),
                int(curated_rows),
                int(rejected_rows),
                json.dumps(report or {}, sort_keys=True, default=str),
                run_id,
            ),
        )


def _text(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


def link_curated_dataset(
    registry_path: str | Path,
    *,
    dataset_sha256: str,
    source_id: str,
    curated: pd.DataFrame,
    default_license_id: str | None = None,
) -> int:
    path = initialize_evidence_registry(registry_path)
    rows = []
    with transaction(path) as connection:
        for _, item in curated.iterrows():
            publication_id = _text(item.get("publication_id"))
            if publication_id:
                connection.execute(
                    "INSERT OR IGNORE INTO evidence_publications(publication_id,metadata_json,created_at_utc) VALUES (?,?,?)",
                    (publication_id, "{}", utc_now()),
                )
            evidence_key = str(
                item.get("evidence_key")
                or hashlib.sha256(
                    json.dumps(item.to_dict(), sort_keys=True, default=str).encode()
                ).hexdigest()
            )
            rows.append(
                (
                    uuid4().hex,
                    dataset_sha256,
                    evidence_key,
                    source_id,
                    publication_id,
                    _text(item.get("source_record_id")),
                    _text(item.get("assay_id")),
                    _text(item.get("license_id")) or default_license_id,
                    float(item.get("assay_quality_score", 0.0) or 0.0),
                    _text(item.get("review_status")) or "pending",
                    "",
                    utc_now(),
                )
            )
        execute_many_chunked(
            connection,
            """INSERT OR REPLACE INTO dataset_evidence_links(link_id,dataset_sha256,evidence_key,source_id,publication_id,source_record_id,assay_id,license_id,evidence_quality,review_status,notes,created_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
            chunk_size=1000,
        )
    return len(rows)


def record_review(
    registry_path: str | Path,
    *,
    dataset_sha256: str,
    evidence_key: str,
    decision: str,
    reviewer: str,
    comment: str = "",
    original: dict[str, Any] | None = None,
    revised: dict[str, Any] | None = None,
) -> str:
    decision = decision.strip().lower()
    if decision not in {"pending", "accepted", "rejected", "edited"}:
        raise ValueError("decision must be pending, accepted, rejected or edited")
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    review_id = uuid4().hex
    path = initialize_evidence_registry(registry_path)
    with transaction(path) as connection:
        connection.execute(
            "INSERT INTO evidence_reviews VALUES (?,?,?,?,?,?,?,?,?)",
            (
                review_id,
                dataset_sha256,
                evidence_key,
                decision,
                reviewer.strip(),
                comment.strip(),
                json.dumps(original or {}, sort_keys=True, default=str),
                json.dumps(revised or {}, sort_keys=True, default=str),
                utc_now(),
            ),
        )
        connection.execute(
            "UPDATE dataset_evidence_links SET review_status=? WHERE dataset_sha256=? AND evidence_key=?",
            (decision, dataset_sha256, evidence_key),
        )
    return review_id


def evidence_readiness(registry_path: str | Path, dataset_sha256: str) -> dict[str, Any]:
    path = initialize_evidence_registry(registry_path)
    with connect(path, read_only=True) as connection:
        row = connection.execute(
            """SELECT COUNT(*) rows_total,SUM(CASE WHEN license_id IS NOT NULL THEN 1 ELSE 0 END) licensed_rows,SUM(CASE WHEN publication_id IS NOT NULL THEN 1 ELSE 0 END) publication_rows,SUM(CASE WHEN review_status='accepted' THEN 1 ELSE 0 END) accepted_rows,SUM(CASE WHEN review_status='rejected' THEN 1 ELSE 0 END) rejected_rows,AVG(evidence_quality) mean_quality,COUNT(DISTINCT source_id) source_count FROM dataset_evidence_links WHERE dataset_sha256=?""",
            (dataset_sha256,),
        ).fetchone()
    total = int(row["rows_total"] or 0)
    licensed, publication, accepted, rejected = (
        int(row[key] or 0)
        for key in ("licensed_rows", "publication_rows", "accepted_rows", "rejected_rows")
    )
    return {
        "dataset_sha256": dataset_sha256,
        "rows_total": total,
        "licensed_rows": licensed,
        "publication_rows": publication,
        "accepted_rows": accepted,
        "rejected_rows": rejected,
        "source_count": int(row["source_count"] or 0),
        "mean_quality": round(float(row["mean_quality"] or 0.0), 4),
        "license_coverage": round(licensed / max(total, 1), 4),
        "publication_coverage": round(publication / max(total, 1), 4),
        "review_coverage": round(accepted / max(total, 1), 4),
        "release_ready": bool(total and licensed == total and accepted == total and rejected == 0),
    }


def list_import_runs(registry_path: str | Path, limit: int = 100) -> list[dict[str, Any]]:
    path = initialize_evidence_registry(registry_path)
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            "SELECT * FROM evidence_import_runs ORDER BY started_at_utc DESC LIMIT ?",
            (max(1, min(int(limit), 1000)),),
        ).fetchall()
    return [
        {
            **dict(row),
            "parameters": json.loads(row["parameters_json"]),
            "report": json.loads(row["report_json"]),
        }
        for row in rows
    ]


def list_evidence_links(
    registry_path: str | Path,
    *,
    dataset_sha256: str | None = None,
    review_status: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    path = initialize_evidence_registry(registry_path)
    clauses, parameters = [], []
    if dataset_sha256:
        clauses.append("links.dataset_sha256=?")
        parameters.append(dataset_sha256)
    if review_status:
        clauses.append("links.review_status=?")
        parameters.append(review_status.lower())
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    parameters.append(max(1, min(int(limit), 5000)))
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            f"""SELECT links.*,sources.source_name,sources.source_release,licenses.license_name FROM dataset_evidence_links links JOIN evidence_sources sources ON sources.source_id=links.source_id LEFT JOIN evidence_licenses licenses ON licenses.license_id=links.license_id {where} ORDER BY links.created_at_utc DESC LIMIT ?""",
            tuple(parameters),
        ).fetchall()
    return [dict(row) for row in rows]


def seed_standard_licenses(registry_path: str | Path) -> list[EvidenceLicense]:
    definitions: Iterable[dict[str, Any]] = (
        {
            "license_id": "CHEMBL_TERMS",
            "license_name": "ChEMBL terms and licensing",
            "license_url": "https://www.ebi.ac.uk/chembl/about",
        },
        {
            "license_id": "BINDINGDB_TERMS",
            "license_name": "BindingDB terms and citation requirements",
            "license_url": "https://www.bindingdb.org/rwd/bind/info.jsp",
        },
        {
            "license_id": "PUBCHEM_PUBLIC_DATA",
            "license_name": "PubChem public data notice",
            "license_url": "https://pubchem.ncbi.nlm.nih.gov/docs/downloads",
        },
        {
            "license_id": "UNIPROT_TERMS",
            "license_name": "UniProt terms and citation requirements",
            "license_url": "https://www.uniprot.org/help/license",
        },
        {
            "license_id": "LOCAL_USER_SUPPLIED",
            "license_name": "User-supplied data terms",
            "commercial_use": "user_responsibility",
            "redistribution": "user_responsibility",
            "attribution_required": False,
            "notes": "Operator must verify the original source licence.",
        },
    )
    return [register_license(registry_path, **item) for item in definitions]


def registry_summary(registry_path: str | Path) -> dict[str, Any]:
    path = initialize_evidence_registry(registry_path)
    tables = (
        "evidence_licenses",
        "evidence_sources",
        "evidence_publications",
        "evidence_import_runs",
        "dataset_evidence_links",
        "evidence_reviews",
        "evidence_assay_context",
        "evidence_replicates",
        "evidence_source_releases",
    )
    with connect(path, read_only=True) as connection:
        counts = {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in tables
        }
    return {
        "database": asdict(database_health(path, name="Evidence Registry")),
        "counts": counts,
        "generated_at_utc": utc_now(),
    }


def license_json(record: EvidenceLicense) -> str:
    return json.dumps(asdict(record), indent=2, sort_keys=True, default=str)
