from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from biointel.api.middleware import (
    OptionalApiKeyMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from biointel.api.security_store import ApiSecurityStore
from biointel.education.phase32_35.base import (
    IntegrityFailure,
    PermissionDenied,
)
from biointel.education.phase32_35.compute import ResearchCompute
from biointel.education.phase32_35.discovery import DiscoveryEcosystem
from biointel.education.phase32_35.sync import SyncEngine
from biointel.multitenancy.middleware import TenantContextMiddleware
from biointel.multitenancy.store import TenantStore


def test_remote_api_auth_role_and_tenant_context_are_fail_closed(
    tmp_path: Path,
    monkeypatch,
):
    from biointel.education.phase32_35 import compute_api

    compute = ResearchCompute(tmp_path / "education.sqlite3", tmp_path / "media")
    project = compute.create_project(
        "tenant-a",
        "owner-a",
        "institution-a",
        title="Tenant A project",
    )
    monkeypatch.setattr(compute_api, "_COMPUTE", compute)
    security = ApiSecurityStore(tmp_path / "api-security.sqlite3")
    tenants = TenantStore(tmp_path / "tenants.sqlite3")
    tenants.ensure_tenant("tenant-a", "Tenant A")
    tenants.ensure_tenant("tenant-b", "Tenant B")
    security.register_client(
        client_id="operator-a",
        display_name="Operator A",
        role="operator",
        raw_key="operator-secret",
        quota_per_minute=100,
        metadata={"tenant_ids": ["tenant-a"], "default_tenant": "tenant-a"},
    )
    security.register_client(
        client_id="viewer-a",
        display_name="Viewer A",
        role="viewer",
        raw_key="viewer-secret",
        quota_per_minute=100,
        metadata={"tenant_ids": ["tenant-a"], "default_tenant": "tenant-a"},
    )
    tenants.add_membership("tenant-a", "operator-a", "owner")
    tenants.add_membership("tenant-a", "viewer-a", "viewer")
    app = FastAPI()
    app.include_router(compute_api.router)
    app.add_middleware(TenantContextMiddleware, tenant_store=tenants)
    app.add_middleware(
        OptionalApiKeyMiddleware,
        api_key=None,
        security_store=security,
        require_auth=True,
    )
    client = TestClient(app)
    assert client.get("/phase34/capabilities").status_code == 401
    viewer_headers = {
        "X-API-Key": "viewer-secret",
        "X-BioIntel-Tenant": "tenant-a",
    }
    listed = client.get("/phase34/tenants/tenant-a/projects", headers=viewer_headers)
    assert listed.status_code == 200
    assert listed.json()[0]["project_id"] == project["project_id"]
    denied_write = client.post(
        "/phase34/projects",
        headers=viewer_headers,
        json={
            "tenant_id": "tenant-a",
            "owner_id": "viewer-a",
            "institution_id": "institution-a",
            "title": "Must be denied",
        },
    )
    assert denied_write.status_code == 403
    wrong_tenant = client.get(
        "/phase34/tenants/tenant-b/projects",
        headers={
            "X-API-Key": "operator-secret",
            "X-BioIntel-Tenant": "tenant-b",
        },
    )
    assert wrong_tenant.status_code == 403


def test_request_limits_and_security_headers(tmp_path: Path):
    app = FastAPI()

    @app.post("/payload")
    def payload(value: dict):
        return value

    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=64, upload_max_bytes=64)
    app.add_middleware(SecurityHeadersMiddleware, api_version="phase31-35")
    client = TestClient(app)
    normal = client.post("/payload", json={"value": "safe"})
    assert normal.status_code == 200
    assert normal.headers["x-content-type-options"] == "nosniff"
    assert normal.headers["x-frame-options"] == "DENY"
    assert normal.headers["cache-control"] == "no-store"
    oversized = client.post("/payload", json={"value": "x" * 100})
    assert oversized.status_code == 413


