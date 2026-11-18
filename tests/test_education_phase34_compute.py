from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from biointel.education.phase32_35.base import (
    Conflict,
    IntegrityFailure,
    PermissionDenied,
    ResearchPlatformError,
)
from biointel.education.phase32_35.compute import (
    INITIAL_WORKFLOW_LIBRARY,
    ResearchCompute,
    detect_format,
)


@pytest.fixture()
def compute(tmp_path: Path) -> ResearchCompute:
    return ResearchCompute(tmp_path / "education.sqlite3", tmp_path / "media")


def project(compute: ResearchCompute, *, tenant: str = "tenant-a") -> dict:
    return compute.create_project(
        tenant,
        "researcher-a",
        "institution-a",
        title="Reproducible genomics QC",
        hypothesis="The bounded fixture passes format and quality checks.",
        objectives=["Validate", "Reproduce"],
    )


def runnable_fixture(compute: ResearchCompute, tmp_path: Path) -> tuple[dict, dict, dict]:
    research = project(compute)
    source = tmp_path / "fixture.fasta"
    source.write_text(">alpha\nACGTACGTNN\n>beta\nGGCC\n", encoding="utf-8")
    dataset = compute.register_dataset(
        research["project_id"],
        "researcher-a",
        title="FASTA fixture",
        source_paths=[source],
        source="deterministic test fixture",
        licence="CC0",
        consent_status="not_applicable",
        access_level="private",
    )
    workflow = compute.define_workflow(
        research["project_id"],
        "administrator-a",
        name="genomics_fasta_qc",
        domain="genomics",
        version="1.0.0",
        steps=INITIAL_WORKFLOW_LIBRARY["genomics_fasta_qc"]["steps"],
        approve=True,
        approver_role="institution_administrator",
    )
    return research, dataset, workflow


def test_format_detection_is_bounded_and_rejects_malformed_files(tmp_path: Path):
    fasta = tmp_path / "sample.fa"
    fasta.write_text(">id\nACGT\n", encoding="utf-8")
    assert detect_format(fasta)[0] == "FASTA"
    dicom = tmp_path / "sample.dcm"
    dicom.write_bytes(bytes(128) + b"DICM" + bytes(32))
    detected, details = detect_format(dicom)
    assert detected == "DICOM_METADATA"
    assert "no diagnostic interpretation" in details["validation"]
    malformed = tmp_path / "bad.vcf"
    malformed.write_text("not a VCF", encoding="utf-8")
    with pytest.raises(IntegrityFailure, match="signature"):
        detect_format(malformed)
    unsupported = tmp_path / "payload.exe"
    unsupported.write_bytes(b"MZ")
    with pytest.raises(ResearchPlatformError, match="Unsupported"):
        detect_format(unsupported)


def test_dataset_registry_checksums_copies_and_workspace_assets(
    compute: ResearchCompute,
    tmp_path: Path,
):
    research, dataset, _workflow = runnable_fixture(compute, tmp_path)
    assert dataset["format"] == "FASTA"
    assert dataset["manifest_sha256"]
    assert dataset["files"][0]["imported_bytes"] == dataset["files"][0]["size_bytes"]
    asset = compute.add_project_asset(
        research["project_id"],
        "researcher-a",
        asset_type="sample_sheet",
        title="Sample sheet",
        content={"samples": [{"id": "alpha"}, {"id": "beta"}]},
    )
    workspace = compute.project_workspace(research["project_id"])
    assert asset["asset_type"] == "sample_sheet"
    assert len(workspace["datasets"]) == 1
    assert json.loads(workspace["assets"][0]["content_json"])["samples"][0]["id"] == "alpha"


def test_dataset_import_can_pause_and_resume_without_exposing_source_paths(
    compute: ResearchCompute,
    tmp_path: Path,
):
    research = project(compute)
    source = tmp_path / "resumable.fasta"
    source.write_text(">sequence\n" + ("ACGT" * 1024) + "\n", encoding="utf-8")
    session = compute.begin_dataset_import(
        research["project_id"],
        "researcher-a",
        title="Resumable fixture",
        source_paths=[source],
        source="local fixture",
        licence="CC0",
        consent_status="not_applicable",
        access_level="private",
    )
    assert "encrypted_request" not in session
    assert "staging_location" not in session
    paused = compute.resume_dataset_import(
        session["session_id"],
        "researcher-a",
        max_bytes=128,
    )
    assert paused["state"] == "paused"
    completed = compute.resume_dataset_import(
        session["session_id"],
        "researcher-a",
        max_bytes=1024 * 1024,
    )
    assert completed["state"] == "completed"
    assert completed["dataset_id"]


