from __future__ import annotations

import json
import sqlite3
from biointel.database.core import managed_connect
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS biotechnology_runs (
    run_fingerprint TEXT PRIMARY KEY,
    project_code TEXT NOT NULL,
    project_name TEXT NOT NULL,
    status TEXT NOT NULL,
    quality_score REAL NOT NULL,
    input_rows INTEGER NOT NULL,
    output_rows INTEGER NOT NULL,
    parameters_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_biotechnology_runs_project
ON biotechnology_runs(project_code, created_at_utc DESC);
CREATE TABLE IF NOT EXISTS biotechnology_run_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_fingerprint TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY(run_fingerprint) REFERENCES biotechnology_runs(run_fingerprint) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_biotechnology_run_events_run
ON biotechnology_run_events(run_fingerprint, created_at_utc DESC);
"""


@dataclass(frozen=True)
class RegisteredRun:
    run_fingerprint: str
    project_code: str
    project_name: str
    status: str
    quality_score: float
    input_rows: int
    output_rows: int
    parameters: dict[str, Any]
    metrics: dict[str, Any]
    created_at_utc: str


def initialize_run_registry(path: str | Path) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with managed_connect(target) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(SCHEMA)
        connection.commit()
    return target


def register_run(
    path: str | Path,
    *,
    run_fingerprint: str,
    project_code: str,
    project_name: str,
    status: str,
    quality_score: float,
    input_rows: int,
    output_rows: int,
    parameters: Mapping[str, Any],
    metrics: Mapping[str, Any],
) -> RegisteredRun:
    registry = initialize_run_registry(path)
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with managed_connect(registry) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            """
            INSERT INTO biotechnology_runs (
                run_fingerprint, project_code, project_name, status, quality_score,
                input_rows, output_rows, parameters_json, metrics_json, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_fingerprint) DO UPDATE SET
                status=excluded.status,
                quality_score=excluded.quality_score,
                input_rows=excluded.input_rows,
                output_rows=excluded.output_rows,
                parameters_json=excluded.parameters_json,
                metrics_json=excluded.metrics_json
            """,
            (
                run_fingerprint, project_code, project_name, status, float(quality_score),
                int(input_rows), int(output_rows), json.dumps(dict(parameters), sort_keys=True, default=str),
                json.dumps(dict(metrics), sort_keys=True, default=str), created,
            ),
        )
        connection.execute(
            "INSERT INTO biotechnology_run_events (run_fingerprint,event_type,message,details_json,created_at_utc) VALUES (?,?,?,?,?)",
            (run_fingerprint, "run_registered", "Analysis run registered", "{}", created),
        )
        connection.commit()
    return RegisteredRun(run_fingerprint, project_code, project_name, status, float(quality_score), int(input_rows), int(output_rows), dict(parameters), dict(metrics), created)


def list_runs(path: str | Path, *, project_code: str | None = None, limit: int = 100) -> pd.DataFrame:
    registry = initialize_run_registry(path)
    query = "SELECT * FROM biotechnology_runs"
    params: list[Any] = []
    if project_code:
        query += " WHERE project_code=?"
        params.append(project_code)
    query += " ORDER BY created_at_utc DESC LIMIT ?"
    params.append(max(int(limit), 1))
    with managed_connect(registry) as connection:
        frame = pd.read_sql_query(query, connection, params=params)
    if frame.empty:
        return frame
    frame["parameters"] = frame.pop("parameters_json").map(json.loads)
    frame["metrics"] = frame.pop("metrics_json").map(json.loads)
    return frame


def compare_runs(path: str | Path, *, project_code: str, limit: int = 20) -> pd.DataFrame:
    runs = list_runs(path, project_code=project_code, limit=limit)
    if runs.empty:
        return runs
    metric_keys = sorted({key for payload in runs["metrics"] for key in payload})
    records: list[dict[str, Any]] = []
    for row in runs.itertuples(index=False):
        record = {
            "run_fingerprint": row.run_fingerprint,
            "created_at_utc": row.created_at_utc,
            "status": row.status,
            "quality_score": row.quality_score,
            "input_rows": row.input_rows,
            "output_rows": row.output_rows,
        }
        record.update({f"metric_{key}": row.metrics.get(key) for key in metric_keys})
        records.append(record)
    return pd.DataFrame(records)
