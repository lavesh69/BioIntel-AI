from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .platform import ADMIN, STUDENT, TEACHER, Denied, EducationError, ident, now

MIGRATION_ID = "education_phase3_granular_rbac_v1"

PERMISSIONS: tuple[str, ...] = (
    "education.dashboard.view",
    "classroom.view",
    "classroom.manage",
    "academy.view",
    "academy.manage",
    "pulse.view",
    "pulse.manage",
    "universe.view",
    "universe.manage",
    "exam.view",
    "exam.create",
    "exam.publish",
    "exam.monitor",
    "exam.take",
    "exam.grade",
    "result.publish",
    "rbac.manage",
    "learning.view",
    "learning.manage",
    "timetable.manage",
    "attendance.manage",
    "notifications.manage",
    "reports.view",
    "shiro.tutor",
    "shiro.manage",
    "institution.manage",
    "database.manage",
    "campus.manage",
    "identity.manage",
    "storage.manage",
    "storage.write",
    "backup.manage",
    "jobs.enqueue",
    "integrations.manage",
    "imports.manage",
    "governance.reports",
)

DEFAULT_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "platform_administrator": set(PERMISSIONS),
    "institution_administrator": set(PERMISSIONS),
    "principal": set(PERMISSIONS),
    "dean": set(PERMISSIONS),
    "registrar": set(PERMISSIONS),
    "department_head": set(PERMISSIONS),
    "examination_controller": {
        "education.dashboard.view", "classroom.view", "exam.view", "exam.create",
        "exam.publish", "exam.monitor", "exam.grade", "result.publish",
    },
    "subject_teacher": {
        "education.dashboard.view", "classroom.view", "classroom.manage",
        "academy.view", "academy.manage", "pulse.view", "universe.view",
        "exam.view", "exam.create", "exam.monitor", "exam.grade",
    },
    "class_teacher": {
        "education.dashboard.view", "classroom.view", "classroom.manage",
        "academy.view", "pulse.view", "universe.view", "exam.view",
        "exam.create", "exam.monitor", "exam.grade",
    },
    "lecturer": {
        "education.dashboard.view", "classroom.view", "classroom.manage",
        "academy.view", "academy.manage", "pulse.view", "universe.view",
        "exam.view", "exam.create", "exam.monitor", "exam.grade",
    },
    "assistant_professor": {
        "education.dashboard.view", "classroom.view", "classroom.manage",
        "academy.view", "academy.manage", "pulse.view", "universe.view",
        "exam.view", "exam.create", "exam.monitor", "exam.grade",
    },
    "professor": {
        "education.dashboard.view", "classroom.view", "classroom.manage",
        "academy.view", "academy.manage", "pulse.view", "universe.view",
        "exam.view", "exam.create", "exam.monitor", "exam.grade",
    },
    "teaching_assistant": {
        "education.dashboard.view", "classroom.view", "classroom.manage",
        "academy.view", "pulse.view", "universe.view", "exam.view", "exam.monitor",
    },
    "laboratory_instructor": {
        "education.dashboard.view", "classroom.view", "classroom.manage",
        "academy.view", "universe.view", "universe.manage", "exam.view",
        "exam.create", "exam.monitor", "exam.grade",
    },
    "academic_mentor": {
        "education.dashboard.view", "classroom.view", "academy.view",
        "pulse.view", "universe.view", "exam.view", "exam.monitor",
    },
    "class_coordinator": {
        "education.dashboard.view", "classroom.view", "classroom.manage",
        "academy.view", "pulse.view", "universe.view", "exam.view", "exam.monitor",
    },
    "school_student": {
        "education.dashboard.view", "classroom.view", "academy.view", "pulse.view",
        "universe.view", "exam.view", "exam.take",
    },
    "college_student": {
        "education.dashboard.view", "classroom.view", "academy.view", "pulse.view",
        "universe.view", "exam.view", "exam.take",
    },
    "university_student": {
        "education.dashboard.view", "classroom.view", "academy.view", "pulse.view",
        "universe.view", "exam.view", "exam.take",
    },
    "parent_guardian": {"education.dashboard.view", "classroom.view", "exam.view"},
    "guest_educator": {"education.dashboard.view", "academy.view", "pulse.view", "universe.view"},
    "research_mentor": {"education.dashboard.view", "academy.view", "pulse.view", "universe.view"},
    "career_counsellor": {"education.dashboard.view", "pulse.view", "universe.view"},
    "librarian": {"education.dashboard.view", "academy.view", "pulse.view", "universe.view"},
    "laboratory_manager": {"education.dashboard.view", "classroom.view", "universe.view", "universe.manage"},
    "content_moderator": {"education.dashboard.view", "academy.view", "academy.manage", "pulse.view", "pulse.manage"},
}

