from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from biointel.live_workspace_v210 import core
from biointel.live_workspace_v210.api import router
from biointel.live_workspace_v210.core import LiveWorkspaceStore, PermissionDenied, RecordLocked


@pytest.fixture()
def store(tmp_path: Path) -> LiveWorkspaceStore:
    return LiveWorkspaceStore(tmp_path / "live_workspace.sqlite3")


def create_two_members(store: LiveWorkspaceStore):
    workspace, code = store.create_workspace(
        tenant_id="default",
        owner_user_id="owner-1",
        owner_display_name="Owner",
        name="Neuro Lab",
    )
    store.join_workspace(
        workspace_id=workspace.workspace_id,
        access_code=code,
        user_id="researcher-2",
        display_name="Researcher Two",
    )
    return workspace, code


def test_workspace_join_code_is_hashed_and_membership_is_role_scoped(store: LiveWorkspaceStore) -> None:
    workspace, code = create_two_members(store)
    with sqlite3.connect(store.path) as connection:
        encoded = connection.execute(
            "SELECT access_code_hash FROM live_workspaces WHERE workspace_id=?", (workspace.workspace_id,)
        ).fetchone()[0]
    assert code not in encoded
    assert encoded.startswith("pbkdf2_sha256$")
    assert store.verify_access_code(workspace.workspace_id, code)
    assert store.get_member(workspace.workspace_id, "owner-1")["role"] == "owner"
    assert store.get_member(workspace.workspace_id, "researcher-2")["role"] == "researcher"


def test_live_presence_same_record_and_expiry_cleanup(store: LiveWorkspaceStore) -> None:
    workspace, _code = create_two_members(store)
    for user, session, display, state in (
        ("owner-1", "session-owner", "Owner", "editing"),
        ("researcher-2", "session-two", "Researcher Two", "viewing"),
    ):
        store.heartbeat(
            workspace_id=workspace.workspace_id,
            session_id=session,
            user_id=user,
            display_name=display,
            page_key="eeg_meg",
            page_title="EEG/MEG Analytics",
            category="Neuro/CNS",
            record_type="EEG_RECORD",
            record_id="EEG-018",
            activity_state=state,
        )
    viewers = store.list_presence(
        workspace.workspace_id,
        actor_user_id="owner-1",
        record_type="EEG_RECORD",
        record_id="EEG-018",
    )
    assert {item["user_id"] for item in viewers} == {"owner-1", "researcher-2"}
    assert {item["activity_state"] for item in viewers} == {"viewing", "editing"}

    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE live_presence_sessions SET expires_at_utc='2000-01-01T00:00:00+00:00' WHERE session_id='session-two'"
        )
    remaining = store.list_presence(workspace.workspace_id, actor_user_id="owner-1")
    assert [item["user_id"] for item in remaining] == ["owner-1"]


def test_record_lock_prevents_overwrite_and_supports_admin_takeover(store: LiveWorkspaceStore) -> None:
    workspace, _code = create_two_members(store)
    lock = store.acquire_lock(
        workspace_id=workspace.workspace_id,
        user_id="owner-1",
        session_id="session-owner",
        resource_type="EEG_RECORD",
        resource_id="EEG-018",
    )
    assert lock["owner_user_id"] == "owner-1"
    with pytest.raises(RecordLocked, match="Owner"):
        store.acquire_lock(
            workspace_id=workspace.workspace_id,
            user_id="researcher-2",
            session_id="session-two",
            resource_type="EEG_RECORD",
            resource_id="EEG-018",
        )
    store.set_member_role(
        workspace.workspace_id,
        actor_user_id="owner-1",
        target_user_id="researcher-2",
        role="admin",
    )
    takeover = store.acquire_lock(
        workspace_id=workspace.workspace_id,
        user_id="researcher-2",
        session_id="session-two",
        resource_type="EEG_RECORD",
        resource_id="EEG-018",
        force=True,
    )
    assert takeover["owner_user_id"] == "researcher-2"
    assert takeover["revision"] == 2


