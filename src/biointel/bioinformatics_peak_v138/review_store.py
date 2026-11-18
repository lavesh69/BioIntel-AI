from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterator
from uuid import uuid4

import numpy as np
import pandas as pd

from biointel.database.core import managed_connect


REVIEW_STATUSES = ("Needs review", "Accepted", "Rejected", "Needs confirmation", "Escalated")


@dataclass(frozen=True)
class RunSnapshot:
    run_id: str
    module_key: str
    created_at_utc: str
    input_sha256: str
    result_sha256: str
    row_count: int
    result_path: str
    summary: dict[str, Any]
    parameters: dict[str, Any]


class ReviewStore:
    def __init__(self, project_root: str | Path):
        project = Path(project_root).resolve()
        user_root = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or project / "UserData").resolve()
        self.root = user_root / "bioinformatics_peak_v139"
        self.root.mkdir(parents=True, exist_ok=True)
        self.runs_dir = self.root / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "scientific_review.sqlite3"
        self._initialise()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = managed_connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS run_snapshots (
                    run_id TEXT PRIMARY KEY,
                    module_key TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    input_sha256 TEXT NOT NULL,
                    result_sha256 TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    result_path TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    parameters_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_run_snapshots_module_time
                    ON run_snapshots(module_key, created_at_utc DESC);

                CREATE TABLE IF NOT EXISTS review_decisions (
                    decision_id TEXT PRIMARY KEY,
                    module_key TEXT NOT NULL,
                    run_id TEXT,
                    record_key TEXT NOT NULL,
                    record_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    note TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    UNIQUE(module_key, run_id, record_sha256),
                    FOREIGN KEY(run_id) REFERENCES run_snapshots(run_id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_review_decisions_module_status
                    ON review_decisions(module_key, status, updated_at_utc DESC);
                """
            )

    @staticmethod
    def frame_sha(frame: pd.DataFrame) -> str:
        canonical = frame.to_csv(index=False, lineterminator="\n", na_rep="<NA>").encode("utf-8")
        return sha256(canonical).hexdigest()

    @staticmethod
    def _json_value(value: Any) -> Any:
        if value is None or value is pd.NA:
            return None
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return None if not np.isfinite(value) else float(value)
        if isinstance(value, (np.bool_,)):
            return bool(value)
        if isinstance(value, (pd.Timestamp, datetime)):
            return value.isoformat()
        if pd.isna(value):
            return None
        return value

    @classmethod
    def canonical_record(cls, record: dict[str, Any]) -> tuple[str, str]:
        cleaned = {str(key): cls._json_value(value) for key, value in record.items()}
        payload = json.dumps(cleaned, sort_keys=True, separators=(",", ":"), default=str)
        return payload, sha256(payload.encode("utf-8")).hexdigest()

    def save_snapshot(
        self,
        *,
        module_key: str,
        input_sha256: str,
        result: pd.DataFrame,
        summary: dict[str, Any],
        parameters: dict[str, Any],
    ) -> RunSnapshot:
        if result.empty:
            raise ValueError("Cannot save an empty run snapshot.")
        run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:10]}"
        path = self.runs_dir / f"{run_id}.csv.gz"
        partial = path.with_suffix(path.suffix + ".partial")
        result.to_csv(partial, index=False, compression="gzip")
        partial.replace(path)
        snapshot = RunSnapshot(
            run_id=run_id,
            module_key=module_key,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            input_sha256=input_sha256,
            result_sha256=sha256(path.read_bytes()).hexdigest(),
            row_count=len(result),
            result_path=str(path),
            summary=dict(summary),
            parameters=dict(parameters),
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO run_snapshots(
                    run_id, module_key, created_at_utc, input_sha256, result_sha256,
                    row_count, result_path, summary_json, parameters_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.run_id,
                    snapshot.module_key,
                    snapshot.created_at_utc,
                    snapshot.input_sha256,
                    snapshot.result_sha256,
                    snapshot.row_count,
                    snapshot.result_path,
                    json.dumps(snapshot.summary, sort_keys=True, default=str),
                    json.dumps(snapshot.parameters, sort_keys=True, default=str),
                ),
            )
        return snapshot

    def list_snapshots(self, module_key: str, *, limit: int = 25) -> list[RunSnapshot]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM run_snapshots
                WHERE module_key=? ORDER BY created_at_utc DESC LIMIT ?
                """,
                (module_key, max(1, min(int(limit), 250))),
            ).fetchall()
        return [
            RunSnapshot(
                run_id=row["run_id"], module_key=row["module_key"], created_at_utc=row["created_at_utc"],
                input_sha256=row["input_sha256"], result_sha256=row["result_sha256"], row_count=int(row["row_count"]),
                result_path=row["result_path"], summary=json.loads(row["summary_json"]), parameters=json.loads(row["parameters_json"]),
            )
            for row in rows
        ]

    def load_snapshot_frame(self, run_id: str, *, maximum_rows: int = 250_000) -> pd.DataFrame:
        with self._connect() as connection:
            row = connection.execute("SELECT result_path, result_sha256 FROM run_snapshots WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        path = Path(row["result_path"]).resolve()
        try:
            path.relative_to(self.runs_dir.resolve())
        except ValueError as exc:
            raise ValueError("Stored run path is outside the protected run directory") from exc
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256(path.read_bytes()).hexdigest() != row["result_sha256"]:
            raise ValueError("Stored run snapshot checksum mismatch")
        return pd.read_csv(path, compression="gzip", nrows=max(1, min(int(maximum_rows), 250_000)), low_memory=False)

    def upsert_decision(
        self,
        *,
        module_key: str,
        record_key: str,
        record: dict[str, Any],
        status: str,
        reason: str,
        note: str = "",
        reviewer: str = "Local reviewer",
        run_id: str | None = None,
    ) -> dict[str, Any]:
        if status not in REVIEW_STATUSES:
            raise ValueError(f"Unsupported review status: {status}")
        reason = str(reason).strip()[:500]
        note = str(note).strip()[:5000]
        reviewer = str(reviewer).strip()[:200] or "Local reviewer"
        if not reason:
            raise ValueError("A review reason is required.")
        record_json, record_sha = self.canonical_record(record)
        now = datetime.now(timezone.utc).isoformat()
        decision_id = f"decision-{uuid4().hex}"
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT decision_id, created_at_utc FROM review_decisions
                WHERE module_key=? AND run_id IS ? AND record_sha256=?
                """,
                (module_key, run_id, record_sha),
            ).fetchone()
            if existing:
                decision_id = existing["decision_id"]
                created_at = existing["created_at_utc"]
                connection.execute(
                    """
                    UPDATE review_decisions SET record_key=?, status=?, reason=?, note=?, reviewer=?,
                        record_json=?, updated_at_utc=? WHERE decision_id=?
                    """,
                    (record_key, status, reason, note, reviewer, record_json, now, decision_id),
                )
            else:
                created_at = now
                connection.execute(
                    """
                    INSERT INTO review_decisions(
                        decision_id, module_key, run_id, record_key, record_sha256, status,
                        reason, note, reviewer, record_json, created_at_utc, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (decision_id, module_key, run_id, record_key, record_sha, status, reason, note, reviewer, record_json, now, now),
                )
        return {
            "decision_id": decision_id,
            "module_key": module_key,
            "run_id": run_id,
            "record_key": record_key,
            "record_sha256": record_sha,
            "status": status,
            "reason": reason,
            "note": note,
            "reviewer": reviewer,
            "created_at_utc": created_at,
            "updated_at_utc": now,
        }

    def decisions(self, module_key: str, *, status: str | None = None, limit: int = 1000) -> pd.DataFrame:
        query = "SELECT * FROM review_decisions WHERE module_key=?"
        parameters: list[Any] = [module_key]
        if status:
            if status not in REVIEW_STATUSES:
                raise ValueError(status)
            query += " AND status=?"
            parameters.append(status)
        query += " ORDER BY updated_at_utc DESC LIMIT ?"
        parameters.append(max(1, min(int(limit), 10_000)))
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        records = [dict(row) for row in rows]
        return pd.DataFrame(records)

    def summary(self, module_key: str) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS records FROM review_decisions WHERE module_key=? GROUP BY status",
                (module_key,),
            ).fetchall()
        counts = {status: 0 for status in REVIEW_STATUSES}
        counts.update({row["status"]: int(row["records"]) for row in rows})
        return counts

    def snapshot_dict(self, snapshot: RunSnapshot) -> dict[str, Any]:
        return asdict(snapshot)


__all__ = ["REVIEW_STATUSES", "ReviewStore", "RunSnapshot"]
