import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def get_exam_db_path(root_dir: Optional[str] = None) -> str:
    if root_dir is None:
        root_dir = os.getcwd()
    user_data = os.path.join(root_dir, "UserData", "databases")
    os.makedirs(user_data, exist_ok=True)
    return os.path.join(user_data, "biointel_examination.sqlite")


def init_exam_db(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS exam_sessions (
        exam_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        subject TEXT NOT NULL,
        duration_minutes INTEGER DEFAULT 60,
        total_questions INTEGER DEFAULT 20,
        passing_score REAL DEFAULT 70.0,
        proctoring_enabled INTEGER DEFAULT 0,
        questions JSON,
        created_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS exam_submissions (
        submission_id TEXT PRIMARY KEY,
        exam_id TEXT NOT NULL,
        candidate_id TEXT NOT NULL,
        candidate_name TEXT NOT NULL,
        answers JSON,
        score REAL,
        passed INTEGER,
        submitted_at TEXT,
        proctoring_logs JSON,
        FOREIGN KEY(exam_id) REFERENCES exam_sessions(exam_id)
    )
    """)
    conn.commit()
    conn.close()


class ExaminationService:
    def __init__(self, root_dir: Optional[str] = None):
        self.db_path = get_exam_db_path(root_dir)
        init_exam_db(self.db_path)

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def create_exam(
        self,
        title: str,
        subject: str,
        duration: int,
        questions: List[Dict[str, Any]],
        passing_score: float = 70.0,
        proctoring_enabled: bool = False,
    ) -> Dict[str, Any]:
        if not title.strip() or not subject.strip() or int(duration) <= 0:
            raise ValueError("Title, subject and a positive duration are required.")
        if not 0 <= float(passing_score) <= 100:
            raise ValueError("Passing score must be between 0 and 100.")
        now = datetime.now(timezone.utc).isoformat()
        eid = f"exm_{int(datetime.now().timestamp() * 1000)}"
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO exam_sessions (exam_id,title,subject,duration_minutes,total_questions,passing_score,proctoring_enabled,questions,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    eid,
                    title.strip(),
                    subject.strip(),
                    int(duration),
                    len(questions),
                    float(passing_score),
                    int(proctoring_enabled),
                    json.dumps(questions),
                    now,
                ),
            )
        return {
            "exam_id": eid,
            "title": title.strip(),
            "subject": subject.strip(),
            "duration_minutes": int(duration),
            "passing_score": float(passing_score),
            "proctoring_enabled": bool(proctoring_enabled),
        }

    def list_exams(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT exam_id, title, subject, duration_minutes, total_questions, questions, created_at FROM exam_sessions ORDER BY created_at DESC"
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "exam_id": r[0],
                "title": r[1],
                "subject": r[2],
                "duration_minutes": r[3],
                "total_questions": r[4],
                "questions": json.loads(r[5]) if r[5] else [],
                "created_at": r[6],
            }
            for r in rows
        ]

    def submit_exam(
        self,
        exam_id: str,
        candidate_id: str,
        candidate_name: str,
        answers: Dict[str, Any],
        score: float,
    ) -> Dict[str, Any]:
        conn = self._get_conn()
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        sub_id = f"sub_{exam_id}_{candidate_id}"
        row = cur.execute(
            "SELECT passing_score FROM exam_sessions WHERE exam_id=?", (exam_id,)
        ).fetchone()
        if row is None:
            conn.close()
            raise ValueError("Examination not found.")
        passed = 1 if float(score) >= float(row[0]) else 0
        cur.execute(
            """
            INSERT INTO exam_submissions (submission_id, exam_id, candidate_id, candidate_name, answers, score, passed, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(submission_id) DO UPDATE SET answers=excluded.answers, score=excluded.score, passed=excluded.passed
        """,
            (
                sub_id,
                exam_id,
                candidate_id,
                candidate_name,
                json.dumps(answers),
                score,
                passed,
                now,
            ),
        )
        conn.commit()
        conn.close()
        return {
            "submission_id": sub_id,
            "score": score,
            "passed": bool(passed),
            "submitted_at": now,
        }
