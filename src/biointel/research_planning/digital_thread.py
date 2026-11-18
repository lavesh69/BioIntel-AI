from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from biointel.database.core import managed_connect


@dataclass(frozen=True)
class ThreadNode:
    node_id: str
    node_type: str
    title: str
    module_key: str
    status: str = "Draft"
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class ThreadLink:
    source_id: str
    target_id: str
    relation: str
    required: bool = True


_ALLOWED_NODE_TYPES = {
    "research_question", "objective", "protocol", "population", "eligibility_rule", "endpoint",
    "estimand", "sample_size", "randomization", "visit", "biospecimen", "crf_variable",
    "analysis", "risk", "assumption", "milestone", "budget_item", "preregistration", "evidence_gap",
    "ethics_requirement", "data_asset", "monitoring_event", "dissemination_output",
    "ethics_plan", "data_management_plan", "monitoring_plan", "publication_plan",
}
_ALLOWED_STATUSES = {"Draft", "Reviewed", "Locked", "Superseded", "Retracted", "Needs review"}


class ResearchDigitalThreadStore:
    """SQLite-backed cross-module planning graph with immutable audit events."""

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
                CREATE TABLE IF NOT EXISTS thread_nodes (
                    node_id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    module_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS thread_links (
                    source_id TEXT NOT NULL REFERENCES thread_nodes(node_id) ON DELETE CASCADE,
                    target_id TEXT NOT NULL REFERENCES thread_nodes(node_id) ON DELETE CASCADE,
                    relation TEXT NOT NULL,
                    required INTEGER NOT NULL DEFAULT 1 CHECK(required IN (0,1)),
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY(source_id, target_id, relation)
                );
                CREATE TABLE IF NOT EXISTS thread_audit (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    module_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_thread_nodes_module ON thread_nodes(module_key, node_type);
                CREATE INDEX IF NOT EXISTS idx_thread_links_target ON thread_links(target_id);
                """
            )
            con.commit()

    @staticmethod
    def stable_node_id(module_key: str, node_type: str, title: str) -> str:
        raw = f"{module_key}|{node_type}|{title.strip().casefold()}".encode("utf-8")
        return f"rpn_{sha256(raw).hexdigest()[:24]}"

    @staticmethod
    def _payload(payload: dict[str, Any] | None) -> tuple[str, str]:
        text = json.dumps(payload or {}, sort_keys=True, default=str, ensure_ascii=False)
        return text, sha256(text.encode("utf-8")).hexdigest()

    def upsert_node(self, node: ThreadNode) -> str:
        if node.node_type not in _ALLOWED_NODE_TYPES:
            raise ValueError(f"Unsupported research-thread node type: {node.node_type}")
        if node.status not in _ALLOWED_STATUSES:
            raise ValueError(f"Unsupported research-thread status: {node.status}")
        node_id = node.node_id.strip() or self.stable_node_id(node.module_key, node.node_type, node.title)
        if not node.title.strip() or not node.module_key.strip():
            raise ValueError("Thread nodes require a title and module key.")
        payload_json, payload_hash = self._payload(node.payload)
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as con:
            con.execute(
                """
                INSERT INTO thread_nodes(node_id,node_type,title,module_key,status,payload_json,payload_sha256,updated_at_utc)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(node_id) DO UPDATE SET
                    node_type=excluded.node_type,
                    title=excluded.title,
                    module_key=excluded.module_key,
                    status=excluded.status,
                    payload_json=excluded.payload_json,
                    payload_sha256=excluded.payload_sha256,
                    updated_at_utc=excluded.updated_at_utc
                """,
                (node_id, node.node_type, node.title.strip(), node.module_key.strip(), node.status, payload_json, payload_hash, now),
            )
            con.execute(
                "INSERT INTO thread_audit(event_type,entity_id,module_key,payload_json,created_at_utc) VALUES(?,?,?,?,?)",
                ("node_upsert", node_id, node.module_key, payload_json, now),
            )
            con.commit()
        return node_id

    def link(self, link: ThreadLink) -> None:
        if not link.relation.strip():
            raise ValueError("Thread links require a relation.")
        if link.source_id == link.target_id:
            raise ValueError("A thread node cannot link to itself.")
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as con:
            exists = con.execute(
                "SELECT node_id FROM thread_nodes WHERE node_id IN (?,?)", (link.source_id, link.target_id)
            ).fetchall()
            if len(exists) != 2:
                raise ValueError("Both source and target nodes must exist before linking.")
            con.execute(
                """
                INSERT INTO thread_links(source_id,target_id,relation,required,updated_at_utc)
                VALUES(?,?,?,?,?)
                ON CONFLICT(source_id,target_id,relation) DO UPDATE SET
                    required=excluded.required, updated_at_utc=excluded.updated_at_utc
                """,
                (link.source_id, link.target_id, link.relation.strip(), int(link.required), now),
            )
            con.execute(
                "INSERT INTO thread_audit(event_type,entity_id,module_key,payload_json,created_at_utc) VALUES(?,?,?,?,?)",
                ("link_upsert", f"{link.source_id}->{link.target_id}", "research_planning", json.dumps(link.__dict__, sort_keys=True), now),
            )
            con.commit()

    def bulk_upsert(self, nodes: Iterable[ThreadNode], links: Iterable[ThreadLink] = ()) -> None:
        for node in nodes:
            self.upsert_node(node)
        for link in links:
            self.link(link)

    def nodes(self, module_key: str | None = None) -> pd.DataFrame:
        query = "SELECT * FROM thread_nodes"
        params: tuple[Any, ...] = ()
        if module_key:
            query += " WHERE module_key=?"
            params = (module_key,)
        query += " ORDER BY updated_at_utc DESC, node_type, title"
        with closing(self._connect()) as con:
            rows = con.execute(query, params).fetchall()
        data = [dict(row) for row in rows]
        frame = pd.DataFrame(data)
        if not frame.empty:
            frame["payload"] = frame["payload_json"].map(lambda value: json.loads(value or "{}"))
        return frame

    def links(self) -> pd.DataFrame:
        with closing(self._connect()) as con:
            rows = con.execute(
                """
                SELECT l.*, s.title AS source_title, s.node_type AS source_type,
                       t.title AS target_title, t.node_type AS target_type
                FROM thread_links l
                JOIN thread_nodes s ON s.node_id=l.source_id
                JOIN thread_nodes t ON t.node_id=l.target_id
                ORDER BY l.updated_at_utc DESC
                """
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def audit(self, limit: int = 500) -> pd.DataFrame:
        safe_limit = max(1, min(int(limit), 5000))
        with closing(self._connect()) as con:
            rows = con.execute(
                "SELECT * FROM thread_audit ORDER BY event_id DESC LIMIT ?", (safe_limit,)
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def orphan_report(self) -> pd.DataFrame:
        """Find required planning entities with no incoming or outgoing links."""
        with closing(self._connect()) as con:
            rows = con.execute(
                """
                SELECT n.node_id,n.node_type,n.title,n.module_key,n.status,
                       COUNT(DISTINCT o.target_id) AS outgoing_links,
                       COUNT(DISTINCT i.source_id) AS incoming_links
                FROM thread_nodes n
                LEFT JOIN thread_links o ON o.source_id=n.node_id
                LEFT JOIN thread_links i ON i.target_id=n.node_id
                GROUP BY n.node_id
                HAVING outgoing_links=0 AND incoming_links=0
                ORDER BY n.node_type,n.title
                """
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def impact_candidates(self, node_id: str, max_depth: int = 5) -> pd.DataFrame:
        """Return downstream nodes that may need revalidation after a node changes."""
        max_depth = max(1, min(int(max_depth), 10))
        with closing(self._connect()) as con:
            rows = con.execute(
                """
                WITH RECURSIVE downstream(node_id, depth, path) AS (
                    SELECT target_id, 1, source_id || '>' || target_id
                    FROM thread_links WHERE source_id=?
                    UNION ALL
                    SELECT l.target_id, d.depth+1, d.path || '>' || l.target_id
                    FROM thread_links l
                    JOIN downstream d ON l.source_id=d.node_id
                    WHERE d.depth < ? AND instr(d.path, l.target_id)=0
                )
                SELECT d.node_id, MIN(d.depth) AS impact_depth, n.node_type, n.title,
                       n.module_key, n.status
                FROM downstream d JOIN thread_nodes n ON n.node_id=d.node_id
                GROUP BY d.node_id ORDER BY impact_depth,n.module_key,n.title
                """,
                (node_id, max_depth),
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])
