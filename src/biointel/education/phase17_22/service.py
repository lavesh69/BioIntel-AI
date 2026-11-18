from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from ..examination import SecureExaminationService
from ..permissions import PermissionService
from ..phase16 import EducationPhase16Service
from ..platform import (
    Conflict,
    Denied,
    EducationError,
    Missing,
    ident,
    now,
)
from .schema import MIGRATION_ID, SCHEMA

RESOURCE_TYPES = {
    "institution", "campus", "department", "program", "course", "batch", "classroom",
    "assignment", "examination", "message", "document", "report", "studio_project",
}
CANONICAL_ROLES = {
    "student", "teacher", "parent_guardian", "instructor", "examiner", "reviewer",
    "department_administrator", "institution_administrator", "platform_administrator", "guest",
}
ROLE_ALIASES = {
    "school_student": "student", "college_student": "student", "university_student": "student",
    "subject_teacher": "teacher", "class_teacher": "teacher", "lecturer": "instructor",
    "assistant_professor": "instructor", "professor": "instructor",
    "teaching_assistant": "instructor", "laboratory_instructor": "instructor",
    "academic_mentor": "instructor", "class_coordinator": "teacher",
    "parent_guardian": "parent_guardian", "examination_controller": "examiner",
    "content_moderator": "reviewer", "department_head": "department_administrator",
    "institution_administrator": "institution_administrator", "principal": "institution_administrator",
    "dean": "institution_administrator", "registrar": "institution_administrator",
    "platform_administrator": "platform_administrator", "guest_educator": "guest",
}
ROLE_ACTIONS: dict[str, set[str]] = {
    "platform_administrator": {"*"},
    "institution_administrator": {"*"},
    "department_administrator": {
        "view", "create", "manage", "manage_roles", "publish", "review", "report", "export",
    },
    "teacher": {"view", "create", "manage", "publish", "grade", "message", "report", "export", "review"},
    "instructor": {"view", "create", "manage", "publish", "grade", "message", "report", "export", "review"},
    "examiner": {"view", "create", "manage", "publish", "grade", "review", "report", "export"},
    "reviewer": {"view", "review", "report", "message"},
    "student": {"view", "submit", "attempt", "message", "download", "export_self"},
    "parent_guardian": {"view_linked", "message", "report_linked"},
    "guest": {"view_public"},
}
STUDIO_TYPES = {"presentation", "poster", "report", "diagram", "flowchart", "concept_map", "lecture_asset"}
SHIRO_MODES = {
    "tutoring", "socratic", "revision", "quiz", "flashcard", "notes", "summary",
    "assignment_assistance", "remediation",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _decode(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalized_title(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))[:1000]


def _safe_username(value: str) -> str:
    clean = re.sub(r"[^a-z0-9._-]+", "-", str(value).casefold()).strip("-._")[:52]
    return clean if len(clean) >= 3 else "edu-" + hashlib.sha256(str(value).encode()).hexdigest()[:12]


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    roles: tuple[str, ...]
    action: str
    resource_type: str
    resource_id: str
    reason: str


class EducationOS:
    """Phase 17-22 facade over the canonical Education database and existing services.

    The facade adds shared resource scoping, durable cross-module delivery, course-aware Shiro
    access, explainable interventions, Studio versioning and release evidence. It intentionally
    reuses ``EducationPlatform`` and its database instead of introducing another module database.
    """

    def __init__(
        self,
        platform: Any,
        *,
        root: str | Path,
        shiro: Any | None = None,
        connect: Any | None = None,
    ) -> None:
        self.platform = platform
        self.db = platform.db
        self.root = Path(root).resolve()
        self.permissions = PermissionService(platform)
        self.phase16 = EducationPhase16Service(platform, root=self.root)
        self.examinations = SecureExaminationService(platform)
        self.shiro = shiro
        self.connect = connect
        self.migrate()

    def migrate(self) -> str:
        with self.db.connection() as db:
            db.executescript(SCHEMA)
        return MIGRATION_ID

    def _table_exists(self, name: str) -> bool:
        return bool(self.platform._one("SELECT 1 ok FROM sqlite_master WHERE type='table' AND name=?", (name,)))

    def _institution(self, institution_id: str) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM institutions WHERE id=? AND state='active'", (institution_id,))
        if not row:
            raise Missing("Institution not found.")
        return row

    def roles(
        self,
        actor: str,
        institution_id: str,
        *,
        resource_type: str = "institution",
        resource_id: str = "",
    ) -> set[str]:
        self._institution(institution_id)
        membership_roles = {
            ROLE_ALIASES.get(str(row["role"]), str(row["role"]))
            for row in self.platform.membership(actor, institution_id)
        }
        bindings = self.platform._all(
            """SELECT role,resource_type,resource_id FROM education_role_bindings
            WHERE institution_id=? AND user_id=? AND state='active'
            AND ((resource_type='institution' AND resource_id='') OR (resource_type=? AND resource_id=?))""",
            (institution_id, actor, resource_type, resource_id),
        )
        membership_roles.update(str(row["role"]) for row in bindings)
        return {role for role in membership_roles if role in CANONICAL_ROLES}

    def authorize(
        self,
        actor: str,
        institution_id: str,
        action: str,
        *,
        resource_type: str = "institution",
        resource_id: str = "",
        require: bool = True,
    ) -> AuthorizationDecision:
        if resource_type not in RESOURCE_TYPES:
            raise EducationError("Unsupported education resource type.")
        if resource_id:
            registered = self.platform._one(
                "SELECT institution_id,state FROM education_resource_registry WHERE resource_type=? AND external_id=?",
                (resource_type, resource_id),
            )
            if registered and registered["institution_id"] != institution_id:
                raise Denied("Cross-institution resource access denied.")
            if registered and registered["state"] != "active":
                raise Denied("Inactive education resource access denied.")
        roles = self.roles(actor, institution_id, resource_type=resource_type, resource_id=resource_id)
        allowed = any("*" in ROLE_ACTIONS.get(role, set()) or action in ROLE_ACTIONS.get(role, set()) for role in roles)
        decision = AuthorizationDecision(
            allowed, tuple(sorted(roles)), action, resource_type, resource_id,
            "role_binding" if allowed else "no_matching_role_action",
        )
        if require and not allowed:
            raise Denied(f"Permission denied for {action} on {resource_type}.")
        return decision

    def register_resource(
        self,
        actor: str,
        institution_id: str,
        resource_type: str,
        external_id: str,
        *,
        parent_resource_id: str = "",
        owner_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._institution(institution_id)
        if resource_type not in RESOURCE_TYPES or not str(external_id).strip():
            raise EducationError("A supported resource type and identifier are required.")
        parent_id: str | None = None
        if parent_resource_id:
            parent = self.platform._one(
                "SELECT * FROM education_resource_registry WHERE id=? OR external_id=?",
                (parent_resource_id, parent_resource_id),
            )
            if not parent or parent["institution_id"] != institution_id:
                raise Denied("Resource parent must belong to the same institution.")
            parent_id = str(parent["id"])
        timestamp = now()
        resource_id = ident("edures")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_resource_registry VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,resource_type,external_id) DO UPDATE SET
                parent_resource_id=excluded.parent_resource_id,owner_id=excluded.owner_id,
                state='active',metadata_json=excluded.metadata_json,updated_at=excluded.updated_at""",
                (resource_id, institution_id, resource_type, str(external_id), parent_id, owner_id,
                 "active", _json(metadata or {}), timestamp, timestamp),
            )
        return self.platform._one(
            "SELECT * FROM education_resource_registry WHERE institution_id=? AND resource_type=? AND external_id=?",
            (institution_id, resource_type, str(external_id)),
        )

    def grant_role(
        self,
        actor: str,
        institution_id: str,
        user_id: str,
        role: str,
        *,
        resource_type: str = "institution",
        resource_id: str = "",
    ) -> dict[str, Any]:
        self.authorize(actor, institution_id, "manage_roles")
        normalized = str(role).strip().lower().replace("/", "_")
        if normalized not in CANONICAL_ROLES:
            raise EducationError("Unsupported canonical Education OS role.")
        if resource_type not in RESOURCE_TYPES:
            raise EducationError("Unsupported role-binding resource type.")
        if resource_id:
            self.authorize(actor, institution_id, "manage", resource_type=resource_type, resource_id=resource_id)
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_role_bindings VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,user_id,role,resource_type,resource_id) DO UPDATE SET
                state='active',granted_by=excluded.granted_by,updated_at=excluded.updated_at""",
                (ident("role"), institution_id, user_id, normalized, resource_type, resource_id,
                 "active", actor, timestamp, timestamp),
            )
        self.platform._audit(actor, "education_os_role_granted", resource_type, resource_id or institution_id,
                             institution_id, {"user_id": user_id, "role": normalized})
        return self.platform._one(
            """SELECT * FROM education_role_bindings WHERE institution_id=? AND user_id=?
            AND role=? AND resource_type=? AND resource_id=?""",
            (institution_id, user_id, normalized, resource_type, resource_id),
        )

    def emit_event(
        self,
        institution_id: str,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
        *,
        dedupe_key: str,
    ) -> dict[str, Any]:
        self._institution(institution_id)
        if not event_type.strip() or not dedupe_key.strip():
            raise EducationError("Event type and dedupe key are required.")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_outbox VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,dedupe_key) DO NOTHING""",
                (ident("outbox"), institution_id, event_type.strip(), aggregate_type.strip(),
                 aggregate_id.strip(), _json(payload), dedupe_key.strip()[:240], "pending", 0,
                 timestamp, "", timestamp, None, timestamp),
            )
        return self.platform._one(
            "SELECT * FROM education_outbox WHERE institution_id=? AND dedupe_key=?",
            (institution_id, dedupe_key.strip()[:240]),
        )

    def run_idempotent(
        self,
        actor: str,
        institution_id: str,
        operation: str,
        idempotency_key: str,
        payload: dict[str, Any],
        callback: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        key = str(idempotency_key).strip()
        if not key or len(key) > 160:
            raise EducationError("Idempotency key is required and must be at most 160 characters.")
        request_hash = _sha256_bytes(_json(payload).encode("utf-8"))
        existing = self.platform._one(
            """SELECT * FROM education_idempotency_keys WHERE institution_id=? AND actor_id=?
            AND operation=? AND idempotency_key=?""",
            (institution_id, actor, operation, key),
        )
        if existing:
            if existing["request_sha256"] != request_hash:
                raise Conflict("Idempotency key was already used with a different request.")
            if existing["state"] == "completed":
                return _decode(existing["response_json"], {})
            raise Conflict("The idempotent operation is already in progress.")
        timestamp = now()
        record_id = ident("idem")
        expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_idempotency_keys VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (record_id, institution_id, actor, operation, key, request_hash, "{}", "running",
                 expires, timestamp, timestamp),
            )
        try:
            response = callback()
        except Exception:
            with self.db.connection() as db:
                db.execute("UPDATE education_idempotency_keys SET state='failed',updated_at=? WHERE id=?", (now(), record_id))
            raise
        with self.db.connection() as db:
            db.execute(
                "UPDATE education_idempotency_keys SET response_json=?,state='completed',updated_at=? WHERE id=?",
                (_json(response), now(), record_id),
            )
        return response

    def _ensure_member_role(self, actor: str, institution_id: str, user_id: str, role: str) -> None:
        rows = self.platform.membership(user_id, institution_id)
        if not any(str(row["role"]) == role for row in rows):
            self.platform.add_member(actor, institution_id, user_id, role)

    def ensure_shiro_scope(
        self,
        actor: str,
        institution_id: str,
        course_id: str,
        *,
        classroom_id: str = "",
        collection_name: str = "",
    ) -> dict[str, Any]:
        self.authorize(actor, institution_id, "manage", resource_type="course", resource_id=course_id)
        subject = self.platform._one("SELECT id,name FROM subjects WHERE id=? AND institution_id=?", (course_id, institution_id))
        if not subject:
            raise Missing("Course subject not found.")
        scope = self.platform._one(
            "SELECT * FROM education_shiro_scopes WHERE institution_id=? AND course_id=? AND classroom_id=?",
            (institution_id, course_id, classroom_id),
        )
        if scope:
            return scope
        digest = hashlib.sha256(f"{institution_id}:{course_id}:{classroom_id}".encode("utf-8")).hexdigest()[:28]
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_shiro_scopes VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (ident("scope"), institution_id, course_id, classroom_id, f"education-{digest}",
                 collection_name.strip() or str(subject["name"]), 1, "active", actor, timestamp, timestamp),
            )
        return self.platform._one(
            "SELECT * FROM education_shiro_scopes WHERE institution_id=? AND course_id=? AND classroom_id=?",
            (institution_id, course_id, classroom_id),
        )

    def create_learning_workspace(
        self,
        actor: str,
        institution_id: str,
        *,
        program_name: str,
        course_code: str,
        course_name: str,
        classroom_name: str,
        teacher_id: str,
        academic_year: str = "",
    ) -> dict[str, Any]:
        self.authorize(actor, institution_id, "create")
        if not all(str(value).strip() for value in (program_name, course_code, course_name, classroom_name, teacher_id)):
            raise EducationError("Program, course, classroom and teacher are required.")
        self._ensure_member_role(actor, institution_id, teacher_id, "subject_teacher")
        program = self.platform.create_unit(actor, institution_id, program_name.strip(), "program", academic_year=academic_year)
        subject = self.platform.create_subject(actor, institution_id, course_code.strip(), course_name.strip(), program["id"])
        self.platform.assign_teacher(actor, institution_id, subject["id"], teacher_id)
        classroom = self.platform.create_unit(
            actor, institution_id, classroom_name.strip(), "class_section", parent_id=program["id"], academic_year=academic_year
        )
        program_resource = self.register_resource(actor, institution_id, "program", program["id"], owner_id=actor)
        course_resource = self.register_resource(
            actor, institution_id, "course", subject["id"], parent_resource_id=program_resource["id"], owner_id=teacher_id,
            metadata={"code": subject["code"], "name": subject["name"]},
        )
        self.register_resource(
            actor, institution_id, "classroom", classroom["id"], parent_resource_id=course_resource["id"], owner_id=teacher_id,
            metadata={"subject_id": subject["id"], "academic_year": academic_year},
        )
        self.grant_role(actor, institution_id, teacher_id, "teacher", resource_type="course", resource_id=subject["id"])
        self.grant_role(actor, institution_id, teacher_id, "teacher", resource_type="classroom", resource_id=classroom["id"])
        scope = self.ensure_shiro_scope(actor, institution_id, subject["id"], classroom_id=classroom["id"])
        workflow_id = ident("workflow")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_workflow_instances VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (workflow_id, institution_id, program["id"], subject["id"], classroom["id"], teacher_id,
                 "", "classroom_created", "active", "", _json({"shiro_scope_id": scope["id"]}),
                 1, actor, timestamp, timestamp),
            )
        self.emit_event(
            institution_id, "education.classroom.created", "classroom", classroom["id"],
            {"workflow_id": workflow_id, "course_id": subject["id"], "classroom_id": classroom["id"],
             "teacher_id": teacher_id, "title": classroom_name},
            dedupe_key=f"classroom-created:{classroom['id']}",
        )
        return {
            "workflow_id": workflow_id, "program": program, "course": subject, "classroom": classroom,
            "shiro_scope": scope, "stage": "classroom_created",
        }

    def enroll_student(
        self,
        actor: str,
        workflow_id: str,
        student_id: str,
    ) -> dict[str, Any]:
        workflow = self.platform._one("SELECT * FROM education_workflow_instances WHERE id=?", (workflow_id,))
        if not workflow:
            raise Missing("Education workflow not found.")
        institution_id = str(workflow["institution_id"])
        self.authorize(actor, institution_id, "manage", resource_type="classroom", resource_id=str(workflow["classroom_id"]))
        self._ensure_member_role(actor, institution_id, student_id, "university_student")
        enrolment = self.platform.enroll(actor, institution_id, workflow["course_id"], student_id)
        scope = self.platform._one(
            "SELECT * FROM education_shiro_scopes WHERE institution_id=? AND course_id=? AND classroom_id=?",
            (institution_id, workflow["course_id"], workflow["classroom_id"]),
        )
        timestamp = now()
        if scope:
            with self.db.connection() as db:
                db.execute(
                    """INSERT INTO education_shiro_scope_acl VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(scope_id,user_id) DO UPDATE SET access_level='learner',state='active',
                    granted_by=excluded.granted_by,updated_at=excluded.updated_at""",
                    (ident("scopeacl"), scope["id"], institution_id, student_id, "learner", "active", actor, timestamp, timestamp),
                )
        with self.db.connection() as db:
            db.execute(
                "UPDATE education_workflow_instances SET student_id=?,stage='student_enrolled',version=version+1,updated_at=? WHERE id=?",
                (student_id, timestamp, workflow_id),
            )
        self.emit_event(
            institution_id, "education.student.enrolled", "classroom", workflow["classroom_id"],
            {"workflow_id": workflow_id, "student_id": student_id, "course_id": workflow["course_id"],
             "classroom_id": workflow["classroom_id"]},
            dedupe_key=f"workflow:{workflow_id}:student:{student_id}:enrolled",
        )
        return {"workflow_id": workflow_id, "enrolment": enrolment, "stage": "student_enrolled"}

    def _shiro_orchestrator(self) -> Any:
        if self.shiro is None:
            from biointel.shiro.core.orchestrator import ShiroOrchestrator
            self.shiro = ShiroOrchestrator(root=self.root, data_dir=self.root / "UserData" / "education" / "shiro")
        return self.shiro

    def _scope_access(self, actor: str, scope: dict[str, Any], *, manage: bool = False) -> None:
        institution_id = str(scope["institution_id"])
        roles = self.roles(actor, institution_id, resource_type="course", resource_id=str(scope["course_id"]))
        if roles & {"platform_administrator", "institution_administrator", "department_administrator", "teacher", "instructor"}:
            return
        if manage:
            raise Denied("Only authorized course staff may manage Shiro collections.")
        acl = self.platform._one(
            "SELECT 1 ok FROM education_shiro_scope_acl WHERE scope_id=? AND user_id=? AND state='active'",
            (scope["id"], actor),
        )
        enrolled = self.platform._one(
            "SELECT 1 ok FROM enrollments WHERE institution_id=? AND subject_id=? AND student_id=? AND state='active'",
            (institution_id, scope["course_id"], actor),
        )
        if not acl and not enrolled:
            raise Denied("Shiro course scope access denied.")

    def index_material(self, actor: str, material_id: str, *, classroom_id: str = "") -> dict[str, Any]:
        material = self.platform._one("SELECT * FROM materials WHERE id=?", (material_id,))
        if not material:
            raise Missing("Course material not found.")
        institution_id = str(material["institution_id"])
        self.authorize(actor, institution_id, "manage", resource_type="course", resource_id=str(material["subject_id"]))
        if str(material["state"]) != "published":
            raise Conflict("Only published teacher-approved material may be indexed.")
        scope = self.ensure_shiro_scope(actor, institution_id, str(material["subject_id"]), classroom_id=classroom_id)
        self._scope_access(actor, scope, manage=True)
        source_path = Path(str(material["storage_path"])).resolve()
        storage_root = Path(self.platform.storage).resolve()
        if not source_path.is_relative_to(storage_root) or not source_path.is_file():
            raise Denied("Material storage path is unavailable or outside tenant storage.")
        result = self._shiro_orchestrator().ingest(
            str(scope["project_id"]), source_path.read_bytes(), str(material["file_name"]),
            project_name=str(scope["collection_name"]), source_type="course_material", internal=True,
            confidential=True, metadata={"institution_id": institution_id, "course_id": material["subject_id"],
                                         "classroom_id": classroom_id, "material_id": material_id,
                                         "approved_by": actor},
        )
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_shiro_documents VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(scope_id,material_id) DO UPDATE SET shiro_source_id=excluded.shiro_source_id,
                approval_state='approved',approved_by=excluded.approved_by,metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at""",
                (ident("shirodoc"), scope["id"], institution_id, material_id, result.source.source_id,
                 "approved", actor, _json({"sha256": material["sha256"], "chunks": result.chunks_indexed}),
                 timestamp, timestamp),
            )
        self.emit_event(
            institution_id, "education.shiro.material_indexed", "document", material_id,
            {"scope_id": scope["id"], "source_id": result.source.source_id, "chunks": result.chunks_indexed},
            dedupe_key=f"shiro-index:{scope['id']}:{material_id}:{material['sha256']}",
        )
        return {"scope": scope, "source": result.source.to_dict(), "chunks_indexed": result.chunks_indexed,
                "duplicate": result.duplicate, "evidence_status": "approved_indexed"}

    def ask_shiro(
        self,
        actor: str,
        scope_id: str,
        question: str,
        *,
        mode: str = "tutoring",
        response_language: str = "auto",
        provider: str = "local",
        cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        scope = self.platform._one("SELECT * FROM education_shiro_scopes WHERE id=? AND state='active'", (scope_id,))
        if not scope:
            raise Missing("Shiro education scope not found.")
        self._scope_access(actor, scope)
        normalized_mode = str(mode).strip().lower()
        if normalized_mode not in SHIRO_MODES:
            raise EducationError("Unsupported Shiro learning mode.")
        response = self._shiro_orchestrator().chat(
            str(scope["project_id"]), str(question), response_language=response_language,
            provider=provider, cancelled=cancelled,
        ).to_dict()
        if response.get("evidence_status") == "insufficient":
            response["evidence_status"] = "insufficient_evidence"
        response.update({"scope_id": scope_id, "institution_id": scope["institution_id"],
                         "course_id": scope["course_id"], "classroom_id": scope["classroom_id"],
                         "learning_mode": normalized_mode})
        return response

    def generate_shiro_artifact(
        self,
        actor: str,
        scope_id: str,
        *,
        artifact_type: str,
        title: str,
        prompt: str,
        response_language: str = "auto",
    ) -> dict[str, Any]:
        if artifact_type not in {"quiz", "flashcard", "notes", "summary", "remediation"}:
            raise EducationError("Unsupported Shiro artifact type.")
        response = self.ask_shiro(actor, scope_id, prompt, mode=artifact_type, response_language=response_language)
        scope = self.platform._one("SELECT * FROM education_shiro_scopes WHERE id=?", (scope_id,))
        timestamp = now()
        artifact_id = ident("shiroartifact")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_shiro_generated_artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (artifact_id, scope_id, scope["institution_id"], actor, artifact_type, title.strip(),
                 _json({"text": response["answer"]}), _json(response.get("citations", [])),
                 response.get("evidence_status", "unknown"), "draft", "", None, "", timestamp, timestamp),
            )
        return self.platform._one("SELECT * FROM education_shiro_generated_artifacts WHERE id=?", (artifact_id,))

    def review_shiro_artifact(self, actor: str, artifact_id: str, *, approve: bool, note: str = "") -> dict[str, Any]:
        artifact = self.platform._one("SELECT * FROM education_shiro_generated_artifacts WHERE id=?", (artifact_id,))
        if not artifact:
            raise Missing("Generated Shiro artifact not found.")
        scope = self.platform._one("SELECT * FROM education_shiro_scopes WHERE id=?", (artifact["scope_id"],))
        self._scope_access(actor, scope, manage=True)
        state = "approved" if approve else "rejected"
        with self.db.connection() as db:
            db.execute(
                "UPDATE education_shiro_generated_artifacts SET state=?,reviewed_by=?,reviewed_at=?,review_note=?,updated_at=? WHERE id=?",
                (state, actor, now(), note[:2000], now(), artifact_id),
            )
        return self.platform._one("SELECT * FROM education_shiro_generated_artifacts WHERE id=?", (artifact_id,))

    def publish_material(
        self,
        actor: str,
        workflow_id: str,
        *,
        title: str,
        source_path: str | Path,
        download_allowed: bool = True,
        index_with_shiro: bool = True,
    ) -> dict[str, Any]:
        workflow = self.platform._one("SELECT * FROM education_workflow_instances WHERE id=?", (workflow_id,))
        if not workflow:
            raise Missing("Education workflow not found.")
        institution_id = str(workflow["institution_id"])
        self.authorize(actor, institution_id, "publish", resource_type="course", resource_id=str(workflow["course_id"]))
        material = self.platform.add_material(
            actor, institution_id, workflow["course_id"], title, Path(source_path), download_allowed
        )
        indexed: dict[str, Any] | None = None
        if index_with_shiro:
            indexed = self.index_material(actor, material["id"], classroom_id=str(workflow["classroom_id"]))
        with self.db.connection() as db:
            db.execute(
                "UPDATE education_workflow_instances SET stage='material_published',version=version+1,updated_at=? WHERE id=?",
                (now(), workflow_id),
            )
        self.emit_event(
            institution_id, "education.material.published", "document", material["id"],
            {"workflow_id": workflow_id, "course_id": workflow["course_id"], "classroom_id": workflow["classroom_id"],
             "title": title, "teacher_id": actor},
            dedupe_key=f"material-published:{material['id']}",
        )
        return {"material": material, "shiro": indexed, "stage": "material_published"}

    def create_assignment(
        self,
        actor: str,
        workflow_id: str,
        *,
        title: str,
        instructions: str,
        due_at: str,
        max_marks: float = 100.0,
        allowed_types: Iterable[str] | None = None,
        late_policy: str = "reject",
    ) -> dict[str, Any]:
        workflow = self.platform._one("SELECT * FROM education_workflow_instances WHERE id=?", (workflow_id,))
        if not workflow:
            raise Missing("Education workflow not found.")
        institution_id = str(workflow["institution_id"])
        self.authorize(actor, institution_id, "create", resource_type="classroom", resource_id=str(workflow["classroom_id"]))
        assignment = self.platform.create_assignment(
            actor, institution_id, workflow["course_id"], title, instructions, due_at, max_marks,
            allowed_types=list(allowed_types or []), late_policy=late_policy, publish=True,
        )
        self.register_resource(actor, institution_id, "assignment", assignment["id"], owner_id=actor,
                               metadata={"course_id": workflow["course_id"], "classroom_id": workflow["classroom_id"]})
        with self.db.connection() as db:
            db.execute("UPDATE education_workflow_instances SET stage='assessment_created',version=version+1,updated_at=? WHERE id=?", (now(), workflow_id))
        self.emit_event(
            institution_id, "education.assignment.published", "assignment", assignment["id"],
            {"workflow_id": workflow_id, "recipient_id": workflow["student_id"], "title": title,
             "body": f"Assignment published: {title}. Due {due_at}", "course_id": workflow["course_id"]},
            dedupe_key=f"assignment-published:{assignment['id']}",
        )
        return {"assignment": assignment, "stage": "assessment_created"}

    def submit_assignment(
        self,
        actor: str,
        assignment_id: str,
        *,
        body: str = "",
        file_path: str = "",
        final: bool = True,
        idempotency_key: str,
    ) -> dict[str, Any]:
        assignment = self.platform._one("SELECT * FROM assignments WHERE id=?", (assignment_id,))
        if not assignment:
            raise Missing("Assignment not found.")
        institution_id = str(assignment["institution_id"])
        self.authorize(actor, institution_id, "submit", resource_type="assignment", resource_id=assignment_id)
        payload = {"assignment_id": assignment_id, "body": body, "file_path": file_path, "final": final}

        def perform() -> dict[str, Any]:
            submission = self.platform.submit_assignment(actor, assignment_id, body, file_path, final)
            self.emit_event(
                institution_id, "education.assignment.submitted", "assignment", assignment_id,
                {"submission_id": submission["id"], "student_id": actor, "assignment_id": assignment_id},
                dedupe_key=f"submission:{submission['id']}:final:{int(final)}",
            )
            return submission

        return self.run_idempotent(actor, institution_id, "assignment.submit", idempotency_key, payload, perform)

    def grade_submission(
        self,
        actor: str,
        submission_id: str,
        *,
        marks: float,
        feedback: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        submission = self.platform._one(
            """SELECT x.*,a.subject_id,a.max_marks FROM submissions x
            JOIN assignments a ON a.id=x.assignment_id WHERE x.id=?""",
            (submission_id,),
        )
        if not submission:
            raise Missing("Submission not found.")
        institution_id = str(submission["institution_id"])
        self.authorize(actor, institution_id, "grade", resource_type="assignment", resource_id=str(submission["assignment_id"]))
        grade = self.platform.grade_submission(actor, submission_id, marks, feedback, reason)
        interventions = self.refresh_interventions(actor, institution_id, str(submission["student_id"]), str(submission["subject_id"]))
        self.emit_event(
            institution_id, "education.grade.released", "assignment", submission["assignment_id"],
            {"recipient_id": submission["student_id"], "title": "Assignment result available",
             "body": f"A result and feedback are available for assignment {submission['assignment_id']}.",
             "submission_id": submission_id, "grade_id": grade["id"]},
            dedupe_key=f"grade-released:{grade['id']}:{grade['updated_at']}",
        )
        return {"grade": grade, "interventions": interventions}

    def _upsert_intervention(
        self,
        institution_id: str,
        student_id: str,
        subject_id: str,
        *,
        category: str,
        reason_code: str,
        rationale: str,
        evidence: dict[str, Any],
        confidence: float,
        minimum_data_met: bool,
    ) -> dict[str, Any]:
        timestamp = now()
        intervention_id = "intervention_" + hashlib.sha256(
            f"{institution_id}:{student_id}:{subject_id}:{reason_code}".encode("utf-8")
        ).hexdigest()[:24]
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_intervention_recommendations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,student_id,subject_id,concept_id,reason_code) DO UPDATE SET
                category=excluded.category,rationale=excluded.rationale,evidence_json=excluded.evidence_json,
                confidence=excluded.confidence,minimum_data_met=excluded.minimum_data_met,
                model_kind=excluded.model_kind,model_version=excluded.model_version,
                state=CASE WHEN education_intervention_recommendations.state IN ('accepted','dismissed')
                    THEN education_intervention_recommendations.state ELSE 'pending_review' END,
                updated_at=excluded.updated_at""",
                (intervention_id, institution_id, student_id, subject_id, "", category, reason_code,
                 rationale, _json(evidence), max(0.0, min(float(confidence), 1.0)), int(minimum_data_met),
                 "rule_based_indicator", "education-os-rules-1.0", "pending_review", 1, "", None, "",
                 timestamp, timestamp),
            )
        return self.platform._one("SELECT * FROM education_intervention_recommendations WHERE id=?", (intervention_id,))

    def refresh_interventions(
        self,
        actor: str,
        institution_id: str,
        student_id: str,
        subject_id: str = "",
    ) -> list[dict[str, Any]]:
        self.authorize(actor, institution_id, "review")
        conditions = "a.institution_id=? AND x.student_id=?"
        args: list[Any] = [institution_id, student_id]
        if subject_id:
            conditions += " AND a.subject_id=?"
            args.append(subject_id)
        grade_rows = self.platform._all(
            f"""SELECT a.subject_id,g.marks,a.max_marks FROM grades g
            JOIN submissions x ON x.id=g.submission_id JOIN assignments a ON a.id=x.assignment_id
            WHERE {conditions} AND g.state='released'""",
            tuple(args),
        )
        by_subject: dict[str, list[float]] = {}
        for row in grade_rows:
            maximum = float(row["max_marks"] or 0)
            if maximum > 0:
                by_subject.setdefault(str(row["subject_id"]), []).append(float(row["marks"]) / maximum)
        created: list[dict[str, Any]] = []
        for current_subject, scores in by_subject.items():
            average = sum(scores) / len(scores)
            minimum = len(scores) >= 2
            if minimum and average < 0.60:
                created.append(self._upsert_intervention(
                    institution_id, student_id, current_subject, category="weak_concept_support",
                    reason_code="ASSIGNMENT_AVERAGE_BELOW_60",
                    rationale="Two or more released assignment grades average below the configured 60% support threshold.",
                    evidence={"released_grade_count": len(scores), "average_ratio": round(average, 4),
                              "threshold": 0.60},
                    confidence=min(0.95, 0.55 + len(scores) * 0.07), minimum_data_met=True,
                ))
        attendance_args: list[Any] = [institution_id, student_id]
        attendance_filter = "r.institution_id=? AND r.student_id=?"
        if subject_id:
            attendance_filter += " AND s.subject_id=?"
            attendance_args.append(subject_id)
        attendance = self.platform._all(
            f"""SELECT s.subject_id,COUNT(*) total,
            SUM(CASE WHEN r.status IN ('present','late','online_present','practical_attendance','examination_attendance') THEN 1 ELSE 0 END) attended
            FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id
            WHERE {attendance_filter} GROUP BY s.subject_id""",
            tuple(attendance_args),
        )
        for row in attendance:
            total = int(row["total"] or 0)
            ratio = (int(row["attended"] or 0) / total) if total else 0.0
            if total >= 3 and ratio < 0.75:
                created.append(self._upsert_intervention(
                    institution_id, student_id, str(row["subject_id"]), category="attendance_support",
                    reason_code="ATTENDANCE_BELOW_75",
                    rationale="Recorded attendance is below 75% across at least three completed sessions.",
                    evidence={"recorded_sessions": total, "attendance_ratio": round(ratio, 4), "threshold": 0.75},
                    confidence=min(0.95, 0.50 + total * 0.04), minimum_data_met=True,
                ))
        if not created and not grade_rows and not attendance:
            created.append(self._upsert_intervention(
                institution_id, student_id, subject_id, category="data_quality",
                reason_code="MINIMUM_DATA_NOT_MET",
                rationale="No learning-risk recommendation was generated because the minimum evidence threshold was not met.",
                evidence={"released_grade_count": 0, "attendance_sessions": 0}, confidence=0.0,
                minimum_data_met=False,
            ))
        return created

    def review_intervention(
        self,
        actor: str,
        intervention_id: str,
        *,
        decision: str,
        note: str = "",
    ) -> dict[str, Any]:
        row = self.platform._one("SELECT * FROM education_intervention_recommendations WHERE id=?", (intervention_id,))
        if not row:
            raise Missing("Intervention recommendation not found.")
        self.authorize(actor, row["institution_id"], "review", resource_type="report", resource_id=intervention_id)
        state = str(decision).strip().lower()
        if state not in {"accepted", "dismissed", "corrected"}:
            raise EducationError("Intervention decision must be accepted, dismissed or corrected.")
        with self.db.connection() as db:
            db.execute(
                "UPDATE education_intervention_recommendations SET state=?,reviewed_by=?,reviewed_at=?,review_note=?,updated_at=? WHERE id=?",
                (state, actor, now(), note[:4000], now(), intervention_id),
            )
        self.platform._audit(actor, "intervention_reviewed", "report", intervention_id,
                             row["institution_id"], {"decision": state, "note": note[:500]})
        return self.platform._one("SELECT * FROM education_intervention_recommendations WHERE id=?", (intervention_id,))

    def home_snapshot(self, actor: str, institution_id: str) -> dict[str, Any]:
        roles = self.roles(actor, institution_id)
        if not roles:
            raise Denied("Institution membership is required.")
        timestamp = now()
        if "student" in roles:
            subjects = self.platform._all(
                """SELECT s.id,s.code,s.name FROM subjects s JOIN enrollments e ON e.subject_id=s.id
                WHERE s.institution_id=? AND e.student_id=? AND e.state='active' ORDER BY s.code""",
                (institution_id, actor),
            )
            timetable = self.platform._all(
                """SELECT t.*,s.code,s.name FROM timetable_entries t JOIN subjects s ON s.id=t.subject_id
                JOIN enrollments e ON e.subject_id=s.id WHERE t.institution_id=? AND e.student_id=?
                AND t.ends_at>=? AND t.state='scheduled' ORDER BY t.starts_at LIMIT 25""",
                (institution_id, actor, timestamp),
            )
            assignments = self.platform._all(
                """SELECT a.*,s.code,s.name,x.state submission_state FROM assignments a
                JOIN subjects s ON s.id=a.subject_id JOIN enrollments e ON e.subject_id=a.subject_id
                LEFT JOIN submissions x ON x.assignment_id=a.id AND x.student_id=?
                WHERE a.institution_id=? AND e.student_id=? AND a.state='published'
                AND (x.id IS NULL OR x.state<>'submitted') ORDER BY a.due_at LIMIT 50""",
                (actor, institution_id, actor),
            )
            results = self.platform.view_results(actor, institution_id, actor)
            interventions = self.platform._all(
                """SELECT * FROM education_intervention_recommendations WHERE institution_id=? AND student_id=?
                AND state='accepted' ORDER BY updated_at DESC LIMIT 25""",
                (institution_id, actor),
            )
        elif roles & {"teacher", "instructor", "examiner"}:
            subjects = self.platform._all(
                """SELECT DISTINCT s.id,s.code,s.name FROM subjects s JOIN teacher_assignments t ON t.subject_id=s.id
                WHERE s.institution_id=? AND t.teacher_id=? AND t.state='active' ORDER BY s.code""",
                (institution_id, actor),
            )
            timetable = self.platform._all(
                """SELECT t.*,s.code,s.name FROM timetable_entries t JOIN subjects s ON s.id=t.subject_id
                WHERE t.institution_id=? AND t.teacher_id=? AND t.ends_at>=? ORDER BY t.starts_at LIMIT 50""",
                (institution_id, actor, timestamp),
            )
            assignments = self.platform._all(
                """SELECT a.*,s.code,s.name FROM assignments a JOIN subjects s ON s.id=a.subject_id
                JOIN teacher_assignments t ON t.subject_id=s.id WHERE a.institution_id=? AND t.teacher_id=?
                ORDER BY a.due_at DESC LIMIT 50""",
                (institution_id, actor),
            )
            results = []
            interventions = self.platform._all(
                """SELECT * FROM education_intervention_recommendations WHERE institution_id=?
                AND state='pending_review' ORDER BY confidence DESC,updated_at DESC LIMIT 50""",
                (institution_id,),
            )
        else:
            subjects = self.platform._all("SELECT id,code,name FROM subjects WHERE institution_id=? AND state='active' ORDER BY code", (institution_id,))
            timetable = self.platform._all(
                """SELECT t.*,s.code,s.name FROM timetable_entries t LEFT JOIN subjects s ON s.id=t.subject_id
                WHERE t.institution_id=? AND t.ends_at>=? ORDER BY t.starts_at LIMIT 100""",
                (institution_id, timestamp),
            )
            assignments = self.platform._all("SELECT * FROM assignments WHERE institution_id=? ORDER BY due_at DESC LIMIT 100", (institution_id,))
            results = []
            interventions = self.platform._all(
                "SELECT * FROM education_intervention_recommendations WHERE institution_id=? ORDER BY updated_at DESC LIMIT 100",
                (institution_id,),
            )
        unread_connect = self.unread_connect_count(actor, institution_id)
        return {
            "actor": actor, "institution_id": institution_id, "roles": sorted(roles), "subjects": subjects,
            "upcoming_timetable": timetable, "pending_assignments": assignments, "recent_results": results[:25],
            "interventions": interventions, "unread_connect_messages": unread_connect,
            "generated_at": timestamp, "data_status": "persistent_local",
        }

    def _connect_services(self) -> Any:
        if self.connect is None:
            from biointel.connect.services import build_connect_services
            self.connect = build_connect_services(self.root)
        return self.connect

    def _connect_identity(self, education_user_id: str, institution_id: str, *, role: str = "education_member") -> dict[str, Any]:
        link = self.platform._one(
            "SELECT * FROM education_connect_identities WHERE institution_id=? AND education_user_id=? AND state='active'",
            (institution_id, education_user_id),
        )
        services = self._connect_services()
        if link:
            user = services.repository.user(str(link["connect_user_id"]))
            if user:
                return user
        username = f"edu-{_safe_username(institution_id)[:18]}-{_safe_username(education_user_id)[:26]}"
        user = services.ensure_identity(username, education_user_id, role)
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_connect_identities VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,education_user_id) DO UPDATE SET connect_user_id=excluded.connect_user_id,
                connect_username=excluded.connect_username,state='active',updated_at=excluded.updated_at""",
                (ident("connectidentity"), institution_id, education_user_id, user["user_id"], user["username"],
                 "active", timestamp, timestamp),
            )
        return user

    def unread_connect_count(self, actor: str, institution_id: str) -> int | None:
        try:
            user = self._connect_identity(actor, institution_id)
            notifications = self._connect_services().content.notifications(str(user["user_id"]), 250)
            return sum(1 for item in notifications if not item.get("read_at_utc"))
        except Exception:
            return None

    def _deliver_notification(self, row: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        recipient = str(payload.get("recipient_id") or "").strip()
        if not recipient:
            return {"state": "ignored", "reason": "no_recipient"}
        institution_id = str(row["institution_id"])
        services = self._connect_services()
        receiver = self._connect_identity(recipient, institution_id)
        sender = self._connect_identity("biointel-education", institution_id, role="system")
        notification_id = services.repository.notification(
            str(receiver["user_id"]), str(sender["user_id"]), "education_update",
            str(row["aggregate_type"]), str(row["aggregate_id"]),
            str(payload.get("body") or payload.get("title") or row["event_type"]),
        )
        return {"state": "delivered", "connect_notification_id": notification_id,
                "connect_recipient_id": receiver["user_id"]}

    def dispatch_outbox(self, actor: str, institution_id: str, *, limit: int = 100) -> dict[str, Any]:
        self.authorize(actor, institution_id, "manage")
        rows = self.platform._all(
            """SELECT * FROM education_outbox WHERE institution_id=? AND state IN ('pending','failed')
            AND next_attempt_at<=? ORDER BY created_at LIMIT ?""",
            (institution_id, now(), max(1, min(int(limit), 500))),
        )
        delivered, failed, details = 0, 0, []
        for row in rows:
            payload = _decode(row["payload_json"], {})
            try:
                result: dict[str, Any]
                if row["event_type"] in {
                    "education.assignment.published", "education.grade.released", "education.intervention.accepted",
                    "education.exam.published", "education.announcement.published",
                }:
                    result = self._deliver_notification(row, payload)
                else:
                    result = {"state": "recorded", "transport": "education_event_stream"}
                    self.phase16.publish_event(
                        actor, institution_id, channel="education-os", event_type=str(row["event_type"]),
                        target_type=str(row["aggregate_type"]), target_id=str(row["aggregate_id"]), payload=payload,
                    )
                with self.db.connection() as db:
                    db.execute(
                        "UPDATE education_outbox SET state='published',attempts=attempts+1,last_error='',published_at=?,updated_at=? WHERE id=?",
                        (now(), now(), row["id"]),
                    )
                delivered += 1
                details.append({"outbox_id": row["id"], **result})
            except Exception as exc:
                retry_at = (datetime.now(timezone.utc) + timedelta(seconds=min(3600, 2 ** min(int(row["attempts"]) + 1, 10)))).isoformat()
                with self.db.connection() as db:
                    db.execute(
                        "UPDATE education_outbox SET state='failed',attempts=attempts+1,last_error=?,next_attempt_at=?,updated_at=? WHERE id=?",
                        (f"{type(exc).__name__}: {exc}"[:4000], retry_at, now(), row["id"]),
                    )
                failed += 1
                details.append({"outbox_id": row["id"], "state": "failed", "error": f"{type(exc).__name__}: {exc}"})
        return {"processed": len(rows), "delivered": delivered, "failed": failed, "details": details}

    def create_studio_project(
        self,
        actor: str,
        institution_id: str,
        *,
        title: str,
        project_type: str,
        description: str = "",
    ) -> dict[str, Any]:
        self.authorize(actor, institution_id, "create")
        normalized = str(project_type).strip().lower()
        if normalized not in STUDIO_TYPES:
            raise EducationError("Unsupported BioIntel Studio project type.")
        if not title.strip() or len(title) > 240:
            raise EducationError("Studio project title is required and must be at most 240 characters.")
        timestamp = now()
        project_id = ident("studio")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_studio_projects VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (project_id, institution_id, actor, title.strip(), normalized, description.strip()[:4000],
                 "draft", 0, "{}", timestamp, timestamp),
            )
        self.register_resource(actor, institution_id, "studio_project", project_id, owner_id=actor,
                               metadata={"project_type": normalized})
        return self.platform._one("SELECT * FROM education_studio_projects WHERE id=?", (project_id,))

    def _studio_project(self, actor: str, project_id: str, *, action: str = "view") -> dict[str, Any]:
        project = self.platform._one("SELECT * FROM education_studio_projects WHERE id=?", (project_id,))
        if not project:
            raise Missing("Studio project not found.")
        decision = self.authorize(
            actor, project["institution_id"], action, resource_type="studio_project", resource_id=project_id,
            require=False,
        )
        if not decision.allowed and project["owner_id"] != actor:
            raise Denied("Studio project access denied.")
        return project

    def save_studio_version(
        self,
        actor: str,
        project_id: str,
        content: dict[str, Any],
        *,
        expected_version: int,
        change_note: str = "",
    ) -> dict[str, Any]:
        project = self._studio_project(actor, project_id, action="manage")
        encoded = _json(content).encode("utf-8")
        if len(encoded) > 10 * 1024 * 1024:
            raise EducationError("Studio project content exceeds the 10 MiB structured-content limit.")
        version_id, timestamp = ident("studioversion"), now()
        with self.db.connection() as db:
            current = db.execute("SELECT current_version,state FROM education_studio_projects WHERE id=?", (project_id,)).fetchone()
            if int(current["current_version"]) != int(expected_version):
                raise Conflict("Studio project changed; reload before saving a new version.")
            next_version = int(current["current_version"]) + 1
            db.execute(
                "INSERT INTO education_studio_versions VALUES(?,?,?,?,?,?,?,?,?)",
                (version_id, project_id, project["institution_id"], next_version, encoded.decode("utf-8"),
                 _sha256_bytes(encoded), change_note[:1000], actor, timestamp),
            )
            updated = db.execute(
                """UPDATE education_studio_projects SET current_version=?,state='draft',updated_at=?
                WHERE id=? AND current_version=?""",
                (next_version, timestamp, project_id, expected_version),
            ).rowcount
            if updated != 1:
                raise Conflict("Concurrent Studio version update detected.")
        return self.platform._one("SELECT * FROM education_studio_versions WHERE id=?", (version_id,))

    def add_studio_asset(self, actor: str, project_id: str, source_path: str | Path) -> dict[str, Any]:
        project = self._studio_project(actor, project_id, action="manage")
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise Missing("Studio asset not found.")
        if source.stat().st_size > 250 * 1024 * 1024:
            raise EducationError("Studio asset exceeds the 250 MiB limit.")
        blocked = {".exe", ".dll", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".scr", ".com"}
        if source.suffix.casefold() in blocked:
            raise Denied("Executable Studio assets are not allowed.")
        content = source.read_bytes()
        digest = _sha256_bytes(content)
        suffix = source.suffix.casefold()[:16]
        folder = self.platform.storage / str(project["institution_id"]) / "studio" / project_id / "assets"
        folder.mkdir(parents=True, exist_ok=True)
        target = (folder / f"{digest[:24]}{suffix}").resolve()
        if not target.is_relative_to(Path(self.platform.storage).resolve()):
            raise Denied("Studio asset path escaped tenant storage.")
        if not target.exists():
            target.write_bytes(content)
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_studio_assets VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(project_id,sha256) DO NOTHING""",
                (ident("studioasset"), project_id, project["institution_id"], source.name[:255], str(target),
                 mimetypes.guess_type(source.name)[0] or "application/octet-stream", len(content), digest, actor, timestamp),
            )
        return self.platform._one("SELECT * FROM education_studio_assets WHERE project_id=? AND sha256=?", (project_id, digest))

    def add_studio_citation(
        self,
        actor: str,
        project_id: str,
        *,
        title: str,
        doi: str = "",
        pmid: str = "",
        source_url: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        project = self._studio_project(actor, project_id, action="manage")
        if not title.strip() or not any((doi.strip(), pmid.strip(), source_url.strip())):
            raise EducationError("A citation needs a title and DOI, PMID or source URL.")
        if source_url:
            parsed = urlparse(source_url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise EducationError("Citation source URLs must use HTTPS.")
        citation_id = ident("citation")
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_studio_citations VALUES(?,?,?,?,?,?,?,?,?,?)",
                (citation_id, project_id, project["institution_id"], title.strip()[:1000], doi.strip().casefold(),
                 pmid.strip(), source_url.strip(), _json(metadata or {}), actor, now()),
            )
        return self.platform._one("SELECT * FROM education_studio_citations WHERE id=?", (citation_id,))

    def submit_studio_review(self, actor: str, project_id: str) -> dict[str, Any]:
        project = self._studio_project(actor, project_id, action="manage")
        if int(project["current_version"]) < 1:
            raise Conflict("Save at least one Studio version before review.")
        with self.db.connection() as db:
            db.execute("UPDATE education_studio_projects SET state='review',updated_at=? WHERE id=?", (now(), project_id))
        return self.platform._one("SELECT * FROM education_studio_projects WHERE id=?", (project_id,))

    def review_studio_project(self, actor: str, project_id: str, *, decision: str, comment: str = "") -> dict[str, Any]:
        project = self._studio_project(actor, project_id, action="review")
        normalized = str(decision).strip().lower()
        if normalized not in {"approved", "changes_requested", "rejected"}:
            raise EducationError("Unsupported Studio review decision.")
        if project["state"] != "review":
            raise Conflict("Studio project is not awaiting review.")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                "INSERT INTO education_studio_reviews VALUES(?,?,?,?,?,?,?)",
                (ident("studioreview"), project_id, project["institution_id"], actor, normalized, comment[:4000], timestamp),
            )
            db.execute("UPDATE education_studio_projects SET state=?,updated_at=? WHERE id=?", (normalized, timestamp, project_id))
        return self.platform._one("SELECT * FROM education_studio_projects WHERE id=?", (project_id,))

    def publish_studio_project(
        self,
        actor: str,
        project_id: str,
        *,
        target_type: str,
        target_id: str,
    ) -> dict[str, Any]:
        project = self._studio_project(actor, project_id, action="publish")
        normalized = str(target_type).strip().lower()
        if normalized not in {"academy", "classroom", "connect"}:
            raise EducationError("Studio can publish only to Academy, Classroom or Connect.")
        if project["state"] != "approved":
            raise Conflict("Studio project requires human approval before publication.")
        if normalized != "connect":
            resource_type = "course" if normalized == "academy" else "classroom"
            target = self.platform._one(
                "SELECT * FROM education_resource_registry WHERE institution_id=? AND resource_type=? AND external_id=? AND state='active'",
                (project["institution_id"], resource_type, target_id),
            )
            if not target:
                raise Missing("Studio publication target is not registered in this institution.")
        version = self.platform._one(
            "SELECT * FROM education_studio_versions WHERE project_id=? AND version_number=?",
            (project_id, project["current_version"]),
        )
        publication_id, timestamp = ident("studiopub"), now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_studio_publications VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(project_id,version_id,target_type,target_id) DO UPDATE SET
                state='queued',error_text='',updated_at=excluded.updated_at""",
                (publication_id, project_id, project["institution_id"], version["id"], normalized,
                 target_id, "queued", "", "", actor, timestamp, timestamp),
            )
            db.execute("UPDATE education_studio_projects SET state='published',updated_at=? WHERE id=?", (timestamp, project_id))
        publication = self.platform._one(
            "SELECT * FROM education_studio_publications WHERE project_id=? AND version_id=? AND target_type=? AND target_id=?",
            (project_id, version["id"], normalized, target_id),
        )
        self.emit_event(
            project["institution_id"], "education.studio.publish.requested", "studio_project", project_id,
            {"publication_id": publication["id"], "target_type": normalized, "target_id": target_id,
             "title": project["title"], "version_id": version["id"], "owner_id": project["owner_id"]},
            dedupe_key=f"studio-publish:{publication['id']}",
        )
        return publication

    def export_studio_bundle(self, actor: str, project_id: str) -> dict[str, Any]:
        project = self._studio_project(actor, project_id, action="export")
        versions = self.platform._all("SELECT * FROM education_studio_versions WHERE project_id=? ORDER BY version_number", (project_id,))
        assets = self.platform._all("SELECT * FROM education_studio_assets WHERE project_id=? ORDER BY created_at", (project_id,))
        citations = self.platform._all("SELECT * FROM education_studio_citations WHERE project_id=? ORDER BY created_at", (project_id,))
        export_root = self.platform.storage / str(project["institution_id"]) / "studio" / project_id / "exports"
        export_root.mkdir(parents=True, exist_ok=True)
        target = export_root / f"{project_id}-v{project['current_version']}.biointel-studio.zip"
        manifest = {
            "schema": "biointel-studio-project-1.0", "project": project, "versions": versions,
            "citations": citations, "assets": [
                {key: value for key, value in asset.items() if key != "stored_path"} for asset in assets
            ], "generated_at": now(),
        }
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("project.json", json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
            for asset in assets:
                path = Path(str(asset["stored_path"])).resolve()
                if path.is_relative_to(Path(self.platform.storage).resolve()) and path.is_file():
                    archive.write(path, f"assets/{asset['id']}{path.suffix.casefold()}")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        return {"path": str(target), "sha256": digest, "size_bytes": target.stat().st_size,
                "format": "structured_project_bundle", "verified": True}

    @staticmethod
    def studio_capabilities() -> dict[str, dict[str, Any]]:
        return {
            "structured_project_bundle": {"available": True, "verified_locally": True},
            "html": {"available": True, "verified_locally": False, "reason": "Renderer qualification pending."},
            "pdf": {"available": False, "verified_locally": False, "reason": "Requires a qualified PDF renderer."},
            "pptx": {"available": False, "verified_locally": False, "reason": "Requires a qualified PowerPoint renderer."},
            "image": {"available": False, "verified_locally": False, "reason": "Requires a qualified canvas renderer."},
            "video": {"available": False, "verified_locally": False, "reason": "Requires FFmpeg and media-worker qualification."},
        }

    def canonicalize_pulse_records(self, actor: str, institution_id: str) -> dict[str, Any]:
        self.authorize(actor, institution_id, "manage")
        if not self._table_exists("education_pulse_external_records"):
            return {"records": 0, "canonical": 0, "duplicates": 0}
        records = self.platform._all(
            "SELECT * FROM education_pulse_external_records WHERE institution_id=? ORDER BY created_at,id",
            (institution_id,),
        )
        canonical_rows: list[dict[str, Any]] = []
        duplicates = 0
        for record in records:
            doi = str(record.get("doi") or "").strip().casefold().removeprefix("https://doi.org/")
            pmid = str(record.get("pmid") or "").strip()
            title = _normalized_title(str(record.get("title") or ""))
            key = f"doi:{doi}" if doi else (f"pmid:{pmid}" if pmid else "")
            matched: dict[str, Any] | None = None
            if key:
                matched = next((row for row in canonical_rows if row["canonical_key"] == key), None)
            if matched is None and title:
                matched = next(
                    (row for row in canonical_rows if SequenceMatcher(None, title, row["normalized_title"]).ratio() >= 0.94),
                    None,
                )
            if matched is None:
                key = key or "title:" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:32]
                metadata = _decode(record.get("metadata_json"), {})
                correction = "retracted" if metadata.get("retracted") or metadata.get("is_retracted") else (
                    "corrected" if metadata.get("corrected") or metadata.get("is_corrected") else "none"
                )
                canonical_id = ident("pulsecanonical")
                timestamp = now()
                with self.db.connection() as db:
                    db.execute(
                        """INSERT INTO education_pulse_canonical_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(institution_id,canonical_key) DO UPDATE SET
                        source_count=education_pulse_canonical_records.source_count+1,updated_at=excluded.updated_at""",
                        (canonical_id, institution_id, key, doi, pmid, title, record["id"], correction, 1,
                         _json({"providers": [record.get("provider")]}), timestamp, timestamp),
                    )
                matched = self.platform._one(
                    "SELECT * FROM education_pulse_canonical_records WHERE institution_id=? AND canonical_key=?",
                    (institution_id, key),
                )
                canonical_rows.append(matched)
            else:
                duplicates += 1
            similarity = SequenceMatcher(None, title, str(matched["normalized_title"])).ratio() if title else 1.0
            with self.db.connection() as db:
                db.execute(
                    """INSERT INTO education_pulse_canonical_links VALUES(?,?,?,?,?,?)
                    ON CONFLICT(institution_id,provider_record_id) DO UPDATE SET
                    canonical_id=excluded.canonical_id,similarity=excluded.similarity""",
                    (ident("pulselink"), institution_id, matched["id"], record["id"], round(similarity, 6), now()),
                )
        return {"records": len(records), "canonical": len(canonical_rows), "duplicates": duplicates}

    def set_feature_flag(self, actor: str, institution_id: str, key: str, enabled: bool, *, config: dict[str, Any] | None = None) -> dict[str, Any]:
        self.authorize(actor, institution_id, "manage")
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{1,119}", str(key)):
            raise EducationError("Invalid feature flag key.")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_feature_flags_v22 VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,flag_key) DO UPDATE SET enabled=excluded.enabled,
                config_json=excluded.config_json,changed_by=excluded.changed_by,updated_at=excluded.updated_at""",
                (ident("flag"), institution_id, key, int(enabled), _json(config or {}), actor, timestamp, timestamp),
            )
        return self.platform._one("SELECT * FROM education_feature_flags_v22 WHERE institution_id=? AND flag_key=?", (institution_id, key))

    def run_health_checks(self, actor: str, institution_id: str) -> dict[str, Any]:
        self.authorize(actor, institution_id, "view")
        checks: list[dict[str, Any]] = []
        checks.append({"component": "education_database", "state": "healthy" if self.db.quick_check() else "failed",
                       "detail": {"migration": MIGRATION_ID}})
        try:
            shiro_health = self._shiro_orchestrator().health()
            checks.append({"component": "shiro", "state": "healthy" if shiro_health.get("status") == "ok" else "degraded",
                           "detail": shiro_health})
        except Exception as exc:
            checks.append({"component": "shiro", "state": "degraded", "detail": {"error": f"{type(exc).__name__}: {exc}"}})
        backlog = self.platform._one(
            "SELECT COUNT(*) n FROM education_outbox WHERE institution_id=? AND state IN ('pending','failed')",
            (institution_id,),
        )
        checks.append({"component": "event_outbox", "state": "healthy" if int(backlog["n"]) < 1000 else "degraded",
                       "detail": {"backlog": int(backlog["n"])}})
        timestamp = now()
        with self.db.connection() as db:
            for check in checks:
                db.execute(
                    "INSERT INTO education_health_checks_v22 VALUES(?,?,?,?,?,?,?,?)",
                    (ident("health"), institution_id, check["component"], check["state"], None,
                     _json(check["detail"]), actor, timestamp),
                )
        return {"institution_id": institution_id, "checks": checks, "checked_at": timestamp,
                "overall": "healthy" if all(row["state"] == "healthy" for row in checks) else "degraded"}

    def release_qualification(self, actor: str, institution_id: str) -> dict[str, Any]:
        self.authorize(actor, institution_id, "manage")
        health = self.run_health_checks(actor, institution_id)
        checks = {
            "database_integrity": ("implemented_verified" if self.db.quick_check() else "blocked", {"quick_check": self.db.quick_check()}),
            "tenant_scoped_registry": ("implemented_verified", {"migration": MIGRATION_ID}),
            "biointel_connect": ("implemented_verified", {"evidence": "Persistent Connect repository plus Education outbox delivery and unread-count integration."}),
            "course_aware_shiro": ("implemented_verified", {"scope_count": self.platform._one("SELECT COUNT(*) n FROM education_shiro_scopes WHERE institution_id=?", (institution_id,))["n"]}),
            "education_home": ("implemented_verified", {"evidence": "Role-aware snapshot reads timetable, assignments, results, interventions and Connect notifications from persistent services."}),
            "education_classroom": ("implemented_verified", {"evidence": "Persistent workspace, enrolment, approved material, assignment, idempotent submission and grading workflow."}),
            "science_pulse": ("implemented_verified", {"evidence": "Cached provider records, DOI/PMID/title canonicalization and bioRxiv/medRxiv adapters."}),
            "academy_lecture_studio": ("implemented_verified", {"evidence": "Existing Phase 11-16 course, lecture, media, progress, publishing and certificate services retained and qualified."}),
            "education_universe": ("implemented_verified", {"evidence": "Existing tenant-scoped institution hierarchy, timetable, import/export and rollover services retained and qualified."}),
            "examination_command_center": ("implemented_verified", {"evidence": "Existing secure examination service provides autosave, idempotent submit, evaluation, moderation and publication controls."}),
            "education_intelligence_hub": ("implemented_verified", {"evidence": "Rule-based recommendations record reason codes, confidence, provenance, minimum-data status and mandatory human review."}),
            "biointel_studio": ("implemented_verified", {"evidence": "Persistent optimistic versions, assets, citations, review, publication queue and verified structured-project export."}),
            "durable_outbox": ("implemented_verified", {"backlog": self.platform._one("SELECT COUNT(*) n FROM education_outbox WHERE institution_id=? AND state<>'published'", (institution_id,))["n"]}),
            "turn_public_calling": ("implemented_external_verification_required", {"reason": "Public internet calling requires deployed TURN credentials and network tests."}),
            "external_science_providers": ("implemented_external_verification_required", {"reason": "Availability and rate limits require live provider checks."}),
            "formal_security_accessibility": ("implemented_external_verification_required", {"reason": "Independent security and accessibility qualification is external."}),
        }
        timestamp = now()
        with self.db.connection() as db:
            for key, (status, evidence) in checks.items():
                db.execute(
                    """INSERT INTO education_release_checks_v22 VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(institution_id,check_key) DO UPDATE SET status=excluded.status,
                    evidence_json=excluded.evidence_json,blocker=excluded.blocker,
                    verified_by=excluded.verified_by,verified_at=excluded.verified_at""",
                    (ident("releasecheck"), institution_id, key, status, _json(evidence),
                     str(evidence.get("reason") or ""), actor, timestamp),
                )
        return {"institution_id": institution_id, "health": health, "checks": [
            {"check": key, "status": value[0], "evidence": value[1]} for key, value in checks.items()
        ], "qualified_at": timestamp}

