from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from biointel.live_workspace_v210.advanced import LiveWorkspaceAdvancedStore
from biointel.live_workspace_v210.api import router
from biointel.live_workspace_v210.core import PermissionDenied, RevisionConflict
from biointel.security.ui_user_store import configured_ui_users, public_local_ui_users, upsert_local_ui_user

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def store(tmp_path: Path) -> LiveWorkspaceAdvancedStore:
    return LiveWorkspaceAdvancedStore(tmp_path / "live.sqlite3")


def workspace_with_researcher(store: LiveWorkspaceAdvancedStore):
    workspace, _ = store.create_workspace(
        tenant_id="default",
        owner_user_id="owner",
        owner_display_name="Owner",
        name="Neuro Collaboration Lab",
    )
    invite = store.create_invite(workspace.workspace_id, actor_user_id="owner", role="researcher", expires_hours=2)
    member = store.redeem_invite(token=invite["token"], user_id="researcher", display_name="Researcher")
    return workspace, member


def test_secure_invites_profiles_privacy_and_presence_masking(store: LiveWorkspaceAdvancedStore) -> None:
    workspace, member = workspace_with_researcher(store)
    assert member["role"] == "researcher"
    with pytest.raises(PermissionDenied):
        store.redeem_invite(token="wrong-token", user_id="intruder", display_name="Intruder")
    store.update_workspace_settings(
        workspace.workspace_id,
        actor_user_id="owner",
        settings={"presence_detail": "module_only", "retention_days": 99999},
    )
    assert store.workspace_settings(workspace.workspace_id, actor_user_id="owner")["retention_days"] == 3650
    store.update_member_profile(
        workspace.workspace_id,
        user_id="researcher",
        availability="reviewing",
        status_message="Reviewing EEG batch",
        presence_visibility="workspace",
    )
    store.heartbeat(
        workspace_id=workspace.workspace_id,
        session_id="session-r",
        user_id="researcher",
        display_name="Researcher",
        page_key="eeg",
        page_title="EEG/MEG",
        record_type="EEG_RECORD",
        record_id="EEG-18",
    )
    row = store.list_presence(workspace.workspace_id, actor_user_id="owner")[0]
    assert row["availability"] == "reviewing"
    assert row["record_id"] == ""


def test_threaded_comments_tasks_evidence_links_and_timeline(store: LiveWorkspaceAdvancedStore) -> None:
    workspace, _ = workspace_with_researcher(store)
    comment = store.add_comment(
        workspace_id=workspace.workspace_id,
        user_id="researcher",
        resource_type="VARIANT",
        resource_id="V-1",
        body="Please review",
    )
    reply = store.add_reply(
        workspace_id=workspace.workspace_id,
        user_id="owner",
        parent_comment_id=comment["comment_id"],
        body="Reviewed",
    )
    assert reply["parent_comment_id"] == comment["comment_id"]
    edited = store.edit_comment(reply["comment_id"], user_id="owner", body="Reviewed with evidence")
    assert edited["body"] == "Reviewed with evidence"
    resolved = store.set_comment_resolved(comment["comment_id"], user_id="owner", resolved=True)
    assert resolved["resolved_at_utc"]

    task = store.create_task(
        workspace_id=workspace.workspace_id,
        user_id="owner",
        title="Verify genome build",
        assigned_to="researcher",
        priority="high",
    )
    assert task["assigned_to"] == "researcher"
    assert store.update_task(task["task_id"], user_id="researcher", status="done")["status"] == "done"

    bookmark = store.add_bookmark(
        workspace_id=workspace.workspace_id,
        user_id="owner",
        kind="publication",
        title="Evidence paper",
        safe_reference="PMID-123",
        evidence_level="supporting",
    )
    assert bookmark["safe_reference"] == "PMID-123"
    link = store.add_project_link(
        workspace_id=workspace.workspace_id,
        user_id="owner",
        project_id="PARKINSON-01",
        subject_alias="SUBJECT-01",
        module_key="neuroimaging",
        resource_type="SCAN",
        resource_id="SCAN-01",
        title="Baseline MRI",
    )
    assert link["module_key"] == "neuroimaging"
    event = store.add_timeline_event(
        workspace_id=workspace.workspace_id,
        user_id="owner",
        project_id="PARKINSON-01",
        subject_alias="SUBJECT-01",
        event_type="analysis_completed",
        title="MRI connectivity completed",
    )
    assert event["event_type"] == "analysis_completed"
    assert len(store.list_timeline(workspace.workspace_id, actor_user_id="researcher")) == 1


