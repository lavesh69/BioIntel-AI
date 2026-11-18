from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from biointel.database.core import managed_connect


class PlanningReviewStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        connection = managed_connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def _init(self) -> None:
        with closing(self._connect()) as con:
            con.executescript('''
            CREATE TABLE IF NOT EXISTS planning_reviews (
                module_key TEXT NOT NULL,
                record_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                note TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                PRIMARY KEY (module_key, record_id)
            );
            CREATE TABLE IF NOT EXISTS planning_versions (
                version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_key TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('Draft','Reviewed','Locked','Superseded','Retracted')),
                payload_sha256 TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_planning_versions_module ON planning_versions(module_key, version_id DESC);
            ''')
            con.commit()

    def upsert_review(self, module_key: str, record_id: str, decision: str, reviewer: str, note: str) -> None:
        allowed = {'Needs review','Accepted','Rejected','Needs confirmation','Escalated'}
        if decision not in allowed:
            raise ValueError('Unsupported review decision.')
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as con:
            con.execute('''
            INSERT INTO planning_reviews(module_key, record_id, decision, reviewer, note, updated_at_utc)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(module_key, record_id) DO UPDATE SET
              decision=excluded.decision, reviewer=excluded.reviewer,
              note=excluded.note, updated_at_utc=excluded.updated_at_utc
            ''', (module_key, str(record_id), decision, reviewer.strip() or 'Local reviewer', note.strip(), now))
            con.commit()

    def reviews(self, module_key: str) -> pd.DataFrame:
        with closing(self._connect()) as con:
            rows = con.execute('SELECT * FROM planning_reviews WHERE module_key=? ORDER BY updated_at_utc DESC', (module_key,)).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def save_version(self, module_key: str, status: str, payload_sha256: str, payload: dict[str, Any], reviewer: str, reason: str) -> int:
        if status not in {'Draft','Reviewed','Locked','Superseded','Retracted'}:
            raise ValueError('Unsupported plan status.')
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as con:
            cursor = con.execute('''INSERT INTO planning_versions(module_key,status,payload_sha256,payload_json,reviewer,reason,created_at_utc)
            VALUES(?,?,?,?,?,?,?)''', (module_key,status,payload_sha256,json.dumps(payload,sort_keys=True,default=str),reviewer.strip() or 'Local reviewer',reason.strip(),now))
            con.commit()
            return int(cursor.lastrowid)

    def versions(self, module_key: str) -> pd.DataFrame:
        with closing(self._connect()) as con:
            rows = con.execute('SELECT version_id,module_key,status,payload_sha256,reviewer,reason,created_at_utc FROM planning_versions WHERE module_key=? ORDER BY version_id DESC', (module_key,)).fetchall()
        return pd.DataFrame([dict(row) for row in rows])
