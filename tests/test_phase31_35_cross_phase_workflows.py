from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from biointel.education.phase32_35.base import (
    PermissionDenied,
    PlatformStore,
    canonical_json,
)
from biointel.education.phase32_35.compute import ResearchCompute
from biointel.education.phase32_35.discovery import DiscoveryEcosystem
from biointel.education.phase32_35.schema import MIGRATION_ID
from biointel.education.phase32_35.sync import MemorySyncAdapter, SyncEngine
from biointel.education.phase32_35.twin import DigitalTwinLab


def reviewed_task(
    discovery: DiscoveryEcosystem,
    workspace_id: str,
    agent_key: str,
    task_input: dict,
    evidence_ids: list[str],
    key: str,
) -> dict:
    task = discovery.create_agent_task(
        workspace_id,
        "researcher-a",
        agent_key=agent_key,
        task_input=task_input,
        evidence_ids=evidence_ids,
        idempotency_key=key,
    )
    task = discovery.execute_agent_task(task["task_id"])
    discovery.decide_approval(
        task["task_id"],
        "reviewer-a",
        reviewer_role="scientific_reviewer",
        operation="task_output_review",
        decision="approved",
    )
    return discovery.task(task["task_id"])


def test_workflow_a_local_migration_restart_and_persistence(tmp_path: Path):
    database = tmp_path / "education.sqlite3"
    media = tmp_path / "media"
    store = PlatformStore(database)
    assert store.migrate() == MIGRATION_ID
    assert store.migrate() == MIGRATION_ID
    assert store.quick_check()
    compute = ResearchCompute(database, media)
    project = compute.create_project(
        "tenant-a",
        "researcher-a",
        "institution-a",
        title="Persistent research project",
    )
    del compute
    restarted = ResearchCompute(database, media)
    persisted = restarted.projects("tenant-a")
    assert [row["project_id"] for row in persisted] == [project["project_id"]]
    assert restarted.store.quick_check()


def test_workflows_b_and_g_multi_device_conflict_file_and_revocation(
    tmp_path: Path,
):
    sync = SyncEngine(tmp_path / "education.sqlite3", tmp_path / "media")
    device_a = sync.register_device(
        "tenant-a",
        "researcher-a",
        device_name="Device A",
        device_type="desktop",
        operating_system="Windows 11",
        permissions=["notes", "research_projects", "selected_files"],
        approved_by="administrator-a",
    )
    device_b = sync.register_device(
        "tenant-a",
        "researcher-a",
        device_name="Device B",
        device_type="laptop",
        operating_system="Windows 10",
        permissions=["notes", "research_projects", "selected_files"],
        approved_by="administrator-a",
    )
    adapter = MemorySyncAdapter()
    local = sync.append_change(
        "tenant-a",
        device_a["device_id"],
        "researcher-a",
        entity_type="notes",
        entity_id="shared-note",
        operation="UPDATE",
        payload={"body": "Device A offline note"},
        idempotency_key="device-a-note",
    )
    sync.sync_once("tenant-a", device_a["device_id"], adapter)
    remote_payload = {"body": "Device B offline note"}
    remote = {
        **local,
        "change_id": "remote-device-b-change",
        "idempotency_key": "device-b-note",
        "device_id": device_b["device_id"],
        "actor_id": "researcher-a",
        "entity_version": 2,
        "payload_ciphertext": sync._encrypt(remote_payload),
        "checksum": hashlib.sha256(canonical_json(remote_payload).encode()).hexdigest(),
    }
    assert sync.apply_remote_change("tenant-a", remote) == "conflict"
    conflict = sync.conflicts("tenant-a")[0]
    resolved = sync.resolve_conflict(
        "tenant-a",
        conflict["conflict_id"],
        "administrator-a",
        decision="merge",
        merged_payload={"body": "Human merged Device A and Device B notes"},
    )
    assert resolved["state"] == "resolved"
    assert sync.status("tenant-a")["open_conflicts"] == 0

    source = tmp_path / "results.csv"
    source.write_text("sample,value\nA,1\n", encoding="utf-8")
    registered = sync.register_file(
        "tenant-a",
        "researcher-a",
        "researcher-a",
        entity_type="selected_files",
        entity_id="research-project",
        source_path=source,
    )
    assert sync.verify_file(registered["file_id"])
    sync.create_session(
        device_b["device_id"],
        "device-b-session-token",
        expires_at_utc="2099-01-01T00:00:00+00:00",
    )
    sync.revoke_device(device_b["device_id"], "administrator-a", lost=True)
    with pytest.raises(PermissionDenied):
        sync.append_change(
            "tenant-a",
            device_b["device_id"],
            "researcher-a",
            entity_type="notes",
            entity_id="blocked",
            operation="UPDATE",
            payload={"body": "must fail"},
            idempotency_key="revoked-device-write",
        )
    diagnostics = sync.diagnostic_bundle("tenant-a")
    assert any(row["code"] == "DEVICE_LOST" for row in diagnostics["incidents"])
    assert "device-b-session-token" not in json.dumps(diagnostics)


