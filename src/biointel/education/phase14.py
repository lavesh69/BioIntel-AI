from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .phase11 import ADMIN_ROLES, TEACHER_ROLES, _json
from .phase13 import EducationPhase13Service
from .platform import Conflict, Denied, EducationError, Missing, ident, now, parse_time

MIGRATION_ID = "education_phase14_academic_intelligence_v1"

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS education_learning_outcomes(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 subject_id TEXT REFERENCES subjects(id),
 unit_id TEXT REFERENCES academic_units(id),
 code TEXT NOT NULL,
 title TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 outcome_level TEXT NOT NULL DEFAULT 'course',
 bloom_level TEXT NOT NULL DEFAULT 'understand',
 target_percent REAL NOT NULL DEFAULT 60,
 state TEXT NOT NULL DEFAULT 'active',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,code)
);
CREATE INDEX IF NOT EXISTS idx_phase14_outcomes
 ON education_learning_outcomes(institution_id,subject_id,outcome_level,state);

CREATE TABLE IF NOT EXISTS education_outcome_relationships(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 source_outcome_id TEXT NOT NULL REFERENCES education_learning_outcomes(id) ON DELETE CASCADE,
 target_outcome_id TEXT NOT NULL REFERENCES education_learning_outcomes(id) ON DELETE CASCADE,
 strength INTEGER NOT NULL DEFAULT 1,
 rationale TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(source_outcome_id,target_outcome_id)
);

CREATE TABLE IF NOT EXISTS education_outcome_assessment_mappings(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 outcome_id TEXT NOT NULL REFERENCES education_learning_outcomes(id) ON DELETE CASCADE,
 assessment_type TEXT NOT NULL,
 assessment_id TEXT NOT NULL,
 weight REAL NOT NULL DEFAULT 1,
 rationale TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(outcome_id,assessment_type,assessment_id)
);
CREATE INDEX IF NOT EXISTS idx_phase14_outcome_assessment
 ON education_outcome_assessment_mappings(institution_id,outcome_id,assessment_type);