def test_tool_registry_and_workflow_definition_block_arbitrary_execution(
    compute: ResearchCompute,
):
    research = project(compute)
    tools = compute.approved_tools()
    assert {row["tool_name"] for row in tools} == {
        "file_manifest",
        "fasta_qc",
        "fastq_qc",
        "structure_inspect",
        "tabular_qc",
        "vcf_qc",
    }
    with pytest.raises(PermissionDenied, match="not approved"):
        compute.define_workflow(
            research["project_id"],
            "researcher-a",
            name="unsafe",
            domain="test",
            version="1",
            steps=[{"id": "shell", "tool": "powershell"}],
        )
    with pytest.raises(PermissionDenied, match="arbitrary commands"):
        compute.define_workflow(
            research["project_id"],
            "researcher-a",
            name="unsafe",
            domain="test",
            version="2",
            steps=[{"id": "shell", "tool": "file_manifest", "command": "whoami"}],
        )
    with pytest.raises(ResearchPlatformError, match="cycle"):
        compute.define_workflow(
            research["project_id"],
            "researcher-a",
            name="cycle",
            domain="test",
            version="1",
            steps=[
                {"id": "one", "tool": "file_manifest", "dependencies": ["two"]},
                {"id": "two", "tool": "file_manifest", "dependencies": ["one"]},
            ],
        )


def test_local_orchestration_is_idempotent_checkpointed_and_reproducible(
    compute: ResearchCompute,
    tmp_path: Path,
):
    research, dataset, workflow = runnable_fixture(compute, tmp_path)
    submitted = compute.submit_run(
        research["project_id"],
        workflow["workflow_id"],
        dataset["dataset_id"],
        "researcher-a",
        idempotency_key="fixture-run",
        seed=123,
    )
    duplicate = compute.submit_run(
        research["project_id"],
        workflow["workflow_id"],
        dataset["dataset_id"],
        "researcher-a",
        idempotency_key="fixture-run",
    )
    assert duplicate["run_id"] == submitted["run_id"]
    completed = compute.execute_run(submitted["run_id"])
    assert completed["state"] == "completed"
    explorer = compute.result_explorer(completed["run_id"])
    assert explorer["quality_metrics"] == {
        "completed_steps": 2,
        "total_steps": 2,
        "verified_artifacts": 2,
    }
    with pytest.raises(Conflict, match="not claimable"):
        compute.execute_run(completed["run_id"])
    bundle = compute.export_run_bundle(completed["run_id"])
    inspection = compute.inspect_run_bundle(bundle)
    assert inspection["valid"] is True
    assert inspection["import_execution_performed"] is False
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["run"]["seed"] == 123
    assert manifest["provenance_graph"]["edges"]


def test_failure_retry_checkpoint_recovery_and_cancellation(
    compute: ResearchCompute,
    tmp_path: Path,
):
    research, dataset, workflow = runnable_fixture(compute, tmp_path)
    run = compute.submit_run(
        research["project_id"],
        workflow["workflow_id"],
        dataset["dataset_id"],
        "researcher-a",
        idempotency_key="retry-fixture",
        max_retries=1,
    )
    stored = Path(dataset["storage_location"]) / dataset["files"][0]["relative_path"]
    original = stored.read_bytes()
    stored.write_bytes(b">tampered\nAAAA\n")
    with pytest.raises(IntegrityFailure, match="checksum changed"):
        compute.execute_run(run["run_id"])
    assert compute.run(run["run_id"])["state"] == "failed"
    stored.write_bytes(original)
    assert compute.retry_run(run["run_id"], "researcher-a")["state"] == "retrying"
    assert compute.execute_run(run["run_id"])["state"] == "completed"

    second = compute.submit_run(
        research["project_id"],
        workflow["workflow_id"],
        dataset["dataset_id"],
        "researcher-a",
        idempotency_key="cancel-fixture",
    )
    assert compute.cancel_run(second["run_id"], "researcher-a")["state"] == "cancelled"
    with pytest.raises(PermissionDenied):
        compute.cancel_run(second["run_id"], "someone-else")


def test_quota_tenant_isolation_and_format_compatibility(
    compute: ResearchCompute,
    tmp_path: Path,
):
    research, dataset, workflow = runnable_fixture(compute, tmp_path)
    compute.set_quota(
        "tenant-a",
        "administrator-a",
        administrator_role="institution_administrator",
        max_cpu=1,
        max_gpu=0,
    )
    with pytest.raises(PermissionDenied, match="quota"):
        compute.submit_run(
            research["project_id"],
            workflow["workflow_id"],
            dataset["dataset_id"],
            "researcher-a",
            idempotency_key="too-large",
            cpu_limit=2,
        )
    other = project(compute, tenant="tenant-b")
    with pytest.raises((PermissionDenied, ResearchPlatformError)):
        compute.submit_run(
            other["project_id"],
            workflow["workflow_id"],
            dataset["dataset_id"],
            "researcher-a",
            idempotency_key="cross-tenant",
        )

    csv_path = tmp_path / "table.csv"
    csv_path.write_text("sample,value\nA,1\n", encoding="utf-8")
    csv_dataset = compute.register_dataset(
        research["project_id"],
        "researcher-a",
        title="Table",
        source_paths=[csv_path],
        source="fixture",
        licence="CC0",
        consent_status="not_applicable",
        access_level="private",
    )
    with pytest.raises(ResearchPlatformError, match="incompatible"):
        compute.submit_run(
            research["project_id"],
            workflow["workflow_id"],
            csv_dataset["dataset_id"],
            "researcher-a",
            idempotency_key="wrong-format",
        )


