from __future__ import annotations

import json
import sqlite3
from biointel.database.core import managed_connect
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .provenance import utc_now


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,
    workflow_name TEXT NOT NULL,
    workflow_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_seconds REAL NOT NULL DEFAULT 0,
    output_directory TEXT NOT NULL,
    resumed INTEGER NOT NULL DEFAULT 0,
    implementation_readiness REAL NOT NULL DEFAULT 0,
    scientific_evidence_score REAL NOT NULL DEFAULT 0,
    parameters_json TEXT NOT NULL DEFAULT '{}',
    environment_json TEXT NOT NULL DEFAULT '{}',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_steps (
    run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    block TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_seconds REAL NOT NULL DEFAULT 0,
    attempt INTEGER NOT NULL DEFAULT 1,
    depends_on_json TEXT NOT NULL DEFAULT '[]',
    command_json TEXT NOT NULL DEFAULT '[]',
    exit_code INTEGER,
    stdout_path TEXT NOT NULL DEFAULT '',
    stderr_path TEXT NOT NULL DEFAULT '',
    result_path TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    metrics_json TEXT NOT NULL DEFAULT '{}',
    artifacts_json TEXT NOT NULL DEFAULT '[]',
    skipped_reason TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (run_id, step_id),
    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS workflow_artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    role TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS workflow_audit_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_status ON workflow_steps(status, finished_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_artifacts_run ON workflow_artifacts(run_id, step_id);
"""


class WorkflowRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = managed_connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def upsert_run(self, record: dict[str, Any]) -> None:
        now = utc_now()
        values = {
            "run_id": record["run_id"],
            "workflow_name": record["workflow_name"],
            "workflow_sha256": record["workflow_sha256"],
            "status": record.get("status", "running"),
            "started_at": record.get("started_at", now),
            "finished_at": record.get("finished_at", ""),
            "duration_seconds": float(record.get("duration_seconds", 0)),
            "output_directory": record.get("output_directory", ""),
            "resumed": int(bool(record.get("resumed", False))),
            "implementation_readiness": float(record.get("implementation_readiness", 0)),
            "scientific_evidence_score": float(record.get("scientific_evidence_score", 0)),
            "parameters_json": json.dumps(record.get("parameters", {}), sort_keys=True, default=str),
            "environment_json": json.dumps(record.get("environment", {}), sort_keys=True, default=str),
            "warnings_json": json.dumps(record.get("warnings", []), sort_keys=True, default=str),
            "created_at": now,
            "updated_at": now,
        }
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_runs (
                    run_id, workflow_name, workflow_sha256, status, started_at, finished_at,
                    duration_seconds, output_directory, resumed, implementation_readiness,
                    scientific_evidence_score, parameters_json, environment_json, warnings_json,
                    created_at, updated_at
                ) VALUES (
                    :run_id, :workflow_name, :workflow_sha256, :status, :started_at, :finished_at,
                    :duration_seconds, :output_directory, :resumed, :implementation_readiness,
                    :scientific_evidence_score, :parameters_json, :environment_json, :warnings_json,
                    :created_at, :updated_at
                )
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    finished_at=excluded.finished_at,
                    duration_seconds=excluded.duration_seconds,
                    output_directory=excluded.output_directory,
                    resumed=excluded.resumed,
                    implementation_readiness=excluded.implementation_readiness,
                    scientific_evidence_score=excluded.scientific_evidence_score,
                    parameters_json=excluded.parameters_json,
                    environment_json=excluded.environment_json,
                    warnings_json=excluded.warnings_json,
                    updated_at=excluded.updated_at
                """,
                values,
            )

    def upsert_step(self, record: dict[str, Any]) -> None:
        values = {
            "run_id": record["run_id"],
            "step_id": record["step_id"],
            "block": record.get("block", ""),
            "status": record.get("status", "pending"),
            "started_at": record.get("started_at", utc_now()),
            "finished_at": record.get("finished_at", ""),
            "duration_seconds": float(record.get("duration_seconds", 0)),
            "attempt": int(record.get("attempt", 1)),
            "depends_on_json": json.dumps(record.get("depends_on", []), default=str),
            "command_json": json.dumps(record.get("command", []), default=str),
            "exit_code": record.get("exit_code"),
            "stdout_path": record.get("stdout_path", ""),
            "stderr_path": record.get("stderr_path", ""),
            "result_path": record.get("result_path", ""),
            "error": record.get("error", ""),
            "metrics_json": json.dumps(record.get("metrics", {}), sort_keys=True, default=str),
            "artifacts_json": json.dumps(record.get("artifacts", []), sort_keys=True, default=str),
            "skipped_reason": record.get("skipped_reason", ""),
        }
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_steps (
                    run_id, step_id, block, status, started_at, finished_at, duration_seconds,
                    attempt, depends_on_json, command_json, exit_code, stdout_path, stderr_path,
                    result_path, error, metrics_json, artifacts_json, skipped_reason
                ) VALUES (
                    :run_id, :step_id, :block, :status, :started_at, :finished_at, :duration_seconds,
                    :attempt, :depends_on_json, :command_json, :exit_code, :stdout_path, :stderr_path,
                    :result_path, :error, :metrics_json, :artifacts_json, :skipped_reason
                )
                ON CONFLICT(run_id, step_id) DO UPDATE SET
                    status=excluded.status,
                    finished_at=excluded.finished_at,
                    duration_seconds=excluded.duration_seconds,
                    attempt=excluded.attempt,
                    command_json=excluded.command_json,
                    exit_code=excluded.exit_code,
                    stdout_path=excluded.stdout_path,
                    stderr_path=excluded.stderr_path,
                    result_path=excluded.result_path,
                    error=excluded.error,
                    metrics_json=excluded.metrics_json,
                    artifacts_json=excluded.artifacts_json,
                    skipped_reason=excluded.skipped_reason
                """,
                values,
            )

    def add_artifacts(self, run_id: str, artifacts: list[dict[str, Any]]) -> None:
        if not artifacts:
            return
        with self.connect() as connection:
            for artifact in artifacts:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO workflow_artifacts (
                        artifact_id, run_id, step_id, role, path, sha256, size_bytes,
                        media_type, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact["artifact_id"], run_id, artifact.get("step_id", ""), artifact.get("role", "output"),
                        artifact["path"], artifact["sha256"], int(artifact["size_bytes"]),
                        artifact.get("media_type", "application/octet-stream"),
                        json.dumps(artifact.get("metadata", {}), sort_keys=True, default=str), utc_now(),
                    ),
                )

    def audit(self, run_id: str | None, event_type: str, message: str, payload: dict[str, Any] | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO workflow_audit_events (run_id, event_type, message, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (run_id, event_type, message, json.dumps(payload or {}, sort_keys=True, default=str), utc_now()),
            )

    def recent_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM workflow_runs ORDER BY updated_at DESC LIMIT ?", (max(1, int(limit)),)
            ).fetchall()
        return [dict(row) for row in rows]

    def run_steps(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM workflow_steps WHERE run_id=? ORDER BY started_at, step_id", (run_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def integrity_report(self) -> dict[str, Any]:
        with self.connect() as connection:
            quick = connection.execute("PRAGMA quick_check").fetchone()[0]
            foreign = [dict(row) for row in connection.execute("PRAGMA foreign_key_check").fetchall()]
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("workflow_runs", "workflow_steps", "workflow_artifacts", "workflow_audit_events")
            }
        return {"quick_check": quick, "foreign_key_issues": foreign, "counts": counts, "healthy": quick == "ok" and not foreign}
