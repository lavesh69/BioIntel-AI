from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from biointel.database.core import connect, database_health, transaction
from biointel.intelligence.data_intelligence import database_paths

DATASET_EXTENSION_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS dataset_files (
    file_id TEXT PRIMARY KEY,
    dataset_sha256 TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    file_format TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    role TEXT NOT NULL,
    compression TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    UNIQUE(dataset_sha256, relative_path)
);
CREATE INDEX IF NOT EXISTS idx_dataset_files_dataset ON dataset_files(dataset_sha256);
CREATE INDEX IF NOT EXISTS idx_dataset_files_format ON dataset_files(file_format);

CREATE TABLE IF NOT EXISTS dataset_samples (
    sample_id TEXT NOT NULL,
    dataset_sha256 TEXT NOT NULL,
    sample_name TEXT NOT NULL,
    organism TEXT,
    tissue_or_matrix TEXT,
    condition_name TEXT,
    batch_name TEXT,
    replicate_type TEXT,
    replicate_number INTEGER,
    subject_id TEXT,
    timepoint TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY(dataset_sha256, sample_id)
);
CREATE INDEX IF NOT EXISTS idx_dataset_samples_dataset ON dataset_samples(dataset_sha256);
CREATE INDEX IF NOT EXISTS idx_dataset_samples_condition ON dataset_samples(condition_name);
CREATE INDEX IF NOT EXISTS idx_dataset_samples_batch ON dataset_samples(batch_name);

CREATE TABLE IF NOT EXISTS dataset_qc_metrics (
    qc_id TEXT PRIMARY KEY,
    dataset_sha256 TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL,
    metric_text TEXT,
    unit TEXT,
    scope TEXT NOT NULL DEFAULT 'dataset',
    scope_id TEXT,
    status TEXT NOT NULL DEFAULT 'informational',
    threshold_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    UNIQUE(dataset_sha256, metric_name, scope, scope_id)
);
CREATE INDEX IF NOT EXISTS idx_dataset_qc_dataset ON dataset_qc_metrics(dataset_sha256);
CREATE INDEX IF NOT EXISTS idx_dataset_qc_status ON dataset_qc_metrics(status);

CREATE TABLE IF NOT EXISTS dataset_columns (
    dataset_sha256 TEXT NOT NULL,
    column_name TEXT NOT NULL,
    ordinal_position INTEGER NOT NULL,
    data_type TEXT NOT NULL,
    semantic_role TEXT NOT NULL,
    unit TEXT,
    description TEXT NOT NULL DEFAULT '',
    nullable INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(dataset_sha256, column_name)
);
CREATE INDEX IF NOT EXISTS idx_dataset_columns_role ON dataset_columns(semantic_role);