def test_review_publication_handoffs_and_reference_only_bundle_import(
    compute: ResearchCompute,
    tmp_path: Path,
):
    research, dataset, workflow = runnable_fixture(compute, tmp_path)
    queued = compute.submit_run(
        research["project_id"],
        workflow["workflow_id"],
        dataset["dataset_id"],
        "researcher-a",
        idempotency_key="review-fixture",
    )
    completed = compute.execute_run(queued["run_id"])
    with pytest.raises(PermissionDenied, match="reviewer approval"):
        compute.publish_to_project(completed["run_id"], "researcher-a", title="QC report")
    review = compute.review_run(
        completed["run_id"],
        "reviewer-a",
        reviewer_role="project_reviewer",
        decision="approved",
        comments="Fixture output reviewed.",
    )
    report = compute.publish_to_project(
        completed["run_id"],
        "researcher-a",
        title="QC report",
    )
    handoff = compute.create_handoff(
        completed["run_id"],
        "researcher-a",
        destination="shiro",
        payload={"evidence_summary": "Human review still required"},
    )
    imported = compute.import_run_bundle(
        "tenant-a",
        "researcher-a",
        compute.export_run_bundle(completed["run_id"]),
    )
    assert review["decision"] == "approved"
    assert report["asset_type"] == "report"
    assert handoff["state"] == "review_required"
    assert imported["state"] == "reference_only"


def test_remote_adapter_is_redacted_disabled_and_strictly_configured(
    compute: ResearchCompute,
):
    with pytest.raises(PermissionDenied, match="allowlist"):
        compute.register_remote_adapter(
            "tenant-a",
            "administrator-a",
            administrator_role="institution_administrator",
            adapter_type="slurm",
            endpoint="ssh://cluster.example",
            allowed_hosts=["other.example"],
            command_templates=["sbatch {approved_script}"],
            credentials={"token": "secret"},
            resource_limits={"cpu": 8},
        )
    with pytest.raises(PermissionDenied, match="metacharacter"):
        compute.register_remote_adapter(
            "tenant-a",
            "administrator-a",
            administrator_role="institution_administrator",
            adapter_type="ssh_batch",
            endpoint="ssh://cluster.example",
            allowed_hosts=["cluster.example"],
            command_templates=["approved {input}; whoami"],
            credentials={"token": "secret"},
            resource_limits={"cpu": 8},
        )
    adapter = compute.register_remote_adapter(
        "tenant-a",
        "administrator-a",
        administrator_role="institution_administrator",
        adapter_type="slurm",
        endpoint="ssh://cluster.example",
        allowed_hosts=["cluster.example"],
        command_templates=["sbatch {approved_script}"],
        credentials={"token": "secret"},
        resource_limits={"cpu": 8},
    )
    status = compute.remote_adapter_status(adapter["adapter_id"])
    assert status["enabled"] == 0
    assert status["credentials_exposed"] is False
    assert status["health_check_performed"] is False
    assert "secret" not in json.dumps(status)


def test_phase34_fastapi_and_streamlit_surfaces(
    compute: ResearchCompute,
    monkeypatch,
    tmp_path: Path,
):
    from biointel.education.phase32_35 import compute_api

    monkeypatch.setattr(compute_api, "_COMPUTE", compute)
    app = FastAPI()
    app.include_router(compute_api.router)
    client = TestClient(app)
    capabilities = client.get("/phase34/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["arbitrary_user_shell"] is False
    assert client.get("/phase34/tools").status_code == 200
    created = client.post(
        "/phase34/projects",
        json={
            "tenant_id": "tenant-a",
            "owner_id": "researcher-a",
            "institution_id": "institution-a",
            "title": "API project",
        },
    )
    assert created.status_code == 201

    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path / "streamlit-user-data"))
    page = (
        Path(__file__).resolve().parents[1]
        / "pages"
        / "350_Bioinformatics_Research_Compute.py"
    )
    rendered = AppTest.from_file(str(page), default_timeout=60).run(timeout=60)
    assert not rendered.exception
