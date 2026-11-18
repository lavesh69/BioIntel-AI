from __future__ import annotations

import hashlib
import hmac
import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .permissions import PermissionService
from .platform import Conflict, Denied, EducationError, Missing, ident, now, parse_time

MIGRATION_ID = "education_phase3_secure_examination_v1"
QUESTION_TYPES = {"single_choice", "multiple_choice", "true_false", "short_text", "long_answer"}
DIFFICULTIES = {"easy", "medium", "hard"}
BLOOM_LEVELS = {"remember", "understand", "apply", "analyze", "evaluate", "create"}
INTEGRITY_EVENTS = {
    "focus_lost", "focus_restored", "fullscreen_exited", "fullscreen_entered",
    "network_disconnected", "network_reconnected", "copy_attempt", "paste_attempt",
    "concurrent_session", "clock_skew", "manual_note",
}

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS education_exam_policies(
 exam_id TEXT PRIMARY KEY REFERENCES examinations(id),
 duration_minutes INTEGER NOT NULL,
 attempts_allowed INTEGER NOT NULL DEFAULT 1,
 shuffle_questions INTEGER NOT NULL DEFAULT 1,
 shuffle_options INTEGER NOT NULL DEFAULT 1,
 autosave_seconds INTEGER NOT NULL DEFAULT 15,
 allow_resume INTEGER NOT NULL DEFAULT 1,
 access_code_hash TEXT NOT NULL DEFAULT '',
 instructions TEXT NOT NULL DEFAULT '',
 integrity_policy_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_exam_questions(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 exam_id TEXT NOT NULL REFERENCES examinations(id),
 creator_id TEXT NOT NULL,
 question_type TEXT NOT NULL,
 prompt TEXT NOT NULL,
 options_json TEXT NOT NULL DEFAULT '[]',
 correct_answer_json TEXT NOT NULL DEFAULT 'null',
 marks REAL NOT NULL,
 negative_marks REAL NOT NULL DEFAULT 0,
 difficulty TEXT NOT NULL DEFAULT 'medium',
 bloom_level TEXT NOT NULL DEFAULT 'understand',
 position INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_education_exam_questions_exam
 ON education_exam_questions(exam_id,state,position);
CREATE TABLE IF NOT EXISTS education_exam_sessions(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 exam_id TEXT NOT NULL REFERENCES examinations(id),
 student_id TEXT NOT NULL,
 attempt_number INTEGER NOT NULL,
 state TEXT NOT NULL DEFAULT 'active',
 started_at TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 last_seen_at TEXT NOT NULL,
 submitted_at TEXT,
 question_order_json TEXT NOT NULL DEFAULT '[]',
 option_order_json TEXT NOT NULL DEFAULT '{}',
 integrity_flags_json TEXT NOT NULL DEFAULT '[]',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(exam_id,student_id,attempt_number)
);
CREATE INDEX IF NOT EXISTS idx_education_exam_sessions_exam
 ON education_exam_sessions(exam_id,state,updated_at);
CREATE TABLE IF NOT EXISTS education_exam_answers(
 id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL REFERENCES education_exam_sessions(id),
 question_id TEXT NOT NULL REFERENCES education_exam_questions(id),
 answer_json TEXT NOT NULL DEFAULT 'null',
 version INTEGER NOT NULL DEFAULT 1,
 saved_at TEXT NOT NULL,
 UNIQUE(session_id,question_id)
);
CREATE TABLE IF NOT EXISTS education_exam_answer_versions(
 id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL REFERENCES education_exam_sessions(id),
 question_id TEXT NOT NULL REFERENCES education_exam_questions(id),
 answer_json TEXT NOT NULL DEFAULT 'null',
 version INTEGER NOT NULL,
 saved_at TEXT NOT NULL,
 UNIQUE(session_id,question_id,version)
);
CREATE TABLE IF NOT EXISTS education_exam_events(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 session_id TEXT NOT NULL REFERENCES education_exam_sessions(id),
 actor_id TEXT NOT NULL,
 event_type TEXT NOT NULL,
 detail_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_education_exam_events_session
 ON education_exam_events(session_id,created_at);
CREATE TABLE IF NOT EXISTS education_exam_manual_grades(
 id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL REFERENCES education_exam_sessions(id),
 question_id TEXT NOT NULL REFERENCES education_exam_questions(id),
 grader_id TEXT NOT NULL,
 marks REAL NOT NULL,
 feedback TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(session_id,question_id)
);
CREATE TABLE IF NOT EXISTS education_exam_scores(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 session_id TEXT NOT NULL UNIQUE REFERENCES education_exam_sessions(id),
 exam_id TEXT NOT NULL REFERENCES examinations(id),
 student_id TEXT NOT NULL,
 objective_score REAL NOT NULL DEFAULT 0,
 manual_score REAL NOT NULL DEFAULT 0,
 negative_score REAL NOT NULL DEFAULT 0,
 final_score REAL NOT NULL DEFAULT 0,
 max_marks REAL NOT NULL,
 grading_state TEXT NOT NULL DEFAULT 'pending',
 detail_json TEXT NOT NULL DEFAULT '{}',
 released INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_education_exam_scores_exam
 ON education_exam_scores(exam_id,grading_state,released);
INSERT OR IGNORE INTO education_migrations(id,applied_at)
 VALUES('education_phase3_secure_examination_v1',datetime('now'));
"""


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _decode(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError):
        return fallback


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_answer(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple, set)):
        return sorted(str(item).strip() for item in value)
    if isinstance(value, bool):
        return value
    return value


class SecureExaminationService:
    """Server-authoritative examination engine layered over the existing result system."""

    def __init__(self, platform):
        self.platform = platform
        self.db = platform.db
        self.permissions = PermissionService(platform)
        self.migrate()

    def migrate(self) -> str:
        with self.db.connection() as db:
            db.executescript(SCHEMA)
        return MIGRATION_ID

    def _exam(self, exam_id: str) -> dict[str, Any]:
        exam = self.platform._one(
            """SELECT e.*,p.duration_minutes,p.attempts_allowed,p.shuffle_questions,
            p.shuffle_options,p.autosave_seconds,p.allow_resume,p.access_code_hash,
            p.instructions,p.integrity_policy_json
            FROM examinations e LEFT JOIN education_exam_policies p ON p.exam_id=e.id
            WHERE e.id=?""",
            (exam_id,),
        )
        if not exam:
            raise Missing("Examination not found.")
        return exam

    def _session(self, session_id: str) -> dict[str, Any]:
        session = self.platform._one("SELECT * FROM education_exam_sessions WHERE id=?", (session_id,))
        if not session:
            raise Missing("Examination session not found.")
        return session

    def _require_subject_staff(self, actor: str, exam: dict[str, Any], permission: str) -> None:
        self.permissions.require(actor, exam["institution_id"], permission)
        self.platform._teacher(actor, exam["institution_id"], exam["subject_id"])

    def create_exam(
        self,
        actor: str,
        institution_id: str,
        subject_id: str,
        title: str,
        max_marks: float,
        starts_at: str,
        ends_at: str,
        *,
        duration_minutes: int,
        attempts_allowed: int = 1,
        shuffle_questions: bool = True,
        shuffle_options: bool = True,
        autosave_seconds: int = 15,
        allow_resume: bool = True,
        access_code: str = "",
        instructions: str = "",
    ) -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "exam.create")
        self.platform._subject(institution_id, subject_id)
        self.platform._teacher(actor, institution_id, subject_id)
        start, end = parse_time(starts_at), parse_time(ends_at)
        if end <= start:
            raise EducationError("Exam end must follow exam start.")
        if not str(title).strip():
            raise EducationError("Examination title is required.")
        if float(max_marks) <= 0:
            raise EducationError("Maximum marks must be greater than zero.")
        duration = int(duration_minutes)
        if duration < 1 or duration > 24 * 60:
            raise EducationError("Duration must be between 1 and 1440 minutes.")
        attempts = int(attempts_allowed)
        if attempts < 1 or attempts > 10:
            raise EducationError("Attempts allowed must be between 1 and 10.")
        autosave = int(autosave_seconds)
        if autosave < 5 or autosave > 300:
            raise EducationError("Autosave interval must be between 5 and 300 seconds.")
        exam_id, timestamp = ident("exam"), now()
        code_hash = hashlib.sha256(f"{exam_id}:{access_code}".encode()).hexdigest() if access_code else ""
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO examinations VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (exam_id, institution_id, subject_id, actor, title.strip(), float(max_marks), start.isoformat(), end.isoformat(), "draft", timestamp, timestamp),
            )
            db.execute(
                """INSERT INTO education_exam_policies
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    exam_id, duration, attempts, int(bool(shuffle_questions)), int(bool(shuffle_options)),
                    autosave, int(bool(allow_resume)), code_hash, instructions.strip(),
                    _json({"event_logging": True, "tab_switch_policy": "flag_only"}), timestamp, timestamp,
                ),
            )
        self.platform._audit(actor, "secure_exam_created", "examination", exam_id, institution_id, {"duration_minutes": duration, "attempts_allowed": attempts})
        return self._exam(exam_id)

    def add_question(
        self,
        actor: str,
        exam_id: str,
        question_type: str,
        prompt: str,
        marks: float,
        *,
        options: Iterable[str] | None = None,
        correct_answer: Any = None,
        negative_marks: float = 0,
        difficulty: str = "medium",
        bloom_level: str = "understand",
        position: int | None = None,
    ) -> dict[str, Any]:
        exam = self._exam(exam_id)
        self._require_subject_staff(actor, exam, "exam.create")
        if exam["state"] != "draft":
            raise Conflict("Published examinations cannot be structurally edited.")
        qtype = str(question_type).strip().lower()
        if qtype not in QUESTION_TYPES:
            raise EducationError("Unsupported question type.")
        if not str(prompt).strip():
            raise EducationError("Question prompt is required.")
        score = float(marks)
        penalty = float(negative_marks)
        if score <= 0:
            raise EducationError("Question marks must be greater than zero.")
        if penalty < 0 or penalty > score:
            raise EducationError("Negative marks must be between zero and question marks.")
        difficulty = str(difficulty).strip().lower()
        bloom_level = str(bloom_level).strip().lower()
        if difficulty not in DIFFICULTIES or bloom_level not in BLOOM_LEVELS:
            raise EducationError("Invalid difficulty or Bloom level.")
        option_list = [str(item).strip() for item in (options or []) if str(item).strip()]
        if qtype == "true_false":
            option_list = ["True", "False"]
        if qtype in {"single_choice", "multiple_choice", "true_false"}:
            if len(option_list) < 2:
                raise EducationError("Objective questions require at least two options.")
            if len(set(option_list)) != len(option_list):
                raise EducationError("Question options must be unique.")
            canonical = _canonical_answer(correct_answer)
            valid = canonical in option_list if qtype != "multiple_choice" else bool(canonical) and set(canonical).issubset(set(option_list))
            if not valid:
                raise EducationError("Correct answer must match the supplied options.")
        elif qtype == "short_text":
            canonical = _canonical_answer(correct_answer)
            if not canonical:
                raise EducationError("Short-text questions require an expected answer.")
        else:
            canonical = None
        if position is None:
            current = self.platform._one("SELECT COALESCE(MAX(position),0) n FROM education_exam_questions WHERE exam_id=?", (exam_id,)) or {"n": 0}
            position = int(current["n"]) + 1
        question_id, timestamp = ident("exq"), now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_exam_questions
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    question_id, exam["institution_id"], exam_id, actor, qtype, prompt.strip(),
                    _json(option_list), _json(canonical), score, penalty, difficulty,
                    bloom_level, int(position), "active", timestamp, timestamp,
                ),
            )
        self.platform._audit(actor, "exam_question_added", "exam_question", question_id, exam["institution_id"], {"exam_id": exam_id, "question_type": qtype, "marks": score})
        return self.question(question_id, include_answer=True)

    def question(self, question_id: str, *, include_answer: bool = False) -> dict[str, Any]:
        question = self.platform._one("SELECT * FROM education_exam_questions WHERE id=?", (question_id,))
        if not question:
            raise Missing("Examination question not found.")
        question["options"] = _decode(question.pop("options_json"), [])
        answer = _decode(question.pop("correct_answer_json"), None)
        if include_answer:
            question["correct_answer"] = answer
        return question

    def questions(self, actor: str, exam_id: str, *, include_answers: bool = False) -> list[dict[str, Any]]:
        exam = self._exam(exam_id)
        self._require_subject_staff(actor, exam, "exam.view")
        rows = self.platform._all("SELECT id FROM education_exam_questions WHERE exam_id=? AND state='active' ORDER BY position,id", (exam_id,))
        return [self.question(row["id"], include_answer=include_answers) for row in rows]

    def publish_exam(self, actor: str, exam_id: str) -> dict[str, Any]:
        exam = self._exam(exam_id)
        self._require_subject_staff(actor, exam, "exam.publish")
        questions = self.platform._all("SELECT marks FROM education_exam_questions WHERE exam_id=? AND state='active'", (exam_id,))
        if not questions:
            raise Conflict("Add at least one question before publishing.")
        total = round(sum(float(row["marks"]) for row in questions), 6)
        if abs(total - float(exam["max_marks"])) > 1e-6:
            raise Conflict(f"Question marks total {total:g}; examination maximum is {float(exam['max_marks']):g}.")
        timestamp = now()
        with self.db.connection() as db:
            db.execute("UPDATE examinations SET state='published',updated_at=? WHERE id=?", (timestamp, exam_id))
        self.platform._audit(actor, "secure_exam_published", "examination", exam_id, exam["institution_id"], {"question_count": len(questions), "marks": total})
        return self._exam(exam_id)

    def list_exams(self, actor: str, institution_id: str, *, state: str | None = None) -> list[dict[str, Any]]:
        self.permissions.require(actor, institution_id, "exam.view")
        roles = self.permissions.roles(actor, institution_id)
        args: list[Any] = [institution_id]
        clause = "e.institution_id=?"
        if state:
            clause += " AND e.state=?"
            args.append(state)
        student_roles = {"school_student", "college_student", "university_student"}
        if roles & student_roles and not roles - student_roles:
            clause += " AND e.state='published' AND EXISTS(SELECT 1 FROM enrollments n WHERE n.subject_id=e.subject_id AND n.student_id=? AND n.state='active')"
            args.append(actor)
        return self.platform._all(
            f"""SELECT e.*,s.code subject_code,s.name subject_name,p.duration_minutes,
            p.attempts_allowed,p.autosave_seconds,p.allow_resume,
            (SELECT COUNT(*) FROM education_exam_questions q WHERE q.exam_id=e.id AND q.state='active') question_count,
            (SELECT COUNT(*) FROM education_exam_sessions x WHERE x.exam_id=e.id) session_count
            FROM examinations e JOIN subjects s ON s.id=e.subject_id
            LEFT JOIN education_exam_policies p ON p.exam_id=e.id
            WHERE {clause} ORDER BY e.starts_at DESC""",
            tuple(args),
        )

    def _verify_access_code(self, exam: dict[str, Any], access_code: str) -> None:
        expected = str(exam.get("access_code_hash") or "")
        if not expected:
            return
        received = hashlib.sha256(f"{exam['id']}:{access_code}".encode()).hexdigest()
        if not hmac.compare_digest(expected, received):
            raise Denied("Invalid examination access code.")

    def start_exam(self, actor: str, exam_id: str, *, access_code: str = "") -> dict[str, Any]:
        exam = self._exam(exam_id)
        self.permissions.require(actor, exam["institution_id"], "exam.take")
        if exam["state"] != "published":
            raise Conflict("Examination is not published.")
        if not self.platform._one("SELECT 1 ok FROM enrollments WHERE subject_id=? AND student_id=? AND state='active'", (exam["subject_id"], actor)):
            raise Denied("Student is not enrolled in this examination subject.")
        current = _utc_now()
        start, end = parse_time(exam["starts_at"]), parse_time(exam["ends_at"])
        if current < start:
            raise Conflict("Examination has not started yet.")
        if current >= end:
            raise Conflict("Examination window has ended.")
        self._verify_access_code(exam, access_code)
        active = self.platform._one(
            "SELECT * FROM education_exam_sessions WHERE exam_id=? AND student_id=? AND state='active' ORDER BY attempt_number DESC LIMIT 1",
            (exam_id, actor),
        )
        if active:
            if not bool(exam.get("allow_resume", 1)):
                raise Conflict("This examination does not allow resuming an interrupted session.")
            return self.session_view(actor, active["id"])
        attempts = self.platform._one("SELECT COUNT(*) n FROM education_exam_sessions WHERE exam_id=? AND student_id=?", (exam_id, actor)) or {"n": 0}
        attempt_number = int(attempts["n"]) + 1
        if attempt_number > int(exam.get("attempts_allowed") or 1):
            raise Conflict("No examination attempts remain.")
        questions = self.platform._all("SELECT id,options_json FROM education_exam_questions WHERE exam_id=? AND state='active' ORDER BY position,id", (exam_id,))
        if not questions:
            raise Conflict("Examination has no active questions.")
        rng = random.SystemRandom()
        question_order = [row["id"] for row in questions]
        if bool(exam.get("shuffle_questions", 1)):
            rng.shuffle(question_order)
        option_order: dict[str, list[int]] = {}
        for row in questions:
            options = _decode(row["options_json"], [])
            indexes = list(range(len(options)))
            if options and bool(exam.get("shuffle_options", 1)):
                rng.shuffle(indexes)
            option_order[row["id"]] = indexes
        expires = min(end, current + timedelta(minutes=int(exam.get("duration_minutes") or 60)))
        session_id, timestamp = ident("exsess"), current.isoformat()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_exam_sessions
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    session_id, exam["institution_id"], exam_id, actor, attempt_number,
                    "active", timestamp, expires.isoformat(), timestamp, None,
                    _json(question_order), _json(option_order), "[]", timestamp, timestamp,
                ),
            )
        self.platform._audit(actor, "exam_session_started", "exam_session", session_id, exam["institution_id"], {"exam_id": exam_id, "attempt_number": attempt_number, "expires_at": expires.isoformat()})
        return self.session_view(actor, session_id)

    def _active_owned_session(self, actor: str, session_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        session = self._session(session_id)
        if session["student_id"] != actor:
            raise Denied("Examination session belongs to another student.")
        exam = self._exam(session["exam_id"])
        self.permissions.require(actor, exam["institution_id"], "exam.take")
        if session["state"] != "active":
            raise Conflict("Examination session is no longer active.")
        if _utc_now() >= parse_time(session["expires_at"]):
            self._expire_session(session)
            raise Conflict("Examination time has expired.")
        return session, exam

    def _expire_session(self, session: dict[str, Any]) -> None:
        timestamp = now()
        with self.db.connection() as db:
            db.execute("UPDATE education_exam_sessions SET state='expired',submitted_at=?,updated_at=? WHERE id=? AND state='active'", (timestamp, timestamp, session["id"]))
        refreshed = self._session(session["id"])
        if refreshed["state"] == "expired":
            self._score_session(refreshed)

    def save_answer(self, actor: str, session_id: str, question_id: str, answer: Any) -> dict[str, Any]:
        session, exam = self._active_owned_session(actor, session_id)
        question = self.platform._one("SELECT * FROM education_exam_questions WHERE id=? AND exam_id=? AND state='active'", (question_id, exam["id"]))
        if not question:
            raise Missing("Question is not part of this examination.")
        canonical = _canonical_answer(answer)
        current = self.platform._one("SELECT * FROM education_exam_answers WHERE session_id=? AND question_id=?", (session_id, question_id))
        version = int(current["version"]) + 1 if current else 1
        timestamp = now()
        payload = _json(canonical)
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_exam_answers VALUES(?,?,?,?,?,?)
                ON CONFLICT(session_id,question_id) DO UPDATE SET
                answer_json=excluded.answer_json,version=excluded.version,saved_at=excluded.saved_at""",
                (ident("exa"), session_id, question_id, payload, version, timestamp),
            )
            db.execute("INSERT INTO education_exam_answer_versions VALUES(?,?,?,?,?,?)", (ident("exav"), session_id, question_id, payload, version, timestamp))
            db.execute("UPDATE education_exam_sessions SET last_seen_at=?,updated_at=? WHERE id=?", (timestamp, timestamp, session_id))
        return {"session_id": session_id, "question_id": question_id, "answer": canonical, "version": version, "saved_at": timestamp}

    def record_event(self, actor: str, session_id: str, event_type: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
        session = self._session(session_id)
        event = str(event_type).strip().lower()
        if event not in INTEGRITY_EVENTS:
            raise EducationError("Unsupported integrity event.")
        if actor != session["student_id"]:
            exam = self._exam(session["exam_id"])
            self._require_subject_staff(actor, exam, "exam.monitor")
        timestamp = now()
        event_id = ident("exevt")
        with self.db.connection() as db:
            db.execute("INSERT INTO education_exam_events VALUES(?,?,?,?,?,?,?)", (event_id, session["institution_id"], session_id, actor, event, _json(detail or {}), timestamp))
        return self.platform._one("SELECT * FROM education_exam_events WHERE id=?", (event_id,))

    def session_view(self, actor: str, session_id: str) -> dict[str, Any]:
        session = self._session(session_id)
        exam = self._exam(session["exam_id"])
        roles = self.permissions.roles(actor, exam["institution_id"])
        is_owner = actor == session["student_id"]
        if not is_owner and not self.permissions.has(actor, exam["institution_id"], "exam.monitor"):
            raise Denied("Examination session access denied.")
        if session["state"] == "active" and _utc_now() >= parse_time(session["expires_at"]):
            self._expire_session(session)
            session = self._session(session_id)
        order = _decode(session["question_order_json"], [])
        option_order = _decode(session["option_order_json"], {})
        question_rows = self.platform._all(
            "SELECT * FROM education_exam_questions WHERE exam_id=? AND state='active'",
            (exam["id"],),
        )
        by_id = {row["id"]: row for row in question_rows}
        answers = {row["question_id"]: _decode(row["answer_json"], None) for row in self.platform._all("SELECT * FROM education_exam_answers WHERE session_id=?", (session_id,))}
        questions: list[dict[str, Any]] = []
        for number, question_id in enumerate(order, 1):
            row = by_id.get(question_id)
            if not row:
                continue
            options = _decode(row["options_json"], [])
            indexes = option_order.get(question_id, list(range(len(options))))
            displayed = [options[index] for index in indexes if 0 <= int(index) < len(options)]
            questions.append({
                "id": row["id"], "number": number, "question_type": row["question_type"],
                "prompt": row["prompt"], "options": displayed, "marks": row["marks"],
                "negative_marks": row["negative_marks"], "difficulty": row["difficulty"],
                "bloom_level": row["bloom_level"], "answer": answers.get(row["id"]),
            })
        remaining = max(0, int((parse_time(session["expires_at"]) - _utc_now()).total_seconds())) if session["state"] == "active" else 0
        return {
            **session,
            "exam_title": exam["title"],
            "subject_id": exam["subject_id"],
            "max_marks": exam["max_marks"],
            "instructions": exam.get("instructions") or "",
            "autosave_seconds": int(exam.get("autosave_seconds") or 15),
            "remaining_seconds": remaining,
            "questions": questions,
            "answered": sum(1 for item in questions if item["answer"] not in (None, "", [])),
            "can_view_answers": bool(roles and not is_owner),
        }

    def submit_exam(self, actor: str, session_id: str) -> dict[str, Any]:
        session, _exam = self._active_owned_session(actor, session_id)
        timestamp = now()
        with self.db.connection() as db:
            db.execute("UPDATE education_exam_sessions SET state='submitted',submitted_at=?,last_seen_at=?,updated_at=? WHERE id=? AND state='active'", (timestamp, timestamp, timestamp, session_id))
        scored = self._score_session(self._session(session_id))
        self.platform._audit(actor, "exam_session_submitted", "exam_session", session_id, session["institution_id"], {"grading_state": scored["grading_state"]})
        return scored

    def _score_session(self, session: dict[str, Any]) -> dict[str, Any]:
        exam = self._exam(session["exam_id"])
        questions = self.platform._all("SELECT * FROM education_exam_questions WHERE exam_id=? AND state='active'", (exam["id"],))
        answers = {row["question_id"]: _decode(row["answer_json"], None) for row in self.platform._all("SELECT * FROM education_exam_answers WHERE session_id=?", (session["id"],))}
        manual = {row["question_id"]: float(row["marks"]) for row in self.platform._all("SELECT * FROM education_exam_manual_grades WHERE session_id=?", (session["id"],))}
        objective_score = 0.0
        manual_score = 0.0
        negative_score = 0.0
        pending_manual: list[str] = []
        detail: list[dict[str, Any]] = []
        for question in questions:
            qid, qtype = question["id"], question["question_type"]
            answer = _canonical_answer(answers.get(qid))
            correct = _canonical_answer(_decode(question["correct_answer_json"], None))
            awarded = 0.0
            penalty = 0.0
            status = "unanswered"
            if qtype == "long_answer":
                if qid in manual:
                    awarded = manual[qid]
                    manual_score += awarded
                    status = "manually_graded"
                else:
                    pending_manual.append(qid)
                    status = "manual_review_required"
            elif answer not in (None, "", []):
                is_correct = answer.casefold() == correct.casefold() if qtype == "short_text" and isinstance(answer, str) and isinstance(correct, str) else answer == correct
                if is_correct:
                    awarded = float(question["marks"])
                    objective_score += awarded
                    status = "correct"
                else:
                    penalty = float(question["negative_marks"])
                    negative_score += penalty
                    status = "incorrect"
            detail.append({"question_id": qid, "status": status, "awarded": awarded, "penalty": penalty})
        final = max(0.0, min(float(exam["max_marks"]), objective_score + manual_score - negative_score))
        grading_state = "pending_manual" if pending_manual else "completed"
        timestamp = now()
        existing = self.platform._one("SELECT id FROM education_exam_scores WHERE session_id=?", (session["id"],))
        score_id = existing["id"] if existing else ident("exscore")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_exam_scores
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET
                objective_score=excluded.objective_score,manual_score=excluded.manual_score,
                negative_score=excluded.negative_score,final_score=excluded.final_score,
                grading_state=excluded.grading_state,detail_json=excluded.detail_json,
                updated_at=excluded.updated_at""",
                (
                    score_id, session["institution_id"], session["id"], exam["id"], session["student_id"],
                    objective_score, manual_score, negative_score, final, float(exam["max_marks"]),
                    grading_state, _json({"questions": detail, "pending_manual": pending_manual}), 0,
                    timestamp, timestamp,
                ),
            )
        return self.score(session["id"])

    def grade_manual_answer(self, actor: str, session_id: str, question_id: str, marks: float, feedback: str = "") -> dict[str, Any]:
        session = self._session(session_id)
        exam = self._exam(session["exam_id"])
        self._require_subject_staff(actor, exam, "exam.grade")
        question = self.platform._one("SELECT * FROM education_exam_questions WHERE id=? AND exam_id=? AND question_type='long_answer'", (question_id, exam["id"]))
        if not question:
            raise Missing("Manual-grade question not found.")
        score = float(marks)
        if score < 0 or score > float(question["marks"]):
            raise EducationError("Manual marks are outside the question range.")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_exam_manual_grades VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(session_id,question_id) DO UPDATE SET
                grader_id=excluded.grader_id,marks=excluded.marks,feedback=excluded.feedback,updated_at=excluded.updated_at""",
                (ident("exmg"), session_id, question_id, actor, score, feedback.strip(), timestamp, timestamp),
            )
        result = self._score_session(session)
        self.platform._audit(actor, "exam_manual_answer_graded", "exam_session", session_id, exam["institution_id"], {"question_id": question_id, "marks": score})
        return result

    def score(self, session_id: str) -> dict[str, Any]:
        score = self.platform._one("SELECT * FROM education_exam_scores WHERE session_id=?", (session_id,))
        if not score:
            raise Missing("Examination score not found.")
        score["detail"] = _decode(score.pop("detail_json"), {})
        return score

    def publish_scores(self, actor: str, exam_id: str) -> dict[str, Any]:
        exam = self._exam(exam_id)
        self._require_subject_staff(actor, exam, "result.publish")
        scores = self.platform._all("SELECT * FROM education_exam_scores WHERE exam_id=?", (exam_id,))
        if not scores:
            raise Conflict("No submitted examination scores are available.")
        pending = [row["session_id"] for row in scores if row["grading_state"] != "completed"]
        if pending:
            raise Conflict("Complete manual grading before publishing results.")
        for score in scores:
            percentage = 100.0 * float(score["final_score"]) / max(float(score["max_marks"]), 1.0)
            grade = "A+" if percentage >= 90 else "A" if percentage >= 80 else "B" if percentage >= 70 else "C" if percentage >= 60 else "D" if percentage >= 50 else "F"
            self.platform.set_result(actor, exam_id, score["student_id"], score["final_score"], grade, reason="Secure examination score publication")
        self.platform.publish_results(actor, exam_id)
        timestamp = now()
        with self.db.connection() as db:
            db.execute("UPDATE education_exam_scores SET released=1,updated_at=? WHERE exam_id=?", (timestamp, exam_id))
        self.platform._audit(actor, "secure_exam_scores_published", "examination", exam_id, exam["institution_id"], {"result_count": len(scores)})
        return {"exam_id": exam_id, "published": True, "result_count": len(scores)}

    def monitor(self, actor: str, exam_id: str) -> dict[str, Any]:
        exam = self._exam(exam_id)
        self._require_subject_staff(actor, exam, "exam.monitor")
        sessions = self.platform._all(
            """SELECT s.*,sc.final_score,sc.grading_state,sc.released,
            (SELECT COUNT(*) FROM education_exam_answers a WHERE a.session_id=s.id) answered,
            (SELECT COUNT(*) FROM education_exam_events v WHERE v.session_id=s.id) integrity_events
            FROM education_exam_sessions s LEFT JOIN education_exam_scores sc ON sc.session_id=s.id
            WHERE s.exam_id=? ORDER BY s.started_at DESC""",
            (exam_id,),
        )
        event_counts = self.platform._all("SELECT event_type,COUNT(*) records FROM education_exam_events v JOIN education_exam_sessions s ON s.id=v.session_id WHERE s.exam_id=? GROUP BY event_type ORDER BY records DESC", (exam_id,))
        return {"exam": exam, "sessions": sessions, "event_counts": event_counts, "generated_at": now()}

    def student_history(self, actor: str, institution_id: str) -> list[dict[str, Any]]:
        self.permissions.require(actor, institution_id, "exam.view")
        return self.platform._all(
            """SELECT s.id session_id,s.exam_id,e.title,e.starts_at,e.ends_at,s.attempt_number,
            s.state,s.started_at,s.submitted_at,sc.final_score,sc.max_marks,sc.grading_state,sc.released
            FROM education_exam_sessions s JOIN examinations e ON e.id=s.exam_id
            LEFT JOIN education_exam_scores sc ON sc.session_id=s.id
            WHERE s.institution_id=? AND s.student_id=? ORDER BY s.started_at DESC""",
            (institution_id, actor),
        )
