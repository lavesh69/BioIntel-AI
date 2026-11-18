import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def get_education_db_path(root_dir: Optional[str] = None) -> str:
    if root_dir is None:
        root_dir = os.getcwd()
    user_data = os.path.join(root_dir, "UserData", "databases")
    os.makedirs(user_data, exist_ok=True)
    return os.path.join(user_data, "biointel_education.sqlite")


def init_education_db(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS edu_institutions (
        institution_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        code TEXT UNIQUE,
        country TEXT,
        website TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS edu_classes (
        class_id TEXT PRIMARY KEY,
        institution_id TEXT NOT NULL,
        name TEXT NOT NULL,
        academic_year TEXT,
        department TEXT,
        teacher_in_charge TEXT,
        student_count INTEGER DEFAULT 0,
        created_at TEXT,
        FOREIGN KEY(institution_id) REFERENCES edu_institutions(institution_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS edu_students (
        student_id TEXT PRIMARY KEY,
        class_id TEXT NOT NULL,
        name TEXT NOT NULL,
        email TEXT,
        roll_number TEXT,
        guardian_name TEXT,
        guardian_contact TEXT,
        enrolled_at TEXT,
        FOREIGN KEY(class_id) REFERENCES edu_classes(class_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS edu_attendance (
        record_id TEXT PRIMARY KEY,
        class_id TEXT NOT NULL,
        student_id TEXT NOT NULL,
        date TEXT NOT NULL,
        status TEXT NOT NULL,
        remarks TEXT,
        marked_by TEXT,
        created_at TEXT,
        FOREIGN KEY(student_id) REFERENCES edu_students(student_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS edu_assignments (
        assignment_id TEXT PRIMARY KEY,
        class_id TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        due_date TEXT,
        total_marks INTEGER DEFAULT 100,
        rubric JSON,
        created_by TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS edu_submissions (
        submission_id TEXT PRIMARY KEY,
        assignment_id TEXT NOT NULL,
        student_id TEXT NOT NULL,
        submitted_at TEXT,
        content TEXT,
        attachment_urls JSON,
        score REAL,
        feedback TEXT,
        status TEXT DEFAULT 'submitted',
        FOREIGN KEY(assignment_id) REFERENCES edu_assignments(assignment_id),
        FOREIGN KEY(student_id) REFERENCES edu_students(student_id)
    )
    """)

    conn.commit()
    conn.close()


class ClassroomService:
    def __init__(self, root_dir: Optional[str] = None):
        self.db_path = get_education_db_path(root_dir)
        init_education_db(self.db_path)

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def list_classes(self) -> List[Dict[str, Any]]:
        return self.get_classes()

    def get_classes(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT class_id, institution_id, name, academic_year, department, teacher_in_charge, student_count, created_at FROM edu_classes ORDER BY name ASC"
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "class_id": r[0],
                "institution_id": r[1],
                "name": r[2],
                "academic_year": r[3],
                "department": r[4],
                "teacher_in_charge": r[5],
                "student_count": r[6],
                "created_at": r[7],
            }
            for r in rows
        ]

    def add_class(
        self,
        name: str,
        academic_year: str,
        department: str,
        teacher: str,
        institution_id: str = "inst_main",
    ) -> Dict[str, Any]:
        if not name.strip() or not institution_id.strip():
            raise ValueError("Class name and institution ID are required.")
        now = datetime.now(timezone.utc).isoformat()
        cid = f"cls_{int(datetime.now().timestamp() * 1000)}"
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO edu_institutions(institution_id,name,code,country,website,created_at) VALUES(?,?,?,?,?,?)",
                (institution_id, "Local institution", institution_id, "", "", now),
            )
            conn.execute(
                "INSERT INTO edu_classes (class_id,institution_id,name,academic_year,department,teacher_in_charge,created_at) VALUES(?,?,?,?,?,?,?)",
                (cid, institution_id, name.strip(), academic_year, department, teacher, now),
            )
        return {
            "class_id": cid,
            "institution_id": institution_id,
            "name": name.strip(),
            "department": department,
            "teacher_in_charge": teacher,
        }

    def mark_attendance(
        self, class_id: str, student_id: str, date_str: str, status: str, remarks: str = ""
    ) -> bool:
        conn = self._get_conn()
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        rec_id = f"att_{student_id}_{date_str}"
        cur.execute(
            """
            INSERT INTO edu_attendance (record_id, class_id, student_id, date, status, remarks, marked_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET status=excluded.status, remarks=excluded.remarks
        """,
            (rec_id, class_id, student_id, date_str, status, remarks, "Teacher", now),
        )
        conn.commit()
        conn.close()
        return True

    def get_attendance_report(self, class_id: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT record_id, class_id, student_id, date, status, remarks FROM edu_attendance WHERE class_id = ? ORDER BY date DESC",
            (class_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "record_id": r[0],
                "class_id": r[1],
                "student_id": r[2],
                "date": r[3],
                "status": r[4],
                "remarks": r[5],
            }
            for r in rows
        ]

    def create_assignment(
        self, class_id: str, title: str, description: str, due_date: str, total_marks: int = 100
    ) -> Dict[str, Any]:
        conn = self._get_conn()
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        aid = f"asg_{int(datetime.now().timestamp() * 1000)}"
        cur.execute(
            "INSERT INTO edu_assignments (assignment_id, class_id, title, description, due_date, total_marks, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (aid, class_id, title, description, due_date, total_marks, now),
        )
        conn.commit()
        conn.close()
        return {
            "assignment_id": aid,
            "title": title,
            "due_date": due_date,
            "total_marks": total_marks,
        }

    def get_assignments(self, class_id: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT assignment_id, class_id, title, description, due_date, total_marks, created_at FROM edu_assignments WHERE class_id = ? ORDER BY created_at DESC",
            (class_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "assignment_id": r[0],
                "class_id": r[1],
                "title": r[2],
                "description": r[3],
                "due_date": r[4],
                "total_marks": r[5],
                "created_at": r[6],
            }
            for r in rows
        ]