def test_scientific_annotations_are_revision_safe(store: LiveWorkspaceAdvancedStore) -> None:
    workspace, _ = workspace_with_researcher(store)
    annotation = store.create_annotation(
        workspace_id=workspace.workspace_id,
        user_id="researcher",
        resource_type="EEG_RECORD",
        resource_id="EEG-18",
        annotation_type="EEG_EVENT",
        label="Candidate event",
        confidence=0.7,
        geometry={"start_seconds": 12.2, "end_seconds": 13.1},
    )
    assert annotation["revision"] == 1
    updated = store.update_annotation(
        annotation["annotation_id"],
        user_id="researcher",
        expected_revision=1,
        status="needs_review",
        label="Candidate event for review",
    )
    assert updated["revision"] == 2
    with pytest.raises(RevisionConflict) as conflict:
        store.update_annotation(
            annotation["annotation_id"],
            user_id="researcher",
            expected_revision=1,
            status="accepted",
        )
    assert conflict.value.current_revision == 2


def test_collaborative_sessions_jobs_notifications_offline_drafts_and_resync(store: LiveWorkspaceAdvancedStore) -> None:
    workspace, _ = workspace_with_researcher(store)
    session = store.create_collaboration_session(
        workspace_id=workspace.workspace_id,
        user_id="owner",
        title="EEG Review",
    )
    joined = store.join_collaboration_session(session["collaboration_session_id"], user_id="researcher")
    assert {row["user_id"] for row in joined["participants"]} == {"owner", "researcher"}
    navigated = store.update_collaboration_navigation(
        session["collaboration_session_id"],
        user_id="owner",
        page_key="eeg",
        page_title="EEG/MEG",
        resource_type="EEG_RECORD",
        resource_id="EEG-18",
        cursor={"time_seconds": 12.5},
    )
    assert navigated["cursor"]["time_seconds"] == 12.5

    store.upsert_shared_job(
        workspace_id=workspace.workspace_id,
        user_id="researcher",
        job_id="job-1",
        workflow="EEG preprocessing",
        status="running",
        progress=0.5,
    )
    action = store.request_job_action(
        workspace_id=workspace.workspace_id,
        user_id="researcher",
        job_id="job-1",
        action="pause",
    )
    assert action["action"] == "pause"

    store.update_notification_preferences(
        workspace.workspace_id,
        user_id="researcher",
        muted=False,
        mention_only=False,
        browser_notifications=True,
    )
    task = store.create_task(
        workspace_id=workspace.workspace_id,
        user_id="owner",
        title="Review EEG",
        assigned_to="researcher",
    )
    assert task
    assert store.list_notifications(workspace.workspace_id, user_id="researcher")
    assert store.mark_all_notifications_read(workspace.workspace_id, user_id="researcher") >= 1

    draft = store.save_offline_draft(
        workspace_id=workspace.workspace_id,
        user_id="researcher",
        resource_type="EEG_RECORD",
        resource_id="EEG-18",
        base_revision=2,
        draft={"label": "offline note"},
    )
    with pytest.raises(RevisionConflict):
        store.sync_offline_draft(draft["draft_id"], user_id="researcher", current_revision=3)
    activity = store.list_activity_filtered(workspace.workspace_id, actor_user_id="owner", after_event_id=0)
    assert activity and activity == sorted(activity, key=lambda row: row["event_id"])


def test_backup_restore_and_admin_health(store: LiveWorkspaceAdvancedStore) -> None:
    workspace, _ = workspace_with_researcher(store)
    store.create_task(workspace_id=workspace.workspace_id, user_id="owner", title="Task")
    store.add_bookmark(
        workspace_id=workspace.workspace_id,
        user_id="owner",
        kind="database",
        title="Reference",
        safe_reference="DB-1",
    )
    store.create_annotation(
        workspace_id=workspace.workspace_id,
        user_id="owner",
        resource_type="SCAN",
        resource_id="SCAN-1",
        annotation_type="IMAGE_ROI",
        label="ROI",
        geometry={"x": 1, "y": 2},
    )
    archive, manifest = store.export_workspace_backup(workspace.workspace_id, actor_user_id="owner")
    assert manifest["archive_sha256"]
    inspection = store.inspect_workspace_backup(archive)
    assert inspection["valid"] is True
    restored = store.restore_workspace_backup(archive, actor_user_id="restoring-owner", new_name="Restored Lab")
    assert restored["restored_counts"]["tasks"] == 1
    restored_store = store.get_workspace(restored["workspace_id"])
    assert restored_store.name == "Restored Lab"
    health = store.admin_health(workspace.workspace_id, actor_user_id="owner")
    assert health["database_integrity"] == "ok"
    assert health["journal_mode"].lower() == "wal"


