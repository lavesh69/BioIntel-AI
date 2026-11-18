from __future__ import annotations

from biointel.runtime_paths import runtime_database_path

import hashlib
import json
import sqlite3
from biointel.database.core import managed_connect
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from biointel.database.core import transaction
from biointel.dti.feature_cache import FeatureCache


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


DATASET_READINESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS dataset_aliases (
    alias_sha256 TEXT NOT NULL,
    task_type TEXT NOT NULL,
    canonical_dataset_sha256 TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY(alias_sha256, task_type)
);
CREATE INDEX IF NOT EXISTS idx_dataset_aliases_canonical
ON dataset_aliases(canonical_dataset_sha256, task_type);

CREATE TABLE IF NOT EXISTS dataset_provenance (
    provenance_id TEXT PRIMARY KEY,
    dataset_sha256 TEXT NOT NULL,
    source_type TEXT NOT NULL,
    provider TEXT,
    release_label TEXT,
    licence_id TEXT,
    external_id TEXT,
    access_method TEXT,
    status TEXT NOT NULL,
    retrieved_at_utc TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dataset_provenance_dataset
ON dataset_provenance(dataset_sha256);
CREATE INDEX IF NOT EXISTS idx_dataset_provenance_provider
ON dataset_provenance(provider, status);

CREATE TABLE IF NOT EXISTS dataset_validation_issues (
    issue_id TEXT PRIMARY KEY,
    dataset_sha256 TEXT NOT NULL,
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    resolution_status TEXT NOT NULL DEFAULT 'open',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    resolved_at_utc TEXT
);
CREATE INDEX IF NOT EXISTS idx_dataset_issues_dataset
ON dataset_validation_issues(dataset_sha256, resolution_status);

CREATE TABLE IF NOT EXISTS dataset_readiness (
    dataset_sha256 TEXT PRIMARY KEY,
    file_count INTEGER NOT NULL,
    column_count INTEGER NOT NULL,
    sample_count INTEGER NOT NULL,
    qc_count INTEGER NOT NULL,
    lineage_count INTEGER NOT NULL,
    provenance_count INTEGER NOT NULL,
    sample_metadata_applicable INTEGER NOT NULL DEFAULT 0,
    metadata_completeness REAL NOT NULL,
    integrity_status TEXT NOT NULL,
    scientific_status TEXT NOT NULL,
    readiness_score REAL NOT NULL,
    blockers_json TEXT NOT NULL DEFAULT '[]',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    calculated_at_utc TEXT NOT NULL
);
"""

EXPERIMENT_READINESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiment_dataset_bindings (
    experiment_id TEXT NOT NULL,
    dataset_sha256 TEXT NOT NULL,
    binding_role TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    verification_message TEXT NOT NULL DEFAULT '',
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY(experiment_id, dataset_sha256, binding_role)
);
CREATE INDEX IF NOT EXISTS idx_experiment_bindings_dataset
ON experiment_dataset_bindings(dataset_sha256);

CREATE TABLE IF NOT EXISTS experiment_artifacts (
    artifact_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    relative_path TEXT,
    sha256 TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_experiment_artifacts_experiment
ON experiment_artifacts(experiment_id, artifact_type);

CREATE TABLE IF NOT EXISTS experiment_validation_requirements (
    experiment_id TEXT NOT NULL,
    requirement_key TEXT NOT NULL,
    requirement_label TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    evidence_reference TEXT,
    checked_at_utc TEXT NOT NULL,
    PRIMARY KEY(experiment_id, requirement_key)
);
CREATE INDEX IF NOT EXISTS idx_experiment_requirements_status
ON experiment_validation_requirements(status);
"""

PROJECT_READINESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS project_resources (
    resource_link_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    status TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at_utc TEXT NOT NULL,
    UNIQUE(project_id, resource_type, resource_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_project_resources_project
ON project_resources(project_id, resource_type);
"""

INTERNET_READINESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_sync_events (
    event_id TEXT PRIMARY KEY,
    source_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    records_seen INTEGER NOT NULL DEFAULT 0,
    records_imported INTEGER NOT NULL DEFAULT 0,
    checksum TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_source_sync_events_source
ON source_sync_events(source_key, created_at_utc);
"""

DOCUMENT_READINESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS document_registry_versions (
    run_id TEXT PRIMARY KEY,
    registry_version TEXT NOT NULL,
    original_engine_version TEXT NOT NULL,
    last_verified_at_utc TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
"""

FEATURE_PROFILE_SCHEMA = """
CREATE TABLE IF NOT EXISTS feature_cache_profiles (
    profile_key TEXT PRIMARY KEY,
    feature_kind TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    library_name TEXT NOT NULL,
    library_version TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    entry_count INTEGER NOT NULL DEFAULT 0,
    valid_count INTEGER NOT NULL DEFAULT 0,
    invalid_count INTEGER NOT NULL DEFAULT 0,
    updated_at_utc TEXT NOT NULL
);
"""


def _ensure_column(connection: sqlite3.Connection, table: str, name: str, definition: str) -> None:
    columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
    if name not in columns:
        connection.execute(f'ALTER TABLE "{table}" ADD COLUMN {name} {definition}')


@lru_cache(maxsize=16)
def _initialize_readiness_schema_once(root_text: str) -> None:
    project_root = Path(root_text).resolve()
    with transaction(runtime_database_path(project_root, "datasets.sqlite3")) as connection:
        connection.executescript(DATASET_READINESS_SCHEMA)
    with transaction(runtime_database_path(project_root, "experiments.sqlite3")) as connection:
        connection.executescript(EXPERIMENT_READINESS_SCHEMA)
        _ensure_column(connection, "experiment_dataset_bindings", "resolved_dataset_sha256", "TEXT")
        _ensure_column(
            connection,
            "experiment_dataset_bindings",
            "resolution_type",
            "TEXT NOT NULL DEFAULT 'direct'",
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_experiment_bindings_resolved ON experiment_dataset_bindings(resolved_dataset_sha256, verified)"
        )
    with transaction(runtime_database_path(project_root, "projects.sqlite3")) as connection:
        connection.executescript(PROJECT_READINESS_SCHEMA)
    with transaction(runtime_database_path(project_root, "internet_downloads.sqlite3")) as connection:
        connection.executescript(INTERNET_READINESS_SCHEMA)
    with transaction(runtime_database_path(project_root, "document_history.sqlite3")) as connection:
        connection.executescript(DOCUMENT_READINESS_SCHEMA)
    feature_cache_path = runtime_database_path(project_root, "feature_cache.sqlite3")
    FeatureCache(feature_cache_path)
    with transaction(feature_cache_path) as connection:
        connection.executescript(FEATURE_PROFILE_SCHEMA)
        _ensure_column(
            connection, "feature_cache", "schema_version", "TEXT NOT NULL DEFAULT 'legacy-v1'"
        )
        _ensure_column(
            connection,
            "feature_cache",
            "library_version",
            "TEXT NOT NULL DEFAULT 'bundled-runtime'",
        )
        _ensure_column(connection, "feature_cache", "parameters_json", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(connection, "feature_cache", "entity_id", "TEXT")
        _ensure_column(connection, "feature_cache", "source_dataset_sha256", "TEXT")
        _ensure_column(
            connection, "feature_cache", "validation_status", "TEXT NOT NULL DEFAULT 'valid'"
        )
        _ensure_column(connection, "feature_cache", "error_message", "TEXT")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_feature_cache_schema ON feature_cache(feature_kind, schema_version, validation_status)"
        )


def initialize_readiness_schema(root: str | Path) -> None:
    """Initialize readiness tables once per project process.

    The schema is idempotent, but executing six write transactions on every
    Streamlit rerun caused avoidable locks and multi-second page stalls.
    """

    _initialize_readiness_schema_once(str(Path(root).resolve()))


def clear_readiness_schema_cache() -> None:
    _initialize_readiness_schema_once.cache_clear()


def _json_object(value: object) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def backfill_missing_dataset_readiness(root: str | Path) -> int:
    """Create readiness/QC coverage records for datasets added after older seeds.

    Historical release scripts populated readiness rows only for the datasets that
    existed at that step. Later scientific expansion releases can legitimately add
    datasets, so readiness must be incrementally and idempotently backfilled rather
    than relying on a frozen historical count.
    """

    project_root = Path(root).resolve()
    initialize_readiness_schema(project_root)
    database = runtime_database_path(project_root, "datasets.sqlite3")
    applicable_terms = (
        "fastq", "variant", "rna-seq", "transcriptomics", "proteomics",
        "microbiome", "qpcr", "elisa", "bioprocess", "single-cell",
        "clinical", "genomics", "structure", "pathway",
    )
    created = 0
    with transaction(database) as connection:
        connection.row_factory = sqlite3.Row
        missing = connection.execute(
            """
            SELECT d.*
            FROM datasets d
            LEFT JOIN dataset_readiness r USING(dataset_sha256)
            WHERE r.dataset_sha256 IS NULL
            ORDER BY d.dataset_name
            """
        ).fetchall()
        now = utc_now()
        for row in missing:
            sha = str(row["dataset_sha256"])
            name = str(row["dataset_name"] or "")
            metadata = _json_object(row["metadata_json"])
            counts = {
                table: int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE dataset_sha256=?",
                        (sha,),
                    ).fetchone()[0]
                )
                for table in (
                    "dataset_files", "dataset_columns", "dataset_samples",
                    "dataset_qc_metrics", "dataset_provenance",
                )
            }
            lineage = int(
                connection.execute(
                    "SELECT COUNT(*) FROM dataset_links WHERE source_dataset_sha256=? OR target_dataset_sha256=?",
                    (sha, sha),
                ).fetchone()[0]
            )
            primary = int(
                connection.execute(
                    "SELECT COUNT(*) FROM dataset_files WHERE dataset_sha256=? AND role IN ('primary_data','primary')",
                    (sha,),
                ).fetchone()[0]
            )
            applicable = int(any(term in name.casefold() for term in applicable_terms))
            required_metadata = (
                row["dataset_name"], row["dataset_version"], row["task_type"],
                row["source_description"], row["column_names_json"], row["metadata_json"],
            )
            completeness = round(100.0 * sum(bool(value) for value in required_metadata) / len(required_metadata), 2)
            blockers: list[str] = []
            warnings: list[str] = []
            if counts["dataset_columns"] == 0:
                blockers.append("Column dictionary is missing")
            if counts["dataset_files"] == 0:
                blockers.append("No registered file or manifest")
            if counts["dataset_files"] and primary == 0:
                warnings.append("No primary data file; registry manifest only")
            if applicable and counts["dataset_samples"] == 0:
                warnings.append("Sample-level metadata is expected but missing")
            if counts["dataset_qc_metrics"] < 3:
                warnings.append("QC coverage is limited")
            synthetic = bool(
                metadata.get("synthetic")
                or metadata.get("demo_only")
                or metadata.get("preloaded_demo")
                or "synthetic" in name.casefold()
            )
            release_eligible = bool(metadata.get("scientific_release_eligible", False)) and not synthetic
            reference_only = bool(
                metadata.get("real_public_reference")
                or metadata.get("public_reference")
                or "reference" in str(row["task_type"] or "").casefold()
                or "reference" in name.casefold()
            )
            scientific_status = (
                "release_eligible"
                if release_eligible
                else "reference_only" if (synthetic or reference_only) else "needs_evidence_review"
            )
            score = 0.0
            score += 20 if counts["dataset_files"] else 0
            score += 15 if primary else (7 if counts["dataset_files"] else 0)
            score += 20 if counts["dataset_columns"] else 0
            score += 15 if counts["dataset_qc_metrics"] >= 3 else min(counts["dataset_qc_metrics"] * 4, 12)
            score += 10 if counts["dataset_provenance"] else 0
            score += 8 if lineage or not row["parent_sha256"] else 0
            score += 7 if (not applicable or counts["dataset_samples"] > 0) else 0
            score += 5 * completeness / 100
            score = min(100.0, round(score, 2))
            integrity = "verified" if primary else ("manifest_only" if counts["dataset_files"] else "registry_only")
            connection.execute(
                """
                INSERT INTO dataset_readiness(
                    dataset_sha256,file_count,column_count,sample_count,qc_count,
                    lineage_count,provenance_count,sample_metadata_applicable,
                    metadata_completeness,integrity_status,scientific_status,
                    readiness_score,blockers_json,warnings_json,calculated_at_utc
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sha, counts["dataset_files"], counts["dataset_columns"],
                    counts["dataset_samples"], counts["dataset_qc_metrics"], lineage,
                    counts["dataset_provenance"], applicable, completeness, integrity,
                    scientific_status, score, json.dumps(blockers), json.dumps(warnings), now,
                ),
            )
            for severity, category, messages in (
                ("blocker", "completeness", blockers),
                ("warning", "coverage", warnings),
            ):
                for message in messages:
                    issue_id = hashlib.sha256(
                        f"{sha}|{severity}|{category}|{message}".encode("utf-8")
                    ).hexdigest()[:28]
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO dataset_validation_issues(
                            issue_id,dataset_sha256,severity,category,message,
                            resolution_status,metadata_json,created_at_utc,resolved_at_utc
                        ) VALUES (?,?,?,?,?,'open','{}',?,NULL)
                        """,
                        (issue_id, sha, severity, category, message, now),
                    )
            created += 1
    return created

def dataset_readiness_rows(root: str | Path) -> list[dict[str, Any]]:
    project_root = Path(root).resolve()
    initialize_readiness_schema(project_root)
    backfill_missing_dataset_readiness(project_root)
    path = runtime_database_path(project_root, "datasets.sqlite3")
    with managed_connect(path) as connection:
        connection.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in connection.execute(
                """
                SELECT d.dataset_name,d.dataset_version,d.task_type,d.row_count,
                       d.source_description,d.dataset_sha256,d.metadata_json,
                       r.file_count,r.column_count,r.sample_count,r.qc_count,
                       r.lineage_count,r.provenance_count,r.sample_metadata_applicable,
                       r.metadata_completeness,r.integrity_status,r.scientific_status,
                       r.readiness_score,r.blockers_json,r.warnings_json,r.calculated_at_utc
                FROM datasets d
                LEFT JOIN dataset_readiness r USING(dataset_sha256)
                ORDER BY COALESCE(r.readiness_score,0) ASC,d.dataset_name
                """
            )
        ]


def platform_readiness_summary(root: str | Path) -> dict[str, Any]:
    project_root = Path(root).resolve()
    initialize_readiness_schema(project_root)
    backfilled = backfill_missing_dataset_readiness(project_root)
    payload: dict[str, Any] = {
        "generated_at_utc": utc_now(),
        "readiness_rows_backfilled": backfilled,
    }
    with managed_connect(runtime_database_path(project_root, "datasets.sqlite3")) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT (SELECT COUNT(*) FROM datasets) datasets,
                   COUNT(*) readiness_scored,
                   SUM(CASE WHEN file_count>0 THEN 1 ELSE 0 END) with_files,
                   SUM(CASE WHEN column_count>0 THEN 1 ELSE 0 END) with_columns,
                   SUM(CASE WHEN qc_count>0 THEN 1 ELSE 0 END) with_qc,
                   SUM(CASE WHEN provenance_count>0 THEN 1 ELSE 0 END) with_provenance,
                   SUM(CASE WHEN lineage_count>0 THEN 1 ELSE 0 END) with_lineage,
                   AVG(readiness_score) average_readiness,
                   SUM(CASE WHEN scientific_status='release_eligible' THEN 1 ELSE 0 END) release_eligible
            FROM dataset_readiness
            """
        ).fetchone()
        payload["datasets"] = dict(row) if row else {}
        payload["open_dataset_issues"] = int(
            connection.execute(
                "SELECT COUNT(*) FROM dataset_validation_issues WHERE resolution_status='open'"
            ).fetchone()[0]
        )
        payload["dataset_aliases"] = int(
            connection.execute("SELECT COUNT(*) FROM dataset_aliases").fetchone()[0]
        )
    with managed_connect(runtime_database_path(project_root, "experiments.sqlite3")) as connection:
        connection.row_factory = sqlite3.Row
        payload["experiments"] = dict(
            connection.execute(
                """
                SELECT COUNT(*) experiments,
                       SUM(CASE WHEN synthetic_demo=1 THEN 1 ELSE 0 END) synthetic,
                       (SELECT COUNT(*) FROM experiment_dataset_bindings WHERE verified=1) verified_bindings,
                       (SELECT COUNT(*) FROM experiment_artifacts WHERE status='available') artifacts,
                       (SELECT COUNT(*) FROM experiment_validation_requirements WHERE status='blocked') blocked_requirements
                FROM experiments
                """
            ).fetchone()
        )
    with managed_connect(runtime_database_path(project_root, "internet_downloads.sqlite3")) as connection:
        connection.row_factory = sqlite3.Row
        payload["sources"] = dict(
            connection.execute(
                """
                SELECT COUNT(*) sources,
                       SUM(CASE WHEN local_status IN ('ready','downloaded','imported','imported_reference') THEN 1 ELSE 0 END) local_ready,
                       SUM(CASE WHEN local_status IN ('connector_ready','profile_only') THEN 1 ELSE 0 END) connector_only,
                       COALESCE(SUM(records_available),0) records_available
                FROM scientific_source_catalog
                """
            ).fetchone()
        )
    with managed_connect(runtime_database_path(project_root, "projects.sqlite3")) as connection:
        connection.row_factory = sqlite3.Row
        payload["projects"] = dict(
            connection.execute(
                """
                SELECT COUNT(*) projects,
                       SUM(CASE WHEN dataset_sha256 IS NOT NULL AND dataset_sha256!='' THEN 1 ELSE 0 END) with_dataset,
                       SUM(CASE WHEN model_filename IS NOT NULL AND model_filename!='' THEN 1 ELSE 0 END) with_model,
                       (SELECT COUNT(*) FROM project_resources) resource_links
                FROM projects
                """
            ).fetchone()
        )
    with managed_connect(runtime_database_path(project_root, "feature_cache.sqlite3")) as connection:
        connection.row_factory = sqlite3.Row
        payload["feature_cache"] = dict(
            connection.execute(
                """
                SELECT COUNT(*) entries,
                       SUM(CASE WHEN validation_status='valid' THEN 1 ELSE 0 END) valid_entries,
                       COUNT(DISTINCT schema_version) schema_versions,
                       COUNT(DISTINCT feature_kind) feature_kinds
                FROM feature_cache
                """
            ).fetchone()
        )
    return payload


def provider_readiness_rows(root: str | Path) -> list[dict[str, Any]]:
    project_root = Path(root).resolve()
    initialize_readiness_schema(project_root)
    with managed_connect(runtime_database_path(project_root, "internet_downloads.sqlite3")) as connection:
        connection.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in connection.execute(
                """
            SELECT c.*,
                   (SELECT COUNT(*) FROM internet_downloads d WHERE lower(d.provider)=lower(c.provider)) download_records,
                   (SELECT COUNT(*) FROM source_sync_events e WHERE e.source_key=c.source_key) sync_events,
                   (SELECT MAX(created_at_utc) FROM source_sync_events e WHERE e.source_key=c.source_key) last_sync_event
            FROM scientific_source_catalog c
            ORDER BY c.local_status,c.provider
            """
            )
        ]
