from __future__ import annotations

import hashlib
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st

from biointel.ui.runtime_guard import write_runtime_error
from biointel.ui.access_control import current_ui_identity

from .core import LiveWorkspaceStore, PermissionDenied, RecordLocked, RevisionConflict, host_config_path, load_host_config, save_host_config
from .advanced import LiveWorkspaceAdvancedStore
from .tls import generate_lan_tls_certificate, inspect_tls_files
from .advanced_ui import (
    render_advanced_admin,
    render_annotations,
    render_collaboration_sessions,
    render_evidence_and_timeline,
    render_notifications,
    render_profile,
    render_tasks,
)

_USER_ID = "biointel_live_workspace_user_id"
_SESSION_ID = "biointel_live_workspace_session_id"
_DISPLAY_NAME = "biointel_live_workspace_display_name"
_ACTIVE_WORKSPACE = "biointel_live_workspace_active_id"
_JOIN_CODE = "biointel_live_workspace_join_code"
_RECORD_TYPE = "biointel_live_workspace_record_type"
_RECORD_ID = "biointel_live_workspace_record_id"
_ACTIVITY_STATE = "biointel_live_workspace_activity_state"
_STATUS_MESSAGE = "biointel_live_workspace_status_message"


@st.cache_resource(show_spinner=False)
def _store() -> LiveWorkspaceAdvancedStore:
    return LiveWorkspaceAdvancedStore()


def _identity() -> tuple[str, str, str]:
    ui_identity = current_ui_identity()
    stable_account = ui_identity.username and ui_identity.username != "local"
    expected_user_id = (
        "ui-" + hashlib.sha256(ui_identity.username.lower().encode("utf-8")).hexdigest()[:20]
        if stable_account
        else ""
    )
    if stable_account:
        st.session_state[_USER_ID] = expected_user_id
        st.session_state[_DISPLAY_NAME] = ui_identity.display_name
    elif _USER_ID not in st.session_state:
        st.session_state[_USER_ID] = f"user-{uuid4().hex[:20]}"
    if _SESSION_ID not in st.session_state:
        st.session_state[_SESSION_ID] = f"session-{uuid4().hex[:20]}"
    if _DISPLAY_NAME not in st.session_state:
        st.session_state[_DISPLAY_NAME] = ui_identity.display_name or "Researcher"
    return (
        str(st.session_state[_USER_ID]),
        str(st.session_state[_SESSION_ID]),
        str(st.session_state[_DISPLAY_NAME]),
    )


def _active() -> tuple[LiveWorkspaceStore, str, str, str, str] | None:
    store = _store()
    user_id, session_id, display_name = _identity()
    workspace_id = str(st.session_state.get(_ACTIVE_WORKSPACE, "")).strip()
    if not workspace_id:
        return None
    try:
        store.get_member(workspace_id, user_id)
        identity = current_ui_identity()
        store.register_account_session(
            workspace_id,
            user_id=user_id,
            account_session_id=session_id,
            client_label="Streamlit browser session",
            auth_source=identity.source,
            ttl_hours=12,
        )
    except Exception:
        return None
    return store, workspace_id, user_id, session_id, display_name


