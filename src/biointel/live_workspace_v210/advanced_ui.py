from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

import pandas as pd
import streamlit as st

from biointel.security.ui_user_store import public_local_ui_users, set_local_ui_user_enabled, upsert_local_ui_user
from biointel.ui.runtime_guard import write_runtime_error
from biointel.ui.navigation import PAGE_CATALOG

from .advanced import LiveWorkspaceAdvancedStore
from .core import PermissionDenied, RecordLocked, RevisionConflict, load_host_config, save_host_config

ActiveContext = tuple[LiveWorkspaceAdvancedStore, str, str, str, str]


def _page_path_for_key(page_key: str) -> str:
    normalized = str(page_key or "").strip()
    for page in PAGE_CATALOG:
        if page.key == normalized:
            return page.path
    return ""


def _call(context: str, fn: Callable[..., Any], *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except RevisionConflict as exc:
        st.warning(f"Conflict detected. Latest revision is {exc.current_revision}; reload or save a separate draft.")
    except (PermissionDenied, RecordLocked, ValueError, KeyError) as exc:
        st.warning(str(exc))
    except Exception as exc:
        error_id, _ = write_runtime_error(f"live_workspace_v215.{context}", exc)
        st.error(f"Collaboration operation stopped safely · {error_id}")
    return None


def render_profile(active: ActiveContext) -> None:
    store, workspace_id, user_id, session_id, _display_name = active
    st.subheader("My collaboration status")
    profile = _call("profile", store.get_member_profile, workspace_id, user_id=user_id) or {}
    c1, c2 = st.columns(2)
    availability_options = ["available", "busy", "reviewing", "running", "do_not_disturb", "away"]
    current = str(profile.get("availability", "available"))
    with c1:
        availability = st.selectbox("Availability", availability_options, index=availability_options.index(current) if current in availability_options else 0)
        visibility = st.selectbox("Presence visibility", ["workspace", "module_only", "hidden"], index=["workspace", "module_only", "hidden"].index(str(profile.get("presence_visibility", "workspace"))))
    with c2:
        status_message = st.text_input("Status message", value=str(profile.get("status_message", "")), max_chars=140)
        notification_mode = st.selectbox("Notification mode", ["all", "mentions", "muted"], index=["all", "mentions", "muted"].index(str(profile.get("notification_mode", "all"))))
    if st.button("Update my status", width="stretch"):
        if _call("update_profile", store.update_member_profile, workspace_id, user_id=user_id, availability=availability, status_message=status_message, presence_visibility=visibility, notification_mode=notification_mode):
            st.success("Status updated.")
            st.rerun()

    sessions = _call("my_sessions", store.list_account_sessions, workspace_id, actor_user_id=user_id) or []
    with st.expander("My signed-in browser sessions", expanded=False):
        if sessions:
            frame = pd.DataFrame(sessions)
            st.dataframe(frame[["account_session_id", "client_label", "auth_source", "last_seen_at_utc", "expires_at_utc", "revoked_at_utc"]], hide_index=True, width="stretch")
            other = [item for item in sessions if item["account_session_id"] != session_id and not item.get("revoked_at_utc")]
            if other:
                labels = {f"{item['client_label']} · {item['last_seen_at_utc']}": item["account_session_id"] for item in other}
                selected = st.selectbox("Session to sign out", list(labels))
                if st.button("Sign out selected session"):
                    if _call("revoke_session", store.revoke_account_session, labels[selected], actor_user_id=user_id):
                        st.success("Session revoked.")
                        st.rerun()
        else:
            st.info("No account sessions recorded yet.")


def render_collaboration_sessions(active: ActiveContext, *, page_key: str = "", page_title: str = "", resource_type: str = "", resource_id: str = "") -> None:
    store, workspace_id, user_id, _session_id, _display_name = active
    st.subheader("Collaborative review sessions")
    st.caption("Follow a team lead inside BioIntel without screen sharing. Only page, safe record alias and optional scientific pointer coordinates are synchronized.")
    with st.form("create_collab_session"):
        title = st.text_input("Session title", placeholder="Parkinson Imaging Review", max_chars=200)
        sync_navigation = st.checkbox("Synchronize module and record navigation", value=True)
        submitted = st.form_submit_button("Start collaborative session", width="stretch")
    if submitted:
        session = _call("create_collab_session", store.create_collaboration_session, workspace_id=workspace_id, user_id=user_id, title=title, sync_navigation=sync_navigation)
        if session:
            st.success("Collaborative session started.")
            st.rerun()

    sessions = _call("list_collab_sessions", store.list_collaboration_sessions, workspace_id, actor_user_id=user_id) or []
    for session in sessions:
        with st.expander(f"{session['title']} · {session['status']}", expanded=False):
            st.caption(f"Host: {session['host_user_id']} · Updated: {session['updated_at_utc']}")
            st.write(f"Current location: **{session.get('page_title') or session.get('page_key') or 'Not selected'}**")
            record = f"{session.get('resource_type','')} {session.get('resource_id','')}".strip()
            if record:
                st.write(f"Record: `{record}`")
            if session.get("cursor"):
                st.caption("Shared scientific pointer / selection")
                st.json(session["cursor"])
            host_page_path = _page_path_for_key(str(session.get("page_key", "")))
            if host_page_path:
                st.page_link(host_page_path, label="Open host module", width="stretch")
            c1, c2, c3 = st.columns(3)
            if c1.button("Join / follow", key=f"join_collab_{session['collaboration_session_id']}"):
                if _call("join_collab", store.join_collaboration_session, session["collaboration_session_id"], user_id=user_id, follow_host=True):
                    st.success("Joined session.")
                    st.rerun()
            if str(session.get("host_user_id")) == user_id:
                if c2.button("Share current location", key=f"share_nav_{session['collaboration_session_id']}"):
                    if _call("update_nav", store.update_collaboration_navigation, session["collaboration_session_id"], user_id=user_id, page_key=page_key or "live-workspace", page_title=page_title or "BioIntel Live Workspace", resource_type=resource_type, resource_id=resource_id, cursor={}):
                        st.success("Navigation shared.")
                        st.rerun()
                if c3.button("End session", key=f"end_collab_{session['collaboration_session_id']}"):
                    if _call("end_collab", store.end_collaboration_session, session["collaboration_session_id"], user_id=user_id):
                        st.success("Session ended.")
                        st.rerun()
            participants = session.get("participants") or []
            participant_ids = {str(item.get("user_id", "")) for item in participants}
            if str(session.get("host_user_id")) == user_id:
                state_action = "resume" if session.get("status") == "paused" else "pause"
                if st.button(f"{state_action.title()} session", key=f"state_collab_{session['collaboration_session_id']}"):
                    next_state = "active" if state_action == "resume" else "paused"
                    if _call("set_collab_state", store.set_collaboration_session_status, session["collaboration_session_id"], user_id=user_id, status=next_state):
                        st.success(f"Session {next_state}.")
                        st.rerun()
            elif user_id in participant_ids:
                if st.button("Leave session", key=f"leave_collab_{session['collaboration_session_id']}"):
                    if _call("leave_collab", store.leave_collaboration_session, session["collaboration_session_id"], user_id=user_id):
                        st.success("Left collaborative session.")
                        st.rerun()
            if participants:
                st.dataframe(pd.DataFrame(participants)[["display_name", "role", "follow_host", "last_seen_at_utc"]], hide_index=True, width="stretch")


def render_annotations(active: ActiveContext, *, resource_type: str, resource_id: str) -> None:
    store, workspace_id, user_id, _session_id, _display_name = active
    st.markdown("#### Scientific annotations")
    st.caption("Supports EEG events, imaging ROIs, variant evidence, biomarker candidates, histology regions and other safe review metadata. Raw files stay in their module storage.")
    if not resource_type or not resource_id:
        st.info("Set a record type and safe alias to use shared annotations.")
        return
    with st.form("create_scientific_annotation"):
        annotation_type = st.selectbox("Annotation type", ["EEG_EVENT", "IMAGE_ROI", "VARIANT_EVIDENCE", "BIOMARKER", "HISTOLOGY_REGION", "TIMELINE_EVENT", "GENERAL_NOTE"])
        label = st.text_input("Label / interpretation", max_chars=500)
        status = st.selectbox("Review status", ["draft", "needs_review", "accepted", "rejected"])
        confidence = st.slider("Research confidence", 0.0, 1.0, 0.5, 0.05)
        coordinates = st.text_area("Optional safe geometry JSON", value="{}", help="Examples: EEG time range, image ROI coordinates or selected graph node. Do not paste raw scientific arrays.")
        attributes = st.text_area("Optional attributes JSON", value="{}")
        submitted = st.form_submit_button("Add annotation", width="stretch")
    if submitted:
        try:
            geometry = json.loads(coordinates or "{}")
            attribute_payload = json.loads(attributes or "{}")
        except json.JSONDecodeError:
            st.warning("Geometry and attributes must be valid JSON objects.")
        else:
            created = _call("create_annotation", store.create_annotation, workspace_id=workspace_id, user_id=user_id, resource_type=resource_type, resource_id=resource_id, annotation_type=annotation_type, label=label, status=status, confidence=confidence, geometry=geometry, attributes=attribute_payload)
            if created:
                st.success("Annotation added with revision history.")
                st.rerun()
    annotations = _call("list_annotations", store.list_annotations, workspace_id, actor_user_id=user_id, resource_type=resource_type, resource_id=resource_id) or []
    for item in annotations:
        with st.expander(f"{item['annotation_type']} · {item['label']} · r{item['revision']}"):
            st.caption(f"Status: {item['status']} · Confidence: {item.get('confidence')} · Updated: {item['updated_at_utc']}")
            if item.get("geometry"):
                st.json(item["geometry"])
            new_status = st.selectbox("Update status", ["draft", "needs_review", "accepted", "rejected", "archived"], index=["draft", "needs_review", "accepted", "rejected", "archived"].index(item["status"]), key=f"ann_status_{item['annotation_id']}")
            new_label = st.text_input("Update label", value=item["label"], key=f"ann_label_{item['annotation_id']}")
            c1, c2 = st.columns(2)
            if c1.button("Save annotation revision", key=f"ann_save_{item['annotation_id']}"):
                if _call("update_annotation", store.update_annotation, item["annotation_id"], user_id=user_id, expected_revision=int(item["revision"]), label=new_label, status=new_status):
                    st.success("Annotation revision saved.")
                    st.rerun()
            if c2.button("Move annotation to trash", key=f"ann_delete_{item['annotation_id']}"):
                if _call("delete_annotation", store.soft_delete_item, workspace_id=workspace_id, user_id=user_id, item_type="annotation", item_id=item["annotation_id"]):
                    st.success("Annotation moved to recoverable trash.")
                    st.rerun()


    st.markdown("#### Offline-safe draft recovery")
    versions = _call("draft_record_versions", store.list_record_versions, workspace_id, actor_user_id=user_id, resource_type=resource_type, resource_id=resource_id) or []
    current_revision = int(versions[0]["revision"]) if versions else 0
    draft_text = st.text_area("Draft JSON", value="{}", key=f"offline_draft_{resource_type}_{resource_id}", help="Saved locally in the workspace database until you reconnect and pass a revision conflict check.")
    if st.button("Save recoverable draft", key=f"save_draft_{resource_type}_{resource_id}"):
        try:
            draft_payload = json.loads(draft_text or "{}")
        except json.JSONDecodeError:
            st.warning("Draft must be valid JSON.")
        else:
            if _call("save_offline_draft", store.save_offline_draft, workspace_id=workspace_id, user_id=user_id, resource_type=resource_type, resource_id=resource_id, base_revision=current_revision, draft=draft_payload):
                st.success("Draft saved for safe reconnect handling.")
                st.rerun()
    drafts = _call("list_offline_drafts", store.list_offline_drafts, workspace_id, user_id=user_id, status="pending") or []
    for draft in drafts:
        if draft["resource_type"] != resource_type or draft["resource_id"] != resource_id:
            continue
        with st.expander(f"Draft {draft['draft_id'][-8:]} · base revision {draft['base_revision']}"):
            st.json(draft.get("draft", {}))
            if st.button("Check draft against latest revision", key=f"sync_draft_{draft['draft_id']}"):
                if _call("sync_offline_draft", store.sync_offline_draft, draft["draft_id"], user_id=user_id, current_revision=current_revision):
                    st.success("No conflict detected. Draft is ready to apply through the owning module.")
                    st.rerun()


def render_tasks(active: ActiveContext) -> None:
    store, workspace_id, user_id, _session_id, _display_name = active
    st.subheader("Tasks and scientific review assignments")
    members = _call("task_members", store.list_members, workspace_id, actor_user_id=user_id) or []
    assignees = {"Unassigned": ""}
    assignees.update({f"{item['display_name']} · {item['role']}": item["user_id"] for item in members})
    with st.form("create_workspace_task"):
        title = st.text_input("Task", max_chars=200)
        description = st.text_area("Description", max_chars=4000)
        assigned_label = st.selectbox("Assign to", list(assignees))
        priority = st.selectbox("Priority", ["normal", "high", "urgent", "low"])
        project_id = st.text_input("Optional project alias", max_chars=128)
        submitted = st.form_submit_button("Create task", width="stretch")
    if submitted:
        if _call("create_task", store.create_task, workspace_id=workspace_id, user_id=user_id, title=title, description=description, assigned_to=assignees[assigned_label], priority=priority, project_id=project_id):
            st.success("Task created.")
            st.rerun()
    tasks = _call("list_tasks", store.list_tasks, workspace_id, actor_user_id=user_id) or []
    if not tasks:
        st.info("No open tasks.")
        return
    for task in tasks:
        with st.expander(f"{task['title']} · {task['status']} · {task['priority']}"):
            st.write(task.get("description") or "No description")
            st.caption(f"Assigned: {task.get('assigned_to') or 'Unassigned'} · Updated: {task['updated_at_utc']}")
            next_status = st.selectbox("Status", ["backlog", "assigned", "in_progress", "blocked", "review", "done", "cancelled"], index=["backlog", "assigned", "in_progress", "blocked", "review", "done", "cancelled"].index(task["status"]), key=f"task_status_{task['task_id']}")
            c1, c2 = st.columns(2)
            if c1.button("Update task", key=f"task_update_{task['task_id']}"):
                if _call("update_task", store.update_task, task["task_id"], user_id=user_id, status=next_status):
                    st.success("Task updated.")
                    st.rerun()
            if c2.button("Move task to trash", key=f"task_delete_{task['task_id']}"):
                if _call("delete_task", store.soft_delete_item, workspace_id=workspace_id, user_id=user_id, item_type="task", item_id=task["task_id"]):
                    st.success("Task moved to recoverable trash.")
                    st.rerun()


def render_evidence_and_timeline(active: ActiveContext) -> None:
    store, workspace_id, user_id, _session_id, _display_name = active
    evidence_tab, links_tab, timeline_tab = st.tabs(["Evidence library", "Cross-module links", "Research timeline"])
    with evidence_tab:
        with st.form("add_evidence_bookmark"):
            kind = st.selectbox("Evidence type", ["publication", "trial", "database", "target", "variant", "pathway", "brain_region", "analysis_result", "website"])
            title = st.text_input("Title", max_chars=240)
            reference = st.text_input("Safe reference / URL / result alias", max_chars=1000)
            source = st.text_input("Source", max_chars=160)
            evidence_level = st.selectbox("Evidence level", ["ungraded", "exploratory", "supporting", "replicated", "externally_validated"])
            notes = st.text_area("Notes", max_chars=3000)
            submitted = st.form_submit_button("Add to team evidence library", width="stretch")
        if submitted:
            if _call("add_bookmark", store.add_bookmark, workspace_id=workspace_id, user_id=user_id, kind=kind, title=title, safe_reference=reference, source_name=source, evidence_level=evidence_level, notes=notes):
                st.success("Evidence bookmark added.")
                st.rerun()
        bookmarks = _call("list_bookmarks", store.list_bookmarks, workspace_id, actor_user_id=user_id) or []
        if bookmarks:
            st.dataframe(pd.DataFrame(bookmarks)[["kind", "title", "safe_reference", "source_name", "evidence_level", "added_by", "created_at_utc"]], hide_index=True, width="stretch")
            bookmark_labels = {f"{item['title']} · {item['kind']}": item["bookmark_id"] for item in bookmarks}
            selected_bookmark = st.selectbox("Evidence item management", list(bookmark_labels), key="delete_evidence_bookmark")
            if st.button("Move selected evidence item to trash"):
                if _call("delete_bookmark", store.soft_delete_item, workspace_id=workspace_id, user_id=user_id, item_type="bookmark", item_id=bookmark_labels[selected_bookmark]):
                    st.success("Evidence item moved to recoverable trash.")
                    st.rerun()
    with links_tab:
        with st.form("add_project_link"):
            project = st.text_input("Project alias", max_chars=128)
            subject = st.text_input("Optional subject alias", max_chars=128)
            module = st.text_input("Module key", max_chars=128)
            resource_type = st.text_input("Resource type", max_chars=128)
            resource_id = st.text_input("Resource alias", max_chars=128)
            title = st.text_input("Link title", max_chars=240)
            submitted = st.form_submit_button("Link across modules", width="stretch")
        if submitted:
            if _call("add_project_link", store.add_project_link, workspace_id=workspace_id, user_id=user_id, project_id=project, subject_alias=subject, module_key=module, resource_type=resource_type, resource_id=resource_id, title=title):
                st.success("Cross-module link added.")
                st.rerun()
        links = _call("list_links", store.list_project_links, workspace_id, actor_user_id=user_id) or []
        if links:
            st.dataframe(pd.DataFrame(links)[["project_id", "subject_alias", "module_key", "resource_type", "resource_id", "title", "created_at_utc"]], hide_index=True, width="stretch")
            link_labels = {f"{item['title']} · {item['module_key']}": item["link_id"] for item in links}
            selected_link = st.selectbox("Cross-module link management", list(link_labels), key="delete_project_link")
            if st.button("Move selected link to trash"):
                if _call("delete_project_link", store.soft_delete_item, workspace_id=workspace_id, user_id=user_id, item_type="project_link", item_id=link_labels[selected_link]):
                    st.success("Cross-module link moved to recoverable trash.")
                    st.rerun()
    with timeline_tab:
        with st.form("add_timeline_event"):
            project = st.text_input("Project alias", key="timeline_project", max_chars=128)
            subject = st.text_input("Subject alias", key="timeline_subject", max_chars=128)
            event_type = st.selectbox("Event type", ["dataset_uploaded", "analysis_completed", "review", "decision", "milestone", "error_resolved", "custom"])
            title = st.text_input("Timeline title", key="timeline_title", max_chars=240)
            detail = st.text_area("Safe detail", key="timeline_detail", max_chars=3000)
            submitted = st.form_submit_button("Add timeline event", width="stretch")
        if submitted:
            if _call("add_timeline", store.add_timeline_event, workspace_id=workspace_id, user_id=user_id, event_type=event_type, title=title, safe_detail=detail, project_id=project, subject_alias=subject):
                st.success("Timeline event added.")
                st.rerun()
        rows = _call("list_timeline", store.list_timeline, workspace_id, actor_user_id=user_id) or []
        for item in rows[:100]:
            st.markdown(f"**{item['title']}** · {item['event_type']}")
            if item.get("safe_detail"):
                st.write(item["safe_detail"])
            c1, c2 = st.columns([5, 1])
            c1.caption(f"{item['occurred_at_utc']} · project {item.get('project_id') or '—'} · subject {item.get('subject_alias') or '—'}")
            if c2.button("Trash", key=f"timeline_delete_{item['timeline_id']}"):
                if _call("delete_timeline", store.soft_delete_item, workspace_id=workspace_id, user_id=user_id, item_type="timeline", item_id=item["timeline_id"]):
                    st.success("Timeline event moved to recoverable trash.")
                    st.rerun()


def render_notifications(active: ActiveContext) -> None:
    store, workspace_id, user_id, _session_id, _display_name = active
    st.subheader("Notification centre")
    preferences = _call("get_notification_prefs", store.get_notification_preferences, workspace_id, user_id=user_id) or {}
    c1, c2, c3 = st.columns(3)
    muted = c1.toggle("Mute workspace", value=bool(preferences.get("muted", 0)))
    mention_only = c2.toggle("Mentions only", value=bool(preferences.get("mention_only", 0)))
    browser = c3.toggle("Browser notifications", value=bool(preferences.get("browser_notifications", 0)), help="Browser permission is still controlled by your browser.")
    if st.button("Save notification preferences"):
        _call("notification_prefs", store.update_notification_preferences, workspace_id, user_id=user_id, muted=muted, mention_only=mention_only, browser_notifications=browser)
        st.success("Notification preferences saved.")
    notifications = _call("notifications", store.list_notifications, workspace_id, user_id=user_id, unread_only=False) or []
    if st.button("Mark all as read", disabled=not notifications):
        count = _call("mark_all_read", store.mark_all_notifications_read, workspace_id, user_id=user_id)
        if count is not None:
            st.success(f"Marked {count} notification(s) as read.")
            st.rerun()
    for item in notifications:
        marker = "●" if not item.get("read_at_utc") else "○"
        st.markdown(f"{marker} **{item['title']}** — {item['body']}")
        st.caption(item["created_at_utc"])


def render_advanced_admin(active: ActiveContext) -> None:
    store, workspace_id, user_id, _session_id, _display_name = active
    member = _call("advanced_admin_member", store.get_member, workspace_id, user_id)
    if not member or member.get("role") not in {"owner", "admin"}:
        st.info("Owner or Admin role is required for advanced controls.")
        return

    settings_tab, invites_tab, accounts_tab, access_tab, backup_tab, trash_tab, health_tab = st.tabs([
        "Privacy settings", "Invites", "Login accounts", "Member access", "Backup & recovery", "Trash recovery", "Health"
    ])
    with settings_tab:
        settings = _call("workspace_settings", store.workspace_settings, workspace_id, actor_user_id=user_id) or {}
        private = st.toggle("Private workspace", value=bool(settings.get("private", True)))
        mask = st.toggle("Mask sensitive record titles", value=bool(settings.get("mask_record_titles", True)))
        guest = st.toggle("Allow guest access", value=bool(settings.get("guest_access", False)))
        external = st.toggle("Allow optional external website access", value=bool(settings.get("external_web_access", False)))
        presence = st.selectbox("Presence detail", ["module_only", "record_alias", "hidden"], index=["module_only", "record_alias", "hidden"].index(str(settings.get("presence_detail", "record_alias"))))
        activity = st.selectbox("Activity detail", ["minimal", "standard", "detailed"], index=["minimal", "standard", "detailed"].index(str(settings.get("activity_detail", "standard"))))
        retention = st.number_input("Activity retention days", 7, 3650, int(settings.get("retention_days", 365)))
        if st.button("Save privacy settings", width="stretch"):
            if _call("update_settings", store.update_workspace_settings, workspace_id, actor_user_id=user_id, settings={"private": private, "mask_record_titles": mask, "guest_access": guest, "external_web_access": external, "presence_detail": presence, "activity_detail": activity, "retention_days": retention}):
                st.success("Workspace settings updated.")
                st.rerun()
    with invites_tab:
        with st.form("create_advanced_invite"):
            role = st.selectbox("Invite role", ["researcher", "reviewer", "viewer", "admin"])
            expires = st.number_input("Expires after hours", 1, 720, 24)
            max_uses = st.number_input("Maximum uses", 1, 100, 1)
            note = st.text_input("Invite note", max_chars=500)
            submitted = st.form_submit_button("Create secure invite", width="stretch")
        if submitted:
            invite = _call("create_invite", store.create_invite, workspace_id, actor_user_id=user_id, role=role, note=note, expires_hours=expires, max_uses=max_uses)
            if invite:
                st.success("Copy this token now. Only its secure hash is stored.")
                st.code(f"Workspace: {workspace_id}\nInvite token: {invite['token']}")
        invites = _call("list_invites", store.list_invites, workspace_id, actor_user_id=user_id) or []
        if invites:
            st.dataframe(pd.DataFrame(invites)[["invite_id", "role", "expires_at_utc", "max_uses", "use_count", "active", "revoked_at_utc"]], hide_index=True, width="stretch")
            active_invites = [item for item in invites if item.get("active")]
            if active_invites:
                invite_labels = {f"{item['role']} · expires {item['expires_at_utc']} · {item['invite_id'][-8:]}": item["invite_id"] for item in active_invites}
                selected_invite = st.selectbox("Active invite", list(invite_labels), key="revoke_live_invite")
                if st.button("Revoke selected invite"):
                    if _call("revoke_invite", store.revoke_invite, invite_labels[selected_invite], actor_user_id=user_id):
                        st.success("Invite revoked immediately.")
                        st.rerun()
    with accounts_tab:
        st.warning("LAN Host Mode should use named password-protected accounts. Passwords are stored only as PBKDF2 hashes in local UserData.")
        with st.form("create_local_ui_account"):
            username = st.text_input("Username", max_chars=64)
            display_name = st.text_input("Display name", max_chars=120)
            role = st.selectbox("Application role", ["researcher", "reviewer", "viewer", "admin"])
            password = st.text_input("Password (minimum 12 characters)", type="password")
            confirmation = st.text_input("Confirm password", type="password")
            enable_totp = st.checkbox("Enable authenticator-app two-factor login")
            submitted = st.form_submit_button("Create / update account", width="stretch")
        if submitted:
            if password != confirmation:
                st.warning("Passwords do not match.")
            else:
                result = _call("create_ui_account", upsert_local_ui_user, username=username, display_name=display_name, role=role, password=password, enabled=True, totp_enabled=enable_totp)
                if result:
                    st.success("Local UI account saved. Restart BioIntel after enabling LAN Host Mode.")
                    if result.get("totp_enabled") and result.get("totp_secret"):
                        st.warning("Add this secret to the user's authenticator app now. It is intentionally shown only during account update.")
                        st.code(result["totp_secret"])
        users = public_local_ui_users()
        if users:
            st.dataframe(pd.DataFrame(users), hide_index=True, width="stretch")
            labels = {f"{item['display_name']} · {item['username']} · {'enabled' if item['enabled'] else 'disabled'}": item for item in users}
            selected_label = st.selectbox("Manage local login account", list(labels), key="manage_local_login_account")
            selected_user = labels[selected_label]
            desired = st.toggle("Account enabled", value=bool(selected_user["enabled"]), key="manage_local_login_enabled")
            if st.button("Apply account status", key="apply_local_account_status"):
                if _call("set_ui_account_enabled", set_local_ui_user_enabled, selected_user["username"], enabled=desired):
                    st.success("Account status updated. Active Streamlit session expires according to the normal session policy.")
                    st.rerun()
    with access_tab:
        members = _call("access_members", store.list_members, workspace_id, actor_user_id=user_id) or []
        if members:
            member_labels = {f"{item['display_name']} · {item['role']}": item for item in members}
            selected_label = st.selectbox("Workspace member", list(member_labels), key="permission_member")
            selected_member = member_labels[selected_label]
            permissions = _call("get_member_permissions", store.get_member_permissions, workspace_id, user_id=selected_member["user_id"], actor_user_id=user_id) or {}
            categories = st.multiselect("Allowed categories (empty = unrestricted)", ["Neuro/CNS", "Bioinformatics", "Discovery", "Lab Analytics", "Operations"], default=list(permissions.get("allowed_categories", [])))
            modules_text = st.text_area("Allowed module keys, one per line (empty = unrestricted)", value="\n".join(permissions.get("allowed_modules", [])))
            projects_text = st.text_area("Allowed project aliases, one per line (empty = unrestricted)", value="\n".join(permissions.get("allowed_projects", [])))
            if st.button("Save member access limits", width="stretch"):
                modules = [item.strip() for item in modules_text.splitlines() if item.strip()]
                projects = [item.strip() for item in projects_text.splitlines() if item.strip()]
                if _call("set_member_permissions", store.set_member_permissions, workspace_id, actor_user_id=user_id, target_user_id=selected_member["user_id"], allowed_categories=categories, allowed_modules=modules, allowed_projects=projects):
                    st.success("Member access limits updated.")
                    st.rerun()
            enabled = st.toggle("Workspace membership enabled", value=bool(selected_member.get("enabled", 1)), key="workspace_member_enabled")
            if st.button("Apply membership status"):
                if _call("set_member_enabled", store.set_member_enabled, workspace_id, actor_user_id=user_id, target_user_id=selected_member["user_id"], enabled=enabled):
                    st.success("Workspace membership status updated.")
                    st.rerun()
    with backup_tab:
        archive_result = None
        if st.button("Create integrity-protected workspace backup", width="stretch"):
            archive_result = _call("create_backup", store.export_workspace_backup, workspace_id, actor_user_id=user_id)
            if archive_result:
                st.session_state["live_workspace_backup_bytes"] = archive_result[0]
                st.session_state["live_workspace_backup_manifest"] = archive_result[1]
        data = st.session_state.get("live_workspace_backup_bytes")
        manifest = st.session_state.get("live_workspace_backup_manifest")
        if data and manifest:
            st.download_button("Download workspace backup", data=data, file_name=manifest["file_name"], mime="application/zip", width="stretch")
            st.json(manifest)
        uploaded = st.file_uploader("Restore a Live Workspace backup as a new workspace", type=["zip"], key="live_workspace_restore_backup")
        restore_name = st.text_input("Restored workspace name", value="Restored BioIntel Workspace")
        if uploaded is not None:
            raw = uploaded.getvalue()
            inspection = _call("inspect_backup", store.inspect_workspace_backup, raw)
            if inspection:
                st.success("Backup checksum and schema are valid.")
                st.json(inspection["manifest"])
                if st.button("Restore as new workspace", type="primary"):
                    restored = _call("restore_backup", store.restore_workspace_backup, raw, actor_user_id=user_id, new_name=restore_name)
                    if restored:
                        st.success("Workspace restored. Save the new join code now.")
                        st.code(f"Workspace: {restored['workspace_id']}\nJoin code: {restored['join_code']}")
    with trash_tab:
        deleted = _call("list_deleted_items", store.list_deleted_items, workspace_id, actor_user_id=user_id) or []
        if not deleted:
            st.info("Recoverable trash is empty.")
        for item in deleted:
            with st.expander(f"{item['item_type']} · {item['item_id']} · deleted {item['deleted_at_utc']}"):
                st.json(item.get("snapshot", {}))
                if st.button("Restore item", key=f"restore_deleted_{item['deleted_item_id']}"):
                    if _call("restore_deleted_item", store.restore_deleted_item, item["deleted_item_id"], actor_user_id=user_id):
                        st.success("Item restored.")
                        st.rerun()
    with health_tab:
        health = _call("admin_health", store.admin_health, workspace_id, actor_user_id=user_id)
        if health:
            st.json(health)
        audit_rows = _call("audit_export", store.list_activity_filtered, workspace_id, actor_user_id=user_id, after_event_id=0, limit=1000) or []
        if audit_rows:
            audit_json = json.dumps(audit_rows, indent=2, default=str).encode("utf-8")
            audit_csv = pd.DataFrame(audit_rows).drop(columns=["detail"], errors="ignore").to_csv(index=False).encode("utf-8")
            c1, c2 = st.columns(2)
            c1.download_button("Download audit JSON", data=audit_json, file_name=f"{workspace_id}-audit.json", mime="application/json", width="stretch")
            c2.download_button("Download audit CSV", data=audit_csv, file_name=f"{workspace_id}-audit.csv", mime="text/csv", width="stretch")
        if st.button("Run retention cleanup", help="Removes only expired presence/locks/sessions and old read/audit/trash metadata according to workspace retention settings."):
            result = _call("prune_retention", store.prune_retention, workspace_id, actor_user_id=user_id)
            if result:
                st.success("Retention cleanup completed safely.")
                st.json(result)
        sessions = _call("all_sessions", store.list_account_sessions, workspace_id, actor_user_id=user_id, user_id=user_id) or []
        st.caption(f"Current administrator sessions: {len(sessions)}")
        if st.button("Sign out my other devices", disabled=len(sessions) <= 1):
            count = _call("revoke_other_sessions", store.revoke_all_account_sessions, workspace_id, actor_user_id=user_id, keep_session_id=active[3])
            if count is not None:
                st.success(f"Revoked {count} other session(s).")
                st.rerun()


__all__ = [
    "render_advanced_admin",
    "render_annotations",
    "render_collaboration_sessions",
    "render_evidence_and_timeline",
    "render_notifications",
    "render_profile",
    "render_tasks",
]
