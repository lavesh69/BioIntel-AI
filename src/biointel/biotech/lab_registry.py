from __future__ import annotations

import hashlib
import json
import sqlite3
from biointel.database.core import managed_connect
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "lab_analytics.sqlite3"

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS lab_runs (
    run_id TEXT PRIMARY KEY,
    workflow TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('completed','review','failed')),
    created_at_utc TEXT NOT NULL,
    operator TEXT NOT NULL DEFAULT 'local_user',
    source_filename TEXT NOT NULL DEFAULT '',
    input_sha256 TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    recommendations_json TEXT NOT NULL,
    software_version TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS lab_artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES lab_runs(run_id) ON DELETE CASCADE,
    artifact_name TEXT NOT NULL,
    artifact_kind TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    row_count INTEGER,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lab_reviews (
    review_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES lab_runs(run_id) ON DELETE CASCADE,
    decision TEXT NOT NULL CHECK(decision IN ('pending','accepted','rejected')),
    reviewer TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lab_runs_workflow_time ON lab_runs(workflow, created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_lab_artifacts_run ON lab_artifacts(run_id);
"""


def connect(path: str | Path = DEFAULT_PATH) -> sqlite3.Connection:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = managed_connect(target)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(SCHEMA)
    return connection


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def record_run(
    *,
    workflow: str,
    input_frame: pd.DataFrame,
    parameters: dict[str, Any],
    outputs: dict[str, Any],
    recommendations: list[str] | None = None,
    source_filename: str = "",
    status: str = "completed",
    operator: str = "local_user",
    software_version: str = "",
    path: str | Path = DEFAULT_PATH,
) -> str:
    input_payload = input_frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    canonical = json.dumps(parameters, sort_keys=True, default=str).encode("utf-8")
    created = datetime.now(UTC).isoformat(timespec="seconds")
    run_id = _digest(workflow.encode() + input_payload + canonical + created.encode())[:24]
    with closing(connect(path)) as connection:
        connection.execute(
            "INSERT INTO lab_runs(run_id,workflow,status,created_at_utc,operator,source_filename,input_sha256,parameters_json,recommendations_json,software_version) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (run_id, workflow, status, created, operator, source_filename, _digest(input_payload), json.dumps(parameters, sort_keys=True, default=str), json.dumps(recommendations or []), software_version),
        )
        for name, value in outputs.items():
            if isinstance(value, pd.DataFrame):
                payload = value.to_csv(index=False, lineterminator="\n").encode("utf-8")
                kind = "table"
                rows = len(value)
            else:
                payload = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
                kind = "json"
                rows = None
            artifact_id = _digest(run_id.encode() + str(name).encode() + payload)[:24]
            connection.execute(
                "INSERT INTO lab_artifacts(artifact_id,run_id,artifact_name,artifact_kind,sha256,row_count,created_at_utc) VALUES(?,?,?,?,?,?,?)",
                (artifact_id, run_id, str(name), kind, _digest(payload), rows, created),
            )
        connection.commit()
    return run_id


def list_runs(*, limit: int = 100, path: str | Path = DEFAULT_PATH) -> pd.DataFrame:
    with closing(connect(path)) as connection:
        return pd.read_sql_query(
            "SELECT run_id,workflow,status,created_at_utc,operator,source_filename,input_sha256,software_version FROM lab_runs ORDER BY created_at_utc DESC LIMIT ?",
            connection,
            params=(int(limit),),
        )


def registry_summary(path: str | Path = DEFAULT_PATH) -> dict[str, int]:
    with closing(connect(path)) as connection:
        runs = connection.execute("SELECT COUNT(*) FROM lab_runs").fetchone()[0]
        artifacts = connection.execute("SELECT COUNT(*) FROM lab_artifacts").fetchone()[0]
        reviews = connection.execute("SELECT COUNT(*) FROM lab_reviews").fetchone()[0]
    return {"runs": int(runs), "artifacts": int(artifacts), "reviews": int(reviews)}
