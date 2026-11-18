from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .permissions import PermissionService
from .platform import ADMIN, STUDENT, TEACHER, Conflict, Denied, EducationError, Missing, ident, now, parse_time

MIGRATION_ID = "education_phase4_intelligence_operations_v1"

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS education_concepts(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 subject_id TEXT NOT NULL REFERENCES subjects(id),
 code TEXT NOT NULL,
 title TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 prerequisite_ids_json TEXT NOT NULL DEFAULT '[]',
 difficulty TEXT NOT NULL DEFAULT 'medium',
 state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(subject_id,code)
);
CREATE INDEX IF NOT EXISTS idx_education_concepts_subject
 ON education_concepts(institution_id,subject_id,state);
CREATE TABLE IF NOT EXISTS education_mastery_events(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 subject_id TEXT NOT NULL,
 student_id TEXT NOT NULL,
 concept_id TEXT NOT NULL REFERENCES education_concepts(id),
 evidence_type TEXT NOT NULL,
 evidence_id TEXT NOT NULL DEFAULT '',
 score REAL NOT NULL,
 weight REAL NOT NULL,
 occurred_at TEXT NOT NULL,
 recorded_by TEXT NOT NULL,
 detail_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_education_mastery_events_student
 ON education_mastery_events(institution_id,student_id,concept_id,occurred_at);
CREATE TABLE IF NOT EXISTS education_mastery_state(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 subject_id TEXT NOT NULL,
 student_id TEXT NOT NULL,
 concept_id TEXT NOT NULL REFERENCES education_concepts(id),
 mastery REAL NOT NULL DEFAULT 0,
 confidence REAL NOT NULL DEFAULT 0,
 evidence_count INTEGER NOT NULL DEFAULT 0,
 streak INTEGER NOT NULL DEFAULT 0,
 last_practiced_at TEXT,
 next_review_at TEXT,
 updated_at TEXT NOT NULL,
 UNIQUE(student_id,concept_id)
);
CREATE INDEX IF NOT EXISTS idx_education_mastery_review
 ON education_mastery_state(institution_id,student_id,next_review_at);
CREATE TABLE IF NOT EXISTS education_learning_recommendations(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 subject_id TEXT NOT NULL,
 student_id TEXT NOT NULL,
 concept_id TEXT REFERENCES education_concepts(id),
 recommendation_type TEXT NOT NULL,
 priority INTEGER NOT NULL DEFAULT 50,
 title TEXT NOT NULL,
 reason_json TEXT NOT NULL DEFAULT '{}',
 state TEXT NOT NULL DEFAULT 'open',
 due_at TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_education_recommendations_student
 ON education_learning_recommendations(institution_id,student_id,state,priority);
CREATE TABLE IF NOT EXISTS education_timetable_series(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 subject_id TEXT NOT NULL REFERENCES subjects(id),
 teacher_id TEXT NOT NULL,
 student_group TEXT NOT NULL DEFAULT '',
 room TEXT NOT NULL DEFAULT '',
 recurrence TEXT NOT NULL DEFAULT 'weekly',
 occurrence_count INTEGER NOT NULL,
 created_by TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_timetable_series_entries(
 series_id TEXT NOT NULL REFERENCES education_timetable_series(id),
 entry_id TEXT NOT NULL REFERENCES timetable_entries(id),
 occurrence_number INTEGER NOT NULL,
 PRIMARY KEY(series_id,entry_id)
);
CREATE TABLE IF NOT EXISTS education_attendance_alerts(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 subject_id TEXT NOT NULL,
 student_id TEXT NOT NULL,
 attendance_ratio REAL NOT NULL,
 threshold REAL NOT NULL,
 state TEXT NOT NULL DEFAULT 'open',
 detail_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(subject_id,student_id,state)
);
CREATE TABLE IF NOT EXISTS education_notification_preferences(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 user_id TEXT NOT NULL,
 event_type TEXT NOT NULL DEFAULT '*',
 channel TEXT NOT NULL DEFAULT 'in_app',
 enabled INTEGER NOT NULL DEFAULT 1,
 digest_mode TEXT NOT NULL DEFAULT 'instant',
 quiet_start TEXT NOT NULL DEFAULT '',
 quiet_end TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,user_id,event_type,channel)
);
CREATE TABLE IF NOT EXISTS education_notifications(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 user_id TEXT NOT NULL,
 event_type TEXT NOT NULL,
 title TEXT NOT NULL,
 body TEXT NOT NULL,
 action_url TEXT NOT NULL DEFAULT '',
 priority TEXT NOT NULL DEFAULT 'normal',
 state TEXT NOT NULL DEFAULT 'unread',
 read_at TEXT,
 dedupe_key TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL DEFAULT 'system',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_education_notification_dedupe
 ON education_notifications(institution_id,user_id,dedupe_key)
 WHERE dedupe_key<>'';
CREATE INDEX IF NOT EXISTS idx_education_notifications_user
 ON education_notifications(institution_id,user_id,state,created_at);
CREATE TABLE IF NOT EXISTS education_tutor_sources(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 subject_id TEXT NOT NULL,
 project_id TEXT NOT NULL,
 source_id TEXT NOT NULL,
 material_id TEXT NOT NULL DEFAULT '',
 title TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 indexed_by TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(project_id,source_id)
);
CREATE TABLE IF NOT EXISTS education_tutor_queries(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 subject_id TEXT NOT NULL,
 actor_id TEXT NOT NULL,
 project_id TEXT NOT NULL,
 question TEXT NOT NULL,
 answer TEXT NOT NULL,
 evidence_status TEXT NOT NULL,
 citations_json TEXT NOT NULL DEFAULT '[]',
 language TEXT NOT NULL DEFAULT 'auto',
 policy_mode TEXT NOT NULL DEFAULT 'guided',
 created_at TEXT NOT NULL
);
INSERT OR IGNORE INTO education_migrations(id,applied_at)
 VALUES('education_phase4_intelligence_operations_v1',datetime('now'));
"""

VALID_DIFFICULTIES = {"foundation", "easy", "medium", "hard", "advanced"}
VALID_EVIDENCE = {"practice", "assignment", "quiz", "examination", "laboratory", "teacher_observation", "self_check"}
VALID_PRIORITY = {"low", "normal", "high", "urgent"}
PRESENT_STATUSES = {"present", "late", "online_present", "practical_attendance", "examination_attendance"}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _decode(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError):
        return fallback


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EducationPhase4Service:
    """Institution-safe learning intelligence, operations, notifications and Shiro tutor bridge."""

    def __init__(self, platform: Any, *, root: str | Path | None = None, shiro_data_dir: str | Path | None = None):
        self.platform = platform
        self.db = platform.db
        self.permissions = PermissionService(platform)
        self.root = Path(root).resolve() if root else Path(__file__).resolve().parents[3]
        self.shiro_data_dir = Path(shiro_data_dir).resolve() if shiro_data_dir else platform.storage / "shiro-education"
        self._shiro = None
        self.migrate()
        # Phase 4 builds on the Phase 3 secure-examination schema and guarantees it exists.
        from .examination import SecureExaminationService
        self.examinations = SecureExaminationService(platform)

    def migrate(self) -> str:
        with self.db.connection() as db:
            db.executescript(SCHEMA)
        return MIGRATION_ID

    def _roles(self, actor: str, institution_id: str) -> set[str]:
        return {str(row["role"]) for row in self.platform._require(actor, institution_id)}

    def _subject_access(self, actor: str, institution_id: str, subject_id: str, *, manage: bool = False) -> dict[str, Any]:
        subject = self.platform._subject(institution_id, subject_id)
        roles = self._roles(actor, institution_id)
        if roles & TEACHER:
            if not roles & ADMIN:
                assigned = self.platform._one(
                    "SELECT 1 ok FROM teacher_assignments WHERE subject_id=? AND teacher_id=? AND state='active'",
                    (subject_id, actor),
                )
                if manage and not assigned:
                    raise Denied("Only assigned subject staff may manage this subject.")
            return subject
        if manage:
            raise Denied("Subject management permission denied.")
        enrolled = self.platform._one(
            "SELECT 1 ok FROM enrollments WHERE subject_id=? AND student_id=? AND state='active'",
            (subject_id, actor),
        )
        if not enrolled:
            raise Denied("Subject access denied.")
        return subject

    # ---------- Adaptive learning and knowledge graph ----------
    def create_concept(
        self,
        actor: str,
        institution_id: str,
        subject_id: str,
        code: str,
        title: str,
        *,
        description: str = "",
        prerequisites: Iterable[str] | None = None,
        difficulty: str = "medium",
    ) -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "learning.manage")
        self._subject_access(actor, institution_id, subject_id, manage=True)
        code = str(code).strip().upper()
        title = str(title).strip()
        difficulty = str(difficulty).strip().lower()
        if not code or not title:
            raise EducationError("Concept code and title are required.")
        if difficulty not in VALID_DIFFICULTIES:
            raise EducationError("Unsupported concept difficulty.")
        prerequisite_ids = list(dict.fromkeys(str(value).strip() for value in (prerequisites or []) if str(value).strip()))
        for concept_id in prerequisite_ids:
            row = self.platform._one("SELECT subject_id FROM education_concepts WHERE id=? AND state='active'", (concept_id,))
            if not row or row["subject_id"] != subject_id:
                raise Denied("Every prerequisite must belong to the same subject.")
        concept_id, timestamp = ident("concept"), now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_concepts
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (concept_id, institution_id, subject_id, code, title, str(description).strip(), _json(prerequisite_ids), difficulty, "active", actor, timestamp, timestamp),
            )
        self.platform._audit(actor, "learning_concept_created", "education_concept", concept_id, institution_id, {"subject_id": subject_id, "code": code})
        return self.platform._one("SELECT * FROM education_concepts WHERE id=?", (concept_id,))

    def _student_subject_access(self, actor: str, institution_id: str, subject_id: str, student_id: str, *, record: bool = False) -> None:
        roles = self._roles(actor, institution_id)
        if actor == student_id:
            if not self.platform._one("SELECT 1 ok FROM enrollments WHERE subject_id=? AND student_id=? AND state='active'", (subject_id, student_id)):
                raise Denied("Student is not enrolled in this subject.")
            if record and not roles & STUDENT:
                raise Denied("Only a student identity can record self-practice evidence.")
            return
        if roles & TEACHER:
            self._subject_access(actor, institution_id, subject_id, manage=True)
            return
        if self.platform._guardian_can(actor, institution_id, student_id) and not record:
            return
        raise Denied("Learner record access denied.")

    def record_mastery_evidence(
        self,
        actor: str,
        institution_id: str,
        student_id: str,
        concept_id: str,
        score: float,
        *,
        evidence_type: str = "practice",
        evidence_id: str = "",
        weight: float = 1.0,
        occurred_at: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        concept = self.platform._one("SELECT * FROM education_concepts WHERE id=? AND institution_id=? AND state='active'", (concept_id, institution_id))
        if not concept:
            raise Missing("Learning concept not found.")
        evidence_type = str(evidence_type).strip().lower()
        if evidence_type not in VALID_EVIDENCE:
            raise EducationError("Unsupported mastery evidence type.")
        self._student_subject_access(actor, institution_id, concept["subject_id"], student_id, record=True)
        roles = self._roles(actor, institution_id)
        if actor == student_id and evidence_type not in {"practice", "self_check"}:
            raise Denied("Students may record only self-practice or self-check evidence.")
        if actor != student_id and not roles & TEACHER:
            raise Denied("Only teaching staff may record assessed evidence.")
        score_value = float(score)
        weight_value = float(weight)
        if not 0 <= score_value <= 1:
            raise EducationError("Mastery score must be between 0 and 1.")
        if not 0.1 <= weight_value <= 5:
            raise EducationError("Evidence weight must be between 0.1 and 5.")
        occurred = parse_time(occurred_at).isoformat() if occurred_at else now()
        event_id = ident("mastery")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_mastery_events
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (event_id, institution_id, concept["subject_id"], student_id, concept_id, evidence_type, str(evidence_id), score_value, weight_value, occurred, actor, _json(detail or {}), now()),
            )
        state = self.recalculate_mastery(institution_id, student_id, concept_id)
        self._refresh_recommendation(institution_id, student_id, concept, state)
        self.platform._audit(actor, "mastery_evidence_recorded", "education_concept", concept_id, institution_id, {"student_id": student_id, "score": score_value, "type": evidence_type})
        return {"event_id": event_id, "state": state}

    def recalculate_mastery(self, institution_id: str, student_id: str, concept_id: str) -> dict[str, Any]:
        concept = self.platform._one("SELECT * FROM education_concepts WHERE id=? AND institution_id=?", (concept_id, institution_id))
        if not concept:
            raise Missing("Learning concept not found.")
        events = self.platform._all(
            "SELECT * FROM education_mastery_events WHERE institution_id=? AND student_id=? AND concept_id=? ORDER BY occurred_at",
            (institution_id, student_id, concept_id),
        )
        current = _utc_now()
        weighted, total_weight = 0.0, 0.0
        for event in events:
            age_days = max(0.0, (current - parse_time(event["occurred_at"])).total_seconds() / 86400)
            decay = 0.5 ** (age_days / 45.0)
            effective = float(event["weight"]) * decay
            weighted += float(event["score"]) * effective
            total_weight += effective
        mastery = weighted / total_weight if total_weight else 0.0
        confidence = 1.0 - math.exp(-total_weight / 3.5) if total_weight else 0.0
        previous = self.platform._one("SELECT * FROM education_mastery_state WHERE student_id=? AND concept_id=?", (student_id, concept_id))
        streak = int(previous["streak"]) if previous else 0
        if events:
            streak = streak + 1 if float(events[-1]["score"]) >= 0.75 else 0
        interval_days = 1
        if mastery >= 0.9 and confidence >= 0.7:
            interval_days = 30
        elif mastery >= 0.8:
            interval_days = 14
        elif mastery >= 0.65:
            interval_days = 7
        elif mastery >= 0.45:
            interval_days = 3
        last_practiced = events[-1]["occurred_at"] if events else None
        next_review = (parse_time(last_practiced) + timedelta(days=interval_days)).isoformat() if last_practiced else now()
        state_id = previous["id"] if previous else ident("mastery_state")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_mastery_state
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(student_id,concept_id) DO UPDATE SET
                mastery=excluded.mastery,confidence=excluded.confidence,evidence_count=excluded.evidence_count,
                streak=excluded.streak,last_practiced_at=excluded.last_practiced_at,
                next_review_at=excluded.next_review_at,updated_at=excluded.updated_at""",
                (state_id, institution_id, concept["subject_id"], student_id, concept_id, mastery, confidence, len(events), streak, last_practiced, next_review, timestamp),
            )
        return self.platform._one("SELECT * FROM education_mastery_state WHERE student_id=? AND concept_id=?", (student_id, concept_id))

    def _refresh_recommendation(self, institution_id: str, student_id: str, concept: dict[str, Any], state: dict[str, Any]) -> None:
        mastery, confidence = float(state["mastery"]), float(state["confidence"])
        if mastery >= 0.8 and confidence >= 0.55:
            recommendation_type, priority, title = "spaced_review", 35, f"Review {concept['title']} on schedule"
        elif mastery >= 0.55:
            recommendation_type, priority, title = "guided_practice", 65, f"Strengthen {concept['title']} with guided practice"
        else:
            recommendation_type, priority, title = "remediation", 90, f"Revisit foundations for {concept['title']}"
        timestamp = now()
        existing = self.platform._one(
            "SELECT * FROM education_learning_recommendations WHERE institution_id=? AND student_id=? AND concept_id=? AND state='open'",
            (institution_id, student_id, concept["id"]),
        )
        reason = {"mastery": round(mastery, 4), "confidence": round(confidence, 4), "evidence_count": int(state["evidence_count"]), "human_override_allowed": True}
        with self.db.connection() as db:
            if existing:
                db.execute(
                    "UPDATE education_learning_recommendations SET recommendation_type=?,priority=?,title=?,reason_json=?,due_at=?,updated_at=? WHERE id=?",
                    (recommendation_type, priority, title, _json(reason), state["next_review_at"], timestamp, existing["id"]),
                )
            else:
                db.execute(
                    "INSERT INTO education_learning_recommendations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ident("recommend"), institution_id, concept["subject_id"], student_id, concept["id"], recommendation_type, priority, title, _json(reason), "open", state["next_review_at"], timestamp, timestamp),
                )

    def learner_snapshot(self, actor: str, institution_id: str, student_id: str | None = None, subject_id: str | None = None) -> dict[str, Any]:
        student_id = student_id or actor
        roles = self._roles(actor, institution_id)
        if actor != student_id and not roles & TEACHER and not self.platform._guardian_can(actor, institution_id, student_id):
            raise Denied("Learner intelligence access denied.")
        args: list[Any] = [institution_id, student_id]
        subject_filter = ""
        if subject_id:
            self._student_subject_access(actor, institution_id, subject_id, student_id)
            subject_filter = " AND c.subject_id=?"
            args.append(subject_id)
        rows = self.platform._all(
            f"""SELECT c.id concept_id,c.subject_id,c.code,c.title,c.difficulty,c.prerequisite_ids_json,
            COALESCE(s.mastery,0) mastery,COALESCE(s.confidence,0) confidence,
            COALESCE(s.evidence_count,0) evidence_count,s.streak,s.last_practiced_at,s.next_review_at,
            sub.code subject_code,sub.name subject_name
            FROM education_concepts c JOIN subjects sub ON sub.id=c.subject_id
            LEFT JOIN education_mastery_state s ON s.concept_id=c.id AND s.student_id=?
            WHERE c.institution_id=? AND c.state='active'{subject_filter}
            ORDER BY sub.code,c.code""",
            (student_id, institution_id, *([subject_id] if subject_id else [])),
        )
        recommendations = self.platform._all(
            "SELECT * FROM education_learning_recommendations WHERE institution_id=? AND student_id=? AND state='open' ORDER BY priority DESC,created_at DESC",
            (institution_id, student_id),
        )
        for row in rows:
            row["prerequisite_ids"] = _decode(row.pop("prerequisite_ids_json"), [])
        for item in recommendations:
            item["reason"] = _decode(item.pop("reason_json"), {})
        average = sum(float(row["mastery"]) for row in rows) / len(rows) if rows else 0.0
        return {
            "student_id": student_id,
            "average_mastery": round(average, 4),
            "concepts": rows,
            "recommendations": recommendations,
            "explainability": "Mastery is a recency-weighted educational estimate from recorded evidence. It is not a permanent learner label and supports human review.",
        }

    # ---------- Timetable and attendance operations ----------
    @staticmethod
    def _overlap_sql() -> str:
        return "t.starts_at < ? AND t.ends_at > ? AND t.state='scheduled'"

    def timetable_conflicts(
        self,
        institution_id: str,
        teacher_id: str,
        student_group: str,
        room: str,
        starts_at: str,
        ends_at: str,
    ) -> list[dict[str, Any]]:
        start, end = parse_time(starts_at), parse_time(ends_at)
        if end <= start:
            raise EducationError("Timetable end must follow start.")
        rows = self.platform._all(
            f"""SELECT t.*,s.code subject_code,s.name subject_name FROM timetable_entries t
            LEFT JOIN subjects s ON s.id=t.subject_id WHERE t.institution_id=? AND {self._overlap_sql()}
            AND ((?<>'' AND t.teacher_id=?) OR (?<>'' AND t.student_group=?) OR (?<>'' AND t.room=?))
            ORDER BY t.starts_at""",
            (institution_id, end.isoformat(), start.isoformat(), teacher_id, teacher_id, student_group, student_group, room, room),
        )
        for row in rows:
            reasons = []
            if teacher_id and row["teacher_id"] == teacher_id:
                reasons.append("teacher")
            if student_group and row["student_group"] == student_group:
                reasons.append("student_group")
            if room and row["room"] == room:
                reasons.append("room")
            row["conflict_reasons"] = reasons
        return rows

    def create_weekly_timetable(
        self,
        actor: str,
        institution_id: str,
        subject_id: str,
        teacher_id: str,
        student_group: str,
        room: str,
        first_start: str,
        first_end: str,
        *,
        weeks: int = 12,
        meeting_id: str = "",
    ) -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "timetable.manage")
        self._subject_access(actor, institution_id, subject_id, manage=True)
        if not self.platform._one("SELECT 1 ok FROM teacher_assignments WHERE institution_id=? AND subject_id=? AND teacher_id=? AND state='active'", (institution_id, subject_id, teacher_id)):
            raise Denied("The selected teacher is not assigned to this subject.")
        count = int(weeks)
        if count < 1 or count > 104:
            raise EducationError("Weekly occurrence count must be between 1 and 104.")
        start, end = parse_time(first_start), parse_time(first_end)
        if end <= start:
            raise EducationError("Timetable end must follow start.")
        planned = [(start + timedelta(weeks=index), end + timedelta(weeks=index)) for index in range(count)]
        all_conflicts: list[dict[str, Any]] = []
        for occurrence_start, occurrence_end in planned:
            for conflict in self.timetable_conflicts(institution_id, teacher_id, student_group, room, occurrence_start.isoformat(), occurrence_end.isoformat()):
                all_conflicts.append({"occurrence_start": occurrence_start.isoformat(), **conflict})
        if all_conflicts:
            raise Conflict(f"Timetable series has {len(all_conflicts)} conflict(s); no entries were created.")
        series_id, timestamp = ident("ttseries"), now()
        entries: list[str] = []
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_timetable_series VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (series_id, institution_id, subject_id, teacher_id, str(student_group), str(room), "weekly", count, actor, "active", timestamp, timestamp),
            )
            for index, (occurrence_start, occurrence_end) in enumerate(planned, start=1):
                entry_id = ident("tt")
                db.execute(
                    "INSERT INTO timetable_entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (entry_id, institution_id, subject_id, teacher_id, str(student_group), str(room), occurrence_start.isoformat(), occurrence_end.isoformat(), str(meeting_id), "scheduled", timestamp, timestamp),
                )
                db.execute("INSERT INTO education_timetable_series_entries VALUES(?,?,?)", (series_id, entry_id, index))
                entries.append(entry_id)
        self.platform._audit(actor, "weekly_timetable_created", "timetable_series", series_id, institution_id, {"occurrences": count, "subject_id": subject_id})
        return {"series_id": series_id, "entry_ids": entries, "occurrence_count": count}

    def create_attendance_from_timetable(self, actor: str, entry_id: str, *, period: str | None = None) -> dict[str, Any]:
        entry = self.platform._one("SELECT * FROM timetable_entries WHERE id=?", (entry_id,))
        if not entry:
            raise Missing("Timetable entry not found.")
        self.permissions.require(actor, entry["institution_id"], "attendance.manage")
        self._subject_access(actor, entry["institution_id"], entry["subject_id"], manage=True)
        session_date = parse_time(entry["starts_at"]).date().isoformat()
        period_value = str(period or parse_time(entry["starts_at"]).strftime("%H:%M")).strip()
        existing = self.platform._one("SELECT * FROM attendance_sessions WHERE subject_id=? AND session_date=? AND period=?", (entry["subject_id"], session_date, period_value))
        if existing:
            return existing
        return self.platform.attendance_session(actor, entry["institution_id"], entry["subject_id"], session_date, period_value)

    def bulk_mark_attendance(self, actor: str, session_id: str, records: dict[str, str], *, note: str = "") -> dict[str, Any]:
        session = self.platform._one("SELECT * FROM attendance_sessions WHERE id=?", (session_id,))
        if not session:
            raise Missing("Attendance session not found.")
        self.permissions.require(actor, session["institution_id"], "attendance.manage")
        self._subject_access(actor, session["institution_id"], session["subject_id"], manage=True)
        enrolled = {row["student_id"] for row in self.platform._all("SELECT student_id FROM enrollments WHERE subject_id=? AND state='active'", (session["subject_id"],))}
        invalid = sorted(set(records) - enrolled)
        if invalid:
            raise Denied("Attendance contains students who are not enrolled in the subject.")
        saved = [self.platform.mark_attendance(actor, session_id, student_id, status, note) for student_id, status in records.items()]
        return {"session_id": session_id, "saved": len(saved), "records": saved}

    def attendance_shortage_alerts(self, actor: str, institution_id: str, *, threshold: float = 0.75, subject_id: str | None = None) -> list[dict[str, Any]]:
        roles = self._roles(actor, institution_id)
        if not roles & TEACHER:
            raise Denied("Attendance alert management is limited to institutional staff.")
        threshold_value = float(threshold)
        if not 0 < threshold_value <= 1:
            raise EducationError("Attendance threshold must be between 0 and 1.")
        args: list[Any] = [institution_id]
        filter_sql = ""
        if subject_id:
            self._subject_access(actor, institution_id, subject_id, manage=True)
            filter_sql = " AND e.subject_id=?"
            args.append(subject_id)
        stats = self.platform._all(
            f"""SELECT e.subject_id,e.student_id,s.code subject_code,s.name subject_name,
            COUNT(r.id) total,SUM(CASE WHEN r.status IN ('present','late','online_present','practical_attendance','examination_attendance') THEN 1 ELSE 0 END) attended
            FROM enrollments e JOIN subjects s ON s.id=e.subject_id
            LEFT JOIN attendance_sessions a ON a.subject_id=e.subject_id
            LEFT JOIN attendance_records r ON r.session_id=a.id AND r.student_id=e.student_id
            WHERE e.institution_id=? AND e.state='active'{filter_sql}
            GROUP BY e.subject_id,e.student_id HAVING COUNT(r.id)>0""",
            tuple(args),
        )
        alerts: list[dict[str, Any]] = []
        timestamp = now()
        with self.db.connection() as db:
            for stat in stats:
                ratio = float(stat["attended"] or 0) / max(int(stat["total"] or 0), 1)
                if ratio >= threshold_value:
                    db.execute("UPDATE education_attendance_alerts SET state='resolved',updated_at=? WHERE subject_id=? AND student_id=? AND state='open'", (timestamp, stat["subject_id"], stat["student_id"]))
                    continue
                existing = self.platform._one("SELECT * FROM education_attendance_alerts WHERE subject_id=? AND student_id=? AND state='open'", (stat["subject_id"], stat["student_id"]))
                alert_id = existing["id"] if existing else ident("attn_alert")
                detail = {"attended": int(stat["attended"] or 0), "total": int(stat["total"] or 0), "human_review_required": True}
                if existing:
                    db.execute("UPDATE education_attendance_alerts SET attendance_ratio=?,threshold=?,detail_json=?,updated_at=? WHERE id=?", (ratio, threshold_value, _json(detail), timestamp, alert_id))
                else:
                    db.execute("INSERT INTO education_attendance_alerts VALUES(?,?,?,?,?,?,?,?,?,?)", (alert_id, institution_id, stat["subject_id"], stat["student_id"], ratio, threshold_value, "open", _json(detail), timestamp, timestamp))
                alerts.append({**stat, "id": alert_id, "attendance_ratio": round(ratio, 4), "threshold": threshold_value, "detail": detail})
        return alerts

    # ---------- Notification center ----------
    def save_notification_preference(
        self,
        actor: str,
        institution_id: str,
        *,
        event_type: str = "*",
        channel: str = "in_app",
        enabled: bool = True,
        digest_mode: str = "instant",
        quiet_start: str = "",
        quiet_end: str = "",
    ) -> dict[str, Any]:
        self._roles(actor, institution_id)
        if channel not in {"in_app", "email", "desktop", "sms", "whatsapp"}:
            raise EducationError("Unsupported notification channel.")
        if digest_mode not in {"instant", "daily", "weekly", "off"}:
            raise EducationError("Unsupported notification digest mode.")
        timestamp = now()
        existing = self.platform._one("SELECT * FROM education_notification_preferences WHERE institution_id=? AND user_id=? AND event_type=? AND channel=?", (institution_id, actor, event_type, channel))
        preference_id = existing["id"] if existing else ident("notify_pref")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_notification_preferences VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,user_id,event_type,channel) DO UPDATE SET enabled=excluded.enabled,
                digest_mode=excluded.digest_mode,quiet_start=excluded.quiet_start,quiet_end=excluded.quiet_end,updated_at=excluded.updated_at""",
                (preference_id, institution_id, actor, str(event_type), channel, int(bool(enabled)), digest_mode, str(quiet_start), str(quiet_end), timestamp, timestamp),
            )
        return self.platform._one("SELECT * FROM education_notification_preferences WHERE id=?", (preference_id,))

    def emit_notification(
        self,
        actor: str,
        institution_id: str,
        user_id: str,
        event_type: str,
        title: str,
        body: str,
        *,
        action_url: str = "",
        priority: str = "normal",
        dedupe_key: str = "",
    ) -> dict[str, Any]:
        roles = self._roles(actor, institution_id)
        if actor != user_id and not roles & TEACHER:
            raise Denied("Notification creation permission denied.")
        if not self.platform.membership(user_id, institution_id):
            raise Denied("Notification recipient is not an active institution member.")
        priority = str(priority).lower()
        if priority not in VALID_PRIORITY:
            raise EducationError("Unsupported notification priority.")
        preference = self.platform._one(
            """SELECT * FROM education_notification_preferences WHERE institution_id=? AND user_id=?
            AND channel='in_app' AND event_type IN (?, '*') ORDER BY CASE WHEN event_type=? THEN 0 ELSE 1 END LIMIT 1""",
            (institution_id, user_id, event_type, event_type),
        )
        if preference and not int(preference["enabled"]):
            return {"suppressed": True, "reason": "recipient_preference"}
        timestamp = now()
        notification_id = ident("notify")
        try:
            with self.db.connection() as db:
                db.execute(
                    "INSERT INTO education_notifications VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (notification_id, institution_id, user_id, str(event_type), str(title).strip(), str(body).strip(), str(action_url), priority, "unread", None, str(dedupe_key), actor, timestamp, timestamp),
                )
        except Exception as exc:
            if dedupe_key and "UNIQUE constraint failed" in str(exc):
                return self.platform._one("SELECT * FROM education_notifications WHERE institution_id=? AND user_id=? AND dedupe_key=?", (institution_id, user_id, dedupe_key))
            raise
        return self.platform._one("SELECT * FROM education_notifications WHERE id=?", (notification_id,))

    def notification_inbox(self, actor: str, institution_id: str, *, unread_only: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        self._roles(actor, institution_id)
        state_filter = " AND state='unread'" if unread_only else ""
        return self.platform._all(
            f"SELECT * FROM education_notifications WHERE institution_id=? AND user_id=?{state_filter} ORDER BY created_at DESC LIMIT ?",
            (institution_id, actor, max(1, min(500, int(limit)))),
        )

    def mark_notification_read(self, actor: str, notification_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_notifications WHERE id=?", (notification_id,))
        if not row:
            raise Missing("Notification not found.")
        if row["user_id"] != actor:
            raise Denied("Only the recipient can read this notification.")
        timestamp = now()
        with self.db.connection() as db:
            db.execute("UPDATE education_notifications SET state='read',read_at=?,updated_at=? WHERE id=?", (timestamp, timestamp, notification_id))
        return self.platform._one("SELECT * FROM education_notifications WHERE id=?", (notification_id,))

    def generate_due_reminders(self, actor: str, institution_id: str, *, horizon_hours: int = 48) -> dict[str, int]:
        self.permissions.require(actor, institution_id, "notifications.manage")
        current = _utc_now()
        horizon = current + timedelta(hours=max(1, min(24 * 30, int(horizon_hours))))
        assignments = self.platform._all(
            """SELECT a.id,a.title,a.due_at,e.student_id FROM assignments a JOIN enrollments e ON e.subject_id=a.subject_id
            LEFT JOIN submissions s ON s.assignment_id=a.id AND s.student_id=e.student_id
            WHERE a.institution_id=? AND a.state='published' AND a.due_at>? AND a.due_at<=?
            AND (s.id IS NULL OR s.state<>'submitted')""",
            (institution_id, current.isoformat(), horizon.isoformat()),
        )
        exams = self.platform._all(
            """SELECT x.id,x.title,x.starts_at,e.student_id FROM examinations x JOIN enrollments e ON e.subject_id=x.subject_id
            WHERE x.institution_id=? AND x.state='published' AND x.starts_at>? AND x.starts_at<=?""",
            (institution_id, current.isoformat(), horizon.isoformat()),
        )
        created = 0
        for item in assignments:
            result = self.emit_notification(actor, institution_id, item["student_id"], "assignment_due", f"Assignment due: {item['title']}", f"Submit before {item['due_at']}.", priority="high", dedupe_key=f"assignment:{item['id']}:{item['student_id']}")
            created += int(not result.get("suppressed", False))
        for item in exams:
            result = self.emit_notification(actor, institution_id, item["student_id"], "exam_upcoming", f"Upcoming examination: {item['title']}", f"Exam window opens at {item['starts_at']}.", priority="high", dedupe_key=f"exam:{item['id']}:{item['student_id']}")
            created += int(not result.get("suppressed", False))
        return {"assignment_candidates": len(assignments), "exam_candidates": len(exams), "notifications_processed": created}

    # ---------- Shiro AI education tutor ----------
    def _orchestrator(self):
        if self._shiro is None:
            from biointel.shiro.core.orchestrator import ShiroOrchestrator

            self._shiro = ShiroOrchestrator(root=self.root, data_dir=self.shiro_data_dir)
        return self._shiro

    @staticmethod
    def tutor_project_id(institution_id: str, subject_id: str) -> str:
        digest = hashlib.sha256(f"{institution_id}:{subject_id}".encode("utf-8")).hexdigest()[:24]
        return f"edu-{digest}"

    def index_subject_text(self, actor: str, institution_id: str, subject_id: str, title: str, text: str) -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "shiro.manage")
        subject = self._subject_access(actor, institution_id, subject_id, manage=True)
        content = str(text).strip()
        if len(content) < 20:
            raise EducationError("Tutor source text is too short to index.")
        if len(content.encode("utf-8")) > 25 * 1024 * 1024:
            raise EducationError("Tutor source exceeds the 25 MiB local indexing limit.")
        project_id = self.tutor_project_id(institution_id, subject_id)
        filename = f"{str(title).strip() or subject['code']}.md"
        result = self._orchestrator().ingest(project_id, content.encode("utf-8"), filename, project_name=f"{subject['code']} · {subject['name']}", source_type="education_material", internal=True, confidential=True, metadata={"institution_id": institution_id, "subject_id": subject_id, "indexed_by": actor})
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_tutor_sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(project_id,source_id) DO UPDATE SET state='active',updated_at=excluded.updated_at""",
                (ident("tutor_src"), institution_id, subject_id, project_id, result.source.source_id, "", filename, result.source.sha256, actor, "active", timestamp, timestamp),
            )
        self.platform._audit(actor, "education_tutor_source_indexed", "subject", subject_id, institution_id, {"source_id": result.source.source_id, "chunks": result.chunks_indexed})
        return result.to_dict()

    def index_material(self, actor: str, material_id: str) -> dict[str, Any]:
        material = self.platform._one("SELECT * FROM materials WHERE id=? AND state='published'", (material_id,))
        if not material:
            raise Missing("Published learning material not found.")
        self.permissions.require(actor, material["institution_id"], "shiro.manage")
        self._subject_access(actor, material["institution_id"], material["subject_id"], manage=True)
        path = Path(material["storage_path"])
        if not path.is_file():
            raise Missing("Learning material file is unavailable.")
        project_id = self.tutor_project_id(material["institution_id"], material["subject_id"])
        result = self._orchestrator().ingest(project_id, path.read_bytes(), material["file_name"], project_name=material["subject_id"], source_type="education_material", internal=True, confidential=True, metadata={"institution_id": material["institution_id"], "subject_id": material["subject_id"], "material_id": material_id, "indexed_by": actor})
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_tutor_sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(project_id,source_id) DO UPDATE SET material_id=excluded.material_id,state='active',updated_at=excluded.updated_at""",
                (ident("tutor_src"), material["institution_id"], material["subject_id"], project_id, result.source.source_id, material_id, material["title"], result.source.sha256, actor, "active", timestamp, timestamp),
            )
        return result.to_dict()

    def _active_exam_for_subject(self, actor: str, subject_id: str) -> dict[str, Any] | None:
        current = now()
        return self.platform._one(
            """SELECT s.id session_id,e.id exam_id,e.title FROM education_exam_sessions s
            JOIN examinations e ON e.id=s.exam_id WHERE s.student_id=? AND e.subject_id=?
            AND s.state='active' AND s.expires_at>? LIMIT 1""",
            (actor, subject_id, current),
        )

    def ask_tutor(
        self,
        actor: str,
        institution_id: str,
        subject_id: str,
        question: str,
        *,
        response_language: str = "auto",
        policy_mode: str = "guided",
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "shiro.tutor")
        self._subject_access(actor, institution_id, subject_id)
        roles = self._roles(actor, institution_id)
        policy_mode = str(policy_mode).strip().lower()
        if policy_mode not in {"guided", "revision", "teacher_planning"}:
            raise EducationError("Unsupported tutor policy mode.")
        if roles & STUDENT and self._active_exam_for_subject(actor, subject_id):
            raise Conflict("Shiro Tutor is locked while the student has an active examination attempt in this subject.")
        if policy_mode == "teacher_planning" and not roles & TEACHER:
            raise Denied("Teacher-planning mode is limited to staff.")
        clean = " ".join(str(question).strip().split())
        if not clean:
            raise EducationError("A tutor question is required.")
        prefix = {
            "guided": "Using only the indexed course evidence, explain the concept step by step and include a self-check question. Do not invent sources. Learner question: ",
            "revision": "Using only the indexed course evidence, create a concise revision explanation with key terms and limitations. Learner question: ",
            "teacher_planning": "Using only the indexed course evidence, provide a teacher planning note with learning objectives and misconceptions. Teacher request: ",
        }[policy_mode]
        project_id = self.tutor_project_id(institution_id, subject_id)
        response = self._orchestrator().chat(project_id, prefix + clean, conversation_id=conversation_id, response_language=response_language, provider="local", external_requested=False, source_types=["education_material"])
        citations = [citation.to_dict() for citation in response.citations]
        query_id = ident("tutor_query")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_tutor_queries VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (query_id, institution_id, subject_id, actor, project_id, clean, response.answer, response.evidence_status, _json(citations), response.language.code, policy_mode, now()),
            )
        return {**response.to_dict(), "query_id": query_id, "policy_mode": policy_mode, "academic_integrity": "Tutor access is blocked during active subject examinations; answers are limited to indexed institutional evidence."}

    @staticmethod
    def academy_project_id(institution_id: str, course_id: str) -> str:
        digest = hashlib.sha256(f"academy:{institution_id}:{course_id}".encode("utf-8")).hexdigest()[:24]
        return f"academy-{digest}"

    def _academy_course_access(
        self, actor: str, institution_id: str, course_id: str, *, manage: bool = False
    ) -> dict[str, Any]:
        course = self.platform._one(
            "SELECT * FROM courses WHERE id=? AND institution_id=?", (course_id, institution_id)
        )
        if not course:
            raise Missing("Academy course not found.")
        roles = self._roles(actor, institution_id)
        if roles & ADMIN or (roles & TEACHER and course["educator_id"] == actor):
            return course
        if manage:
            raise Denied("Only the course educator or an institution administrator may manage Academy evidence.")
        enrolled = self.platform._one(
            "SELECT 1 ok FROM academy_enrollments WHERE course_id=? AND student_id=? AND state='active'",
            (course_id, actor),
        )
        if not enrolled:
            raise Denied("Active Academy enrollment is required for this course tutor.")
        return course

    def index_academy_transcript(self, actor: str, transcript_id: str) -> dict[str, Any]:
        transcript = self.platform._one(
            """SELECT t.*,l.title lecture_title,l.state lecture_state,l.course_id,
                      c.institution_id,c.title course_title,c.educator_id
               FROM education_lecture_transcripts t
               JOIN lectures l ON l.id=t.lecture_id
               JOIN courses c ON c.id=l.course_id WHERE t.id=?""",
            (transcript_id,),
        )
        if not transcript or transcript["lecture_state"] != "published":
            raise Missing("A published lecture transcript is required.")
        self._academy_course_access(
            actor, transcript["institution_id"], transcript["course_id"], manage=True
        )
        content = str(transcript.get("body") or "").strip()
        if len(content) < 20:
            raise EducationError("Lecture transcript is too short to index.")
        project_id = self.academy_project_id(
            transcript["institution_id"], transcript["course_id"]
        )
        filename = f"{transcript['lecture_title']} - {transcript['language']}.txt"
        result = self._orchestrator().ingest(
            project_id,
            content.encode("utf-8"),
            filename,
            project_name=f"{transcript['course_title']} · Academy",
            source_type="education_lecture_transcript",
            internal=True,
            confidential=True,
            metadata={
                "institution_id": transcript["institution_id"],
                "course_id": transcript["course_id"],
                "lecture_id": transcript["lecture_id"],
                "transcript_id": transcript_id,
                "language": transcript["language"],
                "approved_by": actor,
            },
        )
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_tutor_sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(project_id,source_id) DO UPDATE SET
                   material_id=excluded.material_id,state='active',updated_at=excluded.updated_at""",
                (
                    ident("academy_tutor_src"), transcript["institution_id"],
                    transcript["course_id"], project_id, result.source.source_id,
                    transcript_id, filename, result.source.sha256, actor, "active",
                    timestamp, timestamp,
                ),
            )
        self.platform._audit(
            actor, "academy_transcript_indexed", "lecture_transcript", transcript_id,
            transcript["institution_id"],
            {"course_id": transcript["course_id"], "source_id": result.source.source_id},
        )
        return result.to_dict()

    def ask_academy_tutor(
        self,
        actor: str,
        institution_id: str,
        course_id: str,
        question: str,
        *,
        response_language: str = "auto",
        policy_mode: str = "guided",
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        self.permissions.require(actor, institution_id, "shiro.tutor")
        course = self._academy_course_access(actor, institution_id, course_id)
        roles = self._roles(actor, institution_id)
        active_exam = self.platform._one(
            """SELECT s.id FROM education_exam_sessions s
               WHERE s.student_id=? AND s.state='active' AND s.expires_at>? LIMIT 1""",
            (actor, now()),
        )
        if roles & STUDENT and active_exam:
            raise Conflict("Shiro Tutor is locked while the learner has an active examination attempt.")
        mode = str(policy_mode).strip().lower()
        if mode not in {"guided", "revision", "teacher_planning"}:
            raise EducationError("Unsupported Academy tutor mode.")
        if mode == "teacher_planning" and not roles & (TEACHER | ADMIN):
            raise Denied("Teacher-planning mode is limited to authorized staff.")
        clean = " ".join(str(question).strip().split())
        if not clean:
            raise EducationError("A tutor question is required.")
        prefix = {
            "guided": "Using only approved lecture transcripts for this course, explain with uncertainty and a self-check. Do not invent sources. Question: ",
            "revision": "Using only approved lecture transcripts for this course, create a concise revision note with limitations. Request: ",
            "teacher_planning": "Using only approved lecture transcripts, draft educator planning content that remains unapproved until human review. Request: ",
        }[mode]
        project_id = self.academy_project_id(institution_id, course_id)
        response = self._orchestrator().chat(
            project_id,
            prefix + clean,
            conversation_id=conversation_id,
            response_language=response_language,
            provider="local",
            external_requested=False,
            source_types=["education_lecture_transcript"],
        )
        citations = [citation.to_dict() for citation in response.citations]
        query_id = ident("academy_tutor_query")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_tutor_queries VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    query_id, institution_id, course_id, actor, project_id, clean,
                    response.answer, response.evidence_status, _json(citations),
                    response.language.code, mode, now(),
                ),
            )
        return {
            **response.to_dict(),
            "query_id": query_id,
            "course_id": course_id,
            "course_title": course["title"],
            "policy_mode": mode,
            "academic_integrity": "Only explicitly indexed published lecture transcripts are retrieved; active examination attempts lock learner access.",
        }
    # ---------- Unified institutional reports ----------
    def learner_progress_report(self, actor: str, institution_id: str, student_id: str) -> dict[str, Any]:
        roles = self._roles(actor, institution_id)
        if actor != student_id and not roles & TEACHER and not self.platform._guardian_can(actor, institution_id, student_id):
            raise Denied("Learner report access denied.")
        attendance = self.platform.student_attendance(actor, institution_id, student_id)
        results = self.platform.view_results(actor, institution_id, student_id)
        learning = self.learner_snapshot(actor, institution_id, student_id)
        assignments = self.platform._all(
            """SELECT sub.id,sub.state,sub.submitted_at,sub.late,a.title,a.max_marks,g.marks,g.feedback,s.code subject_code
            FROM enrollments e JOIN assignments a ON a.subject_id=e.subject_id JOIN subjects s ON s.id=a.subject_id
            LEFT JOIN submissions sub ON sub.assignment_id=a.id AND sub.student_id=e.student_id
            LEFT JOIN grades g ON g.submission_id=sub.id
            WHERE e.institution_id=? AND e.student_id=? AND a.state='published' ORDER BY a.due_at DESC""",
            (institution_id, student_id),
        )
        attended = sum(1 for row in attendance if row["status"] in PRESENT_STATUSES)
        attendance_ratio = attended / len(attendance) if attendance else None
        graded = [row for row in assignments if row.get("marks") is not None]
        assignment_average = sum(100 * float(row["marks"]) / float(row["max_marks"]) for row in graded) / len(graded) if graded else None
        return {
            "student_id": student_id,
            "generated_at": now(),
            "summary": {
                "attendance_ratio": None if attendance_ratio is None else round(attendance_ratio, 4),
                "assignment_average_percent": None if assignment_average is None else round(assignment_average, 2),
                "average_concept_mastery": learning["average_mastery"],
                "published_results": len(results),
                "open_recommendations": len(learning["recommendations"]),
            },
            "attendance": attendance,
            "assignments": assignments,
            "results": results,
            "learning": learning,
            "governance": {"source": "persisted institutional records", "human_review_required": True, "generated_by": actor},
        }