def _safe_call(context: str, function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (PermissionDenied, RecordLocked, ValueError, KeyError) as exc:
        st.warning(str(exc))
    except Exception as exc:
        error_id, _ = write_runtime_error(f"live_workspace_v210.{context}", exc)
        st.error(f"Live Workspace operation stopped safely · {error_id}")
    return None


def _private_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
            address = str(item[4][0])
            if address and not address.startswith("127.") and not address.startswith("169.254."):
                addresses.add(address)
    except OSError:
        pass
    return sorted(addresses)


def _presence_context(page_key: str, page_title: str, category: str) -> dict[str, str]:
    return {
        "page_key": page_key,
        "page_title": page_title,
        "category": category,
        "project_id": str(st.session_state.get("biointel_active_project_id", "")),
        "record_type": str(st.session_state.get(_RECORD_TYPE, "")),
        "record_id": str(st.session_state.get(_RECORD_ID, "")),
        "activity_state": str(st.session_state.get(_ACTIVITY_STATE, "viewing")),
        "status_message": str(st.session_state.get(_STATUS_MESSAGE, "")),
    }


def _heartbeat(page_key: str, page_title: str, category: str) -> dict[str, Any] | None:
    active = _active()
    if active is None:
        return None
    store, workspace_id, user_id, session_id, display_name = active
    config = load_host_config()
    return store.heartbeat(
        workspace_id=workspace_id,
        session_id=session_id,
        user_id=user_id,
        display_name=display_name,
        ttl_seconds=int(config.get("presence_ttl_seconds", 45)),
        client_label="Streamlit",
        **_presence_context(page_key, page_title, category),
    )


def _compact_presence_impl(page_key: str, page_title: str, category: str) -> None:
    active = _active()
    if active is None:
        return
    store, workspace_id, user_id, _session_id, _display_name = active
    heartbeat = _safe_call("sidebar_heartbeat", _heartbeat, page_key, page_title, category)
    if heartbeat is None:
        return
    presence = _safe_call("sidebar_presence", store.list_presence, workspace_id, actor_user_id=user_id) or []
    same_page = [item for item in presence if item.get("page_key") == page_key]
    with st.expander("BioIntel Live Workspace", expanded=False):
        c1, c2 = st.columns(2)
        c1.metric("Online", len({item.get("user_id") for item in presence}))
        c2.metric("On this module", len({item.get("user_id") for item in same_page}))
        for item in same_page[:6]:
            state = str(item.get("activity_state", "viewing")).title()
            st.caption(f"• {item.get('display_name', 'Researcher')} — {state}")
        if len(same_page) > 6:
            st.caption(f"+{len(same_page)-6} more")
        st.text_input(
            "Shared record type",
            key=_RECORD_TYPE,
            placeholder="e.g. EEG_RECORD",
            help="Use a non-identifying record type. Raw data is never shared through presence.",
        )
        st.text_input(
            "Shared record alias",
            key=_RECORD_ID,
            placeholder="e.g. EEG-018",
            help="Use a pseudonymized alias, not patient name/MRN.",
        )
        st.selectbox("Current activity", ["viewing", "editing", "reviewing", "running", "idle"], key=_ACTIVITY_STATE)
        record_type = str(st.session_state.get(_RECORD_TYPE, ""))
        record_id = str(st.session_state.get(_RECORD_ID, ""))
        if record_type and record_id:
            viewers = _safe_call(
                "sidebar_record_viewers", store.list_presence, workspace_id,
                actor_user_id=user_id, record_type=record_type, record_id=record_id,
            ) or []
            st.caption(f"Same record: {len({item.get('user_id') for item in viewers})} member(s)")
        st.page_link("pages/158_Collaboration_Scientific_Review_System_2.py", label="Open Live Workspace")


if hasattr(st, "fragment"):
    _compact_presence_fragment = st.fragment(run_every="10s")(_compact_presence_impl)
else:  # pragma: no cover - supported runtime is Streamlit 1.58
    _compact_presence_fragment = _compact_presence_impl


def render_live_workspace_sidebar(page_key: str, page_title: str, category: str) -> bool:
    """Attach privacy-safe live presence and enforce active workspace access limits.

    Returns ``False`` only when an active workspace explicitly blocks the current
    module/project. Personal mode and unrestricted memberships always return True.
    """
    active = _active()
    if active is None:
        return True
    store, workspace_id, user_id, _session_id, _display_name = active
    project_id = str(st.session_state.get("biointel_active_project_id", ""))
    allowed = _safe_call(
        "sidebar_authorize_module",
        store.authorize_module,
        workspace_id,
        user_id=user_id,
        page_key=page_key,
        category=category,
        project_id=project_id,
    )
    if allowed is not True:
        with st.sidebar.expander("BioIntel Live Workspace", expanded=True):
            st.error("Your active workspace does not permit this module or project.")
            st.caption("Switch workspace or ask an Owner/Admin to update Member access.")
        return False
    with st.sidebar:
        _compact_presence_fragment(page_key, page_title, category)
    return True


def _render_setup() -> None:
    store = _store()
    user_id, _session_id, display_name = _identity()
    st.subheader("Identity and workspace access")
    st.caption("Your display name and page/record context are shared. Uploaded scientific data is not broadcast.")
    new_name = st.text_input("Your team display name", value=display_name, max_chars=80)
    if new_name and new_name != display_name:
        st.session_state[_DISPLAY_NAME] = new_name.strip()
        display_name = new_name.strip()

    memberships = _safe_call("list_workspaces", store.list_workspaces, tenant_id="default", user_id=user_id) or []
    if memberships:
        labels = {f"{item['name']} · {item.get('role','member')}": item["workspace_id"] for item in memberships}
        current = str(st.session_state.get(_ACTIVE_WORKSPACE, ""))
        options = list(labels)
        index = next((i for i, label in enumerate(options) if labels[label] == current), 0)
        selected = st.selectbox("Your workspaces", options, index=index)
        if st.button("Use selected workspace", width="stretch"):
            st.session_state[_ACTIVE_WORKSPACE] = labels[selected]
            st.success("Workspace activated for this browser session.")
            st.rerun()

    create_tab, join_tab, invite_tab = st.tabs(["Create lab workspace", "Join with workspace code", "Join with secure invite"])
    with create_tab:
        with st.form("live_workspace_create_form"):
            name = st.text_input("Workspace name", value="BioIntel Lab Workspace", max_chars=120)
            description = st.text_area("Purpose", placeholder="Non-identifying research project description", max_chars=500)
            join_role = st.selectbox("Default role for new members", ["researcher", "reviewer", "viewer"])
            custom_code = st.text_input("Optional custom join code", type="password", max_chars=80)
            submitted = st.form_submit_button("Create workspace", width="stretch")
        if submitted:
            result = _safe_call(
                "create_workspace",
                store.create_workspace,
                tenant_id="default",
                owner_user_id=user_id,
                owner_display_name=display_name,
                name=name,
                description=description,
                default_join_role=join_role,
                access_code=custom_code or None,
            )
            if result:
                workspace, code = result
                st.session_state[_ACTIVE_WORKSPACE] = workspace.workspace_id
                st.session_state[_JOIN_CODE] = code
                st.success("Workspace created. Save the join code now; it is stored only as a secure hash.")
                st.code(f"Workspace ID: {workspace.workspace_id}\nJoin code: {code}")
    with join_tab:
        with st.form("live_workspace_join_form"):
            workspace_id = st.text_input("Workspace ID", placeholder="ws-...")
            access_code = st.text_input("Join code", type="password")
            requested_role = st.selectbox("Requested access", ["researcher", "reviewer", "viewer"])
            submitted = st.form_submit_button("Join workspace", width="stretch")
        if submitted:
            member = _safe_call(
                "join_workspace",
                store.join_workspace,
                workspace_id=workspace_id,
                access_code=access_code,
                user_id=user_id,
                display_name=display_name,
                requested_role=requested_role,
            )
            if member:
                st.session_state[_ACTIVE_WORKSPACE] = workspace_id
                st.session_state[_JOIN_CODE] = access_code
                st.success(f"Joined as {member['role']}.")
                st.rerun()


    with invite_tab:
        with st.form("live_workspace_secure_invite_form"):
            invite_token = st.text_input("Secure invite token", type="password")
            submitted = st.form_submit_button("Redeem invite", width="stretch")
        if submitted:
            member = _safe_call(
                "redeem_invite",
                store.redeem_invite,
                token=invite_token,
                user_id=user_id,
                display_name=display_name,
            )
            if member:
                st.session_state[_ACTIVE_WORKSPACE] = member["workspace_id"]
                st.success(f"Joined as {member['role']}.")
                st.rerun()



def _live_room_impl() -> None:
    active = _active()
    if active is None:
        st.info("Create or join a workspace in Setup first.")
        return
    store, workspace_id, user_id, _session_id, _display_name = active
    _safe_call("live_room_heartbeat", _heartbeat, "live-workspace", "BioIntel Live Workspace", "Collaboration")
    summary = _safe_call("dashboard", store.dashboard, workspace_id, actor_user_id=user_id) or {}
    columns = st.columns(8)
    columns[0].metric("Online", int(summary.get("online_members", 0)))
    columns[1].metric("Browser sessions", int(summary.get("active_sessions", 0)))
    columns[2].metric("Locks", int(summary.get("active_locks", 0)))
    columns[3].metric("Open reviews", int(summary.get("open_reviews", 0)))
    columns[4].metric("Comments", int(summary.get("comments", 0)))
    columns[5].metric("Open tasks", int(summary.get("open_tasks", 0)))
    columns[6].metric("Annotations", int(summary.get("annotations", 0)))
    columns[7].metric("Unread", int(summary.get("unread_notifications", 0)))

    presence = _safe_call("presence", store.list_presence, workspace_id, actor_user_id=user_id) or []
    if presence:
        frame = pd.DataFrame(
            [
                {
                    "Member": item.get("display_name"),
                    "Role": item.get("role"),
                    "Availability": item.get("availability", "available"),
                    "Activity": item.get("activity_state"),
                    "Status": item.get("member_status_message", ""),
                    "Module": item.get("page_title") or item.get("page_key"),
                    "Record": f"{item.get('record_type','')} {item.get('record_id','')}".strip(),
                    "Last seen": item.get("last_seen_at_utc"),
                    "Client": item.get("client_label"),
                }
                for item in presence
            ]
        )
        st.dataframe(frame, hide_index=True, width="stretch")
    else:
        st.info("No active members yet.")

    st.markdown("#### Live activity")
    activity = _safe_call("activity", store.list_activity, workspace_id, actor_user_id=user_id, limit=60) or []
    for item in activity[:30]:
        st.markdown(f"**{item.get('actor_display_name')}** — {item.get('summary')}")
        st.caption(str(item.get("created_at_utc", "")))


if hasattr(st, "fragment"):
    _live_room_fragment = st.fragment(run_every="5s")(_live_room_impl)
else:  # pragma: no cover
    _live_room_fragment = _live_room_impl


def _render_record_room() -> None:
    active = _active()
    if active is None:
        st.info("Create or join a workspace in Setup first.")
        return
    store, workspace_id, user_id, session_id, _display_name = active
    st.subheader("Shared record room")
    st.warning("Use only pseudonymized record aliases. Do not enter patient name, email, MRN or raw scientific data.")
    left, right = st.columns(2)
    with left:
        st.text_input("Record type", key=_RECORD_TYPE, placeholder="EEG_RECORD")
    with right:
        st.text_input("Record alias", key=_RECORD_ID, placeholder="EEG-018")
    st.selectbox("Your activity", ["viewing", "editing", "reviewing", "running", "idle"], key=_ACTIVITY_STATE)
    st.text_input("Optional short status", key=_STATUS_MESSAGE, max_chars=140)
    record_type = str(st.session_state.get(_RECORD_TYPE, "")).strip()
    record_id = str(st.session_state.get(_RECORD_ID, "")).strip()
    if not record_type or not record_id:
        st.info("Enter a record type and pseudonymized alias to open a shared record room.")
        return
    _safe_call("record_heartbeat", _heartbeat, "live-workspace", "BioIntel Live Workspace", "Collaboration")
    viewers = _safe_call(
        "record_viewers", store.list_presence, workspace_id,
        actor_user_id=user_id, record_type=record_type, record_id=record_id,
    ) or []
    st.markdown("#### Currently viewing or working here")
    for item in viewers:
        st.markdown(f"- **{item.get('display_name')}** · {item.get('activity_state')} · {item.get('page_title') or item.get('page_key')}")

    lock = _safe_call("get_lock", store.get_lock, workspace_id, record_type, record_id, actor_user_id=user_id)
    if lock:
        st.info(f"Edit lock: {lock.get('owner_display_name')} · revision {lock.get('revision')} · expires {lock.get('expires_at_utc')}")
    lock_note = st.text_input("Lock note", placeholder="Editing channel QC annotations", max_chars=240)
    c1, c2, c3 = st.columns(3)
    if c1.button("Acquire edit lock", width="stretch"):
        acquired = _safe_call(
            "acquire_lock", store.acquire_lock,
            workspace_id=workspace_id, user_id=user_id, session_id=session_id,
            resource_type=record_type, resource_id=record_id, note=lock_note,
            ttl_seconds=int(load_host_config().get("lock_ttl_seconds", 120)),
        )
        if acquired:
            st.success("Edit lock acquired.")
            st.rerun()
    if c2.button("Renew my lock", width="stretch"):
        renewed = _safe_call(
            "renew_lock", store.renew_lock,
            workspace_id=workspace_id, user_id=user_id, session_id=session_id,
            resource_type=record_type, resource_id=record_id,
            ttl_seconds=int(load_host_config().get("lock_ttl_seconds", 120)),
        )
        if renewed:
            st.success("Lock renewed.")
    if c3.button("Release lock", width="stretch"):
        if _safe_call(
            "release_lock", store.release_lock,
            workspace_id=workspace_id, user_id=user_id,
            resource_type=record_type, resource_id=record_id,
        ):
            st.success("Lock released.")
            st.rerun()

    st.markdown("#### Conflict-safe revision history")
    versions = _safe_call(
        "record_versions", store.list_record_versions, workspace_id,
        actor_user_id=user_id, resource_type=record_type, resource_id=record_id,
    ) or []
    current_revision = int(versions[0]["revision"]) if versions else 0
    st.caption(f"Current revision: {current_revision}. Only provenance hashes and safe summaries are stored here, not raw result data.")
    if versions:
        st.dataframe(pd.DataFrame(versions), hide_index=True, width="stretch")
    with st.expander("Commit a new record revision", expanded=False):
        payload_hash = st.text_input(
            "Result/provenance SHA-256", max_chars=64,
            placeholder="64-character SHA-256 of the saved result bundle",
            key="live_workspace_revision_hash",
        )
        revision_summary = st.text_input(
            "Safe revision summary", max_chars=500,
            placeholder="Reviewed channel QC annotations", key="live_workspace_revision_summary",
        )
        if st.button("Commit revision", disabled=len(payload_hash.strip()) != 64, width="stretch"):
            committed = _safe_call(
                "commit_revision", store.commit_record_revision,
                workspace_id=workspace_id, user_id=user_id, session_id=session_id,
                resource_type=record_type, resource_id=record_id, expected_revision=current_revision,
                payload_sha256=payload_hash, summary=revision_summary,
            )
            if committed:
                st.success(f"Revision {committed['revision']} committed.")
                st.rerun()

    st.markdown("#### Discussion")
    comment = st.text_area("Comment or @mention", max_chars=4000, placeholder="@Researcher please review this annotation.")
    if st.button("Post comment", disabled=not comment.strip(), width="stretch"):
        if _safe_call(
            "add_comment", store.add_comment,
            workspace_id=workspace_id, user_id=user_id,
            resource_type=record_type, resource_id=record_id, body=comment,
        ):
            st.success("Comment posted.")
            st.rerun()
    comments = _safe_call(
        "list_comments", store.list_comment_threads, workspace_id,
        actor_user_id=user_id, resource_type=record_type, resource_id=record_id,
    ) or []
    for item in comments:
        prefix = "↳ " if item.get("parent_comment_id") else ""
        resolved = " · resolved" if item.get("resolved_at_utc") else ""
        st.markdown(f"{prefix}**{item.get('author_display_name')}**{resolved}  \n{item.get('body')}")
        st.caption(str(item.get("created_at_utc", "")))
        c1, c2 = st.columns(2)
        reply = c1.text_input("Reply", key=f"reply_{item['comment_id']}", label_visibility="collapsed", placeholder="Reply to this comment")
        if c1.button("Reply", key=f"reply_button_{item['comment_id']}", disabled=not reply.strip()):
            if _safe_call("reply_comment", store.add_reply, workspace_id=workspace_id, user_id=user_id, parent_comment_id=item["comment_id"], body=reply):
                st.rerun()
        if c2.button("Reopen" if item.get("resolved_at_utc") else "Resolve", key=f"resolve_{item['comment_id']}"):
            if _safe_call("resolve_comment", store.set_comment_resolved, item["comment_id"], user_id=user_id, resolved=not bool(item.get("resolved_at_utc"))):
                st.rerun()
        if str(item.get("author_user_id", "")) == user_id:
            edited_body = st.text_area("Edit my comment", value=str(item.get("body", "")), key=f"edit_comment_{item['comment_id']}")
            if st.button("Save comment edit", key=f"edit_comment_button_{item['comment_id']}"):
                if _safe_call("edit_comment", store.edit_comment, item["comment_id"], user_id=user_id, body=edited_body):
                    st.success("Comment updated; prior text remains in revision history.")
                    st.rerun()

    render_annotations(active, resource_type=record_type, resource_id=record_id)


def _render_reviews() -> None:
    active = _active()
    if active is None:
        st.info("Create or join a workspace in Setup first.")
        return
    store, workspace_id, user_id, _session_id, _display_name = active
    members = _safe_call("review_members", store.list_members, workspace_id, actor_user_id=user_id) or []
    assign_options = {"Unassigned": ""}
    assign_options.update({f"{item['display_name']} · {item['role']}": item["user_id"] for item in members})
    with st.form("live_workspace_review_form"):
        resource_type = st.text_input("Review object type", value=str(st.session_state.get(_RECORD_TYPE, "ANALYSIS_RUN")))
        resource_id = st.text_input("Review object alias", value=str(st.session_state.get(_RECORD_ID, "")))
        title = st.text_input("Review title", max_chars=200)
        assigned_label = st.selectbox("Assign to", list(assign_options))
        priority = st.selectbox("Priority", ["normal", "high", "urgent", "low"])
        submitted = st.form_submit_button("Request review", width="stretch")
    if submitted:
        if _safe_call(
            "request_review", store.request_review,
            workspace_id=workspace_id, user_id=user_id,
            resource_type=resource_type, resource_id=resource_id, title=title,
            assigned_to=assign_options[assigned_label], priority=priority,
        ):
            st.success("Review requested.")
            st.rerun()

    reviews = _safe_call("list_reviews", store.list_reviews, workspace_id, actor_user_id=user_id) or []
    for review in reviews:
        with st.expander(f"{review.get('title')} · {review.get('status')} · {review.get('priority')}"):
            st.caption(f"{review.get('resource_type')} {review.get('resource_id')} · assigned: {review.get('assigned_to') or 'unassigned'}")
            status = st.selectbox(
                "Status",
                ["draft", "ready_for_review", "requested", "in_review", "reviewed", "approved", "changes_requested", "rejected", "closed", "archived"],
                index=["draft", "ready_for_review", "requested", "in_review", "reviewed", "approved", "changes_requested", "rejected", "closed", "archived"].index(str(review.get("status"))) if str(review.get("status")) in {"draft", "ready_for_review", "requested", "in_review", "reviewed", "approved", "changes_requested", "rejected", "closed", "archived"} else 2,
                key=f"review_status_{review['review_id']}",
            )
            note = st.text_area("Decision note", value=str(review.get("decision_note", "")), key=f"review_note_{review['review_id']}")
            if st.button("Update review", key=f"review_update_{review['review_id']}"):
                if _safe_call(
                    "update_review", store.update_review,
                    review_id=str(review["review_id"]), user_id=user_id,
                    status=status, decision_note=note,
                ):
                    st.success("Review updated.")
                    st.rerun()


def _render_jobs() -> None:
    active = _active()
    if active is None:
        st.info("Create or join a workspace in Setup first.")
        return
    store, workspace_id, user_id, _session_id, _display_name = active
    st.subheader("Shared analysis jobs")
    st.caption("Share safe job status and progress with the team. Job inputs and result payloads remain in their original local stores.")
    try:
        from biointel.ui.live_experience import LiveExperienceStore

        local_runs = LiveExperienceStore().recent_runs(limit=30)
    except Exception as exc:
        error_id, _ = write_runtime_error("live_workspace_v210.local_runs", exc)
        st.warning(f"Local run registry unavailable · {error_id}")
        local_runs = []
    if local_runs:
        labels = {
            f"{run.workflow} · {run.status} · {run.run_id[:12]}": run
            for run in local_runs
        }
        selected = st.selectbox("Recent local run", list(labels), key="live_workspace_share_run")
        run = labels[selected]
        if st.button("Share this run status", width="stretch"):
            shared = _safe_call(
                "share_job", store.upsert_shared_job,
                workspace_id=workspace_id, user_id=user_id, job_id=run.run_id,
                workflow=run.workflow, status=run.status, progress=run.progress,
                page_key=run.page_key, current_stage=run.current_stage,
                safe_detail=run.detail, result_reference=run.run_id,
            )
            if shared:
                st.success("Job status shared with the workspace.")
                st.rerun()
    else:
        st.info("No recent local analysis run is available to share.")

    jobs = _safe_call("shared_jobs", store.list_shared_jobs, workspace_id, actor_user_id=user_id) or []
    if jobs:
        frame = pd.DataFrame(jobs)
        frame["progress_percent"] = (pd.to_numeric(frame["progress"], errors="coerce").fillna(0) * 100).round(1)
        st.dataframe(
            frame[["workflow", "owner_display_name", "status", "progress_percent", "current_stage", "updated_at_utc"]],
            hide_index=True, width="stretch",
        )
        active_jobs = [item for item in jobs if str(item.get("status", "")).lower() in {"queued", "running", "paused", "retrying"}]
        duplicates: dict[str, int] = {}
        for item in active_jobs:
            key = str(item.get("workflow", "")).strip().casefold()
            duplicates[key] = duplicates.get(key, 0) + 1
        duplicate_names = [name for name, count in duplicates.items() if name and count > 1]
        if duplicate_names:
            st.warning("Possible duplicate active workflows: " + ", ".join(sorted(duplicate_names)))
        st.markdown("#### Job control requests")
        member = _safe_call("job_member", store.get_member, workspace_id, user_id) or {}
        controllable = [item for item in jobs if item.get("owner_user_id") == user_id or member.get("role") in {"owner", "admin"}]
        if controllable:
            labels = {f"{item['workflow']} · {item['status']} · {item['job_id'][:12]}": item for item in controllable}
            selected_label = st.selectbox("Shared job", list(labels), key="live_workspace_job_control")
            selected_job = labels[selected_label]
            action = st.selectbox("Requested action", ["cancel", "pause", "resume", "retry"], key="live_workspace_job_action")
            note = st.text_input("Optional control note", max_chars=500, key="live_workspace_job_action_note")
            if st.button("Send job-control request", width="stretch"):
                if _safe_call(
                    "request_job_action",
                    store.request_job_action,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    job_id=selected_job["job_id"],
                    action=action,
                    note=note,
                ):
                    st.success("Job-control request recorded for the owning execution service.")
                    st.rerun()
        actions = _safe_call("list_job_actions", store.list_job_actions, workspace_id, actor_user_id=user_id) or []
        if actions:
            with st.expander("Recent control requests", expanded=False):
                st.dataframe(pd.DataFrame(actions)[["job_id", "action", "status", "requested_by", "created_at_utc"]], hide_index=True, width="stretch")
    else:
        st.info("No jobs have been shared with this workspace yet.")


def _render_admin() -> None:
    active = _active()
    if active is None:
        st.info("Create or join a workspace in Setup first.")
        return
    store, workspace_id, user_id, _session_id, _display_name = active
    member = _safe_call("admin_member", store.get_member, workspace_id, user_id)
    if not member:
        return
    st.subheader("LAN host configuration")
    config = load_host_config()
    enabled = st.toggle("Enable Lab Collaboration Host Mode on next restart", value=bool(config.get("enabled", False)))
    bind_lan = st.toggle("Allow trusted LAN browsers", value=bool(config.get("bind_lan", config.get("enabled", False))))
    require_auth = st.toggle("Require named password-protected UI accounts", value=bool(config.get("require_ui_auth", True)), disabled=True, help="Required for LAN Host Mode.")
    presence_ttl = st.slider("Presence timeout (seconds)", 20, 300, int(config.get("presence_ttl_seconds", 45)), 5)
    lock_ttl = st.slider("Edit-lock timeout (seconds)", 30, 900, int(config.get("lock_ttl_seconds", 120)), 30)
    max_users = st.slider("Maximum active team members", 2, 100, int(config.get("max_active_users", 25)))
    backup_interval = st.slider("Automatic collaboration backup interval (hours)", 1, 168, int(config.get("backup_interval_hours", 12)))
    backup_retention = st.slider("Automatic collaboration backups retained", 1, 200, int(config.get("backup_retention", 20)))
    st.markdown("#### Optional trusted-LAN HTTPS")
    https_enabled = st.toggle("Use HTTPS for LAN browsers", value=bool(config.get("https_enabled", False)))
    tls_status = inspect_tls_files(str(config.get("tls_cert_file", "")), str(config.get("tls_key_file", "")))
    if st.button("Generate / replace local LAN certificate", help="Creates a self-signed certificate in local UserData. Browsers may require the lab administrator to trust it."):
        generated = _safe_call(
            "generate_lan_tls_certificate",
            generate_lan_tls_certificate,
            host_config_path().parent / "tls",
        )
        if generated:
            config["tls_cert_file"] = generated["certificate_file"]
            config["tls_key_file"] = generated["private_key_file"]
            tls_status = inspect_tls_files(generated["certificate_file"], generated["private_key_file"])
            st.session_state["live_workspace_tls_generated"] = generated
            st.success("Local TLS certificate generated. Save host configuration and restart BioIntel.")
    generated = st.session_state.get("live_workspace_tls_generated")
    if generated:
        st.caption(f"Certificate SHA-256: {generated['sha256_fingerprint']}")
        st.caption(f"Valid until: {generated['valid_until_utc']}")
    if https_enabled and not tls_status.get("ready"):
        st.warning("HTTPS is selected but certificate files are not ready. Generate the local certificate first.")
    default_role = st.selectbox(
        "Default join role", ["researcher", "reviewer", "viewer"],
        index=["researcher", "reviewer", "viewer"].index(str(config.get("default_join_role", "researcher"))),
    )
    if st.button("Save host configuration", width="stretch"):
        saved = _safe_call(
            "save_host_config", save_host_config,
            {
                "enabled": enabled,
                "presence_ttl_seconds": presence_ttl,
                "lock_ttl_seconds": lock_ttl,
                "default_join_role": default_role,
                "workspace_name": store.get_workspace(workspace_id).name,
                "allow_lan_only": True,
                "bind_lan": bind_lan,
                "require_ui_auth": require_auth,
                "api_lan_enabled": False,
                "max_active_users": max_users,
                "backup_interval_hours": backup_interval,
                "backup_retention": backup_retention,
                "https_enabled": https_enabled,
                "tls_cert_file": str(config.get("tls_cert_file", "")),
                "tls_key_file": str(config.get("tls_key_file", "")),
            },
        )
        if saved:
            st.success("Configuration saved. Restart RUN_BOTH_WINDOWS.bat to apply network binding.")
    if enabled and bind_lan:
        addresses = _private_ipv4_addresses()
        st.warning("LAN mode is for trusted local networks only. Do not expose these ports directly to the public internet.")
        for address in addresses:
            st.code(f"{'https' if https_enabled else 'http'}://{address}:<UI_PORT>")
        st.caption("The exact LAN addresses are written to OPEN_BIOINTEL_LAN_URLS.txt after restart.")

    if str(member.get("role")) in {"owner", "admin"}:
        with st.expander("Rotate workspace join code", expanded=False):
            st.caption("Existing members stay connected. The old join code stops working immediately.")
            custom_code = st.text_input("Optional new join code", type="password", max_chars=80, key="live_workspace_rotate_code")
            if st.button("Rotate join code", width="stretch"):
                code = _safe_call(
                    "rotate_access_code", store.rotate_access_code, workspace_id,
                    actor_user_id=user_id, new_code=custom_code or None,
                )
                if code:
                    st.session_state[_JOIN_CODE] = code
                    st.success("Join code rotated. Copy it now; only its secure hash is stored.")
                    st.code(f"Workspace ID: {workspace_id}\nNew join code: {code}")

    st.subheader("Members and roles")
    members = _safe_call("admin_members", store.list_members, workspace_id, actor_user_id=user_id) or []
    st.dataframe(pd.DataFrame(members), hide_index=True, width="stretch")
    if str(member.get("role")) in {"owner", "admin"} and members:
        labels = {f"{item['display_name']} · {item['role']}": item["user_id"] for item in members}
        selected = st.selectbox("Member", list(labels), key="live_workspace_admin_member")
        role = st.selectbox("New role", ["viewer", "reviewer", "researcher", "admin", "owner"])
        if st.button("Update member role", width="stretch"):
            try:
                store.set_member_role(
                    workspace_id, actor_user_id=user_id, target_user_id=labels[selected], role=role
                )
            except (PermissionDenied, ValueError, KeyError) as exc:
                st.warning(str(exc))
            except Exception as exc:
                error_id, _ = write_runtime_error("live_workspace_v210.set_member_role", exc)
                st.error(f"Role update stopped safely · {error_id}")
            else:
                st.success("Role updated.")
                st.rerun()

    st.divider()
    render_advanced_admin(active)


def render_live_workspace_page() -> None:
    st.title("BioIntel Live Workspace")
    st.caption("Real-Time Lab Presence & Record Collaboration · Local-first, LAN-capable and privacy-bounded")
    st.info(
        "See who is online, which module or pseudonymized record they are viewing, coordinate edits with locks, "
        "discuss results and manage scientific reviews. This is collaboration awareness—not screen spying."
    )
    tabs = st.tabs([
        "Setup", "My status", "Live room", "Team session", "Record room", "Tasks",
        "Evidence & timeline", "Reviews", "Shared jobs", "Notifications", "Admin / LAN host",
    ])
    with tabs[0]:
        _render_setup()
    active = _active()
    with tabs[1]:
        render_profile(active) if active else st.info("Create or join a workspace in Setup first.")
    with tabs[2]:
        _live_room_fragment()
    with tabs[3]:
        if active:
            render_collaboration_sessions(
                active,
                page_key="live-workspace",
                page_title="BioIntel Live Workspace",
                resource_type=str(st.session_state.get(_RECORD_TYPE, "")),
                resource_id=str(st.session_state.get(_RECORD_ID, "")),
            )
        else:
            st.info("Create or join a workspace in Setup first.")
    with tabs[4]:
        _render_record_room()
    with tabs[5]:
        render_tasks(active) if active else st.info("Create or join a workspace in Setup first.")
    with tabs[6]:
        render_evidence_and_timeline(active) if active else st.info("Create or join a workspace in Setup first.")
    with tabs[7]:
        _render_reviews()
    with tabs[8]:
        _render_jobs()
    with tabs[9]:
        render_notifications(active) if active else st.info("Create or join a workspace in Setup first.")
    with tabs[10]:
        _render_admin()


__all__ = ["render_live_workspace_page", "render_live_workspace_sidebar"]
