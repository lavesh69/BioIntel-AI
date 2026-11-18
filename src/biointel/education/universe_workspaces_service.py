import os
import sqlite3
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

def get_universe_db_path(root_dir: Optional[str] = None) -> str:
    if root_dir is None:
        root_dir = os.getcwd()
    user_data = os.path.join(root_dir, "UserData", "databases")
    os.makedirs(user_data, exist_ok=True)
    return os.path.join(user_data, "biointel_universe_workspaces.sqlite")

def init_universe_db(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS universe_workspace_records (
        record_id TEXT PRIMARY KEY,
        module_key TEXT NOT NULL,
        title TEXT NOT NULL,
        category TEXT,
        status TEXT DEFAULT 'active',
        payload JSON NOT NULL,
        created_by TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """)
    conn.commit()
    conn.close()

class UniverseWorkspacesService:
    def __init__(self, root_dir: Optional[str] = None):
        self.db_path = get_universe_db_path(root_dir)
        init_universe_db(self.db_path)

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def save_record(self, module_key: str, title: str, payload: Dict[str, Any], record_id: Optional[str] = None, created_by: str = "User") -> Dict[str, Any]:
        conn = self._get_conn()
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        if not record_id:
            record_id = f"uv_{module_key}_{int(datetime.now().timestamp()*1000)}"
        cur.execute("""
            INSERT INTO universe_workspace_records (record_id, module_key, title, payload, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
                title=excluded.title,
                payload=excluded.payload,
                updated_at=excluded.updated_at
        """, (record_id, module_key, title, json.dumps(payload), created_by, now, now))
        conn.commit()
        conn.close()
        return {"record_id": record_id, "module_key": module_key, "title": title, "payload": payload, "updated_at": now}

    def list_records(self, module_key: str, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT record_id, module_key, title, category, status, payload, created_by, created_at, updated_at FROM universe_workspace_records WHERE module_key = ? ORDER BY updated_at DESC LIMIT ?", (module_key, limit))
        rows = cur.fetchall()
        conn.close()
        return [{
            "record_id": r[0], "module_key": r[1], "title": r[2], "category": r[3],
            "status": r[4], "payload": json.loads(r[5]) if r[5] else {}, "created_by": r[6], "created_at": r[7], "updated_at": r[8]
        } for r in rows]

    def delete_record(self, record_id: str) -> bool:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM universe_workspace_records WHERE record_id = ?", (record_id,))
        conn.commit()
        conn.close()
        return True
