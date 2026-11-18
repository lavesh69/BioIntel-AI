from __future__ import annotations

import json
import sqlite3
from biointel.database.core import managed_connect
from datetime import UTC, datetime
from pathlib import Path

from biointel.connected.models import ConnectionDiagnostic, QueryResult

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS connected_queries(
    query_id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    query_text TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    response_sha256 TEXT NOT NULL,
    cache_status TEXT NOT NULL,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    retrieved_at_utc TEXT NOT NULL,
    elapsed_ms REAL NOT NULL DEFAULT 0,
    request_id TEXT NOT NULL DEFAULT '',
    provider_version TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_connected_queries_provider_time
ON connected_queries(provider, retrieved_at_utc DESC);
CREATE TABLE IF NOT EXISTS connected_records(
    query_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    record_id TEXT NOT NULL,
    record_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_url TEXT NOT NULL,
    normalized_json TEXT NOT NULL,
    PRIMARY KEY(query_id, provider, record_id, record_type),
    FOREIGN KEY(query_id) REFERENCES connected_queries(query_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_connected_records_identity
ON connected_records(provider, record_id, record_type);
CREATE TABLE IF NOT EXISTS copilot_runs(
    run_id TEXT PRIMARY KEY,
    query_text TEXT NOT NULL,
    mode TEXT NOT NULL,
    model TEXT NOT NULL,
    provider_count INTEGER NOT NULL,
    tool_calls INTEGER NOT NULL,
    status TEXT NOT NULL,
    answer_sha256 TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    response_id TEXT NOT NULL DEFAULT '',
    request_id TEXT NOT NULL DEFAULT '',
    evidence_records INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS provider_health_checks(
    check_id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    available INTEGER NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    records INTEGER NOT NULL DEFAULT 0,
    cache_status TEXT NOT NULL DEFAULT 'none',
    http_status INTEGER,
    request_id TEXT NOT NULL DEFAULT '',
    error_type TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    checked_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_provider_health_provider_time
ON provider_health_checks(provider, check_id DESC);
"""


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column(connection: sqlite3.Connection, table: str, definition: str) -> None:
    name = definition.split()[0]
    if name not in _columns(connection, table):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def initialize_registry(path: str | Path) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with managed_connect(target) as connection:
        connection.executescript(SCHEMA)
        for definition in (
            "elapsed_ms REAL NOT NULL DEFAULT 0",
            "request_id TEXT NOT NULL DEFAULT ''",
            "provider_version TEXT NOT NULL DEFAULT ''",
        ):
            _add_column(connection, "connected_queries", definition)
        for definition in (
            "response_id TEXT NOT NULL DEFAULT ''",
            "request_id TEXT NOT NULL DEFAULT ''",
            "evidence_records INTEGER NOT NULL DEFAULT 0",
            "input_tokens INTEGER NOT NULL DEFAULT 0",
            "output_tokens INTEGER NOT NULL DEFAULT 0",
        ):
            _add_column(connection, "copilot_runs", definition)
        connection.commit()
    return target


def record_query(path: str | Path, result: QueryResult) -> int:
    target = initialize_registry(path)
    with managed_connect(target) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        cursor = connection.execute(
            """
            INSERT INTO connected_queries(
                provider, query_text, entity_type, record_count, source_url,
                response_sha256, cache_status, warnings_json, retrieved_at_utc,
                elapsed_ms, request_id, provider_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.provider,
                result.query,
                result.entity_type,
                len(result.records),
                result.source_url,
                result.sha256,
                result.cache_status,
                json.dumps(list(result.warnings), sort_keys=True),
                result.retrieved_at_utc,
                float(result.elapsed_ms),
                result.request_id,
                result.provider_version,
            ),
        )
        query_id = int(cursor.lastrowid)
        for record in result.records:
            connection.execute(
                """
                INSERT OR REPLACE INTO connected_records(
                    query_id, provider, record_id, record_type, title, summary,
                    source_url, normalized_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    query_id,
                    record.provider,
                    record.record_id,
                    record.record_type,
                    record.title,
                    record.summary,
                    record.source_url,
                    json.dumps(record.payload, sort_keys=True, default=str),
                ),
            )
        connection.commit()
    return query_id


def record_copilot_run(
    path: str | Path,
    *,
    run_id: str,
    query_text: str,
    mode: str,
    model: str,
    provider_count: int,
    tool_calls: int,
    status: str,
    answer_sha256: str,
    error: str = "",
    response_id: str = "",
    request_id: str = "",
    evidence_records: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    target = initialize_registry(path)
    with managed_connect(target) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO copilot_runs(
                run_id, query_text, mode, model, provider_count, tool_calls,
                status, answer_sha256, created_at_utc, error, response_id,
                request_id, evidence_records, input_tokens, output_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                query_text,
                mode,
                model,
                int(provider_count),
                int(tool_calls),
                status,
                answer_sha256,
                datetime.now(UTC).isoformat(timespec="seconds"),
                error[:2000],
                response_id[:300],
                request_id[:300],
                int(evidence_records),
                int(input_tokens),
                int(output_tokens),
            ),
        )
        connection.commit()


def record_health_check(path: str | Path, diagnostic: ConnectionDiagnostic) -> int:
    target = initialize_registry(path)
    with managed_connect(target) as connection:
        cursor = connection.execute(
            """
            INSERT INTO provider_health_checks(
                provider, available, stage, status, latency_ms, records,
                cache_status, http_status, request_id, error_type, error,
                checked_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                diagnostic.provider,
                1 if diagnostic.available else 0,
                diagnostic.stage,
                diagnostic.status,
                diagnostic.latency_ms,
                diagnostic.records,
                diagnostic.cache_status,
                diagnostic.http_status,
                diagnostic.request_id,
                diagnostic.error_type,
                diagnostic.error[:2000],
                diagnostic.checked_at_utc or datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def recent_queries(path: str | Path, limit: int = 100) -> list[dict[str, object]]:
    target = initialize_registry(path)
    with managed_connect(target) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT query_id, provider, query_text, entity_type, record_count,
                   source_url, response_sha256, cache_status, warnings_json,
                   retrieved_at_utc, elapsed_ms, request_id, provider_version
            FROM connected_queries
            ORDER BY query_id DESC LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
    return [{**dict(row), "warnings": json.loads(str(row["warnings_json"] or "[]"))} for row in rows]


def recent_copilot_runs(path: str | Path, limit: int = 100) -> list[dict[str, object]]:
    target = initialize_registry(path)
    with managed_connect(target) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM copilot_runs ORDER BY created_at_utc DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    return [dict(row) for row in rows]


def recent_health_checks(path: str | Path, limit: int = 200) -> list[dict[str, object]]:
    target = initialize_registry(path)
    with managed_connect(target) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM provider_health_checks ORDER BY check_id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    return [dict(row) for row in rows]


def latest_health_by_provider(path: str | Path) -> list[dict[str, object]]:
    target = initialize_registry(path)
    with managed_connect(target) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT h.* FROM provider_health_checks h
            JOIN (
                SELECT provider, MAX(check_id) AS max_id
                FROM provider_health_checks GROUP BY provider
            ) latest ON latest.max_id = h.check_id
            ORDER BY h.provider
            """
        ).fetchall()
    return [dict(row) for row in rows]


def registry_summary(path: str | Path) -> dict[str, object]:
    target = initialize_registry(path)
    with managed_connect(target) as connection:
        query_count = int(connection.execute("SELECT COUNT(*) FROM connected_queries").fetchone()[0])
        record_count = int(connection.execute("SELECT COUNT(*) FROM connected_records").fetchone()[0])
        provider_count = int(connection.execute("SELECT COUNT(DISTINCT provider) FROM connected_queries").fetchone()[0])
        copilot_count = int(connection.execute("SELECT COUNT(*) FROM copilot_runs").fetchone()[0])
        health_count = int(connection.execute("SELECT COUNT(*) FROM provider_health_checks").fetchone()[0])
    return {
        "queries": query_count,
        "records": record_count,
        "providers_used": provider_count,
        "copilot_runs": copilot_count,
        "health_checks": health_count,
        "path": str(target),
    }
