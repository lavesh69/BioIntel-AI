from __future__ import annotations

import json
import sqlite3
from biointel.database.core import managed_connect
from dataclasses import asdict
from pathlib import Path
from typing import Any

from biointel.training.model_artifact import ModelArtifact

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    trained_at_utc TEXT NOT NULL,
    model_file TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    task_type TEXT NOT NULL,
    dataset_name TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    dataset_sha256 TEXT NOT NULL,
    split_strategy TEXT NOT NULL,
    synthetic_demo INTEGER NOT NULL,
    train_rows INTEGER NOT NULL,
    validation_rows INTEGER NOT NULL,
    test_rows INTEGER NOT NULL,
    metrics_json TEXT NOT NULL,
    validation_metrics_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);
"""


def initialize_registry(path: str | Path) -> Path:
    registry_path = Path(path).resolve()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with managed_connect(registry_path) as connection:
        connection.execute(SCHEMA)
        connection.commit()
    return registry_path


def register_experiment(
    registry_path: str | Path,
    artifact: ModelArtifact,
    model_file: str,
) -> None:
    """Insert or update an experiment without storing raw sequences or datasets."""

    path = initialize_registry(registry_path)
    metadata = artifact.metadata
    with managed_connect(path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO experiments (
                experiment_id, trained_at_utc, model_file, model_name,
                model_version, task_type, dataset_name, dataset_version,
                dataset_sha256, split_strategy, synthetic_demo, train_rows,
                validation_rows, test_rows, metrics_json,
                validation_metrics_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metadata.experiment_id,
                metadata.trained_at_utc,
                Path(model_file).name,
                metadata.model_name,
                metadata.model_version,
                metadata.task_type,
                metadata.dataset_name,
                metadata.dataset_version,
                metadata.dataset_sha256,
                metadata.split_strategy,
                int(metadata.synthetic_demo),
                metadata.train_rows,
                metadata.validation_rows,
                metadata.test_rows,
                json.dumps(metadata.metrics, sort_keys=True),
                json.dumps(metadata.validation_metrics, sort_keys=True),
                json.dumps(asdict(metadata), sort_keys=True, default=str),
            ),
        )
        connection.commit()


def list_experiments(
    registry_path: str | Path,
    limit: int = 500,
) -> list[dict[str, Any]]:
    path = initialize_registry(registry_path)
    with managed_connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT * FROM experiments
            ORDER BY trained_at_utc DESC
            LIMIT ?
            """,
            (max(1, min(limit, 5000)),),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_experiment(
    registry_path: str | Path,
    experiment_id: str,
) -> bool:
    path = initialize_registry(registry_path)
    with managed_connect(path) as connection:
        cursor = connection.execute(
            "DELETE FROM experiments WHERE experiment_id = ?",
            (experiment_id,),
        )
        connection.commit()
        return cursor.rowcount > 0