CREATE TABLE IF NOT EXISTS dataset_links (
    link_id TEXT PRIMARY KEY,
    source_dataset_sha256 TEXT NOT NULL,
    target_dataset_sha256 TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    UNIQUE(source_dataset_sha256, target_dataset_sha256, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_dataset_links_source ON dataset_links(source_dataset_sha256);
CREATE INDEX IF NOT EXISTS idx_dataset_links_target ON dataset_links(target_dataset_sha256);
"""

EXPERIMENT_EXTENSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiment_folds (
    experiment_id TEXT NOT NULL,
    fold_index INTEGER NOT NULL,
    train_rows INTEGER NOT NULL,
    validation_rows INTEGER NOT NULL,
    test_rows INTEGER NOT NULL,
    metrics_json TEXT NOT NULL,
    validation_metrics_json TEXT NOT NULL,
    split_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY(experiment_id, fold_index)
);
CREATE INDEX IF NOT EXISTS idx_experiment_folds_experiment ON experiment_folds(experiment_id);

CREATE TABLE IF NOT EXISTS hyperparameter_trials (
    trial_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    trial_number INTEGER NOT NULL,
    parameters_json TEXT NOT NULL,
    objective_name TEXT NOT NULL,
    objective_value REAL,
    state TEXT NOT NULL,
    duration_seconds REAL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    UNIQUE(experiment_id, trial_number)
);
CREATE INDEX IF NOT EXISTS idx_trials_experiment ON hyperparameter_trials(experiment_id);
CREATE INDEX IF NOT EXISTS idx_trials_state ON hyperparameter_trials(state);

CREATE TABLE IF NOT EXISTS experiment_runtime_metrics (
    experiment_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    unit TEXT NOT NULL,
    hardware TEXT NOT NULL DEFAULT 'local_cpu',
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY(experiment_id, metric_name)
);

CREATE TABLE IF NOT EXISTS experiment_events (
    event_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_experiment_events_experiment ON experiment_events(experiment_id, created_at_utc);
"""

EVIDENCE_EXTENSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence_assay_context (
    evidence_key TEXT NOT NULL,
    dataset_sha256 TEXT NOT NULL,
    assay_format TEXT,
    assay_system TEXT,
    organism TEXT,
    tissue_or_cell_line TEXT,
    protein_construct TEXT,
    substrate TEXT,
    temperature_c REAL,
    ph REAL,
    incubation_minutes REAL,
    cofactors TEXT,
    context_quality REAL NOT NULL DEFAULT 0.0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY(dataset_sha256, evidence_key)
);
CREATE INDEX IF NOT EXISTS idx_assay_context_dataset ON evidence_assay_context(dataset_sha256);
CREATE INDEX IF NOT EXISTS idx_assay_context_system ON evidence_assay_context(assay_system);

CREATE TABLE IF NOT EXISTS evidence_replicates (
    replicate_id TEXT PRIMARY KEY,
    evidence_key TEXT NOT NULL,
    dataset_sha256 TEXT NOT NULL,
    biological_replicate INTEGER,
    technical_replicate INTEGER,
    measured_value REAL,
    measured_unit TEXT,
    relation TEXT NOT NULL DEFAULT '=',
    qc_status TEXT NOT NULL DEFAULT 'accepted',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_replicates_key ON evidence_replicates(evidence_key);
CREATE INDEX IF NOT EXISTS idx_evidence_replicates_dataset ON evidence_replicates(dataset_sha256);

CREATE TABLE IF NOT EXISTS evidence_source_releases (
    release_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    release_label TEXT NOT NULL,
    release_date TEXT,
    connector_status TEXT NOT NULL,
    local_record_count INTEGER NOT NULL DEFAULT 0,
    checksum TEXT,
    licence_id TEXT,
    refresh_cadence TEXT,
    notes TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    UNIQUE(provider, release_label)
);
CREATE INDEX IF NOT EXISTS idx_source_releases_provider ON evidence_source_releases(provider);
CREATE INDEX IF NOT EXISTS idx_source_releases_status ON evidence_source_releases(connector_status);
"""

INTERNET_EXTENSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS scientific_source_catalog (
    source_key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    official_host TEXT NOT NULL,
    access_method TEXT NOT NULL,
    licence_profile TEXT NOT NULL,
    refresh_cadence TEXT NOT NULL,
    local_status TEXT NOT NULL,
    last_checked_at_utc TEXT,
    records_available INTEGER,
    notes TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_source_catalog_provider ON scientific_source_catalog(provider);
CREATE INDEX IF NOT EXISTS idx_source_catalog_status ON scientific_source_catalog(local_status);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def initialize_scientific_registries(root: str | Path) -> None:
    paths = database_paths(root)
    with transaction(paths["datasets"]) as connection:
        connection.executescript(DATASET_EXTENSION_SCHEMA)
    with transaction(paths["experiments"]) as connection:
        connection.executescript(EXPERIMENT_EXTENSION_SCHEMA)
    with transaction(paths["evidence"]) as connection:
        connection.executescript(EVIDENCE_EXTENSION_SCHEMA)
    with transaction(paths["downloads"]) as connection:
        connection.executescript(INTERNET_EXTENSION_SCHEMA)


def register_dataset_file(
    root: str | Path,
    *,
    dataset_sha256: str,
    relative_path: str,
    role: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    project_root = Path(root).resolve()
    absolute = project_root / relative_path
    if not absolute.is_file():
        raise FileNotFoundError(absolute)
    file_hash = sha256_file(absolute)
    file_id = hashlib.sha256(f"{dataset_sha256}|{relative_path}".encode()).hexdigest()[:32]
    suffix = absolute.suffix.lower().lstrip(".") or "unknown"
    compression = "gzip" if absolute.suffix.lower() in {".gz", ".bgz"} else None
    with transaction(runtime_database_path(project_root, "datasets.sqlite3")) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO dataset_files(
                file_id,dataset_sha256,relative_path,file_format,size_bytes,sha256,
                role,compression,metadata_json,created_at_utc
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                file_id,
                dataset_sha256,
                relative_path,
                suffix,
                absolute.stat().st_size,
                file_hash,
                role,
                compression,
                json.dumps(metadata or {}, sort_keys=True, default=str),
                utc_now(),
            ),
        )
    return file_id


def replace_dataset_samples(root: str | Path, dataset_sha256: str, rows: Iterable[dict[str, Any]]) -> int:
    project_root = Path(root).resolve()
    prepared = list(rows)
    with transaction(runtime_database_path(project_root, "datasets.sqlite3")) as connection:
        connection.execute("DELETE FROM dataset_samples WHERE dataset_sha256=?", (dataset_sha256,))
        connection.executemany(
            """
            INSERT INTO dataset_samples(
                sample_id,dataset_sha256,sample_name,organism,tissue_or_matrix,
                condition_name,batch_name,replicate_type,replicate_number,subject_id,
                timepoint,metadata_json,created_at_utc
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    str(row["sample_id"]),
                    dataset_sha256,
                    str(row.get("sample_name") or row["sample_id"]),
                    row.get("organism"),
                    row.get("tissue_or_matrix"),
                    row.get("condition_name"),
                    row.get("batch_name"),
                    row.get("replicate_type"),
                    row.get("replicate_number"),
                    row.get("subject_id"),
                    row.get("timepoint"),
                    json.dumps(row.get("metadata", {}), sort_keys=True, default=str),
                    utc_now(),
                )
                for row in prepared
            ],
        )
    return len(prepared)


def replace_dataset_qc(root: str | Path, dataset_sha256: str, rows: Iterable[dict[str, Any]]) -> int:
    project_root = Path(root).resolve()
    prepared = list(rows)
    with transaction(runtime_database_path(project_root, "datasets.sqlite3")) as connection:
        connection.execute("DELETE FROM dataset_qc_metrics WHERE dataset_sha256=?", (dataset_sha256,))
        connection.executemany(
            """
            INSERT INTO dataset_qc_metrics(
                qc_id,dataset_sha256,metric_name,metric_value,metric_text,unit,
                scope,scope_id,status,threshold_json,created_at_utc
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    hashlib.sha256(
                        f"{dataset_sha256}|{row['metric_name']}|{row.get('scope','dataset')}|{row.get('scope_id','')}".encode()
                    ).hexdigest()[:32],
                    dataset_sha256,
                    str(row["metric_name"]),
                    row.get("metric_value"),
                    row.get("metric_text"),
                    row.get("unit"),
                    row.get("scope", "dataset"),
                    row.get("scope_id"),
                    row.get("status", "informational"),
                    json.dumps(row.get("threshold", {}), sort_keys=True, default=str),
                    utc_now(),
                )
                for row in prepared
            ],
        )
    return len(prepared)


def replace_dataset_columns(root: str | Path, dataset_sha256: str, rows: Iterable[dict[str, Any]]) -> int:
    project_root = Path(root).resolve()
    prepared = list(rows)
    with transaction(runtime_database_path(project_root, "datasets.sqlite3")) as connection:
        connection.execute("DELETE FROM dataset_columns WHERE dataset_sha256=?", (dataset_sha256,))
        connection.executemany(
            """
            INSERT INTO dataset_columns(
                dataset_sha256,column_name,ordinal_position,data_type,semantic_role,
                unit,description,nullable,metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    dataset_sha256,
                    str(row["column_name"]),
                    int(row["ordinal_position"]),
                    str(row.get("data_type", "string")),
                    str(row.get("semantic_role", "feature")),
                    row.get("unit"),
                    str(row.get("description", "")),
                    int(bool(row.get("nullable", True))),
                    json.dumps(row.get("metadata", {}), sort_keys=True, default=str),
                )
                for row in prepared
            ],
        )
    return len(prepared)


