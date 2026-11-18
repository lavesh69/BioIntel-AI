from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import sqlite3
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from .core import (
    LiveWorkspaceStore,
    PermissionDenied,
    RevisionConflict,
    _clean_text,
    _decode,
    _hash_secret,
    _json,
    _safe_id,
    _verify_secret,
    load_host_config,
    parse_utc,
    utc_now,
    utc_text,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bounded_json(value: Any, *, maximum_bytes: int = 256_000, field: str = "payload") -> str:
    encoded = _json(value)
    if len(encoded.encode("utf-8")) > maximum_bytes:
        raise ValueError(f"{field} is larger than the supported {maximum_bytes} byte safety limit.")
    return encoded


class LiveWorkspaceAdvancedStore(LiveWorkspaceStore):
    """Peak-potential local-first collaboration extensions.

    The advanced layer stores only collaboration metadata, annotations, safe aliases,
    provenance hashes and project coordination records. Raw scientific files remain in
    their original BioIntel project stores and are never broadcast through presence.
    """

    TASK_STATUSES = {"backlog", "assigned", "in_progress", "blocked", "review", "done", "cancelled"}
    ANNOTATION_STATUSES = {"draft", "accepted", "rejected", "needs_review", "archived"}
    SESSION_STATUSES = {"active", "paused", "ended"}
    USER_STATUSES = {"available", "busy", "reviewing", "running", "do_not_disturb", "away", "offline"}
    INVITE_ROLES = {"guest", "viewer", "reviewer", "researcher", "admin"}

    def _initialize(self) -> None:
        super()._initialize()
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS live_workspace_invites(
                    invite_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL,
                    max_uses INTEGER NOT NULL DEFAULT 1 CHECK(max_uses >= 1 AND max_uses <= 100),
                    use_count INTEGER NOT NULL DEFAULT 0 CHECK(use_count >= 0),
                    revoked_at_utc TEXT,
                    FOREIGN KEY(workspace_id,created_by) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_live_invites_workspace ON live_workspace_invites(workspace_id,expires_at_utc,revoked_at_utc);

                CREATE TABLE IF NOT EXISTS live_member_profiles(
                    workspace_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    availability TEXT NOT NULL DEFAULT 'available',
                    status_message TEXT NOT NULL DEFAULT '',
                    presence_visibility TEXT NOT NULL DEFAULT 'workspace',
                    notification_mode TEXT NOT NULL DEFAULT 'all',
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY(workspace_id,user_id),
                    FOREIGN KEY(workspace_id,user_id) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS live_member_permissions(
                    workspace_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    allowed_categories_json TEXT NOT NULL DEFAULT '[]',
                    allowed_modules_json TEXT NOT NULL DEFAULT '[]',
                    allowed_projects_json TEXT NOT NULL DEFAULT '[]',
                    updated_by TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY(workspace_id,user_id),
                    FOREIGN KEY(workspace_id,user_id) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS live_account_sessions(
                    account_session_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    client_label TEXT NOT NULL DEFAULT '',
                    auth_source TEXT NOT NULL DEFAULT '',
                    created_at_utc TEXT NOT NULL,
                    last_seen_at_utc TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL,
                    revoked_at_utc TEXT,
                    FOREIGN KEY(workspace_id,user_id) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_live_account_sessions ON live_account_sessions(workspace_id,user_id,expires_at_utc,revoked_at_utc);

                CREATE TABLE IF NOT EXISTS live_comment_threads(
                    comment_id TEXT PRIMARY KEY,
                    parent_comment_id TEXT NOT NULL DEFAULT '',
                    resolved_at_utc TEXT,
                    resolved_by TEXT NOT NULL DEFAULT '',
                    deleted_at_utc TEXT,
                    deleted_by TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(comment_id) REFERENCES live_comments(comment_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS live_comment_revisions(
                    revision_id TEXT PRIMARY KEY,
                    comment_id TEXT NOT NULL,
                    body TEXT NOT NULL,
                    edited_by TEXT NOT NULL,
                    edited_at_utc TEXT NOT NULL,
                    FOREIGN KEY(comment_id) REFERENCES live_comments(comment_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_live_comment_revisions ON live_comment_revisions(comment_id,edited_at_utc DESC);

                CREATE TABLE IF NOT EXISTS live_tasks(
                    task_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT '',
                    resource_type TEXT NOT NULL DEFAULT '',
                    resource_id TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'normal',
                    assigned_to TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL,
                    due_at_utc TEXT,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    completed_at_utc TEXT,
                    deleted_at_utc TEXT,
                    FOREIGN KEY(workspace_id,created_by) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_live_tasks_workspace ON live_tasks(workspace_id,status,priority,updated_at_utc DESC);

                CREATE TABLE IF NOT EXISTS live_bookmarks(
                    bookmark_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    safe_reference TEXT NOT NULL,
                    source_name TEXT NOT NULL DEFAULT '',
                    evidence_level TEXT NOT NULL DEFAULT 'ungraded',
                    notes TEXT NOT NULL DEFAULT '',
                    added_by TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    last_checked_at_utc TEXT,
                    deleted_at_utc TEXT,
                    FOREIGN KEY(workspace_id,added_by) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_live_bookmarks_workspace ON live_bookmarks(workspace_id,kind,created_at_utc DESC);

                CREATE TABLE IF NOT EXISTS live_annotations(
                    annotation_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT '',
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    annotation_type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    confidence REAL,
                    geometry_json TEXT NOT NULL DEFAULT '{}',
                    attributes_json TEXT NOT NULL DEFAULT '{}',
                    created_by TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_by TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1,
                    deleted_at_utc TEXT,
                    FOREIGN KEY(workspace_id,created_by) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_live_annotations_record ON live_annotations(workspace_id,resource_type,resource_id,updated_at_utc DESC);
                CREATE TABLE IF NOT EXISTS live_annotation_revisions(
                    annotation_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    changed_by TEXT NOT NULL,
                    changed_at_utc TEXT NOT NULL,
                    PRIMARY KEY(annotation_id,revision),
                    FOREIGN KEY(annotation_id) REFERENCES live_annotations(annotation_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS live_project_links(
                    link_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    subject_alias TEXT NOT NULL DEFAULT '',
                    module_key TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    deleted_at_utc TEXT,
                    FOREIGN KEY(workspace_id,created_by) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_live_project_links ON live_project_links(workspace_id,project_id,subject_alias,module_key);

                CREATE TABLE IF NOT EXISTS live_timeline_events(
                    timeline_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT '',
                    subject_alias TEXT NOT NULL DEFAULT '',
                    event_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    safe_detail TEXT NOT NULL DEFAULT '',
                    occurred_at_utc TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    system_generated INTEGER NOT NULL DEFAULT 0 CHECK(system_generated IN (0,1)),
                    deleted_at_utc TEXT,
                    FOREIGN KEY(workspace_id,created_by) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_live_timeline ON live_timeline_events(workspace_id,project_id,subject_alias,occurred_at_utc DESC);

                CREATE TABLE IF NOT EXISTS live_collaboration_sessions(
                    collaboration_session_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    host_user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    sync_navigation INTEGER NOT NULL DEFAULT 1 CHECK(sync_navigation IN (0,1)),
                    page_key TEXT NOT NULL DEFAULT '',
                    page_title TEXT NOT NULL DEFAULT '',
                    resource_type TEXT NOT NULL DEFAULT '',
                    resource_id TEXT NOT NULL DEFAULT '',
                    cursor_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    ended_at_utc TEXT,
                    FOREIGN KEY(workspace_id,host_user_id) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS live_collaboration_participants(
                    collaboration_session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    joined_at_utc TEXT NOT NULL,
                    last_seen_at_utc TEXT NOT NULL,
                    follow_host INTEGER NOT NULL DEFAULT 1 CHECK(follow_host IN (0,1)),
                    PRIMARY KEY(collaboration_session_id,user_id),
                    FOREIGN KEY(collaboration_session_id) REFERENCES live_collaboration_sessions(collaboration_session_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS live_notification_preferences(
                    workspace_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    muted INTEGER NOT NULL DEFAULT 0 CHECK(muted IN (0,1)),
                    mention_only INTEGER NOT NULL DEFAULT 0 CHECK(mention_only IN (0,1)),
                    browser_notifications INTEGER NOT NULL DEFAULT 0 CHECK(browser_notifications IN (0,1)),
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY(workspace_id,user_id),
                    FOREIGN KEY(workspace_id,user_id) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS live_job_actions(
                    action_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'requested',
                    note TEXT NOT NULL DEFAULT '',
                    created_at_utc TEXT NOT NULL,
                    handled_at_utc TEXT,
                    FOREIGN KEY(workspace_id,job_id) REFERENCES live_shared_jobs(workspace_id,job_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_live_job_actions ON live_job_actions(workspace_id,job_id,created_at_utc DESC);

                CREATE TABLE IF NOT EXISTS live_offline_drafts(
                    draft_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    base_revision INTEGER NOT NULL DEFAULT 0,
                    draft_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    synced_at_utc TEXT,
                    FOREIGN KEY(workspace_id,user_id) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_live_offline_drafts ON live_offline_drafts(workspace_id,user_id,status,updated_at_utc DESC);

                CREATE TABLE IF NOT EXISTS live_deleted_items(
                    deleted_item_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    deleted_by TEXT NOT NULL,
                    deleted_at_utc TEXT NOT NULL,
                    restored_at_utc TEXT,
                    restored_by TEXT NOT NULL DEFAULT '',
                    UNIQUE(workspace_id,item_type,item_id,deleted_at_utc),
                    FOREIGN KEY(workspace_id,deleted_by) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_live_deleted_items ON live_deleted_items(workspace_id,restored_at_utc,deleted_at_utc DESC);

                CREATE TABLE IF NOT EXISTS live_workspace_backups(
                    backup_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    archive_sha256 TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    FOREIGN KEY(workspace_id,created_by) REFERENCES live_workspace_members(workspace_id,user_id) ON DELETE CASCADE
                );
                """
            )

    # --- workspace privacy and member state -------------------------------------------------
    def workspace_settings(self, workspace_id: str, *, actor_user_id: str) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        with self._connect() as connection:
            self._member(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"))
            row = connection.execute("SELECT settings_json FROM live_workspaces WHERE workspace_id=?", (workspace_id,)).fetchone()
        current = _decode(row["settings_json"] if row else "{}", {})
        defaults = {
            "private": True,
            "invite_only": True,
            "mask_record_titles": True,
            "presence_detail": "record_alias",
            "activity_detail": "standard",
            "external_web_access": False,
            "guest_access": False,
            "retention_days": 365,
        }
        return {**defaults, **(current if isinstance(current, dict) else {})}

    def update_workspace_settings(self, workspace_id: str, *, actor_user_id: str, settings: dict[str, Any]) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        allowed = {"private", "invite_only", "mask_record_titles", "presence_detail", "activity_detail", "external_web_access", "guest_access", "retention_days"}
        with self._connect() as connection:
            member = self._require(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"), self.ADMIN_ROLES)
            row = connection.execute("SELECT settings_json FROM live_workspaces WHERE workspace_id=?", (workspace_id,)).fetchone()
            decoded = _decode(row["settings_json"] if row else "{}", {})
            current = {
                "private": True,
                "invite_only": True,
                "mask_record_titles": True,
                "presence_detail": "record_alias",
                "activity_detail": "standard",
                "external_web_access": False,
                "guest_access": False,
                "retention_days": 365,
                **(decoded if isinstance(decoded, dict) else {}),
            }
            for key, value in settings.items():
                if key in allowed:
                    current[key] = value
            if current.get("presence_detail") not in {"module_only", "record_alias", "hidden"}:
                raise ValueError("presence_detail must be module_only, record_alias or hidden.")
            if current.get("activity_detail") not in {"minimal", "standard", "detailed"}:
                raise ValueError("activity_detail must be minimal, standard or detailed.")
            current["retention_days"] = min(max(int(current.get("retention_days", 365)), 7), 3650)
            connection.execute("UPDATE live_workspaces SET settings_json=?,updated_at_utc=? WHERE workspace_id=?", (_bounded_json(current, maximum_bytes=32_000, field="settings"), utc_text(), workspace_id))
            self._activity(connection, workspace_id, actor_user_id, str(member["display_name"]), "workspace_settings_updated", "Updated workspace privacy and collaboration settings")
        return self.workspace_settings(workspace_id, actor_user_id=actor_user_id)

    def update_member_profile(self, workspace_id: str, *, user_id: str, availability: str, status_message: str = "", presence_visibility: str = "workspace", notification_mode: str = "all") -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id"); user_id = _safe_id(user_id, field="user_id")
        availability = str(availability).strip().lower()
        if availability not in self.USER_STATUSES:
            raise ValueError("Unsupported availability status.")
        if presence_visibility not in {"workspace", "module_only", "hidden"}:
            raise ValueError("Unsupported presence visibility.")
        if notification_mode not in {"all", "mentions", "muted"}:
            raise ValueError("Unsupported notification mode.")
        now = utc_text()
        with self._connect() as connection:
            member = self._member(connection, workspace_id, user_id)
            connection.execute(
                """INSERT INTO live_member_profiles(workspace_id,user_id,availability,status_message,presence_visibility,notification_mode,updated_at_utc)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(workspace_id,user_id) DO UPDATE SET availability=excluded.availability,
                status_message=excluded.status_message,presence_visibility=excluded.presence_visibility,notification_mode=excluded.notification_mode,updated_at_utc=excluded.updated_at_utc""",
                (workspace_id, user_id, availability, _clean_text(status_message, maximum=140, field="status_message"), presence_visibility, notification_mode, now),
            )
            self._activity(connection, workspace_id, user_id, str(member["display_name"]), "member_status_updated", f"Status changed to {availability}")
        return self.get_member_profile(workspace_id, user_id=user_id)

    def get_member_profile(self, workspace_id: str, *, user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            member = self._member(connection, _safe_id(workspace_id, field="workspace_id"), _safe_id(user_id, field="user_id"))
            row = connection.execute("SELECT * FROM live_member_profiles WHERE workspace_id=? AND user_id=?", (workspace_id, user_id)).fetchone()
        return dict(row) if row else {"workspace_id": workspace_id, "user_id": user_id, "availability": "available", "status_message": "", "presence_visibility": "workspace", "notification_mode": "all", "display_name": str(member["display_name"])}

    def list_presence(self, workspace_id: str, *, actor_user_id: str, page_key: str = "", record_type: str = "", record_id: str = "") -> list[dict[str, Any]]:
        rows = super().list_presence(workspace_id, actor_user_id=actor_user_id, page_key=page_key, record_type=record_type, record_id=record_id)
        settings = self.workspace_settings(workspace_id, actor_user_id=actor_user_id)
        with self._connect() as connection:
            profiles = {str(row["user_id"]): dict(row) for row in connection.execute("SELECT * FROM live_member_profiles WHERE workspace_id=?", (_safe_id(workspace_id, field="workspace_id"),)).fetchall()}
        output: list[dict[str, Any]] = []
        for row in rows:
            profile = profiles.get(str(row.get("user_id")), {})
            visibility = str(profile.get("presence_visibility", "workspace"))
            if visibility == "hidden" and str(row.get("user_id")) != actor_user_id:
                continue
            item = dict(row)
            item["availability"] = profile.get("availability", "available")
            item["member_status_message"] = profile.get("status_message", "")
            detail = str(settings.get("presence_detail", "record_alias"))
            if visibility == "module_only" or detail == "module_only":
                item["record_type"] = ""; item["record_id"] = ""
            elif detail == "hidden" and str(row.get("user_id")) != actor_user_id:
                item["page_key"] = ""; item["page_title"] = ""; item["record_type"] = ""; item["record_id"] = ""
            output.append(item)
        return output

    def set_member_permissions(
        self,
        workspace_id: str,
        *,
        actor_user_id: str,
        target_user_id: str,
        allowed_categories: list[str] | None = None,
        allowed_modules: list[str] | None = None,
        allowed_projects: list[str] | None = None,
    ) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        actor_user_id = _safe_id(actor_user_id, field="actor_user_id")
        target_user_id = _safe_id(target_user_id, field="target_user_id")
        categories = sorted({_clean_text(item, maximum=80, field="category", allow_empty=False) for item in (allowed_categories or [])})
        modules = sorted({_safe_id(item, field="module") for item in (allowed_modules or [])})
        projects = sorted({_safe_id(item, field="project") for item in (allowed_projects or [])})
        with self._connect() as connection:
            actor = self._require(connection, workspace_id, actor_user_id, self.ADMIN_ROLES)
            self._member(connection, workspace_id, target_user_id)
            connection.execute(
                """INSERT INTO live_member_permissions(workspace_id,user_id,allowed_categories_json,allowed_modules_json,allowed_projects_json,updated_by,updated_at_utc)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(workspace_id,user_id) DO UPDATE SET
                allowed_categories_json=excluded.allowed_categories_json,allowed_modules_json=excluded.allowed_modules_json,
                allowed_projects_json=excluded.allowed_projects_json,updated_by=excluded.updated_by,updated_at_utc=excluded.updated_at_utc""",
                (workspace_id, target_user_id, _bounded_json(categories, maximum_bytes=16_000, field="categories"), _bounded_json(modules, maximum_bytes=32_000, field="modules"), _bounded_json(projects, maximum_bytes=32_000, field="projects"), actor_user_id, utc_text()),
            )
            self._activity(connection, workspace_id, actor_user_id, str(actor["display_name"]), "member_permissions_updated", "Updated member module/project access", object_type="member", object_id=target_user_id)
        return self.get_member_permissions(workspace_id, user_id=target_user_id, actor_user_id=actor_user_id)

    def get_member_permissions(self, workspace_id: str, *, user_id: str, actor_user_id: str | None = None) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        user_id = _safe_id(user_id, field="user_id")
        actor_user_id = _safe_id(actor_user_id or user_id, field="actor_user_id")
        with self._connect() as connection:
            actor = self._member(connection, workspace_id, actor_user_id)
            if actor_user_id != user_id and str(actor["role"]) not in self.ADMIN_ROLES:
                raise PermissionDenied("Admin role is required to inspect another member permissions.")
            self._member(connection, workspace_id, user_id)
            row = connection.execute("SELECT * FROM live_member_permissions WHERE workspace_id=? AND user_id=?", (workspace_id, user_id)).fetchone()
        if row is None:
            return {"workspace_id": workspace_id, "user_id": user_id, "allowed_categories": [], "allowed_modules": [], "allowed_projects": [], "unrestricted": True}
        return {
            "workspace_id": workspace_id,
            "user_id": user_id,
            "allowed_categories": _decode(row["allowed_categories_json"], []),
            "allowed_modules": _decode(row["allowed_modules_json"], []),
            "allowed_projects": _decode(row["allowed_projects_json"], []),
            "updated_by": str(row["updated_by"]),
            "updated_at_utc": str(row["updated_at_utc"]),
            "unrestricted": not any((_decode(row["allowed_categories_json"], []), _decode(row["allowed_modules_json"], []), _decode(row["allowed_projects_json"], []))),
        }

    def authorize_module(self, workspace_id: str, *, user_id: str, page_key: str, category: str, project_id: str = "") -> bool:
        permissions = self.get_member_permissions(workspace_id, user_id=user_id)
        if permissions.get("unrestricted"):
            return True
        allowed_modules = set(permissions.get("allowed_modules", []))
        allowed_categories = {str(item).casefold() for item in permissions.get("allowed_categories", [])}
        allowed_projects = set(permissions.get("allowed_projects", []))
        module_ok = not allowed_modules or _safe_id(page_key, field="page_key") in allowed_modules
        category_ok = not allowed_categories or _clean_text(category, maximum=80, field="category", allow_empty=False).casefold() in allowed_categories
        project_ok = not allowed_projects or (bool(project_id) and _safe_id(project_id, field="project_id") in allowed_projects)
        return bool(module_ok and category_ok and project_ok)

    def heartbeat(self, **kwargs) -> dict[str, Any]:
        workspace_id = _safe_id(kwargs.get("workspace_id", ""), field="workspace_id")
        user_id = _safe_id(kwargs.get("user_id", ""), field="user_id")
        page_key = _safe_id(kwargs.get("page_key", ""), field="page_key", allow_empty=True)
        category = _clean_text(kwargs.get("category", ""), maximum=80, field="category")
        project_id = _safe_id(kwargs.get("project_id", ""), field="project_id", allow_empty=True)
        if page_key and category and not self.authorize_module(workspace_id, user_id=user_id, page_key=page_key, category=category, project_id=project_id):
            raise PermissionDenied("Your active workspace role does not permit this module or project.")
        config = load_host_config()
        if bool(config.get("enabled")):
            max_users = min(max(int(config.get("max_active_users", 25)), 2), 100)
            now = utc_text()
            with self._connect() as connection:
                connection.execute("DELETE FROM live_presence_sessions WHERE expires_at_utc<=?", (now,))
                active_ids = {str(row[0]) for row in connection.execute("SELECT DISTINCT user_id FROM live_presence_sessions WHERE workspace_id=?", (workspace_id,)).fetchall()}
            if user_id not in active_ids and len(active_ids) >= max_users:
                raise PermissionDenied(f"Workspace has reached its configured {max_users}-member active-session limit.")
        return super().heartbeat(**kwargs)

    def set_member_enabled(self, workspace_id: str, *, actor_user_id: str, target_user_id: str, enabled: bool) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        actor_user_id = _safe_id(actor_user_id, field="actor_user_id")
        target_user_id = _safe_id(target_user_id, field="target_user_id")
        if actor_user_id == target_user_id and not enabled:
            raise ValueError("You cannot disable your own active membership.")
        with self._connect() as connection:
            actor = self._require(connection, workspace_id, actor_user_id, self.ADMIN_ROLES)
            target = self._member(connection, workspace_id, target_user_id)
            if str(target["role"]) == "owner" and str(actor["role"]) != "owner":
                raise PermissionDenied("Only an owner can disable another owner.")
            connection.execute("UPDATE live_workspace_members SET enabled=?,updated_at_utc=? WHERE workspace_id=? AND user_id=?", (1 if enabled else 0, utc_text(), workspace_id, target_user_id))
            if not enabled:
                connection.execute("DELETE FROM live_presence_sessions WHERE workspace_id=? AND user_id=?", (workspace_id, target_user_id))
                connection.execute("UPDATE live_account_sessions SET revoked_at_utc=? WHERE workspace_id=? AND user_id=? AND revoked_at_utc IS NULL", (utc_text(), workspace_id, target_user_id))
            self._activity(connection, workspace_id, actor_user_id, str(actor["display_name"]), "member_enabled" if enabled else "member_disabled", f"{'Enabled' if enabled else 'Disabled'} member {target['display_name']}", object_type="member", object_id=target_user_id)
        return self.get_member(workspace_id, target_user_id)

    # --- invite and account session controls ------------------------------------------------
    @staticmethod
    def generate_invite_token() -> str:
        return "BIO-" + secrets.token_urlsafe(24)

    def create_invite(self, workspace_id: str, *, actor_user_id: str, role: str = "researcher", project_id: str = "", note: str = "", expires_hours: int = 24, max_uses: int = 1) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id"); role = str(role).strip().lower()
        if role not in self.INVITE_ROLES:
            raise ValueError("Unsupported invite role.")
        expires_hours = min(max(int(expires_hours), 1), 24 * 30); max_uses = min(max(int(max_uses), 1), 100)
        invite_id = f"invite-{uuid4().hex}"; token = self.generate_invite_token(); now = utc_now()
        with self._connect() as connection:
            member = self._require(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"), self.ADMIN_ROLES)
            connection.execute(
                """INSERT INTO live_workspace_invites(invite_id,workspace_id,token_hash,role,project_id,note,created_by,created_at_utc,expires_at_utc,max_uses,use_count)
                VALUES(?,?,?,?,?,?,?,?,?,?,0)""",
                (invite_id, workspace_id, _hash_secret(token), role, _safe_id(project_id, field="project_id", allow_empty=True), _clean_text(note, maximum=500, field="note"), actor_user_id, utc_text(now), utc_text(now + timedelta(hours=expires_hours)), max_uses),
            )
            self._activity(connection, workspace_id, actor_user_id, str(member["display_name"]), "invite_created", f"Created a {role} workspace invite", object_type="invite", object_id=invite_id)
        return {"invite_id": invite_id, "workspace_id": workspace_id, "token": token, "role": role, "expires_at_utc": utc_text(now + timedelta(hours=expires_hours)), "max_uses": max_uses, "visible_once": True}

    def list_invites(self, workspace_id: str, *, actor_user_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._require(connection, _safe_id(workspace_id, field="workspace_id"), _safe_id(actor_user_id, field="actor_user_id"), self.ADMIN_ROLES)
            rows = connection.execute("SELECT invite_id,workspace_id,role,project_id,note,created_by,created_at_utc,expires_at_utc,max_uses,use_count,revoked_at_utc FROM live_workspace_invites WHERE workspace_id=? ORDER BY created_at_utc DESC", (workspace_id,)).fetchall()
        now = utc_now()
        return [{**dict(row), "active": not row["revoked_at_utc"] and parse_utc(str(row["expires_at_utc"])) > now and int(row["use_count"]) < int(row["max_uses"])} for row in rows]

    def revoke_invite(self, invite_id: str, *, actor_user_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM live_workspace_invites WHERE invite_id=?", (_safe_id(invite_id, field="invite_id"),)).fetchone()
            if row is None:
                raise KeyError(invite_id)
            member = self._require(connection, str(row["workspace_id"]), _safe_id(actor_user_id, field="actor_user_id"), self.ADMIN_ROLES)
            cursor = connection.execute("UPDATE live_workspace_invites SET revoked_at_utc=? WHERE invite_id=? AND revoked_at_utc IS NULL", (utc_text(), invite_id))
            self._activity(connection, str(row["workspace_id"]), actor_user_id, str(member["display_name"]), "invite_revoked", "Revoked a workspace invite", object_type="invite", object_id=invite_id)
        return cursor.rowcount == 1

    def redeem_invite(self, *, token: str, user_id: str, display_name: str) -> dict[str, Any]:
        token = _clean_text(token, maximum=120, field="token", allow_empty=False); user_id = _safe_id(user_id, field="user_id")
        now = utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            candidates = connection.execute("SELECT * FROM live_workspace_invites WHERE revoked_at_utc IS NULL AND expires_at_utc>? AND use_count<max_uses", (utc_text(now),)).fetchall()
            row = next((candidate for candidate in candidates if _verify_secret(token, str(candidate["token_hash"]))), None)
            if row is None:
                raise PermissionDenied("Invite is invalid, expired, revoked or already used.")
            workspace_id = str(row["workspace_id"]); role = str(row["role"]); timestamp = utc_text(now)
            connection.execute(
                """INSERT INTO live_workspace_members(workspace_id,user_id,display_name,role,enabled,joined_at_utc,updated_at_utc)
                VALUES(?,?,?,?,1,?,?) ON CONFLICT(workspace_id,user_id) DO UPDATE SET display_name=excluded.display_name,enabled=1,updated_at_utc=excluded.updated_at_utc""",
                (workspace_id, user_id, _clean_text(display_name, maximum=80, field="display_name", allow_empty=False), role, timestamp, timestamp),
            )
            connection.execute("UPDATE live_workspace_invites SET use_count=use_count+1 WHERE invite_id=?", (str(row["invite_id"]),))
            self._activity(connection, workspace_id, user_id, display_name, "invite_redeemed", "Joined workspace using a time-bounded invite", object_type="invite", object_id=str(row["invite_id"]))
            connection.commit()
        return {**self.get_member(workspace_id, user_id), "project_id": str(row["project_id"]), "workspace_id": workspace_id}

    def register_account_session(self, workspace_id: str, *, user_id: str, account_session_id: str, client_label: str, auth_source: str, ttl_hours: int = 12) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id"); user_id = _safe_id(user_id, field="user_id"); account_session_id = _safe_id(account_session_id, field="account_session_id")
        ttl_hours = min(max(int(ttl_hours), 1), 24 * 30); now = utc_now()
        with self._connect() as connection:
            self._member(connection, workspace_id, user_id)
            existing = connection.execute("SELECT revoked_at_utc FROM live_account_sessions WHERE account_session_id=?", (account_session_id,)).fetchone()
            if existing is not None and existing["revoked_at_utc"]:
                raise PermissionDenied("This browser session was revoked. Sign in again to create a new session.")
            connection.execute(
                """INSERT INTO live_account_sessions(account_session_id,workspace_id,user_id,client_label,auth_source,created_at_utc,last_seen_at_utc,expires_at_utc,revoked_at_utc)
                VALUES(?,?,?,?,?,?,?,?,NULL) ON CONFLICT(account_session_id) DO UPDATE SET last_seen_at_utc=excluded.last_seen_at_utc,expires_at_utc=excluded.expires_at_utc,client_label=excluded.client_label""",
                (account_session_id, workspace_id, user_id, _clean_text(client_label, maximum=120, field="client_label"), _clean_text(auth_source, maximum=80, field="auth_source"), utc_text(now), utc_text(now), utc_text(now + timedelta(hours=ttl_hours))),
            )
        return self.get_account_session(account_session_id, actor_user_id=user_id)

    def get_account_session(self, account_session_id: str, *, actor_user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM live_account_sessions WHERE account_session_id=?", (_safe_id(account_session_id, field="account_session_id"),)).fetchone()
            if row is None:
                raise KeyError(account_session_id)
            actor = self._member(connection, str(row["workspace_id"]), _safe_id(actor_user_id, field="actor_user_id"))
            if str(row["user_id"]) != actor_user_id and str(actor["role"]) not in self.ADMIN_ROLES:
                raise PermissionDenied("You cannot inspect another member session.")
        return dict(row)

    def list_account_sessions(self, workspace_id: str, *, actor_user_id: str, user_id: str = "") -> list[dict[str, Any]]:
        workspace_id = _safe_id(workspace_id, field="workspace_id"); actor_user_id = _safe_id(actor_user_id, field="actor_user_id")
        with self._connect() as connection:
            actor = self._member(connection, workspace_id, actor_user_id)
            target = _safe_id(user_id, field="user_id", allow_empty=True) or actor_user_id
            if target != actor_user_id and str(actor["role"]) not in self.ADMIN_ROLES:
                raise PermissionDenied("Admin role is required to inspect another member sessions.")
            rows = connection.execute("SELECT * FROM live_account_sessions WHERE workspace_id=? AND user_id=? ORDER BY last_seen_at_utc DESC", (workspace_id, target)).fetchall()
        return [dict(row) for row in rows]

    def revoke_account_session(self, account_session_id: str, *, actor_user_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM live_account_sessions WHERE account_session_id=?", (_safe_id(account_session_id, field="account_session_id"),)).fetchone()
            if row is None:
                raise KeyError(account_session_id)
            actor = self._member(connection, str(row["workspace_id"]), _safe_id(actor_user_id, field="actor_user_id"))
            if str(row["user_id"]) != actor_user_id and str(actor["role"]) not in self.ADMIN_ROLES:
                raise PermissionDenied("You cannot revoke another member session.")
            cursor = connection.execute("UPDATE live_account_sessions SET revoked_at_utc=? WHERE account_session_id=? AND revoked_at_utc IS NULL", (utc_text(), account_session_id))
        return cursor.rowcount == 1

    def revoke_all_account_sessions(self, workspace_id: str, *, actor_user_id: str, target_user_id: str | None = None, keep_session_id: str = "") -> int:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        actor_user_id = _safe_id(actor_user_id, field="actor_user_id")
        target = _safe_id(target_user_id or actor_user_id, field="target_user_id")
        with self._connect() as connection:
            actor = self._member(connection, workspace_id, actor_user_id)
            if target != actor_user_id and str(actor["role"]) not in self.ADMIN_ROLES:
                raise PermissionDenied("Admin role is required to revoke another member sessions.")
            clauses = ["workspace_id=?", "user_id=?", "revoked_at_utc IS NULL"]
            params: list[Any] = [workspace_id, target]
            if keep_session_id:
                clauses.append("account_session_id!=?")
                params.append(_safe_id(keep_session_id, field="keep_session_id"))
            cursor = connection.execute(f"UPDATE live_account_sessions SET revoked_at_utc=? WHERE {' AND '.join(clauses)}", (utc_text(), *params))
            self._activity(connection, workspace_id, actor_user_id, str(actor["display_name"]), "sessions_revoked", f"Revoked {cursor.rowcount} account session(s)", object_type="member", object_id=target)
        return int(cursor.rowcount)

    # --- threaded discussions ----------------------------------------------------------------
    def add_reply(self, *, workspace_id: str, user_id: str, parent_comment_id: str, body: str) -> dict[str, Any]:
        parent = self.get_comment(parent_comment_id, actor_user_id=user_id)
        if str(parent["workspace_id"]) != workspace_id:
            raise PermissionDenied("Parent comment belongs to another workspace.")
        comment = self.add_comment(workspace_id=workspace_id, user_id=user_id, resource_type=str(parent["resource_type"]), resource_id=str(parent["resource_id"]), body=body)
        with self._connect() as connection:
            connection.execute("INSERT OR REPLACE INTO live_comment_threads(comment_id,parent_comment_id) VALUES(?,?)", (str(comment["comment_id"]), _safe_id(parent_comment_id, field="parent_comment_id")))
        return {**comment, "parent_comment_id": parent_comment_id}

    def edit_comment(self, comment_id: str, *, user_id: str, body: str) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM live_comments WHERE comment_id=?", (_safe_id(comment_id, field="comment_id"),)).fetchone()
            if row is None:
                raise KeyError(comment_id)
            member = self._member(connection, str(row["workspace_id"]), _safe_id(user_id, field="user_id"))
            if str(row["author_user_id"]) != user_id and str(member["role"]) not in self.ADMIN_ROLES:
                raise PermissionDenied("Only the author or an admin can edit this comment.")
            connection.execute("INSERT INTO live_comment_revisions(revision_id,comment_id,body,edited_by,edited_at_utc) VALUES(?,?,?,?,?)", (f"comment-revision-{uuid4().hex}", comment_id, str(row["body"]), user_id, utc_text()))
            cleaned = _clean_text(body, maximum=4000, field="body", allow_empty=False)
            connection.execute("UPDATE live_comments SET body=?,updated_at_utc=? WHERE comment_id=?", (cleaned, utc_text(), comment_id))
            self._activity(connection, str(row["workspace_id"]), user_id, str(member["display_name"]), "comment_edited", "Edited a collaboration comment", object_type=str(row["resource_type"]), object_id=str(row["resource_id"]))
            connection.commit()
        return self.get_comment(comment_id, actor_user_id=user_id)

    def set_comment_resolved(self, comment_id: str, *, user_id: str, resolved: bool) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM live_comments WHERE comment_id=?", (_safe_id(comment_id, field="comment_id"),)).fetchone()
            if row is None:
                raise KeyError(comment_id)
            member = self._require(connection, str(row["workspace_id"]), _safe_id(user_id, field="user_id"), self.WRITE_ROLES)
            connection.execute(
                """INSERT INTO live_comment_threads(comment_id,parent_comment_id,resolved_at_utc,resolved_by) VALUES(?,'',?,?)
                ON CONFLICT(comment_id) DO UPDATE SET resolved_at_utc=excluded.resolved_at_utc,resolved_by=excluded.resolved_by""",
                (comment_id, utc_text() if resolved else None, user_id if resolved else ""),
            )
            connection.execute("UPDATE live_comments SET status=?,updated_at_utc=? WHERE comment_id=?", ("resolved" if resolved else "open", utc_text(), comment_id))
            self._activity(connection, str(row["workspace_id"]), user_id, str(member["display_name"]), "comment_resolved" if resolved else "comment_reopened", "Resolved discussion" if resolved else "Reopened discussion", object_type=str(row["resource_type"]), object_id=str(row["resource_id"]))
        return self.get_comment_thread(comment_id, actor_user_id=user_id)

    def get_comment_thread(self, comment_id: str, *, actor_user_id: str) -> dict[str, Any]:
        base = self.get_comment(comment_id, actor_user_id=actor_user_id)
        with self._connect() as connection:
            thread = connection.execute("SELECT * FROM live_comment_threads WHERE comment_id=?", (comment_id,)).fetchone()
            revisions = connection.execute("SELECT * FROM live_comment_revisions WHERE comment_id=? ORDER BY edited_at_utc DESC", (comment_id,)).fetchall()
        return {**base, **(dict(thread) if thread else {"parent_comment_id": "", "resolved_at_utc": None, "resolved_by": ""}), "revisions": [dict(row) for row in revisions]}

    def list_comment_threads(self, workspace_id: str, *, actor_user_id: str, resource_type: str, resource_id: str, limit: int = 200) -> list[dict[str, Any]]:
        comments = super().list_comments(workspace_id, actor_user_id=actor_user_id, resource_type=resource_type, resource_id=resource_id, limit=limit)
        with self._connect() as connection:
            thread_rows = {str(row["comment_id"]): dict(row) for row in connection.execute("SELECT * FROM live_comment_threads WHERE comment_id IN (SELECT comment_id FROM live_comments WHERE workspace_id=? AND resource_type=? AND resource_id=?)", (workspace_id, resource_type, resource_id)).fetchall()}
        return [{**comment, **thread_rows.get(str(comment["comment_id"]), {"parent_comment_id": "", "resolved_at_utc": None, "resolved_by": ""})} for comment in comments]

    # --- tasks, evidence and project timeline ------------------------------------------------
    def create_task(self, *, workspace_id: str, user_id: str, title: str, description: str = "", assigned_to: str = "", priority: str = "normal", project_id: str = "", resource_type: str = "", resource_id: str = "", due_at_utc: str | None = None) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id"); user_id = _safe_id(user_id, field="user_id"); priority = str(priority).strip().lower()
        if priority not in {"low", "normal", "high", "urgent"}:
            raise ValueError("Unsupported task priority.")
        if due_at_utc:
            parse_utc(due_at_utc)
        task_id = f"task-{uuid4().hex}"; now = utc_text()
        with self._connect() as connection:
            member = self._require(connection, workspace_id, user_id, self.WRITE_ROLES)
            assigned = _safe_id(assigned_to, field="assigned_to", allow_empty=True)
            if assigned:
                self._member(connection, workspace_id, assigned)
            connection.execute(
                """INSERT INTO live_tasks(task_id,workspace_id,project_id,resource_type,resource_id,title,description,status,priority,assigned_to,created_by,due_at_utc,created_at_utc,updated_at_utc)
                VALUES(?,?,?,?,?,?,?,'assigned',?,?,?,?,?,?)""",
                (task_id, workspace_id, _safe_id(project_id, field="project_id", allow_empty=True), _safe_id(resource_type, field="resource_type", allow_empty=True), _safe_id(resource_id, field="resource_id", allow_empty=True), _clean_text(title, maximum=200, field="title", allow_empty=False), _clean_text(description, maximum=4000, field="description"), priority, assigned, user_id, due_at_utc, now, now),
            )
            self._activity(connection, workspace_id, user_id, str(member["display_name"]), "task_created", f"Created task: {title}", object_type="task", object_id=task_id, detail={"assigned_to": assigned, "priority": priority})
            if assigned:
                self._notify(connection, workspace_id, assigned, "Task assigned", title, "task", task_id)
        return self.get_task(task_id, actor_user_id=user_id)

    def _notify(self, connection: sqlite3.Connection, workspace_id: str, user_id: str, title: str, body: str, object_type: str = "", object_id: str = "", level: str = "info") -> None:
        pref = connection.execute("SELECT muted,mention_only FROM live_notification_preferences WHERE workspace_id=? AND user_id=?", (workspace_id, user_id)).fetchone()
        if pref is not None and int(pref["muted"]):
            return
        connection.execute("INSERT INTO live_notifications(notification_id,workspace_id,user_id,level,title,body,object_type,object_id,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?)", (f"notification-{uuid4().hex}", workspace_id, user_id, level, _clean_text(title, maximum=160, field="title"), _clean_text(body, maximum=500, field="body"), _safe_id(object_type, field="object_type", allow_empty=True), _safe_id(object_id, field="object_id", allow_empty=True), utc_text()))

    def get_task(self, task_id: str, *, actor_user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM live_tasks WHERE task_id=?", (_safe_id(task_id, field="task_id"),)).fetchone()
            if row is None:
                raise KeyError(task_id)
            self._member(connection, str(row["workspace_id"]), _safe_id(actor_user_id, field="actor_user_id"))
        return dict(row)

    def update_task(self, task_id: str, *, user_id: str, status: str | None = None, assigned_to: str | None = None, priority: str | None = None, description: str | None = None) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM live_tasks WHERE task_id=?", (_safe_id(task_id, field="task_id"),)).fetchone()
            if row is None:
                raise KeyError(task_id)
            member = self._require(connection, str(row["workspace_id"]), _safe_id(user_id, field="user_id"), self.WRITE_ROLES)
            next_status = str(status or row["status"]).strip().lower()
            if next_status not in self.TASK_STATUSES:
                raise ValueError("Unsupported task status.")
            next_priority = str(priority or row["priority"]).strip().lower()
            if next_priority not in {"low", "normal", "high", "urgent"}:
                raise ValueError("Unsupported task priority.")
            next_assigned = str(row["assigned_to"]) if assigned_to is None else _safe_id(assigned_to, field="assigned_to", allow_empty=True)
            if next_assigned:
                self._member(connection, str(row["workspace_id"]), next_assigned)
            next_description = str(row["description"]) if description is None else _clean_text(description, maximum=4000, field="description")
            completed = utc_text() if next_status == "done" else None
            connection.execute("UPDATE live_tasks SET status=?,priority=?,assigned_to=?,description=?,updated_at_utc=?,completed_at_utc=? WHERE task_id=?", (next_status, next_priority, next_assigned, next_description, utc_text(), completed, task_id))
            self._activity(connection, str(row["workspace_id"]), user_id, str(member["display_name"]), "task_updated", f"Task moved to {next_status}", object_type="task", object_id=task_id)
            connection.commit()
        return self.get_task(task_id, actor_user_id=user_id)

    def list_tasks(self, workspace_id: str, *, actor_user_id: str, status: str = "", assigned_to: str = "", include_deleted: bool = False, limit: int = 300) -> list[dict[str, Any]]:
        workspace_id = _safe_id(workspace_id, field="workspace_id"); clauses = ["workspace_id=?"]; params: list[Any] = [workspace_id]
        if not include_deleted: clauses.append("deleted_at_utc IS NULL")
        if status:
            if status not in self.TASK_STATUSES: raise ValueError("Unsupported task status.")
            clauses.append("status=?"); params.append(status)
        if assigned_to: clauses.append("assigned_to=?"); params.append(_safe_id(assigned_to, field="assigned_to"))
        params.append(min(max(int(limit), 1), 1000))
        with self._connect() as connection:
            self._member(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"))
            rows = connection.execute(f"SELECT * FROM live_tasks WHERE {' AND '.join(clauses)} ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,updated_at_utc DESC LIMIT ?", tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def add_bookmark(self, *, workspace_id: str, user_id: str, kind: str, title: str, safe_reference: str, source_name: str = "", evidence_level: str = "ungraded", notes: str = "", project_id: str = "") -> dict[str, Any]:
        bookmark_id = f"bookmark-{uuid4().hex}"; workspace_id = _safe_id(workspace_id, field="workspace_id"); user_id = _safe_id(user_id, field="user_id")
        with self._connect() as connection:
            member = self._require(connection, workspace_id, user_id, self.WRITE_ROLES)
            connection.execute("INSERT INTO live_bookmarks(bookmark_id,workspace_id,project_id,kind,title,safe_reference,source_name,evidence_level,notes,added_by,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (bookmark_id, workspace_id, _safe_id(project_id, field="project_id", allow_empty=True), _clean_text(kind, maximum=80, field="kind", allow_empty=False), _clean_text(title, maximum=240, field="title", allow_empty=False), _clean_text(safe_reference, maximum=1000, field="safe_reference", allow_empty=False), _clean_text(source_name, maximum=160, field="source_name"), _clean_text(evidence_level, maximum=80, field="evidence_level"), _clean_text(notes, maximum=3000, field="notes"), user_id, utc_text()))
            self._activity(connection, workspace_id, user_id, str(member["display_name"]), "bookmark_added", f"Added evidence bookmark: {title}", object_type="bookmark", object_id=bookmark_id)
        return self.get_bookmark(bookmark_id, actor_user_id=user_id)

    def get_bookmark(self, bookmark_id: str, *, actor_user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM live_bookmarks WHERE bookmark_id=?", (_safe_id(bookmark_id, field="bookmark_id"),)).fetchone()
            if row is None: raise KeyError(bookmark_id)
            self._member(connection, str(row["workspace_id"]), _safe_id(actor_user_id, field="actor_user_id"))
        return dict(row)

    def list_bookmarks(self, workspace_id: str, *, actor_user_id: str, kind: str = "", limit: int = 300) -> list[dict[str, Any]]:
        clauses=["workspace_id=?", "deleted_at_utc IS NULL"]; params: list[Any]=[_safe_id(workspace_id, field="workspace_id")]
        if kind: clauses.append("kind=?"); params.append(_clean_text(kind, maximum=80, field="kind"))
        params.append(min(max(int(limit),1),1000))
        with self._connect() as connection:
            self._member(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"))
            rows=connection.execute(f"SELECT * FROM live_bookmarks WHERE {' AND '.join(clauses)} ORDER BY created_at_utc DESC LIMIT ?", tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def add_project_link(self, *, workspace_id: str, user_id: str, project_id: str, module_key: str, resource_type: str, resource_id: str, title: str, subject_alias: str = "") -> dict[str, Any]:
        link_id=f"link-{uuid4().hex}"; workspace_id=_safe_id(workspace_id, field="workspace_id"); user_id=_safe_id(user_id, field="user_id")
        with self._connect() as connection:
            member=self._require(connection,workspace_id,user_id,self.WRITE_ROLES)
            connection.execute("INSERT INTO live_project_links(link_id,workspace_id,project_id,subject_alias,module_key,resource_type,resource_id,title,created_by,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?)", (link_id,workspace_id,_safe_id(project_id,field="project_id"),_safe_id(subject_alias,field="subject_alias",allow_empty=True),_safe_id(module_key,field="module_key"),_safe_id(resource_type,field="resource_type"),_safe_id(resource_id,field="resource_id"),_clean_text(title,maximum=240,field="title",allow_empty=False),user_id,utc_text()))
            self._activity(connection,workspace_id,user_id,str(member["display_name"]),"project_link_added",f"Linked {title} to project",object_type="project_link",object_id=link_id)
        return {"link_id":link_id,"workspace_id":workspace_id,"project_id":project_id,"module_key":module_key,"resource_type":resource_type,"resource_id":resource_id,"title":title,"subject_alias":subject_alias}

    def list_project_links(self, workspace_id: str, *, actor_user_id: str, project_id: str = "", subject_alias: str = "") -> list[dict[str, Any]]:
        clauses=["workspace_id=?","deleted_at_utc IS NULL"]; params:list[Any]=[_safe_id(workspace_id,field="workspace_id")]
        if project_id: clauses.append("project_id=?"); params.append(_safe_id(project_id,field="project_id"))
        if subject_alias: clauses.append("subject_alias=?"); params.append(_safe_id(subject_alias,field="subject_alias"))
        with self._connect() as connection:
            self._member(connection,workspace_id,_safe_id(actor_user_id,field="actor_user_id"))
            rows=connection.execute(f"SELECT * FROM live_project_links WHERE {' AND '.join(clauses)} ORDER BY created_at_utc DESC",tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def add_timeline_event(self, *, workspace_id: str, user_id: str, event_type: str, title: str, safe_detail: str = "", project_id: str = "", subject_alias: str = "", occurred_at_utc: str | None = None, system_generated: bool = False) -> dict[str, Any]:
        timeline_id=f"timeline-{uuid4().hex}"; occurred=occurred_at_utc or utc_text(); parse_utc(occurred)
        with self._connect() as connection:
            member=self._require(connection,_safe_id(workspace_id,field="workspace_id"),_safe_id(user_id,field="user_id"),self.WRITE_ROLES)
            connection.execute("INSERT INTO live_timeline_events(timeline_id,workspace_id,project_id,subject_alias,event_type,title,safe_detail,occurred_at_utc,created_by,created_at_utc,system_generated) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (timeline_id,workspace_id,_safe_id(project_id,field="project_id",allow_empty=True),_safe_id(subject_alias,field="subject_alias",allow_empty=True),_clean_text(event_type,maximum=80,field="event_type",allow_empty=False),_clean_text(title,maximum=240,field="title",allow_empty=False),_clean_text(safe_detail,maximum=3000,field="safe_detail"),occurred,user_id,utc_text(),1 if system_generated else 0))
            self._activity(connection,workspace_id,user_id,str(member["display_name"]),"timeline_event_added",f"Timeline: {title}",object_type="timeline",object_id=timeline_id)
        return {"timeline_id":timeline_id,"workspace_id":workspace_id,"project_id":project_id,"subject_alias":subject_alias,"event_type":event_type,"title":title,"safe_detail":safe_detail,"occurred_at_utc":occurred}

    def list_timeline(self, workspace_id: str, *, actor_user_id: str, project_id: str = "", subject_alias: str = "", limit: int = 500) -> list[dict[str, Any]]:
        clauses=["workspace_id=?","deleted_at_utc IS NULL"];params:list[Any]=[_safe_id(workspace_id,field="workspace_id")]
        if project_id: clauses.append("project_id=?");params.append(_safe_id(project_id,field="project_id"))
        if subject_alias: clauses.append("subject_alias=?");params.append(_safe_id(subject_alias,field="subject_alias"))
        params.append(min(max(int(limit),1),2000))
        with self._connect() as connection:
            self._member(connection,workspace_id,_safe_id(actor_user_id,field="actor_user_id"))
            rows=connection.execute(f"SELECT * FROM live_timeline_events WHERE {' AND '.join(clauses)} ORDER BY occurred_at_utc DESC LIMIT ?",tuple(params)).fetchall()
        return [dict(row) for row in rows]

    # --- scientific annotations ---------------------------------------------------------------
    def create_annotation(self, *, workspace_id: str, user_id: str, resource_type: str, resource_id: str, annotation_type: str, label: str, status: str = "draft", confidence: float | None = None, geometry: dict[str, Any] | None = None, attributes: dict[str, Any] | None = None, project_id: str = "") -> dict[str, Any]:
        workspace_id=_safe_id(workspace_id,field="workspace_id");user_id=_safe_id(user_id,field="user_id");status=str(status).strip().lower()
        if status not in self.ANNOTATION_STATUSES: raise ValueError("Unsupported annotation status.")
        if confidence is not None and not 0 <= float(confidence) <= 1: raise ValueError("confidence must be between 0 and 1.")
        annotation_id=f"annotation-{uuid4().hex}";now=utc_text()
        with self._connect() as connection:
            member=self._require(connection,workspace_id,user_id,self.WRITE_ROLES)
            connection.execute("""INSERT INTO live_annotations(annotation_id,workspace_id,project_id,resource_type,resource_id,annotation_type,label,status,confidence,geometry_json,attributes_json,created_by,created_at_utc,updated_by,updated_at_utc,revision)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",(annotation_id,workspace_id,_safe_id(project_id,field="project_id",allow_empty=True),_safe_id(resource_type,field="resource_type"),_safe_id(resource_id,field="resource_id"),_clean_text(annotation_type,maximum=100,field="annotation_type",allow_empty=False),_clean_text(label,maximum=500,field="label",allow_empty=False),status,float(confidence) if confidence is not None else None,_bounded_json(geometry or {},field="geometry"),_bounded_json(attributes or {},field="attributes"),user_id,now,user_id,now))
            snapshot=self._annotation_snapshot(connection,annotation_id)
            connection.execute("INSERT INTO live_annotation_revisions(annotation_id,revision,snapshot_json,changed_by,changed_at_utc) VALUES(?,?,?,?,?)",(annotation_id,1,_bounded_json(snapshot,field="annotation snapshot"),user_id,now))
            self._activity(connection,workspace_id,user_id,str(member["display_name"]),"annotation_created",f"Created {annotation_type} annotation",object_type=resource_type,object_id=resource_id,detail={"annotation_id":annotation_id})
        return self.get_annotation(annotation_id,actor_user_id=user_id)

    @staticmethod
    def _annotation_snapshot(connection: sqlite3.Connection, annotation_id: str) -> dict[str, Any]:
        row=connection.execute("SELECT * FROM live_annotations WHERE annotation_id=?",(annotation_id,)).fetchone()
        if row is None: raise KeyError(annotation_id)
        payload=dict(row);payload["geometry"]=_decode(payload.pop("geometry_json"),{});payload["attributes"]=_decode(payload.pop("attributes_json"),{})
        return payload

    def get_annotation(self, annotation_id: str, *, actor_user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row=connection.execute("SELECT * FROM live_annotations WHERE annotation_id=?",(_safe_id(annotation_id,field="annotation_id"),)).fetchone()
            if row is None: raise KeyError(annotation_id)
            self._member(connection,str(row["workspace_id"]),_safe_id(actor_user_id,field="actor_user_id"))
            payload=dict(row)
        payload["geometry"]=_decode(payload.pop("geometry_json"),{});payload["attributes"]=_decode(payload.pop("attributes_json"),{})
        return payload

    def update_annotation(self, annotation_id: str, *, user_id: str, expected_revision: int, label: str | None = None, status: str | None = None, confidence: float | None = None, geometry: dict[str,Any] | None = None, attributes: dict[str,Any] | None = None) -> dict[str,Any]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE");row=connection.execute("SELECT * FROM live_annotations WHERE annotation_id=?",(_safe_id(annotation_id,field="annotation_id"),)).fetchone()
            if row is None: raise KeyError(annotation_id)
            member=self._require(connection,str(row["workspace_id"]),_safe_id(user_id,field="user_id"),self.WRITE_ROLES)
            current=int(row["revision"])
            if current!=int(expected_revision): raise RevisionConflict("Annotation changed since it was opened.",current_revision=current)
            next_status=str(status or row["status"]).strip().lower()
            if next_status not in self.ANNOTATION_STATUSES: raise ValueError("Unsupported annotation status.")
            if confidence is not None and not 0<=float(confidence)<=1: raise ValueError("confidence must be between 0 and 1.")
            revision=current+1
            connection.execute("""UPDATE live_annotations SET label=?,status=?,confidence=?,geometry_json=?,attributes_json=?,updated_by=?,updated_at_utc=?,revision=? WHERE annotation_id=?""",(_clean_text(label if label is not None else row["label"],maximum=500,field="label",allow_empty=False),next_status,float(confidence) if confidence is not None else row["confidence"],_bounded_json(geometry if geometry is not None else _decode(row["geometry_json"],{}),field="geometry"),_bounded_json(attributes if attributes is not None else _decode(row["attributes_json"],{}),field="attributes"),user_id,utc_text(),revision,annotation_id))
            snapshot=self._annotation_snapshot(connection,annotation_id)
            connection.execute("INSERT INTO live_annotation_revisions(annotation_id,revision,snapshot_json,changed_by,changed_at_utc) VALUES(?,?,?,?,?)",(annotation_id,revision,_bounded_json(snapshot,field="annotation snapshot"),user_id,utc_text()))
            self._activity(connection,str(row["workspace_id"]),user_id,str(member["display_name"]),"annotation_updated",f"Updated annotation revision {revision}",object_type=str(row["resource_type"]),object_id=str(row["resource_id"]),detail={"annotation_id":annotation_id})
            connection.commit()
        return self.get_annotation(annotation_id,actor_user_id=user_id)

    def list_annotations(self, workspace_id: str, *, actor_user_id: str, resource_type: str = "", resource_id: str = "", status: str = "", limit: int = 500) -> list[dict[str,Any]]:
        clauses=["workspace_id=?","deleted_at_utc IS NULL"];params:list[Any]=[_safe_id(workspace_id,field="workspace_id")]
        if resource_type: clauses.append("resource_type=?");params.append(_safe_id(resource_type,field="resource_type"))
        if resource_id: clauses.append("resource_id=?");params.append(_safe_id(resource_id,field="resource_id"))
        if status:
            if status not in self.ANNOTATION_STATUSES: raise ValueError("Unsupported annotation status.")
            clauses.append("status=?");params.append(status)
        params.append(min(max(int(limit),1),2000))
        with self._connect() as connection:
            self._member(connection,workspace_id,_safe_id(actor_user_id,field="actor_user_id"))
            rows=connection.execute(f"SELECT * FROM live_annotations WHERE {' AND '.join(clauses)} ORDER BY updated_at_utc DESC LIMIT ?",tuple(params)).fetchall()
        output=[]
        for row in rows:
            payload=dict(row);payload["geometry"]=_decode(payload.pop("geometry_json"),{});payload["attributes"]=_decode(payload.pop("attributes_json"),{});output.append(payload)
        return output

    # --- collaborative review sessions and follow-navigation ---------------------------------
    def create_collaboration_session(self, *, workspace_id: str, user_id: str, title: str, sync_navigation: bool = True) -> dict[str,Any]:
        session_id=f"collab-{uuid4().hex}";now=utc_text()
        with self._connect() as connection:
            member=self._require(connection,_safe_id(workspace_id,field="workspace_id"),_safe_id(user_id,field="user_id"),self.WRITE_ROLES)
            connection.execute("INSERT INTO live_collaboration_sessions(collaboration_session_id,workspace_id,title,host_user_id,status,sync_navigation,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,?)",(session_id,workspace_id,_clean_text(title,maximum=200,field="title",allow_empty=False),user_id,"active",1 if sync_navigation else 0,now,now))
            connection.execute("INSERT INTO live_collaboration_participants(collaboration_session_id,user_id,joined_at_utc,last_seen_at_utc,follow_host) VALUES(?,?,?,?,1)",(session_id,user_id,now,now))
            self._activity(connection,workspace_id,user_id,str(member["display_name"]),"collaboration_session_started",f"Started collaborative session: {title}",object_type="collaboration_session",object_id=session_id)
        return self.get_collaboration_session(session_id,actor_user_id=user_id)

    def get_collaboration_session(self, collaboration_session_id: str, *, actor_user_id: str) -> dict[str,Any]:
        with self._connect() as connection:
            row=connection.execute("SELECT * FROM live_collaboration_sessions WHERE collaboration_session_id=?",(_safe_id(collaboration_session_id,field="collaboration_session_id"),)).fetchone()
            if row is None: raise KeyError(collaboration_session_id)
            self._member(connection,str(row["workspace_id"]),_safe_id(actor_user_id,field="actor_user_id"))
            participants=connection.execute("SELECT p.*,m.display_name,m.role FROM live_collaboration_participants p JOIN live_workspace_members m ON m.workspace_id=? AND m.user_id=p.user_id WHERE p.collaboration_session_id=? ORDER BY p.joined_at_utc",(str(row["workspace_id"]),collaboration_session_id)).fetchall()
        payload=dict(row);payload["cursor"]=_decode(payload.pop("cursor_json"),{});payload["participants"]=[dict(item) for item in participants];return payload

    def list_collaboration_sessions(self, workspace_id: str, *, actor_user_id: str, active_only: bool = True) -> list[dict[str,Any]]:
        with self._connect() as connection:
            self._member(connection,_safe_id(workspace_id,field="workspace_id"),_safe_id(actor_user_id,field="actor_user_id"))
            rows=connection.execute("SELECT * FROM live_collaboration_sessions WHERE workspace_id=?"+(" AND status!='ended'" if active_only else "")+" ORDER BY updated_at_utc DESC",(workspace_id,)).fetchall()
        return [{**dict(row),"cursor":_decode(row["cursor_json"],{})} for row in rows]

    def join_collaboration_session(self, collaboration_session_id: str, *, user_id: str, follow_host: bool = True) -> dict[str,Any]:
        now=utc_text()
        with self._connect() as connection:
            row=connection.execute("SELECT * FROM live_collaboration_sessions WHERE collaboration_session_id=?",(_safe_id(collaboration_session_id,field="collaboration_session_id"),)).fetchone()
            if row is None: raise KeyError(collaboration_session_id)
            if str(row["status"])=="ended": raise ValueError("Collaboration session has ended.")
            self._member(connection,str(row["workspace_id"]),_safe_id(user_id,field="user_id"))
            connection.execute("INSERT INTO live_collaboration_participants(collaboration_session_id,user_id,joined_at_utc,last_seen_at_utc,follow_host) VALUES(?,?,?,?,?) ON CONFLICT(collaboration_session_id,user_id) DO UPDATE SET last_seen_at_utc=excluded.last_seen_at_utc,follow_host=excluded.follow_host",(collaboration_session_id,user_id,now,now,1 if follow_host else 0))
        return self.get_collaboration_session(collaboration_session_id,actor_user_id=user_id)

    def update_collaboration_navigation(self, collaboration_session_id: str, *, user_id: str, page_key: str, page_title: str = "", resource_type: str = "", resource_id: str = "", cursor: dict[str,Any] | None = None) -> dict[str,Any]:
        with self._connect() as connection:
            row=connection.execute("SELECT * FROM live_collaboration_sessions WHERE collaboration_session_id=?",(_safe_id(collaboration_session_id,field="collaboration_session_id"),)).fetchone()
            if row is None: raise KeyError(collaboration_session_id)
            if str(row["host_user_id"])!=_safe_id(user_id,field="user_id"): raise PermissionDenied("Only the session host can synchronize navigation.")
            connection.execute("UPDATE live_collaboration_sessions SET page_key=?,page_title=?,resource_type=?,resource_id=?,cursor_json=?,updated_at_utc=? WHERE collaboration_session_id=?",(_safe_id(page_key,field="page_key",allow_empty=True),_clean_text(page_title,maximum=160,field="page_title"),_safe_id(resource_type,field="resource_type",allow_empty=True),_safe_id(resource_id,field="resource_id",allow_empty=True),_bounded_json(cursor or {},maximum_bytes=32_000,field="cursor"),utc_text(),collaboration_session_id))
        return self.get_collaboration_session(collaboration_session_id,actor_user_id=user_id)

    def set_collaboration_session_status(self, collaboration_session_id: str, *, user_id: str, status: str) -> dict[str, Any]:
        status = str(status).strip().lower()
        if status not in {"active", "paused"}:
            raise ValueError("Collaboration session status must be active or paused.")
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM live_collaboration_sessions WHERE collaboration_session_id=?", (_safe_id(collaboration_session_id, field="collaboration_session_id"),)).fetchone()
            if row is None:
                raise KeyError(collaboration_session_id)
            member = self._member(connection, str(row["workspace_id"]), _safe_id(user_id, field="user_id"))
            if str(row["host_user_id"]) != user_id and str(member["role"]) not in self.ADMIN_ROLES:
                raise PermissionDenied("Only the session host or an admin can pause or resume the session.")
            if str(row["status"]) == "ended":
                raise ValueError("Collaboration session has ended.")
            connection.execute("UPDATE live_collaboration_sessions SET status=?,updated_at_utc=? WHERE collaboration_session_id=?", (status, utc_text(), collaboration_session_id))
            self._activity(connection, str(row["workspace_id"]), user_id, str(member["display_name"]), f"collaboration_session_{status}", f"{status.title()} collaborative session: {row['title']}", object_type="collaboration_session", object_id=collaboration_session_id)
        return self.get_collaboration_session(collaboration_session_id, actor_user_id=user_id)

    def leave_collaboration_session(self, collaboration_session_id: str, *, user_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM live_collaboration_sessions WHERE collaboration_session_id=?", (_safe_id(collaboration_session_id, field="collaboration_session_id"),)).fetchone()
            if row is None:
                raise KeyError(collaboration_session_id)
            self._member(connection, str(row["workspace_id"]), _safe_id(user_id, field="user_id"))
            if str(row["host_user_id"]) == user_id:
                raise ValueError("The session host must end the session instead of leaving it.")
            cursor = connection.execute("DELETE FROM live_collaboration_participants WHERE collaboration_session_id=? AND user_id=?", (collaboration_session_id, user_id))
        return cursor.rowcount == 1

    def end_collaboration_session(self, collaboration_session_id: str, *, user_id: str) -> dict[str,Any]:
        with self._connect() as connection:
            row=connection.execute("SELECT * FROM live_collaboration_sessions WHERE collaboration_session_id=?",(_safe_id(collaboration_session_id,field="collaboration_session_id"),)).fetchone()
            if row is None: raise KeyError(collaboration_session_id)
            member=self._member(connection,str(row["workspace_id"]),_safe_id(user_id,field="user_id"))
            if str(row["host_user_id"])!=user_id and str(member["role"]) not in self.ADMIN_ROLES: raise PermissionDenied("Only the host or an admin can end this session.")
            connection.execute("UPDATE live_collaboration_sessions SET status='ended',ended_at_utc=?,updated_at_utc=? WHERE collaboration_session_id=?",(utc_text(),utc_text(),collaboration_session_id))
            self._activity(connection,str(row["workspace_id"]),user_id,str(member["display_name"]),"collaboration_session_ended",f"Ended collaborative session: {row['title']}",object_type="collaboration_session",object_id=collaboration_session_id)
        return self.get_collaboration_session(collaboration_session_id,actor_user_id=user_id)

    # --- notifications, jobs, offline recovery and resync -------------------------------------
    def get_notification_preferences(self, workspace_id: str, *, user_id: str) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        user_id = _safe_id(user_id, field="user_id")
        with self._connect() as connection:
            self._member(connection, workspace_id, user_id)
            row = connection.execute("SELECT * FROM live_notification_preferences WHERE workspace_id=? AND user_id=?", (workspace_id, user_id)).fetchone()
        return dict(row) if row else {"workspace_id": workspace_id, "user_id": user_id, "muted": 0, "mention_only": 0, "browser_notifications": 0, "updated_at_utc": ""}

    def update_notification_preferences(self, workspace_id: str, *, user_id: str, muted: bool = False, mention_only: bool = False, browser_notifications: bool = False) -> dict[str,Any]:
        with self._connect() as connection:
            self._member(connection,_safe_id(workspace_id,field="workspace_id"),_safe_id(user_id,field="user_id"))
            connection.execute("INSERT INTO live_notification_preferences(workspace_id,user_id,muted,mention_only,browser_notifications,updated_at_utc) VALUES(?,?,?,?,?,?) ON CONFLICT(workspace_id,user_id) DO UPDATE SET muted=excluded.muted,mention_only=excluded.mention_only,browser_notifications=excluded.browser_notifications,updated_at_utc=excluded.updated_at_utc",(workspace_id,user_id,1 if muted else 0,1 if mention_only else 0,1 if browser_notifications else 0,utc_text()))
            row=connection.execute("SELECT * FROM live_notification_preferences WHERE workspace_id=? AND user_id=?",(workspace_id,user_id)).fetchone()
        return dict(row)

    def mark_all_notifications_read(self, workspace_id: str, *, user_id: str) -> int:
        with self._connect() as connection:
            self._member(connection,_safe_id(workspace_id,field="workspace_id"),_safe_id(user_id,field="user_id"))
            cursor=connection.execute("UPDATE live_notifications SET read_at_utc=? WHERE workspace_id=? AND user_id=? AND read_at_utc IS NULL",(utc_text(),workspace_id,user_id))
        return int(cursor.rowcount)

    def request_job_action(self, *, workspace_id: str, user_id: str, job_id: str, action: str, note: str = "") -> dict[str,Any]:
        action=str(action).strip().lower()
        if action not in {"cancel","retry","pause","resume"}: raise ValueError("Unsupported job action.")
        action_id=f"job-action-{uuid4().hex}"
        with self._connect() as connection:
            member=self._require(connection,_safe_id(workspace_id,field="workspace_id"),_safe_id(user_id,field="user_id"),self.WRITE_ROLES)
            job=connection.execute("SELECT * FROM live_shared_jobs WHERE workspace_id=? AND job_id=?",(workspace_id,_safe_id(job_id,field="job_id"))).fetchone()
            if job is None: raise KeyError(job_id)
            if str(job["owner_user_id"])!=user_id and str(member["role"]) not in self.ADMIN_ROLES: raise PermissionDenied("Only the job owner or an admin can request this action.")
            connection.execute("INSERT INTO live_job_actions(action_id,workspace_id,job_id,requested_by,action,note,created_at_utc) VALUES(?,?,?,?,?,?,?)",(action_id,workspace_id,job_id,user_id,action,_clean_text(note,maximum=500,field="note"),utc_text()))
            self._activity(connection,workspace_id,user_id,str(member["display_name"]),"job_action_requested",f"Requested {action} for {job['workflow']}",object_type="job",object_id=job_id)
        return {"action_id":action_id,"workspace_id":workspace_id,"job_id":job_id,"action":action,"status":"requested","note":note}

    def list_job_actions(self, workspace_id: str, *, actor_user_id: str, job_id: str = "") -> list[dict[str,Any]]:
        clauses=["workspace_id=?"];params:list[Any]=[_safe_id(workspace_id,field="workspace_id")]
        if job_id: clauses.append("job_id=?");params.append(_safe_id(job_id,field="job_id"))
        with self._connect() as connection:
            self._member(connection,workspace_id,_safe_id(actor_user_id,field="actor_user_id"));rows=connection.execute(f"SELECT * FROM live_job_actions WHERE {' AND '.join(clauses)} ORDER BY created_at_utc DESC",tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def save_offline_draft(self, *, workspace_id: str, user_id: str, resource_type: str, resource_id: str, base_revision: int, draft: dict[str,Any]) -> dict[str,Any]:
        draft_id=f"draft-{uuid4().hex}";now=utc_text()
        with self._connect() as connection:
            self._require(connection,_safe_id(workspace_id,field="workspace_id"),_safe_id(user_id,field="user_id"),self.WRITE_ROLES)
            connection.execute("INSERT INTO live_offline_drafts(draft_id,workspace_id,user_id,resource_type,resource_id,base_revision,draft_json,status,created_at_utc,updated_at_utc) VALUES(?,?,?,?,?,?,?,'pending',?,?)",(draft_id,workspace_id,user_id,_safe_id(resource_type,field="resource_type"),_safe_id(resource_id,field="resource_id"),max(int(base_revision),0),_bounded_json(draft,field="draft"),now,now))
        return {"draft_id":draft_id,"workspace_id":workspace_id,"resource_type":resource_type,"resource_id":resource_id,"base_revision":base_revision,"draft":draft,"status":"pending","created_at_utc":now}

    def list_offline_drafts(self, workspace_id: str, *, user_id: str, status: str = "pending") -> list[dict[str,Any]]:
        with self._connect() as connection:
            self._member(connection,_safe_id(workspace_id,field="workspace_id"),_safe_id(user_id,field="user_id"));rows=connection.execute("SELECT * FROM live_offline_drafts WHERE workspace_id=? AND user_id=? AND status=? ORDER BY updated_at_utc DESC",(workspace_id,user_id,_clean_text(status,maximum=40,field="status"))).fetchall()
        return [{**dict(row),"draft":_decode(row["draft_json"],{})} for row in rows]

    def sync_offline_draft(self, draft_id: str, *, user_id: str, current_revision: int) -> dict[str,Any]:
        with self._connect() as connection:
            row=connection.execute("SELECT * FROM live_offline_drafts WHERE draft_id=?",(_safe_id(draft_id,field="draft_id"),)).fetchone()
            if row is None: raise KeyError(draft_id)
            if str(row["user_id"])!=_safe_id(user_id,field="user_id"): raise PermissionDenied("Draft belongs to another member.")
            if int(row["base_revision"])!=int(current_revision):
                connection.execute("UPDATE live_offline_drafts SET status='conflict',updated_at_utc=? WHERE draft_id=?",(utc_text(),draft_id))
                raise RevisionConflict("Offline draft conflicts with a newer server revision.",current_revision=int(current_revision))
            connection.execute("UPDATE live_offline_drafts SET status='ready_to_apply',synced_at_utc=?,updated_at_utc=? WHERE draft_id=?",(utc_text(),utc_text(),draft_id))
        return {**dict(row),"draft":_decode(row["draft_json"],{}),"status":"ready_to_apply"}

    def list_activity_filtered(self, workspace_id: str, *, actor_user_id: str, event_type: str = "", actor_user: str = "", after_event_id: int = 0, limit: int = 200) -> list[dict[str,Any]]:
        clauses=["workspace_id=?","event_id>?"];params:list[Any]=[_safe_id(workspace_id,field="workspace_id"),max(int(after_event_id),0)]
        if event_type: clauses.append("event_type=?");params.append(_clean_text(event_type,maximum=100,field="event_type"))
        if actor_user: clauses.append("actor_user_id=?");params.append(_safe_id(actor_user,field="actor_user"))
        params.append(min(max(int(limit),1),1000))
        with self._connect() as connection:
            self._member(connection,workspace_id,_safe_id(actor_user_id,field="actor_user_id"));rows=connection.execute(f"SELECT * FROM live_activity_events WHERE {' AND '.join(clauses)} ORDER BY event_id ASC LIMIT ?",tuple(params)).fetchall()
        return [{**dict(row),"detail":_decode(row["detail_json"],{})} for row in rows]

    _DELETABLE_TABLES = {
        "task": ("live_tasks", "task_id"),
        "bookmark": ("live_bookmarks", "bookmark_id"),
        "annotation": ("live_annotations", "annotation_id"),
        "project_link": ("live_project_links", "link_id"),
        "timeline": ("live_timeline_events", "timeline_id"),
    }

    def soft_delete_item(self, *, workspace_id: str, user_id: str, item_type: str, item_id: str) -> dict[str, Any]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        user_id = _safe_id(user_id, field="user_id")
        item_type = str(item_type).strip().lower()
        if item_type not in self._DELETABLE_TABLES:
            raise ValueError("Unsupported recoverable item type.")
        table, key = self._DELETABLE_TABLES[item_type]
        item_id = _safe_id(item_id, field="item_id")
        now = utc_text()
        with self._connect() as connection:
            member = self._require(connection, workspace_id, user_id, self.WRITE_ROLES)
            row = connection.execute(f"SELECT * FROM {table} WHERE workspace_id=? AND {key}=?", (workspace_id, item_id)).fetchone()
            if row is None:
                raise KeyError(item_id)
            snapshot = dict(row)
            connection.execute(f"UPDATE {table} SET deleted_at_utc=? WHERE workspace_id=? AND {key}=?", (now, workspace_id, item_id))
            deleted_item_id = f"deleted-{uuid4().hex}"
            connection.execute("INSERT INTO live_deleted_items(deleted_item_id,workspace_id,item_type,item_id,snapshot_json,deleted_by,deleted_at_utc) VALUES(?,?,?,?,?,?,?)", (deleted_item_id, workspace_id, item_type, item_id, _bounded_json(snapshot, field="deleted snapshot"), user_id, now))
            self._activity(connection, workspace_id, user_id, str(member["display_name"]), "item_deleted", f"Moved {item_type} to recoverable trash", object_type=item_type, object_id=item_id)
        return {"deleted_item_id": deleted_item_id, "workspace_id": workspace_id, "item_type": item_type, "item_id": item_id, "deleted_at_utc": now}

    def list_deleted_items(self, workspace_id: str, *, actor_user_id: str, include_restored: bool = False) -> list[dict[str, Any]]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        with self._connect() as connection:
            self._require(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"), self.ADMIN_ROLES)
            rows = connection.execute("SELECT * FROM live_deleted_items WHERE workspace_id=?" + ("" if include_restored else " AND restored_at_utc IS NULL") + " ORDER BY deleted_at_utc DESC", (workspace_id,)).fetchall()
        return [{**dict(row), "snapshot": _decode(row["snapshot_json"], {})} for row in rows]

    def restore_deleted_item(self, deleted_item_id: str, *, actor_user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM live_deleted_items WHERE deleted_item_id=?", (_safe_id(deleted_item_id, field="deleted_item_id"),)).fetchone()
            if row is None:
                raise KeyError(deleted_item_id)
            if row["restored_at_utc"]:
                raise ValueError("Item has already been restored.")
            workspace_id = str(row["workspace_id"])
            actor = self._require(connection, workspace_id, _safe_id(actor_user_id, field="actor_user_id"), self.ADMIN_ROLES)
            item_type = str(row["item_type"])
            if item_type not in self._DELETABLE_TABLES:
                raise ValueError("Unsupported recoverable item type.")
            table, key = self._DELETABLE_TABLES[item_type]
            cursor = connection.execute(f"UPDATE {table} SET deleted_at_utc=NULL WHERE workspace_id=? AND {key}=?", (workspace_id, str(row["item_id"])))
            if cursor.rowcount != 1:
                raise KeyError(str(row["item_id"]))
            now = utc_text()
            connection.execute("UPDATE live_deleted_items SET restored_at_utc=?,restored_by=? WHERE deleted_item_id=?", (now, actor_user_id, deleted_item_id))
            self._activity(connection, workspace_id, actor_user_id, str(actor["display_name"]), "item_restored", f"Restored {item_type} from trash", object_type=item_type, object_id=str(row["item_id"]))
            connection.commit()
        return {"deleted_item_id": deleted_item_id, "workspace_id": workspace_id, "item_type": item_type, "item_id": str(row["item_id"]), "restored_at_utc": now}

    # --- backup, restore and health ------------------------------------------------------------
    _BACKUP_TABLES = (
        "live_workspaces","live_workspace_members","live_member_profiles","live_comments","live_comment_threads","live_comment_revisions",
        "live_review_requests","live_record_versions","live_shared_jobs","live_activity_events","live_notifications","live_tasks","live_bookmarks",
        "live_annotations","live_annotation_revisions","live_project_links","live_timeline_events","live_collaboration_sessions","live_collaboration_participants",
        "live_notification_preferences","live_job_actions",
    )

    def export_workspace_backup(self, workspace_id: str, *, actor_user_id: str) -> tuple[bytes, dict[str,Any]]:
        workspace_id=_safe_id(workspace_id,field="workspace_id");actor_user_id=_safe_id(actor_user_id,field="actor_user_id")
        with self._connect() as connection:
            member=self._require(connection,workspace_id,actor_user_id,self.ADMIN_ROLES)
            data:dict[str,Any]={}
            for table in self._BACKUP_TABLES:
                columns={str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
                if "workspace_id" in columns:
                    rows=connection.execute(f"SELECT * FROM {table} WHERE workspace_id=?",(workspace_id,)).fetchall()
                elif table=="live_comment_threads":
                    rows=connection.execute("SELECT t.* FROM live_comment_threads t JOIN live_comments c ON c.comment_id=t.comment_id WHERE c.workspace_id=?",(workspace_id,)).fetchall()
                elif table=="live_comment_revisions":
                    rows=connection.execute("SELECT r.* FROM live_comment_revisions r JOIN live_comments c ON c.comment_id=r.comment_id WHERE c.workspace_id=?",(workspace_id,)).fetchall()
                elif table=="live_annotation_revisions":
                    rows=connection.execute("SELECT r.* FROM live_annotation_revisions r JOIN live_annotations a ON a.annotation_id=r.annotation_id WHERE a.workspace_id=?",(workspace_id,)).fetchall()
                elif table=="live_collaboration_participants":
                    rows=connection.execute("SELECT p.* FROM live_collaboration_participants p JOIN live_collaboration_sessions s ON s.collaboration_session_id=p.collaboration_session_id WHERE s.workspace_id=?",(workspace_id,)).fetchall()
                else:
                    rows=[]
                data[table]=[dict(row) for row in rows]
        export={"schema":"biointel.live-workspace.backup.v1","workspace_id":workspace_id,"exported_at_utc":utc_text(),"tables":data}
        payload=json.dumps(export,ensure_ascii=False,sort_keys=True,indent=2,default=str).encode("utf-8")
        manifest={"schema":"biointel.live-workspace.backup-manifest.v1","workspace_id":workspace_id,"exported_at_utc":export["exported_at_utc"],"payload_file":"workspace.json","payload_sha256":_sha256(payload),"table_counts":{key:len(value) for key,value in data.items()}}
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            archive.writestr("workspace.json",payload);archive.writestr("manifest.json",json.dumps(manifest,indent=2,sort_keys=True).encode("utf-8"))
        archive_bytes=buffer.getvalue();archive_hash=_sha256(archive_bytes);backup_id=f"backup-{uuid4().hex}";file_name=f"BioIntel-Live-Workspace-{workspace_id}-{datetime.now():%Y%m%d-%H%M%S}.zip"
        with self._connect() as connection:
            connection.execute("INSERT INTO live_workspace_backups(backup_id,workspace_id,created_by,archive_sha256,created_at_utc,file_name,size_bytes) VALUES(?,?,?,?,?,?,?)",(backup_id,workspace_id,actor_user_id,archive_hash,utc_text(),file_name,len(archive_bytes)))
            self._activity(connection,workspace_id,actor_user_id,str(member["display_name"]),"workspace_backup_created","Created an integrity-protected workspace backup",object_type="backup",object_id=backup_id)
        return archive_bytes,{**manifest,"backup_id":backup_id,"file_name":file_name,"archive_sha256":archive_hash,"size_bytes":len(archive_bytes)}

    @staticmethod
    def inspect_workspace_backup(archive_bytes: bytes) -> dict[str,Any]:
        if len(archive_bytes)>256*1024*1024: raise ValueError("Backup archive exceeds the 256 MB collaboration safety limit.")
        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes),"r") as archive:
                names=set(archive.namelist())
                if names!={"workspace.json","manifest.json"}: raise ValueError("Backup archive contains unexpected files.")
                if any(Path(name).is_absolute() or ".." in Path(name).parts for name in names): raise ValueError("Backup archive contains unsafe paths.")
                payload=archive.read("workspace.json");manifest=json.loads(archive.read("manifest.json"))
        except (zipfile.BadZipFile,json.JSONDecodeError,KeyError) as exc:
            raise ValueError("Backup archive is invalid.") from exc
        if _sha256(payload)!=str(manifest.get("payload_sha256","")): raise ValueError("Backup payload checksum does not match its manifest.")
        export=json.loads(payload)
        if export.get("schema")!="biointel.live-workspace.backup.v1": raise ValueError("Unsupported backup schema.")
        return {"valid":True,"manifest":manifest,"workspace":export}

    def restore_workspace_backup(self, archive_bytes: bytes, *, actor_user_id: str, new_name: str | None = None) -> dict[str,Any]:
        inspected=self.inspect_workspace_backup(archive_bytes);export=inspected["workspace"];tables=export.get("tables",{})
        original_rows=tables.get("live_workspaces",[])
        if len(original_rows)!=1: raise ValueError("Backup must contain exactly one workspace.")
        original=original_rows[0];new_id=f"ws-{uuid4().hex}";now=utc_text();join_code=self.generate_join_code()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT INTO live_workspaces(workspace_id,tenant_id,name,description,status,access_code_hash,default_join_role,created_by,created_at_utc,updated_at_utc,settings_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(new_id,str(original.get("tenant_id","default")),_clean_text(new_name or f"{original.get('name','Workspace')} (Restored)",maximum=120,field="name",allow_empty=False),str(original.get("description","")),"active",_hash_secret(join_code),str(original.get("default_join_role","researcher")),_safe_id(actor_user_id,field="actor_user_id"),now,now,str(original.get("settings_json","{}"))))
            connection.execute("INSERT INTO live_workspace_members(workspace_id,user_id,display_name,role,enabled,joined_at_utc,updated_at_utc) VALUES(?,?,?,?,1,?,?)",(new_id,actor_user_id,"Restoring owner","owner",now,now))
            # Safe restore deliberately imports coordination records with regenerated IDs and the restoring owner.
            counts={"tasks":0,"bookmarks":0,"timeline":0,"project_links":0,"annotations":0}
            for row in tables.get("live_tasks",[]):
                connection.execute("INSERT INTO live_tasks(task_id,workspace_id,project_id,resource_type,resource_id,title,description,status,priority,assigned_to,created_by,due_at_utc,created_at_utc,updated_at_utc,completed_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(f"task-{uuid4().hex}",new_id,str(row.get("project_id","")),str(row.get("resource_type","")),str(row.get("resource_id","")),str(row.get("title","")),str(row.get("description","")),str(row.get("status","backlog")),str(row.get("priority","normal")),"",actor_user_id,row.get("due_at_utc"),now,now,row.get("completed_at_utc")));counts["tasks"]+=1
            for row in tables.get("live_bookmarks",[]):
                connection.execute("INSERT INTO live_bookmarks(bookmark_id,workspace_id,project_id,kind,title,safe_reference,source_name,evidence_level,notes,added_by,created_at_utc,last_checked_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(f"bookmark-{uuid4().hex}",new_id,str(row.get("project_id","")),str(row.get("kind","reference")),str(row.get("title","")),str(row.get("safe_reference","")),str(row.get("source_name","")),str(row.get("evidence_level","ungraded")),str(row.get("notes","")),actor_user_id,now,row.get("last_checked_at_utc")));counts["bookmarks"]+=1
            for row in tables.get("live_timeline_events",[]):
                connection.execute("INSERT INTO live_timeline_events(timeline_id,workspace_id,project_id,subject_alias,event_type,title,safe_detail,occurred_at_utc,created_by,created_at_utc,system_generated) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(f"timeline-{uuid4().hex}",new_id,str(row.get("project_id","")),str(row.get("subject_alias","")),str(row.get("event_type","restored")),str(row.get("title","")),str(row.get("safe_detail","")),str(row.get("occurred_at_utc",now)),actor_user_id,now,int(row.get("system_generated",0))));counts["timeline"]+=1
            for row in tables.get("live_project_links",[]):
                connection.execute("INSERT INTO live_project_links(link_id,workspace_id,project_id,subject_alias,module_key,resource_type,resource_id,title,created_by,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?)",(f"link-{uuid4().hex}",new_id,str(row.get("project_id","")),str(row.get("subject_alias","")),str(row.get("module_key","restored")),str(row.get("resource_type","RESOURCE")),str(row.get("resource_id","RESTORED")),str(row.get("title","")),actor_user_id,now));counts["project_links"]+=1
            for row in tables.get("live_annotations",[]):
                annotation_id=f"annotation-{uuid4().hex}"
                connection.execute("INSERT INTO live_annotations(annotation_id,workspace_id,project_id,resource_type,resource_id,annotation_type,label,status,confidence,geometry_json,attributes_json,created_by,created_at_utc,updated_by,updated_at_utc,revision) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",(annotation_id,new_id,str(row.get("project_id","")),str(row.get("resource_type","RESOURCE")),str(row.get("resource_id","RESTORED")),str(row.get("annotation_type","restored")),str(row.get("label","Restored annotation")),str(row.get("status","draft")),row.get("confidence"),str(row.get("geometry_json","{}")),str(row.get("attributes_json","{}")),actor_user_id,now,actor_user_id,now));counts["annotations"]+=1
            self._activity(connection,new_id,actor_user_id,"Restoring owner","workspace_restored","Restored collaboration workspace from an integrity-checked backup",object_type="workspace",object_id=new_id,detail=counts)
            connection.commit()
        return {"workspace_id":new_id,"join_code":join_code,"restored_counts":counts,"source_workspace_id":str(original.get("workspace_id",""))}

    def prune_retention(self, workspace_id: str, *, actor_user_id: str) -> dict[str, int]:
        workspace_id = _safe_id(workspace_id, field="workspace_id")
        actor_user_id = _safe_id(actor_user_id, field="actor_user_id")
        settings = self.workspace_settings(workspace_id, actor_user_id=actor_user_id)
        retention_days = min(max(int(settings.get("retention_days", 365)), 7), 3650)
        cutoff = utc_text(utc_now() - timedelta(days=retention_days))
        now = utc_text()
        with self._connect() as connection:
            actor = self._require(connection, workspace_id, actor_user_id, self.ADMIN_ROLES)
            counts = {
                "expired_presence": int(connection.execute("DELETE FROM live_presence_sessions WHERE workspace_id=? AND expires_at_utc<=?", (workspace_id, now)).rowcount),
                "expired_locks": int(connection.execute("DELETE FROM live_record_locks WHERE workspace_id=? AND expires_at_utc<=?", (workspace_id, now)).rowcount),
                "expired_account_sessions": int(connection.execute("DELETE FROM live_account_sessions WHERE workspace_id=? AND expires_at_utc<=?", (workspace_id, now)).rowcount),
                "expired_invites": int(connection.execute("DELETE FROM live_workspace_invites WHERE workspace_id=? AND expires_at_utc<=?", (workspace_id, cutoff)).rowcount),
                "old_read_notifications": int(connection.execute("DELETE FROM live_notifications WHERE workspace_id=? AND read_at_utc IS NOT NULL AND created_at_utc<?", (workspace_id, cutoff)).rowcount),
                "old_activity_events": int(connection.execute("DELETE FROM live_activity_events WHERE workspace_id=? AND created_at_utc<?", (workspace_id, cutoff)).rowcount),
                "old_restored_trash": int(connection.execute("DELETE FROM live_deleted_items WHERE workspace_id=? AND restored_at_utc IS NOT NULL AND restored_at_utc<?", (workspace_id, cutoff)).rowcount),
            }
            self._activity(connection, workspace_id, actor_user_id, str(actor["display_name"]), "retention_cleanup", "Applied workspace retention policy", detail={"retention_days": retention_days, **counts})
        return {"retention_days": retention_days, **counts}

    def admin_health(self, workspace_id: str, *, actor_user_id: str) -> dict[str,Any]:
        workspace_id=_safe_id(workspace_id,field="workspace_id")
        with self._connect() as connection:
            self._require(connection,workspace_id,_safe_id(actor_user_id,field="actor_user_id"),self.ADMIN_ROLES)
            integrity=str(connection.execute("PRAGMA integrity_check").fetchone()[0]);wal=str(connection.execute("PRAGMA journal_mode").fetchone()[0]);page_count=int(connection.execute("PRAGMA page_count").fetchone()[0]);page_size=int(connection.execute("PRAGMA page_size").fetchone()[0])
            counts={}
            for table in ("live_workspace_members","live_presence_sessions","live_record_locks","live_tasks","live_bookmarks","live_annotations","live_review_requests","live_notifications","live_shared_jobs"):
                counts[table]=int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE workspace_id=?",(workspace_id,)).fetchone()[0])
            stale_sessions=int(connection.execute("SELECT COUNT(*) FROM live_account_sessions WHERE workspace_id=? AND (revoked_at_utc IS NOT NULL OR expires_at_utc<=?)",(workspace_id,utc_text())).fetchone()[0])
        return {"database_integrity":integrity,"journal_mode":wal,"database_size_bytes":page_count*page_size,"counts":counts,"stale_account_sessions":stale_sessions,"generated_at_utc":utc_text()}

    def dashboard(self, workspace_id: str, *, actor_user_id: str) -> dict[str,Any]:
        base=super().dashboard(workspace_id,actor_user_id=actor_user_id)
        with self._connect() as connection:
            tasks=int(connection.execute("SELECT COUNT(*) FROM live_tasks WHERE workspace_id=? AND deleted_at_utc IS NULL AND status NOT IN ('done','cancelled')",(workspace_id,)).fetchone()[0])
            annotations=int(connection.execute("SELECT COUNT(*) FROM live_annotations WHERE workspace_id=? AND deleted_at_utc IS NULL",(workspace_id,)).fetchone()[0])
            active_sessions=int(connection.execute("SELECT COUNT(*) FROM live_collaboration_sessions WHERE workspace_id=? AND status!='ended'",(workspace_id,)).fetchone()[0])
            unread=int(connection.execute("SELECT COUNT(*) FROM live_notifications WHERE workspace_id=? AND user_id=? AND read_at_utc IS NULL",(workspace_id,actor_user_id)).fetchone()[0])
        return {**base,"open_tasks":tasks,"annotations":annotations,"collaboration_sessions":active_sessions,"unread_notifications":unread}


__all__=["LiveWorkspaceAdvancedStore"]