CREATE TABLE IF NOT EXISTS education_outcome_evidence(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 outcome_id TEXT NOT NULL REFERENCES education_learning_outcomes(id) ON DELETE CASCADE,
 evidence_type TEXT NOT NULL,
 title TEXT NOT NULL,
 target_type TEXT NOT NULL DEFAULT '',
 target_id TEXT NOT NULL DEFAULT '',
 description TEXT NOT NULL DEFAULT '',
 source_path TEXT NOT NULL DEFAULT '',
 sha256 TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'submitted',
 review_decision TEXT NOT NULL DEFAULT 'pending',
 review_note TEXT NOT NULL DEFAULT '',
 submitted_by TEXT NOT NULL,
 reviewed_by TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 reviewed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_phase14_outcome_evidence
 ON education_outcome_evidence(institution_id,outcome_id,review_decision,created_at);

CREATE TABLE IF NOT EXISTS education_outcome_attainment_runs(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 subject_id TEXT NOT NULL REFERENCES subjects(id),
 outcome_id TEXT NOT NULL REFERENCES education_learning_outcomes(id),
 period_start TEXT,
 period_end TEXT,
 student_count INTEGER NOT NULL DEFAULT 0,
 evidence_count INTEGER NOT NULL DEFAULT 0,
 attainment_percent REAL,
 target_percent REAL NOT NULL DEFAULT 60,
 state TEXT NOT NULL DEFAULT 'completed',
 detail_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_phase14_attainment
 ON education_outcome_attainment_runs(institution_id,subject_id,outcome_id,created_at);

CREATE TABLE IF NOT EXISTS education_quality_cycles(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 title TEXT NOT NULL,
 period_start TEXT NOT NULL,
 period_end TEXT NOT NULL,
 standard_name TEXT NOT NULL DEFAULT 'Internal quality review',
 state TEXT NOT NULL DEFAULT 'open',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_improvement_actions(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 cycle_id TEXT NOT NULL REFERENCES education_quality_cycles(id) ON DELETE CASCADE,
 outcome_id TEXT REFERENCES education_learning_outcomes(id),
 title TEXT NOT NULL,
 rationale TEXT NOT NULL DEFAULT '',
 owner_id TEXT NOT NULL,
 due_at TEXT,
 priority TEXT NOT NULL DEFAULT 'medium',
 state TEXT NOT NULL DEFAULT 'open',
 completion_evidence TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 completed_at TEXT
);

CREATE TABLE IF NOT EXISTS education_psychometric_runs(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 exam_id TEXT NOT NULL REFERENCES examinations(id),
 session_count INTEGER NOT NULL DEFAULT 0,
 question_count INTEGER NOT NULL DEFAULT 0,
 reliability_alpha REAL,
 mean_score_percent REAL,
 state TEXT NOT NULL DEFAULT 'completed',
 detail_json TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_phase14_psychometric_runs
 ON education_psychometric_runs(institution_id,exam_id,created_at);

CREATE TABLE IF NOT EXISTS education_question_statistics(
 id TEXT PRIMARY KEY,
 run_id TEXT NOT NULL REFERENCES education_psychometric_runs(id) ON DELETE CASCADE,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 exam_id TEXT NOT NULL REFERENCES examinations(id),
 question_id TEXT NOT NULL REFERENCES education_exam_questions(id),
 response_count INTEGER NOT NULL DEFAULT 0,
 omitted_count INTEGER NOT NULL DEFAULT 0,
 difficulty_index REAL,
 discrimination_index REAL,
 point_biserial REAL,
 mean_item_score REAL,
 distractor_json TEXT NOT NULL DEFAULT '{}',
 flags_json TEXT NOT NULL DEFAULT '[]',
 created_at TEXT NOT NULL,
 UNIQUE(run_id,question_id)
);

CREATE TABLE IF NOT EXISTS education_student_success_snapshots(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 student_id TEXT NOT NULL,
 subject_id TEXT NOT NULL REFERENCES subjects(id),
 attendance_percent REAL,
 assignment_percent REAL,
 mastery_percent REAL,
 exam_percent REAL,
 risk_level TEXT NOT NULL DEFAULT 'insufficient_evidence',
 factors_json TEXT NOT NULL DEFAULT '[]',
 explanation_json TEXT NOT NULL DEFAULT '{}',
 evidence_count INTEGER NOT NULL DEFAULT 0,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_phase14_success_snapshots
 ON education_student_success_snapshots(institution_id,student_id,subject_id,created_at);

CREATE TABLE IF NOT EXISTS education_intervention_cases(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 snapshot_id TEXT NOT NULL REFERENCES education_student_success_snapshots(id),
 student_id TEXT NOT NULL,
 subject_id TEXT NOT NULL REFERENCES subjects(id),
 priority TEXT NOT NULL DEFAULT 'medium',
 reason TEXT NOT NULL,
 action_plan TEXT NOT NULL,
 assigned_to TEXT NOT NULL,
 due_at TEXT,
 state TEXT NOT NULL DEFAULT 'open',
 review_note TEXT NOT NULL DEFAULT '',
 created_by TEXT NOT NULL,
 reviewed_by TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 closed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_phase14_interventions
 ON education_intervention_cases(institution_id,state,priority,due_at);

CREATE TABLE IF NOT EXISTS education_calendar_details(
 event_id TEXT PRIMARY KEY REFERENCES academic_events(id) ON DELETE CASCADE,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 description TEXT NOT NULL DEFAULT '',
 location TEXT NOT NULL DEFAULT '',
 audience_json TEXT NOT NULL DEFAULT '{}',
 owner_id TEXT NOT NULL,
 all_day INTEGER NOT NULL DEFAULT 0,
 source TEXT NOT NULL DEFAULT 'biointel',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS education_calendar_exports(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL REFERENCES institutions(id),
 start_at TEXT NOT NULL,
 end_at TEXT NOT NULL,
 event_count INTEGER NOT NULL DEFAULT 0,
 output_path TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL
);

INSERT OR IGNORE INTO education_migrations(id,applied_at)
 VALUES('education_phase14_academic_intelligence_v1',datetime('now'));
"""

OUTCOME_LEVELS = {"course", "program", "institution"}
BLOOM_LEVELS = {"remember", "understand", "apply", "analyze", "evaluate", "create"}
ASSESSMENT_TYPES = {"assignment", "exam_question", "rubric_criterion"}
EVIDENCE_TYPES = {"assessment", "report", "curriculum", "meeting", "survey", "external_review", "other"}
REVIEW_DECISIONS = {"approve", "request_changes", "reject"}
RISK_LEVELS = {"insufficient_evidence", "on_track", "watch", "priority_support"}
INTERVENTION_STATES = {"open", "in_progress", "completed", "cancelled"}


def _decode(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _mean(values: Iterable[float]) -> float | None:
    values = [float(value) for value in values]
    return sum(values) / len(values) if values else None


def _variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = sum(values) / len(values)
    return sum((value - average) ** 2 for value in values) / (len(values) - 1)


def _correlation(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denominator = math.sqrt(sum((x - mean_x) ** 2 for x in xs) * sum((y - mean_y) ** 2 for y in ys))
    return numerator / denominator if denominator else None


def _percent(numerator: float, denominator: float) -> float | None:
    return round(100.0 * numerator / denominator, 2) if denominator else None


def _canonical(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().casefold()
    if isinstance(value, (list, tuple, set)):
        return sorted(str(item).strip().casefold() for item in value)
    return value


def _ics_escape(value: Any) -> str:
    return str(value or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_datetime(value: str) -> str:
    parsed = parse_time(value)
    return parsed.strftime("%Y%m%dT%H%M%SZ")


class EducationPhase14Service(EducationPhase13Service):
    """Academic quality, psychometrics, transparent support and calendar operations."""

    def __init__(self, platform: Any, *, root: str | Path | None = None):
        super().__init__(platform, root=root)
        self.root = Path(root or self.root)
        self.migrate_phase14()

    def migrate_phase14(self) -> str:
        with self.db.connection() as db:
            db.executescript(SCHEMA)
        return MIGRATION_ID

    def _roles(self, actor: str, institution_id: str) -> set[str]:
        return {str(row["role"]) for row in self.platform._require(actor, institution_id)}

    def _require_staff(self, actor: str, institution_id: str) -> set[str]:
        roles = self._roles(actor, institution_id)
        if not roles & TEACHER_ROLES:
            raise Denied("Academic staff access required.")
        return roles

    def _require_admin(self, actor: str, institution_id: str) -> set[str]:
        roles = self._roles(actor, institution_id)
        if not roles & ADMIN_ROLES:
            raise Denied("Institution administrator access required.")
        return roles

    def _outcome(self, outcome_id: str) -> dict[str, Any]:
        outcome = self.platform._one("SELECT * FROM education_learning_outcomes WHERE id=?", (outcome_id,))
        if not outcome:
            raise Missing("Learning outcome not found.")
        return outcome

    # ------------------------------------------------------------------
    # Outcome mapping, evidence and quality improvement
    # ------------------------------------------------------------------
    def create_learning_outcome(
        self,
        actor: str,
        institution_id: str,
        *,
        code: str,
        title: str,
        description: str = "",
        outcome_level: str = "course",
        subject_id: str | None = None,
        unit_id: str | None = None,
        bloom_level: str = "understand",
        target_percent: float = 60.0,
    ) -> dict[str, Any]:
        self._require_staff(actor, institution_id)
        level = str(outcome_level).strip().lower()
        bloom = str(bloom_level).strip().lower()
        if level not in OUTCOME_LEVELS:
            raise EducationError("Unsupported outcome level.")
        if bloom not in BLOOM_LEVELS:
            raise EducationError("Unsupported Bloom level.")
        if level == "course" and not subject_id:
            raise EducationError("Course outcomes require a subject.")
        if subject_id:
            self.platform._subject(institution_id, subject_id)
            self.platform._teacher(actor, institution_id, subject_id)
        if unit_id:
            unit = self.platform._one("SELECT institution_id FROM academic_units WHERE id=?", (unit_id,))
            if not unit or unit["institution_id"] != institution_id:
                raise Denied("Academic unit access denied.")
        target = float(target_percent)
        if target <= 0 or target > 100:
            raise EducationError("Target percentage must be greater than zero and at most 100.")
        if not str(code).strip() or not str(title).strip():
            raise EducationError("Outcome code and title are required.")
        outcome_id, timestamp = ident("outcome"), now()
        try:
            with self.db.connection() as db:
                db.execute(
                    """INSERT INTO education_learning_outcomes
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (outcome_id, institution_id, subject_id, unit_id, str(code).strip()[:80], str(title).strip()[:500], str(description)[:20000], level, bloom, target, "active", actor, timestamp, timestamp),
                )
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise Conflict("Outcome code already exists in this institution.") from exc
            raise
        self.platform._audit(actor, "learning_outcome_created", "learning_outcome", outcome_id, institution_id, {"code": code, "level": level})
        return self._outcome(outcome_id)

    def map_outcome_relationship(self, actor: str, source_outcome_id: str, target_outcome_id: str, *, strength: int = 1, rationale: str = "") -> dict[str, Any]:
        source, target = self._outcome(source_outcome_id), self._outcome(target_outcome_id)
        if source["institution_id"] != target["institution_id"]:
            raise Denied("Cross-institution outcome mapping is not allowed.")
        self._require_staff(actor, source["institution_id"])
        if source_outcome_id == target_outcome_id:
            raise EducationError("An outcome cannot map to itself.")
        value = int(strength)
        if value < 1 or value > 3:
            raise EducationError("Mapping strength must be 1, 2 or 3.")
        relationship_id, timestamp = ident("omap"), now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_outcome_relationships
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(source_outcome_id,target_outcome_id) DO UPDATE SET
                strength=excluded.strength,rationale=excluded.rationale,created_by=excluded.created_by,created_at=excluded.created_at""",
                (relationship_id, source["institution_id"], source_outcome_id, target_outcome_id, value, str(rationale)[:5000], actor, timestamp),
            )
        return self.platform._one("SELECT * FROM education_outcome_relationships WHERE source_outcome_id=? AND target_outcome_id=?", (source_outcome_id, target_outcome_id))

    def map_assessment_to_outcome(
        self,
        actor: str,
        outcome_id: str,
        *,
        assessment_type: str,
        assessment_id: str,
        weight: float = 1.0,
        rationale: str = "",
    ) -> dict[str, Any]:
        outcome = self._outcome(outcome_id)
        self._require_staff(actor, outcome["institution_id"])
        kind = str(assessment_type).strip().lower()
        if kind not in ASSESSMENT_TYPES:
            raise EducationError("Unsupported assessment mapping type.")
        assessment: dict[str, Any] | None = None
        if kind == "assignment":
            assessment = self.platform._one("SELECT institution_id,subject_id,title FROM assignments WHERE id=?", (assessment_id,))
        elif kind == "exam_question":
            assessment = self.platform._one(
                """SELECT q.institution_id,e.subject_id,q.prompt title FROM education_exam_questions q
                JOIN examinations e ON e.id=q.exam_id WHERE q.id=?""",
                (assessment_id,),
            )
        else:
            assessment = self.platform._one(
                """SELECT a.institution_id,a.subject_id,c.title FROM education_rubric_criteria c
                JOIN education_assignment_rubrics r ON r.id=c.rubric_id
                JOIN assignments a ON a.id=r.assignment_id WHERE c.id=?""",
                (assessment_id,),
            )
        if not assessment or assessment["institution_id"] != outcome["institution_id"]:
            raise Denied("Assessment mapping target is unavailable in this institution.")
        if outcome.get("subject_id") and assessment.get("subject_id") != outcome["subject_id"]:
            raise Conflict("Assessment and course outcome belong to different subjects.")
        numeric_weight = float(weight)
        if numeric_weight <= 0 or numeric_weight > 100:
            raise EducationError("Mapping weight must be greater than zero and at most 100.")
        mapping_id, timestamp = ident("amap"), now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_outcome_assessment_mappings
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(outcome_id,assessment_type,assessment_id) DO UPDATE SET
                weight=excluded.weight,rationale=excluded.rationale,created_by=excluded.created_by,updated_at=excluded.updated_at""",
                (mapping_id, outcome["institution_id"], outcome_id, kind, assessment_id, numeric_weight, str(rationale)[:5000], actor, timestamp, timestamp),
            )
        return self.platform._one("SELECT * FROM education_outcome_assessment_mappings WHERE outcome_id=? AND assessment_type=? AND assessment_id=?", (outcome_id, kind, assessment_id))

    def submit_outcome_evidence(
        self,
        actor: str,
        outcome_id: str,
        *,
        evidence_type: str,
        title: str,
        description: str = "",
        target_type: str = "",
        target_id: str = "",
        source_path: str = "",
    ) -> dict[str, Any]:
        outcome = self._outcome(outcome_id)
        self._require_staff(actor, outcome["institution_id"])
        kind = str(evidence_type).strip().lower()
        if kind not in EVIDENCE_TYPES:
            raise EducationError("Unsupported evidence type.")
        if not str(title).strip():
            raise EducationError("Evidence title is required.")
        digest, normalized_path = "", ""
        if source_path:
            path = Path(source_path).expanduser().resolve()
            if not path.is_file():
                raise Missing("Evidence file not found.")
            if path.stat().st_size > 500 * 1024 * 1024:
                raise EducationError("Evidence file exceeds the 500 MiB limit.")
            file_digest = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    file_digest.update(block)
            digest, normalized_path = file_digest.hexdigest(), str(path)
        evidence_id, timestamp = ident("oev"), now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_outcome_evidence
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (evidence_id, outcome["institution_id"], outcome_id, kind, str(title).strip()[:500], str(target_type)[:100], str(target_id)[:300], str(description)[:20000], normalized_path, digest, "submitted", "pending", "", actor, "", timestamp, None),
            )
        self.platform._audit(actor, "outcome_evidence_submitted", "outcome_evidence", evidence_id, outcome["institution_id"], {"outcome_id": outcome_id, "type": kind, "sha256": digest})
        return self.platform._one("SELECT * FROM education_outcome_evidence WHERE id=?", (evidence_id,))

    def review_outcome_evidence(self, actor: str, evidence_id: str, *, decision: str, note: str = "") -> dict[str, Any]:
        evidence = self.platform._one("SELECT * FROM education_outcome_evidence WHERE id=?", (evidence_id,))
        if not evidence:
            raise Missing("Outcome evidence not found.")
        roles = self._require_admin(actor, evidence["institution_id"])
        if actor == evidence["submitted_by"] and not roles & {"platform_administrator", "institution_administrator"}:
            raise Denied("Independent evidence review is required.")
        value = str(decision).strip().lower()
        if value not in REVIEW_DECISIONS:
            raise EducationError("Unsupported evidence review decision.")
        timestamp = now()
        state = "approved" if value == "approve" else "changes_requested" if value == "request_changes" else "rejected"
        with self.db.connection() as db:
            db.execute(
                "UPDATE education_outcome_evidence SET state=?,review_decision=?,review_note=?,reviewed_by=?,reviewed_at=? WHERE id=?",
                (state, value, str(note)[:10000], actor, timestamp, evidence_id),
            )
        self.platform._audit(actor, "outcome_evidence_reviewed", "outcome_evidence", evidence_id, evidence["institution_id"], {"decision": value})
        return self.platform._one("SELECT * FROM education_outcome_evidence WHERE id=?", (evidence_id,))

    def _assessment_percentages(self, outcome: dict[str, Any], period_start: str | None, period_end: str | None) -> tuple[list[dict[str, Any]], set[str]]:
        mappings = self.platform._all("SELECT * FROM education_outcome_assessment_mappings WHERE outcome_id=? ORDER BY created_at", (outcome["id"],))
        evidence: list[dict[str, Any]] = []
        students: set[str] = set()
        for mapping in mappings:
            kind, target_id, weight = mapping["assessment_type"], mapping["assessment_id"], float(mapping["weight"])
            if kind == "assignment":
                params: list[Any] = [target_id]
                date_filter = ""
                if period_start:
                    date_filter += " AND COALESCE(s.submitted_at,s.created_at)>=?"
                    params.append(parse_time(period_start).isoformat())
                if period_end:
                    date_filter += " AND COALESCE(s.submitted_at,s.created_at)<=?"
                    params.append(parse_time(period_end).isoformat())
                rows = self.platform._all(
                    f"""SELECT s.student_id,g.marks,a.max_marks FROM assignments a
                    JOIN submissions s ON s.assignment_id=a.id AND s.state='submitted'
                    JOIN grades g ON g.submission_id=s.id AND g.state='released'
                    WHERE a.id=? {date_filter}""",
                    tuple(params),
                )
                values = []
                for row in rows:
                    students.add(row["student_id"])
                    percent = _percent(float(row["marks"]), float(row["max_marks"]))
                    if percent is not None:
                        values.append(percent)
                evidence.append({"mapping": mapping, "label": "assignment", "sample_count": len(values), "percent": _mean(values), "weight": weight})
            elif kind == "exam_question":
                question = self.platform._one("SELECT marks FROM education_exam_questions WHERE id=?", (target_id,))
                rows = self.platform._all(
                    """SELECT es.student_id,sc.detail_json FROM education_exam_sessions es
                    JOIN education_exam_scores sc ON sc.session_id=es.id
                    WHERE es.exam_id=(SELECT exam_id FROM education_exam_questions WHERE id=?)
                    AND es.state IN ('submitted','expired')""",
                    (target_id,),
                )
                values = []
                max_marks = float((question or {}).get("marks") or 0)
                for row in rows:
                    students.add(row["student_id"])
                    detail = _decode(row["detail_json"], [])
                    item = next((entry for entry in detail if entry.get("question_id") == target_id), None)
                    if item and max_marks:
                        values.append(max(0.0, min(100.0, 100.0 * float(item.get("awarded") or 0) / max_marks)))
                evidence.append({"mapping": mapping, "label": "exam_question", "sample_count": len(values), "percent": _mean(values), "weight": weight})
            else:
                criterion = self.platform._one("SELECT max_marks FROM education_rubric_criteria WHERE id=?", (target_id,))
                rows = self.platform._all("SELECT submission_id,marks FROM education_rubric_scores WHERE criterion_id=?", (target_id,))
                values = []
                maximum = float((criterion or {}).get("max_marks") or 0)
                for row in rows:
                    submission = self.platform._one("SELECT student_id FROM submissions WHERE id=?", (row["submission_id"],))
                    if submission:
                        students.add(submission["student_id"])
                    if maximum:
                        values.append(max(0.0, min(100.0, 100.0 * float(row["marks"]) / maximum)))
                evidence.append({"mapping": mapping, "label": "rubric_criterion", "sample_count": len(values), "percent": _mean(values), "weight": weight})
        return evidence, students

    def calculate_outcome_attainment(self, actor: str, outcome_id: str, *, period_start: str | None = None, period_end: str | None = None) -> dict[str, Any]:
        outcome = self._outcome(outcome_id)
        self._require_staff(actor, outcome["institution_id"])
        if not outcome.get("subject_id"):
            raise EducationError("Attainment is calculated for course outcomes with a subject.")
        if period_start:
            parse_time(period_start)
        if period_end:
            parse_time(period_end)
        if period_start and period_end and parse_time(period_end) < parse_time(period_start):
            raise EducationError("Attainment period end must follow its start.")
        evidence, students = self._assessment_percentages(outcome, period_start, period_end)
        usable = [item for item in evidence if item["percent"] is not None and item["sample_count"] > 0]
        total_weight = sum(float(item["weight"]) for item in usable)
        attainment = sum(float(item["percent"]) * float(item["weight"]) for item in usable) / total_weight if total_weight else None
        run_id, timestamp = ident("attain"), now()
        detail = {
            "outcome": {"id": outcome["id"], "code": outcome["code"], "title": outcome["title"]},
            "sources": evidence,
            "method": "weighted mean of approved mapped assessment results",
            "human_review_required": True,
            "no_accreditation_claim": True,
        }
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_outcome_attainment_runs
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, outcome["institution_id"], outcome["subject_id"], outcome_id, period_start, period_end, len(students), len(usable), attainment, float(outcome["target_percent"]), "completed", _json(detail), actor, timestamp),
            )
        result = self.platform._one("SELECT * FROM education_outcome_attainment_runs WHERE id=?", (run_id,))
        result["detail"] = detail
        result["target_met"] = attainment is not None and attainment >= float(outcome["target_percent"])
        return result

    def create_quality_cycle(self, actor: str, institution_id: str, *, title: str, period_start: str, period_end: str, standard_name: str = "Internal quality review") -> dict[str, Any]:
        self._require_admin(actor, institution_id)
        start, end = parse_time(period_start), parse_time(period_end)
        if end <= start:
            raise EducationError("Quality-cycle end must follow start.")
        cycle_id, timestamp = ident("qcycle"), now()
        with self.db.connection() as db:
            db.execute("INSERT INTO education_quality_cycles VALUES(?,?,?,?,?,?,?,?,?,?)", (cycle_id, institution_id, str(title).strip()[:500], start.isoformat(), end.isoformat(), str(standard_name)[:500], "open", actor, timestamp, timestamp))
        return self.platform._one("SELECT * FROM education_quality_cycles WHERE id=?", (cycle_id,))

    def create_improvement_action(self, actor: str, cycle_id: str, *, title: str, rationale: str, owner_id: str, outcome_id: str | None = None, due_at: str | None = None, priority: str = "medium") -> dict[str, Any]:
        cycle = self.platform._one("SELECT * FROM education_quality_cycles WHERE id=?", (cycle_id,))
        if not cycle:
            raise Missing("Quality cycle not found.")
        self._require_admin(actor, cycle["institution_id"])
        if outcome_id:
            outcome = self._outcome(outcome_id)
            if outcome["institution_id"] != cycle["institution_id"]:
                raise Denied("Outcome belongs to another institution.")
        if due_at:
            parse_time(due_at)
        if priority not in {"low", "medium", "high", "critical"}:
            raise EducationError("Unsupported improvement priority.")
        action_id, timestamp = ident("improve"), now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_improvement_actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (action_id, cycle["institution_id"], cycle_id, outcome_id, str(title).strip()[:500], str(rationale)[:10000], str(owner_id)[:200], due_at, priority, "open", "", actor, timestamp, timestamp, None),
            )
        return self.platform._one("SELECT * FROM education_improvement_actions WHERE id=?", (action_id,))

    def update_improvement_action(self, actor: str, action_id: str, *, state: str, review_note: str = "", completion_evidence: str = "") -> dict[str, Any]:
        action = self.platform._one("SELECT * FROM education_improvement_actions WHERE id=?", (action_id,))
        if not action:
            raise Missing("Improvement action not found.")
        roles = self._roles(actor, action["institution_id"])
        if actor != action["owner_id"] and not roles & ADMIN_ROLES:
            raise Denied("Only the assigned owner or an administrator may update this action.")
        value = str(state).strip().lower()
        if value not in {"open", "in_progress", "completed", "cancelled"}:
            raise EducationError("Unsupported action state.")
        if value == "completed" and not str(completion_evidence).strip():
            raise EducationError("Completion evidence is required before closing an improvement action.")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                "UPDATE education_improvement_actions SET state=?,completion_evidence=?,updated_at=?,completed_at=? WHERE id=?",
                (value, str(completion_evidence or review_note)[:20000], timestamp, timestamp if value == "completed" else None, action_id),
            )
        return self.platform._one("SELECT * FROM education_improvement_actions WHERE id=?", (action_id,))

    def accreditation_evidence_matrix(self, actor: str, institution_id: str, *, subject_id: str | None = None) -> dict[str, Any]:
        self._require_staff(actor, institution_id)
        params: list[Any] = [institution_id]
        where = ""
        if subject_id:
            self.platform._subject(institution_id, subject_id)
            where = " AND o.subject_id=?"
            params.append(subject_id)
        outcomes = self.platform._all(f"SELECT o.*,s.code subject_code,s.name subject_name FROM education_learning_outcomes o LEFT JOIN subjects s ON s.id=o.subject_id WHERE o.institution_id=? AND o.state='active'{where} ORDER BY o.outcome_level,o.code", tuple(params))
        rows = []
        for outcome in outcomes:
            mappings = self.platform._one("SELECT COUNT(*) n FROM education_outcome_assessment_mappings WHERE outcome_id=?", (outcome["id"],)) or {"n": 0}
            evidence = self.platform._one("SELECT COUNT(*) n,SUM(CASE WHEN review_decision='approve' THEN 1 ELSE 0 END) approved FROM education_outcome_evidence WHERE outcome_id=?", (outcome["id"],)) or {"n": 0, "approved": 0}
            latest = self.platform._one("SELECT * FROM education_outcome_attainment_runs WHERE outcome_id=? ORDER BY created_at DESC LIMIT 1", (outcome["id"],))
            rows.append({
                **outcome,
                "mapping_count": int(mappings["n"] or 0),
                "evidence_count": int(evidence["n"] or 0),
                "approved_evidence_count": int(evidence["approved"] or 0),
                "latest_attainment_percent": latest.get("attainment_percent") if latest else None,
                "target_met": bool(latest and latest.get("attainment_percent") is not None and float(latest["attainment_percent"]) >= float(outcome["target_percent"])),
            })
        return {
            "institution_id": institution_id,
            "subject_id": subject_id,
            "outcomes": rows,
            "summary": {
                "outcomes": len(rows),
                "mapped": sum(1 for row in rows if row["mapping_count"] > 0),
                "with_approved_evidence": sum(1 for row in rows if row["approved_evidence_count"] > 0),
                "target_met": sum(1 for row in rows if row["target_met"]),
            },
            "qualification_statement": "Internal evidence organization only; this report does not claim external accreditation.",
        }

    # ------------------------------------------------------------------
    # Exam psychometrics
    # ------------------------------------------------------------------
    def run_exam_psychometrics(self, actor: str, exam_id: str) -> dict[str, Any]:
        exam = self.platform._one("SELECT * FROM examinations WHERE id=?", (exam_id,))
        if not exam:
            raise Missing("Examination not found.")
        self._require_staff(actor, exam["institution_id"])
        self.platform._teacher(actor, exam["institution_id"], exam["subject_id"])
        questions = self.platform._all("SELECT * FROM education_exam_questions WHERE exam_id=? AND state='active' ORDER BY position,id", (exam_id,))
        objective = [question for question in questions if question["question_type"] != "long_answer"]
        sessions = self.platform._all("SELECT * FROM education_exam_sessions WHERE exam_id=? AND state IN ('submitted','expired') ORDER BY submitted_at,started_at", (exam_id,))
        if not sessions:
            raise Conflict("Psychometrics require at least one submitted examination session.")
        answers_by_session: dict[str, dict[str, Any]] = {}
        totals: list[float] = []
        for session in sessions:
            answers_by_session[session["id"]] = {row["question_id"]: _decode(row["answer_json"], None) for row in self.platform._all("SELECT question_id,answer_json FROM education_exam_answers WHERE session_id=?", (session["id"],))}
            score = self.platform._one("SELECT final_score,max_marks FROM education_exam_scores WHERE session_id=?", (session["id"],))
            totals.append(100.0 * float(score["final_score"]) / float(score["max_marks"]) if score and float(score["max_marks"] or 0) else 0.0)
        item_vectors: list[list[float]] = []
        statistics_rows: list[dict[str, Any]] = []
        for question in objective:
            correct = _canonical(_decode(question["correct_answer_json"], None))
            item_scores: list[float] = []
            omitted = 0
            distractors: Counter[str] = Counter()
            for session in sessions:
                answer = answers_by_session[session["id"]].get(question["id"])
                canonical = _canonical(answer)
                if answer in (None, "", []):
                    omitted += 1
                    distractors["<omitted>"] += 1
                    item_scores.append(0.0)
                else:
                    distractors[json.dumps(answer, ensure_ascii=False, sort_keys=True, default=str)] += 1
                    item_scores.append(1.0 if canonical == correct else 0.0)
            item_vectors.append(item_scores)
            difficulty = _mean(item_scores)
            point_biserial = _correlation(item_scores, totals)
            correct_group = [total for total, score in zip(totals, item_scores) if score >= 1]
            incorrect_group = [total for total, score in zip(totals, item_scores) if score < 1]
            discrimination = (_mean(correct_group) or 0.0) - (_mean(incorrect_group) or 0.0) if correct_group and incorrect_group else None
            flags: list[str] = []
            if len(sessions) < 5:
                flags.append("insufficient_sample")
            if difficulty is not None and difficulty < 0.2:
                flags.append("very_difficult")
            if difficulty is not None and difficulty > 0.9:
                flags.append("very_easy")
            if point_biserial is not None and point_biserial < 0:
                flags.append("negative_discrimination")
            elif point_biserial is not None and point_biserial < 0.1:
                flags.append("low_discrimination")
            if omitted / len(sessions) > 0.2:
                flags.append("high_omission")
            statistics_rows.append({
                "question": question,
                "response_count": len(sessions),
                "omitted_count": omitted,
                "difficulty_index": difficulty,
                "discrimination_index": discrimination,
                "point_biserial": point_biserial,
                "mean_item_score": difficulty,
                "distractors": dict(distractors),
                "flags": flags,
            })
        alpha: float | None = None
        if len(item_vectors) >= 2 and len(sessions) >= 2:
            item_variances = sum(_variance(vector) for vector in item_vectors)
            total_item_scores = [sum(vector[index] for vector in item_vectors) for index in range(len(sessions))]
            total_variance = _variance(total_item_scores)
            if total_variance > 0:
                k = len(item_vectors)
                alpha = k / (k - 1) * (1 - item_variances / total_variance)
                alpha = max(-1.0, min(1.0, alpha))
        run_id, timestamp = ident("psych"), now()
        detail = {
            "method": "classical test theory; objective items only",
            "sample_warning": len(sessions) < 30,
            "human_review_required": True,
            "not_for_automatic_student_decisions": True,
        }
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_psychometric_runs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, exam["institution_id"], exam_id, len(sessions), len(objective), alpha, _mean(totals), "completed", _json(detail), actor, timestamp),
            )
            for item in statistics_rows:
                db.execute(
                    "INSERT INTO education_question_statistics VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ident("qstat"), run_id, exam["institution_id"], exam_id, item["question"]["id"], item["response_count"], item["omitted_count"], item["difficulty_index"], item["discrimination_index"], item["point_biserial"], item["mean_item_score"], _json(item["distractors"]), _json(item["flags"]), timestamp),
                )
        result = self.platform._one("SELECT * FROM education_psychometric_runs WHERE id=?", (run_id,))
        result["questions"] = self.psychometric_run(actor, run_id)["questions"]
        result["detail"] = detail
        return result

    def psychometric_run(self, actor: str, run_id: str) -> dict[str, Any]:
        run = self.platform._one("SELECT * FROM education_psychometric_runs WHERE id=?", (run_id,))
        if not run:
            raise Missing("Psychometric run not found.")
        self._require_staff(actor, run["institution_id"])
        questions = self.platform._all(
            """SELECT s.*,q.prompt,q.question_type,q.marks,q.difficulty,q.bloom_level
            FROM education_question_statistics s JOIN education_exam_questions q ON q.id=s.question_id
            WHERE s.run_id=? ORDER BY q.position,q.id""",
            (run_id,),
        )
        for row in questions:
            row["distractors"] = _decode(row.pop("distractor_json", "{}"), {})
            row["flags"] = _decode(row.pop("flags_json", "[]"), [])
        run["detail"] = _decode(run.pop("detail_json", "{}"), {})
        return {"run": run, "questions": questions}

    # ------------------------------------------------------------------
    # Transparent student-success support
    # ------------------------------------------------------------------
    def calculate_student_success_snapshot(self, actor: str, institution_id: str, student_id: str, subject_id: str) -> dict[str, Any]:
        self._require_staff(actor, institution_id)
        self.platform._teacher(actor, institution_id, subject_id)
        if not self.platform._one("SELECT 1 ok FROM enrollments WHERE subject_id=? AND student_id=? AND state='active'", (subject_id, student_id)):
            raise Denied("Student is not actively enrolled in this subject.")
        attendance_rows = self.platform._all(
            """SELECT r.status FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id
            WHERE r.institution_id=? AND r.student_id=? AND s.subject_id=?""",
            (institution_id, student_id, subject_id),
        )
        attendance_positive = {"present", "late", "excused_absence", "medical_leave", "institutional_duty", "online_present", "practical_attendance", "examination_attendance"}
        attendance = _percent(sum(1 for row in attendance_rows if row["status"] in attendance_positive), len(attendance_rows))
        grade_rows = self.platform._all(
            """SELECT g.marks,a.max_marks FROM grades g JOIN submissions s ON s.id=g.submission_id
            JOIN assignments a ON a.id=s.assignment_id WHERE g.institution_id=? AND s.student_id=? AND a.subject_id=? AND g.state='released'""",
            (institution_id, student_id, subject_id),
        )
        assignment_values = [100.0 * float(row["marks"]) / float(row["max_marks"]) for row in grade_rows if float(row["max_marks"] or 0)]
        assignment = _mean(assignment_values)
        mastery_rows = self.platform._all("SELECT mastery FROM education_mastery_state WHERE institution_id=? AND student_id=? AND subject_id=?", (institution_id, student_id, subject_id))
        mastery = 100.0 * (_mean([float(row["mastery"]) for row in mastery_rows]) or 0.0) if mastery_rows else None
        exam_rows = self.platform._all(
            """SELECT s.final_score,s.max_marks FROM education_exam_scores s JOIN examinations e ON e.id=s.exam_id
            WHERE s.institution_id=? AND s.student_id=? AND e.subject_id=? AND s.grading_state='completed'""",
            (institution_id, student_id, subject_id),
        )
        exam_values = [100.0 * float(row["final_score"]) / float(row["max_marks"]) for row in exam_rows if float(row["max_marks"] or 0)]
        exam = _mean(exam_values)
        metrics = {"attendance_percent": attendance, "assignment_percent": assignment, "mastery_percent": mastery, "exam_percent": exam}
        thresholds = {"attendance_percent": 75.0, "assignment_percent": 55.0, "mastery_percent": 50.0, "exam_percent": 50.0}
        factors = []
        for key, value in metrics.items():
            if value is not None and value < thresholds[key]:
                factors.append({"metric": key, "value": round(value, 2), "threshold": thresholds[key]})
        evidence_count = sum(value is not None for value in metrics.values())
        if evidence_count < 2:
            risk = "insufficient_evidence"
        elif len(factors) >= 2:
            risk = "priority_support"
        elif factors:
            risk = "watch"
        else:
            risk = "on_track"
        explanation = {
            "metrics": metrics,
            "thresholds": thresholds,
            "rules": "priority_support requires at least two measured indicators below transparent thresholds; watch requires one",
            "excluded_inputs": ["race", "religion", "gender", "health", "politics", "disability", "family_income"],
            "not_a_diagnosis": True,
            "human_review_required": True,
            "no_automatic_penalty": True,
        }
        snapshot_id, timestamp = ident("success"), now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_student_success_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (snapshot_id, institution_id, student_id, subject_id, attendance, assignment, mastery, exam, risk, _json(factors), _json(explanation), evidence_count, actor, timestamp),
            )
        result = self.platform._one("SELECT * FROM education_student_success_snapshots WHERE id=?", (snapshot_id,))
        result["factors"] = factors
        result["explanation"] = explanation
        return result

    def create_intervention_case(
        self,
        actor: str,
        snapshot_id: str,
        *,
        reason: str,
        action_plan: str,
        assigned_to: str,
        due_at: str | None = None,
        priority: str = "medium",
    ) -> dict[str, Any]:
        snapshot = self.platform._one("SELECT * FROM education_student_success_snapshots WHERE id=?", (snapshot_id,))
        if not snapshot:
            raise Missing("Student-success snapshot not found.")
        self._require_staff(actor, snapshot["institution_id"])
        if due_at:
            parse_time(due_at)
        if priority not in {"low", "medium", "high", "critical"}:
            raise EducationError("Unsupported intervention priority.")
        if not str(reason).strip() or not str(action_plan).strip():
            raise EducationError("Intervention reason and action plan are required.")
        case_id, timestamp = ident("intervention"), now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_intervention_cases VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (case_id, snapshot["institution_id"], snapshot_id, snapshot["student_id"], snapshot["subject_id"], priority, str(reason)[:10000], str(action_plan)[:20000], str(assigned_to)[:200], due_at, "open", "", actor, "", timestamp, timestamp, None),
            )
        self.platform._audit(actor, "student_support_case_created", "intervention_case", case_id, snapshot["institution_id"], {"student_id": snapshot["student_id"], "priority": priority, "human_review": True})
        return self.platform._one("SELECT * FROM education_intervention_cases WHERE id=?", (case_id,))

    def update_intervention_case(self, actor: str, case_id: str, *, state: str, review_note: str = "") -> dict[str, Any]:
        case = self.platform._one("SELECT * FROM education_intervention_cases WHERE id=?", (case_id,))
        if not case:
            raise Missing("Intervention case not found.")
        roles = self._roles(actor, case["institution_id"])
        if actor != case["assigned_to"] and not roles & TEACHER_ROLES:
            raise Denied("Intervention-case access denied.")
        value = str(state).strip().lower()
        if value not in INTERVENTION_STATES:
            raise EducationError("Unsupported intervention state.")
        timestamp = now()
        with self.db.connection() as db:
            db.execute("UPDATE education_intervention_cases SET state=?,review_note=?,reviewed_by=?,updated_at=?,closed_at=? WHERE id=?", (value, str(review_note)[:10000], actor, timestamp, timestamp if value in {"completed", "cancelled"} else None, case_id))
        return self.platform._one("SELECT * FROM education_intervention_cases WHERE id=?", (case_id,))

    # ------------------------------------------------------------------
    # Academic calendar and portable ICS export
    # ------------------------------------------------------------------
    def create_calendar_event(
        self,
        actor: str,
        institution_id: str,
        *,
        title: str,
        event_type: str,
        starts_at: str,
        ends_at: str,
        description: str = "",
        location: str = "",
        audience: dict[str, Any] | None = None,
        all_day: bool = False,
    ) -> dict[str, Any]:
        self._require_staff(actor, institution_id)
        start, end = parse_time(starts_at), parse_time(ends_at)
        if end <= start:
            raise EducationError("Calendar event end must follow start.")
        if not str(title).strip():
            raise EducationError("Calendar event title is required.")
        event_id, timestamp = ident("event"), now()
        with self.db.connection() as db:
            db.execute("INSERT INTO academic_events VALUES(?,?,?,?,?,?,?,?,?)", (event_id, institution_id, str(title).strip()[:500], str(event_type).strip()[:100] or "academic", start.isoformat(), end.isoformat(), "scheduled", timestamp, timestamp))
            db.execute("INSERT INTO education_calendar_details VALUES(?,?,?,?,?,?,?,?,?,?)", (event_id, institution_id, str(description)[:20000], str(location)[:500], _json(audience or {}), actor, int(bool(all_day)), "biointel", timestamp, timestamp))
        return self.calendar_event(actor, event_id)

    def calendar_event(self, actor: str, event_id: str) -> dict[str, Any]:
        row = self.platform._one("""SELECT e.*,d.description,d.location,d.audience_json,d.owner_id,d.all_day,d.source
        FROM academic_events e LEFT JOIN education_calendar_details d ON d.event_id=e.id WHERE e.id=?""", (event_id,))
        if not row:
            raise Missing("Calendar event not found.")
        self.platform._require(actor, row["institution_id"])
        row["audience"] = _decode(row.pop("audience_json", "{}"), {})
        return row

    def academic_calendar(self, actor: str, institution_id: str, *, start_at: str, end_at: str) -> dict[str, Any]:
        self.platform._require(actor, institution_id)
        start, end = parse_time(start_at), parse_time(end_at)
        if end <= start:
            raise EducationError("Calendar range end must follow start.")
        events = self.platform._all(
            """SELECT e.*,d.description,d.location,d.audience_json,d.owner_id,d.all_day,d.source
            FROM academic_events e LEFT JOIN education_calendar_details d ON d.event_id=e.id
            WHERE e.institution_id=? AND e.state='scheduled' AND e.starts_at<? AND e.ends_at>?
            ORDER BY e.starts_at,e.title""",
            (institution_id, end.isoformat(), start.isoformat()),
        )
        roles = self._roles(actor, institution_id)
        is_staff = bool(roles & TEACHER_ROLES)
        visible_events: list[dict[str, Any]] = []
        for row in events:
            audience = _decode(row.pop("audience_json", "{}"), {})
            allowed_roles = {str(item) for item in audience.get("roles", [])}
            allowed_users = {str(item) for item in audience.get("users", [])}
            visible = not audience or actor == row.get("owner_id") or bool(roles & ADMIN_ROLES)
            visible = visible or (bool(allowed_roles) and bool(roles & allowed_roles)) or actor in allowed_users
            if visible:
                row["audience"] = audience
                row["calendar_kind"] = "academic_event"
                visible_events.append(row)
        timetable = self.platform._all(
            """SELECT id,institution_id,subject_id,teacher_id,student_group,room,starts_at,ends_at,state
            FROM timetable_entries WHERE institution_id=? AND state='scheduled' AND starts_at<? AND ends_at>?
            ORDER BY starts_at""",
            (institution_id, end.isoformat(), start.isoformat()),
        )
        if not is_staff:
            enrolled_subjects = {row["subject_id"] for row in self.platform._all("SELECT subject_id FROM enrollments WHERE student_id=? AND state='active'", (actor,))}
            timetable = [row for row in timetable if row.get("subject_id") in enrolled_subjects]
        for row in timetable:
            row["title"] = (self.platform._one("SELECT code||' · '||name label FROM subjects WHERE id=?", (row["subject_id"],)) or {"label": "Class"})["label"]
            row["event_type"] = "class"
            row["description"] = f"Teacher {row['teacher_id']} · Group {row['student_group']}"
            row["location"] = row["room"]
            row["calendar_kind"] = "timetable"
        combined = sorted(visible_events + timetable, key=lambda row: str(row["starts_at"]))
        return {"institution_id": institution_id, "start_at": start.isoformat(), "end_at": end.isoformat(), "events": combined, "event_count": len(combined)}

    def export_calendar_ics(self, actor: str, institution_id: str, *, start_at: str, end_at: str) -> dict[str, Any]:
        calendar = self.academic_calendar(actor, institution_id, start_at=start_at, end_at=end_at)
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//BioIntel//Education Calendar//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
        for event in calendar["events"]:
            uid = f"{event['id']}@biointel.local"
            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{_ics_escape(uid)}",
                f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
                f"DTSTART:{_ics_datetime(event['starts_at'])}",
                f"DTEND:{_ics_datetime(event['ends_at'])}",
                f"SUMMARY:{_ics_escape(event.get('title'))}",
                f"DESCRIPTION:{_ics_escape(event.get('description'))}",
                f"LOCATION:{_ics_escape(event.get('location'))}",
                f"CATEGORIES:{_ics_escape(event.get('event_type'))}",
                "END:VEVENT",
            ])
        lines.append("END:VCALENDAR")
        content = "\r\n".join(lines) + "\r\n"
        output_root = self.root / "education" / "calendar_exports" / institution_id
        output_root.mkdir(parents=True, exist_ok=True)
        export_id, timestamp = ident("ical"), now()
        path = output_root / f"{export_id}.ics"
        path.write_text(content, encoding="utf-8", newline="")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.db.connection() as db:
            db.execute("INSERT INTO education_calendar_exports VALUES(?,?,?,?,?,?,?,?,?)", (export_id, institution_id, calendar["start_at"], calendar["end_at"], calendar["event_count"], str(path), digest, actor, timestamp))
        return self.platform._one("SELECT * FROM education_calendar_exports WHERE id=?", (export_id,))

    # ------------------------------------------------------------------
    # Phase posture
    # ------------------------------------------------------------------
    def phase14_posture(self, actor: str, institution_id: str) -> dict[str, Any]:
        self.platform._require(actor, institution_id)
        table_counts = {}
        for key, table in {
            "outcomes": "education_learning_outcomes",
            "approved_evidence": "education_outcome_evidence",
            "attainment_runs": "education_outcome_attainment_runs",
            "psychometric_runs": "education_psychometric_runs",
            "success_snapshots": "education_student_success_snapshots",
            "open_interventions": "education_intervention_cases",
            "calendar_exports": "education_calendar_exports",
        }.items():
            condition = "institution_id=?"
            if key == "approved_evidence":
                condition += " AND review_decision='approve'"
            if key == "open_interventions":
                condition += " AND state IN ('open','in_progress')"
            row = self.platform._one(f"SELECT COUNT(*) n FROM {table} WHERE {condition}", (institution_id,)) or {"n": 0}
            table_counts[key] = int(row["n"] or 0)
        controls = {
            "outcome_mapping": True,
            "evidence_review": True,
            "attainment_calculation": True,
            "quality_cycles": True,
            "psychometrics": True,
            "transparent_support_rules": True,
            "human_intervention_review": True,
            "portable_ics_calendar": True,
        }
        return {
            "institution_id": institution_id,
            "counts": table_counts,
            "controls": controls,
            "local_control_coverage_percent": round(100 * sum(controls.values()) / len(controls), 2),
            "qualification_boundaries": [
                "Outcome evidence organization does not itself confer accreditation.",
                "Psychometrics require adequate samples and expert interpretation.",
                "Student-support snapshots are transparent support signals, not diagnoses or automatic penalties.",
                "External calendar synchronization still requires provider credentials.",
            ],
        }
