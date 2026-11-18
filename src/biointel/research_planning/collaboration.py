from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from biointel.database.core import managed_connect


class PlanningCollaborationStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        con = managed_connect(self.path, timeout=20)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=20000")
        return con

    def _init(self) -> None:
        with closing(self._connect()) as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS planning_threads (
                    thread_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module_key TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('Open','Resolved','Reopened')),
                    due_date TEXT,
                    created_by TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS planning_comments (
                    comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER NOT NULL REFERENCES planning_threads(thread_id) ON DELETE CASCADE,
                    author TEXT NOT NULL,
                    body TEXT NOT NULL,
                    mention TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS planning_change_requests (
                    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module_key TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    proposed_by TEXT NOT NULL,
                    proposal TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    decision TEXT NOT NULL CHECK(decision IN ('Pending','Accepted','Rejected')),
                    decided_by TEXT NOT NULL,
                    decision_reason TEXT NOT NULL,
                    conflict_of_interest TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    decided_at_utc TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_planning_threads_module ON planning_threads(module_key,status);
                """
            )
            con.commit()

    def create_thread(self, module_key: str, entity_id: str, title: str, created_by: str, due_date: str | None = None) -> int:
        if not all(str(value).strip() for value in (module_key, entity_id, title, created_by)):
            raise ValueError("Module, entity, title and creator are required.")
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as con:
            cur = con.execute(
                "INSERT INTO planning_threads(module_key,entity_id,title,status,due_date,created_by,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?)",
                (module_key.strip(), entity_id.strip(), title.strip(), "Open", due_date, created_by.strip(), now, now),
            )
            con.commit()
            return int(cur.lastrowid)

    def add_comment(self, thread_id: int, author: str, body: str, mention: str = "") -> int:
        if not author.strip() or not body.strip():
            raise ValueError("Comment author and body are required.")
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as con:
            exists = con.execute("SELECT thread_id FROM planning_threads WHERE thread_id=?", (int(thread_id),)).fetchone()
            if not exists:
                raise ValueError("Unknown collaboration thread.")
            cur = con.execute(
                "INSERT INTO planning_comments(thread_id,author,body,mention,created_at_utc) VALUES(?,?,?,?,?)",
                (int(thread_id), author.strip(), body.strip(), mention.strip(), now),
            )
            con.execute("UPDATE planning_threads SET updated_at_utc=? WHERE thread_id=?", (now, int(thread_id)))
            con.commit()
            return int(cur.lastrowid)

    def set_thread_status(self, thread_id: int, status: str) -> None:
        if status not in {"Open", "Resolved", "Reopened"}:
            raise ValueError("Unsupported thread status.")
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as con:
            cur = con.execute("UPDATE planning_threads SET status=?,updated_at_utc=? WHERE thread_id=?", (status, now, int(thread_id)))
            if cur.rowcount != 1:
                raise ValueError("Unknown collaboration thread.")
            con.commit()

    def propose_change(self, module_key: str, entity_id: str, proposed_by: str, proposal: str, rationale: str, conflict_of_interest: str = "None declared") -> int:
        if not all(str(value).strip() for value in (module_key, entity_id, proposed_by, proposal, rationale)):
            raise ValueError("Change request fields cannot be blank.")
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as con:
            cur = con.execute(
                """INSERT INTO planning_change_requests(module_key,entity_id,proposed_by,proposal,rationale,decision,decided_by,decision_reason,conflict_of_interest,created_at_utc)
                VALUES(?,?,?,?,?,'Pending','','',?,?)""",
                (module_key.strip(), entity_id.strip(), proposed_by.strip(), proposal.strip(), rationale.strip(), conflict_of_interest.strip(), now),
            )
            con.commit()
            return int(cur.lastrowid)

    def decide_change(self, request_id: int, decision: str, decided_by: str, reason: str) -> None:
        if decision not in {"Accepted", "Rejected"}:
            raise ValueError("Decision must be Accepted or Rejected.")
        if not decided_by.strip() or not reason.strip():
            raise ValueError("Decision reviewer and reason are required.")
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as con:
            cur = con.execute(
                "UPDATE planning_change_requests SET decision=?,decided_by=?,decision_reason=?,decided_at_utc=? WHERE request_id=? AND decision='Pending'",
                (decision, decided_by.strip(), reason.strip(), now, int(request_id)),
            )
            if cur.rowcount != 1:
                raise ValueError("Change request is unknown or already decided.")
            con.commit()

    def threads(self, module_key: str | None = None) -> pd.DataFrame:
        query = "SELECT * FROM planning_threads"
        params: tuple[object, ...] = ()
        if module_key:
            query += " WHERE module_key=?"
            params = (module_key,)
        query += " ORDER BY updated_at_utc DESC"
        with closing(self._connect()) as con:
            rows = con.execute(query, params).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def comments(self, thread_id: int) -> pd.DataFrame:
        with closing(self._connect()) as con:
            rows = con.execute("SELECT * FROM planning_comments WHERE thread_id=? ORDER BY comment_id", (int(thread_id),)).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def change_requests(self, module_key: str | None = None) -> pd.DataFrame:
        query = "SELECT * FROM planning_change_requests"
        params: tuple[object, ...] = ()
        if module_key:
            query += " WHERE module_key=?"
            params = (module_key,)
        query += " ORDER BY request_id DESC"
        with closing(self._connect()) as con:
            rows = con.execute(query, params).fetchall()
        return pd.DataFrame([dict(row) for row in rows])
