import os
import sqlite3
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

def get_intelligence_db_path(root_dir: Optional[str] = None) -> str:
    if root_dir is None:
        root_dir = os.getcwd()
    user_data = os.path.join(root_dir, "UserData", "databases")
    os.makedirs(user_data, exist_ok=True)
    return os.path.join(user_data, "biointel_intelligence_hub.sqlite")

def init_intelligence_db(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS intelligence_alerts (
        alert_id TEXT PRIMARY KEY,
        student_id TEXT NOT NULL,
        student_name TEXT NOT NULL,
        risk_level TEXT NOT NULL,
        reason_code TEXT NOT NULL,
        metrics JSON,
        status TEXT DEFAULT 'pending_review',
        assigned_to TEXT,
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()

class IntelligenceHubService:
    def __init__(self, root_dir: Optional[str] = None):
        self.db_path = get_intelligence_db_path(root_dir)
        init_intelligence_db(self.db_path)

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def get_summary_metrics(self) -> Dict[str, Any]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(
            """SELECT COUNT(DISTINCT student_id), COUNT(*), MAX(created_at)
               FROM intelligence_alerts
               WHERE status IN ('pending_review','assigned','in_progress')"""
        )
        student_count, alert_count, last_activity = cur.fetchone()
        conn.close()
        return {
            "total_students": int(student_count or 0),
            "overall_attendance_pct": None,
            "average_assignment_score": None,
            "at_risk_students_count": int(alert_count or 0),
            "data_lineage": "Persistent intelligence_alerts records; attendance and assignment metrics require the canonical institution-scoped Education Intelligence workspace.",
            "last_updated": last_activity,
            "state": "ready" if last_activity else "empty",
        }

    def list_alerts(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT alert_id, student_id, student_name, risk_level, reason_code, metrics, status, assigned_to, created_at FROM intelligence_alerts ORDER BY created_at DESC")
        rows = cur.fetchall()
        conn.close()
        return [{
            "alert_id": r[0], "student_id": r[1], "student_name": r[2], "risk_level": r[3],
            "reason_code": r[4], "metrics": json.loads(r[5]) if r[5] else {}, "status": r[6], "assigned_to": r[7], "created_at": r[8]
        } for r in rows]
