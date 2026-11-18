from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from biointel.database.core import connect, database_health, transaction, utc_now
from biointel.documents.models import DocumentExtraction
from biointel.documents.security import sha256_bytes

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS document_extraction_runs (
    run_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    completed_at_utc TEXT,
    page_count INTEGER NOT NULL DEFAULT 0,
    sheet_count INTEGER NOT NULL DEFAULT 0,
    paragraph_count INTEGER NOT NULL DEFAULT 0,
    image_count INTEGER NOT NULL DEFAULT 0,
    table_count INTEGER NOT NULL DEFAULT 0,
    row_count INTEGER NOT NULL DEFAULT 0,
    character_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    error_message TEXT NOT NULL DEFAULT '',
    output_directory TEXT,
    source_saved_path TEXT,
    options_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    parent_run_id TEXT,
    duplicate_of_run_id TEXT,
    engine_version TEXT NOT NULL DEFAULT '2.7.0',
    tags_json TEXT NOT NULL DEFAULT '[]',
    project_code TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    deleted_at_utc TEXT,
    content_indexed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_document_runs_time ON document_extraction_runs(started_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_document_runs_type_status ON document_extraction_runs(file_type, status);
CREATE INDEX IF NOT EXISTS idx_document_runs_sha256 ON document_extraction_runs(source_sha256);
CREATE INDEX IF NOT EXISTS idx_document_runs_name ON document_extraction_runs(source_name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS document_extraction_outputs (
    output_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    format TEXT NOT NULL,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    verified_at_utc TEXT,
    integrity_status TEXT NOT NULL DEFAULT 'unknown',
    FOREIGN KEY(run_id) REFERENCES document_extraction_runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_document_outputs_run ON document_extraction_outputs(run_id, format);

CREATE TABLE IF NOT EXISTS document_extraction_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES document_extraction_runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_document_events_run_time ON document_extraction_events(run_id, created_at_utc);

CREATE TABLE IF NOT EXISTS document_content (
    content_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    content_type TEXT NOT NULL,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    text TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES document_extraction_runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_document_content_run ON document_content(run_id, content_type);

CREATE TABLE IF NOT EXISTS document_entities (
    entity_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    text TEXT NOT NULL,
    normalized TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES document_extraction_runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_document_entities_run_type ON document_entities(run_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_document_entities_normalized ON document_entities(normalized COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS document_ocr_corrections (
    correction_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    region_id TEXT NOT NULL,
    original_text TEXT NOT NULL,
    corrected_text TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    comment TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES document_extraction_runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ocr_corrections_run ON document_ocr_corrections(run_id, created_at_utc DESC);
"""


@dataclass(frozen=True)
class DocumentRun:
    run_id: str
    source_name: str
    file_type: str
    mime_type: str
    source_sha256: str
    source_size_bytes: int
    status: str
    started_at_utc: str
    completed_at_utc: str | None
    page_count: int
    sheet_count: int
    paragraph_count: int
    image_count: int
    table_count: int
    row_count: int
    character_count: int
    warning_count: int
    warnings: list[str]
    error_message: str
    output_directory: str | None
    source_saved_path: str | None
    options: dict[str, Any]
    metadata: dict[str, Any]
    parent_run_id: str | None = None
    duplicate_of_run_id: str | None = None
    engine_version: str = "2.7.0"
    tags: list[str] = field(default_factory=list)
    project_code: str = ""
    notes: str = ""
    deleted_at_utc: str | None = None
    content_indexed: bool = False


@dataclass(frozen=True)
class DocumentOutput:
    output_id: str
    run_id: str
    format: str
    filename: str
    path: str
    size_bytes: int
    sha256: str
    created_at_utc: str
    verified_at_utc: str | None = None
    integrity_status: str = "unknown"


def _columns(connection: Any, table: str) -> set[str]:
    return {str(row["name"]) for row in connection.execute(f'PRAGMA table_info("{table}")')}


def _ensure_column(connection: Any, table: str, name: str, definition: str) -> None:
    if name not in _columns(connection, table):
        connection.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}')


def initialize_document_history(path: str | Path) -> Path:
    database = Path(path).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    with connect(database) as connection:
        connection.executescript(SCHEMA)
        for name, definition in (
            ("parent_run_id", "TEXT"),
            ("duplicate_of_run_id", "TEXT"),
            ("engine_version", "TEXT NOT NULL DEFAULT '2.7.0'"),
            ("tags_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("project_code", "TEXT NOT NULL DEFAULT ''"),
            ("notes", "TEXT NOT NULL DEFAULT ''"),
            ("deleted_at_utc", "TEXT"),
            ("content_indexed", "INTEGER NOT NULL DEFAULT 0"),
        ):
            _ensure_column(connection, "document_extraction_runs", name, definition)
        for name, definition in (
            ("verified_at_utc", "TEXT"),
            ("integrity_status", "TEXT NOT NULL DEFAULT 'unknown'"),
        ):
            _ensure_column(connection, "document_extraction_outputs", name, definition)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_document_runs_project "
            "ON document_extraction_runs(project_code, started_at_utc DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_document_runs_deleted "
            "ON document_extraction_runs(deleted_at_utc, started_at_utc DESC)"
        )
        try:
            connection.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS document_content_fts USING fts5("
                "content_id UNINDEXED, run_id UNINDEXED, source_name, name, source, text, "
                "tokenize='unicode61 remove_diacritics 2')"
            )
        except Exception:
            # FTS5 is present in supported Python builds; LIKE fallback remains available.
            pass
        connection.commit()
    return database


def add_event(history_path: str | Path, run_id: str, event_type: str, message: str) -> None:
    path = initialize_document_history(history_path)
    with transaction(path) as connection:
        connection.execute(
            "INSERT INTO document_extraction_events VALUES (?, ?, ?, ?, ?)",
            (uuid4().hex, run_id, event_type, message[:10_000], utc_now()),
        )


def start_run(
    history_path: str | Path,
    *,
    source_name: str,
    file_type: str,
    mime_type: str,
    source_sha256: str,
    source_size_bytes: int,
    options: dict[str, Any] | None = None,
    parent_run_id: str | None = None,
    duplicate_of_run_id: str | None = None,
    tags: list[str] | None = None,
    project_code: str = "",
    notes: str = "",
    engine_version: str = "2.7.0",
) -> str:
    run_id = uuid4().hex
    path = initialize_document_history(history_path)
    now = utc_now()
    with transaction(path) as connection:
        connection.execute(
            """
            INSERT INTO document_extraction_runs (
                run_id, source_name, file_type, mime_type, source_sha256,
                source_size_bytes, status, started_at_utc, options_json,
                parent_run_id, duplicate_of_run_id, engine_version, tags_json,
                project_code, notes
            ) VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                source_name,
                file_type,
                mime_type,
                source_sha256,
                int(source_size_bytes),
                now,
                json.dumps(options or {}, sort_keys=True, default=str),
                parent_run_id,
                duplicate_of_run_id,
                engine_version,
                json.dumps(sorted(set(tags or [])), ensure_ascii=False),
                project_code.strip(),
                notes.strip(),
            ),
        )
        connection.execute(
            "INSERT INTO document_extraction_events VALUES (?, ?, ?, ?, ?)",
            (uuid4().hex, run_id, "started", "Document extraction started.", now),
        )
    return run_id


def complete_run(
    history_path: str | Path,
    run_id: str,
    *,
    summary: dict[str, Any],
    warnings: list[str],
    output_directory: str,
    source_saved_path: str | None,
    metadata: dict[str, Any],
) -> None:
    path = initialize_document_history(history_path)
    now = utc_now()
    with transaction(path) as connection:
        connection.execute(
            """
            UPDATE document_extraction_runs
            SET status='completed', completed_at_utc=?, page_count=?, sheet_count=?,
                paragraph_count=?, image_count=?, table_count=?, row_count=?,
                character_count=?, warning_count=?, warnings_json=?, output_directory=?,
                source_saved_path=?, metadata_json=?
            WHERE run_id=?
            """,
            (
                now,
                int(summary.get("page_count", 0)),
                int(summary.get("sheet_count", 0)),
                int(summary.get("paragraph_count", 0)),
                int(summary.get("image_count", 0)),
                int(summary.get("table_count", 0)),
                int(summary.get("row_count", 0)),
                int(summary.get("character_count", 0)),
                len(warnings),
                json.dumps(warnings, ensure_ascii=False),
                output_directory,
                source_saved_path,
                json.dumps(metadata, sort_keys=True, default=str),
                run_id,
            ),
        )
        connection.execute(
            "INSERT INTO document_extraction_events VALUES (?, ?, ?, ?, ?)",
            (uuid4().hex, run_id, "completed", "Document extraction completed.", now),
        )


def fail_run(history_path: str | Path, run_id: str, error_message: str) -> None:
    path = initialize_document_history(history_path)
    now = utc_now()
    with transaction(path) as connection:
        connection.execute(
            "UPDATE document_extraction_runs SET status='failed', completed_at_utc=?, "
            "error_message=? WHERE run_id=?",
            (now, error_message[:10_000], run_id),
        )
        connection.execute(
            "INSERT INTO document_extraction_events VALUES (?, ?, ?, ?, ?)",
            (uuid4().hex, run_id, "failed", error_message[:10_000], now),
        )


def add_output(history_path: str | Path, output: DocumentOutput) -> None:
    path = initialize_document_history(history_path)
    with transaction(path) as connection:
        connection.execute(
            """
            INSERT INTO document_extraction_outputs (
                output_id, run_id, format, filename, path, size_bytes, sha256,
                created_at_utc, verified_at_utc, integrity_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                output.output_id,
                output.run_id,
                output.format,
                output.filename,
                output.path,
                output.size_bytes,
                output.sha256,
                output.created_at_utc,
                output.verified_at_utc,
                output.integrity_status,
            ),
        )


def index_extraction(history_path: str | Path, run_id: str, extraction: DocumentExtraction) -> None:
    path = initialize_document_history(history_path)
    now = utc_now()
    content_rows: list[tuple[Any, ...]] = []
    for section in extraction.sections or ():
        content_rows.append(
            (
                uuid4().hex,
                run_id,
                "section",
                section.name,
                section.source,
                section.text,
                json.dumps(section.metadata, sort_keys=True, default=str),
                now,
            )
        )
    if not content_rows and extraction.text:
        content_rows.append((uuid4().hex, run_id, "document", "Document", "document", extraction.text, "{}", now))
    for table in extraction.tables:
        header = " | ".join(table.columns)
        rows = "\n".join(
            " | ".join("" if value is None else str(value) for value in row)
            for row in table.rows[:10_000]
        )
        content_rows.append(
            (
                uuid4().hex,
                run_id,
                "table",
                table.name,
                table.source,
                f"{header}\n{rows}",
                json.dumps({"confidence": table.confidence, **table.metadata}, sort_keys=True, default=str),
                now,
            )
        )
    entity_rows = [
        (
            uuid4().hex,
            run_id,
            entity.entity_type,
            entity.text,
            entity.normalized,
            entity.source,
            float(entity.confidence),
            json.dumps(entity.metadata, sort_keys=True, default=str),
            now,
        )
        for entity in extraction.entities
    ]
    with transaction(path) as connection:
        connection.execute("DELETE FROM document_content WHERE run_id=?", (run_id,))
        connection.execute("DELETE FROM document_entities WHERE run_id=?", (run_id,))
        try:
            connection.execute("DELETE FROM document_content_fts WHERE run_id=?", (run_id,))
        except Exception:
            pass
        connection.executemany(
            "INSERT INTO document_content VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            content_rows,
        )
        if entity_rows:
            connection.executemany(
                "INSERT INTO document_entities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                entity_rows,
            )
        source_name = extraction.source_name
        try:
            connection.executemany(
                "INSERT INTO document_content_fts(content_id,run_id,source_name,name,source,text) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (content_id, run_id, source_name, name, source, text)
                    for content_id, _, _, name, source, text, _, _ in content_rows
                ],
            )
        except Exception:
            pass
        connection.execute(
            "UPDATE document_extraction_runs SET content_indexed=1 WHERE run_id=?",
            (run_id,),
        )


def _run_from_row(row: Any) -> DocumentRun:
    return DocumentRun(
        run_id=row["run_id"],
        source_name=row["source_name"],
        file_type=row["file_type"],
        mime_type=row["mime_type"],
        source_sha256=row["source_sha256"],
        source_size_bytes=int(row["source_size_bytes"]),
        status=row["status"],
        started_at_utc=row["started_at_utc"],
        completed_at_utc=row["completed_at_utc"],
        page_count=int(row["page_count"]),
        sheet_count=int(row["sheet_count"]),
        paragraph_count=int(row["paragraph_count"]),
        image_count=int(row["image_count"]),
        table_count=int(row["table_count"]),
        row_count=int(row["row_count"]),
        character_count=int(row["character_count"]),
        warning_count=int(row["warning_count"]),
        warnings=json.loads(row["warnings_json"]),
        error_message=row["error_message"],
        output_directory=row["output_directory"],
        source_saved_path=row["source_saved_path"],
        options=json.loads(row["options_json"]),
        metadata=json.loads(row["metadata_json"]),
        parent_run_id=row["parent_run_id"],
        duplicate_of_run_id=row["duplicate_of_run_id"],
        engine_version=row["engine_version"] or "2.7.0",
        tags=json.loads(row["tags_json"] or "[]"),
        project_code=row["project_code"] or "",
        notes=row["notes"] or "",
        deleted_at_utc=row["deleted_at_utc"],
        content_indexed=bool(row["content_indexed"]),
    )


def list_runs(
    history_path: str | Path,
    *,
    query: str = "",
    file_type: str | None = None,
    status: str | None = None,
    project_code: str | None = None,
    tag: str | None = None,
    include_deleted: bool = False,
    limit: int = 500,
) -> list[DocumentRun]:
    path = initialize_document_history(history_path)
    clauses: list[str] = []
    parameters: list[Any] = []
    if not include_deleted:
        clauses.append("deleted_at_utc IS NULL")
    if query.strip():
        clauses.append("(source_name LIKE ? OR source_sha256 LIKE ? OR notes LIKE ?)")
        value = f"%{query.strip()}%"
        parameters.extend([value, value, value])
    if file_type and file_type != "all":
        clauses.append("file_type=?")
        parameters.append(file_type)
    if status and status != "all":
        clauses.append("status=?")
        parameters.append(status)
    if project_code:
        clauses.append("project_code=?")
        parameters.append(project_code)
    if tag:
        clauses.append("tags_json LIKE ?")
        parameters.append(f'%"{tag}"%')
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    parameters.append(max(1, min(int(limit), 5_000)))
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            f"SELECT * FROM document_extraction_runs{where} ORDER BY started_at_utc DESC LIMIT ?",
            tuple(parameters),
        ).fetchall()
    return [_run_from_row(row) for row in rows]


def get_run(history_path: str | Path, run_id: str) -> DocumentRun:
    path = initialize_document_history(history_path)
    with connect(path, read_only=True) as connection:
        row = connection.execute(
            "SELECT * FROM document_extraction_runs WHERE run_id=?", (run_id,)
        ).fetchone()
    if row is None:
        raise KeyError(run_id)
    return _run_from_row(row)


def find_duplicate_run(
    history_path: str | Path,
    source_sha256: str,
    *,
    options: dict[str, Any] | None = None,
) -> DocumentRun | None:
    path = initialize_document_history(history_path)
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            "SELECT * FROM document_extraction_runs WHERE source_sha256=? AND status='completed' "
            "AND deleted_at_utc IS NULL ORDER BY completed_at_utc DESC",
            (source_sha256,),
        ).fetchall()
    expected = options or {}
    for row in rows:
        run = _run_from_row(row)
        comparable = {key: run.options.get(key) for key in expected}
        if comparable == expected:
            return run
    return None


def list_outputs(history_path: str | Path, run_id: str) -> list[DocumentOutput]:
    path = initialize_document_history(history_path)
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            "SELECT * FROM document_extraction_outputs WHERE run_id=? ORDER BY format", (run_id,)
        ).fetchall()
    return [DocumentOutput(**dict(row)) for row in rows]


def list_events(history_path: str | Path, run_id: str) -> list[dict[str, Any]]:
    path = initialize_document_history(history_path)
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            "SELECT * FROM document_extraction_events WHERE run_id=? ORDER BY created_at_utc",
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_run_organization(
    history_path: str | Path,
    run_id: str,
    *,
    tags: list[str] | None = None,
    project_code: str | None = None,
    notes: str | None = None,
) -> None:
    path = initialize_document_history(history_path)
    run = get_run(path, run_id)
    with transaction(path) as connection:
        connection.execute(
            "UPDATE document_extraction_runs SET tags_json=?, project_code=?, notes=? WHERE run_id=?",
            (
                json.dumps(sorted(set(tags if tags is not None else run.tags)), ensure_ascii=False),
                project_code if project_code is not None else run.project_code,
                notes if notes is not None else run.notes,
                run_id,
            ),
        )
        connection.execute(
            "INSERT INTO document_extraction_events VALUES (?, ?, ?, ?, ?)",
            (uuid4().hex, run_id, "organized", "Tags/project/notes updated.", utc_now()),
        )


def soft_delete_run(history_path: str | Path, run_id: str) -> None:
    path = initialize_document_history(history_path)
    with transaction(path) as connection:
        connection.execute(
            "UPDATE document_extraction_runs SET deleted_at_utc=? WHERE run_id=?",
            (utc_now(), run_id),
        )
        connection.execute(
            "INSERT INTO document_extraction_events VALUES (?, ?, ?, ?, ?)",
            (uuid4().hex, run_id, "trashed", "Extraction moved to trash.", utc_now()),
        )


def restore_run(history_path: str | Path, run_id: str) -> None:
    path = initialize_document_history(history_path)
    with transaction(path) as connection:
        connection.execute(
            "UPDATE document_extraction_runs SET deleted_at_utc=NULL WHERE run_id=?", (run_id,)
        )
        connection.execute(
            "INSERT INTO document_extraction_events VALUES (?, ?, ?, ?, ?)",
            (uuid4().hex, run_id, "restored", "Extraction restored from trash.", utc_now()),
        )


def delete_run(history_path: str | Path, run_id: str, *, delete_files: bool = True) -> None:
    path = initialize_document_history(history_path)
    run = get_run(path, run_id)
    with transaction(path) as connection:
        try:
            connection.execute("DELETE FROM document_content_fts WHERE run_id=?", (run_id,))
        except Exception:
            pass
        connection.execute("DELETE FROM document_extraction_runs WHERE run_id=?", (run_id,))
    if delete_files and run.output_directory:
        output_directory = _resolve_stored_path(path, run.output_directory).resolve()
        if output_directory.is_dir() and output_directory.name == run_id:
            shutil.rmtree(output_directory, ignore_errors=True)


def purge_deleted(history_path: str | Path, *, older_than_days: int = 30) -> list[str]:
    threshold = datetime.now(UTC) - timedelta(days=max(0, int(older_than_days)))
    path = initialize_document_history(history_path)
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            "SELECT run_id FROM document_extraction_runs WHERE deleted_at_utc IS NOT NULL "
            "AND deleted_at_utc<=?",
            (threshold.isoformat(timespec="seconds"),),
        ).fetchall()
    run_ids = [str(row["run_id"]) for row in rows]
    for run_id in run_ids:
        delete_run(path, run_id, delete_files=True)
    return run_ids


def apply_retention_policy(
    history_path: str | Path,
    *,
    completed_days: int | None = None,
    failed_days: int | None = 90,
) -> list[str]:
    path = initialize_document_history(history_path)
    conditions, parameters = [], []
    now = datetime.now(UTC)
    if completed_days is not None:
        conditions.append("(status='completed' AND started_at_utc<=?)")
        parameters.append((now - timedelta(days=max(0, completed_days))).isoformat(timespec="seconds"))
    if failed_days is not None:
        conditions.append("(status='failed' AND started_at_utc<=?)")
        parameters.append((now - timedelta(days=max(0, failed_days))).isoformat(timespec="seconds"))
    if not conditions:
        return []
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            "SELECT run_id FROM document_extraction_runs WHERE deleted_at_utc IS NULL AND ("
            + " OR ".join(conditions)
            + ")",
            tuple(parameters),
        ).fetchall()
    run_ids = [str(row["run_id"]) for row in rows]
    for run_id in run_ids:
        soft_delete_run(path, run_id)
    return run_ids


def history_summary(history_path: str | Path) -> dict[str, Any]:
    path = initialize_document_history(history_path)
    with connect(path, read_only=True) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS total_runs,
                   SUM(CASE WHEN status='completed' AND deleted_at_utc IS NULL THEN 1 ELSE 0 END) AS completed_runs,
                   SUM(CASE WHEN status='failed' AND deleted_at_utc IS NULL THEN 1 ELSE 0 END) AS failed_runs,
                   SUM(CASE WHEN deleted_at_utc IS NOT NULL THEN 1 ELSE 0 END) AS trashed_runs,
                   COALESCE(SUM(CASE WHEN deleted_at_utc IS NULL THEN row_count ELSE 0 END), 0) AS total_rows,
                   COALESCE(SUM(CASE WHEN deleted_at_utc IS NULL THEN table_count ELSE 0 END), 0) AS total_tables,
                   COALESCE(SUM(CASE WHEN deleted_at_utc IS NULL THEN source_size_bytes ELSE 0 END), 0) AS source_bytes
            FROM document_extraction_runs
            """
        ).fetchone()
        output_row = connection.execute(
            "SELECT COUNT(*) AS output_count, COALESCE(SUM(size_bytes), 0) AS output_bytes "
            "FROM document_extraction_outputs"
        ).fetchone()
        content_count = int(connection.execute("SELECT COUNT(*) FROM document_content").fetchone()[0])
        entity_count = int(connection.execute("SELECT COUNT(*) FROM document_entities").fetchone()[0])
    return {
        "database": asdict(database_health(path, name="Document Extraction History")),
        "total_runs": int(row["total_runs"] or 0),
        "completed_runs": int(row["completed_runs"] or 0),
        "failed_runs": int(row["failed_runs"] or 0),
        "trashed_runs": int(row["trashed_runs"] or 0),
        "total_rows": int(row["total_rows"] or 0),
        "total_tables": int(row["total_tables"] or 0),
        "source_bytes": int(row["source_bytes"] or 0),
        "output_count": int(output_row["output_count"] or 0),
        "output_bytes": int(output_row["output_bytes"] or 0),
        "indexed_content_records": content_count,
        "scientific_entities": entity_count,
    }


def get_output(history_path: str | Path, output_id: str) -> DocumentOutput:
    path = initialize_document_history(history_path)
    with connect(path, read_only=True) as connection:
        row = connection.execute(
            "SELECT * FROM document_extraction_outputs WHERE output_id=?", (output_id,)
        ).fetchone()
    if row is None:
        raise KeyError(output_id)
    return DocumentOutput(**dict(row))


def _resolve_stored_path(history_path: str | Path, stored_path: str | Path) -> Path:
    candidate = Path(stored_path)
    if candidate.is_absolute():
        return candidate
    return Path(history_path).resolve().parents[1] / candidate


def verify_output(history_path: str | Path, output_id: str) -> dict[str, Any]:
    path = initialize_document_history(history_path)
    output = get_output(path, output_id)
    file_path = _resolve_stored_path(path, output.path)
    exists = file_path.is_file()
    actual_size = file_path.stat().st_size if exists else 0
    actual_sha = sha256_bytes(file_path.read_bytes()) if exists else None
    valid = bool(exists and actual_size == output.size_bytes and actual_sha == output.sha256)
    status = "ok" if valid else "missing" if not exists else "corrupt"
    now = utc_now()
    with transaction(path) as connection:
        connection.execute(
            "UPDATE document_extraction_outputs SET verified_at_utc=?, integrity_status=? "
            "WHERE output_id=?",
            (now, status, output_id),
        )
    return {
        "output_id": output_id,
        "exists": exists,
        "valid": valid,
        "status": status,
        "expected_size": output.size_bytes,
        "actual_size": actual_size,
        "expected_sha256": output.sha256,
        "actual_sha256": actual_sha,
        "verified_at_utc": now,
    }


def search_content(
    history_path: str | Path,
    query: str,
    *,
    entity_type: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    path = initialize_document_history(history_path)
    needle = query.strip()
    if not needle:
        return []
    tokens = re.findall(r"[A-Za-z0-9_.+-]+", needle)
    fts_query = " OR ".join(f'"{token}"' for token in tokens if token) or needle
    maximum = max(1, min(int(limit), 1_000))
    with connect(path, read_only=True) as connection:
        try:
            rows = connection.execute(
                """
                SELECT f.run_id, f.source_name, f.name, f.source,
                       snippet(document_content_fts, 5, '[', ']', ' … ', 24) AS snippet,
                       bm25(document_content_fts) AS score
                FROM document_content_fts f
                JOIN document_extraction_runs r ON r.run_id=f.run_id
                WHERE document_content_fts MATCH ? AND r.deleted_at_utc IS NULL
                ORDER BY score LIMIT ?
                """,
                (fts_query, maximum),
            ).fetchall()
            results = [dict(row) for row in rows]
        except Exception:
            value = f"%{needle}%"
            rows = connection.execute(
                """
                SELECT c.run_id, r.source_name, c.name, c.source,
                       substr(c.text, 1, 500) AS snippet, 0.0 AS score
                FROM document_content c
                JOIN document_extraction_runs r ON r.run_id=c.run_id
                WHERE c.text LIKE ? AND r.deleted_at_utc IS NULL
                ORDER BY r.started_at_utc DESC LIMIT ?
                """,
                (value, maximum),
            ).fetchall()
            results = [dict(row) for row in rows]
        if entity_type:
            entity_rows = connection.execute(
                """
                SELECT e.run_id, r.source_name, e.entity_type, e.text, e.normalized,
                       e.source, e.confidence
                FROM document_entities e
                JOIN document_extraction_runs r ON r.run_id=e.run_id
                WHERE e.entity_type=? AND (e.text LIKE ? OR e.normalized LIKE ?)
                  AND r.deleted_at_utc IS NULL
                ORDER BY e.confidence DESC LIMIT ?
                """,
                (entity_type, f"%{needle}%", f"%{needle}%", maximum),
            ).fetchall()
            results.extend({**dict(row), "name": row["entity_type"], "snippet": row["text"], "score": -float(row["confidence"])} for row in entity_rows)
    return results[:maximum]


def list_entities(
    history_path: str | Path,
    *,
    run_id: str | None = None,
    entity_type: str | None = None,
    query: str = "",
    limit: int = 1_000,
) -> list[dict[str, Any]]:
    path = initialize_document_history(history_path)
    clauses, parameters = [], []
    if run_id:
        clauses.append("e.run_id=?")
        parameters.append(run_id)
    if entity_type and entity_type != "all":
        clauses.append("e.entity_type=?")
        parameters.append(entity_type)
    if query.strip():
        clauses.append("(e.text LIKE ? OR e.normalized LIKE ?)")
        parameters.extend([f"%{query.strip()}%", f"%{query.strip()}%"])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    parameters.append(max(1, min(int(limit), 10_000)))
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            "SELECT e.*, r.source_name FROM document_entities e JOIN document_extraction_runs r "
            f"ON r.run_id=e.run_id{where} ORDER BY e.confidence DESC LIMIT ?",
            tuple(parameters),
        ).fetchall()
    return [{**dict(row), "metadata": json.loads(row["metadata_json"])} for row in rows]


def record_ocr_correction(
    history_path: str | Path,
    *,
    run_id: str,
    region_id: str,
    original_text: str,
    corrected_text: str,
    reviewer: str,
    comment: str = "",
) -> str:
    if not reviewer.strip():
        raise ValueError("Reviewer is required.")
    correction_id = uuid4().hex
    path = initialize_document_history(history_path)
    with transaction(path) as connection:
        connection.execute(
            "INSERT INTO document_ocr_corrections VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                correction_id,
                run_id,
                region_id,
                original_text,
                corrected_text,
                reviewer.strip(),
                comment.strip(),
                utc_now(),
            ),
        )
        connection.execute(
            "INSERT INTO document_extraction_events VALUES (?, ?, ?, ?, ?)",
            (uuid4().hex, run_id, "ocr_corrected", f"OCR region {region_id} corrected.", utc_now()),
        )
    return correction_id


def list_ocr_corrections(history_path: str | Path, run_id: str) -> list[dict[str, Any]]:
    path = initialize_document_history(history_path)
    with connect(path, read_only=True) as connection:
        rows = connection.execute(
            "SELECT * FROM document_ocr_corrections WHERE run_id=? ORDER BY created_at_utc DESC",
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]
