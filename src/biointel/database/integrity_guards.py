from __future__ import annotations

from biointel.runtime_paths import runtime_database_directory

import sqlite3
from biointel.database.core import managed_connect
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class GuardResult:
    database: str
    triggers_created: int
    trigger_count: int
    foreign_key_findings: int
    integrity: str


def _connect(path: Path) -> sqlite3.Connection:
    connection = managed_connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _install(connection: sqlite3.Connection, statements: Iterable[str]) -> int:
    before = int(
        connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'biointel_guard_%'"
        ).fetchone()[0]
    )
    for statement in statements:
        connection.executescript(statement)
    after = int(
        connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'biointel_guard_%'"
        ).fetchone()[0]
    )
    return max(after - before, 0)


def _dataset_guards(tables: set[str]) -> list[str]:
    statements: list[str] = []
    children = [
        "dataset_files",
        "dataset_columns",
        "dataset_samples",
        "dataset_qc_metrics",
        "dataset_provenance",
        "dataset_readiness",
        "dataset_validation_issues",
    ]
    for table in children:
        if table not in tables:
            continue
        statements.append(
            f"""
            CREATE TRIGGER IF NOT EXISTS biointel_guard_{table}_insert
            BEFORE INSERT ON {table}
            FOR EACH ROW BEGIN
              SELECT CASE WHEN NOT EXISTS(
                SELECT 1 FROM datasets WHERE dataset_sha256=NEW.dataset_sha256
              ) THEN RAISE(ABORT, 'Unknown dataset_sha256 in {table}') END;
            END;
            CREATE TRIGGER IF NOT EXISTS biointel_guard_{table}_update
            BEFORE UPDATE OF dataset_sha256 ON {table}
            FOR EACH ROW BEGIN
              SELECT CASE WHEN NOT EXISTS(
                SELECT 1 FROM datasets WHERE dataset_sha256=NEW.dataset_sha256
              ) THEN RAISE(ABORT, 'Unknown dataset_sha256 in {table}') END;
            END;
            """
        )
    if "dataset_links" in tables:
        statements.append(
            """
            CREATE TRIGGER IF NOT EXISTS biointel_guard_dataset_links_insert
            BEFORE INSERT ON dataset_links
            FOR EACH ROW BEGIN
              SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM datasets WHERE dataset_sha256=NEW.source_dataset_sha256)
                THEN RAISE(ABORT, 'Unknown source dataset in dataset_links') END;
              SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM datasets WHERE dataset_sha256=NEW.target_dataset_sha256)
                THEN RAISE(ABORT, 'Unknown target dataset in dataset_links') END;
            END;
            """
        )
    if "dataset_aliases" in tables:
        statements.append(
            """
            CREATE TRIGGER IF NOT EXISTS biointel_guard_dataset_aliases_insert
            BEFORE INSERT ON dataset_aliases
            FOR EACH ROW BEGIN
              SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM datasets WHERE dataset_sha256=NEW.canonical_dataset_sha256)
                THEN RAISE(ABORT, 'Unknown canonical dataset in dataset_aliases') END;
            END;
            """
        )
    if "datasets" in tables:
        checks = [table for table in children if table in tables]
        body = "\n".join(
            f"SELECT CASE WHEN EXISTS(SELECT 1 FROM {table} WHERE dataset_sha256=OLD.dataset_sha256) THEN RAISE(ABORT, 'Dataset has dependent {table} records') END;"
            for table in checks
        )
        statements.append(
            f"""
            CREATE TRIGGER IF NOT EXISTS biointel_guard_datasets_delete
            BEFORE DELETE ON datasets
            FOR EACH ROW BEGIN
              {body}
            END;
            """
        )
    return statements


def _experiment_guards(tables: set[str]) -> list[str]:
    statements: list[str] = []
    children = [
        "experiment_artifacts",
        "experiment_dataset_bindings",
        "experiment_events",
        "experiment_folds",
        "experiment_runtime_metrics",
        "experiment_validation_requirements",
        "hyperparameter_trials",
    ]
    for table in children:
        if table not in tables:
            continue
        statements.append(
            f"""
            CREATE TRIGGER IF NOT EXISTS biointel_guard_{table}_insert
            BEFORE INSERT ON {table}
            FOR EACH ROW BEGIN
              SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM experiments WHERE experiment_id=NEW.experiment_id)
                THEN RAISE(ABORT, 'Unknown experiment_id in {table}') END;
            END;
            CREATE TRIGGER IF NOT EXISTS biointel_guard_{table}_update
            BEFORE UPDATE OF experiment_id ON {table}
            FOR EACH ROW BEGIN
              SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM experiments WHERE experiment_id=NEW.experiment_id)
                THEN RAISE(ABORT, 'Unknown experiment_id in {table}') END;
            END;
            """
        )
    return statements


