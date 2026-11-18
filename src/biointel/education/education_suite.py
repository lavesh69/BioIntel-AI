"""BioIntel Education Suite backend.

This module provides local-first classroom capabilities that do not depend on a
remote LMS: interactive lessons, versioned notes, assessment/question banks,
Q&A, offline resources, learning records, coding/notebook grading, similarity
review, resumes, credentials and optional service connectors.

The public product identity is BioIntel. Optional external services remain
separate deployments and are only addressed through user-configured endpoints.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import tokenize
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


class EducationSuiteError(RuntimeError):
    """Raised for invalid Education Suite operations."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _identifier(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load_json(value: str | bytes | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def default_suite_root() -> Path:
    configured = str(os.environ.get("BIOINTEL_USER_DATA_DIR", "")).strip()
    base = Path(configured).expanduser() if configured else Path.home() / ".biointel"
    root = base / "education_suite"
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass(frozen=True)
class CodeRunResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False


class EducationSuiteService:
    """SQLite-backed local Education Suite service."""

    def __init__(self, database_path: str | Path | None = None, storage_root: str | Path | None = None):
        self.root = Path(storage_root).expanduser() if storage_root else default_suite_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database_path = Path(database_path).expanduser() if database_path else self.root / "education_suite.sqlite3"
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.library_root = self.root / "offline_library"
        self.library_root.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.database_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def _init_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS lessons(
          id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,subject_id TEXT NOT NULL DEFAULT '',
          title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',activities_json TEXT NOT NULL DEFAULT '[]',
          state TEXT NOT NULL DEFAULT 'draft',author_id TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS lesson_attempts(
          id TEXT PRIMARY KEY,lesson_id TEXT NOT NULL,learner_id TEXT NOT NULL,responses_json TEXT NOT NULL,
          score REAL NOT NULL,max_score REAL NOT NULL,completed_at TEXT NOT NULL,
          UNIQUE(lesson_id,learner_id,id),FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS notes(
          id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,subject_id TEXT NOT NULL DEFAULT '',title TEXT NOT NULL,
          body TEXT NOT NULL DEFAULT '',owner_id TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS note_revisions(
          id TEXT PRIMARY KEY,note_id TEXT NOT NULL,revision INTEGER NOT NULL,body TEXT NOT NULL,editor_id TEXT NOT NULL,
          created_at TEXT NOT NULL,FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS note_comments(
          id TEXT PRIMARY KEY,note_id TEXT NOT NULL,author_id TEXT NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL,
          FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS questions(
          id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,subject_id TEXT NOT NULL DEFAULT '',question_type TEXT NOT NULL,
          prompt TEXT NOT NULL,options_json TEXT NOT NULL DEFAULT '[]',answer_json TEXT NOT NULL,
          explanation TEXT NOT NULL DEFAULT '',points REAL NOT NULL DEFAULT 1,tags_json TEXT NOT NULL DEFAULT '[]',
          author_id TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS assessments(
          id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,subject_id TEXT NOT NULL DEFAULT '',title TEXT NOT NULL,
          instructions TEXT NOT NULL DEFAULT '',settings_json TEXT NOT NULL DEFAULT '{}',state TEXT NOT NULL DEFAULT 'draft',
          created_by TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS assessment_items(
          assessment_id TEXT NOT NULL,question_id TEXT NOT NULL,position INTEGER NOT NULL,
          PRIMARY KEY(assessment_id,question_id),FOREIGN KEY(assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
          FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS assessment_attempts(
          id TEXT PRIMARY KEY,assessment_id TEXT NOT NULL,learner_id TEXT NOT NULL,responses_json TEXT NOT NULL,
          score REAL NOT NULL,max_score REAL NOT NULL,feedback_json TEXT NOT NULL,submitted_at TEXT NOT NULL,
          FOREIGN KEY(assessment_id) REFERENCES assessments(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS qa_questions(
          id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,subject_id TEXT NOT NULL DEFAULT '',title TEXT NOT NULL,
          body TEXT NOT NULL,author_id TEXT NOT NULL,tags_json TEXT NOT NULL DEFAULT '[]',state TEXT NOT NULL DEFAULT 'open',
          accepted_answer_id TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS qa_answers(
          id TEXT PRIMARY KEY,question_id TEXT NOT NULL,body TEXT NOT NULL,author_id TEXT NOT NULL,created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,FOREIGN KEY(question_id) REFERENCES qa_questions(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS qa_votes(
          target_type TEXT NOT NULL,target_id TEXT NOT NULL,voter_id TEXT NOT NULL,value INTEGER NOT NULL,
          updated_at TEXT NOT NULL,PRIMARY KEY(target_type,target_id,voter_id)
        );
        CREATE TABLE IF NOT EXISTS learning_events(
          id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,actor_id TEXT NOT NULL,event_type TEXT NOT NULL,
          object_type TEXT NOT NULL DEFAULT '',object_id TEXT NOT NULL DEFAULT '',detail_json TEXT NOT NULL DEFAULT '{}',
          occurred_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS offline_resources(
          id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,subject_id TEXT NOT NULL DEFAULT '',title TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',file_name TEXT NOT NULL,path TEXT NOT NULL,mime_type TEXT NOT NULL DEFAULT '',
          size_bytes INTEGER NOT NULL,sha256 TEXT NOT NULL,created_by TEXT NOT NULL,created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS service_connectors(
          id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,connector_type TEXT NOT NULL,display_name TEXT NOT NULL,
          endpoint TEXT NOT NULL DEFAULT '',enabled INTEGER NOT NULL DEFAULT 0,config_json TEXT NOT NULL DEFAULT '{}',
          updated_by TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(institution_id,connector_type)
        );
        CREATE TABLE IF NOT EXISTS code_tasks(
          id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,subject_id TEXT NOT NULL DEFAULT '',title TEXT NOT NULL,
          prompt TEXT NOT NULL,tests_json TEXT NOT NULL DEFAULT '[]',language TEXT NOT NULL DEFAULT 'python',
          created_by TEXT NOT NULL,created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS code_submissions(
          id TEXT PRIMARY KEY,task_id TEXT NOT NULL,learner_id TEXT NOT NULL,source_code TEXT NOT NULL,
          result_json TEXT NOT NULL,score REAL NOT NULL,max_score REAL NOT NULL,submitted_at TEXT NOT NULL,
          FOREIGN KEY(task_id) REFERENCES code_tasks(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS resume_profiles(
          id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,name TEXT NOT NULL,headline TEXT NOT NULL DEFAULT '',
          profile_json TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS credentials(
          id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,recipient_id TEXT NOT NULL,title TEXT NOT NULL,
          credential_type TEXT NOT NULL,evidence TEXT NOT NULL DEFAULT '',issuer TEXT NOT NULL,
          metadata_json TEXT NOT NULL DEFAULT '{}',issued_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS application_documents(
          id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,document_type TEXT NOT NULL,title TEXT NOT NULL,
          body TEXT NOT NULL,opportunity_id TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_lessons_scope ON lessons(institution_id,subject_id,state);
        CREATE INDEX IF NOT EXISTS idx_questions_scope ON questions(institution_id,subject_id);
        CREATE INDEX IF NOT EXISTS idx_assessments_scope ON assessments(institution_id,subject_id,state);
        CREATE INDEX IF NOT EXISTS idx_qa_scope ON qa_questions(institution_id,subject_id,state);
        CREATE INDEX IF NOT EXISTS idx_events_scope ON learning_events(institution_id,actor_id,event_type,occurred_at);
        CREATE INDEX IF NOT EXISTS idx_resources_scope ON offline_resources(institution_id,subject_id);
        """
        with self.connection() as db:
            db.executescript(schema)

    @staticmethod
    def _rows(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    # ---------- Lessons ----------
    def create_lesson(
        self,
        institution_id: str,
        subject_id: str,
        title: str,
        description: str,
        activities: Sequence[Mapping[str, Any]],
        author_id: str,
        publish: bool = False,
    ) -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise EducationSuiteError("Lesson title is required.")
        normalized = []
        for index, activity in enumerate(activities):
            kind = str(activity.get("type", "text")).strip().lower()
            if kind not in {"text", "mcq", "multi_select", "true_false", "short", "numeric", "checklist", "link"}:
                raise EducationSuiteError(f"Unsupported activity type at position {index + 1}: {kind}")
            item = dict(activity)
            item["id"] = str(item.get("id") or _identifier("act"))
            item["type"] = kind
            item["points"] = float(item.get("points", 0 if kind in {"text", "link", "checklist"} else 1))
            normalized.append(item)
        lesson_id = _identifier("lesson")
        timestamp = _now()
        with self.connection() as db:
            db.execute(
                "INSERT INTO lessons VALUES(?,?,?,?,?,?,?,?,?,?)",
                (lesson_id, institution_id, subject_id, title, description.strip(), _json(normalized),
                 "published" if publish else "draft", author_id, timestamp, timestamp),
            )
        self.track_event(institution_id, author_id, "lesson_created", "lesson", lesson_id, {"published": publish})
        return self.get_lesson(lesson_id)

    def get_lesson(self, lesson_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM lessons WHERE id=?", (lesson_id,)).fetchone()
        if not row:
            raise EducationSuiteError("Lesson not found.")
        result = dict(row)
        result["activities"] = _load_json(result.pop("activities_json"), [])
        return result

    def list_lessons(self, institution_id: str, subject_id: str = "", include_drafts: bool = True) -> list[dict[str, Any]]:
        clauses = ["institution_id=?"]
        args: list[Any] = [institution_id]
        if subject_id:
            clauses.append("subject_id=?")
            args.append(subject_id)
        if not include_drafts:
            clauses.append("state='published'")
        with self.connection() as db:
            rows = db.execute(f"SELECT * FROM lessons WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC", args).fetchall()
        result = self._rows(rows)
        for item in result:
            item["activities"] = _load_json(item.pop("activities_json"), [])
        return result

    def publish_lesson(self, lesson_id: str, actor_id: str) -> dict[str, Any]:
        timestamp = _now()
        with self.connection() as db:
            db.execute("UPDATE lessons SET state='published',updated_at=? WHERE id=?", (timestamp, lesson_id))
        lesson = self.get_lesson(lesson_id)
        self.track_event(lesson["institution_id"], actor_id, "lesson_published", "lesson", lesson_id)
        return lesson

    def submit_lesson_attempt(self, lesson_id: str, learner_id: str, responses: Mapping[str, Any]) -> dict[str, Any]:
        lesson = self.get_lesson(lesson_id)
        score = 0.0
        maximum = 0.0
        feedback: dict[str, Any] = {}
        for activity in lesson["activities"]:
            points = float(activity.get("points", 0) or 0)
            if points <= 0:
                continue
            maximum += points
            response = responses.get(activity["id"])
            correct = self._is_correct(activity.get("type", ""), response, activity.get("answer"), activity)
            if correct:
                score += points
            feedback[activity["id"]] = {"correct": correct, "points": points if correct else 0.0}
        attempt_id = _identifier("lattempt")
        with self.connection() as db:
            db.execute(
                "INSERT INTO lesson_attempts VALUES(?,?,?,?,?,?,?)",
                (attempt_id, lesson_id, learner_id, _json(dict(responses)), score, maximum, _now()),
            )
        self.track_event(lesson["institution_id"], learner_id, "lesson_completed", "lesson", lesson_id,
                         {"score": score, "max_score": maximum})
        return {"id": attempt_id, "score": score, "max_score": maximum, "feedback": feedback}

    # ---------- Notes ----------
    def save_note(self, institution_id: str, subject_id: str, title: str, body: str, editor_id: str, note_id: str = "") -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise EducationSuiteError("Note title is required.")
        timestamp = _now()
        with self.connection() as db:
            if note_id:
                current = db.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
                if not current:
                    raise EducationSuiteError("Note not found.")
                revision = int(current["revision"]) + 1
                db.execute("UPDATE notes SET title=?,body=?,revision=?,updated_at=? WHERE id=?",
                           (title, body, revision, timestamp, note_id))
            else:
                note_id = _identifier("note")
                revision = 1
                db.execute("INSERT INTO notes VALUES(?,?,?,?,?,?,?,?,?)",
                           (note_id, institution_id, subject_id, title, body, editor_id, revision, timestamp, timestamp))
            db.execute("INSERT INTO note_revisions VALUES(?,?,?,?,?,?)",
                       (_identifier("rev"), note_id, revision, body, editor_id, timestamp))
        self.track_event(institution_id, editor_id, "note_saved", "note", note_id, {"revision": revision})
        return self.get_note(note_id)

    def get_note(self, note_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
            revisions = db.execute("SELECT * FROM note_revisions WHERE note_id=? ORDER BY revision DESC", (note_id,)).fetchall()
            comments = db.execute("SELECT * FROM note_comments WHERE note_id=? ORDER BY created_at", (note_id,)).fetchall()
        if not row:
            raise EducationSuiteError("Note not found.")
        result = dict(row)
        result["revisions"] = self._rows(revisions)
        result["comments"] = self._rows(comments)
        return result

    def list_notes(self, institution_id: str, subject_id: str = "") -> list[dict[str, Any]]:
        query = "SELECT * FROM notes WHERE institution_id=?"
        args: list[Any] = [institution_id]
        if subject_id:
            query += " AND subject_id=?"
            args.append(subject_id)
        query += " ORDER BY updated_at DESC"
        with self.connection() as db:
            return self._rows(db.execute(query, args).fetchall())

    def add_note_comment(self, note_id: str, author_id: str, body: str) -> dict[str, Any]:
        if not body.strip():
            raise EducationSuiteError("Comment cannot be empty.")
        comment_id = _identifier("comment")
        with self.connection() as db:
            db.execute("INSERT INTO note_comments VALUES(?,?,?,?,?)", (comment_id, note_id, author_id, body.strip(), _now()))
            row = db.execute("SELECT * FROM note_comments WHERE id=?", (comment_id,)).fetchone()
        return dict(row)

    # ---------- Question bank and assessments ----------
    def create_question(
        self,
        institution_id: str,
        subject_id: str,
        question_type: str,
        prompt: str,
        answer: Any,
        author_id: str,
        options: Sequence[str] | None = None,
        explanation: str = "",
        points: float = 1.0,
        tags: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        question_type = question_type.strip().lower()
        if question_type not in {"mcq", "multi_select", "true_false", "short", "numeric"}:
            raise EducationSuiteError("Unsupported question type.")
        if not prompt.strip():
            raise EducationSuiteError("Question prompt is required.")
        if float(points) <= 0:
            raise EducationSuiteError("Question points must be greater than zero.")
        question_id = _identifier("question")
        timestamp = _now()
        with self.connection() as db:
            db.execute(
                "INSERT INTO questions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (question_id, institution_id, subject_id, question_type, prompt.strip(), _json(list(options or [])),
                 _json(answer), explanation.strip(), float(points), _json(list(tags or [])), author_id, timestamp, timestamp),
            )
        return self.get_question(question_id)

    def get_question(self, question_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM questions WHERE id=?", (question_id,)).fetchone()
        if not row:
            raise EducationSuiteError("Question not found.")
        result = dict(row)
        result["options"] = _load_json(result.pop("options_json"), [])
        result["answer"] = _load_json(result.pop("answer_json"), None)
        result["tags"] = _load_json(result.pop("tags_json"), [])
        return result

    def list_questions(self, institution_id: str, subject_id: str = "") -> list[dict[str, Any]]:
        query = "SELECT * FROM questions WHERE institution_id=?"
        args: list[Any] = [institution_id]
        if subject_id:
            query += " AND subject_id=?"
            args.append(subject_id)
        query += " ORDER BY created_at DESC"
        with self.connection() as db:
            rows = db.execute(query, args).fetchall()
        result = self._rows(rows)
        for item in result:
            item["options"] = _load_json(item.pop("options_json"), [])
            item["answer"] = _load_json(item.pop("answer_json"), None)
            item["tags"] = _load_json(item.pop("tags_json"), [])
        return result

    def create_assessment(
        self,
        institution_id: str,
        subject_id: str,
        title: str,
        question_ids: Sequence[str],
        created_by: str,
        instructions: str = "",
        settings: Mapping[str, Any] | None = None,
        publish: bool = False,
    ) -> dict[str, Any]:
        if not title.strip():
            raise EducationSuiteError("Assessment title is required.")
        if not question_ids:
            raise EducationSuiteError("Select at least one question.")
        assessment_id = _identifier("assessment")
        timestamp = _now()
        with self.connection() as db:
            existing = {row[0] for row in db.execute(
                f"SELECT id FROM questions WHERE id IN ({','.join('?' for _ in question_ids)})", tuple(question_ids)
            ).fetchall()}
            missing = [item for item in question_ids if item not in existing]
            if missing:
                raise EducationSuiteError(f"Unknown question IDs: {', '.join(missing)}")
            db.execute("INSERT INTO assessments VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (assessment_id, institution_id, subject_id, title.strip(), instructions.strip(),
                        _json(dict(settings or {})), "published" if publish else "draft", created_by, timestamp, timestamp,))
            db.executemany("INSERT INTO assessment_items VALUES(?,?,?)",
                           [(assessment_id, question_id, position) for position, question_id in enumerate(question_ids, 1)])
        self.track_event(institution_id, created_by, "assessment_created", "assessment", assessment_id,
                         {"published": publish, "questions": len(question_ids)})
        return self.get_assessment(assessment_id)

    def get_assessment(self, assessment_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM assessments WHERE id=?", (assessment_id,)).fetchone()
            qrows = db.execute("""
              SELECT q.*,ai.position FROM assessment_items ai JOIN questions q ON q.id=ai.question_id
              WHERE ai.assessment_id=? ORDER BY ai.position
            """, (assessment_id,)).fetchall()
        if not row:
            raise EducationSuiteError("Assessment not found.")
        result = dict(row)
        result["settings"] = _load_json(result.pop("settings_json"), {})
        result["questions"] = []
        for qrow in qrows:
            question = dict(qrow)
            question["options"] = _load_json(question.pop("options_json"), [])
            question["answer"] = _load_json(question.pop("answer_json"), None)
            question["tags"] = _load_json(question.pop("tags_json"), [])
            result["questions"].append(question)
        return result

    def list_assessments(self, institution_id: str, subject_id: str = "", published_only: bool = False) -> list[dict[str, Any]]:
        clauses = ["a.institution_id=?"]
        args: list[Any] = [institution_id]
        if subject_id:
            clauses.append("a.subject_id=?")
            args.append(subject_id)
        if published_only:
            clauses.append("a.state='published'")
        with self.connection() as db:
            rows = db.execute(f"""
              SELECT a.*,COUNT(ai.question_id) question_count
              FROM assessments a LEFT JOIN assessment_items ai ON ai.assessment_id=a.id
              WHERE {' AND '.join(clauses)} GROUP BY a.id ORDER BY a.updated_at DESC
            """, args).fetchall()
        result = self._rows(rows)
        for item in result:
            item["settings"] = _load_json(item.pop("settings_json"), {})
        return result

    def submit_assessment(self, assessment_id: str, learner_id: str, responses: Mapping[str, Any]) -> dict[str, Any]:
        assessment = self.get_assessment(assessment_id)
        if assessment["state"] != "published":
            raise EducationSuiteError("Assessment is not published.")
        score = 0.0
        maximum = 0.0
        feedback: dict[str, Any] = {}
        for question in assessment["questions"]:
            points = float(question["points"])
            maximum += points
            response = responses.get(question["id"])
            correct = self._is_correct(question["question_type"], response, question["answer"], question)
            earned = points if correct else 0.0
            score += earned
            feedback[question["id"]] = {
                "correct": correct,
                "earned": earned,
                "maximum": points,
                "explanation": question.get("explanation", ""),
            }
        attempt_id = _identifier("aattempt")
        with self.connection() as db:
            db.execute("INSERT INTO assessment_attempts VALUES(?,?,?,?,?,?,?,?)",
                       (attempt_id, assessment_id, learner_id, _json(dict(responses)), score, maximum, _json(feedback), _now()))
        self.track_event(assessment["institution_id"], learner_id, "assessment_submitted", "assessment", assessment_id,
                         {"score": score, "max_score": maximum})
        return {"id": attempt_id, "score": score, "max_score": maximum, "feedback": feedback}

    @staticmethod
    def _is_correct(question_type: str, response: Any, answer: Any, metadata: Mapping[str, Any]) -> bool:
        kind = str(question_type).lower()
        if kind in {"mcq", "true_false"}:
            return str(response).strip().casefold() == str(answer).strip().casefold()
        if kind == "multi_select":
            left = {str(item).strip().casefold() for item in (response or [])}
            right = {str(item).strip().casefold() for item in (answer or [])}
            return left == right
        if kind == "short":
            accepted = answer if isinstance(answer, list) else [answer]
            normalized = str(response or "").strip().casefold()
            return normalized in {str(item).strip().casefold() for item in accepted}
        if kind == "numeric":
            try:
                tolerance = float(metadata.get("tolerance", 1e-6) or 1e-6)
                return abs(float(response) - float(answer)) <= tolerance
            except (TypeError, ValueError):
                return False
        return False

    # ---------- Q&A ----------
    def create_qa_question(self, institution_id: str, subject_id: str, title: str, body: str, author_id: str,
                           tags: Sequence[str] | None = None) -> dict[str, Any]:
        if not title.strip() or not body.strip():
            raise EducationSuiteError("Question title and details are required.")
        question_id = _identifier("qa")
        timestamp = _now()
        with self.connection() as db:
            db.execute("INSERT INTO qa_questions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (question_id, institution_id, subject_id, title.strip(), body.strip(), author_id,
                        _json(list(tags or [])), "open", "", timestamp, timestamp))
        self.track_event(institution_id, author_id, "qa_question_created", "qa_question", question_id)
        return self.get_qa_question(question_id)

    def answer_qa_question(self, question_id: str, body: str, author_id: str) -> dict[str, Any]:
        if not body.strip():
            raise EducationSuiteError("Answer cannot be empty.")
        answer_id = _identifier("answer")
        timestamp = _now()
        with self.connection() as db:
            db.execute("INSERT INTO qa_answers VALUES(?,?,?,?,?,?)",
                       (answer_id, question_id, body.strip(), author_id, timestamp, timestamp))
            row = db.execute("SELECT * FROM qa_answers WHERE id=?", (answer_id,)).fetchone()
        return dict(row)

    def accept_qa_answer(self, question_id: str, answer_id: str, actor_id: str) -> dict[str, Any]:
        with self.connection() as db:
            question = db.execute("SELECT * FROM qa_questions WHERE id=?", (question_id,)).fetchone()
            answer = db.execute("SELECT * FROM qa_answers WHERE id=? AND question_id=?", (answer_id, question_id)).fetchone()
            if not question or not answer:
                raise EducationSuiteError("Question or answer not found.")
            if actor_id != question["author_id"]:
                raise EducationSuiteError("Only the question author can accept an answer.")
            db.execute("UPDATE qa_questions SET accepted_answer_id=?,state='answered',updated_at=? WHERE id=?",
                       (answer_id, _now(), question_id))
        return self.get_qa_question(question_id)

    def vote(self, target_type: str, target_id: str, voter_id: str, value: int) -> None:
        if target_type not in {"question", "answer"} or value not in {-1, 0, 1}:
            raise EducationSuiteError("Invalid vote.")
        with self.connection() as db:
            if value == 0:
                db.execute("DELETE FROM qa_votes WHERE target_type=? AND target_id=? AND voter_id=?",
                           (target_type, target_id, voter_id))
            else:
                db.execute("""INSERT INTO qa_votes VALUES(?,?,?,?,?)
                  ON CONFLICT(target_type,target_id,voter_id) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
                           (target_type, target_id, voter_id, value, _now()))

    def get_qa_question(self, question_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM qa_questions WHERE id=?", (question_id,)).fetchone()
            answers = db.execute("""
              SELECT a.*,COALESCE(SUM(v.value),0) votes FROM qa_answers a
              LEFT JOIN qa_votes v ON v.target_type='answer' AND v.target_id=a.id
              WHERE a.question_id=? GROUP BY a.id ORDER BY votes DESC,a.created_at
            """, (question_id,)).fetchall()
        if not row:
            raise EducationSuiteError("Question not found.")
        result = dict(row)
        result["tags"] = _load_json(result.pop("tags_json"), [])
        result["answers"] = self._rows(answers)
        return result

    def list_qa_questions(self, institution_id: str, subject_id: str = "", search: str = "") -> list[dict[str, Any]]:
        clauses = ["q.institution_id=?"]
        args: list[Any] = [institution_id]
        if subject_id:
            clauses.append("q.subject_id=?")
            args.append(subject_id)
        if search.strip():
            clauses.append("(q.title LIKE ? OR q.body LIKE ? OR q.tags_json LIKE ?)")
            token = f"%{search.strip()}%"
            args.extend([token, token, token])
        with self.connection() as db:
            rows = db.execute(f"""
              SELECT q.*,COUNT(DISTINCT a.id) answer_count,COALESCE(SUM(v.value),0) votes
              FROM qa_questions q LEFT JOIN qa_answers a ON a.question_id=q.id
              LEFT JOIN qa_votes v ON v.target_type='question' AND v.target_id=q.id
              WHERE {' AND '.join(clauses)} GROUP BY q.id ORDER BY q.updated_at DESC
            """, args).fetchall()
        result = self._rows(rows)
        for item in result:
            item["tags"] = _load_json(item.pop("tags_json"), [])
        return result

    # ---------- Learning records and analytics ----------
    def track_event(self, institution_id: str, actor_id: str, event_type: str, object_type: str = "",
                    object_id: str = "", detail: Mapping[str, Any] | None = None) -> str:
        event_id = _identifier("event")
        with self.connection() as db:
            db.execute("INSERT INTO learning_events VALUES(?,?,?,?,?,?,?,?)",
                       (event_id, institution_id, actor_id, event_type, object_type, object_id,
                        _json(dict(detail or {})), _now()))
        return event_id

    def analytics_summary(self, institution_id: str, actor_id: str = "") -> dict[str, Any]:
        actor_clause = " AND actor_id=?" if actor_id else ""
        args: list[Any] = [institution_id] + ([actor_id] if actor_id else [])
        with self.connection() as db:
            event_rows = db.execute(
                f"SELECT event_type,COUNT(*) count FROM learning_events WHERE institution_id=?{actor_clause} GROUP BY event_type ORDER BY count DESC",
                args,
            ).fetchall()
            totals = db.execute(
                f"SELECT COUNT(*) events,COUNT(DISTINCT actor_id) actors,COUNT(DISTINCT object_id) objects FROM learning_events WHERE institution_id=?{actor_clause}",
                args,
            ).fetchone()
        return {"events": int(totals["events"] or 0), "actors": int(totals["actors"] or 0),
                "objects": int(totals["objects"] or 0), "by_type": self._rows(event_rows)}

    def export_learning_records(self, institution_id: str) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM learning_events WHERE institution_id=? ORDER BY occurred_at", (institution_id,)).fetchall()
        statements = []
        for row in rows:
            item = dict(row)
            statements.append({
                "id": item["id"],
                "actor": {"account": {"homePage": "biointel://education", "name": item["actor_id"]}},
                "verb": {"id": f"biointel://verb/{item['event_type']}", "display": {"en": item["event_type"].replace("_", " ")}},
                "object": {"id": f"biointel://{item['object_type'] or 'object'}/{item['object_id'] or 'unknown'}"},
                "result": _load_json(item["detail_json"], {}),
                "timestamp": item["occurred_at"],
            })
        return statements

    # ---------- Offline library ----------
    def add_offline_resource(self, institution_id: str, subject_id: str, title: str, description: str,
                             source: str | Path | bytes, file_name: str, created_by: str,
                             mime_type: str = "application/octet-stream") -> dict[str, Any]:
        if not title.strip() or not file_name.strip():
            raise EducationSuiteError("Resource title and file name are required.")
        resource_id = _identifier("resource")
        suffix = Path(file_name).suffix.lower()
        destination = self.library_root / institution_id / f"{resource_id}{suffix}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        if isinstance(source, bytes):
            data = source
            if len(data) > 512 * 1024 * 1024:
                raise EducationSuiteError("Offline resource exceeds 512 MiB.")
            destination.write_bytes(data)
            digest.update(data)
            size = len(data)
        else:
            path = Path(source)
            if not path.is_file():
                raise EducationSuiteError("Offline resource file not found.")
            if path.stat().st_size > 512 * 1024 * 1024:
                raise EducationSuiteError("Offline resource exceeds 512 MiB.")
            with path.open("rb") as src, destination.open("wb") as dst:
                while chunk := src.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
                    dst.write(chunk)
        with self.connection() as db:
            db.execute("INSERT INTO offline_resources VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       (resource_id, institution_id, subject_id, title.strip(), description.strip(), file_name,
                        str(destination), mime_type, size, digest.hexdigest(), created_by, _now()))
            row = db.execute("SELECT * FROM offline_resources WHERE id=?", (resource_id,)).fetchone()
        self.track_event(institution_id, created_by, "offline_resource_added", "resource", resource_id,
                         {"size_bytes": size})
        return dict(row)

    def list_offline_resources(self, institution_id: str, subject_id: str = "") -> list[dict[str, Any]]:
        query = "SELECT * FROM offline_resources WHERE institution_id=?"
        args: list[Any] = [institution_id]
        if subject_id:
            query += " AND subject_id=?"
            args.append(subject_id)
        query += " ORDER BY created_at DESC"
        with self.connection() as db:
            return self._rows(db.execute(query, args).fetchall())

    # ---------- Optional service connectors ----------
    def configure_connector(self, institution_id: str, connector_type: str, display_name: str, endpoint: str,
                            actor_id: str, enabled: bool = True, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        connector_type = connector_type.strip().lower()
        if connector_type not in {"live_class", "virtual_classroom", "whiteboard", "collaborative_notes",
                                  "multi_user_lab", "assessment_worker", "code_sandbox", "learning_record_store",
                                  "education_search", "lms_bridge", "offline_library_sync"}:
            raise EducationSuiteError("Unsupported connector type.")
        connector_id = _identifier("connector")
        timestamp = _now()
        with self.connection() as db:
            db.execute("""INSERT INTO service_connectors VALUES(?,?,?,?,?,?,?,?,?)
              ON CONFLICT(institution_id,connector_type) DO UPDATE SET display_name=excluded.display_name,
              endpoint=excluded.endpoint,enabled=excluded.enabled,config_json=excluded.config_json,
              updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
                       (connector_id, institution_id, connector_type, display_name.strip() or "BioIntel Service",
                        endpoint.strip(), int(enabled), _json(dict(config or {})), actor_id, timestamp))
            row = db.execute("SELECT * FROM service_connectors WHERE institution_id=? AND connector_type=?",
                             (institution_id, connector_type)).fetchone()
        result = dict(row)
        result["config"] = _load_json(result.pop("config_json"), {})
        return result

    def list_connectors(self, institution_id: str) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM service_connectors WHERE institution_id=? ORDER BY connector_type",
                              (institution_id,)).fetchall()
        result = self._rows(rows)
        for item in result:
            item["config"] = _load_json(item.pop("config_json"), {})
        return result

    @staticmethod
    def connector_health(endpoint: str, timeout: float = 3.0) -> dict[str, Any]:
        endpoint = endpoint.strip()
        if not endpoint:
            return {"ok": False, "status": "Not configured", "detail": "No endpoint has been saved."}
        if not re.match(r"^https?://", endpoint, re.I):
            return {"ok": False, "status": "Invalid endpoint", "detail": "Use an HTTP or HTTPS URL."}
        request = urllib.request.Request(endpoint, method="GET", headers={"User-Agent": "BioIntel-Education/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                code = int(getattr(response, "status", 200))
                return {"ok": 200 <= code < 500, "status": f"HTTP {code}", "detail": response.geturl()}
        except urllib.error.HTTPError as exc:
            return {"ok": exc.code < 500, "status": f"HTTP {exc.code}", "detail": str(exc.reason)}
        except Exception as exc:  # network and TLS failures are surfaced, never hidden
            return {"ok": False, "status": "Unavailable", "detail": str(exc)}

    # ---------- Coding and notebook grading ----------
    @staticmethod
    def validate_python_source(source_code: str) -> None:
        if len(source_code.encode("utf-8")) > 256 * 1024:
            raise EducationSuiteError("Source code exceeds the 256 KiB classroom limit.")
        try:
            tree = ast.parse(source_code)
        except SyntaxError as exc:
            raise EducationSuiteError(f"Python syntax error: {exc}") from exc
        blocked = {"os", "subprocess", "socket", "ctypes", "multiprocessing", "resource", "winreg"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in blocked:
                        raise EducationSuiteError(f"Import blocked in local classroom runner: {alias.name}")
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in blocked:
                raise EducationSuiteError(f"Import blocked in local classroom runner: {node.module}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "compile", "__import__", "open"}:
                raise EducationSuiteError(f"Function blocked in local classroom runner: {node.func.id}")

    @classmethod
    def run_python(cls, source_code: str, stdin_text: str = "", timeout: float = 4.0) -> CodeRunResult:
        cls.validate_python_source(source_code)
        with tempfile.TemporaryDirectory(prefix="biointel-education-code-") as temp_dir:
            script = Path(temp_dir) / "submission.py"
            script.write_text(source_code, encoding="utf-8", newline="\n")
            try:
                environment = os.environ.copy()
                environment.pop("PYTHONPATH", None)
                environment.pop("PYTHONHOME", None)
                environment.update({
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "BIOINTEL_CODE_RUNNER": "1",
                })
                completed = subprocess.run(
                    [sys.executable, "-I", "-S", str(script)],
                    input=stdin_text,
                    capture_output=True,
                    text=True,
                    cwd=temp_dir,
                    timeout=max(0.5, min(float(timeout), 15.0)),
                    env=environment,
                    check=False,
                )
                return CodeRunResult(completed.returncode == 0, completed.stdout[-20000:], completed.stderr[-20000:], completed.returncode)
            except subprocess.TimeoutExpired as exc:
                return CodeRunResult(False, str(exc.stdout or "")[-20000:], "Execution timed out.", -1, True)

    @classmethod
    def grade_python(cls, source_code: str, tests: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        if not tests:
            raise EducationSuiteError("At least one code test is required.")
        results = []
        passed = 0
        for index, test in enumerate(tests, 1):
            run = cls.run_python(source_code, str(test.get("stdin", "")), float(test.get("timeout", 4.0)))
            expected = str(test.get("expected_stdout", "")).strip()
            actual = run.stdout.strip()
            ok = run.ok and actual == expected
            passed += int(ok)
            results.append({"test": index, "passed": ok, "expected": expected, "actual": actual,
                            "stderr": run.stderr, "timed_out": run.timed_out})
        return {"passed": passed, "total": len(tests), "score": passed / len(tests) * 100.0, "tests": results}

    def create_code_task(self, institution_id: str, subject_id: str, title: str, prompt: str,
                         tests: Sequence[Mapping[str, Any]], created_by: str) -> dict[str, Any]:
        if not title.strip() or not prompt.strip():
            raise EducationSuiteError("Code task title and prompt are required.")
        task_id = _identifier("code")
        with self.connection() as db:
            db.execute("INSERT INTO code_tasks VALUES(?,?,?,?,?,?,?,?,?)",
                       (task_id, institution_id, subject_id, title.strip(), prompt.strip(), _json(list(tests)),
                        "python", created_by, _now()))
            row = db.execute("SELECT * FROM code_tasks WHERE id=?", (task_id,)).fetchone()
        result = dict(row)
        result["tests"] = _load_json(result.pop("tests_json"), [])
        return result

    def list_code_tasks(self, institution_id: str, subject_id: str = "") -> list[dict[str, Any]]:
        query = "SELECT * FROM code_tasks WHERE institution_id=?"
        args: list[Any] = [institution_id]
        if subject_id:
            query += " AND subject_id=?"
            args.append(subject_id)
        query += " ORDER BY created_at DESC"
        with self.connection() as db:
            rows = db.execute(query, args).fetchall()
        result = self._rows(rows)
        for item in result:
            item["tests"] = _load_json(item.pop("tests_json"), [])
        return result

    def submit_code(self, task_id: str, learner_id: str, source_code: str) -> dict[str, Any]:
        with self.connection() as db:
            task = db.execute("SELECT * FROM code_tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise EducationSuiteError("Code task not found.")
        tests = _load_json(task["tests_json"], [])
        result = self.grade_python(source_code, tests)
        submission_id = _identifier("codesub")
        with self.connection() as db:
            db.execute("INSERT INTO code_submissions VALUES(?,?,?,?,?,?,?,?)",
                       (submission_id, task_id, learner_id, source_code, _json(result), result["score"], 100.0, _now()))
        self.track_event(task["institution_id"], learner_id, "code_submitted", "code_task", task_id,
                         {"score": result["score"]})
        return {"id": submission_id, **result}

    @classmethod
    def grade_notebook(cls, notebook_data: bytes, tests: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        try:
            notebook = json.loads(notebook_data.decode("utf-8-sig"))
        except Exception as exc:
            raise EducationSuiteError(f"Invalid notebook file: {exc}") from exc
        cells = notebook.get("cells", [])
        code = "\n\n".join("".join(cell.get("source", [])) for cell in cells if cell.get("cell_type") == "code")
        if not code.strip():
            raise EducationSuiteError("Notebook has no code cells.")
        result = cls.grade_python(code, tests)
        result["code_cells"] = sum(1 for cell in cells if cell.get("cell_type") == "code")
        return result

    @staticmethod
    def _normalized_tokens(source_code: str) -> list[str]:
        try:
            stream = io.BytesIO(source_code.encode("utf-8")).readline
            tokens = []
            for token in tokenize.tokenize(stream):
                if token.type in {tokenize.ENCODING, tokenize.ENDMARKER, tokenize.NEWLINE, tokenize.NL,
                                  tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT}:
                    continue
                if token.type == tokenize.NAME and token.string not in {
                    "def", "class", "return", "if", "else", "elif", "for", "while", "in", "import", "from",
                    "try", "except", "with", "as", "True", "False", "None", "and", "or", "not", "break", "continue",
                }:
                    tokens.append("NAME")
                elif token.type == tokenize.NUMBER:
                    tokens.append("NUMBER")
                elif token.type == tokenize.STRING:
                    tokens.append("STRING")
                else:
                    tokens.append(token.string)
            return tokens
        except (tokenize.TokenError, UnicodeError):
            return re.findall(r"\w+|[^\w\s]", source_code)

    @classmethod
    def code_similarity(cls, left: str, right: str, shingle_size: int = 5) -> dict[str, Any]:
        def shingles(tokens: Sequence[str]) -> set[tuple[str, ...]]:
            if len(tokens) < shingle_size:
                return {tuple(tokens)} if tokens else set()
            return {tuple(tokens[index:index + shingle_size]) for index in range(len(tokens) - shingle_size + 1)}
        a = shingles(cls._normalized_tokens(left))
        b = shingles(cls._normalized_tokens(right))
        union = a | b
        similarity = len(a & b) / len(union) if union else 1.0
        return {
            "similarity": round(similarity * 100.0, 2),
            "shared_fingerprints": len(a & b),
            "left_fingerprints": len(a),
            "right_fingerprints": len(b),
            "interpretation": "Review recommended" if similarity >= 70 else "Moderate overlap" if similarity >= 40 else "Low overlap",
            "note": "Similarity is a review indicator, not a plagiarism verdict.",
        }

    # ---------- Resumes, documents and credentials ----------
    def save_resume(self, owner_id: str, name: str, headline: str, profile: Mapping[str, Any], resume_id: str = "") -> dict[str, Any]:
        if not name.strip():
            raise EducationSuiteError("Resume name is required.")
        timestamp = _now()
        with self.connection() as db:
            if resume_id:
                db.execute("UPDATE resume_profiles SET name=?,headline=?,profile_json=?,updated_at=? WHERE id=? AND owner_id=?",
                           (name.strip(), headline.strip(), _json(dict(profile)), timestamp, resume_id, owner_id))
            else:
                resume_id = _identifier("resume")
                db.execute("INSERT INTO resume_profiles VALUES(?,?,?,?,?,?,?)",
                           (resume_id, owner_id, name.strip(), headline.strip(), _json(dict(profile)), timestamp, timestamp))
            row = db.execute("SELECT * FROM resume_profiles WHERE id=?", (resume_id,)).fetchone()
        result = dict(row)
        result["profile"] = _load_json(result.pop("profile_json"), {})
        return result

    def list_resumes(self, owner_id: str) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM resume_profiles WHERE owner_id=? ORDER BY updated_at DESC", (owner_id,)).fetchall()
        result = self._rows(rows)
        for item in result:
            item["profile"] = _load_json(item.pop("profile_json"), {})
        return result

    @staticmethod
    def resume_markdown(resume: Mapping[str, Any]) -> str:
        profile = dict(resume.get("profile", {}))
        lines = [f"# {resume.get('name', 'Profile')}", str(resume.get("headline", "")).strip(), ""]
        for key, heading in (("summary", "Professional summary"), ("education", "Education"), ("skills", "Skills"),
                             ("projects", "Projects"), ("experience", "Experience"), ("publications", "Publications"),
                             ("awards", "Awards"), ("links", "Links")):
            value = profile.get(key)
            if not value:
                continue
            lines.extend([f"## {heading}"])
            if isinstance(value, list):
                lines.extend(f"- {item}" for item in value)
            else:
                lines.append(str(value))
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def save_application_document(self, owner_id: str, document_type: str, title: str, body: str,
                                  opportunity_id: str = "", document_id: str = "") -> dict[str, Any]:
        if not title.strip() or not body.strip():
            raise EducationSuiteError("Document title and body are required.")
        timestamp = _now()
        with self.connection() as db:
            if document_id:
                db.execute("UPDATE application_documents SET document_type=?,title=?,body=?,opportunity_id=?,updated_at=? WHERE id=? AND owner_id=?",
                           (document_type, title.strip(), body, opportunity_id, timestamp, document_id, owner_id))
            else:
                document_id = _identifier("doc")
                db.execute("INSERT INTO application_documents VALUES(?,?,?,?,?,?,?,?)",
                           (document_id, owner_id, document_type, title.strip(), body, opportunity_id, timestamp, timestamp))
            row = db.execute("SELECT * FROM application_documents WHERE id=?", (document_id,)).fetchone()
        return dict(row)

    def list_application_documents(self, owner_id: str) -> list[dict[str, Any]]:
        with self.connection() as db:
            return self._rows(db.execute("SELECT * FROM application_documents WHERE owner_id=? ORDER BY updated_at DESC", (owner_id,)).fetchall())

    def issue_credential(self, institution_id: str, recipient_id: str, title: str, credential_type: str,
                         evidence: str, issuer: str, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if not title.strip() or not issuer.strip():
            raise EducationSuiteError("Credential title and issuer are required.")
        credential_id = _identifier("credential")
        with self.connection() as db:
            db.execute("INSERT INTO credentials VALUES(?,?,?,?,?,?,?,?,?)",
                       (credential_id, institution_id, recipient_id, title.strip(), credential_type.strip(), evidence.strip(),
                        issuer.strip(), _json(dict(metadata or {})), _now()))
            row = db.execute("SELECT * FROM credentials WHERE id=?", (credential_id,)).fetchone()
        result = dict(row)
        result["metadata"] = _load_json(result.pop("metadata_json"), {})
        return result

    def list_credentials(self, institution_id: str, recipient_id: str = "") -> list[dict[str, Any]]:
        query = "SELECT * FROM credentials WHERE institution_id=?"
        args: list[Any] = [institution_id]
        if recipient_id:
            query += " AND recipient_id=?"
            args.append(recipient_id)
        query += " ORDER BY issued_at DESC"
        with self.connection() as db:
            rows = db.execute(query, args).fetchall()
        result = self._rows(rows)
        for item in result:
            item["metadata"] = _load_json(item.pop("metadata_json"), {})
        return result

    # ---------- Unified search and interchange ----------
    def search(self, institution_id: str, query: str, limit: int = 100) -> list[dict[str, Any]]:
        token = f"%{query.strip()}%"
        if not query.strip():
            return []
        statements = [
            ("lesson", "SELECT id,title,description body,updated_at stamp FROM lessons WHERE institution_id=? AND (title LIKE ? OR description LIKE ?)"),
            ("note", "SELECT id,title,body,updated_at stamp FROM notes WHERE institution_id=? AND (title LIKE ? OR body LIKE ?)"),
            ("question", "SELECT id,prompt title,explanation body,updated_at stamp FROM questions WHERE institution_id=? AND (prompt LIKE ? OR explanation LIKE ?)"),
            ("qa", "SELECT id,title,body,updated_at stamp FROM qa_questions WHERE institution_id=? AND (title LIKE ? OR body LIKE ?)"),
            ("resource", "SELECT id,title,description body,created_at stamp FROM offline_resources WHERE institution_id=? AND (title LIKE ? OR description LIKE ?)"),
        ]
        results: list[dict[str, Any]] = []
        with self.connection() as db:
            for kind, sql in statements:
                for row in db.execute(sql, (institution_id, token, token)).fetchall():
                    item = dict(row)
                    item["kind"] = kind
                    results.append(item)
        return sorted(results, key=lambda item: item.get("stamp", ""), reverse=True)[:max(1, min(limit, 500))]

    @staticmethod
    def roster_from_csv(data: bytes) -> list[dict[str, str]]:
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        required = {"user_id", "name", "role"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise EducationSuiteError("Roster CSV requires user_id,name,role columns.")
        return [{key: str(value or "").strip() for key, value in row.items()} for row in reader]

    @staticmethod
    def gradebook_csv(rows: Sequence[Mapping[str, Any]]) -> bytes:
        columns = ["learner_id", "assessment_id", "score", "max_score", "submitted_at"]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
        return output.getvalue().encode("utf-8-sig")


__all__ = ["CodeRunResult", "EducationSuiteError", "EducationSuiteService", "default_suite_root"]
