from __future__ import annotations

import json
import sqlite3
from biointel.database.core import managed_connect
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ProspectiveStudy:
    study_id: str
    name: str
    model_filename: str
    model_sha256: str
    frozen_at_utc: str
    status: str
    prediction_count: int
    outcome_count: int


class ProspectiveValidationRegistry:
    """Freeze predictions before outcomes are available and score them later."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = managed_connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS prospective_studies(
                    study_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    model_filename TEXT NOT NULL,
                    model_sha256 TEXT NOT NULL,
                    frozen_at_utc TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'frozen'
                );
                CREATE TABLE IF NOT EXISTS prospective_predictions(
                    study_id TEXT NOT NULL,
                    sample_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY(study_id, sample_id),
                    FOREIGN KEY(study_id) REFERENCES prospective_studies(study_id)
                );
                CREATE TABLE IF NOT EXISTS prospective_outcomes(
                    study_id TEXT NOT NULL,
                    sample_id TEXT NOT NULL,
                    observed_value REAL NOT NULL,
                    recorded_at_utc TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(study_id, sample_id),
                    FOREIGN KEY(study_id) REFERENCES prospective_studies(study_id)
                );
                """
            )

    def freeze(
        self,
        *,
        name: str,
        model_filename: str,
        model_sha256: str,
        predictions: pd.DataFrame,
    ) -> ProspectiveStudy:
        if "sample_id" not in predictions.columns or "prediction" not in predictions.columns:
            raise ValueError("Prospective predictions require sample_id and prediction columns.")
        if predictions["sample_id"].astype(str).duplicated().any():
            raise ValueError("Prospective sample_id values must be unique.")
        study_id = "prospective-" + uuid4().hex
        frozen_at = _utc_now()
        rows = [
            (
                study_id,
                str(record["sample_id"]),
                json.dumps(record, sort_keys=True, default=str),
            )
            for record in predictions.to_dict(orient="records")
        ]
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO prospective_studies VALUES (?, ?, ?, ?, ?, 'frozen')",
                (study_id, name.strip(), model_filename, model_sha256, frozen_at),
            )
            connection.executemany("INSERT INTO prospective_predictions VALUES (?, ?, ?)", rows)
        return self.get(study_id)

    def record_outcomes(
        self,
        study_id: str,
        outcomes: pd.DataFrame,
        *,
        value_column: str = "observed_value",
    ) -> ProspectiveStudy:
        required = {"sample_id", value_column}
        missing = required - set(outcomes.columns)
        if missing:
            raise ValueError("Missing outcome columns: " + ", ".join(sorted(missing)))
        rows = [
            (
                study_id,
                str(record["sample_id"]),
                float(record[value_column]),
                _utc_now(),
                str(record.get("notes", "")),
            )
            for record in outcomes.to_dict(orient="records")
        ]
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM prospective_studies WHERE study_id=?", (study_id,)
            ).fetchone()
            if exists is None:
                raise KeyError(study_id)
            connection.executemany(
                """
                INSERT INTO prospective_outcomes VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(study_id, sample_id) DO UPDATE SET
                    observed_value=excluded.observed_value,
                    recorded_at_utc=excluded.recorded_at_utc,
                    notes=excluded.notes
                """,
                rows,
            )
            connection.execute(
                "UPDATE prospective_studies SET status='outcomes_recorded' WHERE study_id=?",
                (study_id,),
            )
        return self.get(study_id)

    def joined_results(self, study_id: str) -> pd.DataFrame:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT p.sample_id, p.payload_json, o.observed_value, o.recorded_at_utc
                FROM prospective_predictions p
                LEFT JOIN prospective_outcomes o
                  ON o.study_id=p.study_id AND o.sample_id=p.sample_id
                WHERE p.study_id=? ORDER BY p.sample_id
                """,
                (study_id,),
            ).fetchall()
        output = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload["observed_value"] = row["observed_value"]
            payload["outcome_recorded_at_utc"] = row["recorded_at_utc"]
            output.append(payload)
        return pd.DataFrame(output)

    def get(self, study_id: str) -> ProspectiveStudy:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT s.*,
                       (SELECT COUNT(*) FROM prospective_predictions p WHERE p.study_id=s.study_id) prediction_count,
                       (SELECT COUNT(*) FROM prospective_outcomes o WHERE o.study_id=s.study_id) outcome_count
                FROM prospective_studies s WHERE s.study_id=?
                """,
                (study_id,),
            ).fetchone()
        if row is None:
            raise KeyError(study_id)
        return ProspectiveStudy(
            study_id=row["study_id"],
            name=row["name"],
            model_filename=row["model_filename"],
            model_sha256=row["model_sha256"],
            frozen_at_utc=row["frozen_at_utc"],
            status=row["status"],
            prediction_count=int(row["prediction_count"]),
            outcome_count=int(row["outcome_count"]),
        )