def test_local_password_accounts_are_hash_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "ui_users.json"
    monkeypatch.setenv("BIOINTEL_UI_USERS_FILE", str(path))
    result = upsert_local_ui_user(
        username="lab.admin",
        display_name="Lab Admin",
        role="admin",
        password="correct-horse-battery-staple",
    )
    assert result["username"] == "lab.admin"
    raw = path.read_text(encoding="utf-8")
    assert "correct-horse-battery-staple" not in raw
    assert public_local_ui_users()[0]["role"] == "admin"
    assert configured_ui_users()["lab.admin"]["source"] == "local_file"


@dataclass
class Identity:
    client_id: str
    display_name: str
    role: str


@dataclass
class Tenant:
    tenant_id: str


def test_advanced_rest_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import biointel.live_workspace_v210.api as api_module

    isolated = LiveWorkspaceAdvancedStore(tmp_path / "api.sqlite3")
    monkeypatch.setattr(api_module, "STORE", isolated)
    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next):
        request.state.api_identity = Identity("api-owner", "API Owner", "local_operator")
        request.state.tenant = Tenant("default")
        return await call_next(request)

    app.include_router(router)
    client = TestClient(app)
    created = client.post("/v1/live-workspace/workspaces", json={"name": "API Lab"})
    assert created.status_code == 200
    workspace_id = created.json()["workspace"]["workspace_id"]
    assert client.post(
        f"/v1/live-workspace/workspaces/{workspace_id}/tasks",
        json={"title": "API task"},
    ).status_code == 200
    assert client.post(
        f"/v1/live-workspace/workspaces/{workspace_id}/annotations",
        json={
            "resource_type": "SCAN",
            "resource_id": "SCAN-1",
            "annotation_type": "IMAGE_ROI",
            "label": "ROI",
        },
    ).status_code == 200
    status = client.get("/v1/live-workspace/status").json()
    assert "scientific-annotations" in status["capabilities"]
    assert client.get(f"/v1/live-workspace/workspaces/{workspace_id}/admin-health").json()["database_integrity"] == "ok"


def test_runtime_and_ui_source_expose_lan_security_and_peak_controls() -> None:
    supervisor = (ROOT / "scripts" / "runtime_supervisor_step206.py").read_text(encoding="utf-8")
    ui = (ROOT / "src" / "biointel" / "live_workspace_v210" / "ui.py").read_text(encoding="utf-8")
    advanced_ui = (ROOT / "src" / "biointel" / "live_workspace_v210" / "advanced_ui.py").read_text(encoding="utf-8")
    assert 'self.ui_bind_host = "0.0.0.0"' in supervisor
    assert "BIOINTEL_UI_AUTH_REQUIRED" in supervisor
    assert "OPEN_BIOINTEL_LAN_URLS.txt" in supervisor
    for label in ("Team session", "Evidence & timeline", "Notifications"):
        assert label in ui
    for label in ("Scientific annotations", "Backup & recovery", "Login accounts"):
        assert label in advanced_ui


