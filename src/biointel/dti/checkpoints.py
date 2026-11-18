from __future__ import annotations

import json
import os
import sqlite3
from biointel.database.core import managed_connect
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd


def checkpoint_format(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".sqlite", ".sqlite3", ".db"}:
        return "sqlite"
    if suffix in {".parquet", ".pq"}:
        return "parquet"
    if suffix == ".csv":
        return "csv"
    raise ValueError("Checkpoint extension must be .sqlite3, .parquet or .csv.")


def _json_safe_record(record: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in record.items():
        is_missing = False
        if not isinstance(value, (list, dict, tuple)):
            try:
                missing_value = pd.isna(value)
                is_missing = bool(missing_value) if not hasattr(missing_value, "__len__") else False
            except (TypeError, ValueError):
                is_missing = False
        if is_missing:
            safe[key] = None
        elif hasattr(value, "item"):
            safe[key] = value.item()
        else:
            safe[key] = value
    return safe


class BatchCheckpointStore:
    """Incremental resumable checkpoint store.

    SQLite is recommended because each chunk is committed transactionally and
    rows are upserted by sample_id without rewriting previous results.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.format = checkpoint_format(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.format == "sqlite":
            self._initialize_sqlite()

    def _connect(self) -> sqlite3.Connection:
        connection = managed_connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize_sqlite(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS prediction_rows(
                    sample_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_prediction_rows_updated "
                "ON prediction_rows(updated_at_utc)"
            )

    def exists(self) -> bool:
        if not self.path.is_file():
            return False
        if self.format != "sqlite":
            return self.path.stat().st_size > 0
        with self._connect() as connection:
            return bool(connection.execute("SELECT 1 FROM prediction_rows LIMIT 1").fetchone())

    def clear(self) -> None:
        if self.path.exists():
            if self.format == "sqlite":
                with self._connect() as connection:
                    connection.execute("DELETE FROM prediction_rows")
                with self._connect() as connection:
                    connection.execute("VACUUM")
            else:
                self.path.unlink()

    def load(self) -> pd.DataFrame:
        if not self.path.is_file():
            return pd.DataFrame()
        if self.format == "sqlite":
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT payload_json FROM prediction_rows ORDER BY rowid"
                ).fetchall()
            return pd.DataFrame([json.loads(row[0]) for row in rows])
        if self.format == "csv":
            if self.path.stat().st_size == 0:
                return pd.DataFrame()
            return pd.read_csv(self.path)
        try:
            return pd.read_parquet(self.path)
        except ImportError as exc:
            raise RuntimeError(
                "Parquet checkpoints require pyarrow or fastparquet. "
                "Use .sqlite3 for a dependency-free transactional checkpoint."
            ) from exc

    def count(self) -> int:
        """Return result count without materialising the whole checkpoint."""

        if not self.path.is_file():
            return 0
        if self.format == "sqlite":
            with self._connect() as connection:
                row = connection.execute("SELECT COUNT(*) FROM prediction_rows").fetchone()
            return int(row[0] if row else 0)
        return int(len(self.load()))

    def sample_ids(self, *, limit: int | None = None) -> list[str]:
        if not self.path.is_file() or (limit is not None and int(limit) < 1):
            return []
        if self.format == "sqlite":
            query = "SELECT sample_id FROM prediction_rows ORDER BY rowid"
            parameters: tuple[object, ...] = ()
            if limit is not None:
                query += " LIMIT ?"
                parameters = (int(limit),)
            with self._connect() as connection:
                rows = connection.execute(query, parameters).fetchall()
            return [str(row[0]) for row in rows]
        values = self.load().get("sample_id", pd.Series(dtype="string")).astype(str)
        return values.head(limit).tolist() if limit is not None else values.tolist()

    def preview(self, limit: int = 100) -> pd.DataFrame:
        bounded = max(1, min(int(limit), 10_000))
        if not self.path.is_file():
            return pd.DataFrame()
        if self.format == "sqlite":
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT payload_json FROM prediction_rows ORDER BY rowid LIMIT ?",
                    (bounded,),
                ).fetchall()
            return pd.DataFrame([json.loads(row[0]) for row in rows])
        return self.load().head(bounded).copy()

    def result_counts(self) -> tuple[int, int]:
        if not self.path.is_file():
            return 0, 0
        if self.format == "sqlite":
            total = 0
            errors = 0
            with self._connect() as connection:
                for row in connection.execute("SELECT payload_json FROM prediction_rows"):
                    total += 1
                    errors += int(bool(json.loads(row[0]).get("error")))
            return total, errors
        frame = self.load()
        error_rows = (
            int(frame["error"].fillna("").astype(bool).sum())
            if not frame.empty and "error" in frame.columns
            else 0
        )
        return int(len(frame)), error_rows

    def append(self, dataframe: pd.DataFrame) -> None:
        if dataframe.empty:
            return
        if "sample_id" not in dataframe.columns:
            raise ValueError("Checkpoint rows require a sample_id column.")
        if self.format == "sqlite":
            records = []
            for record in dataframe.to_dict(orient="records"):
                safe = _json_safe_record(record)
                records.append(
                    (
                        str(safe["sample_id"]),
                        json.dumps(safe, sort_keys=True, default=str),
                    )
                )
            with self._connect() as connection:
                connection.executemany(
                    """
                    INSERT INTO prediction_rows(sample_id, payload_json)
                    VALUES (?, ?)
                    ON CONFLICT(sample_id) DO UPDATE SET
                        payload_json=excluded.payload_json,
                        updated_at_utc=CURRENT_TIMESTAMP
                    """,
                    records,
                )
            return
        if self.format == "csv":
            dataframe.to_csv(
                self.path,
                mode="a",
                header=not self.path.exists() or self.path.stat().st_size == 0,
                index=False,
            )
            return
        previous = self.load()
        combined = pd.concat([previous, dataframe], ignore_index=True)
        combined = combined.drop_duplicates(subset=["sample_id"], keep="last")
        self._atomic_parquet_write(combined)

    def replace(self, dataframe: pd.DataFrame) -> None:
        self.clear()
        self.append(dataframe)

    def _atomic_parquet_write(self, dataframe: pd.DataFrame) -> None:
        handle, temp_name = tempfile.mkstemp(
            prefix=self.path.stem + "-", suffix=self.path.suffix, dir=self.path.parent
        )
        os.close(handle)
        temp = Path(temp_name)
        try:
            dataframe.to_parquet(temp, index=False)
            os.replace(temp, self.path)
        except ImportError as exc:
            temp.unlink(missing_ok=True)
            raise RuntimeError(
                "Parquet checkpoints require pyarrow or fastparquet. "
                "Use .sqlite3 for a dependency-free transactional checkpoint."
            ) from exc
        finally:
            temp.unlink(missing_ok=True)
