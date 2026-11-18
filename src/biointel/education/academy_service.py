import os
import sqlite3
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

def get_academy_db_path(root_dir: Optional[str] = None) -> str:
    if root_dir is None:
        root_dir = os.getcwd()
    user_data = os.path.join(root_dir, "UserData", "databases")
    os.makedirs(user_data, exist_ok=True)
    return os.path.join(user_data, "biointel_academy.sqlite")

def init_academy_db(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS academy_courses (
        course_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        category TEXT,
        instructor TEXT,
        description TEXT,
        modules JSON,
        enrolled_count INTEGER DEFAULT 0,
        rating REAL DEFAULT 4.9,
        created_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS academy_enrollments (
        enrollment_id TEXT PRIMARY KEY,
        course_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        progress_pct REAL DEFAULT 0.0,
        certificate_issued INTEGER DEFAULT 0,
        certificate_hash TEXT,
        completed_at TEXT,
        created_at TEXT,
        FOREIGN KEY(course_id) REFERENCES academy_courses(course_id)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS lecture_media (
        lecture_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        media_path TEXT,
        duration_sec INTEGER,
        transcript TEXT,
        chapters JSON,
        published INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()

class AcademyService:
    def __init__(self, root_dir: Optional[str] = None):
        self.db_path = get_academy_db_path(root_dir)
        init_academy_db(self.db_path)

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def add_course(self, title: str, category: str, instructor: str, description: str, modules: List[Dict[str, Any]]) -> Dict[str, Any]:
        conn = self._get_conn()
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cid = f"crs_{int(datetime.now().timestamp()*1000)}"
        cur.execute("INSERT INTO academy_courses (course_id, title, category, instructor, description, modules, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (cid, title, category, instructor, description, json.dumps(modules), now))
        conn.commit()
        conn.close()
        return {"course_id": cid, "title": title, "category": category, "instructor": instructor}

    def list_courses(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT course_id, title, category, instructor, description, modules, enrolled_count, rating, created_at FROM academy_courses ORDER BY created_at DESC")
        rows = cur.fetchall()
        conn.close()
        return [{
            "course_id": r[0], "title": r[1], "category": r[2], "instructor": r[3],
            "description": r[4], "modules": json.loads(r[5]) if r[5] else [], "enrolled_count": r[6], "rating": r[7], "created_at": r[8]
        } for r in rows]

    def enroll_user(self, course_id: str, user_id: str) -> Dict[str, Any]:
        conn = self._get_conn()
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        eid = f"enr_{course_id}_{user_id}"
        cur.execute("""
            INSERT INTO academy_enrollments (enrollment_id, course_id, user_id, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(enrollment_id) DO NOTHING
        """, (eid, course_id, user_id, now))
        inserted = cur.rowcount == 1
        if inserted:
            cur.execute(
                "UPDATE academy_courses SET enrolled_count = enrolled_count + 1 WHERE course_id = ?",
                (course_id,),
            )
        conn.commit()
        conn.close()
        return {"enrollment_id": eid, "course_id": course_id, "user_id": user_id, "progress_pct": 0.0}
