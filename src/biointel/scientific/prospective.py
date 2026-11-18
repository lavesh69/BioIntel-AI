from __future__ import annotations

import hashlib
import json
import sqlite3
from biointel.database.core import managed_connect
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProspectiveProtocol:
    study_id: str
    title: str
    hypothesis: str
    primary_endpoint: str
    success_criterion: str
    model_sha256: str
    dataset_sha256: str
    random_seed: int
    registered_at: str
    protocol_sha256: str


class ProspectiveStudyRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with managed_connect(self.path) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS protocols(
                    study_id TEXT PRIMARY KEY, title TEXT NOT NULL, protocol_json TEXT NOT NULL,
                    protocol_sha256 TEXT NOT NULL, registered_at TEXT NOT NULL, status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS predictions(
                    study_id TEXT NOT NULL REFERENCES protocols(study_id), sample_id TEXT NOT NULL,
                    prediction REAL NOT NULL, uncertainty REAL, prediction_sha256 TEXT NOT NULL,
                    locked_at TEXT NOT NULL, PRIMARY KEY(study_id, sample_id)
                );
                CREATE TABLE IF NOT EXISTS outcomes(
                    study_id TEXT NOT NULL REFERENCES protocols(study_id), sample_id TEXT NOT NULL,
                    outcome REAL NOT NULL, measured_at TEXT NOT NULL, laboratory TEXT NOT NULL,
                    blinded_code TEXT, source_sha256 TEXT NOT NULL, PRIMARY KEY(study_id, sample_id)
                );
                CREATE TABLE IF NOT EXISTS reviews(
                    review_id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES protocols(study_id),
                    reviewer TEXT NOT NULL, independent INTEGER NOT NULL, decision TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL, notes TEXT NOT NULL
                );
                """
            )

    def register(self, *, title: str, hypothesis: str, primary_endpoint: str, success_criterion: str,
                 model_sha256: str, dataset_sha256: str, random_seed: int = 42) -> ProspectiveProtocol:
        registered = datetime.now(UTC).isoformat()
        payload = {
            "title": title, "hypothesis": hypothesis, "primary_endpoint": primary_endpoint,
            "success_criterion": success_criterion, "model_sha256": model_sha256,
            "dataset_sha256": dataset_sha256, "random_seed": int(random_seed), "registered_at": registered,
        }
        protocol_hash = _hash(payload)
        study_id = f"PVS-{protocol_hash[:16]}"
        protocol = ProspectiveProtocol(study_id, title, hypothesis, primary_endpoint, success_criterion,
                                       model_sha256, dataset_sha256, int(random_seed), registered, protocol_hash)
        with managed_connect(self.path) as db:
            db.execute("INSERT INTO protocols VALUES(?,?,?,?,?,?)",
                       (study_id, title, _canonical(asdict(protocol)), protocol_hash, registered, "registered"))
        return protocol

    def lock_predictions(self, study_id: str, predictions: list[dict[str, Any]]) -> None:
        locked = datetime.now(UTC).isoformat()
        with managed_connect(self.path) as db:
            status = db.execute("SELECT status FROM protocols WHERE study_id=?", (study_id,)).fetchone()
            if not status or status[0] != "registered":
                raise ValueError("Study must be registered and unlocked.")
            for row in predictions:
                sample_id = str(row["sample_id"])
                payload = {"study_id": study_id, "sample_id": sample_id, "prediction": float(row["prediction"]),
                           "uncertainty": row.get("uncertainty"), "locked_at": locked}
                db.execute("INSERT INTO predictions VALUES(?,?,?,?,?,?)",
                           (study_id, sample_id, float(row["prediction"]), row.get("uncertainty"), _hash(payload), locked))
            db.execute("UPDATE protocols SET status='locked' WHERE study_id=?", (study_id,))

    def import_outcomes(self, study_id: str, outcomes: list[dict[str, Any]], *, laboratory: str, source_sha256: str) -> None:
        measured = datetime.now(UTC).isoformat()
        with managed_connect(self.path) as db:
            status = db.execute("SELECT status FROM protocols WHERE study_id=?", (study_id,)).fetchone()
            if not status or status[0] != "locked":
                raise ValueError("Predictions must be locked before outcomes are imported.")
            for row in outcomes:
                db.execute("INSERT INTO outcomes VALUES(?,?,?,?,?,?,?)",
                           (study_id, str(row["sample_id"]), float(row["outcome"]), measured, laboratory,
                            row.get("blinded_code"), source_sha256))
            db.execute("UPDATE protocols SET status='completed' WHERE study_id=?", (study_id,))

    def summary(self) -> dict[str, int]:
        with managed_connect(self.path) as db:
            return {
                "registered": db.execute("SELECT COUNT(*) FROM protocols").fetchone()[0],
                "locked": db.execute("SELECT COUNT(*) FROM protocols WHERE status='locked'").fetchone()[0],
                "completed": db.execute("SELECT COUNT(*) FROM protocols WHERE status='completed'").fetchone()[0],
                "independently_reviewed": db.execute("SELECT COUNT(DISTINCT study_id) FROM reviews WHERE independent=1 AND decision='approved'").fetchone()[0],
            }
