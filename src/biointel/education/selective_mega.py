from __future__ import annotations

import csv
import hashlib
import io
import json
import mimetypes
import re
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from .platform import Conflict, Denied, EducationError, Missing
from .selective_mega_schema import migrate_selective_mega

ADMIN = {
    "platform_administrator",
    "institution_administrator",
    "principal",
    "director",
    "principal_director",
    "dean",
    "registrar",
    "department_head",
}
TEACH = {
    "teacher",
    "faculty",
    "subject_teacher",
    "class_teacher",
    "lecturer",
    "assistant_professor",
    "professor",
    "teaching_assistant",
    "laboratory_instructor",
    "academic_mentor",
    "class_coordinator",
}
STUDENT = {"student", "school_student", "college_student", "university_student"}
ENTITY_TYPES = {
    "campus",
    "department",
    "faculty",
    "school",
    "programme",
    "course",
    "class",
    "section",
    "semester",
    "term",
    "academic_year",
    "room",
    "laboratory",
    "library",
    "hostel",
    "designation",
    "document_template",
    "policy",
    "holiday",
    "working_day",
    "timetable_constraint",
    "student",
    "staff",
    "admission_campaign",
    "admission_application",
    "service_request",
    "placement_company",
    "placement_posting",
    "library_resource",
    "fee_structure",
    "scholarship",
}
CLASSWORK_TYPES = {
    "assignment",
    "quiz_assignment",
    "question",
    "material",
    "topic",
    "unit",
    "module",
    "lesson",
    "practical",
    "laboratory",
    "project",
    "group_work",
    "reading",
    "external_link",
    "dataset",
    "pdf",
    "presentation",
    "video",
    "notebook",
    "download",
}
QUESTION_TYPES = {
    "multiple_choice",
    "multiple_select",
    "true_false",
    "fill_blank",
    "matching",
    "assertion_reason",
    "short_answer",
    "long_answer",
    "numerical",
    "case_study",
    "diagram",
    "practical",
    "viva",
    "coding_response",
    "file_upload",
}
PRIVATE_FIELDS = {
    "student_name",
    "student_id",
    "teacher_name",
    "teacher_id",
    "phone",
    "email",
    "guardian_name",
    "date_of_birth",
    "aadhaar",
    "marks",
    "attendance",
}
SENSITIVE_ENTITY_TYPES = {"student", "staff", "admission_application", "service_request"}
ALLOWED_UPLOADS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".docx",
    ".xlsx",
    ".csv",
    ".pptx",
    ".txt",
    ".zip",
    ".mp4",
    ".webm",
    ".ipynb",
}
ROLE_CAPABILITIES = {
    **{role: {"*"} for role in ADMIN},
    "examination_controller": {
        "reports.read",
        "exam.manage",
        "exam.evaluate",
        "exam.publish",
        "exam.proctor",
        "export",
    },
    **{
        role: {
            "reports.read",
            "classroom.manage",
            "classroom.post",
            "classwork.write",
            "exam.author",
        }
        for role in TEACH
    },
    "evaluator": {"reports.read", "exam.evaluate"},
    "invigilator": {"reports.read", "exam.invigilate"},
    "registrar": {
        "entities.write",
        "workflows.review",
        "reports.read",
        "exam.registration",
        "directory.import",
        "export",
    },
    "counsellor": {"reports.read", "services.manage"},
    "career_counsellor": {"reports.read", "services.manage"},
    "librarian": {"reports.read", "library.manage"},
    **{
        role: {
            "reports.read",
            "classroom.read",
            "classwork.submit",
            "exam.registration",
            "services.request",
        }
        for role in STUDENT
    },
    "parent_guardian": {"reports.read"},
    "guest": {"reports.read"},
    "viewer": {"reports.read"},
    "guest_educator": {"reports.read"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def clean_text(value: Any, maximum: int = 4000) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value or "")).strip()[:maximum]


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class EducationMegaService:
    """Tenant-safe application service for the selective Education Mega Update."""

    def __init__(self, platform: Any, source_config: str | Path | None = None):
        self.platform = platform
        migrate_selective_mega(platform.db)
        if source_config:
            self.sync_source_catalog(Path(source_config))

    def _one(self, sql: str, args: Iterable[Any] = ()) -> dict[str, Any] | None:
        return self.platform._one(sql, tuple(args))

    def _all(self, sql: str, args: Iterable[Any] = ()) -> list[dict[str, Any]]:
        return self.platform._all(sql, tuple(args))

    def roles(self, actor: str, institution_id: str) -> set[str]:
        return {str(item["role"]) for item in self.platform.membership(actor, institution_id)}

    def capabilities(self, actor: str, institution_id: str) -> set[str]:
        result: set[str] = set()
        for role in self.roles(actor, institution_id):
            result.update(ROLE_CAPABILITIES.get(role, {"reports.read"}))
        return result

    def require(self, actor: str, institution_id: str, capability: str) -> None:
        capabilities = self.capabilities(actor, institution_id)
        if "*" not in capabilities and capability not in capabilities:
            raise Denied(f"Permission denied: {capability} is required.")

    def _audit(
        self,
        actor: str,
        institution_id: str,
        action: str,
        target_type: str,
        target_id: str,
        detail: Any = None,
    ) -> None:
        self.platform._audit(actor, action, target_type, target_id, institution_id, detail or {})

    def _notify(
        self,
        institution_id: str,
        event_type: str,
        title: str,
        body: str = "",
        *,
        user_id: str = "",
        role: str = "",
        priority: str = "normal",
        target_url: str = "",
    ) -> dict[str, Any]:
        item_id, stamp = new_id("note"), utc_now()
        with self.platform.db.connection() as db:
            db.execute(
                "INSERT INTO education_notifications_r9 VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    item_id,
                    institution_id,
                    user_id,
                    role,
                    event_type,
                    clean_text(title, 240),
                    clean_text(body),
                    priority,
                    clean_text(target_url, 500),
                    None,
                    stamp,
                ),
            )
        return self._one("SELECT * FROM education_notifications_r9 WHERE id=?", (item_id,)) or {}

    def module_snapshot(self, actor: str = "", institution_id: str = "") -> dict[str, Any]:
        """Return database-derived module health without tenant-filtering the national directory."""
        if institution_id:
            self.require(actor, institution_id, "reports.read")
        tenant, args = (
            (" WHERE institution_id=?", (institution_id,)) if institution_id else ("", ())
        )

        def count(table: str, extra: str = "", *, tenant_scoped: bool = True) -> int:
            base = tenant if tenant_scoped else ""
            query_args = args if tenant_scoped else ()
            where = base + ((" AND " if base else " WHERE ") + extra if extra else "")
            item = self._one(f"SELECT COUNT(*) n FROM {table}{where}", query_args)
            return int(item["n"]) if item else 0

        recent = self._one(
            "SELECT MAX(created_at) updated_at FROM education_audit_events" + tenant, args
        )
        return {
            "institutions": 1 if institution_id else count("institutions", "state='active'"),
            "classes": count("education_classes_r9", "state='active'"),
            "pending_classwork": count("education_classwork_r9", "state IN ('draft','published')"),
            "pending_workflows": count(
                "education_workflows", "state IN ('draft','submitted','pending')"
            ),
            "exam_registrations": count(
                "education_exam_registrations_r9", "state IN ('submitted','approved')"
            ),
            "pending_evaluations": count("education_evaluations_r9", "status='draft'"),
            "official_records": count("education_official_records_r9", tenant_scoped=False),
            "unread_notifications": count("education_notifications_r9", "read_at IS NULL"),
            "last_updated": recent["updated_at"] if recent and recent["updated_at"] else None,
        }

    def create_entity(
        self,
        actor: str,
        institution_id: str,
        entity_type: str,
        name: str,
        *,
        code: str = "",
        parent_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.require(actor, institution_id, "entities.write")
        entity_type, name, code = (
            clean_text(entity_type, 64).lower(),
            clean_text(name, 240),
            clean_text(code, 80),
        )
        if entity_type not in ENTITY_TYPES or not name:
            raise EducationError("A supported record type and name are required.")
        if parent_id:
            parent = self._one(
                "SELECT institution_id FROM education_entities WHERE id=?", (parent_id,)
            )
            if not parent or parent["institution_id"] != institution_id:
                raise Denied("Parent record is outside this institution.")
        entity_id, stamp = new_id("entity"), utc_now()
        try:
            with self.platform.db.connection() as db:
                db.execute(
                    "INSERT INTO education_entities VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        entity_id,
                        institution_id,
                        entity_type,
                        name,
                        code,
                        parent_id,
                        json_text(data or {}),
                        "active",
                        actor,
                        stamp,
                        stamp,
                    ),
                )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise Conflict("This code is already in use for that record type.") from exc
            raise
        self._audit(actor, institution_id, "entity_created", entity_type, entity_id, {"code": code})
        return self._one("SELECT * FROM education_entities WHERE id=?", (entity_id,)) or {}

    def list_entities(
        self,
        actor: str,
        institution_id: str,
        entity_type: str = "",
        query: str = "",
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self.require(actor, institution_id, "reports.read")
        capabilities = self.capabilities(actor, institution_id)
        can_read_sensitive = (
            "*" in capabilities
            or "entities.write" in capabilities
            or "services.manage" in capabilities
        )
        if entity_type in SENSITIVE_ENTITY_TYPES and not can_read_sensitive:
            raise Denied("Personal and restricted institution records require elevated permission.")
        clauses, args = ["institution_id=?", "state!='deleted'"], [institution_id]
        if entity_type:
            clauses.append("entity_type=?")
            args.append(entity_type)
        elif not can_read_sensitive:
            placeholders = ",".join("?" for _ in SENSITIVE_ENTITY_TYPES)
            clauses.append(f"entity_type NOT IN ({placeholders})")
            args.extend(sorted(SENSITIVE_ENTITY_TYPES))
        if query:
            clauses.append("(name LIKE ? OR code LIKE ?)")
            args.extend([f"%{clean_text(query, 120)}%"] * 2)
        args.extend([max(1, min(int(limit), 500)), max(0, int(offset))])
        return self._all(
            f"SELECT * FROM education_entities WHERE {' AND '.join(clauses)} ORDER BY entity_type,name LIMIT ? OFFSET ?",
            args,
        )

    def create_workflow(
        self,
        actor: str,
        institution_id: str,
        workflow_type: str,
        payload: dict[str, Any],
        *,
        subject_id: str = "",
        assignee_id: str = "",
        state: str = "submitted",
    ) -> dict[str, Any]:
        self.require(
            actor,
            institution_id,
            "services.request"
            if workflow_type
            in {"service_request", "leave", "grievance", "certificate", "transcript"}
            else "entities.write",
        )
        workflow_id, stamp = new_id("workflow"), utc_now()
        with self.platform.db.connection() as db:
            db.execute(
                "INSERT INTO education_workflows VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    workflow_id,
                    institution_id,
                    clean_text(workflow_type, 80),
                    clean_text(subject_id, 120),
                    actor,
                    clean_text(assignee_id, 120),
                    state,
                    json_text(payload),
                    "",
                    stamp,
                    stamp,
                ),
            )
        self._audit(actor, institution_id, "workflow_created", workflow_type, workflow_id)
        self._notify(
            institution_id,
            "approval_request",
            f"New {workflow_type.replace('_', ' ')}",
            role="institution_administrator",
        )
        return self._one("SELECT * FROM education_workflows WHERE id=?", (workflow_id,)) or {}

    def transition_workflow(
        self, actor: str, institution_id: str, workflow_id: str, state: str, reason: str = ""
    ) -> dict[str, Any]:
        self.require(actor, institution_id, "workflows.review")
        if state not in {"pending", "approved", "rejected", "cancelled", "completed"}:
            raise EducationError("Unsupported workflow state.")
        current = self._one(
            "SELECT * FROM education_workflows WHERE id=? AND institution_id=?",
            (workflow_id, institution_id),
        )
        if not current:
            raise Missing("Workflow not found.")
        with self.platform.db.connection() as db:
            db.execute(
                "UPDATE education_workflows SET state=?,decision_reason=?,assignee_id=?,updated_at=? WHERE id=?",
                (state, clean_text(reason), actor, utc_now(), workflow_id),
            )
        self._audit(
            actor,
            institution_id,
            "workflow_transitioned",
            current["workflow_type"],
            workflow_id,
            {"state": state},
        )
        return self._one("SELECT * FROM education_workflows WHERE id=?", (workflow_id,)) or {}

    def create_class(
        self,
        actor: str,
        institution_id: str,
        name: str,
        class_code: str,
        *,
        subject_id: str | None = None,
        section: str = "",
        academic_session: str = "",
        visibility: str = "institution",
        meeting_url: str = "",
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.require(actor, institution_id, "classroom.manage")
        name, class_code = clean_text(name, 240), clean_text(class_code, 64).upper()
        if (
            visibility not in {"private", "institution", "code"}
            or not name
            or not re.fullmatch(r"[A-Z0-9_-]{4,64}", class_code)
        ):
            raise EducationError("A name, valid class code and supported visibility are required.")
        class_id, stamp = new_id("class"), utc_now()
        try:
            with self.platform.db.connection() as db:
                db.execute(
                    "INSERT INTO education_classes_r9 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        class_id,
                        institution_id,
                        subject_id,
                        actor,
                        name,
                        class_code,
                        clean_text(section, 80),
                        clean_text(academic_session, 80),
                        visibility,
                        clean_text(meeting_url, 500),
                        json_text(settings or {}),
                        "active",
                        stamp,
                        stamp,
                    ),
                )
                db.execute(
                    "INSERT INTO education_class_members_r9 VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        new_id("member"),
                        institution_id,
                        class_id,
                        actor,
                        "teacher",
                        "active",
                        stamp,
                        stamp,
                        stamp,
                    ),
                )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise Conflict("Class code is already in use.") from exc
            raise
        self._audit(
            actor, institution_id, "class_created", "class", class_id, {"class_code": class_code}
        )
        return self._one("SELECT * FROM education_classes_r9 WHERE id=?", (class_id,)) or {}

    def class_access(
        self, actor: str, institution_id: str, class_id: str, *, write: bool = False
    ) -> dict[str, Any]:
        classroom = self._one(
            "SELECT * FROM education_classes_r9 WHERE id=? AND institution_id=?",
            (class_id, institution_id),
        )
        if not classroom:
            raise Missing("Class not found.")
        caps = self.capabilities(actor, institution_id)
        if "*" in caps or (write and "classroom.manage" in caps):
            return classroom
        member = self._one(
            "SELECT * FROM education_class_members_r9 WHERE class_id=? AND user_id=? AND state='active'",
            (class_id, actor),
        )
        if not member or (write and member["role"] not in {"teacher", "co_teacher"}):
            raise Denied("Active class membership with the required role is required.")
        return classroom

    def invite_class_member(
        self, actor: str, institution_id: str, class_id: str, user_id: str, role: str
    ) -> dict[str, Any]:
        self.class_access(actor, institution_id, class_id, write=True)
        if role not in {"teacher", "co_teacher", "student"} or not clean_text(user_id):
            raise EducationError("A valid user and class role are required.")
        member_id, stamp = new_id("member"), utc_now()
        with self.platform.db.connection() as db:
            db.execute(
                """INSERT INTO education_class_members_r9 VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(class_id,user_id,role) DO UPDATE SET state='invited',updated_at=excluded.updated_at""",
                (
                    member_id,
                    institution_id,
                    class_id,
                    clean_text(user_id, 120),
                    role,
                    "invited",
                    None,
                    stamp,
                    stamp,
                ),
            )
        self._notify(
            institution_id,
            "class_invitation",
            "Class invitation",
            user_id=user_id,
            target_url="pages/340_BioIntel_Classroom.py",
        )
        self._audit(
            actor,
            institution_id,
            "class_member_invited",
            "class",
            class_id,
            {"user_id": user_id, "role": role},
        )
        return (
            self._one(
                "SELECT * FROM education_class_members_r9 WHERE class_id=? AND user_id=? AND role=?",
                (class_id, user_id, role),
            )
            or {}
        )

    def add_stream_post(
        self,
        actor: str,
        institution_id: str,
        class_id: str,
        body: str,
        *,
        title: str = "",
        post_type: str = "announcement",
        scheduled_at: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        audience: list[str] | None = None,
        pinned: bool = False,
    ) -> dict[str, Any]:
        self.class_access(actor, institution_id, class_id, write=True)
        body = clean_text(body, 20000)
        if not body:
            raise EducationError("Post content is required.")
        post_id, stamp = new_id("post"), utc_now()
        with self.platform.db.connection() as db:
            db.execute(
                "INSERT INTO education_stream_posts_r9 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    post_id,
                    institution_id,
                    class_id,
                    actor,
                    post_type,
                    clean_text(title, 240),
                    body,
                    json_text(attachments or []),
                    json_text(audience or []),
                    scheduled_at,
                    None if scheduled_at else stamp,
                    int(pinned),
                    0,
                    "published",
                    "active",
                    stamp,
                    stamp,
                ),
            )
        self._audit(actor, institution_id, "stream_post_created", "stream_post", post_id)
        self._notify(
            institution_id,
            "announcement",
            title or "New class announcement",
            target_url="pages/340_BioIntel_Classroom.py",
        )
        return self._one("SELECT * FROM education_stream_posts_r9 WHERE id=?", (post_id,)) or {}

    def create_classwork(
        self,
        actor: str,
        institution_id: str,
        class_id: str,
        item_type: str,
        title: str,
        *,
        instructions: str = "",
        topic: str = "",
        due_at: str | None = None,
        publish_at: str | None = None,
        max_marks: float = 0,
        settings: dict[str, Any] | None = None,
        state: str = "draft",
    ) -> dict[str, Any]:
        self.class_access(actor, institution_id, class_id, write=True)
        if (
            item_type not in CLASSWORK_TYPES
            or state not in {"draft", "scheduled", "published", "closed", "archived"}
            or float(max_marks) < 0
        ):
            raise EducationError("Invalid classwork type, state or marks.")
        item_id, stamp = new_id("work"), utc_now()
        with self.platform.db.connection() as db:
            db.execute(
                "INSERT INTO education_classwork_r9 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    item_id,
                    institution_id,
                    class_id,
                    actor,
                    item_type,
                    clean_text(title, 240),
                    clean_text(instructions, 20000),
                    clean_text(topic, 160),
                    due_at,
                    publish_at,
                    float(max_marks),
                    json_text(settings or {}),
                    state,
                    stamp,
                    stamp,
                ),
            )
        self._audit(
            actor, institution_id, "classwork_created", item_type, item_id, {"state": state}
        )
        if state == "published":
            self._notify(
                institution_id,
                "new_assignment",
                f"New classwork: {title}",
                target_url="pages/340_BioIntel_Classroom.py",
            )
        return self._one("SELECT * FROM education_classwork_r9 WHERE id=?", (item_id,)) or {}

    def register_exam(
        self,
        actor: str,
        institution_id: str,
        examination_id: str,
        subjects: list[str],
        eligibility: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.require(actor, institution_id, "exam.registration")
        registration_id, stamp = new_id("examreg"), utc_now()
        number = f"EX-{hashlib.sha256(f'{institution_id}:{examination_id}:{actor}'.encode()).hexdigest()[:12].upper()}"
        with self.platform.db.connection() as db:
            db.execute(
                """INSERT INTO education_exam_registrations_r9 VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(examination_id,student_id) DO UPDATE SET subjects_json=excluded.subjects_json,
                eligibility_json=excluded.eligibility_json,state='submitted',decision_reason='',updated_at=excluded.updated_at""",
                (
                    registration_id,
                    institution_id,
                    examination_id,
                    actor,
                    json_text(subjects),
                    json_text(eligibility or {}),
                    number,
                    "submitted",
                    "",
                    stamp,
                    stamp,
                ),
            )
        self._notify(
            institution_id,
            "examination_registration",
            "Examination registration submitted",
            user_id=actor,
        )
        self._audit(
            actor, institution_id, "exam_registration_submitted", "examination", examination_id
        )
        return (
            self._one(
                "SELECT * FROM education_exam_registrations_r9 WHERE examination_id=? AND student_id=?",
                (examination_id, actor),
            )
            or {}
        )

    def decide_exam_registration(
        self,
        actor: str,
        institution_id: str,
        registration_id: str,
        approved: bool,
        reason: str = "",
    ) -> dict[str, Any]:
        self.require(actor, institution_id, "exam.manage")
        registration = self._one(
            "SELECT * FROM education_exam_registrations_r9 WHERE id=? AND institution_id=?",
            (registration_id, institution_id),
        )
        if not registration:
            raise Missing("Examination registration not found.")
        state = "approved" if approved else "rejected"
        if not approved and not clean_text(reason):
            raise EducationError("A rejection reason is required.")
        with self.platform.db.connection() as db:
            db.execute(
                "UPDATE education_exam_registrations_r9 SET state=?,decision_reason=?,updated_at=? WHERE id=?",
                (state, clean_text(reason), utc_now(), registration_id),
            )
        self._notify(
            institution_id,
            "examination_registration",
            f"Examination registration {state}",
            reason,
            user_id=registration["student_id"],
        )
        self._audit(
            actor,
            institution_id,
            "exam_registration_decided",
            "exam_registration",
            registration_id,
            {"state": state},
        )
        return (
            self._one(
                "SELECT * FROM education_exam_registrations_r9 WHERE id=?", (registration_id,)
            )
            or {}
        )

    def add_question(
        self,
        actor: str,
        institution_id: str,
        subject_id: str,
        question_type: str,
        prompt: str,
        *,
        answer: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.require(actor, institution_id, "exam.author")
        prompt = clean_text(prompt, 30000)
        if question_type not in QUESTION_TYPES or not prompt:
            raise EducationError("A supported question type and question text are required.")
        fingerprint = hashlib.sha256(
            re.sub(r"\s+", " ", prompt.casefold()).encode("utf-8")
        ).hexdigest()
        duplicate = self._one(
            "SELECT id FROM education_question_bank_r9 WHERE institution_id=? AND fingerprint=? AND state!='archived'",
            (institution_id, fingerprint),
        )
        if duplicate:
            raise Conflict(f"Possible duplicate question: {duplicate['id']}.")
        question_id, stamp = new_id("question"), utc_now()
        with self.platform.db.connection() as db:
            db.execute(
                "INSERT INTO education_question_bank_r9 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    question_id,
                    institution_id,
                    subject_id,
                    actor,
                    question_type,
                    prompt,
                    json_text(answer or {}),
                    json_text(metadata or {}),
                    fingerprint,
                    1,
                    "",
                    "draft",
                    stamp,
                    stamp,
                ),
            )
        self._audit(actor, institution_id, "question_created", "question", question_id)
        return (
            self._one("SELECT * FROM education_question_bank_r9 WHERE id=?", (question_id,)) or {}
        )

    def schedule_exam(
        self,
        actor: str,
        institution_id: str,
        examination_id: str,
        room: str,
        capacity: int,
        starts_at: str,
        ends_at: str,
        *,
        subject_id: str = "",
        invigilators: list[str] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.require(actor, institution_id, "exam.manage")
        start = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
        if end <= start or int(capacity) < 1:
            raise EducationError("A positive capacity and valid examination window are required.")
        invigilators = invigilators or []
        clashes = self._all(
            """SELECT id,room,invigilators_json FROM education_exam_schedules_r9
            WHERE institution_id=? AND state!='cancelled' AND starts_at<? AND ends_at>?""",
            (institution_id, ends_at, starts_at),
        )
        for item in clashes:
            if item["room"].casefold() == room.casefold() or set(invigilators) & set(
                json.loads(item["invigilators_json"])
            ):
                raise Conflict(f"Room or invigilator conflict with schedule {item['id']}.")
        schedule_id, stamp = new_id("schedule"), utc_now()
        with self.platform.db.connection() as db:
            db.execute(
                "INSERT INTO education_exam_schedules_r9 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    schedule_id,
                    institution_id,
                    examination_id,
                    subject_id,
                    clean_text(room, 120),
                    int(capacity),
                    starts_at,
                    ends_at,
                    json_text(invigilators),
                    json_text(settings or {}),
                    "draft",
                    stamp,
                    stamp,
                ),
            )
        self._audit(
            actor,
            institution_id,
            "exam_scheduled",
            "examination",
            examination_id,
            {"schedule_id": schedule_id},
        )
        return (
            self._one("SELECT * FROM education_exam_schedules_r9 WHERE id=?", (schedule_id,)) or {}
        )

    def allocate_seat(
        self,
        actor: str,
        institution_id: str,
        schedule_id: str,
        student_id: str,
        seat_label: str,
        accessibility: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.require(actor, institution_id, "exam.manage")
        schedule = self._one(
            "SELECT * FROM education_exam_schedules_r9 WHERE id=? AND institution_id=?",
            (schedule_id, institution_id),
        )
        if not schedule:
            raise Missing("Examination schedule not found.")
        used = self._one(
            "SELECT COUNT(*) n FROM education_exam_seats_r9 WHERE schedule_id=?", (schedule_id,)
        )
        if used and int(used["n"]) >= int(schedule["capacity"]):
            raise Conflict("Room capacity has been reached.")
        seat_id, stamp = new_id("seat"), utc_now()
        try:
            with self.platform.db.connection() as db:
                db.execute(
                    "INSERT INTO education_exam_seats_r9 VALUES(?,?,?,?,?,?,?,?)",
                    (
                        seat_id,
                        institution_id,
                        schedule_id,
                        student_id,
                        clean_text(seat_label, 40),
                        json_text(accessibility or {}),
                        stamp,
                        stamp,
                    ),
                )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise Conflict("Student or seat is already allocated.") from exc
            raise
        return self._one("SELECT * FROM education_exam_seats_r9 WHERE id=?", (seat_id,)) or {}

    def issue_admit_card(
        self, actor: str, institution_id: str, registration_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.require(actor, institution_id, "exam.manage")
        registration = self._one(
            "SELECT * FROM education_exam_registrations_r9 WHERE id=? AND institution_id=? AND state='approved'",
            (registration_id, institution_id),
        )
        if not registration:
            raise Conflict(
                "Only an approved examination registration is eligible for an admit card."
            )
        card_id, stamp, reference = (
            new_id("admit"),
            utc_now(),
            f"BIO-{uuid.uuid4().hex[:16].upper()}",
        )
        with self.platform.db.connection() as db:
            db.execute(
                "INSERT INTO education_admit_cards_r9 VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    card_id,
                    institution_id,
                    registration_id,
                    reference,
                    json_text(payload),
                    "issued",
                    actor,
                    stamp,
                    None,
                    stamp,
                ),
            )
        self._notify(
            institution_id, "admit_card", "Admit card issued", user_id=registration["student_id"]
        )
        self._audit(actor, institution_id, "admit_card_issued", "admit_card", card_id)
        return self._one("SELECT * FROM education_admit_cards_r9 WHERE id=?", (card_id,)) or {}

    def save_evaluation(
        self,
        actor: str,
        institution_id: str,
        examination_id: str,
        student_id: str,
        marks: dict[str, float],
        *,
        flags: dict[str, Any] | None = None,
        submit: bool = False,
    ) -> dict[str, Any]:
        self.require(actor, institution_id, "exam.evaluate")
        clean_marks = {clean_text(key, 120): float(value) for key, value in marks.items()}
        if any(value < 0 for value in clean_marks.values()):
            raise EducationError("Question marks cannot be negative.")
        total, stamp, evaluation_id = sum(clean_marks.values()), utc_now(), new_id("evaluation")
        status = "submitted" if submit else "draft"
        with self.platform.db.connection() as db:
            db.execute(
                """INSERT INTO education_evaluations_r9 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(examination_id,student_id,evaluator_id) DO UPDATE SET marks_json=excluded.marks_json,
                total_marks=excluded.total_marks,status=excluded.status,flags_json=excluded.flags_json,
                locked_at=excluded.locked_at,updated_at=excluded.updated_at""",
                (
                    evaluation_id,
                    institution_id,
                    examination_id,
                    student_id,
                    actor,
                    json_text(clean_marks),
                    total,
                    status,
                    json_text(flags or {}),
                    stamp if submit else None,
                    stamp,
                    stamp,
                ),
            )
        self._audit(
            actor,
            institution_id,
            "evaluation_saved",
            "examination",
            examination_id,
            {"student_id": student_id, "status": status},
        )
        return (
            self._one(
                "SELECT * FROM education_evaluations_r9 WHERE examination_id=? AND student_id=? AND evaluator_id=?",
                (examination_id, student_id, actor),
            )
            or {}
        )

    @staticmethod
    def calculate_result(total: float, rules: dict[str, Any]) -> dict[str, Any]:
        maximum = float(rules.get("maximum_marks", 100))
        if maximum <= 0:
            raise EducationError("Maximum marks must be positive.")
        percentage = round(float(total) * 100 / maximum, 2)
        boundaries = sorted(
            [
                (float(item["minimum"]), str(item["grade"]))
                for item in rules.get("grade_boundaries", [])
            ],
            reverse=True,
        )
        grade = next((label for minimum, label in boundaries if percentage >= minimum), "")
        return {
            "marks": float(total),
            "maximum_marks": maximum,
            "percentage": percentage,
            "grade": grade,
            "status": "pass" if percentage >= float(rules.get("pass_percentage", 40)) else "fail",
            "rules": rules,
        }

    def process_result(
        self,
        actor: str,
        institution_id: str,
        examination_id: str,
        student_id: str,
        total: float,
        rules: dict[str, Any],
        *,
        reason: str = "initial processing",
        publish: bool = False,
    ) -> dict[str, Any]:
        self.require(actor, institution_id, "exam.publish")
        result = self.calculate_result(total, rules)
        previous = self._one(
            "SELECT MAX(version) version FROM education_result_versions_r9 WHERE examination_id=? AND student_id=?",
            (examination_id, student_id),
        )
        version = int(previous["version"] or 0) + 1 if previous else 1
        result_id, stamp = new_id("result"), utc_now()
        with self.platform.db.connection() as db:
            db.execute(
                "INSERT INTO education_result_versions_r9 VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    result_id,
                    institution_id,
                    examination_id,
                    student_id,
                    version,
                    json_text(result),
                    clean_text(reason),
                    actor,
                    int(publish),
                    0,
                    stamp,
                ),
            )
        if publish:
            self._notify(
                institution_id,
                "result_publication",
                "Examination result published",
                user_id=student_id,
            )
        self._audit(
            actor,
            institution_id,
            "result_version_created",
            "result",
            result_id,
            {"version": version, "published": publish},
        )
        return (
            self._one("SELECT * FROM education_result_versions_r9 WHERE id=?", (result_id,)) or {}
        )

    def request_revaluation(
        self, actor: str, institution_id: str, examination_id: str, subject_id: str, reason: str
    ) -> dict[str, Any]:
        self.require(actor, institution_id, "exam.registration")
        request_id, stamp = new_id("reval"), utc_now()
        with self.platform.db.connection() as db:
            db.execute(
                "INSERT INTO education_revaluation_r9 VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    request_id,
                    institution_id,
                    examination_id,
                    actor,
                    subject_id,
                    clean_text(reason),
                    "",
                    "{}",
                    "requested",
                    stamp,
                    stamp,
                ),
            )
        self._notify(institution_id, "revaluation_status", "Re-evaluation requested", user_id=actor)
        self._audit(actor, institution_id, "revaluation_requested", "examination", examination_id)
        return self._one("SELECT * FROM education_revaluation_r9 WHERE id=?", (request_id,)) or {}

    def set_proctor_policy(
        self,
        actor: str,
        institution_id: str,
        examination_id: str,
        *,
        enabled: bool = False,
        provider: str = "",
        camera: bool = False,
        microphone: bool = False,
        retention_days: int = 0,
        consent_text: str = "",
    ) -> dict[str, Any]:
        self.require(actor, institution_id, "exam.proctor")
        if enabled and not clean_text(consent_text):
            raise EducationError(
                "Transparent consent text is required before proctoring can be enabled."
            )
        if not enabled and (camera or microphone):
            raise EducationError(
                "Camera and microphone adapters require an enabled consent-based policy."
            )
        if not 0 <= int(retention_days) <= 3650:
            raise EducationError("Retention must be between 0 and 3650 days.")
        policy_id, stamp = new_id("proctor"), utc_now()
        with self.platform.db.connection() as db:
            db.execute(
                """INSERT INTO education_proctor_policies_r9 VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,examination_id) DO UPDATE SET enabled=excluded.enabled,
                provider=excluded.provider,camera=excluded.camera,microphone=excluded.microphone,
                retention_days=excluded.retention_days,consent_text=excluded.consent_text,
                updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
                (
                    policy_id,
                    institution_id,
                    examination_id,
                    int(enabled),
                    clean_text(provider, 120),
                    int(camera),
                    int(microphone),
                    int(retention_days),
                    clean_text(consent_text, 8000),
                    actor,
                    stamp,
                ),
            )
        self._audit(
            actor,
            institution_id,
            "proctor_policy_updated",
            "examination",
            examination_id,
            {"enabled": enabled},
        )
        return (
            self._one(
                "SELECT * FROM education_proctor_policies_r9 WHERE institution_id=? AND examination_id=?",
                (institution_id, examination_id),
            )
            or {}
        )

    def sync_source_catalog(self, config_path: Path) -> int:
        if not config_path.is_file():
            return 0
        payload, stamp, count = json.loads(config_path.read_text(encoding="utf-8")), utc_now(), 0
        with self.platform.db.connection() as db:
            for source in payload.get("sources", []):
                source_id = clean_text(source.get("key") or source.get("id"), 80)
                if not source_id:
                    continue
                db.execute(
                    """INSERT INTO education_official_sources_r9
                    (id,name,authority,url,enabled,adapter,terms_note,limitations,last_success_at,last_checksum,last_error,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(name) DO UPDATE SET authority=excluded.authority,url=excluded.url,
                    adapter=excluded.adapter,terms_note=excluded.terms_note,limitations=excluded.limitations,updated_at=excluded.updated_at""",
                    (
                        source_id,
                        clean_text(source.get("name"), 200),
                        clean_text(source.get("authority"), 200),
                        clean_text(source.get("official_url") or source.get("url"), 800),
                        int(bool(source.get("enabled_by_default", False))),
                        clean_text(source.get("adapter", "authorised_file_import"), 80),
                        clean_text(source.get("terms_note") or source.get("scope"), 2000),
                        clean_text(source.get("limitations"), 4000),
                        None,
                        "",
                        "",
                        stamp,
                    ),
                )
                count += 1
        return count

    def import_official_records(
        self,
        actor: str,
        institution_id: str,
        source_id: str,
        records: list[dict[str, Any]],
        *,
        dataset_year: str = "",
        transformation_version: str = "r9-v1",
    ) -> dict[str, Any]:
        self.require(actor, institution_id, "directory.import")
        source = self._one("SELECT * FROM education_official_sources_r9 WHERE id=?", (source_id,))
        if not source:
            raise Missing("Official source is not configured.")
        checksum = hashlib.sha256(json_text(records).encode("utf-8")).hexdigest()
        prior = self._one(
            "SELECT * FROM education_ingestion_runs_r9 WHERE source_id=? AND checksum=? AND state='completed'",
            (source_id, checksum),
        )
        if prior:
            return {**prior, "idempotent": True}
        run_id, stamp = new_id("ingest"), utc_now()
        imported = rejected = conflicts = 0
        with self.platform.db.connection() as db:
            db.execute(
                "INSERT INTO education_ingestion_runs_r9 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    source_id,
                    "running",
                    len(records),
                    0,
                    0,
                    0,
                    checksum,
                    clean_text(dataset_year, 16),
                    "",
                    0,
                    stamp,
                    None,
                ),
            )
            for raw in records:
                if {str(key).strip().casefold() for key in raw} & PRIVATE_FIELDS:
                    rejected += 1
                    continue
                official_id = clean_text(
                    raw.get("official_id") or raw.get("udise_code") or raw.get("code"), 160
                )
                name = clean_text(raw.get("name") or raw.get("institution_name"), 300)
                if not official_id or not name:
                    rejected += 1
                    continue
                state_ut = clean_text(raw.get("state_ut") or raw.get("state"), 100)
                district = clean_text(raw.get("district"), 120)
                existing = db.execute(
                    "SELECT id,name FROM education_official_records_r9 WHERE source_id=? AND official_id=?",
                    (source_id, official_id),
                ).fetchone()
                conflict_status = "none"
                if not existing:
                    candidates = db.execute(
                        "SELECT id,name FROM education_official_records_r9 WHERE source_id=? AND state_ut=? AND district=? LIMIT 250",
                        (source_id, state_ut, district),
                    ).fetchall()
                    if any(
                        SequenceMatcher(
                            None, name.casefold(), str(candidate["name"]).casefold()
                        ).ratio()
                        >= 0.94
                        for candidate in candidates
                    ):
                        conflict_status, conflicts = "possible_duplicate", conflicts + 1
                record_id = str(existing["id"]) if existing else new_id("official")
                retrieved = clean_text(raw.get("retrieved_at") or stamp, 80)
                raw_checksum = hashlib.sha256(json_text(raw).encode("utf-8")).hexdigest()
                db.execute(
                    """INSERT INTO education_official_records_r9
                    (id,source_id,official_id,name,alternate_names_json,institution_type,management_type,state_ut,district,
                    address,pin_code,board,affiliation,recognition_status,programmes_json,source_url,dataset_year,retrieved_at,
                    checksum,transformation_version,verification_status,freshness_status,conflict_status,raw_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(source_id,official_id) DO UPDATE SET name=excluded.name,
                    alternate_names_json=excluded.alternate_names_json,institution_type=excluded.institution_type,
                    management_type=excluded.management_type,state_ut=excluded.state_ut,district=excluded.district,
                    address=excluded.address,pin_code=excluded.pin_code,board=excluded.board,affiliation=excluded.affiliation,
                    recognition_status=excluded.recognition_status,programmes_json=excluded.programmes_json,
                    source_url=excluded.source_url,dataset_year=excluded.dataset_year,retrieved_at=excluded.retrieved_at,
                    checksum=excluded.checksum,transformation_version=excluded.transformation_version,
                    verification_status=excluded.verification_status,freshness_status=excluded.freshness_status,
                    conflict_status=excluded.conflict_status,raw_json=excluded.raw_json,updated_at=excluded.updated_at""",
                    (
                        record_id,
                        source_id,
                        official_id,
                        name,
                        json_text(raw.get("alternate_names", [])),
                        clean_text(raw.get("institution_type"), 100),
                        clean_text(raw.get("management_type"), 100),
                        state_ut,
                        district,
                        clean_text(raw.get("address"), 800),
                        clean_text(raw.get("pin_code"), 20),
                        clean_text(raw.get("board"), 120),
                        clean_text(raw.get("affiliation"), 200),
                        clean_text(raw.get("recognition_status"), 160),
                        json_text(raw.get("programmes", [])),
                        clean_text(raw.get("source_url") or source["url"], 800),
                        clean_text(raw.get("dataset_year") or dataset_year, 16),
                        retrieved,
                        raw_checksum,
                        transformation_version,
                        "source_asserted_pending_review",
                        "current",
                        conflict_status,
                        json_text(raw),
                        stamp,
                        stamp,
                    ),
                )
                if conflict_status != "none":
                    db.execute(
                        "INSERT INTO education_import_conflicts_r9 VALUES(?,?,?,?,?,?,?,?,?)",
                        (
                            new_id("conflict"),
                            run_id,
                            record_id,
                            "",
                            "fuzzy_name_match",
                            json_text({"name": name}),
                            "pending",
                            "",
                            stamp,
                            stamp,
                        ),
                    )
                imported += 1
            finished = utc_now()
            db.execute(
                """UPDATE education_ingestion_runs_r9 SET state='completed',records_imported=?,
                records_rejected=?,duplicate_merges=?,finished_at=? WHERE id=?""",
                (imported, rejected, conflicts, finished, run_id),
            )
            db.execute(
                "UPDATE education_official_sources_r9 SET last_success_at=?,last_checksum=?,last_error='',updated_at=? WHERE id=?",
                (finished, checksum, finished, source_id),
            )
        self._audit(
            actor,
            institution_id,
            "official_data_imported",
            "official_source",
            source_id,
            {"run_id": run_id, "imported": imported},
        )
        self._notify(
            institution_id,
            "data_import_completion",
            f"{source['name']} import completed",
            f"{imported} imported; {rejected} rejected.",
        )
        return self._one("SELECT * FROM education_ingestion_runs_r9 WHERE id=?", (run_id,)) or {}

    def import_csv(
        self,
        actor: str,
        institution_id: str,
        source_id: str,
        content: bytes,
        *,
        dataset_year: str = "",
    ) -> dict[str, Any]:
        if len(content) > 50 * 1024 * 1024:
            raise EducationError("Import exceeds the 50 MiB limit.")
        if content.startswith(b"MZ") or b"\x00" in content[:1024]:
            raise EducationError("The upload is not a valid text CSV.")
        try:
            records = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
        except (UnicodeDecodeError, csv.Error) as exc:
            raise EducationError("CSV must be UTF-8 with a header row.") from exc
        return self.import_official_records(
            actor, institution_id, source_id, records, dataset_year=dataset_year
        )

    def directory_coverage(self) -> dict[str, Any]:
        sources = self._all("""SELECT s.id,s.name,s.authority,s.url,s.enabled,s.adapter,
            s.terms_note AS scope,s.limitations,s.last_success_at,
            COUNT(r.id) imported,SUM(CASE WHEN r.verification_status='verified' THEN 1 ELSE 0 END) verified,
            SUM(CASE WHEN r.verification_status='source_asserted_pending_review' THEN 1 ELSE 0 END) pending,
            SUM(CASE WHEN r.conflict_status!='none' THEN 1 ELSE 0 END) conflicts
            FROM education_official_sources_r9 s LEFT JOIN education_official_records_r9 r ON r.source_id=s.id
            GROUP BY s.id ORDER BY s.name""")
        totals = {
            key: sum(int(row[key] or 0) for row in sources)
            for key in ("imported", "verified", "pending", "conflicts")
        }
        return {
            "sources": sources,
            "totals": totals,
            "coverage_claim": "partial_authorised_imports_only",
        }

    def list_directory_records(
        self,
        *,
        source_id: str = "",
        query: str = "",
        limit: int = 250,
    ) -> list[dict[str, Any]]:
        """Return imported official institutions with their source provenance."""
        source_id, query = clean_text(source_id, 80), clean_text(query, 160)
        conditions: list[str] = []
        args: list[Any] = []
        if source_id:
            conditions.append("r.source_id=?")
            args.append(source_id)
        if query:
            like = f"%{query}%"
            conditions.append(
                "(r.name LIKE ? OR r.official_id LIKE ? OR r.institution_type LIKE ? "
                "OR r.state_ut LIKE ? OR r.district LIKE ? OR r.board LIKE ?)"
            )
            args.extend([like] * 6)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        args.append(max(1, min(int(limit), 500)))
        return self._all(
            """SELECT r.id,r.name,r.official_id,r.institution_type,r.management_type,
            r.state_ut,r.district,r.board,r.affiliation,r.recognition_status,
            r.dataset_year,r.retrieved_at,r.verification_status,r.freshness_status,
            r.conflict_status,r.source_url,s.id AS source_id,s.name AS source_name
            FROM education_official_records_r9 r
            JOIN education_official_sources_r9 s ON s.id=r.source_id"""
            + where
            + " ORDER BY r.name,r.official_id LIMIT ?",
            tuple(args),
        )

    def search(
        self, actor: str, institution_id: str, query: str, *, category: str = "", limit: int = 50
    ) -> list[dict[str, Any]]:
        self.require(actor, institution_id, "reports.read")
        query = clean_text(query, 160)
        if not query:
            return []
        like, cap, results = f"%{query}%", max(1, min(int(limit), 100)), []
        if category in {"", "institution"}:
            results += [
                {
                    "category": "institution",
                    "id": row["id"],
                    "title": row["name"],
                    "subtitle": row["official_id"],
                    "state": row["verification_status"],
                }
                for row in self._all(
                    "SELECT id,name,official_id,verification_status FROM education_official_records_r9 WHERE name LIKE ? OR official_id LIKE ? ORDER BY name LIMIT ?",
                    (like, like, cap),
                )
            ]
        capabilities = self.capabilities(actor, institution_id)
        if category in {"", "entity"} and (
            "*" in capabilities
            or "entities.write" in capabilities
            or "services.manage" in capabilities
        ):
            results += [
                {
                    "category": row["entity_type"],
                    "id": row["id"],
                    "title": row["name"],
                    "subtitle": row["code"],
                    "state": row["state"],
                }
                for row in self._all(
                    "SELECT * FROM education_entities WHERE institution_id=? AND state!='deleted' AND (name LIKE ? OR code LIKE ?) ORDER BY name LIMIT ?",
                    (institution_id, like, like, cap),
                )
            ]
        if category in {"", "classroom"}:
            results += [
                {
                    "category": "class",
                    "id": row["id"],
                    "title": row["name"],
                    "subtitle": row["class_code"],
                    "state": row["state"],
                }
                for row in self._all(
                    "SELECT * FROM education_classes_r9 WHERE institution_id=? AND state!='archived' AND (name LIKE ? OR class_code LIKE ?) ORDER BY name LIMIT ?",
                    (institution_id, like, like, cap),
                )
            ]
        return results[:cap]

    def notifications(
        self, actor: str, institution_id: str, *, unread_only: bool = False
    ) -> list[dict[str, Any]]:
        roles = self.roles(actor, institution_id)
        if not roles:
            raise Denied("Institution membership is required.")
        placeholders = ",".join("?" for _ in roles) or "''"
        clauses, args = (
            ["institution_id=?", f"(user_id='' OR user_id=? OR role IN ({placeholders}))"],
            [institution_id, actor, *sorted(roles)],
        )
        if unread_only:
            clauses.append("read_at IS NULL")
        return self._all(
            f"SELECT * FROM education_notifications_r9 WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT 100",
            args,
        )

    def mark_notification_read(
        self, actor: str, institution_id: str, notification_id: str
    ) -> dict[str, Any]:
        if notification_id not in {
            item["id"] for item in self.notifications(actor, institution_id)
        }:
            raise Denied("Notification access denied.")
        with self.platform.db.connection() as db:
            db.execute(
                "UPDATE education_notifications_r9 SET read_at=? WHERE id=?",
                (utc_now(), notification_id),
            )
        return (
            self._one("SELECT * FROM education_notifications_r9 WHERE id=?", (notification_id,))
            or {}
        )

    @staticmethod
    def validate_upload(
        filename: str, content: bytes, *, maximum_bytes: int = 50 * 1024 * 1024
    ) -> dict[str, Any]:
        safe_name, suffix = Path(filename).name, Path(filename).suffix.casefold()
        if safe_name != filename or not safe_name:
            raise EducationError("Unsafe upload filename.")
        if suffix not in ALLOWED_UPLOADS or len(content) > maximum_bytes:
            raise EducationError("File type is not allowed or the upload exceeds the size limit.")
        signatures = {
            ".pdf": b"%PDF-",
            ".png": b"\x89PNG",
            ".jpg": b"\xff\xd8\xff",
            ".jpeg": b"\xff\xd8\xff",
        }
        if suffix in signatures and not content.startswith(signatures[suffix]):
            raise EducationError("File content does not match its extension.")
        return {
            "filename": safe_name,
            "mime_type": mimetypes.guess_type(safe_name)[0] or "application/octet-stream",
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    @staticmethod
    def export_csv(rows: list[dict[str, Any]]) -> bytes:
        if not rows:
            return b""
        output, fields = io.StringIO(newline=""), list(rows[0])
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json_text(value) if isinstance(value, (dict, list)) else value
                    for key, value in row.items()
                }
            )
        return output.getvalue().encode("utf-8-sig")