def _project_guards(tables: set[str]) -> list[str]:
    statements: list[str] = []
    for table in ["project_decisions", "project_events", "project_gates", "project_milestones", "project_resources"]:
        if table not in tables:
            continue
        statements.append(
            f"""
            CREATE TRIGGER IF NOT EXISTS biointel_guard_{table}_insert
            BEFORE INSERT ON {table}
            FOR EACH ROW BEGIN
              SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM projects WHERE project_id=NEW.project_id)
                THEN RAISE(ABORT, 'Unknown project_id in {table}') END;
            END;
            CREATE TRIGGER IF NOT EXISTS biointel_guard_{table}_update
            BEFORE UPDATE OF project_id ON {table}
            FOR EACH ROW BEGIN
              SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM projects WHERE project_id=NEW.project_id)
                THEN RAISE(ABORT, 'Unknown project_id in {table}') END;
            END;
            """
        )
    return statements


def _evidence_guards(tables: set[str]) -> list[str]:
    statements: list[str] = []
    for table in ["evidence_assay_context", "evidence_replicates", "evidence_reviews"]:
        if table not in tables:
            continue
        statements.append(
            f"""
            CREATE TRIGGER IF NOT EXISTS biointel_guard_{table}_insert
            BEFORE INSERT ON {table}
            FOR EACH ROW BEGIN
              SELECT CASE WHEN NOT EXISTS(
                SELECT 1 FROM dataset_evidence_links
                WHERE dataset_sha256=NEW.dataset_sha256 AND evidence_key=NEW.evidence_key
              ) THEN RAISE(ABORT, 'Unknown evidence key/dataset pair in {table}') END;
            END;
            CREATE TRIGGER IF NOT EXISTS biointel_guard_{table}_update
            BEFORE UPDATE OF dataset_sha256, evidence_key ON {table}
            FOR EACH ROW BEGIN
              SELECT CASE WHEN NOT EXISTS(
                SELECT 1 FROM dataset_evidence_links
                WHERE dataset_sha256=NEW.dataset_sha256 AND evidence_key=NEW.evidence_key
              ) THEN RAISE(ABORT, 'Unknown evidence key/dataset pair in {table}') END;
            END;
            """
        )
    return statements


def _document_guards(tables: set[str]) -> list[str]:
    if "document_registry_versions" not in tables or "document_extraction_runs" not in tables:
        return []
    return [
        """
        CREATE TRIGGER IF NOT EXISTS biointel_guard_document_registry_versions_insert
        BEFORE INSERT ON document_registry_versions
        FOR EACH ROW BEGIN
          SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM document_extraction_runs WHERE run_id=NEW.run_id)
            THEN RAISE(ABORT, 'Unknown run_id in document_registry_versions') END;
        END;
        """
    ]


def install_integrity_guards(project_root: str | Path) -> dict[str, GuardResult]:
    root = Path(project_root).resolve()
    reports = runtime_database_directory(root)
    scripts = {
        "datasets.sqlite3": _dataset_guards,
        "experiments.sqlite3": _experiment_guards,
        "projects.sqlite3": _project_guards,
        "evidence.sqlite3": _evidence_guards,
        "document_history.sqlite3": _document_guards,
    }
    results: dict[str, GuardResult] = {}
    for filename, builder in scripts.items():
        path = reports / filename
        if not path.is_file():
            continue
        with _connect(path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS database_migration_log(
                    migration_id TEXT PRIMARY KEY,
                    applied_at_utc TEXT NOT NULL,
                    description TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            created = _install(connection, builder(_tables(connection)))
            connection.execute(
                """
                INSERT OR REPLACE INTO database_migration_log(
                    migration_id, applied_at_utc, description, metadata_json
                ) VALUES ('step33-native-integrity-guards', ?, ?, '{}')
                """,
                (_utc_now(), "Application-level parent integrity guards for legacy tables"),
            )
            foreign_key_findings = len(connection.execute("PRAGMA foreign_key_check").fetchall())
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            trigger_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'biointel_guard_%'"
                ).fetchone()[0]
            )
        results[filename] = GuardResult(filename, created, trigger_count, foreign_key_findings, integrity)
    return results
