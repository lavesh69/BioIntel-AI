from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from biointel.database.core import managed_connect


class AssumptionRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        con = managed_connect(self.path, timeout=20)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=20000")
        return con

    def _init(self) -> None:
        with closing(self._connect()) as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS planning_assumptions (
                    assumption_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module_key TEXT NOT NULL,
                    name TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    sensitivity_low REAL,
                    sensitivity_high REAL,
                    impacted_modules TEXT NOT NULL,
                    evidence_uri TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    UNIQUE(module_key,name)
                );
                CREATE TABLE IF NOT EXISTS assumption_audit (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    assumption_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                """
            )
            con.commit()

    def upsert(
        self,
        module_key: str,
        name: str,
        value: Any,
        unit: str = "",
        source: str = "",
        confidence: str = "Moderate",
        owner: str = "Local owner",
        sensitivity_low: float | None = None,
        sensitivity_high: float | None = None,
        impacted_modules: tuple[str, ...] = (),
        evidence_uri: str = "",
        status: str = "Active",
    ) -> int:
        if not module_key.strip() or not name.strip():
            raise ValueError("Assumptions require module_key and name.")
        if confidence not in {"Low", "Moderate", "High"}:
            raise ValueError("Confidence must be Low, Moderate or High.")
        if sensitivity_low is not None and sensitivity_high is not None and sensitivity_low > sensitivity_high:
            raise ValueError("Sensitivity low cannot exceed sensitivity high.")
        now = datetime.now(timezone.utc).isoformat()
        value_json = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
        impacted = json.dumps(sorted(set(impacted_modules)), ensure_ascii=False)
        with closing(self._connect()) as con:
            con.execute(
                """
                INSERT INTO planning_assumptions(module_key,name,value_json,unit,source,confidence,owner,
                    sensitivity_low,sensitivity_high,impacted_modules,evidence_uri,status,updated_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(module_key,name) DO UPDATE SET
                    value_json=excluded.value_json, unit=excluded.unit, source=excluded.source,
                    confidence=excluded.confidence, owner=excluded.owner,
                    sensitivity_low=excluded.sensitivity_low, sensitivity_high=excluded.sensitivity_high,
                    impacted_modules=excluded.impacted_modules, evidence_uri=excluded.evidence_uri,
                    status=excluded.status, updated_at_utc=excluded.updated_at_utc
                """,
                (module_key.strip(), name.strip(), value_json, unit.strip(), source.strip(), confidence,
                 owner.strip() or "Local owner", sensitivity_low, sensitivity_high, impacted,
                 evidence_uri.strip(), status.strip() or "Active", now),
            )
            row = con.execute("SELECT assumption_id FROM planning_assumptions WHERE module_key=? AND name=?", (module_key.strip(), name.strip())).fetchone()
            assumption_id = int(row[0])
            con.execute(
                "INSERT INTO assumption_audit(assumption_id,action,payload_json,created_at_utc) VALUES(?,?,?,?)",
                (assumption_id, "upsert", value_json, now),
            )
            con.commit()
        return assumption_id

    def list(self, module_key: str | None = None) -> pd.DataFrame:
        query = "SELECT * FROM planning_assumptions"
        params: tuple[Any, ...] = ()
        if module_key:
            query += " WHERE module_key=?"
            params = (module_key,)
        query += " ORDER BY updated_at_utc DESC"
        with closing(self._connect()) as con:
            rows = con.execute(query, params).fetchall()
        frame = pd.DataFrame([dict(row) for row in rows])
        if not frame.empty:
            frame["value"] = frame["value_json"].map(json.loads)
            frame["impacted_modules_list"] = frame["impacted_modules"].map(json.loads)
        return frame

    def sensitivity_gaps(self) -> pd.DataFrame:
        with closing(self._connect()) as con:
            rows = con.execute(
                """
                SELECT * FROM planning_assumptions
                WHERE status='Active' AND (sensitivity_low IS NULL OR sensitivity_high IS NULL OR source='')
                ORDER BY confidence,updated_at_utc DESC
                """
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])