def test_viewer_cannot_edit_comment_or_request_review(store: LiveWorkspaceStore) -> None:
    workspace, code = store.create_workspace(
        tenant_id="default", owner_user_id="owner-1", owner_display_name="Owner",
        name="Read-only review", default_join_role="viewer",
    )
    store.join_workspace(
        workspace_id=workspace.workspace_id, access_code=code,
        user_id="viewer-1", display_name="Viewer One", requested_role="viewer",
    )
    with pytest.raises(PermissionDenied):
        store.acquire_lock(
            workspace_id=workspace.workspace_id, user_id="viewer-1", session_id="view-session",
            resource_type="SCAN", resource_id="SCAN-1",
        )
    with pytest.raises(PermissionDenied):
        store.add_comment(
            workspace_id=workspace.workspace_id, user_id="viewer-1",
            resource_type="SCAN", resource_id="SCAN-1", body="Cannot write",
        )
    with pytest.raises(PermissionDenied):
        store.request_review(
            workspace_id=workspace.workspace_id, user_id="viewer-1",
            resource_type="SCAN", resource_id="SCAN-1", title="Cannot request",
        )


def test_mentions_reviews_notifications_and_activity_are_persisted(store: LiveWorkspaceStore) -> None:
    workspace, _code = create_two_members(store)
    comment = store.add_comment(
        workspace_id=workspace.workspace_id,
        user_id="researcher-2",
        resource_type="VARIANT",
        resource_id="VAR-018",
        body="@Owner please review the evidence table.",
    )
    assert comment["mentions"] == ["Owner"]
    notifications = store.list_notifications(workspace.workspace_id, user_id="owner-1", unread_only=True)
    assert any(item["title"] == "You were mentioned" for item in notifications)

    review = store.request_review(
        workspace_id=workspace.workspace_id,
        user_id="researcher-2",
        resource_type="VARIANT",
        resource_id="VAR-018",
        title="Variant evidence review",
        assigned_to="owner-1",
        priority="high",
    )
    updated = store.update_review(
        review_id=review["review_id"], user_id="owner-1", status="approved", decision_note="Evidence checked."
    )
    assert updated["status"] == "approved"
    assert updated["completed_at_utc"]
    activity = store.list_activity(workspace.workspace_id, actor_user_id="owner-1")
    event_types = {item["event_type"] for item in activity}
    assert {"comment_added", "review_requested", "review_updated"}.issubset(event_types)


def test_presence_rejects_raw_or_unsafe_identifiers(store: LiveWorkspaceStore) -> None:
    workspace, _code = create_two_members(store)
    with pytest.raises(ValueError, match="unsupported characters"):
        store.heartbeat(
            workspace_id=workspace.workspace_id,
            session_id="session-owner",
            user_id="owner-1",
            display_name="Owner",
            page_key="eeg",
            record_type="EEG",
            record_id="../../patient.csv",
        )
    with pytest.raises(ValueError, match="characters or fewer"):
        store.heartbeat(
            workspace_id=workspace.workspace_id,
            session_id="session-owner",
            user_id="owner-1",
            display_name="Owner",
            page_key="eeg",
            status_message="x" * 141,
        )


def test_host_configuration_is_atomic_and_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "host_config.json"
    monkeypatch.setenv("BIOINTEL_LIVE_WORKSPACE_HOST_CONFIG", str(config))
    saved = core.save_host_config(
        {
            "enabled": True,
            "workspace_name": "Neuro Lab",
            "presence_ttl_seconds": 5,
            "lock_ttl_seconds": 5000,
            "default_join_role": "reviewer",
        }
    )
    assert saved["enabled"] is True
    assert saved["presence_ttl_seconds"] == 20
    assert saved["lock_ttl_seconds"] == 900
    assert core.load_host_config()["default_join_role"] == "reviewer"
    assert json.loads(config.read_text(encoding="utf-8"))["workspace_name"] == "Neuro Lab"


@dataclass
class Identity:
    client_id: str
    display_name: str
    role: str


@dataclass
class Tenant:
    tenant_id: str