# Phase 4 extends role defaults without weakening explicit institution deny precedence.
for _role, _permissions in {
    "platform_administrator": {"learning.view", "learning.manage", "timetable.manage", "attendance.manage", "notifications.manage", "reports.view", "shiro.tutor", "shiro.manage"},
    "institution_administrator": {"learning.view", "learning.manage", "timetable.manage", "attendance.manage", "notifications.manage", "reports.view", "shiro.tutor", "shiro.manage"},
    "principal": {"learning.view", "learning.manage", "timetable.manage", "attendance.manage", "notifications.manage", "reports.view", "shiro.tutor", "shiro.manage"},
    "dean": {"learning.view", "learning.manage", "timetable.manage", "attendance.manage", "notifications.manage", "reports.view", "shiro.tutor", "shiro.manage"},
    "registrar": {"learning.view", "timetable.manage", "attendance.manage", "notifications.manage", "reports.view", "shiro.tutor"},
    "department_head": {"learning.view", "learning.manage", "timetable.manage", "attendance.manage", "notifications.manage", "reports.view", "shiro.tutor", "shiro.manage"},
    "examination_controller": {"learning.view", "notifications.manage", "reports.view", "shiro.tutor"},
    "subject_teacher": {"learning.view", "learning.manage", "timetable.manage", "attendance.manage", "notifications.manage", "reports.view", "shiro.tutor", "shiro.manage"},
    "class_teacher": {"learning.view", "learning.manage", "timetable.manage", "attendance.manage", "notifications.manage", "reports.view", "shiro.tutor", "shiro.manage"},
    "lecturer": {"learning.view", "learning.manage", "timetable.manage", "attendance.manage", "notifications.manage", "reports.view", "shiro.tutor", "shiro.manage"},
    "assistant_professor": {"learning.view", "learning.manage", "timetable.manage", "attendance.manage", "notifications.manage", "reports.view", "shiro.tutor", "shiro.manage"},
    "professor": {"learning.view", "learning.manage", "timetable.manage", "attendance.manage", "notifications.manage", "reports.view", "shiro.tutor", "shiro.manage"},
    "teaching_assistant": {"learning.view", "attendance.manage", "reports.view", "shiro.tutor"},
    "laboratory_instructor": {"learning.view", "learning.manage", "attendance.manage", "reports.view", "shiro.tutor", "shiro.manage"},
    "academic_mentor": {"learning.view", "reports.view", "shiro.tutor"},
    "class_coordinator": {"learning.view", "timetable.manage", "attendance.manage", "notifications.manage", "reports.view", "shiro.tutor"},
    "school_student": {"learning.view", "reports.view", "shiro.tutor"},
    "college_student": {"learning.view", "reports.view", "shiro.tutor"},
    "university_student": {"learning.view", "reports.view", "shiro.tutor"},
    "parent_guardian": {"learning.view", "reports.view"},
    "research_mentor": {"learning.view", "reports.view", "shiro.tutor"},
    "career_counsellor": {"learning.view", "reports.view"},
    "librarian": {"learning.view", "reports.view", "shiro.tutor", "shiro.manage"},
}.items():
    DEFAULT_ROLE_PERMISSIONS.setdefault(_role, set()).update(_permissions)


# Phase 5 institution-platform permissions. Explicit deny continues to win.
for _role, _permissions in {
    "platform_administrator": {"institution.manage", "database.manage", "campus.manage", "identity.manage", "storage.manage", "storage.write", "backup.manage", "jobs.enqueue", "integrations.manage", "imports.manage", "governance.reports"},
    "institution_administrator": {"institution.manage", "database.manage", "campus.manage", "identity.manage", "storage.manage", "storage.write", "backup.manage", "jobs.enqueue", "integrations.manage", "imports.manage", "governance.reports"},
    "principal": {"institution.manage", "database.manage", "campus.manage", "identity.manage", "storage.manage", "storage.write", "backup.manage", "jobs.enqueue", "integrations.manage", "imports.manage", "governance.reports"},
    "dean": {"institution.manage", "campus.manage", "storage.write", "jobs.enqueue", "integrations.manage", "imports.manage", "governance.reports"},
    "registrar": {"campus.manage", "storage.write", "jobs.enqueue", "imports.manage", "governance.reports"},
    "department_head": {"storage.write", "jobs.enqueue", "imports.manage", "governance.reports"},
    "examination_controller": {"storage.write", "jobs.enqueue", "governance.reports"},
    "subject_teacher": {"storage.write", "jobs.enqueue", "governance.reports"},
    "class_teacher": {"storage.write", "jobs.enqueue", "governance.reports"},
    "lecturer": {"storage.write", "jobs.enqueue", "governance.reports"},
    "assistant_professor": {"storage.write", "jobs.enqueue", "governance.reports"},
    "professor": {"storage.write", "jobs.enqueue", "governance.reports"},
    "laboratory_instructor": {"storage.write", "jobs.enqueue", "governance.reports"},
    "librarian": {"storage.write", "jobs.enqueue", "governance.reports"},
}.items():
    DEFAULT_ROLE_PERMISSIONS.setdefault(_role, set()).update(_permissions)