def test_workflow_c_digital_twin_learning_review_mastery_and_portfolio(
    tmp_path: Path,
):
    lab = DigitalTwinLab(tmp_path / "education.sqlite3", tmp_path / "media")
    project = lab.create_project(
        "tenant-a",
        "teacher-a",
        "institution-a",
        title="Synthetic disease mechanism lesson",
        purpose="Teach model assumptions and uncertainty.",
        classification="Disease-Mechanism Twin",
    )
    model = lab.register_model(
        project["project_id"],
        "teacher-a",
        model_key="glucose_regulation_v1",
    )
    scenario = lab.create_scenario(
        project["project_id"],
        model["model_id"],
        "teacher-a",
        name="Synthetic intervention",
        time_steps=12,
        interventions=[
            {
                "time": 2.0,
                "target": "insulin_sensitivity",
                "mode": "multiply",
                "value": 0.8,
            }
        ],
    )
    simulation = lab.run_scenario(scenario["scenario_id"], "teacher-a")
    explanation = lab.shiro_model_explanation(model["model_id"])
    assert explanation["external_ai_called"] is False
    assert explanation["non_clinical"] is True
    assert simulation.uncertainty
    for target in ("shiro", "classroom", "portfolio"):
        link = lab.link_integration(
            project["project_id"],
            "teacher-a",
            target_module=target,
            target_object_id=f"{target}-fixture",
            purpose="Review-gated education handoff",
            payload={"simulation_id": simulation.simulation_id},
        )
        assert link["state"] == "review_required"
    activity = lab.create_learning_activity(
        project["project_id"],
        simulation.simulation_id,
        "teacher-a",
        classroom_reference="classroom-fixture",
        interpretation_prompt="Explain the trajectory and its uncertainty.",
    )
    submission = lab.submit_interpretation(
        activity["activity_id"],
        "student-a",
        interpretation_text=(
            "The synthetic intervention changed the model trajectory, but the uncertainty "
            "and assumptions prevent clinical interpretation."
        ),
    )
    reviewed = lab.review_interpretation(
        submission["submission_id"],
        "teacher-a",
        score=88,
        feedback="Good model-bound interpretation.",
    )
    portfolio = json.loads(reviewed["portfolio_record_json"])
    assert reviewed["state"] == "reviewed"
    assert reviewed["mastery_delta"] > 0
    assert portfolio["non_clinical"] is True


def test_workflow_d_research_compute_review_report_and_bundle(tmp_path: Path):
    compute = ResearchCompute(tmp_path / "education.sqlite3", tmp_path / "media")
    project = compute.create_project(
        "tenant-a",
        "researcher-a",
        "institution-a",
        title="Local bioinformatics run",
    )
    source = tmp_path / "sequence.fasta"
    source.write_text(">alpha\nACGTACGTNN\n", encoding="utf-8")
    dataset = compute.register_dataset(
        project["project_id"],
        "researcher-a",
        title="Sequence",
        source_paths=[source],
        source="local fixture",
        licence="CC0",
        consent_status="not_applicable",
        access_level="private",
    )
    workflow = compute.define_workflow(
        project["project_id"],
        "administrator-a",
        name="FASTA QC",
        domain="genomics",
        version="1.0.0",
        steps=[
            {"id": "manifest", "tool": "file_manifest"},
            {"id": "qc", "tool": "fasta_qc", "dependencies": ["manifest"]},
        ],
        approve=True,
        approver_role="institution_administrator",
    )
    run = compute.submit_run(
        project["project_id"],
        workflow["workflow_id"],
        dataset["dataset_id"],
        "researcher-a",
        idempotency_key="cross-phase-compute",
    )
    completed = compute.execute_run(run["run_id"])
    compute.review_run(
        completed["run_id"],
        "reviewer-a",
        reviewer_role="project_reviewer",
        decision="approved",
        comments="Fixture output reviewed.",
    )
    report = compute.publish_to_project(
        completed["run_id"],
        "researcher-a",
        title="Reviewed FASTA QC report",
    )
    bundle = compute.export_run_bundle(completed["run_id"])
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert report["source_run_id"] == completed["run_id"]
    assert manifest["provenance_graph"]["edges"]
    assert compute.inspect_run_bundle(bundle)["valid"] is True


