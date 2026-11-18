from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from biointel.education.phase32_35.base import PermissionDenied
from biointel.education.phase32_35.discovery import (
    AGENT_DEFINITIONS,
    NOVELTY_DISCLAIMER,
    DiscoveryEcosystem,
)


@pytest.fixture()
def discovery(tmp_path: Path) -> DiscoveryEcosystem:
    return DiscoveryEcosystem(tmp_path / "education.sqlite3", tmp_path / "media")


def workspace(discovery: DiscoveryEcosystem, *, tenant: str = "tenant-a") -> dict:
    project = discovery.compute.create_project(
        tenant,
        "researcher-a",
        "institution-a",
        title="Scientific discovery fixture",
        hypothesis="No hypothesis is adopted without human review.",
    )
    return discovery.create_workspace(project["project_id"], "researcher-a")


def evidence_fixture(discovery: DiscoveryEcosystem, workspace_id: str) -> list[dict]:
    first = discovery.register_evidence(
        workspace_id,
        "researcher-a",
        source_type="paper",
        title="Synthetic glucose pathway study",
        citation="Example et al. (2025), synthetic fixture A",
        persistent_identifier="fixture:study-a",
        abstract_text="Glucose insulin pathway model with controlled synthetic observations.",
        methodology_text="Randomized synthetic benchmark with held-out evaluation.",
        limitations_text="Synthetic data and limited pathway scope.",
        claims=["glucose pathway association", "insulin response"],
        metadata={"image_sha256": "image-fixture-shared"},
        retraction_status="not_retracted_as_of_record",
    )
    second = discovery.register_evidence(
        workspace_id,
        "researcher-a",
        source_type="paper",
        title="Independent synthetic insulin response study",
        citation="Example et al. (2026), synthetic fixture B",
        persistent_identifier="fixture:study-b",
        abstract_text="Independent glucose and insulin mechanism benchmark.",
        methodology_text="Controlled time-series synthetic benchmark.",
        limitations_text="No patient or clinical validation.",
        claims=["glucose pathway association", "insulin response"],
        metadata={"image_sha256": "image-fixture-shared"},
        retraction_status="not_retracted_as_of_record",
    )
    return [first, second]


def run_reviewed_task(
    discovery: DiscoveryEcosystem,
    workspace_id: str,
    agent_key: str,
    task_input: dict,
    evidence_ids: list[str],
    *,
    suffix: str,
) -> dict:
    task = discovery.create_agent_task(
        workspace_id,
        "researcher-a",
        agent_key=agent_key,
        task_input=task_input,
        evidence_ids=evidence_ids,
        idempotency_key=f"{agent_key}:{suffix}",
    )
    completed = discovery.execute_agent_task(task["task_id"])
    discovery.decide_approval(
        completed["task_id"],
        "reviewer-a",
        reviewer_role="scientific_reviewer",
        operation="task_output_review",
        decision="approved",
    )
    return discovery.task(completed["task_id"])


def compute_fixture(
    discovery: DiscoveryEcosystem,
    workspace_row: dict,
    tmp_path: Path,
) -> tuple[dict, dict]:
    source = tmp_path / "fixture.fasta"
    source.write_text(">sequence\nACGTACGT\n", encoding="utf-8")
    dataset = discovery.compute.register_dataset(
        workspace_row["research_project_id"],
        "researcher-a",
        title="Compute fixture",
        source_paths=[source],
        source="deterministic fixture",
        licence="CC0",
        consent_status="not_applicable",
        access_level="private",
    )
    workflow = discovery.compute.define_workflow(
        workspace_row["research_project_id"],
        "administrator-a",
        name="manifest",
        domain="general",
        version="1.0.0",
        steps=[{"id": "manifest", "tool": "file_manifest"}],
        approve=True,
        approver_role="institution_administrator",
    )
    run = discovery.compute.submit_run(
        workspace_row["research_project_id"],
        workflow["workflow_id"],
        dataset["dataset_id"],
        "researcher-a",
        idempotency_key=f"compute:{workspace_row['workspace_id']}",
    )
    return dataset, run


def test_registry_extends_phase24_with_twelve_controlled_agents(
    discovery: DiscoveryEcosystem,
):
    registry = discovery.agent_registry()
    assert len(registry) == 12
    assert {row["agent_key"] for row in registry} == set(AGENT_DEFINITIONS)
    for row in registry:
        prohibited = set(json.loads(row["prohibited_actions_json"]))
        assert {"diagnose", "recommend_treatment", "approve_ethics"}.issubset(prohibited)