def test_permissions_trash_sessions_and_totp(store: LiveWorkspaceAdvancedStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from biointel.security.ui_user_store import _totp_code, verify_totp

    workspace, _ = workspace_with_researcher(store)
    store.set_member_permissions(
        workspace.workspace_id,
        actor_user_id="owner",
        target_user_id="researcher",
        allowed_categories=["Neuro/CNS"],
        allowed_modules=["eeg"],
        allowed_projects=["PROJECT-1"],
    )
    assert store.authorize_module(
        workspace.workspace_id,
        user_id="researcher",
        page_key="eeg",
        category="Neuro/CNS",
        project_id="PROJECT-1",
    )
    assert not store.authorize_module(
        workspace.workspace_id,
        user_id="researcher",
        page_key="neuroimaging",
        category="Neuro/CNS",
        project_id="PROJECT-1",
    )
    with pytest.raises(PermissionDenied):
        store.heartbeat(
            workspace_id=workspace.workspace_id,
            session_id="restricted-session",
            user_id="researcher",
            display_name="Researcher",
            page_key="neuroimaging",
            page_title="Neuroimaging",
            category="Neuro/CNS",
            project_id="PROJECT-1",
        )

    task = store.create_task(workspace_id=workspace.workspace_id, user_id="owner", title="Recoverable task")
    deleted = store.soft_delete_item(
        workspace_id=workspace.workspace_id,
        user_id="owner",
        item_type="task",
        item_id=task["task_id"],
    )
    assert not store.list_tasks(workspace.workspace_id, actor_user_id="owner")
    store.restore_deleted_item(deleted["deleted_item_id"], actor_user_id="owner")
    assert store.list_tasks(workspace.workspace_id, actor_user_id="owner")[0]["task_id"] == task["task_id"]

    session = store.register_account_session(
        workspace.workspace_id,
        user_id="researcher",
        account_session_id="browser-1",
        client_label="Browser",
        auth_source="local_file",
    )
    assert session["account_session_id"] == "browser-1"
    assert store.revoke_account_session("browser-1", actor_user_id="researcher")
    with pytest.raises(PermissionDenied):
        store.register_account_session(
            workspace.workspace_id,
            user_id="researcher",
            account_session_id="browser-1",
            client_label="Browser",
            auth_source="local_file",
        )

    users_path = tmp_path / "totp-users.json"
    monkeypatch.setenv("BIOINTEL_UI_USERS_FILE", str(users_path))
    created = upsert_local_ui_user(
        username="secure.user",
        display_name="Secure User",
        role="researcher",
        password="long-enough-password-123",
        totp_enabled=True,
    )
    code = _totp_code(created["totp_secret"], timestamp=1_800_000_000)
    assert verify_totp(created["totp_secret"], code, timestamp=1_800_000_000)
    assert not verify_totp(created["totp_secret"], "000000", timestamp=1_800_000_000)


def test_tls_certificate_generation_and_host_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from biointel.live_workspace_v210.core import load_host_config, save_host_config
    from biointel.live_workspace_v210.tls import generate_lan_tls_certificate, inspect_tls_files

    config_path = tmp_path / "host_config.json"
    monkeypatch.setenv("BIOINTEL_LIVE_WORKSPACE_HOST_CONFIG", str(config_path))
    generated = generate_lan_tls_certificate(tmp_path / "tls", valid_days=90)
    assert len(generated["sha256_fingerprint"]) == 64
    status = inspect_tls_files(generated["certificate_file"], generated["private_key_file"])
    assert status["ready"] is True
    saved = save_host_config(
        {
            "enabled": True,
            "bind_lan": True,
            "require_ui_auth": True,
            "https_enabled": True,
            "tls_cert_file": generated["certificate_file"],
            "tls_key_file": generated["private_key_file"],
        }
    )
    assert saved["https_enabled"] is True
    assert load_host_config()["tls_cert_file"] == generated["certificate_file"]


def test_websocket_invite_resync_dashboard_and_notifications(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import biointel.live_workspace_v210.api as api_module

    isolated = LiveWorkspaceAdvancedStore(tmp_path / "socket-api.sqlite3")
    monkeypatch.setattr(api_module, "STORE", isolated)
    workspace, _ = isolated.create_workspace(
        tenant_id="default",
        owner_user_id="owner",
        owner_display_name="Owner",
        name="Socket Lab",
    )
    invite = isolated.create_invite(workspace.workspace_id, actor_user_id="owner", role="researcher")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    with client.websocket_connect(f"/v1/live-workspace/ws/{workspace.workspace_id}") as websocket:
        websocket.send_json(
            {
                "type": "authenticate",
                "invite_token": invite["token"],
                "user_id": "socket-researcher",
                "display_name": "Socket Researcher",
                "session_id": "socket-advanced-session",
            }
        )
        received = [websocket.receive_json(), websocket.receive_json()]
        authenticated = next(item for item in received if item.get("type") == "authenticated")
        assert authenticated["event_cursor"] >= 0
        websocket.send_json({"type": "request_dashboard"})
        assert websocket.receive_json()["type"] == "dashboard_snapshot"
        websocket.send_json({"type": "request_resync", "after_event_id": 0})
        resync = websocket.receive_json()
        assert resync["type"] == "activity_resync"
        assert "event_cursor" in resync
        websocket.send_json({"type": "request_notifications", "unread_only": True})
        assert websocket.receive_json()["type"] == "notification_snapshot"


def test_automatic_sqlite_snapshot_is_integrity_checked(store: LiveWorkspaceAdvancedStore, tmp_path: Path) -> None:
    from biointel.live_workspace_v210.backup import create_live_workspace_snapshot, inspect_live_workspace_snapshot

    workspace, _ = workspace_with_researcher(store)
    store.create_task(workspace_id=workspace.workspace_id, user_id="owner", title="Snapshot task")
    result = create_live_workspace_snapshot(store.path, tmp_path / "automatic-backups", retention=2)
    assert result is not None
    inspected = inspect_live_workspace_snapshot(Path(result["archive_file"]))
    assert inspected["verified"] is True
    assert inspected["sqlite_integrity"] == "ok"


def test_automatic_snapshot_uses_collision_safe_temporary_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from biointel.live_workspace_v210 import backup as backup_module

    database = tmp_path / "live.sqlite3"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE sample (value TEXT)")
        connection.execute("INSERT INTO sample VALUES ('ready')")

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 23, 8, 30, 26, tzinfo=UTC)

    monkeypatch.setattr(backup_module, "datetime", FrozenDateTime)
    backup_dir = tmp_path / "automatic-backups"
    first = backup_module.create_live_workspace_snapshot(database, backup_dir)
    second = backup_module.create_live_workspace_snapshot(database, backup_dir)

    assert first is not None and second is not None
    assert first["archive_file"] != second["archive_file"]
    assert not list(backup_dir.glob("*.tmp"))
    assert backup_module.inspect_live_workspace_snapshot(Path(first["archive_file"]))["verified"] is True
    assert backup_module.inspect_live_workspace_snapshot(Path(second["archive_file"]))["verified"] is True


def test_automatic_snapshot_retries_atomic_publish_on_windows_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from biointel.live_workspace_v210 import backup as backup_module

    database = tmp_path / "live.sqlite3"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE sample (value TEXT)")

    original_replace = backup_module.os.replace
    calls = 0

    def replace_after_transient_lock(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError(32, "The process cannot access the file")
        original_replace(source, target)

    monkeypatch.setattr(backup_module.os, "replace", replace_after_transient_lock)
    result = backup_module.create_live_workspace_snapshot(database, tmp_path / "automatic-backups")

    assert result is not None
    assert calls == 2
    assert Path(result["archive_file"]).is_file()


def test_sidebar_presence_fragment_stays_inside_sidebar_container() -> None:
    from streamlit.testing.v1 import AppTest

    script = """
from biointel.live_workspace_v210 import ui

class Store:
    def authorize_module(self, *args, **kwargs):
        return True

    def heartbeat(self, *args, **kwargs):
        return {"ok": True}

    def list_presence(self, *args, **kwargs):
        return []

store = Store()
ui._active = lambda: (store, "workspace", "user", "session", "Researcher")
ui.st.page_link = lambda *args, **kwargs: None
ui.render_live_workspace_sidebar("wetlab_biotechnology", "Wetlab", "Lab")
"""
    app = AppTest.from_string(script).run(timeout=10)

    assert not app.exception
    assert len(app.sidebar.expander) == 1


def test_collaboration_session_pause_leave_and_retention(store: LiveWorkspaceAdvancedStore) -> None:
    workspace, _ = workspace_with_researcher(store)
    session = store.create_collaboration_session(workspace_id=workspace.workspace_id, user_id="owner", title="Review")
    store.join_collaboration_session(session["collaboration_session_id"], user_id="researcher")
    paused = store.set_collaboration_session_status(session["collaboration_session_id"], user_id="owner", status="paused")
    assert paused["status"] == "paused"
    assert store.leave_collaboration_session(session["collaboration_session_id"], user_id="researcher")
    resumed = store.set_collaboration_session_status(session["collaboration_session_id"], user_id="owner", status="active")
    assert resumed["status"] == "active"
    result = store.prune_retention(workspace.workspace_id, actor_user_id="owner")
    assert result["retention_days"] >= 7