def test_sync_payloads_tokens_journal_and_diagnostics_are_protected(tmp_path: Path):
    sync = SyncEngine(tmp_path / "education.sqlite3", tmp_path / "media")
    device = sync.register_device(
        "tenant-a",
        "owner-a",
        device_name="Secure device",
        device_type="desktop",
        operating_system="Windows",
        permissions=["notes"],
        approved_by="administrator-a",
    )
    sync.create_session(
        device["device_id"],
        "plain-session-token",
        expires_at_utc="2099-01-01T00:00:00+00:00",
    )
    change = sync.append_change(
        "tenant-a",
        device["device_id"],
        "owner-a",
        entity_type="notes",
        entity_id="secret-note",
        operation="UPDATE",
        payload={"body": "confidential research note"},
        idempotency_key="protected-journal",
    )
    assert "confidential research note" not in change["payload_ciphertext"]
    with sync.store.connection() as connection:
        session = connection.execute(
            "SELECT * FROM education_p32_device_sessions"
        ).fetchone()
        assert "plain-session-token" not in session["token_ciphertext"]
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM education_p32_sync_journal WHERE change_id=?",
                (change["change_id"],),
            )
    sync.revoke_device(device["device_id"], "administrator-a")
    diagnostic_text = json.dumps(sync.diagnostic_bundle("tenant-a"))
    assert "plain-session-token" not in diagnostic_text
    assert "confidential research note" not in diagnostic_text
    assert "DEVICE_REVOKED" in diagnostic_text


def test_compute_credentials_archives_and_server_path_import_are_protected(
    tmp_path: Path,
    monkeypatch,
):
    from biointel.education.phase32_35.compute_api import _approved_import_paths

    compute = ResearchCompute(tmp_path / "education.sqlite3", tmp_path / "media")
    adapter = compute.register_remote_adapter(
        "tenant-a",
        "administrator-a",
        administrator_role="institution_administrator",
        adapter_type="slurm",
        endpoint="ssh://cluster.example",
        allowed_hosts=["cluster.example"],
        command_templates=["sbatch {approved_script}"],
        credentials={"token": "remote-credential-secret"},
        resource_limits={"cpu": 4},
    )
    status = compute.remote_adapter_status(adapter["adapter_id"])
    assert "remote-credential-secret" not in json.dumps(status)
    stored = compute.store.one(
        "SELECT encrypted_credentials FROM education_p34_remote_adapters WHERE adapter_id=?",
        (adapter["adapter_id"],),
    )
    assert stored and "remote-credential-secret" not in stored["encrypted_credentials"]

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("../escape.txt", "unsafe")
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "schema": "biointel.phase34.reproducibility-bundle.v1",
                    "run": {"run_id": "unsafe"},
                    "artifacts": [],
                }
            ),
        )
    with pytest.raises(IntegrityFailure, match="Unsafe"):
        compute.inspect_run_bundle(stream.getvalue())

    approved_root = tmp_path / "approved-imports"
    approved_root.mkdir()
    inside = approved_root / "inside.csv"
    inside.write_text("a,b\n1,2\n", encoding="utf-8")
    outside = tmp_path / "outside.csv"
    outside.write_text("a,b\n3,4\n", encoding="utf-8")
    monkeypatch.setenv("BIOINTEL_RESEARCH_IMPORT_ROOT", str(approved_root))
    assert _approved_import_paths([str(inside)]) == [inside.resolve()]
    with pytest.raises(PermissionDenied, match="outside"):
        _approved_import_paths([str(outside)])


def test_discovery_refuses_clinical_actions_and_cross_tenant_evidence(tmp_path: Path):
    discovery = DiscoveryEcosystem(tmp_path / "education.sqlite3", tmp_path / "media")
    project_a = discovery.compute.create_project(
        "tenant-a",
        "owner-a",
        "institution-a",
        title="A",
    )
    project_b = discovery.compute.create_project(
        "tenant-b",
        "owner-b",
        "institution-b",
        title="B",
    )
    workspace_a = discovery.create_workspace(project_a["project_id"], "owner-a")
    workspace_b = discovery.create_workspace(project_b["project_id"], "owner-b")
    source_b = discovery.register_evidence(
        workspace_b["workspace_id"],
        "owner-b",
        source_type="paper",
        title="Tenant B evidence",
        citation="Local fixture B",
        abstract_text="tenant b",
    )
    refused = discovery.create_agent_task(
        workspace_a["workspace_id"],
        "owner-a",
        agent_key="biomarker_discovery",
        task_input={"requested_action": "claim_clinical_validation"},
        idempotency_key="clinical-refusal",
    )
    assert refused["state"] == "refused"
    with pytest.raises(PermissionDenied, match="outside"):
        discovery.create_agent_task(
            workspace_a["workspace_id"],
            "owner-a",
            agent_key="evidence_synthesis",
            task_input={"question": "cross tenant"},
            evidence_ids=[source_b["source_id"]],
            idempotency_key="cross-tenant",
        )