def test_local_literature_search_ranks_deduplicates_and_states_boundary(
    discovery: DiscoveryEcosystem,
):
    current = workspace(discovery)
    sources = evidence_fixture(discovery, current["workspace_id"])
    retracted = discovery.register_evidence(
        current["workspace_id"],
        "researcher-a",
        source_type="paper",
        title="Retracted glucose fixture",
        citation="Retracted fixture",
        abstract_text="glucose pathway",
        claims=["glucose pathway association"],
        retraction_status="retracted",
    )
    result = discovery.search_literature(
        current["workspace_id"],
        "researcher-a",
        topic="glucose gene pathway",
    )
    ids = [row["source_id"] for row in result["results"]]
    assert set(ids) == {source["source_id"] for source in sources}
    assert retracted["source_id"] not in ids
    assert result["external_search_performed"] is False
    assert "no live retraction check" in result["retraction_check_boundary"].lower()


def test_agents_generate_evidence_grounded_outputs_and_claim_graph(
    discovery: DiscoveryEcosystem,
):
    current = workspace(discovery)
    sources = evidence_fixture(discovery, current["workspace_id"])
    ids = [row["source_id"] for row in sources]
    for index, agent_key in enumerate(
        ("evidence_synthesis", "hypothesis_generation", "systems_biology"),
        start=1,
    ):
        task = run_reviewed_task(
            discovery,
            current["workspace_id"],
            agent_key,
            {"question": "How might glucose regulation change?", "pathways": ["glucose"]},
            ids,
            suffix=str(index),
        )
        output = json.loads(task["output_json"])
        assert output["human_review_required"] is True
        assert output["clinical_use"] is False
        assert output["provenance"]["external_ai_called"] is False
    graph = discovery.claim_evidence_graph(current["workspace_id"])
    assert graph["claim_count"] == 3
    assert graph["unsupported_claim_count"] == 0
    assert any(edge["relation"] == "direct_evidence" for edge in graph["edges"])


def test_unsafe_actions_are_persistently_refused_and_tenant_access_isolated(
    discovery: DiscoveryEcosystem,
):
    current = workspace(discovery)
    refused = discovery.create_agent_task(
        current["workspace_id"],
        "researcher-a",
        agent_key="drug_target_prioritization",
        task_input={
            "requested_action": "recommend_treatment",
            "question": "Prescribe this target to a patient.",
        },
        idempotency_key="unsafe-treatment",
    )
    assert refused["state"] == "refused"
    with pytest.raises(PermissionDenied, match="treatment"):
        discovery.execute_agent_task(refused["task_id"])

    other = workspace(discovery, tenant="tenant-b")
    source = evidence_fixture(discovery, other["workspace_id"])[0]
    with pytest.raises(PermissionDenied, match="outside"):
        discovery.create_agent_task(
            current["workspace_id"],
            "researcher-a",
            agent_key="evidence_synthesis",
            task_input={"question": "cross tenant"},
            evidence_ids=[source["source_id"]],
            idempotency_key="cross-tenant-evidence",
        )


def test_hypothesis_novelty_and_state_machine_require_second_human(
    discovery: DiscoveryEcosystem,
):
    current = workspace(discovery)
    sources = evidence_fixture(discovery, current["workspace_id"])
    task = run_reviewed_task(
        discovery,
        current["workspace_id"],
        "hypothesis_generation",
        {"question": "Does the synthetic glucose mechanism alter endpoint X?"},
        [row["source_id"] for row in sources],
        suffix="hypothesis",
    )
    novelty = discovery.record_novelty_search(
        current["workspace_id"],
        "researcher-a",
        queries=["synthetic glucose mechanism endpoint X"],
    )
    assert novelty["unresolved_uncertainty"] == NOVELTY_DISCLAIMER
    assert novelty["legal_patent_assessment"] == 0
    hypothesis = discovery.create_hypothesis_from_task(
        task["task_id"],
        "researcher-a",
        novelty_search_id=novelty["novelty_search_id"],
    )
    with pytest.raises(PermissionDenied, match="second human"):
        discovery.transition_hypothesis(
            hypothesis["hypothesis_id"],
            "researcher-a",
            actor_role="scientific_reviewer",
            new_state="Approved for Testing",
        )
    approved = discovery.transition_hypothesis(
        hypothesis["hypothesis_id"],
        "reviewer-a",
        actor_role="scientific_reviewer",
        new_state="Approved for Testing",
    )
    assert approved["state"] == "Approved for Testing"
    with pytest.raises(PermissionDenied, match="proven"):
        discovery.transition_hypothesis(
            approved["hypothesis_id"],
            "reviewer-a",
            actor_role="scientific_reviewer",
            new_state="Scientifically Proven",
        )


