from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from .phase6 import EducationPhase6Service
from .platform import Conflict, Denied, EducationError, Missing, ident, now, parse_time

MIGRATION_ID = "education_phase7_desktop_workflows_v1"

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS education_identity_accounts(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 user_id TEXT NOT NULL,
 display_name TEXT NOT NULL DEFAULT '',
 email TEXT NOT NULL DEFAULT '',
 pin_salt TEXT NOT NULL,
 pin_hash TEXT NOT NULL,
 failed_attempts INTEGER NOT NULL DEFAULT 0,
 locked_until TEXT,
 state TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,user_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_education_identity_email
 ON education_identity_accounts(institution_id,email) WHERE email<>'';
CREATE TABLE IF NOT EXISTS education_desktop_sessions(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 user_id TEXT NOT NULL,
 token_hash TEXT NOT NULL UNIQUE,
 device_label TEXT NOT NULL DEFAULT 'BioIntel Desktop',
 state TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL,
 last_seen_at TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_education_sessions_user
 ON education_desktop_sessions(institution_id,user_id,state,expires_at);
CREATE TABLE IF NOT EXISTS education_lecture_chapters(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 lecture_id TEXT NOT NULL REFERENCES lectures(id),
 title TEXT NOT NULL,
 start_seconds REAL NOT NULL DEFAULT 0,
 position INTEGER NOT NULL DEFAULT 0,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(lecture_id,position)
);
CREATE TABLE IF NOT EXISTS education_lecture_notes(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 lecture_id TEXT NOT NULL REFERENCES lectures(id),
 user_id TEXT NOT NULL,
 position_seconds REAL NOT NULL DEFAULT 0,
 body TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_lecture_bookmarks(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 lecture_id TEXT NOT NULL REFERENCES lectures(id),
 user_id TEXT NOT NULL,
 position_seconds REAL NOT NULL DEFAULT 0,
 label TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 UNIQUE(lecture_id,user_id,position_seconds)
);
CREATE TABLE IF NOT EXISTS education_assignment_rubrics(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 assignment_id TEXT NOT NULL REFERENCES assignments(id),
 title TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(assignment_id)
);
CREATE TABLE IF NOT EXISTS education_rubric_criteria(
 id TEXT PRIMARY KEY,
 rubric_id TEXT NOT NULL REFERENCES education_assignment_rubrics(id),
 title TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 max_marks REAL NOT NULL,
 position INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_rubric_scores(
 id TEXT PRIMARY KEY,
 rubric_id TEXT NOT NULL REFERENCES education_assignment_rubrics(id),
 criterion_id TEXT NOT NULL REFERENCES education_rubric_criteria(id),
 submission_id TEXT NOT NULL REFERENCES submissions(id),
 grader_id TEXT NOT NULL,
 marks REAL NOT NULL,
 feedback TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(submission_id,criterion_id)
);
CREATE TABLE IF NOT EXISTS education_lecture_transcripts(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 lecture_id TEXT NOT NULL REFERENCES lectures(id),
 language TEXT NOT NULL DEFAULT 'English',
 body TEXT NOT NULL,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(lecture_id,language)
);
CREATE TABLE IF NOT EXISTS education_exam_thresholds(
 exam_id TEXT PRIMARY KEY REFERENCES examinations(id),
 passing_percent REAL NOT NULL DEFAULT 40,
 updated_by TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_exam_moderation_events(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 exam_id TEXT NOT NULL REFERENCES examinations(id),
 session_id TEXT REFERENCES education_exam_sessions(id),
 event_type TEXT NOT NULL,
 actor_id TEXT NOT NULL,
 reason TEXT NOT NULL DEFAULT '',
 detail_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL
);
INSERT OR IGNORE INTO education_migrations(id,applied_at)
 VALUES('education_phase7_desktop_workflows_v1',datetime('now'));
"""

ADMIN_ROLES = {
    "platform_administrator", "institution_administrator", "principal", "dean",
    "registrar", "department_head", "examination_controller",
}
TEACHER_ROLES = {
    "subject_teacher", "class_teacher", "lecturer", "professor", "assistant_professor",
    "teaching_assistant", "laboratory_instructor", "academic_mentor", "class_coordinator",
}
ATTENDANCE_STATES = {"present", "absent", "late", "excused"}


def _pin_hash(pin: str, salt_hex: str) -> str:
    return hashlib.scrypt(
        pin.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32
    ).hex()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class EducationPhase7Service(EducationPhase6Service):
    """Desktop-first application workflows layered over Phase 6 without removing legacy paths."""

    def __init__(self, platform: Any, *, root: Any = None):
        super().__init__(platform, root=root)
        self.migrate_phase7()

    def migrate_phase7(self) -> str:
        with self.db.connection() as db:
            db.executescript(SCHEMA)
        return MIGRATION_ID

    def _roles(self, actor: str, institution_id: str) -> set[str]:
        return {str(row["role"]) for row in self.platform._require(actor, institution_id)}

    def _staff_subject(self, actor: str, institution_id: str, subject_id: str) -> None:
        roles = self._roles(actor, institution_id)
        if roles & ADMIN_ROLES:
            return
        if not roles & TEACHER_ROLES:
            raise Denied("Teaching access required.")
        assigned = self.platform._one(
            "SELECT id FROM teacher_assignments WHERE institution_id=? AND subject_id=? AND teacher_id=? AND state='active'",
            (institution_id, subject_id, actor),
        )
        if not assigned:
            raise Denied("Teacher is not assigned to this subject.")

    # ---------- local desktop identity and sessions ----------
    def identity_accounts(self, institution_id: str) -> list[dict[str, Any]]:
        return self.platform._all(
            "SELECT id,institution_id,user_id,display_name,email,state,failed_attempts,locked_until,created_at,updated_at "
            "FROM education_identity_accounts WHERE institution_id=? ORDER BY display_name,user_id",
            (institution_id,),
        )

    def enroll_identity(
        self,
        actor: str,
        institution_id: str,
        user_id: str,
        pin: str,
        *,
        display_name: str = "",
        email: str = "",
    ) -> dict[str, Any]:
        roles = self._roles(actor, institution_id)
        target = str(user_id).strip()
        if actor != target and not roles & ADMIN_ROLES:
            raise Denied("Only an administrator can enroll another identity.")
        if not self.platform.membership(target, institution_id):
            raise Denied("The identity must have an active institution membership.")
        pin_text = str(pin)
        if len(pin_text) < 6 or len(pin_text) > 64 or pin_text.isdigit() and len(set(pin_text)) < 3:
            raise EducationError("Use a 6-64 character PIN/passphrase that is not repetitive.")
        mail = str(email).strip().lower()
        if mail and ("@" not in mail or len(mail) > 240):
            raise EducationError("Enter a valid email address.")
        salt = secrets.token_hex(16)
        digest = _pin_hash(pin_text, salt)
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_identity_accounts
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,user_id) DO UPDATE SET
                display_name=excluded.display_name,email=excluded.email,pin_salt=excluded.pin_salt,
                pin_hash=excluded.pin_hash,failed_attempts=0,locked_until=NULL,state='active',updated_at=excluded.updated_at""",
                (
                    ident("acct"), institution_id, target, str(display_name).strip()[:160], mail,
                    salt, digest, 0, None, "active", stamp, stamp,
                ),
            )
        self.platform._audit(actor, "desktop_identity_enrolled", "user", target, institution_id, {"email": mail})
        return self.platform._one(
            "SELECT id,institution_id,user_id,display_name,email,state FROM education_identity_accounts WHERE institution_id=? AND user_id=?",
            (institution_id, target),
        )

    def authenticate(
        self,
        institution_id: str,
        login: str,
        pin: str,
        *,
        device_label: str = "BioIntel Desktop",
        hours: int = 12,
    ) -> dict[str, Any]:
        key = str(login).strip().lower()
        row = self.platform._one(
            "SELECT * FROM education_identity_accounts WHERE institution_id=? AND state='active' AND (lower(user_id)=? OR lower(email)=?)",
            (institution_id, key, key),
        )
        if not row:
            raise Denied("Invalid sign-in credentials.")
        current = datetime.now(timezone.utc)
        if row.get("locked_until") and parse_time(row["locked_until"]) > current:
            raise Conflict("Account is temporarily locked after repeated failed sign-ins.")
        valid = hmac.compare_digest(str(row["pin_hash"]), _pin_hash(str(pin), str(row["pin_salt"])))
        if not valid:
            attempts = int(row.get("failed_attempts") or 0) + 1
            locked_until = (current + timedelta(minutes=15)).isoformat() if attempts >= 5 else None
            with self.db.connection() as db:
                db.execute(
                    "UPDATE education_identity_accounts SET failed_attempts=?,locked_until=?,updated_at=? WHERE id=?",
                    (attempts, locked_until, now(), row["id"]),
                )
            raise Denied("Invalid sign-in credentials.")
        if not self.platform.membership(row["user_id"], institution_id):
            raise Denied("Institution membership is not active.")
        token = secrets.token_urlsafe(40)
        stamp = now()
        expires = (current + timedelta(hours=max(1, min(int(hours), 72)))).isoformat()
        with self.db.connection() as db:
            db.execute(
                "UPDATE education_identity_accounts SET failed_attempts=0,locked_until=NULL,updated_at=? WHERE id=?",
                (stamp, row["id"]),
            )
            db.execute(
                "INSERT INTO education_desktop_sessions VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    ident("session"), institution_id, row["user_id"], _token_hash(token),
                    str(device_label).strip()[:120] or "BioIntel Desktop", "active", stamp, stamp, expires, None,
                ),
            )
        self.platform._audit(row["user_id"], "desktop_sign_in", "session", "local", institution_id, {"device": device_label})
        return {
            "token": token,
            "institution_id": institution_id,
            "user_id": row["user_id"],
            "display_name": row.get("display_name") or row["user_id"],
            "expires_at": expires,
        }

    def validate_session(self, token: str) -> dict[str, Any]:
        row = self.platform._one(
            "SELECT s.*,a.display_name,a.email FROM education_desktop_sessions s "
            "LEFT JOIN education_identity_accounts a ON a.institution_id=s.institution_id AND a.user_id=s.user_id "
            "WHERE s.token_hash=?",
            (_token_hash(str(token)),),
        )
        if not row or row["state"] != "active" or row.get("revoked_at"):
            raise Denied("Desktop session is not active.")
        if parse_time(row["expires_at"]) <= datetime.now(timezone.utc):
            with self.db.connection() as db:
                db.execute("UPDATE education_desktop_sessions SET state='expired' WHERE id=?", (row["id"],))
            raise Denied("Desktop session has expired.")
        if not self.platform.membership(row["user_id"], row["institution_id"]):
            raise Denied("Institution membership is no longer active.")
        with self.db.connection() as db:
            db.execute("UPDATE education_desktop_sessions SET last_seen_at=? WHERE id=?", (now(), row["id"]))
        row.pop("token_hash", None)
        return row

    def sessions(self, actor: str, institution_id: str) -> list[dict[str, Any]]:
        self._roles(actor, institution_id)
        return self.platform._all(
            "SELECT id,device_label,state,created_at,last_seen_at,expires_at,revoked_at FROM education_desktop_sessions "
            "WHERE institution_id=? AND user_id=? ORDER BY created_at DESC",
            (institution_id, actor),
        )

    def revoke_session(self, actor: str, institution_id: str, session_id: str) -> dict[str, Any]:
        row = self.platform._one(
            "SELECT * FROM education_desktop_sessions WHERE id=? AND institution_id=? AND user_id=?",
            (session_id, institution_id, actor),
        )
        if not row:
            raise Missing("Session not found.")
        with self.db.connection() as db:
            db.execute(
                "UPDATE education_desktop_sessions SET state='revoked',revoked_at=? WHERE id=?",
                (now(), session_id),
            )
        return self.platform._one("SELECT * FROM education_desktop_sessions WHERE id=?", (session_id,))

    # ---------- timetable planner ----------
    def update_timetable_entry(
        self,
        actor: str,
        institution_id: str,
        entry_id: str,
        *,
        starts_at: str,
        ends_at: str,
        teacher_id: str,
        student_group: str,
        room: str,
        meeting_id: str = "",
    ) -> dict[str, Any]:
        entry = self.platform._one("SELECT * FROM timetable_entries WHERE id=? AND institution_id=?", (entry_id, institution_id))
        if not entry:
            raise Missing("Timetable entry not found.")
        self._staff_subject(actor, institution_id, entry["subject_id"])
        start, end = parse_time(starts_at), parse_time(ends_at)
        if end <= start:
            raise EducationError("End must follow start.")
        clash = self.platform._one(
            """SELECT id FROM timetable_entries WHERE institution_id=? AND id<>? AND state='scheduled'
            AND starts_at<? AND ends_at>? AND (teacher_id=? OR room=? OR student_group=?)""",
            (institution_id, entry_id, end.isoformat(), start.isoformat(), teacher_id, room, student_group),
        )
        if clash:
            raise Conflict("Teacher, room or student-group timetable conflict.")
        with self.db.connection() as db:
            db.execute(
                """UPDATE timetable_entries SET teacher_id=?,student_group=?,room=?,starts_at=?,ends_at=?,meeting_id=?,updated_at=?
                WHERE id=?""",
                (teacher_id, student_group, room, start.isoformat(), end.isoformat(), meeting_id, now(), entry_id),
            )
        self.platform._audit(actor, "timetable_entry_updated", "timetable_entry", entry_id, institution_id, {"starts_at": start.isoformat(), "ends_at": end.isoformat()})
        return self.platform._one("SELECT * FROM timetable_entries WHERE id=?", (entry_id,))

    def cancel_timetable_entry(self, actor: str, institution_id: str, entry_id: str, reason: str) -> dict[str, Any]:
        entry = self.platform._one("SELECT * FROM timetable_entries WHERE id=? AND institution_id=?", (entry_id, institution_id))
        if not entry:
            raise Missing("Timetable entry not found.")
        self._staff_subject(actor, institution_id, entry["subject_id"])
        if not str(reason).strip():
            raise EducationError("A cancellation reason is required.")
        with self.db.connection() as db:
            db.execute("UPDATE timetable_entries SET state='cancelled',updated_at=? WHERE id=?", (now(), entry_id))
        self.platform._audit(actor, "timetable_entry_cancelled", "timetable_entry", entry_id, institution_id, {"reason": str(reason)[:1000]})
        return self.platform._one("SELECT * FROM timetable_entries WHERE id=?", (entry_id,))

    # ---------- attendance and gradebook editors ----------
    def attendance_roster(self, actor: str, institution_id: str, subject_id: str, session_id: str | None = None) -> dict[str, Any]:
        self._staff_subject(actor, institution_id, subject_id)
        students = self.platform._all(
            "SELECT student_id FROM enrollments WHERE institution_id=? AND subject_id=? AND state='active' ORDER BY student_id",
            (institution_id, subject_id),
        )
        records: dict[str, dict[str, Any]] = {}
        session = None
        if session_id:
            session = self.platform._one(
                "SELECT * FROM attendance_sessions WHERE id=? AND institution_id=? AND subject_id=?",
                (session_id, institution_id, subject_id),
            )
            if not session:
                raise Missing("Attendance session not found.")
            records = {
                row["student_id"]: row
                for row in self.platform._all("SELECT * FROM attendance_records WHERE session_id=?", (session_id,))
            }
        rows = [
            {
                "student_id": row["student_id"],
                "status": records.get(row["student_id"], {}).get("status", "present"),
                "note": records.get(row["student_id"], {}).get("note", ""),
            }
            for row in students
        ]
        return {"session": session, "rows": rows}

    def save_attendance_roster(self, actor: str, session_id: str, rows: list[dict[str, Any]], *, lock: bool = False) -> dict[str, Any]:
        session = self.platform._one("SELECT * FROM attendance_sessions WHERE id=?", (session_id,))
        if not session:
            raise Missing("Attendance session not found.")
        self._staff_subject(actor, session["institution_id"], session["subject_id"])
        if session["state"] != "open":
            raise Conflict("Attendance session is locked.")
        valid_students = {
            row["student_id"] for row in self.platform._all(
                "SELECT student_id FROM enrollments WHERE subject_id=? AND state='active'", (session["subject_id"],)
            )
        }
        normalized = []
        for item in rows:
            student_id = str(item.get("student_id", ""))
            status = str(item.get("status", "present")).lower()
            if student_id not in valid_students:
                raise Denied("Attendance row contains a non-enrolled student.")
            if status not in ATTENDANCE_STATES:
                raise EducationError("Invalid attendance state.")
            normalized.append((student_id, status, str(item.get("note", ""))[:500]))
        stamp = now()
        with self.db.connection() as db:
            for student_id, status, note in normalized:
                db.execute(
                    """INSERT INTO attendance_records VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(session_id,student_id) DO UPDATE SET status=excluded.status,note=excluded.note,
                    marked_by=excluded.marked_by,updated_at=excluded.updated_at""",
                    (ident("attr"), session["institution_id"], session_id, student_id, status, note, actor, stamp, stamp),
                )
            if lock:
                db.execute("UPDATE attendance_sessions SET state='locked',updated_at=? WHERE id=?", (stamp, session_id))
        self.platform._audit(actor, "attendance_roster_saved", "attendance_session", session_id, session["institution_id"], {"rows": len(normalized), "locked": bool(lock)})
        return self.attendance_roster(actor, session["institution_id"], session["subject_id"], session_id)

    def editable_gradebook(self, actor: str, institution_id: str, subject_id: str) -> dict[str, Any]:
        self._staff_subject(actor, institution_id, subject_id)
        assignments = self.platform._all(
            "SELECT id,title,max_marks,due_at FROM assignments WHERE institution_id=? AND subject_id=? AND state='published' ORDER BY due_at",
            (institution_id, subject_id),
        )
        rows = self.platform._all(
            """SELECT s.id submission_id,s.student_id,s.assignment_id,s.state submission_state,s.late,
            a.title assignment_title,a.max_marks,g.id grade_id,g.marks,g.feedback,g.updated_at grade_updated_at
            FROM submissions s JOIN assignments a ON a.id=s.assignment_id
            LEFT JOIN grades g ON g.submission_id=s.id
            WHERE s.institution_id=? AND a.subject_id=? AND s.state='submitted'
            ORDER BY a.due_at,s.student_id""",
            (institution_id, subject_id),
        )
        return {"assignments": assignments, "rows": rows}

    def save_gradebook_rows(self, actor: str, institution_id: str, rows: list[dict[str, Any]], *, reason: str = "Bulk gradebook update") -> dict[str, Any]:
        self._roles(actor, institution_id)
        updated = 0
        skipped = 0
        for item in rows:
            submission_id = str(item.get("submission_id", ""))
            if not submission_id or item.get("marks") in (None, ""):
                skipped += 1
                continue
            current = self.platform._one(
                "SELECT g.marks,g.feedback FROM submissions s LEFT JOIN grades g ON g.submission_id=s.id WHERE s.id=? AND s.institution_id=?",
                (submission_id, institution_id),
            )
            if not current:
                raise Missing("Submission not found in this institution.")
            marks = float(item["marks"])
            feedback = str(item.get("feedback", ""))[:4000]
            if current.get("marks") is not None and float(current["marks"]) == marks and str(current.get("feedback") or "") == feedback:
                skipped += 1
                continue
            self.platform.grade_submission(actor, submission_id, marks, feedback, reason if current.get("marks") is not None else "")
            updated += 1
        return {"updated": updated, "skipped": skipped}

    def assignment_board(self, actor: str, institution_id: str, subject_id: str | None = None) -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "classroom.view")
        args: list[Any] = [institution_id]
        where = ""
        if subject_id:
            where = " AND a.subject_id=?"
            args.append(subject_id)
        rows = self.platform._all(
            f"""SELECT a.*,s.code subject_code,
            COUNT(sub.id) submission_count,
            SUM(CASE WHEN sub.state='submitted' THEN 1 ELSE 0 END) submitted_count,
            SUM(CASE WHEN sub.late=1 THEN 1 ELSE 0 END) late_count,
            SUM(CASE WHEN g.id IS NOT NULL THEN 1 ELSE 0 END) graded_count,
            AVG(CASE WHEN g.id IS NOT NULL THEN (g.marks/a.max_marks)*100 END) average_percent
            FROM assignments a LEFT JOIN subjects s ON s.id=a.subject_id
            LEFT JOIN submissions sub ON sub.assignment_id=a.id
            LEFT JOIN grades g ON g.submission_id=sub.id
            WHERE a.institution_id=? {where} GROUP BY a.id ORDER BY a.due_at""",
            tuple(args),
        )
        current = datetime.now(timezone.utc)
        buckets: dict[str, list[dict[str, Any]]] = {key: [] for key in ["draft", "published", "due_soon", "submitted", "late", "under_review", "graded"]}
        for row in rows:
            due = parse_time(row["due_at"])
            if row["state"] == "draft":
                bucket = "draft"
            elif int(row.get("late_count") or 0) > 0:
                bucket = "late"
            elif int(row.get("submission_count") or 0) and int(row.get("graded_count") or 0) >= int(row.get("submitted_count") or 0):
                bucket = "graded"
            elif int(row.get("submitted_count") or 0) > 0:
                bucket = "under_review"
            elif current <= due <= current + timedelta(days=3):
                bucket = "due_soon"
            else:
                bucket = "published"
            buckets[bucket].append(row)
        return {"buckets": buckets, "rows": rows}

    # ---------- assignment rubrics ----------
    def save_assignment_rubric(self, actor: str, assignment_id: str, title: str, criteria: list[dict[str, Any]]) -> dict[str, Any]:
        assignment = self.platform._one("SELECT * FROM assignments WHERE id=?", (assignment_id,))
        if not assignment:
            raise Missing("Assignment not found.")
        self._staff_subject(actor, assignment["institution_id"], assignment["subject_id"])
        clean = []
        for position, item in enumerate(criteria):
            name = str(item.get("title", "")).strip()
            marks = float(item.get("max_marks") or 0)
            if not name or marks <= 0:
                raise EducationError("Each rubric criterion requires a title and positive maximum marks.")
            clean.append({"title": name[:200], "description": str(item.get("description", ""))[:2000], "max_marks": marks, "position": position})
        if not clean:
            raise EducationError("At least one rubric criterion is required.")
        total = sum(item["max_marks"] for item in clean)
        if abs(total - float(assignment["max_marks"])) > 1e-6:
            raise Conflict("Rubric criterion marks must total the assignment maximum marks.")
        existing = self.platform._one("SELECT * FROM education_assignment_rubrics WHERE assignment_id=?", (assignment_id,))
        rubric_id = existing["id"] if existing else ident("rubric")
        stamp = now()
        with self.db.connection() as db:
            if existing:
                db.execute("UPDATE education_assignment_rubrics SET title=?,state='active',updated_at=? WHERE id=?", (str(title).strip()[:200] or assignment["title"], stamp, rubric_id))
                db.execute("DELETE FROM education_rubric_criteria WHERE rubric_id=?", (rubric_id,))
            else:
                db.execute("INSERT INTO education_assignment_rubrics VALUES(?,?,?,?,?,?,?,?)", (rubric_id, assignment["institution_id"], assignment_id, str(title).strip()[:200] or assignment["title"], "active", actor, stamp, stamp))
            for item in clean:
                db.execute("INSERT INTO education_rubric_criteria VALUES(?,?,?,?,?,?,?,?)", (ident("criterion"), rubric_id, item["title"], item["description"], item["max_marks"], item["position"], stamp, stamp))
        self.platform._audit(actor, "assignment_rubric_saved", "assignment", assignment_id, assignment["institution_id"], {"criteria": len(clean), "max_marks": total})
        return self.assignment_rubric(actor, assignment_id)

    def assignment_rubric(self, actor: str, assignment_id: str) -> dict[str, Any]:
        assignment = self.platform._one("SELECT * FROM assignments WHERE id=?", (assignment_id,))
        if not assignment:
            raise Missing("Assignment not found.")
        self._roles(actor, assignment["institution_id"])
        rubric = self.platform._one("SELECT * FROM education_assignment_rubrics WHERE assignment_id=? AND state='active'", (assignment_id,))
        criteria = self.platform._all("SELECT * FROM education_rubric_criteria WHERE rubric_id=? ORDER BY position", (rubric["id"],)) if rubric else []
        return {"assignment": assignment, "rubric": rubric, "criteria": criteria}

    def grade_with_rubric(self, actor: str, submission_id: str, scores: list[dict[str, Any]], *, overall_feedback: str = "", reason: str = "") -> dict[str, Any]:
        submission = self.platform._one("SELECT s.*,a.subject_id,a.max_marks FROM submissions s JOIN assignments a ON a.id=s.assignment_id WHERE s.id=?", (submission_id,))
        if not submission:
            raise Missing("Submission not found.")
        self._staff_subject(actor, submission["institution_id"], submission["subject_id"])
        rubric_data = self.assignment_rubric(actor, submission["assignment_id"])
        rubric = rubric_data["rubric"]
        if not rubric:
            raise Missing("Assignment rubric not found.")
        criteria = {row["id"]: row for row in rubric_data["criteria"]}
        provided = {str(item.get("criterion_id")): item for item in scores}
        if set(provided) != set(criteria):
            raise Conflict("Rubric grading must include every criterion exactly once.")
        total = 0.0
        stamp = now()
        normalized = []
        for criterion_id, criterion in criteria.items():
            item = provided[criterion_id]
            marks = float(item.get("marks") or 0)
            if not 0 <= marks <= float(criterion["max_marks"]):
                raise EducationError("Rubric score is outside the criterion range.")
            total += marks
            normalized.append((criterion_id, marks, str(item.get("feedback", ""))[:2000]))
        existing_grade = self.platform._one("SELECT id FROM grades WHERE submission_id=?", (submission_id,))
        self.platform.grade_submission(actor, submission_id, total, overall_feedback, reason if existing_grade else "")
        with self.db.connection() as db:
            for criterion_id, marks, feedback in normalized:
                db.execute(
                    """INSERT INTO education_rubric_scores VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(submission_id,criterion_id) DO UPDATE SET marks=excluded.marks,feedback=excluded.feedback,
                    grader_id=excluded.grader_id,updated_at=excluded.updated_at""",
                    (ident("rscore"), rubric["id"], criterion_id, submission_id, actor, marks, feedback, stamp, stamp),
                )
        return {"submission_id": submission_id, "total_marks": total, "max_marks": submission["max_marks"], "criteria": len(normalized)}

    # ---------- academy desktop workspace ----------
    def curriculum(self, actor: str, course_id: str) -> dict[str, Any]:
        course = self.platform._one("SELECT * FROM courses WHERE id=?", (course_id,))
        if not course:
            raise Missing("Course not found.")
        roles = self._roles(actor, course["institution_id"])
        enrolled = self.platform._one("SELECT id FROM academy_enrollments WHERE course_id=? AND student_id=? AND state='active'", (course_id, actor))
        if actor != course["educator_id"] and not roles & ADMIN_ROLES and not enrolled:
            raise Denied("Course access denied.")
        sections = self.platform._all("SELECT * FROM course_sections WHERE course_id=? ORDER BY position,created_at", (course_id,))
        lectures = self.platform._all("SELECT * FROM lectures WHERE course_id=? ORDER BY created_at", (course_id,))
        return {"course": course, "sections": sections, "lectures": lectures}

    def create_course_section(self, actor: str, course_id: str, title: str, *, section_type: str = "section", parent_id: str | None = None, position: int = 0) -> dict[str, Any]:
        course = self.platform._one("SELECT * FROM courses WHERE id=?", (course_id,))
        if not course:
            raise Missing("Course not found.")
        roles = self._roles(actor, course["institution_id"])
        if actor != course["educator_id"] and not roles & ADMIN_ROLES:
            raise Denied("Course editing access denied.")
        if section_type not in {"section", "lesson", "assessment", "resource"}:
            raise EducationError("Unsupported curriculum item type.")
        stamp = now()
        sid = ident("section")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO course_sections VALUES(?,?,?,?,?,?,?,?)",
                (sid, course_id, parent_id, section_type, str(title).strip()[:200], int(position), stamp, stamp),
            )
        return self.platform._one("SELECT * FROM course_sections WHERE id=?", (sid,))

    def reorder_course_sections(self, actor: str, course_id: str, ordered_ids: list[str]) -> dict[str, Any]:
        course = self.platform._one("SELECT * FROM courses WHERE id=?", (course_id,))
        if not course:
            raise Missing("Course not found.")
        roles = self._roles(actor, course["institution_id"])
        if actor != course["educator_id"] and not roles & ADMIN_ROLES:
            raise Denied("Course editing access denied.")
        existing = {row["id"] for row in self.platform._all("SELECT id FROM course_sections WHERE course_id=?", (course_id,))}
        if set(ordered_ids) != existing:
            raise Conflict("Curriculum reorder must include every current item exactly once.")
        with self.db.connection() as db:
            for position, section_id in enumerate(ordered_ids):
                db.execute("UPDATE course_sections SET position=?,updated_at=? WHERE id=?", (position, now(), section_id))
        return self.curriculum(actor, course_id)

    def lecture_chapters(self, actor: str, lecture_id: str) -> list[dict[str, Any]]:
        lecture = self.platform._one("SELECT * FROM lectures WHERE id=?", (lecture_id,))
        if not lecture:
            raise Missing("Lecture not found.")
        self._roles(actor, lecture["institution_id"])
        return self.platform._all("SELECT * FROM education_lecture_chapters WHERE lecture_id=? ORDER BY start_seconds,position", (lecture_id,))

    def add_lecture_chapter(self, actor: str, lecture_id: str, title: str, start_seconds: float) -> dict[str, Any]:
        lecture = self.platform._one("SELECT * FROM lectures WHERE id=?", (lecture_id,))
        if not lecture:
            raise Missing("Lecture not found.")
        roles = self._roles(actor, lecture["institution_id"])
        if actor != lecture["educator_id"] and not roles & ADMIN_ROLES:
            raise Denied("Lecture editing access denied.")
        start = max(0.0, float(start_seconds))
        if lecture.get("duration_seconds") and start > float(lecture["duration_seconds"]):
            raise EducationError("Chapter start exceeds lecture duration.")
        position_row = self.platform._one("SELECT COALESCE(MAX(position),-1)+1 n FROM education_lecture_chapters WHERE lecture_id=?", (lecture_id,)) or {"n": 0}
        stamp = now()
        cid = ident("chapter")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_lecture_chapters VALUES(?,?,?,?,?,?,?,?,?)",
                (cid, lecture["institution_id"], lecture_id, str(title).strip()[:200], start, int(position_row["n"]), actor, stamp, stamp),
            )
        return self.platform._one("SELECT * FROM education_lecture_chapters WHERE id=?", (cid,))

    def save_lecture_note(self, actor: str, lecture_id: str, body: str, *, position_seconds: float = 0) -> dict[str, Any]:
        lecture = self.platform._one("SELECT * FROM lectures WHERE id=?", (lecture_id,))
        if not lecture:
            raise Missing("Lecture not found.")
        self._roles(actor, lecture["institution_id"])
        if not str(body).strip():
            raise EducationError("Note text is required.")
        stamp = now()
        nid = ident("lnote")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_lecture_notes VALUES(?,?,?,?,?,?,?,?)",
                (nid, lecture["institution_id"], lecture_id, actor, max(0.0, float(position_seconds)), str(body).strip()[:8000], stamp, stamp),
            )
        return self.platform._one("SELECT * FROM education_lecture_notes WHERE id=?", (nid,))

    def lecture_notebook(self, actor: str, lecture_id: str) -> dict[str, Any]:
        lecture = self.platform._one("SELECT * FROM lectures WHERE id=?", (lecture_id,))
        if not lecture:
            raise Missing("Lecture not found.")
        self._roles(actor, lecture["institution_id"])
        notes = self.platform._all(
            "SELECT * FROM education_lecture_notes WHERE lecture_id=? AND user_id=? ORDER BY position_seconds,created_at",
            (lecture_id, actor),
        )
        bookmarks = self.platform._all(
            "SELECT * FROM education_lecture_bookmarks WHERE lecture_id=? AND user_id=? ORDER BY position_seconds",
            (lecture_id, actor),
        )
        return {"notes": notes, "bookmarks": bookmarks, "chapters": self.lecture_chapters(actor, lecture_id)}

    def add_lecture_bookmark(self, actor: str, lecture_id: str, position_seconds: float, label: str = "") -> dict[str, Any]:
        lecture = self.platform._one("SELECT * FROM lectures WHERE id=?", (lecture_id,))
        if not lecture:
            raise Missing("Lecture not found.")
        self._roles(actor, lecture["institution_id"])
        stamp = now()
        bid = ident("bookmark")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_lecture_bookmarks VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(lecture_id,user_id,position_seconds) DO UPDATE SET label=excluded.label""",
                (bid, lecture["institution_id"], lecture_id, actor, max(0.0, float(position_seconds)), str(label).strip()[:200], stamp),
            )
        return self.platform._one(
            "SELECT * FROM education_lecture_bookmarks WHERE lecture_id=? AND user_id=? AND position_seconds=?",
            (lecture_id, actor, max(0.0, float(position_seconds))),
        )

    def save_lecture_transcript(self, actor: str, lecture_id: str, body: str, *, language: str = "English") -> dict[str, Any]:
        lecture = self.platform._one("SELECT * FROM lectures WHERE id=?", (lecture_id,))
        if not lecture:
            raise Missing("Lecture not found.")
        roles = self._roles(actor, lecture["institution_id"])
        if actor != lecture["educator_id"] and not roles & ADMIN_ROLES:
            raise Denied("Lecture transcript editing access denied.")
        text = str(body).strip()
        if not text:
            raise EducationError("Transcript text is required.")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_lecture_transcripts VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(lecture_id,language) DO UPDATE SET body=excluded.body,created_by=excluded.created_by,updated_at=excluded.updated_at""",
                (ident("transcript"), lecture["institution_id"], lecture_id, str(language)[:80], text[:2_000_000], actor, stamp, stamp),
            )
        return self.platform._one("SELECT * FROM education_lecture_transcripts WHERE lecture_id=? AND language=?", (lecture_id, str(language)[:80]))

    def lecture_transcripts(self, actor: str, lecture_id: str) -> list[dict[str, Any]]:
        lecture = self.platform._one("SELECT * FROM lectures WHERE id=?", (lecture_id,))
        if not lecture:
            raise Missing("Lecture not found.")
        self._roles(actor, lecture["institution_id"])
        return self.platform._all("SELECT * FROM education_lecture_transcripts WHERE lecture_id=? ORDER BY language", (lecture_id,))

    # ---------- Shiro conversation lifecycle ----------
    def rename_conversation(self, actor: str, conversation_id: str, title: str) -> dict[str, Any]:
        conversation = self.conversation(actor, conversation_id)
        clean = str(title).strip()
        if not clean:
            raise EducationError("Conversation title is required.")
        with self.db.connection() as db:
            db.execute("UPDATE education_shiro_conversations SET title=?,updated_at=? WHERE id=?", (clean[:160], now(), conversation_id))
        return self.conversation(actor, conversation_id)

    def archive_conversation(self, actor: str, conversation_id: str) -> dict[str, Any]:
        conversation = self.conversation(actor, conversation_id)
        with self.db.connection() as db:
            db.execute("UPDATE education_shiro_conversations SET state='archived',updated_at=? WHERE id=?", (now(), conversation_id))
        conversation["state"] = "archived"
        return conversation

    def delete_conversation(self, actor: str, conversation_id: str) -> None:
        conversation = self.conversation(actor, conversation_id)
        with self.db.connection() as db:
            db.execute("DELETE FROM education_shiro_messages WHERE conversation_id=?", (conversation_id,))
            db.execute("DELETE FROM education_shiro_conversations WHERE id=?", (conversation_id,))
        self.platform._audit(actor, "shiro_conversation_deleted", "conversation", conversation_id, conversation["institution_id"], {})


    def set_exam_passing_percent(self, actor: str, exam_id: str, passing_percent: float) -> dict[str, Any]:
        exam = self.exams._exam(exam_id)
        self.permissions.require(actor, exam["institution_id"], "exam.monitor")
        value = float(passing_percent)
        if not 0 < value <= 100:
            raise EducationError("Passing percentage must be between 0 and 100.")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_exam_thresholds VALUES(?,?,?,?)
                ON CONFLICT(exam_id) DO UPDATE SET passing_percent=excluded.passing_percent,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
                (exam_id, value, actor, now()),
            )
        return self.platform._one("SELECT * FROM education_exam_thresholds WHERE exam_id=?", (exam_id,))

    def exam_analytics_phase7(self, actor: str, exam_id: str) -> dict[str, Any]:
        data = self.exam_analytics(actor, exam_id)
        threshold = self.platform._one("SELECT passing_percent FROM education_exam_thresholds WHERE exam_id=?", (exam_id,))
        passing_percent = float(threshold["passing_percent"]) if threshold else 40.0
        scores = [float(row["final_score"]) for row in data.get("scores", [])]
        max_marks = float(data["exam"].get("max_marks") or 0)
        pass_mark = max_marks * passing_percent / 100.0
        data["summary"]["pass_rate"] = round(sum(1 for value in scores if value >= pass_mark) / len(scores) * 100, 2) if scores else 0.0
        data["summary"]["passing_percent"] = passing_percent
        data["summary"]["pass_mark"] = pass_mark
        return data

    # ---------- examination moderation ----------
    def record_moderation_event(self, actor: str, exam_id: str, event_type: str, *, session_id: str | None = None, reason: str = "", detail: dict[str, Any] | None = None) -> dict[str, Any]:
        exam = self.exams._exam(exam_id)
        self.permissions.require(actor, exam["institution_id"], "exam.monitor")
        if event_type not in {"review_started", "review_completed", "score_flagged", "revaluation_requested", "revaluation_resolved", "publication_approved"}:
            raise EducationError("Unsupported moderation event.")
        if event_type in {"score_flagged", "revaluation_requested", "revaluation_resolved"} and not str(reason).strip():
            raise EducationError("A moderation reason is required.")
        event_id = ident("moderation")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_exam_moderation_events VALUES(?,?,?,?,?,?,?,?,?)",
                (event_id, exam["institution_id"], exam_id, session_id, event_type, actor, str(reason)[:2000], _json(detail or {}), now()),
            )
        return self.platform._one("SELECT * FROM education_exam_moderation_events WHERE id=?", (event_id,))

    def moderation_timeline(self, actor: str, exam_id: str) -> list[dict[str, Any]]:
        exam = self.exams._exam(exam_id)
        self.permissions.require(actor, exam["institution_id"], "exam.monitor")
        rows = self.platform._all("SELECT * FROM education_exam_moderation_events WHERE exam_id=? ORDER BY created_at DESC", (exam_id,))
        for row in rows:
            try:
                row["detail"] = json.loads(row.pop("detail_json", "{}"))
            except (TypeError, ValueError):
                row["detail"] = {}
        return rows
