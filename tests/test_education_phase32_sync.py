from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from biointel.education.phase32_35.base import (
    IntegrityFailure,
    PermissionDenied,
    ResearchPlatformError,
)
from biointel.education.phase32_35.sync import MemorySyncAdapter, SyncEngine


@pytest.fixture()
def sync_engine(tmp_path: Path) -> SyncEngine:
    return SyncEngine(tmp_path / "education.sqlite3", tmp_path / "media")


def trusted_device(
    engine: SyncEngine,
    name: str,
    *,
    tenant: str = "tenant-a",
    scopes: list[str] | None = None,
) -> dict:
    return engine.register_device(
        tenant,
        f"owner-{name}",
        device_name=name,
        device_type="desktop",
        operating_system="Windows",
        permissions=scopes or ["notes", "preferences", "selected_files"],
        approved_by="administrator",
    )


def test_sync_is_optional_local_first_and_migration_is_idempotent(sync_engine: SyncEngine):
    assert sync_engine.store.migrate() == "education_phase31_to_35_research_platform_v1"
    assert sync_engine.store.migrate() == "education_phase31_to_35_research_platform_v1"
    status = sync_engine.status("tenant-a")
    assert status["optional"] is True
    assert status["local_first"] is True
    assert status["pending_changes"] == 0
    assert status["encryption_boundary"]["end_to_end"].startswith("opaque payload")


def test_sensitive_device_requires_approval_and_revocation_closes_access(sync_engine: SyncEngine):
    device = sync_engine.register_device(
        "tenant-a",
        "user-a",
        device_name="Laptop",
        device_type="laptop",
        operating_system="Windows",
        permissions=["notes"],
    )
    assert device["state"] == "pending"
    with pytest.raises(PermissionDenied):
        sync_engine.append_change(
            "tenant-a",
            device["device_id"],
            "user-a",
            entity_type="notes",
            entity_id="n1",
            operation="CREATE",
            payload={"body": "offline"},
            idempotency_key="pending-device",
        )
    approved = sync_engine.approve_device(device["device_id"], "admin-a")
    assert approved["state"] == "trusted"
    sync_engine.create_session(
        device["device_id"],
        "test-token",
        expires_at_utc="2099-01-01T00:00:00+00:00",
    )
    sync_engine.revoke_device(device["device_id"], "admin-a", lost=True)
    with pytest.raises(PermissionDenied):
        sync_engine.append_change(
            "tenant-a",
            device["device_id"],
            "user-a",
            entity_type="notes",
            entity_id="n2",
            operation="CREATE",
            payload={"body": "blocked"},
            idempotency_key="revoked-device",
        )


def test_journal_is_idempotent_encrypted_and_never_accepts_secrets(sync_engine: SyncEngine):
    device = trusted_device(sync_engine, "A")
    first = sync_engine.append_change(
        "tenant-a",
        device["device_id"],
        "owner-A",
        entity_type="notes",
        entity_id="n1",
        operation="CREATE",
        payload={"body": "encrypted body"},
        idempotency_key="idem-1",
    )
    again = sync_engine.append_change(
        "tenant-a",
        device["device_id"],
        "owner-A",
        entity_type="notes",
        entity_id="n1",
        operation="CREATE",
        payload={"body": "encrypted body"},
        idempotency_key="idem-1",
    )
    assert again["change_id"] == first["change_id"]
    assert "encrypted body" not in first["payload_ciphertext"]
    with pytest.raises(PermissionDenied):
        sync_engine.append_change(
            "tenant-a",
            device["device_id"],
            "owner-A",
            entity_type="notes",
            entity_id="n-secret",
            operation="CREATE",
            payload={"access_token": "must-never-sync"},
            idempotency_key="secret",
        )


def test_two_and_three_device_sync_duplicate_retry_and_offline_queue(sync_engine: SyncEngine):
    devices = [trusted_device(sync_engine, name) for name in ("A", "B", "C")]
    adapter = MemorySyncAdapter()
    for index, device in enumerate(devices):
        sync_engine.append_change(
            "tenant-a",
            device["device_id"],
            f"owner-{chr(65 + index)}",
            entity_type="preferences",
            entity_id=f"profile-{index}",
            operation="UPDATE",
            payload={"theme": ["dark", "light", "system"][index]},
            idempotency_key=f"multi-{index}",
        )
    first = sync_engine.sync_once("tenant-a", devices[0]["device_id"], adapter)
    assert first.acknowledged == 3
    duplicate = sync_engine.sync_once(
        "tenant-a",
        devices[1]["device_id"],
        adapter,
        cursor="0",
    )
    assert duplicate.pushed == 0
    assert len(adapter._changes["tenant-a"]) == 3

    adapter.available = False
    sync_engine.append_change(
        "tenant-a",
        devices[2]["device_id"],
        "owner-C",
        entity_type="notes",
        entity_id="offline-note",
        operation="CREATE",
        payload={"body": "durable offline edit"},
        idempotency_key="offline-edit",
    )
    with pytest.raises(ResearchPlatformError, match="remain queued"):
        sync_engine.sync_once("tenant-a", devices[2]["device_id"], adapter)
    assert sync_engine.status("tenant-a")["pending_changes"] == 1