def test_experiment_plan_persists_controls_and_never_grants_ethics(
    discovery: DiscoveryEcosystem,
):
    current = workspace(discovery)
    source = evidence_fixture(discovery, current["workspace_id"])[0]
    task = run_reviewed_task(
        discovery,
        current["workspace_id"],
        "hypothesis_generation",
        {"question": "Test a glucose mechanism"},
        [source["source_id"]],
        suffix="experiment-hypothesis",
    )
    hypothesis = discovery.create_hypothesis_from_task(task["task_id"], "researcher-a")
    approved = discovery.transition_hypothesis(
        hypothesis["hypothesis_id"],
        "reviewer-a",
        actor_role="research_lead",
        new_state="Approved for Testing",
    )
    with pytest.raises(PermissionDenied, match="cannot approve ethics"):
        discovery.create_experiment_plan(
            approved["hypothesis_id"],
            "researcher-a",
            objective="Unsafe claim",
            design={"population": "human participants"},
            variables={},
            controls=["control"],
            samples={},
            replicates={},
            randomization={},
            blinding={},
            inclusion_criteria=[],
            exclusion_criteria=[],
            endpoints=[{"name": "endpoint"}],
            analysis_plan={},
            resources={},
            timeline={},
            risks=[{"risk": "human participation"}],
            ethics_status="approved",
        )
    experiment = discovery.create_experiment_plan(
        approved["hypothesis_id"],
        "researcher-a",
        objective="Controlled research plan",
        design={"population": "human-derived synthetic reference only"},
        variables={"dependent": ["endpoint"]},
        controls=["negative control"],
        samples={"synthetic": True},
        replicates={"biological": 3},
        randomization={"suggested": True},
        blinding={"outcome_assessor": True},
        inclusion_criteria=["synthetic fixture"],
        exclusion_criteria=["identifiable data"],
        endpoints=[{"name": "endpoint", "type": "primary"}],
        analysis_plan={"effect_size": True},
        resources={"cpu": 1},
        timeline={"days": 3},
        risks=[{"risk": "interpretation overclaim"}],
    )
    assert experiment["state"] == "human_review"
    assert experiment["ethics_status"] == "pending_specialist_review"
    assert json.loads(experiment["controls_json"]) == ["negative control"]


def test_compute_execution_requires_review_and_explicit_second_human_approval(
    discovery: DiscoveryEcosystem,
    tmp_path: Path,
):
    current = workspace(discovery)
    dataset, run = compute_fixture(discovery, current, tmp_path)
    task = run_reviewed_task(
        discovery,
        current["workspace_id"],
        "bioinformatics_workflow",
        {
            "question": "Inspect the approved local workflow",
            "dataset_ids": [dataset["dataset_id"]],
        },
        [],
        suffix="compute-gate",
    )
    with pytest.raises(PermissionDenied, match="approval"):
        discovery.execute_approved_compute(task["task_id"], run["run_id"], "researcher-a")
    approval = discovery.request_consequential_action(
        task["task_id"],
        "researcher-a",
        operation="compute_execute",
        target_id=run["run_id"],
    )
    discovery.decide_approval(
        task["task_id"],
        "reviewer-a",
        reviewer_role="research_lead",
        operation=approval["operation"],
        decision="approved",
    )
    completed = discovery.execute_approved_compute(
        task["task_id"],
        run["run_id"],
        "reviewer-a",
    )
    assert completed["state"] == "completed"


def test_discovery_workflow_retains_agent_and_human_checkpoints(
    discovery: DiscoveryEcosystem,
):
    current = workspace(discovery)
    sources = evidence_fixture(discovery, current["workspace_id"])
    task = run_reviewed_task(
        discovery,
        current["workspace_id"],
        "literature_discovery",
        {"question": "glucose pathway"},
        [row["source_id"] for row in sources],
        suffix="workflow-literature",
    )
    flow = discovery.create_discovery_workflow(
        current["workspace_id"],
        "researcher-a",
        research_question="What mechanism should be tested?",
    )
    flow = discovery.complete_discovery_step(
        flow["discovery_workflow_id"],
        "researcher-a",
        artifact_reference="question-record",
    )
    assert flow["steps"][1]["state"] == "ready"
    flow = discovery.complete_discovery_step(
        flow["discovery_workflow_id"],
        "researcher-a",
        artifact_reference="saved-search",
        task_id=task["task_id"],
    )
    assert flow["current_step"] == 3
    assert json.loads(flow["steps"][1]["provenance_json"])["task_id"] == task["task_id"]


