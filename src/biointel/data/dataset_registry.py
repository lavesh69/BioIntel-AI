from __future__ import annotations

import json
import sqlite3
from biointel.database.core import managed_connect
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from biointel.provenance import stable_dataframe_sha256

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    dataset_sha256 TEXT PRIMARY KEY,
    dataset_name TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    task_type TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    column_names_json TEXT NOT NULL,
    source_description TEXT NOT NULL,
    activity_type TEXT,
    parent_sha256 TEXT,
    notes TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_datasets_name
ON datasets(dataset_name, dataset_version);
CREATE INDEX IF NOT EXISTS idx_datasets_parent
ON datasets(parent_sha256);
"""


@dataclass(frozen=True)
class DatasetRecord:
    dataset_sha256: str
    dataset_name: str
    dataset_version: str
    task_type: str
    row_count: int
    column_names: tuple[str, ...]
    source_description: str
    activity_type: str | None
    parent_sha256: str | None
    notes: str
    created_at_utc: str
    metadata: dict[str, Any]


def initialize_dataset_registry(path: str | Path) -> Path:
    registry = Path(path).resolve()
    registry.parent.mkdir(parents=True, exist_ok=True)
    with managed_connect(registry) as connection:
        connection.executescript(SCHEMA)
        connection.commit()
    return registry


def register_dataset(
    registry_path: str | Path,
    dataframe: pd.DataFrame,
    dataset_name: str,
    dataset_version: str,
    task_type: str,
    source_description: str,
    activity_type: str | None = None,
    parent_sha256: str | None = None,
    notes: str = "",
    metadata: dict[str, Any] | None = None,
) -> DatasetRecord:
    if task_type not in {"classification", "regression", "unlabelled"}:
        raise ValueError("task_type must be classification, regression or unlabelled")
    if not dataset_name.strip():
        raise ValueError("dataset_name is required")
    if not dataset_version.strip():
        raise ValueError("dataset_version is required")

    dataset_hash = stable_dataframe_sha256(dataframe)
    created_at = datetime.now(UTC).isoformat(timespec="seconds")
    columns = tuple(map(str, dataframe.columns))
    metadata_payload = metadata or {}

    record = DatasetRecord(
        dataset_sha256=dataset_hash,
        dataset_name=dataset_name.strip(),
        dataset_version=dataset_version.strip(),
        task_type=task_type,
        row_count=len(dataframe),
        column_names=columns,
        source_description=source_description.strip() or "Not specified",
        activity_type=activity_type,
        parent_sha256=parent_sha256 or None,
        notes=notes.strip(),
        created_at_utc=created_at,
        metadata=metadata_payload,
    )

    path = initialize_dataset_registry(registry_path)
    with managed_connect(path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO datasets (
                dataset_sha256, dataset_name, dataset_version, task_type,
                row_count, column_names_json, source_description,
                activity_type, parent_sha256, notes, created_at_utc,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.dataset_sha256,
                record.dataset_name,
                record.dataset_version,
                record.task_type,
                record.row_count,
                json.dumps(record.column_names),
                record.source_description,
                record.activity_type,
                record.parent_sha256,
                record.notes,
                record.created_at_utc,
                json.dumps(record.metadata, sort_keys=True, default=str),
            ),
        )
        connection.commit()
    return record


def list_datasets(
    registry_path: str | Path,
    limit: int = 1000,
) -> list[DatasetRecord]:
    path = initialize_dataset_registry(registry_path)
    with managed_connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT * FROM datasets
            ORDER BY created_at_utc DESC
            LIMIT ?
            """,
            (max(1, min(limit, 5000)),),
        ).fetchall()

    records: list[DatasetRecord] = []
    for row in rows:
        records.append(
            DatasetRecord(
                dataset_sha256=row["dataset_sha256"],
                dataset_name=row["dataset_name"],
                dataset_version=row["dataset_version"],
                task_type=row["task_type"],
                row_count=int(row["row_count"]),
                column_names=tuple(json.loads(row["column_names_json"])),
                source_description=row["source_description"],
                activity_type=row["activity_type"],
                parent_sha256=row["parent_sha256"],
                notes=row["notes"],
                created_at_utc=row["created_at_utc"],
                metadata=json.loads(row["metadata_json"]),
            )
        )
    return records


def get_dataset(
    registry_path: str | Path,
    dataset_sha256: str,
) -> DatasetRecord | None:
    for record in list_datasets(registry_path, limit=5000):
        if record.dataset_sha256 == dataset_sha256:
            return record
    return None


def delete_dataset_record(
    registry_path: str | Path,
    dataset_sha256: str,
) -> bool:
    path = initialize_dataset_registry(registry_path)
    with managed_connect(path) as connection:
        cursor = connection.execute(
            "DELETE FROM datasets WHERE dataset_sha256 = ?",
            (dataset_sha256,),
        )
        connection.commit()
        return cursor.rowcount > 0


def lineage_edges(
    registry_path: str | Path,
) -> list[dict[str, str]]:
    records = list_datasets(registry_path, limit=5000)
    known = {record.dataset_sha256 for record in records}
    edges = []
    for record in records:
        if record.parent_sha256:
            edges.append(
                {
                    "parent": record.parent_sha256,
                    "child": record.dataset_sha256,
                    "parent_known": str(record.parent_sha256 in known),
                }
            )
    return edges


def dataset_record_json(record: DatasetRecord) -> str:
    return json.dumps(
        asdict(record),
        indent=2,
        sort_keys=True,
        default=str,
    )