def scientific_registry_summary(root: str | Path) -> dict[str, Any]:
    project_root = Path(root).resolve()
    initialize_scientific_registries(project_root)
    # Step 31 readiness tables are part of the scientific registry surface.
    # Import locally to avoid a module-level dependency cycle.
    from biointel.data.readiness import initialize_readiness_schema

    initialize_readiness_schema(project_root)
    tables_by_db = {
        "datasets.sqlite3": (
            "datasets",
            "dataset_files",
            "dataset_samples",
            "dataset_qc_metrics",
            "dataset_columns",
            "dataset_links",
            "dataset_provenance",
            "dataset_validation_issues",
            "dataset_readiness",
            "dataset_aliases",
        ),
        "experiments.sqlite3": (
            "experiments",
            "experiment_folds",
            "hyperparameter_trials",
            "experiment_runtime_metrics",
            "experiment_events",
            "experiment_dataset_bindings",
            "experiment_artifacts",
            "experiment_validation_requirements",
        ),
        "evidence.sqlite3": (
            "dataset_evidence_links",
            "evidence_assay_context",
            "evidence_replicates",
            "evidence_source_releases",
        ),
        "internet_downloads.sqlite3": (
            "internet_downloads",
            "scientific_source_catalog",
            "source_sync_events",
        ),
    }
    payload: dict[str, Any] = {"generated_at_utc": utc_now(), "databases": {}}
    for filename, tables in tables_by_db.items():
        path = runtime_database_path(project_root, filename)
        with connect(path, read_only=True) as connection:
            counts = {table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]) for table in tables}
        payload["databases"][filename] = {
            "health": asdict(database_health(path, name=filename.removesuffix(".sqlite3"))),
            "counts": counts,
        }
    return payload