def test_evaluation_suite_reports_measured_nonfabricated_results(
    discovery: DiscoveryEcosystem,
    tmp_path: Path,
):
    current = workspace(discovery)
    sources = evidence_fixture(discovery, current["workspace_id"])
    ids = [row["source_id"] for row in sources]
    dataset, run = compute_fixture(discovery, current, tmp_path)
    discovery.compute.execute_run(run["run_id"])
    tasks: dict[str, dict] = {}
    task_inputs = {
        "evidence_synthesis": {"question": "glucose mechanism"},
        "hypothesis_generation": {"question": "testable glucose mechanism"},
        "experimental_design": {"objective": "controlled test"},
        "bioinformatics_workflow": {
            "question": "approved workflow",
            "dataset_ids": [dataset["dataset_id"]],
        },
        "statistical_analysis": {"objective": "estimate an effect"},
        "reproducibility": {
            "question": "verify run",
            "compute_run_ids": [run["run_id"]],
        },
        "scientific_reviewer": {"claims": ["This result is proven and guaranteed."]},
        "research_integrity": {"question": "check metadata"},
    }
    for index, (agent_key, task_input) in enumerate(task_inputs.items(), start=1):
        tasks[agent_key] = run_reviewed_task(
            discovery,
            current["workspace_id"],
            agent_key,
            task_input,
            ids,
            suffix=f"evaluation-{index}",
        )
    hypothesis = discovery.create_hypothesis_from_task(
        tasks["hypothesis_generation"]["task_id"],
        "researcher-a",
    )
    hypothesis = discovery.transition_hypothesis(
        hypothesis["hypothesis_id"],
        "reviewer-a",
        actor_role="scientific_reviewer",
        new_state="Approved for Testing",
    )
    discovery.create_experiment_plan(
        hypothesis["hypothesis_id"],
        "researcher-a",
        objective="Evaluate fixture",
        design={"synthetic": True},
        variables={},
        controls=["control"],
        samples={"synthetic": True},
        replicates={"n": 3},
        randomization={},
        blinding={},
        inclusion_criteria=[],
        exclusion_criteria=[],
        endpoints=[{"name": "endpoint"}],
        analysis_plan={},
        resources={},
        timeline={},
        risks=[],
    )
    discovery.create_agent_task(
        current["workspace_id"],
        "researcher-a",
        agent_key="drug_target_prioritization",
        task_input={"requested_action": "diagnose"},
        idempotency_key="evaluation-refusal",
    )
    evaluation = discovery.run_evaluation_suite(
        current["workspace_id"],
        "evaluator-a",
    )
    assert evaluation["fabricated_results"] is False
    assert evaluation["external_services_used"] is False
    assert evaluation["passed_count"] == 15
    assert evaluation["failed_count"] == 0


def test_phase35_fastapi_and_streamlit_surfaces(
    discovery: DiscoveryEcosystem,
    monkeypatch,
    tmp_path: Path,
):
    from biointel.education.phase32_35 import discovery_api

    monkeypatch.setattr(discovery_api, "_DISCOVERY", discovery)
    app = FastAPI()
    app.include_router(discovery_api.router)
    client = TestClient(app)
    capabilities = client.get("/phase35/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["autonomous_discovery"] is False
    assert len(client.get("/phase35/agents").json()) == 12

    current = workspace(discovery)
    evidence = client.post(
        f"/phase35/workspaces/{current['workspace_id']}/evidence",
        json={
            "actor_id": "researcher-a",
            "source_type": "paper",
            "title": "API fixture",
            "citation": "API local source",
            "abstract_text": "glucose evidence",
        },
    )
    assert evidence.status_code == 201

    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path / "streamlit-user-data"))
    page = (
        Path(__file__).resolve().parents[1]
        / "pages"
        / "351_Scientific_Discovery_Agents.py"
    )
    rendered = AppTest.from_file(str(page), default_timeout=60).run(timeout=60)
    assert not rendered.exception