def test_workflows_e_and_f_discovery_twin_compute_and_human_review(
    tmp_path: Path,
):
    database = tmp_path / "education.sqlite3"
    media = tmp_path / "media"
    discovery = DiscoveryEcosystem(database, media)
    research_project = discovery.compute.create_project(
        "tenant-a",
        "researcher-a",
        "institution-a",
        title="Discovery and Digital Twin workspace",
    )
    workspace = discovery.create_workspace(
        research_project["project_id"],
        "researcher-a",
    )
    source = discovery.register_evidence(
        workspace["workspace_id"],
        "researcher-a",
        source_type="paper",
        title="Synthetic pathway evidence",
        citation="Cross-phase deterministic fixture",
        abstract_text="Glucose insulin pathway evidence for a synthetic model.",
        methodology_text="Controlled synthetic benchmark.",
        limitations_text="No clinical validation.",
        claims=["glucose pathway association"],
        retraction_status="not_retracted_as_of_record",
    )
    evidence_task = reviewed_task(
        discovery,
        workspace["workspace_id"],
        "evidence_synthesis",
        {"question": "What pathway hypothesis is testable?"},
        [source["source_id"]],
        "cross-phase-synthesis",
    )
    hypothesis_task = reviewed_task(
        discovery,
        workspace["workspace_id"],
        "hypothesis_generation",
        {"question": "Does synthetic insulin sensitivity alter the glucose trajectory?"},
        [source["source_id"]],
        "cross-phase-hypothesis",
    )
    hypothesis = discovery.create_hypothesis_from_task(
        hypothesis_task["task_id"],
        "researcher-a",
    )
    hypothesis = discovery.transition_hypothesis(
        hypothesis["hypothesis_id"],
        "reviewer-a",
        actor_role="scientific_reviewer",
        new_state="Approved for Testing",
    )
    experiment = discovery.create_experiment_plan(
        hypothesis["hypothesis_id"],
        "researcher-a",
        objective="Test a synthetic pathway model.",
        design={"synthetic": True},
        variables={"independent": ["insulin_sensitivity"]},
        controls=["baseline model"],
        samples={"synthetic": True},
        replicates={"seeds": [1, 2, 3]},
        randomization={},
        blinding={},
        inclusion_criteria=["synthetic scenario"],
        exclusion_criteria=["identifiable data"],
        endpoints=[{"name": "glucose trajectory"}],
        analysis_plan={"sensitivity": True},
        resources={"cpu": 1},
        timeline={"days": 1},
        risks=[{"risk": "overinterpretation"}],
    )
    assert experiment["state"] == "human_review"

    twin = DigitalTwinLab(database, media)
    twin_project = twin.create_project(
        "tenant-a",
        "researcher-a",
        "institution-a",
        title="Synthetic systems model",
        purpose="Research/education pathway scenario.",
    )
    model = twin.register_model(
        twin_project["project_id"],
        "researcher-a",
        model_key="glucose_regulation_v1",
    )
    scenario = twin.create_scenario(
        twin_project["project_id"],
        model["model_id"],
        "researcher-a",
        name="Discovery scenario",
        time_steps=10,
    )
    simulation = twin.run_scenario(scenario["scenario_id"], "researcher-a")
    discovery.set_policy(
        workspace["workspace_id"],
        "administrator-a",
        administrator_role="institution_administrator",
        policy={"digital_twin_project_ids": [twin_project["project_id"]]},
    )
    systems_task = reviewed_task(
        discovery,
        workspace["workspace_id"],
        "systems_biology",
        {
            "question": "Map the synthetic glucose mechanism.",
            "digital_twin_scenario_ids": [scenario["scenario_id"]],
            "pathways": ["glucose regulation"],
        },
        [source["source_id"]],
        "cross-phase-systems",
    )
    output = json.loads(systems_task["output_json"])
    assert output["digital_twin_scenario_draft"]["status"] == "draft_only"
    assert simulation.sensitivity
    assert evidence_task["approval_state"] == "approved"
    graph = discovery.claim_evidence_graph(workspace["workspace_id"])
    assert graph["claim_count"] >= 3
    assert graph["unsupported_claim_count"] == 0