def test_manual_conflict_wrong_tenant_and_corruption_are_fail_closed(sync_engine: SyncEngine):
    local_device = trusted_device(sync_engine, "A")
    remote_device = trusted_device(sync_engine, "B")
    local = sync_engine.append_change(
        "tenant-a",
        local_device["device_id"],
        "owner-A",
        entity_type="notes",
        entity_id="shared-note",
        operation="UPDATE",
        payload={"body": "local"},
        idempotency_key="local-note",
    )
    remote_payload = {"body": "remote"}
    remote = {
        **local,
        "change_id": "change_remote",
        "idempotency_key": "remote-note",
        "device_id": remote_device["device_id"],
        "actor_id": "owner-B",
        "entity_version": 2,
        "payload_ciphertext": sync_engine._encrypt(remote_payload),
        "checksum": hashlib.sha256(
            b'{"body":"remote"}'
        ).hexdigest(),
    }
    assert sync_engine.apply_remote_change("tenant-a", remote) == "conflict"
    assert sync_engine.status("tenant-a")["open_conflicts"] == 1
    conflict = sync_engine.conflicts("tenant-a")[0]
    resolved = sync_engine.resolve_conflict(
        "tenant-a",
        conflict["conflict_id"],
        "administrator-a",
        decision="keep_local",
    )
    assert resolved["state"] == "resolved"
    assert sync_engine.status("tenant-a")["open_conflicts"] == 0

    wrong_tenant = {**remote, "change_id": "change_wrong", "tenant_id": "tenant-b"}
    with pytest.raises(PermissionDenied):
        sync_engine.apply_remote_change("tenant-a", wrong_tenant)
    corrupt = {**remote, "change_id": "change_corrupt", "payload_ciphertext": "invalid"}
    with pytest.raises(IntegrityFailure):
        sync_engine.apply_remote_change("tenant-a", corrupt)


def test_file_identity_checksum_chunk_resume_and_filename_collision(
    sync_engine: SyncEngine,
    tmp_path: Path,
):
    first_path = tmp_path / "a" / "results.csv"
    second_path = tmp_path / "b" / "results.csv"
    first_path.parent.mkdir()
    second_path.parent.mkdir()
    first_path.write_text("sample,value\nA,1\n", encoding="utf-8")
    second_path.write_text("sample,value\nB,2\n", encoding="utf-8")
    first = sync_engine.register_file(
        "tenant-a",
        "owner-A",
        "owner-A",
        entity_type="selected_files",
        entity_id="project-1",
        source_path=first_path,
    )
    second = sync_engine.register_file(
        "tenant-a",
        "owner-A",
        "owner-A",
        entity_type="selected_files",
        entity_id="project-1",
        source_path=second_path,
    )
    assert first["file_id"] != second["file_id"]
    assert first["original_name"] == second["original_name"]
    assert sync_engine.verify_file(first["file_id"])
    chunks = sync_engine.plan_chunks(first["file_id"], direction="upload", chunk_size=64 * 1024)
    assert chunks and chunks[0]["byte_offset"] == 0


def test_phase32_fastapi_and_streamlit_surfaces(
    sync_engine: SyncEngine,
    monkeypatch,
    tmp_path: Path,
):
    from biointel.education.phase32_35 import api

    monkeypatch.setattr(api, "_ENGINE", sync_engine)
    app = FastAPI()
    app.include_router(api.router)
    client = TestClient(app)
    capabilities = client.get("/phase32/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["remote_provider"].startswith("adapter")
    registration = client.post(
        "/phase32/devices",
        json={
            "tenant_id": "tenant-a",
            "owner_id": "user-a",
            "device_name": "API device",
            "device_type": "desktop",
            "operating_system": "Windows",
            "permissions": ["notes"],
        },
    )
    assert registration.status_code == 201
    status = client.get("/phase32/tenants/tenant-a/status")
    assert status.status_code == 200
    assert status.json()["devices"][0]["state"] == "pending"

    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path / "streamlit-user-data"))
    page = Path(__file__).resolve().parents[1] / "pages" / "348_BioIntel_Secure_Sync.py"
    rendered = AppTest.from_file(str(page), default_timeout=60).run(timeout=60)
    assert not rendered.exception
