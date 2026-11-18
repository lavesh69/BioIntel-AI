from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from .paths import engine_home


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class EngineStateStore:
    def __init__(self, path: str | Path | None = None, *, user_data: str | Path | None = None) -> None:
        self.path = Path(path).resolve() if path else engine_home(user_data) / "engine-platform.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")
            try:
                yield connection
            finally:
                connection.close()

    def _initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS engine_state (
                    engine TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    backend TEXT NOT NULL DEFAULT '',
                    version TEXT NOT NULL DEFAULT '',
                    executable TEXT NOT NULL DEFAULT '',
                    executable_sha256 TEXT NOT NULL DEFAULT '',
                    pack_id TEXT NOT NULL DEFAULT '',
                    qualified INTEGER NOT NULL DEFAULT 0,
                    last_probe_utc TEXT NOT NULL DEFAULT '',
                    message TEXT NOT NULL DEFAULT '',
                    updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qualification_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    engine TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    sha256 TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_engine_evidence ON qualification_evidence(engine, evidence_type);
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    engine TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL,
                    state TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    finished_at_utc TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS imported_packs (
                    pack_id TEXT PRIMARY KEY,
                    pack_version TEXT NOT NULL,
                    manifest_sha256 TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    imported_at_utc TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                """
            )

    def upsert_engine(self, engine: str, **values: Any) -> None:
        allowed = {"state", "backend", "version", "executable", "executable_sha256", "pack_id", "qualified", "last_probe_utc", "message"}
        invalid = set(values) - allowed
        if invalid:
            raise ValueError("Unsupported engine-state fields: " + ", ".join(sorted(invalid)))
        current = self.get_engine(engine) or {
            "engine": engine,
            "state": "not-installed",
            "backend": "",
            "version": "",
            "executable": "",
            "executable_sha256": "",
            "pack_id": "",
            "qualified": 0,
            "last_probe_utc": "",
            "message": "",
        }
        current.update(values)
        current["qualified"] = int(bool(current.get("qualified")))
        current["updated_at_utc"] = utc_now()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO engine_state(engine,state,backend,version,executable,executable_sha256,pack_id,qualified,last_probe_utc,message,updated_at_utc)
                VALUES(:engine,:state,:backend,:version,:executable,:executable_sha256,:pack_id,:qualified,:last_probe_utc,:message,:updated_at_utc)
                ON CONFLICT(engine) DO UPDATE SET
                    state=excluded.state, backend=excluded.backend, version=excluded.version,
                    executable=excluded.executable, executable_sha256=excluded.executable_sha256,
                    pack_id=excluded.pack_id, qualified=excluded.qualified,
                    last_probe_utc=excluded.last_probe_utc, message=excluded.message,
                    updated_at_utc=excluded.updated_at_utc
                """,
                current,
            )
            connection.execute("COMMIT")

    def get_engine(self, engine: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM engine_state WHERE engine=?", (engine,)).fetchone()
        return dict(row) if row else None

    def inventory(self) -> pd.DataFrame:
        with self.connection() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM engine_state ORDER BY engine")]
        return pd.DataFrame(rows)

    def record_evidence(self, engine: str, evidence_type: str, status: str, *, sha256: str = "", details: dict[str, Any] | None = None) -> None:
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO qualification_evidence(engine,evidence_type,status,sha256,details_json,created_at_utc) VALUES(?,?,?,?,?,?)",
                (engine, evidence_type, status, sha256, json.dumps(details or {}, sort_keys=True), utc_now()),
            )

    def evidence(self, engine: str | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM qualification_evidence"
        params: tuple[Any, ...] = ()
        if engine:
            sql += " WHERE engine=?"
            params = (engine,)
        sql += " ORDER BY id DESC"
        with self.connection() as connection:
            rows = [dict(row) for row in connection.execute(sql, params)]
        return pd.DataFrame(rows)

    def start_operation(self, operation_id: str, action: str, *, engine: str = "", request: dict[str, Any] | None = None) -> None:
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO operations(operation_id,engine,action,state,request_json,created_at_utc) VALUES(?,?,?,?,?,?)",
                (operation_id, engine, action, "running", json.dumps(request or {}, sort_keys=True), utc_now()),
            )

    def finish_operation(self, operation_id: str, state: str, result: dict[str, Any] | None = None) -> None:
        with self.connection() as connection:
            connection.execute(
                "UPDATE operations SET state=?,result_json=?,finished_at_utc=? WHERE operation_id=?",
                (state, json.dumps(result or {}, sort_keys=True), utc_now(), operation_id),
            )

    def operations(self, limit: int = 200) -> pd.DataFrame:
        with self.connection() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM operations ORDER BY created_at_utc DESC LIMIT ?", (max(1, min(limit, 2000)),))]
        return pd.DataFrame(rows)

    def register_pack(self, pack_id: str, pack_version: str, manifest_sha256: str, path: str, status: str, details: dict[str, Any]) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO imported_packs(pack_id,pack_version,manifest_sha256,path,status,imported_at_utc,details_json)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(pack_id) DO UPDATE SET pack_version=excluded.pack_version,manifest_sha256=excluded.manifest_sha256,path=excluded.path,status=excluded.status,imported_at_utc=excluded.imported_at_utc,details_json=excluded.details_json
                """,
                (pack_id, pack_version, manifest_sha256, path, status, utc_now(), json.dumps(details, sort_keys=True)),
            )

    def packs(self) -> pd.DataFrame:
        with self.connection() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM imported_packs ORDER BY imported_at_utc DESC")]
        return pd.DataFrame(rows)

    def set_setting(self, key: str, value: Any) -> None:
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO settings(key,value_json,updated_at_utc) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at_utc=excluded.updated_at_utc",
                (key, json.dumps(value, sort_keys=True), utc_now()),
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connection() as connection:
            row = connection.execute("SELECT value_json FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def integrity_check(self) -> dict[str, Any]:
        with self.connection() as connection:
            value = connection.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {row[0]: int(row[1]) for row in connection.execute("SELECT 'engine_state', COUNT(*) FROM engine_state UNION ALL SELECT 'qualification_evidence', COUNT(*) FROM qualification_evidence UNION ALL SELECT 'operations', COUNT(*) FROM operations UNION ALL SELECT 'imported_packs', COUNT(*) FROM imported_packs")}
        return {"status": "passed" if value == "ok" else "failed", "sqlite_integrity": value, "tables": tables, "path": str(self.path)}
