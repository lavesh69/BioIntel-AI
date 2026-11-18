from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .examination import SecureExaminationService
from .permissions import PermissionService
from .phase4 import EducationPhase4Service
from .phase5 import EducationPhase5Service
from .platform import Conflict, Denied, EducationError, Missing, ident, now, parse_time

MIGRATION_ID = "education_phase6_visual_operations_v1"

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS education_ui_preferences(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 user_id TEXT NOT NULL,
 theme TEXT NOT NULL DEFAULT 'dark',
 density TEXT NOT NULL DEFAULT 'comfortable',
 font_scale REAL NOT NULL DEFAULT 1.0,
 high_contrast INTEGER NOT NULL DEFAULT 0,
 reduced_motion INTEGER NOT NULL DEFAULT 0,
 dyslexia_mode INTEGER NOT NULL DEFAULT 0,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,user_id)
);
CREATE TABLE IF NOT EXISTS education_page_activity(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 user_id TEXT NOT NULL,
 page_key TEXT NOT NULL,
 visited_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_education_page_activity_user
 ON education_page_activity(institution_id,user_id,visited_at);
CREATE TABLE IF NOT EXISTS education_page_favorites(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 user_id TEXT NOT NULL,
 page_key TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(institution_id,user_id,page_key)
);
CREATE TABLE IF NOT EXISTS education_shiro_conversations(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 subject_id TEXT REFERENCES subjects(id),
 user_id TEXT NOT NULL,
 title TEXT NOT NULL,
 mode TEXT NOT NULL DEFAULT 'guided_learning',
 language TEXT NOT NULL DEFAULT 'English',
 state TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_shiro_messages(
 id TEXT PRIMARY KEY,
 conversation_id TEXT NOT NULL REFERENCES education_shiro_conversations(id),
 role TEXT NOT NULL,
 body TEXT NOT NULL,
 evidence_status TEXT NOT NULL DEFAULT '',
 citations_json TEXT NOT NULL DEFAULT '[]',
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_education_shiro_messages_conversation
 ON education_shiro_messages(conversation_id,created_at);
CREATE TABLE IF NOT EXISTS education_workers(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 worker_id TEXT NOT NULL,
 queue_names_json TEXT NOT NULL DEFAULT '["default"]',
 state TEXT NOT NULL DEFAULT 'online',
 current_job_id TEXT NOT NULL DEFAULT '',
 version TEXT NOT NULL DEFAULT '',
 last_heartbeat_at TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,worker_id)
);
CREATE TABLE IF NOT EXISTS education_job_progress(
 job_id TEXT PRIMARY KEY REFERENCES education_background_jobs(id),
 progress_percent REAL NOT NULL DEFAULT 0,
 progress_message TEXT NOT NULL DEFAULT '',
 cancel_requested INTEGER NOT NULL DEFAULT 0,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_backup_schedules(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 name TEXT NOT NULL,
 frequency TEXT NOT NULL,
 hour_utc INTEGER NOT NULL DEFAULT 2,
 weekday INTEGER,
 retention_count INTEGER NOT NULL DEFAULT 14,
 include_media INTEGER NOT NULL DEFAULT 1,
 state TEXT NOT NULL DEFAULT 'active',
 last_enqueued_at TEXT,
 next_run_at TEXT NOT NULL,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,name)
);
CREATE TABLE IF NOT EXISTS education_integration_sync_runs(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 integration_id TEXT NOT NULL REFERENCES education_integrations(id),
 direction TEXT NOT NULL DEFAULT 'pull',
 entity_type TEXT NOT NULL DEFAULT 'courses',
 state TEXT NOT NULL DEFAULT 'queued',
 created_count INTEGER NOT NULL DEFAULT 0,
 updated_count INTEGER NOT NULL DEFAULT 0,
 failed_count INTEGER NOT NULL DEFAULT 0,
 detail_json TEXT NOT NULL DEFAULT '{}',
 started_by TEXT NOT NULL,
 started_at TEXT NOT NULL,
 finished_at TEXT
);
CREATE TABLE IF NOT EXISTS education_saved_views(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 user_id TEXT NOT NULL,
 module_key TEXT NOT NULL,
 name TEXT NOT NULL,
 filters_json TEXT NOT NULL DEFAULT '{}',
 columns_json TEXT NOT NULL DEFAULT '[]',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,user_id,module_key,name)
);
INSERT OR IGNORE INTO education_migrations(id,applied_at)
 VALUES('education_phase6_visual_operations_v1',datetime('now'));
"""


def _decode(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError):
        return fallback


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _pct(value: float, total: float) -> float:
    return round((value / total * 100.0), 2) if total else 0.0


class EducationPhase6Service:
    """Visual operations, usability and local-first workflow orchestration for Phase 6."""

    def __init__(self, platform: Any, *, root: Any = None):
        self.platform = platform
        self.db = platform.db
        self.permissions = PermissionService(platform)
        self.phase4 = EducationPhase4Service(platform, root=root)
        self.phase5 = EducationPhase5Service(platform, root=root)
        self.exams = SecureExaminationService(platform)
        from .phase6_adapters import ExternalQualificationService
        self.external = ExternalQualificationService(platform)
        self.migrate()

    def migrate(self) -> str:
        with self.db.connection() as db:
            db.executescript(SCHEMA)
        return MIGRATION_ID

    def _membership(self, actor: str, institution_id: str) -> set[str]:
        rows = self.platform._require(actor, institution_id)
        return {str(row["role"]) for row in rows}

    # ---------- experience preferences and navigation ----------
    def preferences(self, actor: str, institution_id: str) -> dict[str, Any]:
        self._membership(actor, institution_id)
        row = self.platform._one(
            "SELECT * FROM education_ui_preferences WHERE institution_id=? AND user_id=?",
            (institution_id, actor),
        )
        return row or {
            "institution_id": institution_id,
            "user_id": actor,
            "theme": "dark",
            "density": "comfortable",
            "font_scale": 1.0,
            "high_contrast": 0,
            "reduced_motion": 0,
            "dyslexia_mode": 0,
        }

    def save_preferences(
        self,
        actor: str,
        institution_id: str,
        *,
        theme: str = "dark",
        density: str = "comfortable",
        font_scale: float = 1.0,
        high_contrast: bool = False,
        reduced_motion: bool = False,
        dyslexia_mode: bool = False,
    ) -> dict[str, Any]:
        self._membership(actor, institution_id)
        if theme not in {"dark", "light", "system"}:
            raise EducationError("Unsupported theme.")
        if density not in {"compact", "comfortable"}:
            raise EducationError("Unsupported density.")
        scale = min(1.5, max(0.85, float(font_scale)))
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_ui_preferences
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,user_id) DO UPDATE SET
                theme=excluded.theme,density=excluded.density,font_scale=excluded.font_scale,
                high_contrast=excluded.high_contrast,reduced_motion=excluded.reduced_motion,
                dyslexia_mode=excluded.dyslexia_mode,updated_at=excluded.updated_at""",
                (
                    ident("uipref"), institution_id, actor, theme, density, scale,
                    int(high_contrast), int(reduced_motion), int(dyslexia_mode), stamp,
                ),
            )
        return self.preferences(actor, institution_id)

    def record_visit(self, actor: str, institution_id: str, page_key: str) -> None:
        self._membership(actor, institution_id)
        page = str(page_key).strip().lower()[:80]
        if not page:
            return
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_page_activity VALUES(?,?,?,?,?)",
                (ident("visit"), institution_id, actor, page, now()),
            )
            db.execute(
                """DELETE FROM education_page_activity WHERE id IN (
                SELECT id FROM education_page_activity WHERE institution_id=? AND user_id=?
                ORDER BY visited_at DESC LIMIT -1 OFFSET 80)""",
                (institution_id, actor),
            )

    def toggle_favorite(self, actor: str, institution_id: str, page_key: str) -> bool:
        self._membership(actor, institution_id)
        existing = self.platform._one(
            "SELECT id FROM education_page_favorites WHERE institution_id=? AND user_id=? AND page_key=?",
            (institution_id, actor, page_key),
        )
        with self.db.connection() as db:
            if existing:
                db.execute("DELETE FROM education_page_favorites WHERE id=?", (existing["id"],))
                return False
            db.execute(
                "INSERT INTO education_page_favorites VALUES(?,?,?,?,?)",
                (ident("fav"), institution_id, actor, page_key, now()),
            )
        return True

    def navigation_state(self, actor: str, institution_id: str) -> dict[str, list[str]]:
        self._membership(actor, institution_id)
        favorites = self.platform._all(
            "SELECT page_key FROM education_page_favorites WHERE institution_id=? AND user_id=? ORDER BY created_at",
            (institution_id, actor),
        )
        recent = self.platform._all(
            """SELECT page_key,MAX(visited_at) last_visit FROM education_page_activity
            WHERE institution_id=? AND user_id=? GROUP BY page_key ORDER BY last_visit DESC LIMIT 6""",
            (institution_id, actor),
        )
        return {
            "favorites": [row["page_key"] for row in favorites],
            "recent": [row["page_key"] for row in recent],
        }

    def save_view(self, actor: str, institution_id: str, module_key: str, name: str, filters: dict[str, Any], columns: list[str]) -> dict[str, Any]:
        self._membership(actor, institution_id)
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_saved_views VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,user_id,module_key,name) DO UPDATE SET
                filters_json=excluded.filters_json,columns_json=excluded.columns_json,updated_at=excluded.updated_at""",
                (ident("view"), institution_id, actor, module_key[:80], name[:120], _json(filters), _json(columns), stamp, stamp),
            )
        return self.platform._one(
            "SELECT * FROM education_saved_views WHERE institution_id=? AND user_id=? AND module_key=? AND name=?",
            (institution_id, actor, module_key[:80], name[:120]),
        )

    # ---------- visual classroom operations ----------
    def timetable_calendar(self, actor: str, institution_id: str, *, start_day: str | date | None = None, days: int = 7) -> dict[str, Any]:
        roles = self._membership(actor, institution_id)
        self.permissions.require(actor, institution_id, "classroom.view")
        start = date.fromisoformat(start_day) if isinstance(start_day, str) else (start_day or datetime.now(timezone.utc).date())
        end = start + timedelta(days=max(1, min(int(days), 31)))
        params: list[Any] = [institution_id, start.isoformat(), end.isoformat()]
        condition = ""
        if roles & {"school_student", "college_student", "university_student"}:
            condition = " AND EXISTS(SELECT 1 FROM enrollments en WHERE en.subject_id=t.subject_id AND en.student_id=? AND en.state='active')"
            params.append(actor)
        elif not self.permissions.has(actor, institution_id, "timetable.manage"):
            condition = " AND t.teacher_id=?"
            params.append(actor)
        rows = self.platform._all(
            f"""SELECT t.*,s.code subject_code,s.name subject_name
            FROM timetable_entries t LEFT JOIN subjects s ON s.id=t.subject_id
            WHERE t.institution_id=? AND date(t.starts_at)>=? AND date(t.starts_at)<? {condition}
            ORDER BY t.starts_at""",
            tuple(params),
        )
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row["starts_at"])[:10]].append(row)
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": [(start + timedelta(days=offset)).isoformat() for offset in range((end - start).days)],
            "entries": rows,
            "by_day": dict(grouped),
        }

    def gradebook(self, actor: str, institution_id: str, subject_id: str) -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "classroom.view")
        subject = self.platform._one("SELECT * FROM subjects WHERE id=? AND institution_id=?", (subject_id, institution_id))
        if not subject:
            raise Missing("Subject not found.")
        roles = self._membership(actor, institution_id)
        is_student = bool(roles & {"school_student", "college_student", "university_student"})
        if is_student:
            enrolled = self.platform._one("SELECT id FROM enrollments WHERE subject_id=? AND student_id=? AND state='active'", (subject_id, actor))
            if not enrolled:
                raise Denied("Subject access denied.")
        elif not self.permissions.has(actor, institution_id, "classroom.manage"):
            assigned = self.platform._one("SELECT id FROM teacher_assignments WHERE subject_id=? AND teacher_id=? AND state='active'", (subject_id, actor))
            if not assigned:
                raise Denied("Subject access denied.")
        assignments = self.platform._all(
            "SELECT id,title,max_marks,due_at,state FROM assignments WHERE institution_id=? AND subject_id=? ORDER BY due_at",
            (institution_id, subject_id),
        )
        students = self.platform._all(
            "SELECT student_id FROM enrollments WHERE institution_id=? AND subject_id=? AND state='active' ORDER BY student_id",
            (institution_id, subject_id),
        )
        if is_student:
            students = [{"student_id": actor}]
        rows: list[dict[str, Any]] = []
        distributions: dict[str, list[float]] = defaultdict(list)
        for student in students:
            entry: dict[str, Any] = {"student_id": student["student_id"]}
            earned = 0.0
            possible = 0.0
            released = 0
            for assignment in assignments:
                result = self.platform._one(
                    """SELECT s.state submission_state,s.late,g.marks,g.state grade_state
                    FROM submissions s LEFT JOIN grades g ON g.submission_id=s.id
                    WHERE s.assignment_id=? AND s.student_id=?""",
                    (assignment["id"], student["student_id"]),
                )
                marks = None if not result or result.get("marks") is None else float(result["marks"])
                key = assignment["title"][:40]
                entry[key] = marks
                if marks is not None:
                    earned += marks
                    possible += float(assignment["max_marks"])
                    released += 1
                    distributions[assignment["id"]].append(_pct(marks, float(assignment["max_marks"])))
            entry["overall_percent"] = _pct(earned, possible)
            entry["graded_items"] = released
            rows.append(entry)
        assignment_stats = []
        for assignment in assignments:
            values = distributions.get(assignment["id"], [])
            assignment_stats.append({
                "assignment_id": assignment["id"],
                "title": assignment["title"],
                "max_marks": assignment["max_marks"],
                "graded": len(values),
                "average_percent": round(sum(values) / len(values), 2) if values else None,
                "minimum_percent": min(values) if values else None,
                "maximum_percent": max(values) if values else None,
            })
        return {"subject": subject, "assignments": assignments, "rows": rows, "assignment_stats": assignment_stats}

    def attendance_heatmap(self, actor: str, institution_id: str, *, subject_id: str | None = None) -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "classroom.view")
        roles = self._membership(actor, institution_id)
        params: list[Any] = [institution_id]
        subject_sql = ""
        if subject_id:
            subject_sql = " AND x.subject_id=?"
            params.append(subject_id)
        student_sql = ""
        if roles & {"school_student", "college_student", "university_student"}:
            student_sql = " AND r.student_id=?"
            params.append(actor)
        rows = self.platform._all(
            f"""SELECT r.student_id,s.session_date,x.subject_id,sub.code subject_code,r.status
            FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id
            JOIN attendance_sessions x ON x.id=r.session_id
            LEFT JOIN subjects sub ON sub.id=x.subject_id
            WHERE r.institution_id=? {subject_sql} {student_sql}
            ORDER BY s.session_date""",
            tuple(params),
        )
        counts: dict[str, Counter[str]] = defaultdict(Counter)
        for row in rows:
            counts[row["student_id"]][row["status"]] += 1
        summary = []
        for student_id, values in counts.items():
            total = sum(values.values())
            present = values.get("present", 0) + values.get("late", 0) + values.get("excused", 0)
            summary.append({"student_id": student_id, "attendance_percent": _pct(present, total), **dict(values)})
        return {"records": rows, "summary": summary}

    # ---------- examination intelligence ----------
    def exam_analytics(self, actor: str, exam_id: str) -> dict[str, Any]:
        exam = self.exams._exam(exam_id)
        self.permissions.require(actor, exam["institution_id"], "exam.monitor")
        questions = self.platform._all(
            "SELECT id,question_type,marks,negative_marks,difficulty,bloom_level FROM education_exam_questions WHERE exam_id=? AND state='active' ORDER BY position",
            (exam_id,),
        )
        sessions = self.platform._all(
            "SELECT * FROM education_exam_sessions WHERE exam_id=? ORDER BY started_at",
            (exam_id,),
        )
        scores = self.platform._all(
            "SELECT * FROM education_exam_scores WHERE exam_id=? ORDER BY final_score DESC",
            (exam_id,),
        )
        values = [float(row["final_score"]) for row in scores]
        max_marks = float(exam["max_marks"] or 0)
        pass_mark = max_marks * 0.4
        histogram = [0] * 10
        for value in values:
            index = min(9, max(0, int((_pct(value, max_marks) or 0) // 10)))
            histogram[index] += 1
        question_rows = []
        for question in questions:
            answers = self.platform._all(
                """SELECT a.answer_json,s.final_score FROM education_exam_answers a
                JOIN education_exam_sessions es ON es.id=a.session_id
                LEFT JOIN education_exam_scores s ON s.session_id=es.id
                WHERE es.exam_id=? AND a.question_id=?""",
                (exam_id, question["id"]),
            )
            blank = sum(1 for row in answers if _decode(row["answer_json"], None) in (None, "", []))
            question_rows.append({
                **question,
                "responses": len(answers),
                "blank_rate": _pct(blank, len(answers)),
            })
        state_counts = Counter(str(row["state"]) for row in sessions)
        bloom = Counter(str(row["bloom_level"]) for row in questions)
        difficulty = Counter(str(row["difficulty"]) for row in questions)
        return {
            "exam": exam,
            "sessions": sessions,
            "scores": scores,
            "question_rows": question_rows,
            "summary": {
                "candidates": len(sessions),
                "submitted": state_counts.get("submitted", 0),
                "active": state_counts.get("active", 0),
                "average_score": round(sum(values) / len(values), 2) if values else None,
                "average_percent": round(sum(_pct(v, max_marks) for v in values) / len(values), 2) if values else None,
                "pass_rate": _pct(sum(1 for value in values if value >= pass_mark), len(values)),
                "highest": max(values) if values else None,
                "lowest": min(values) if values else None,
            },
            "histogram": histogram,
            "bloom_distribution": dict(bloom),
            "difficulty_distribution": dict(difficulty),
            "state_distribution": dict(state_counts),
        }

    # ---------- Shiro conversation and knowledge graph ----------
    def create_conversation(self, actor: str, institution_id: str, *, subject_id: str | None, title: str, mode: str = "guided_learning", language: str = "English") -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "shiro.tutor")
        if not subject_id:
            raise EducationError("A subject is required for a grounded Shiro conversation.")
        self.phase4._subject_access(actor, institution_id, subject_id)
        allowed_modes = {"guided_learning", "revision", "teacher_planning"}
        if mode not in allowed_modes:
            raise EducationError("Unsupported Shiro conversation mode.")
        allowed_languages = {"English", "Hindi", "Hinglish"}
        if language not in allowed_languages:
            raise EducationError("Unsupported Shiro response language.")
        stamp = now()
        conversation_id = ident("chat")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_shiro_conversations VALUES(?,?,?,?,?,?,?,?,?,?)",
                (conversation_id, institution_id, subject_id, actor, title[:160] or "New conversation", mode, language, "active", stamp, stamp),
            )
        return self.conversation(actor, conversation_id)

    def conversation(self, actor: str, conversation_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_shiro_conversations WHERE id=?", (conversation_id,))
        if not row:
            raise Missing("Conversation not found.")
        if row["user_id"] != actor and not self.permissions.has(actor, row["institution_id"], "shiro.manage"):
            raise Denied("Conversation access denied.")
        messages = self.platform._all("SELECT * FROM education_shiro_messages WHERE conversation_id=? ORDER BY created_at", (conversation_id,))
        for message in messages:
            message["citations"] = _decode(message.pop("citations_json", "[]"), [])
        return {**row, "messages": messages}

    def conversations(self, actor: str, institution_id: str, *, limit: int = 30) -> list[dict[str, Any]]:
        self.permissions.require(actor, institution_id, "shiro.tutor")
        return self.platform._all(
            """SELECT c.*,COUNT(m.id) message_count FROM education_shiro_conversations c
            LEFT JOIN education_shiro_messages m ON m.conversation_id=c.id
            WHERE c.institution_id=? AND c.user_id=? AND c.state='active'
            GROUP BY c.id ORDER BY c.updated_at DESC LIMIT ?""",
            (institution_id, actor, max(1, min(int(limit), 100))),
        )

    def ask_conversation(self, actor: str, conversation_id: str, question: str) -> dict[str, Any]:
        conversation = self.conversation(actor, conversation_id)
        prompt = str(question).strip()
        if not prompt:
            raise EducationError("Question is required.")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_shiro_messages VALUES(?,?,?,?,?,?,?)",
                (ident("msg"), conversation_id, "user", prompt, "", "[]", stamp),
            )
        response = self.phase4.ask_tutor(
            actor,
            conversation["institution_id"],
            conversation["subject_id"],
            prompt,
            response_language=conversation["language"],
            policy_mode={"guided_learning": "guided"}.get(conversation["mode"], conversation["mode"]),
        )
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_shiro_messages VALUES(?,?,?,?,?,?,?)",
                (
                    ident("msg"), conversation_id, "assistant", response["answer"],
                    response.get("evidence_status", ""), _json(response.get("citations", [])), now(),
                ),
            )
            db.execute("UPDATE education_shiro_conversations SET updated_at=? WHERE id=?", (now(), conversation_id))
        return self.conversation(actor, conversation_id)

    def knowledge_graph(self, actor: str, institution_id: str, *, student_id: str | None = None, subject_id: str | None = None) -> dict[str, Any]:
        snapshot = self.phase4.learner_snapshot(actor, institution_id, student_id, subject_id)
        nodes = []
        edges = []
        for item in snapshot.get("concepts", []):
            concept = item.get("concept", item)
            state = item.get("mastery_state") or item.get("state") or item
            concept_id = concept.get("id") or concept.get("concept_id")
            nodes.append({
                "id": concept_id,
                "label": concept.get("title") or concept.get("code") or concept_id,
                "code": concept.get("code", ""),
                "mastery": float(state.get("mastery", 0) or 0),
                "confidence": float(state.get("confidence", 0) or 0),
                "difficulty": concept.get("difficulty", "medium"),
            })
            prerequisites = concept.get("prerequisite_ids") or _decode(concept.get("prerequisite_ids_json", "[]"), [])
            for prerequisite in prerequisites:
                edges.append({"source": prerequisite, "target": concept_id})
        return {"nodes": nodes, "edges": edges, "recommendations": snapshot.get("recommendations", []), "student_id": snapshot.get("student_id")}

    # ---------- workers, backups and integration operations ----------
    def register_worker(self, actor: str, institution_id: str, worker_id: str, *, queues: list[str] | None = None, version: str = "") -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "institution.manage")
        queues = [str(item).strip() for item in (queues or ["default"]) if str(item).strip()]
        if not queues:
            raise EducationError("At least one queue is required.")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_workers VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,worker_id) DO UPDATE SET
                queue_names_json=excluded.queue_names_json,state='online',version=excluded.version,
                last_heartbeat_at=excluded.last_heartbeat_at,updated_at=excluded.updated_at""",
                (ident("worker"), institution_id, worker_id[:120], _json(queues), "online", "", version[:80], stamp, stamp, stamp),
            )
        return self.platform._one("SELECT * FROM education_workers WHERE institution_id=? AND worker_id=?", (institution_id, worker_id[:120]))

    def worker_heartbeat(self, institution_id: str, worker_id: str, *, current_job_id: str = "", state: str = "online") -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_workers WHERE institution_id=? AND worker_id=?", (institution_id, worker_id))
        if not row:
            raise Missing("Worker is not registered.")
        if state not in {"online", "busy", "draining", "offline"}:
            raise EducationError("Unsupported worker state.")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                "UPDATE education_workers SET state=?,current_job_id=?,last_heartbeat_at=?,updated_at=? WHERE id=?",
                (state, current_job_id, stamp, stamp, row["id"]),
            )
        return self.platform._one("SELECT * FROM education_workers WHERE id=?", (row["id"],))

    def update_job_progress(self, institution_id: str, worker_id: str, job_id: str, lock_token: str, percent: float, message: str = "") -> dict[str, Any]:
        job = self.platform._one("SELECT * FROM education_background_jobs WHERE id=? AND institution_id=?", (job_id, institution_id))
        if not job:
            raise Missing("Job not found.")
        if job["state"] != "running" or job["locked_by"] != worker_id or job["lock_token"] != lock_token:
            raise Denied("Worker does not own this job lock.")
        value = min(100.0, max(0.0, float(percent)))
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_job_progress VALUES(?,?,?,?,?)
                ON CONFLICT(job_id) DO UPDATE SET progress_percent=excluded.progress_percent,
                progress_message=excluded.progress_message,updated_at=excluded.updated_at""",
                (job_id, value, message[:500], 0, now()),
            )
        return self.platform._one("SELECT * FROM education_job_progress WHERE job_id=?", (job_id,))

    def cancel_job(self, actor: str, institution_id: str, job_id: str) -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "institution.manage")
        job = self.platform._one("SELECT * FROM education_background_jobs WHERE id=? AND institution_id=?", (job_id, institution_id))
        if not job:
            raise Missing("Job not found.")
        with self.db.connection() as db:
            if job["state"] == "queued":
                db.execute("UPDATE education_background_jobs SET state='cancelled',updated_at=? WHERE id=?", (now(), job_id))
            elif job["state"] == "running":
                db.execute(
                    """INSERT INTO education_job_progress VALUES(?,?,?,?,?)
                    ON CONFLICT(job_id) DO UPDATE SET cancel_requested=1,updated_at=excluded.updated_at""",
                    (job_id, 0.0, "Cancellation requested", 1, now()),
                )
            else:
                raise Conflict("Only queued or running jobs can be cancelled.")
        return self.job_operations(actor, institution_id)["jobs_by_id"][job_id]

    def requeue_job(self, actor: str, institution_id: str, job_id: str) -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "institution.manage")
        job = self.platform._one("SELECT * FROM education_background_jobs WHERE id=? AND institution_id=?", (job_id, institution_id))
        if not job:
            raise Missing("Job not found.")
        if job["state"] not in {"failed", "cancelled"}:
            raise Conflict("Only failed or cancelled jobs can be requeued.")
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_background_jobs SET state='queued',available_at=?,locked_by='',lock_token='',locked_at=NULL,
                error_text='',updated_at=? WHERE id=?""",
                (now(), now(), job_id),
            )
            db.execute("DELETE FROM education_job_progress WHERE job_id=?", (job_id,))
        return self.platform._one("SELECT * FROM education_background_jobs WHERE id=?", (job_id,))

    def job_operations(self, actor: str, institution_id: str) -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "institution.manage")
        workers = self.platform._all("SELECT * FROM education_workers WHERE institution_id=? ORDER BY last_heartbeat_at DESC", (institution_id,))
        jobs = self.platform._all(
            """SELECT j.*,p.progress_percent,p.progress_message,p.cancel_requested FROM education_background_jobs j
            LEFT JOIN education_job_progress p ON p.job_id=j.id WHERE j.institution_id=? ORDER BY j.created_at DESC LIMIT 300""",
            (institution_id,),
        )
        counts = Counter(str(row["state"]) for row in jobs)
        return {"workers": workers, "jobs": jobs, "counts": dict(counts), "jobs_by_id": {row["id"]: row for row in jobs}}

    def create_backup_schedule(self, actor: str, institution_id: str, name: str, *, frequency: str = "daily", hour_utc: int = 2, weekday: int | None = None, retention_count: int = 14, include_media: bool = True) -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "backup.manage")
        if frequency not in {"daily", "weekly"}:
            raise EducationError("Backup frequency must be daily or weekly.")
        hour = min(23, max(0, int(hour_utc)))
        if frequency == "weekly" and (weekday is None or not 0 <= int(weekday) <= 6):
            raise EducationError("Weekly backup requires weekday 0-6.")
        current = datetime.now(timezone.utc)
        candidate = current.replace(hour=hour, minute=0, second=0, microsecond=0)
        if candidate <= current:
            candidate += timedelta(days=1)
        if frequency == "weekly":
            while candidate.weekday() != int(weekday):
                candidate += timedelta(days=1)
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_backup_schedules VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,name) DO UPDATE SET frequency=excluded.frequency,
                hour_utc=excluded.hour_utc,weekday=excluded.weekday,retention_count=excluded.retention_count,
                include_media=excluded.include_media,state='active',next_run_at=excluded.next_run_at,
                updated_at=excluded.updated_at""",
                (
                    ident("backsched"), institution_id, name[:120], frequency, hour, weekday,
                    max(1, min(int(retention_count), 365)), int(include_media), "active", None,
                    candidate.isoformat(), actor, stamp, stamp,
                ),
            )
        return self.platform._one("SELECT * FROM education_backup_schedules WHERE institution_id=? AND name=?", (institution_id, name[:120]))

    def enqueue_due_backups(self, actor: str, institution_id: str) -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "backup.manage")
        due = self.platform._all(
            "SELECT * FROM education_backup_schedules WHERE institution_id=? AND state='active' AND next_run_at<=?",
            (institution_id, now()),
        )
        jobs = []
        for schedule in due:
            job = self.phase5.enqueue_job(
                actor, institution_id, "scheduled_backup",
                {"schedule_id": schedule["id"], "include_media": bool(schedule["include_media"]), "retention_count": schedule["retention_count"]},
                queue_name="backup", priority=90,
            )
            next_run = parse_time(schedule["next_run_at"]) + (timedelta(days=1) if schedule["frequency"] == "daily" else timedelta(days=7))
            with self.db.connection() as db:
                db.execute("UPDATE education_backup_schedules SET last_enqueued_at=?,next_run_at=?,updated_at=? WHERE id=?", (now(), next_run.isoformat(), now(), schedule["id"]))
            jobs.append(job)
        return {"scheduled": len(due), "jobs": jobs}

    def start_integration_sync(self, actor: str, integration_id: str, *, direction: str = "pull", entity_type: str = "courses") -> dict[str, Any]:
        integration = self.phase5.integration(actor, integration_id)
        self.permissions.require(actor, integration["institution_id"], "integrations.manage")
        if integration["state"] not in {"configuration_ready", "active"}:
            raise Conflict("Integration is not configuration-ready.")
        if direction not in {"pull", "push", "bidirectional"}:
            raise EducationError("Unsupported sync direction.")
        run_id = ident("sync")
        stamp = now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_integration_sync_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, integration["institution_id"], integration_id, direction, entity_type[:80], "queued", 0, 0, 0, "{}", actor, stamp, None),
            )
        job = self.phase5.enqueue_job(
            actor, integration["institution_id"], "integration_sync",
            {"sync_run_id": run_id, "integration_id": integration_id, "direction": direction, "entity_type": entity_type},
            queue_name="integrations", priority=70,
        )
        with self.db.connection() as db:
            db.execute("UPDATE education_integration_sync_runs SET detail_json=? WHERE id=?", (_json({"job_id": job["id"]}), run_id))
        return self.platform._one("SELECT * FROM education_integration_sync_runs WHERE id=?", (run_id,))

    def integration_operations(self, actor: str, institution_id: str) -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "integrations.manage")
        integrations = self.platform._all("SELECT * FROM education_integrations WHERE institution_id=? ORDER BY created_at DESC", (institution_id,))
        runs = self.platform._all("SELECT * FROM education_integration_sync_runs WHERE institution_id=? ORDER BY started_at DESC LIMIT 200", (institution_id,))
        for row in runs:
            row["detail"] = _decode(row.pop("detail_json", "{}"), {})
        return {"integrations": integrations, "runs": runs}

    def visual_dashboard(self, actor: str, institution_id: str) -> dict[str, Any]:
        roles = self._membership(actor, institution_id)
        today = datetime.now(timezone.utc).date()
        calendar = self.timetable_calendar(actor, institution_id, start_day=today, days=7)
        notifications = self.phase4.notification_inbox(actor, institution_id, limit=30) if self.permissions.has(actor, institution_id, "education.dashboard.view") else []
        audit = []
        if roles & {"platform_administrator", "institution_administrator", "principal", "dean", "registrar", "department_head"}:
            audit = self.platform._all("SELECT action,target_type,created_at FROM education_audit_events WHERE institution_id=? ORDER BY created_at DESC LIMIT 20", (institution_id,))
        return {
            "calendar": calendar,
            "notifications": notifications,
            "unread_notifications": sum(1 for row in notifications if row.get("state") == "unread"),
            "recent_activity": audit,
            "navigation": self.navigation_state(actor, institution_id),
        }