def test_rest_api_and_websocket_presence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Replace the router module singleton with an isolated test database.
    import biointel.live_workspace_v210.api as api_module

    isolated = LiveWorkspaceStore(tmp_path / "api.sqlite3")
    monkeypatch.setattr(api_module, "STORE", isolated)
    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next):
        request.state.api_identity = Identity("owner-api", "Owner API", "local_operator")
        request.state.tenant = Tenant("default")
        return await call_next(request)

    app.include_router(router)
    client = TestClient(app)
    created = client.post("/v1/live-workspace/workspaces", json={"name": "API Lab"})
    assert created.status_code == 200
    payload = created.json()
    workspace_id = payload["workspace"]["workspace_id"]
    join_code = payload["join_code"]
    heartbeat = client.post(
        f"/v1/live-workspace/workspaces/{workspace_id}/presence/heartbeat",
        json={
            "session_id": "api-session",
            "display_name": "Owner API",
            "page_key": "neuroimaging",
            "page_title": "Neuroimaging",
            "record_type": "SCAN",
            "record_id": "SCAN-01",
        },
    )
    assert heartbeat.status_code == 200
    assert client.get(f"/v1/live-workspace/workspaces/{workspace_id}/presence").json()[0]["record_id"] == "SCAN-01"

    with client.websocket_connect(f"/v1/live-workspace/ws/{workspace_id}") as websocket:
        websocket.send_json(
            {
                "type": "authenticate",
                "access_code": join_code,
                "user_id": "socket-user",
                "display_name": "Socket User",
                "session_id": "socket-session",
            }
        )
        # A presence_changed broadcast may arrive before the direct authenticated response.
        messages = [websocket.receive_json(), websocket.receive_json()]
        assert any(message.get("type") == "authenticated" for message in messages)
        websocket.send_json({"type": "request_snapshot"})
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "presence_snapshot"
        assert {item["user_id"] for item in snapshot["items"]} >= {"owner-api", "socket-user"}


def test_revision_conflict_shared_jobs_and_join_code_rotation(store: LiveWorkspaceStore) -> None:
    from biointel.live_workspace_v210.core import RevisionConflict

    workspace, old_code = create_two_members(store)
    store.acquire_lock(
        workspace_id=workspace.workspace_id,
        user_id="owner-1",
        session_id="session-owner",
        resource_type="EEG_RECORD",
        resource_id="EEG-018",
    )
    first = store.commit_record_revision(
        workspace_id=workspace.workspace_id,
        user_id="owner-1",
        session_id="session-owner",
        resource_type="EEG_RECORD",
        resource_id="EEG-018",
        expected_revision=0,
        payload_sha256="a" * 64,
        summary="Initial reviewed annotations",
    )
    assert first["revision"] == 1
    with pytest.raises(RevisionConflict) as conflict:
        store.commit_record_revision(
            workspace_id=workspace.workspace_id,
            user_id="owner-1",
            session_id="session-owner",
            resource_type="EEG_RECORD",
            resource_id="EEG-018",
            expected_revision=0,
            payload_sha256="b" * 64,
        )
    assert conflict.value.current_revision == 1
    assert store.list_record_versions(
        workspace.workspace_id,
        actor_user_id="researcher-2",
        resource_type="EEG_RECORD",
        resource_id="EEG-018",
    )[0]["payload_sha256"] == "a" * 64

    shared = store.upsert_shared_job(
        workspace_id=workspace.workspace_id,
        user_id="researcher-2",
        job_id="run-123",
        workflow="EEG preprocessing",
        status="running",
        progress=0.65,
        current_stage="ICA review",
    )
    assert shared["progress"] == 0.65
    assert store.list_shared_jobs(workspace.workspace_id, actor_user_id="owner-1")[0]["job_id"] == "run-123"

    new_code = store.rotate_access_code(workspace.workspace_id, actor_user_id="owner-1")
    assert new_code != old_code
    assert not store.verify_access_code(workspace.workspace_id, old_code)
    assert store.verify_access_code(workspace.workspace_id, new_code)
