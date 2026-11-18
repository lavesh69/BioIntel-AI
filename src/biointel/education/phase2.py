from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .platform import ADMIN, TEACHER, Denied, EducationError

MIGRATION_ID = "education_phase2_visual_intelligence_v1"
DASHBOARD_WIDGETS: tuple[str, ...] = (
    "today_timeline",
    "pending_actions",
    "attendance_trend",
    "assignment_deadlines",
    "course_progress",
    "research_activity",
    "shiro_recommendations",
    "connect_meetings",
    "lecture_status",
    "pulse_alerts",
    "portfolio_progress",
    "opportunity_deadlines",
    "system_health",
)
DEFAULT_DASHBOARD_WIDGETS: tuple[str, ...] = DASHBOARD_WIDGETS[:6] + ("system_health",)
REPORT_TYPES: tuple[str, ...] = (
    "attendance",
    "assignment_completion",
    "examination_results",
    "academy_progress",
    "learning_analytics",
    "research_projects",
    "portfolio_status",
    "laboratory_inventory",
)
SCHEMA = r"""
CREATE TABLE IF NOT EXISTS education_dashboard_preferences(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 user_id TEXT NOT NULL,
 preset_name TEXT NOT NULL,
 widgets_json TEXT NOT NULL,
 density TEXT NOT NULL DEFAULT 'compact',
 academic_session TEXT NOT NULL DEFAULT '',
 date_start TEXT NOT NULL DEFAULT '',
 date_end TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,user_id,preset_name)
);
CREATE INDEX IF NOT EXISTS idx_education_dashboard_preferences_user
 ON education_dashboard_preferences(institution_id,user_id,updated_at);
CREATE TABLE IF NOT EXISTS education_institution_branding(
 institution_id TEXT PRIMARY KEY,
 campus_name TEXT NOT NULL DEFAULT '',
 accent_color TEXT NOT NULL DEFAULT '#22D3EE',
 certificate_footer TEXT NOT NULL DEFAULT '',
 course_cover_style TEXT NOT NULL DEFAULT 'scientific-grid',
 login_welcome_text TEXT NOT NULL DEFAULT '',
 footer_information TEXT NOT NULL DEFAULT '',
 logo_file_name TEXT NOT NULL DEFAULT '',
 logo_sha256 TEXT NOT NULL DEFAULT '',
 logo_storage_path TEXT NOT NULL DEFAULT '',
 updated_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS education_saved_reports(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 owner_id TEXT NOT NULL,
 report_type TEXT NOT NULL,
 title TEXT NOT NULL,
 filters_json TEXT NOT NULL DEFAULT '{}',
 schedule_state TEXT NOT NULL DEFAULT 'manual_only',
 schedule_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_education_saved_reports_tenant
 ON education_saved_reports(institution_id,owner_id,updated_at);
CREATE TABLE IF NOT EXISTS education_presentation_runs(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 actor_id TEXT NOT NULL,
 persona_id TEXT NOT NULL,
 scenario_id TEXT NOT NULL,
 state TEXT NOT NULL,
 synthetic_acknowledged INTEGER NOT NULL DEFAULT 1,
 started_at TEXT NOT NULL,
 ended_at TEXT
);
INSERT OR IGNORE INTO education_migrations(id,applied_at)
 VALUES('education_phase2_visual_intelligence_v1',datetime('now'));
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _decode(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


class EducationPhase2:
    """Persistent Phase 2 preferences, visual aggregates, reports and presentation audit."""

    def __init__(self, platform: Any):
        self.platform = platform
        self.db = platform.db
        self.migrate()

    def migrate(self) -> str:
        with self.db.connection() as db:
            db.executescript(SCHEMA)
        return MIGRATION_ID

    def _roles(self, actor: str, institution_id: str) -> set[str]:
        return {str(item["role"]) for item in self.platform._require(actor, institution_id)}

    def _require_staff(self, actor: str, institution_id: str) -> set[str]:
        roles = self._roles(actor, institution_id)
        if not roles & TEACHER:
            raise Denied("Education reporting requires an educator or administrator role.")
        return roles

    def _require_admin(self, actor: str, institution_id: str) -> set[str]:
        roles = self._roles(actor, institution_id)
        if not roles & ADMIN:
            raise Denied("Institution branding requires an administrator role.")
        return roles

    def preferences(self, actor: str, institution_id: str, preset_name: str = "Default") -> dict[str, Any]:
        self._roles(actor, institution_id)
        row = self.platform._one(
            "SELECT * FROM education_dashboard_preferences WHERE institution_id=? AND user_id=? AND preset_name=?",
            (institution_id, actor, preset_name),
        )
        if not row:
            return {
                "preset_name": preset_name,
                "widgets": list(DEFAULT_DASHBOARD_WIDGETS),
                "density": "compact",
                "academic_session": "",
                "date_start": "",
                "date_end": "",
                "persisted": False,
            }
        result = dict(row)
        result["widgets"] = [key for key in _decode(result.pop("widgets_json"), []) if key in DASHBOARD_WIDGETS]
        result["persisted"] = True
        return result

    def save_preferences(
        self,
        actor: str,
        institution_id: str,
        preset_name: str,
        widgets: Iterable[str],
        density: str = "compact",
        academic_session: str = "",
        date_start: str = "",
        date_end: str = "",
    ) -> dict[str, Any]:
        self._roles(actor, institution_id)
        name = preset_name.strip()[:80]
        if not name:
            raise EducationError("Dashboard preset name is required.")
        ordered: list[str] = []
        for key in widgets:
            if key in DASHBOARD_WIDGETS and key not in ordered:
                ordered.append(key)
        if density not in {"compact", "expanded"}:
            raise EducationError("Dashboard density must be compact or expanded.")
        t = _now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_dashboard_preferences
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,user_id,preset_name) DO UPDATE SET
                widgets_json=excluded.widgets_json,density=excluded.density,
                academic_session=excluded.academic_session,date_start=excluded.date_start,
                date_end=excluded.date_end,updated_at=excluded.updated_at""",
                (_id("dashpref"), institution_id, actor, name, _json(ordered), density, academic_session.strip(), date_start, date_end, t, t),
            )
        self.platform._audit(actor, "dashboard_preference_saved", "dashboard_preset", name, institution_id, {"widgets": ordered, "density": density})
        return self.preferences(actor, institution_id, name)

    def reset_preferences(self, actor: str, institution_id: str, preset_name: str = "Default") -> dict[str, Any]:
        self._roles(actor, institution_id)
        with self.db.connection() as db:
            db.execute(
                "DELETE FROM education_dashboard_preferences WHERE institution_id=? AND user_id=? AND preset_name=?",
                (institution_id, actor, preset_name),
            )
        self.platform._audit(actor, "dashboard_preference_reset", "dashboard_preset", preset_name, institution_id)
        return self.preferences(actor, institution_id, preset_name)

    def branding(self, actor: str, institution_id: str) -> dict[str, Any]:
        self._roles(actor, institution_id)
        row = self.platform._one("SELECT * FROM education_institution_branding WHERE institution_id=?", (institution_id,))
        if row:
            return row
        institution = self.platform._one("SELECT name FROM institutions WHERE id=?", (institution_id,)) or {}
        return {
            "institution_id": institution_id,
            "campus_name": institution.get("name", ""),
            "accent_color": "#22D3EE",
            "certificate_footer": "",
            "course_cover_style": "scientific-grid",
            "login_welcome_text": "",
            "footer_information": "",
            "logo_file_name": "",
            "logo_sha256": "",
            "logo_storage_path": "",
            "persisted": False,
        }

    def logo_path(self, branding: Mapping[str, Any]) -> str | None:
        candidate = str(branding.get("logo_storage_path") or "")
        if not candidate:
            return None
        path = Path(candidate).resolve()
        root = self.platform.storage.resolve()
        if root != path and root not in path.parents:
            return None
        return str(path) if path.is_file() else None

    def save_branding(
        self,
        actor: str,
        institution_id: str,
        *,
        campus_name: str,
        accent_color: str,
        certificate_footer: str,
        course_cover_style: str,
        login_welcome_text: str,
        footer_information: str,
        logo_name: str = "",
        logo_mime: str = "",
        logo_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        self._require_admin(actor, institution_id)
        accent = accent_color.strip().upper()
        if not re.fullmatch(r"#[0-9A-F]{6}", accent):
            raise EducationError("Accent color must be a six-digit hexadecimal color such as #22D3EE.")
        if course_cover_style not in {"scientific-grid", "molecular-lines", "clean-academic"}:
            raise EducationError("Unsupported course-cover branding style.")
        current = self.branding(actor, institution_id)
        stored_name = str(current.get("logo_file_name") or "")
        stored_sha = str(current.get("logo_sha256") or "")
        stored_path = str(current.get("logo_storage_path") or "")
        if logo_bytes is not None:
            if len(logo_bytes) > 2 * 1024 * 1024:
                raise EducationError("Institution logo must be 2 MB or smaller.")
            signatures = {"image/png": (b"\x89PNG\r\n\x1a\n", ".png"), "image/jpeg": (b"\xff\xd8\xff", ".jpg")}
            signature = signatures.get(logo_mime)
            if not signature or not logo_bytes.startswith(signature[0]):
                raise EducationError("Institution logo must be a validated PNG or JPEG image.")
            target_dir = (self.platform.storage / "branding" / institution_id).resolve()
            storage_root = self.platform.storage.resolve()
            if storage_root not in target_dir.parents:
                raise EducationError("Unsafe branding storage target.")
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"institution-logo{signature[1]}"
            target.write_bytes(logo_bytes)
            stored_name = Path(logo_name).name[:160]
            stored_sha = hashlib.sha256(logo_bytes).hexdigest()
            stored_path = str(target)
        t = _now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_institution_branding VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id) DO UPDATE SET campus_name=excluded.campus_name,
                accent_color=excluded.accent_color,certificate_footer=excluded.certificate_footer,
                course_cover_style=excluded.course_cover_style,login_welcome_text=excluded.login_welcome_text,
                footer_information=excluded.footer_information,logo_file_name=excluded.logo_file_name,
                logo_sha256=excluded.logo_sha256,logo_storage_path=excluded.logo_storage_path,
                updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
                (institution_id, campus_name.strip()[:160], accent, certificate_footer.strip()[:500], course_cover_style,
                 login_welcome_text.strip()[:500], footer_information.strip()[:500], stored_name, stored_sha, stored_path, actor, t, t),
            )
        self.platform._audit(actor, "institution_branding_updated", "institution", institution_id, institution_id, {"accent_color": accent, "logo_sha256": stored_sha})
        return self.branding(actor, institution_id)

    def dashboard_snapshot(self, actor: str, institution_id: str) -> dict[str, Any]:
        roles = self._roles(actor, institution_id)
        staff = bool(roles & TEACHER)
        student_filter = "" if staff else actor
        attendance_sql = """SELECT s.session_date date,r.status status,COUNT(*) records
            FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id
            WHERE r.institution_id=?"""
        attendance_args: tuple[Any, ...] = (institution_id,)
        if not staff:
            attendance_sql += " AND r.student_id=?"
            attendance_args = (institution_id, actor)
        attendance_sql += " GROUP BY s.session_date,r.status ORDER BY s.session_date"
        attendance = self.platform._all(attendance_sql, attendance_args)
        if staff:
            assignments = self.platform._all("""SELECT a.id,a.title,a.state,a.due_at,s.name subject,
                COUNT(DISTINCT sub.id) submissions,COUNT(DISTINCT g.id) graded
                FROM assignments a JOIN subjects s ON s.id=a.subject_id
                LEFT JOIN submissions sub ON sub.assignment_id=a.id LEFT JOIN grades g ON g.submission_id=sub.id
                WHERE a.institution_id=? GROUP BY a.id ORDER BY a.due_at LIMIT 100""", (institution_id,))
            courses = self.platform._all("""SELECT c.id,c.title,c.state,c.difficulty,
                COUNT(DISTINCT l.id) lectures,COUNT(DISTINCT ae.id) enrollments,
                COUNT(DISTINCT CASE WHEN wp.completed=1 THEN wp.id END) completed_lecture_views,
                COUNT(DISTINCT wp.id) progress_rows FROM courses c LEFT JOIN lectures l ON l.course_id=c.id
                LEFT JOIN academy_enrollments ae ON ae.course_id=c.id LEFT JOIN watch_progress wp ON wp.lecture_id=l.id
                WHERE c.institution_id=? GROUP BY c.id ORDER BY c.updated_at DESC""", (institution_id,))
            universe = self.platform._all("""SELECT module_key,state,source_status,COUNT(*) records,MAX(updated_at) updated_at
                FROM education_universe_records WHERE institution_id=? AND deleted_at IS NULL
                GROUP BY module_key,state,source_status""", (institution_id,))
            lectures = self.platform._all("SELECT processing_state,COUNT(*) records FROM lectures WHERE institution_id=? GROUP BY processing_state", (institution_id,))
        else:
            assignments = self.platform._all("""SELECT a.id,a.title,a.state,a.due_at,s.name subject,
                COUNT(DISTINCT sub.id) submissions,COUNT(DISTINCT g.id) graded
                FROM assignments a JOIN subjects s ON s.id=a.subject_id
                LEFT JOIN submissions sub ON sub.assignment_id=a.id AND sub.student_id=?
                LEFT JOIN grades g ON g.submission_id=sub.id WHERE a.institution_id=? AND a.state IN ('published','closed')
                AND EXISTS(SELECT 1 FROM enrollments e WHERE e.subject_id=a.subject_id AND e.student_id=? AND e.state='active')
                GROUP BY a.id ORDER BY a.due_at LIMIT 100""", (actor, institution_id, actor))
            courses = self.platform._all("""SELECT c.id,c.title,c.state,c.difficulty,COUNT(DISTINCT l.id) lectures,
                COUNT(DISTINCT ae.id) enrollments,COUNT(DISTINCT CASE WHEN wp.completed=1 THEN wp.id END) completed_lecture_views,
                COUNT(DISTINCT wp.id) progress_rows FROM courses c LEFT JOIN lectures l ON l.course_id=c.id
                LEFT JOIN academy_enrollments ae ON ae.course_id=c.id AND ae.student_id=?
                LEFT JOIN watch_progress wp ON wp.lecture_id=l.id AND wp.user_id=?
                WHERE c.institution_id=? AND c.state='published' AND EXISTS(SELECT 1 FROM academy_enrollments own
                WHERE own.course_id=c.id AND own.student_id=? AND own.state='active') GROUP BY c.id ORDER BY c.updated_at DESC""", (actor, actor, institution_id, actor))
            from .universe import EducationUniverse
            visible = EducationUniverse(self.platform).list_records(actor, institution_id, limit=500)
            buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
            for row in visible:
                key = (str(row.get("module_key")), str(row.get("state")), str(row.get("source_status")))
                bucket = buckets.setdefault(key, {"module_key": key[0], "state": key[1], "source_status": key[2], "records": 0, "updated_at": ""})
                bucket["records"] += 1
                bucket["updated_at"] = max(str(bucket["updated_at"]), str(row.get("updated_at") or ""))
            universe = list(buckets.values())
            lectures = self.platform._all("""SELECT l.processing_state,COUNT(*) records FROM lectures l JOIN courses c ON c.id=l.course_id
                WHERE l.institution_id=? AND c.state='published' AND EXISTS(SELECT 1 FROM academy_enrollments ae
                WHERE ae.course_id=c.id AND ae.student_id=? AND ae.state='active') GROUP BY l.processing_state""", (institution_id, actor))
        alerts = self.platform._all("SELECT state,COUNT(*) records FROM alerts WHERE user_id=? GROUP BY state", (actor,))
        return {"roles": sorted(roles), "attendance": attendance, "assignments": assignments, "courses": courses,
            "universe": universe, "lectures": lectures, "alerts": alerts,
            "activity": self.activity_stream(actor, institution_id, limit=40), "student_filter": student_filter,
            "calculated_at": _now(), "data_origin": "persisted_education_records"}
    def activity_stream(self, actor: str, institution_id: str, limit: int = 50) -> list[dict[str, Any]]:
        roles = self._roles(actor, institution_id)
        staff = bool(roles & TEACHER)
        events: list[dict[str, Any]] = []
        if staff:
            specs = (
                ("SELECT id,title,state,created_at FROM assignments WHERE institution_id=?", (institution_id,), "Assignment published", "pages/340_BioIntel_Classroom.py", "assignment"),
                ("SELECT id,student_id title,state,created_at FROM submissions WHERE institution_id=?", (institution_id,), "Submission received", "pages/340_BioIntel_Classroom.py", "submission"),
                ("SELECT id,title,state,created_at FROM courses WHERE institution_id=?", (institution_id,), "Course created", "pages/342_BioIntel_Academy_and_Lecture_Studio.py", "course"),
                ("SELECT id,student_id title,state,created_at FROM academy_enrollments WHERE institution_id=?", (institution_id,), "Course enrolled", "pages/342_BioIntel_Academy_and_Lecture_Studio.py", "academy_enrollment"),
                ("SELECT id,verification_code title,'issued' state,created_at FROM certificates WHERE institution_id=?", (institution_id,), "Certificate issued", "pages/342_BioIntel_Academy_and_Lecture_Studio.py", "certificate"),
            )
        else:
            specs = (
                ("""SELECT a.id,a.title,a.state,a.created_at FROM assignments a WHERE a.institution_id=?
                    AND a.state IN ('published','closed') AND EXISTS(SELECT 1 FROM enrollments e WHERE e.subject_id=a.subject_id AND e.student_id=? AND e.state='active')""", (institution_id, actor), "Assignment published", "pages/340_BioIntel_Classroom.py", "assignment"),
                ("SELECT id,student_id title,state,created_at FROM submissions WHERE institution_id=? AND student_id=?", (institution_id, actor), "Submission recorded", "pages/340_BioIntel_Classroom.py", "submission"),
                ("""SELECT c.id,c.title,c.state,c.created_at FROM courses c WHERE c.institution_id=? AND c.state='published'
                    AND EXISTS(SELECT 1 FROM academy_enrollments ae WHERE ae.course_id=c.id AND ae.student_id=? AND ae.state='active')""", (institution_id, actor), "Course available", "pages/342_BioIntel_Academy_and_Lecture_Studio.py", "course"),
                ("SELECT id,student_id title,state,created_at FROM academy_enrollments WHERE institution_id=? AND student_id=?", (institution_id, actor), "Course enrolled", "pages/342_BioIntel_Academy_and_Lecture_Studio.py", "academy_enrollment"),
                ("SELECT id,verification_code title,'issued' state,created_at FROM certificates WHERE institution_id=? AND student_id=?", (institution_id, actor), "Certificate issued", "pages/342_BioIntel_Academy_and_Lecture_Studio.py", "certificate"),
            )
        common = (
            ("SELECT id,student_group title,state,created_at FROM timetable_entries WHERE institution_id=?", (institution_id,), "Meeting or class scheduled", "pages/340_BioIntel_Classroom.py", "timetable"),
            ("SELECT id,title,state,created_at FROM academic_events WHERE institution_id=?", (institution_id,), "Academic event scheduled", "pages/343_BioIntel_Education_Universe.py", "academic_event"),
        )
        for sql, args, action, page, source in (*specs, *common):
            for row in self.platform._all(sql, args):
                events.append({"id": row.get("id"), "title": f"{action}: {row.get('title') or row.get('id')}", "detail": source.replace("_", " ").title(), "state": row.get("state", "recorded"), "when": row.get("created_at"), "page": page, "source": source})
        attendance_sql = """SELECT r.id,r.student_id title,r.status state,r.updated_at created_at
            FROM attendance_records r WHERE r.institution_id=?"""
        attendance_args: tuple[Any, ...] = (institution_id,)
        if not staff:
            attendance_sql += " AND r.student_id=?"
            attendance_args = (institution_id, actor)
        attendance_sql += " ORDER BY r.updated_at DESC LIMIT 100"
        for row in self.platform._all(attendance_sql, attendance_args):
            events.append({"id": row["id"], "title": f"Attendance marked: {row['title']}", "detail": "Classroom attendance", "state": row["state"], "when": row["created_at"], "page": "pages/340_BioIntel_Classroom.py", "source": "attendance"})
        from .universe import EducationUniverse
        visible_ids = {row["id"] for row in EducationUniverse(self.platform).list_records(actor, institution_id, limit=500)}
        universe_events = self.platform._all(
            """SELECT e.id,e.record_id,r.title,e.event_type,e.to_state state,e.created_at,r.module_key
            FROM education_universe_events e JOIN education_universe_records r ON r.id=e.record_id
            WHERE e.institution_id=? ORDER BY e.created_at DESC LIMIT 200""",
            (institution_id,),
        )
        for row in universe_events:
            if row["record_id"] not in visible_ids:
                continue
            events.append({"id": row["id"], "title": f"{str(row['event_type']).replace('_',' ').title()}: {row['title']}", "detail": str(row["module_key"]).replace("_", " ").title(), "state": row.get("state") or "recorded", "when": row["created_at"], "page": "pages/343_BioIntel_Education_Universe.py", "source": row["module_key"]})
        events.sort(key=lambda item: str(item.get("when") or ""), reverse=True)
        return events[: max(1, min(int(limit), 200))]
    def classroom_snapshot(self, actor: str, institution_id: str) -> dict[str, Any]:
        roles = self._roles(actor, institution_id)
        staff = bool(roles & TEACHER)
        attendance_sql = """SELECT s.session_date date,sub.name subject,r.student_id,r.status
            FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id
            JOIN subjects sub ON sub.id=s.subject_id WHERE r.institution_id=?"""
        attendance_args: tuple[Any, ...] = (institution_id,)
        if not staff:
            attendance_sql += " AND r.student_id=?"
            attendance_args = (institution_id, actor)
        attendance_sql += " ORDER BY s.session_date"
        if staff:
            subjects = self.platform._all("SELECT id,code,name,state FROM subjects WHERE institution_id=? ORDER BY name", (institution_id,))
            assignments = self.platform._all("""SELECT a.id,a.title,a.state,a.due_at,s.name subject,
                COUNT(sub.id) submissions,COUNT(g.id) graded FROM assignments a JOIN subjects s ON s.id=a.subject_id
                LEFT JOIN submissions sub ON sub.assignment_id=a.id LEFT JOIN grades g ON g.submission_id=sub.id
                WHERE a.institution_id=? GROUP BY a.id ORDER BY a.due_at""", (institution_id,))
        else:
            subjects = self.platform._all("""SELECT s.id,s.code,s.name,s.state FROM subjects s JOIN enrollments e ON e.subject_id=s.id
                WHERE s.institution_id=? AND e.student_id=? AND e.state='active' ORDER BY s.name""", (institution_id, actor))
            assignments = self.platform._all("""SELECT a.id,a.title,a.state,a.due_at,s.name subject,
                COUNT(sub.id) submissions,COUNT(g.id) graded FROM assignments a JOIN subjects s ON s.id=a.subject_id
                LEFT JOIN submissions sub ON sub.assignment_id=a.id AND sub.student_id=?
                LEFT JOIN grades g ON g.submission_id=sub.id WHERE a.institution_id=? AND a.state IN ('published','closed')
                AND EXISTS(SELECT 1 FROM enrollments e WHERE e.subject_id=a.subject_id AND e.student_id=? AND e.state='active')
                GROUP BY a.id ORDER BY a.due_at""", (actor, institution_id, actor))
        return {"subjects": subjects, "attendance": self.platform._all(attendance_sql, attendance_args),
            "assignments": assignments, "timeline": self.activity_stream(actor, institution_id, 30), "calculated_at": _now()}

    def academy_snapshot(self, actor: str, institution_id: str) -> dict[str, Any]:
        roles = self._roles(actor, institution_id)
        staff = bool(roles & TEACHER)
        if staff:
            courses = self.platform._all("""SELECT c.id,c.title,c.difficulty,c.state,c.updated_at,
                COUNT(DISTINCT l.id) lectures,COUNT(DISTINCT ae.id) enrollments,
                COUNT(DISTINCT wp.id) progress_rows,COUNT(DISTINCT CASE WHEN wp.completed=1 THEN wp.id END) completed
                FROM courses c LEFT JOIN lectures l ON l.course_id=c.id LEFT JOIN academy_enrollments ae ON ae.course_id=c.id
                LEFT JOIN watch_progress wp ON wp.lecture_id=l.id WHERE c.institution_id=? GROUP BY c.id ORDER BY c.updated_at DESC""", (institution_id,))
            lectures = self.platform._all("SELECT id,title,course_id,processing_state,state,updated_at FROM lectures WHERE institution_id=? ORDER BY updated_at DESC", (institution_id,))
        else:
            courses = self.platform._all("""SELECT c.id,c.title,c.difficulty,c.state,c.updated_at,COUNT(DISTINCT l.id) lectures,
                COUNT(DISTINCT ae.id) enrollments,COUNT(DISTINCT wp.id) progress_rows,
                COUNT(DISTINCT CASE WHEN wp.completed=1 THEN wp.id END) completed FROM courses c
                LEFT JOIN lectures l ON l.course_id=c.id LEFT JOIN academy_enrollments ae ON ae.course_id=c.id AND ae.student_id=?
                LEFT JOIN watch_progress wp ON wp.lecture_id=l.id AND wp.user_id=? WHERE c.institution_id=? AND c.state='published'
                AND EXISTS(SELECT 1 FROM academy_enrollments own WHERE own.course_id=c.id AND own.student_id=? AND own.state='active')
                GROUP BY c.id ORDER BY c.updated_at DESC""", (actor, actor, institution_id, actor))
            lectures = self.platform._all("""SELECT l.id,l.title,l.course_id,l.processing_state,l.state,l.updated_at FROM lectures l
                JOIN courses c ON c.id=l.course_id WHERE l.institution_id=? AND c.state='published'
                AND EXISTS(SELECT 1 FROM academy_enrollments ae WHERE ae.course_id=c.id AND ae.student_id=? AND ae.state='active')
                ORDER BY l.updated_at DESC""", (institution_id, actor))
        return {"courses": courses, "lectures": lectures, "calculated_at": _now()}
    def pulse_snapshot(self, actor: str) -> dict[str, Any]:
        publications = self.platform._all("SELECT id,title,record_type,retraction_state,published_at,source_url,metadata_json FROM publications ORDER BY published_at DESC LIMIT 500")
        for item in publications:
            item["metadata"] = _decode(item.pop("metadata_json", "{}"), {})
        news = self.platform._all("SELECT id,title,published_at,topics_json,source_url FROM news_items ORDER BY published_at DESC LIMIT 500")
        for item in news:
            item["topics"] = _decode(item.pop("topics_json", "[]"), [])
        return {
            "publications": publications,
            "news": news,
            "sources": self.platform._all("SELECT id,name,source_type,configured,state FROM pulse_sources ORDER BY name"),
            "alerts": self.platform._all("SELECT id,query,resource_type,state,updated_at FROM alerts WHERE user_id=?", (actor,)),
            "saved": self.platform._all("SELECT resource_type,resource_id,created_at FROM saved_research WHERE user_id=?", (actor,)),
            "calculated_at": _now(),
        }

    def module_records(self, actor: str, institution_id: str, module_key: str) -> list[dict[str, Any]]:
        # Reuse the canonical Universe access policy so visual summaries never
        # bypass protected-question-bank or record-visibility boundaries.
        from .universe import EducationUniverse
        return EducationUniverse(self.platform).list_records(actor, institution_id, module_key=module_key, limit=250)

    def report_rows(self, actor: str, institution_id: str, report_type: str) -> list[dict[str, Any]]:
        self._require_staff(actor, institution_id)
        if report_type not in REPORT_TYPES:
            raise EducationError("Unsupported Education report type.")
        queries: dict[str, tuple[str, tuple[Any, ...]]] = {
            "attendance": ("""SELECT s.session_date AS Date,sub.code AS Subject,r.student_id AS Student,r.status AS Status
                FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id JOIN subjects sub ON sub.id=s.subject_id
                WHERE r.institution_id=? ORDER BY s.session_date,r.student_id""", (institution_id,)),
            "assignment_completion": ("""SELECT a.title AS Assignment,s.name AS Subject,a.state AS State,a.due_at AS Deadline,
                COUNT(sub.id) AS Submissions,COUNT(g.id) AS Graded FROM assignments a JOIN subjects s ON s.id=a.subject_id
                LEFT JOIN submissions sub ON sub.assignment_id=a.id LEFT JOIN grades g ON g.submission_id=sub.id
                WHERE a.institution_id=? GROUP BY a.id ORDER BY a.due_at""", (institution_id,)),
            "examination_results": ("""SELECT e.title AS Examination,s.name AS Subject,r.student_id AS Student,
                r.marks AS Marks,r.grade AS Grade,r.published AS Published FROM results r JOIN examinations e ON e.id=r.examination_id
                JOIN subjects s ON s.id=e.subject_id WHERE e.institution_id=? ORDER BY e.title,r.student_id""", (institution_id,)),
            "academy_progress": ("""SELECT c.title AS Course,ae.student_id AS Student,ae.state AS Enrollment,
                COUNT(wp.id) AS Progress_events,SUM(CASE WHEN wp.completed=1 THEN 1 ELSE 0 END) AS Completed_lectures
                FROM academy_enrollments ae JOIN courses c ON c.id=ae.course_id LEFT JOIN lectures l ON l.course_id=c.id
                LEFT JOIN watch_progress wp ON wp.lecture_id=l.id AND wp.user_id=ae.student_id
                WHERE ae.institution_id=? GROUP BY c.id,ae.student_id ORDER BY c.title,ae.student_id""", (institution_id,)),
            "learning_analytics": ("""SELECT title AS Metric,state AS State,source_status AS Source_status,updated_at AS Updated
                FROM education_universe_records WHERE institution_id=? AND module_key='learning_analytics' AND deleted_at IS NULL ORDER BY updated_at DESC""", (institution_id,)),
            "research_projects": ("""SELECT title AS Project,record_type AS Type,state AS State,owner_id AS Owner,updated_at AS Updated
                FROM education_universe_records WHERE institution_id=? AND module_key='research_hub' AND deleted_at IS NULL ORDER BY updated_at DESC""", (institution_id,)),
            "portfolio_status": ("""SELECT title AS Portfolio_item,record_type AS Type,state AS State,owner_id AS Owner,updated_at AS Updated
                FROM education_universe_records WHERE institution_id=? AND module_key='academic_portfolio' AND deleted_at IS NULL ORDER BY updated_at DESC""", (institution_id,)),
            "laboratory_inventory": ("""SELECT title AS Laboratory_item,record_type AS Type,state AS State,owner_id AS Owner,updated_at AS Updated
                FROM education_universe_records WHERE institution_id=? AND module_key='laboratory_management' AND deleted_at IS NULL ORDER BY updated_at DESC""", (institution_id,)),
        }
        sql, args = queries[report_type]
        return self.platform._all(sql, args)

    def save_report(self, actor: str, institution_id: str, report_type: str, title: str, filters: Mapping[str, Any] | None = None, schedule: Mapping[str, Any] | None = None) -> dict[str, Any]:
        self._require_staff(actor, institution_id)
        if report_type not in REPORT_TYPES:
            raise EducationError("Unsupported Education report type.")
        clean_title = title.strip()[:160]
        if not clean_title:
            raise EducationError("Report title is required.")
        schedule_data = dict(schedule or {})
        schedule_state = "configuration_required" if schedule_data else "manual_only"
        rid, t = _id("edureport"), _now()
        with self.db.connection() as db:
            db.execute("INSERT INTO education_saved_reports VALUES(?,?,?,?,?,?,?,?,?,?)", (rid, institution_id, actor, report_type, clean_title, _json(filters or {}), schedule_state, _json(schedule_data), t, t))
        self.platform._audit(actor, "education_report_saved", "education_report", rid, institution_id, {"report_type": report_type, "schedule_state": schedule_state})
        return self.platform._one("SELECT * FROM education_saved_reports WHERE id=?", (rid,)) or {}

    def list_reports(self, actor: str, institution_id: str) -> list[dict[str, Any]]:
        self._require_staff(actor, institution_id)
        rows = self.platform._all("SELECT * FROM education_saved_reports WHERE institution_id=? ORDER BY updated_at DESC LIMIT 100", (institution_id,))
        for row in rows:
            row["filters"] = _decode(row.pop("filters_json", "{}"), {})
            row["schedule"] = _decode(row.pop("schedule_json", "{}"), {})
        return rows

    def start_presentation(self, actor: str, institution_id: str, persona_id: str, scenario_id: str, synthetic_acknowledged: bool) -> dict[str, Any]:
        self._roles(actor, institution_id)
        if not persona_id.strip() or not scenario_id.strip():
            raise EducationError("Presentation persona and scenario are required.")
        if not self.platform.membership(persona_id, institution_id):
            raise Denied("Presentation persona must be an active institution member.")
        if not synthetic_acknowledged:
            raise EducationError("Presentation Mode must keep the synthetic-data disclosure visible.")
        run_id, t = _id("presentation"), _now()
        with self.db.connection() as db:
            db.execute("INSERT INTO education_presentation_runs VALUES(?,?,?,?,?,?,?,?,NULL)", (run_id, institution_id, actor, persona_id, scenario_id, "active", 1, t))
        return self.platform._one("SELECT * FROM education_presentation_runs WHERE id=?", (run_id,)) or {}

    def finish_presentation(self, actor: str, run_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_presentation_runs WHERE id=?", (run_id,))
        if not row or row["actor_id"] != actor:
            raise Denied("Presentation run access denied.")
        with self.db.connection() as db:
            db.execute("UPDATE education_presentation_runs SET state='completed',ended_at=? WHERE id=?", (_now(), run_id))
        return self.platform._one("SELECT * FROM education_presentation_runs WHERE id=?", (run_id,)) or {}

    @staticmethod
    def export_csv(rows: Iterable[Mapping[str, Any]]) -> bytes:
        values = list(rows)
        if not values:
            return b""
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=list(values[0]))
        writer.writeheader()
        writer.writerows(values)
        return buffer.getvalue().encode("utf-8-sig")

    @staticmethod
    def export_xlsx(rows: Iterable[Mapping[str, Any]], sheet_name: str = "Education report") -> bytes:
        import pandas as pd
        values = list(rows)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            pd.DataFrame(values).to_excel(writer, index=False, sheet_name=sheet_name[:31])
        return buffer.getvalue()

    @staticmethod
    def export_pdf(rows: Iterable[Mapping[str, Any]], title: str) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        values = list(rows)
        buffer = io.BytesIO()
        document = SimpleDocTemplate(buffer, pagesize=landscape(letter), title=title, author="BioIntel AI")
        styles = getSampleStyleSheet()
        story: list[Any] = [Paragraph(title, styles["Title"]), Paragraph("Generated from persisted BioIntel Education records.", styles["BodyText"]), Spacer(1, 12)]
        if values:
            columns = list(values[0])
            data = [columns] + [[str(row.get(column, ""))[:120] for column in columns] for row in values[:500]]
            table = Table(data, repeatRows=1)
            table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B2948")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9FB3C8")), ("FONTSIZE", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(table)
        else:
            story.append(Paragraph("No persisted rows matched the selected report.", styles["BodyText"]))
        document.build(story)
        return buffer.getvalue()


__all__ = ["DASHBOARD_WIDGETS", "DEFAULT_DASHBOARD_WIDGETS", "REPORT_TYPES", "EducationPhase2", "MIGRATION_ID"]