SCHEMA = r"""
CREATE TABLE IF NOT EXISTS education_permission_overrides(
 id TEXT PRIMARY KEY,
 institution_id TEXT NOT NULL,
 role TEXT NOT NULL,
 permission TEXT NOT NULL,
 effect TEXT NOT NULL CHECK(effect IN ('allow','deny')),
 changed_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(institution_id,role,permission)
);
CREATE INDEX IF NOT EXISTS idx_education_permission_overrides_tenant
 ON education_permission_overrides(institution_id,role,permission);
INSERT OR IGNORE INTO education_migrations(id,applied_at)
 VALUES('education_phase3_granular_rbac_v1',datetime('now'));
"""


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    permission: str
    roles: tuple[str, ...]
    source: str


class PermissionService:
    """Institution-scoped permission resolver with explicit deny precedence."""

    def __init__(self, platform):
        self.platform = platform
        self.db = platform.db
        self.migrate()

    def migrate(self) -> str:
        with self.db.connection() as db:
            db.executescript(SCHEMA)
        return MIGRATION_ID

    def roles(self, actor: str, institution_id: str) -> set[str]:
        return {str(row["role"]) for row in self.platform._require(actor, institution_id)}

    def decision(self, actor: str, institution_id: str, permission: str) -> PermissionDecision:
        if permission not in PERMISSIONS:
            raise EducationError(f"Unknown permission: {permission}")
        roles = self.roles(actor, institution_id)
        placeholders = ",".join("?" for _ in roles)
        overrides = []
        if roles:
            overrides = self.platform._all(
                f"SELECT role,effect FROM education_permission_overrides "
                f"WHERE institution_id=? AND permission=? AND role IN ({placeholders})",
                (institution_id, permission, *sorted(roles)),
            )
        if any(row["effect"] == "deny" for row in overrides):
            return PermissionDecision(False, permission, tuple(sorted(roles)), "institution_deny")
        if any(row["effect"] == "allow" for row in overrides):
            return PermissionDecision(True, permission, tuple(sorted(roles)), "institution_allow")
        allowed = any(permission in DEFAULT_ROLE_PERMISSIONS.get(role, set()) for role in roles)
        return PermissionDecision(allowed, permission, tuple(sorted(roles)), "role_default")

    def has(self, actor: str, institution_id: str, permission: str) -> bool:
        return self.decision(actor, institution_id, permission).allowed

    def require(self, actor: str, institution_id: str, permission: str) -> PermissionDecision:
        decision = self.decision(actor, institution_id, permission)
        if not decision.allowed:
            raise Denied(f"Permission denied: {permission}")
        return decision

    def set_override(
        self,
        actor: str,
        institution_id: str,
        role: str,
        permission: str,
        effect: str,
    ) -> dict:
        self.require(actor, institution_id, "rbac.manage")
        if permission not in PERMISSIONS:
            raise EducationError("Unsupported permission.")
        if role not in DEFAULT_ROLE_PERMISSIONS:
            raise EducationError("Unsupported role.")
        normalized = str(effect).strip().lower()
        if normalized not in {"allow", "deny"}:
            raise EducationError("Permission effect must be allow or deny.")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_permission_overrides
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,role,permission) DO UPDATE SET
                effect=excluded.effect,changed_by=excluded.changed_by,updated_at=excluded.updated_at""",
                (ident("perm"), institution_id, role, permission, normalized, actor, timestamp, timestamp),
            )
        self.platform._audit(
            actor,
            "permission_override_saved",
            "role",
            role,
            institution_id,
            {"permission": permission, "effect": normalized},
        )
        return self.platform._one(
            "SELECT * FROM education_permission_overrides WHERE institution_id=? AND role=? AND permission=?",
            (institution_id, role, permission),
        )

    def clear_override(self, actor: str, institution_id: str, role: str, permission: str) -> None:
        self.require(actor, institution_id, "rbac.manage")
        with self.db.connection() as db:
            db.execute(
                "DELETE FROM education_permission_overrides WHERE institution_id=? AND role=? AND permission=?",
                (institution_id, role, permission),
            )
        self.platform._audit(
            actor,
            "permission_override_cleared",
            "role",
            role,
            institution_id,
            {"permission": permission},
        )

    def matrix(self, actor: str, institution_id: str, roles: Iterable[str] | None = None) -> list[dict]:
        self.require(actor, institution_id, "rbac.manage")
        selected = list(roles or DEFAULT_ROLE_PERMISSIONS)
        overrides = self.platform._all(
            "SELECT role,permission,effect FROM education_permission_overrides WHERE institution_id=?",
            (institution_id,),
        )
        override_map = {(row["role"], row["permission"]): row["effect"] for row in overrides}
        rows: list[dict] = []
        for role in selected:
            for permission in PERMISSIONS:
                effect = override_map.get((role, permission))
                default = permission in DEFAULT_ROLE_PERMISSIONS.get(role, set())
                rows.append(
                    {
                        "role": role,
                        "permission": permission,
                        "default": default,
                        "override": effect or "",
                        "effective": False if effect == "deny" else True if effect == "allow" else default,
                    }
                )
        return rows
