from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from biointel.compliance import ComplianceLedger
from biointel.enterprise import SaaSControlPlane
from biointel.fair import build_fair_digital_object, evaluate_fair_object
from biointel.maturity import build_maturity_readiness
from biointel.reproducibility import create_reproducibility_bundle, verify_reproducibility_bundle
from biointel.research import evaluate_academic_readiness, evaluate_pharma_readiness

ROOT = Path(__file__).resolve().parents[1]


def test_compliance_ledger_controls_records_signatures_quality_and_audit(tmp_path: Path) -> None:
    ledger = ComplianceLedger(tmp_path / "compliance.sqlite3")
    first = ledger.create_record(
        record_type="validation_plan",
        title="BioIntel validation plan",
        payload={"scope": "research decision support", "requirements": ["REQ-001"]},
        actor="author-1",
    )
    revised = ledger.revise_record(
        first["record_version_id"],
        payload={"scope": "research decision support", "requirements": ["REQ-001", "REQ-002"]},
        actor="author-1",
        reason="Add security requirement",
    )
    signature = ledger.approve_record(
        revised["record_version_id"],
        signer="quality-approver",
        meaning="Approval",
        reason="Validation plan approved",
        signing_secret="qualified-signing-secret-123",
    )
    assert ledger.verify_signature(
        signature["signature_id"], signing_secret="qualified-signing-secret-123"
    )
    assert not ledger.verify_signature(signature["signature_id"], signing_secret="wrong-secret-123456")

    event = ledger.open_quality_event(
        event_type="capa",
        title="Strengthen restore evidence",
        severity="major",
        owner="platform-owner",
        payload={"root_cause": "restore test evidence incomplete"},
        actor="quality-approver",
    )
    ledger.close_quality_event(
        event["quality_event_id"],
        actor="quality-approver",
        reason="Restore test executed and reviewed",
        effectiveness_verified=True,
    )
    ledger.record_training(
        person_id="operator-1",
        curriculum_id="SOP-PLATFORM-001",
        role_name="operator",
        completed_at="2026-07-05T09:00:00+00:00",
        result="passed",
        evidence=b"training certificate",
        actor="training-admin",
    )
    ledger.add_control_evidence(
        control_id="GXP-002",
        evidence_type="verification_report",
        reference="AUDIT-VERIFY-001",
        content=b"audit chain passed",
        owner="quality-approver",
        reviewed_by="independent-reviewer",
        status="approved",
    )
    snapshot = ledger.snapshot()
    assert snapshot["record_versions"] == 2
    assert snapshot["electronic_signatures"] == 1
    assert snapshot["closed_quality_events"] == 1
    assert snapshot["training_records"] == 1
    assert snapshot["covered_controls"] == 1
    assert snapshot["audit"]["valid"] is True


def test_compliance_ledger_detects_audit_tampering(tmp_path: Path) -> None:
    path = tmp_path / "compliance.sqlite3"
    ledger = ComplianceLedger(path)
    ledger.create_record(
        record_type="sop", title="SOP", payload={"step": 1}, actor="author"
    )
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE audit_events SET reason='tampered' WHERE sequence=1")
    verification = ledger.verify_audit_chain()
    assert verification.valid is False
    assert verification.first_error_sequence == 1


def _complete_fair_metadata() -> dict[str, object]:
    return {
        "persistent_identifier": "doi:10.1234/biointel.dataset.001",
        "data_identifier": "doi:10.1234/biointel.dataset.001",
        "title": "Reviewed drug-target dataset",
        "description": "Curated assay measurements with provenance and quality review.",
        "creators": [{"name": "Research Team", "orcid": "0000-0000-0000-0001"}],
        "keywords": ["drug-target", "binding", "assay"],
        "indexed": True,
        "index_name": "Institutional Data Catalog",
        "access_protocol": "https",
        "access_url": "https://data.example.org/datasets/001",
        "access_rights": "restricted",
        "authorization_documented": True,
        "metadata_persistence_policy": True,
        "tombstone_url": "https://data.example.org/datasets/001/tombstone",
        "representation_language": "json-ld",
        "vocabularies": ["https://www.ebi.ac.uk/ols4/ontologies/bao"],
        "qualified_references": [{"type": "isDescribedBy", "id": "doi:10.1234/paper.001"}],
        "publisher": "Example Research Institute",
        "version": "1.0.0",
        "resource_type": "dataset",
        "distributions": [{"name": "data.csv", "sha256": "a" * 64}],
        "license": "CC-BY-4.0",
        "provenance": {
            "source": "BindingDB release",
            "generated_at": "2026-07-05T00:00:00+00:00",
            "agent": "curation-team",
            "activity": "curation and review",
        },
        "community_standards": ["BioAssay Ontology", "JSON-LD"],
        "schema_version": "1.0",
    }


def test_fair_evaluator_reaches_ten_only_with_complete_machine_actionable_metadata() -> None:
    complete = evaluate_fair_object(_complete_fair_metadata())
    assert complete.score == 10.0
    assert complete.passed == complete.total == 15
    incomplete_payload = _complete_fair_metadata()
    incomplete_payload["license"] = "unknown"
    incomplete = evaluate_fair_object(incomplete_payload)
    assert incomplete.score < 10.0
    assert any(item.principle == "R1.1" and not item.passed for item in incomplete.checks)


def test_fair_digital_object_has_jsonld_checksums_and_provenance(tmp_path: Path) -> None:
    data = tmp_path / "data.csv"
    data.write_text("drug,target,value\nD1,T1,7.0\n", encoding="utf-8")
    payload = build_fair_digital_object(
        persistent_identifier="doi:10.1234/biointel.001",
        title="Dataset",
        description="Reviewed data",
        creators=[{"name": "Scientist"}],
        files=[data],
        license_id="CC-BY-4.0",
        version="1.0.0",
        keywords=["drug-target", "binding", "reviewed"],
        vocabularies=["https://www.ebi.ac.uk/ols4/ontologies/bao"],
        qualified_references=[{"type": "isDescribedBy", "id": "doi:10.1234/article"}],
        access_url="https://data.example.org/001",
    )
    assert payload["@type"] == "schema:Dataset"
    assert len(payload["distributions"][0]["sha256"]) == 64
    assert payload["provenance"]["activity"]


def test_reproducibility_bundle_records_and_verifies_inputs_code_and_environment(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    source = root / "analysis.py"
    source.write_text("print('analysis')\n", encoding="utf-8")
    data = root / "input.csv"
    data.write_text("x,y\n1,2\n", encoding="utf-8")
    artifact = root / "result.json"
    artifact.write_text(json.dumps({"metric": 0.91}), encoding="utf-8")
    bundle = create_reproducibility_bundle(
        tmp_path / "bundle.zip",
        project_root=root,
        inputs=[data],
        code_files=[source],
        artifacts=[artifact],
        parameters={"split": "cold_target", "threshold": 0.5},
        random_seed=42,
        command="python analysis.py",
        package_names=["numpy"],
    )
    verification = verify_reproducibility_bundle(bundle)
    assert verification.valid is True
    assert verification.checked_files == 3
    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["random_seed"] == 42
    assert manifest["parameters"]["split"] == "cold_target"
    assert manifest["environment"]["python"]


def test_saas_control_plane_enforces_tenant_specific_entitlements_quotas_and_idempotency(tmp_path: Path) -> None:
    control = SaaSControlPlane(tmp_path / "saas.sqlite3")
    control.upsert_plan(
        plan_id="starter",
        display_name="Starter",
        entitlements={"private_models": False, "core_research": True},
        quotas={"api_calls": 5},
    )
    control.upsert_plan(
        plan_id="enterprise",
        display_name="Enterprise",
        entitlements={"private_models": True, "core_research": True},
        quotas={"api_calls": None},
    )
    control.subscribe(tenant_id="alpha", plan_id="starter")
    control.subscribe(tenant_id="beta", plan_id="enterprise")
    assert control.has_entitlement("alpha", "private_models") is False
    assert control.has_entitlement("beta", "private_models") is True
    first = control.record_usage(
        tenant_id="alpha", metric="api_calls", quantity=3,
        idempotency_key="request-1",
    )
    duplicate = control.record_usage(
        tenant_id="alpha", metric="api_calls", quantity=3,
        idempotency_key="request-1",
    )
    assert duplicate["usage_event_id"] == first["usage_event_id"]
    assert control.usage("alpha", "api_calls") == 3
    assert control.quota_decision("alpha", "api_calls", 2).allowed is True
    with pytest.raises(PermissionError):
        control.enforce_quota("alpha", "api_calls", 3)
    assert control.enforce_quota("beta", "api_calls", 1_000_000).allowed is True
    request = control.request_data_right(
        tenant_id="alpha", request_type="export", requested_by="owner", reason="Tenant export"
    )
    completed = control.complete_data_right(
        request["request_id"], export_location="s3://exports/alpha.zip"
    )
    assert completed["status"] == "completed"


def test_academic_readiness_complete_package_scores_ten() -> None:
    report = evaluate_academic_readiness({
        "research_question": "Does the model generalize to unseen target families?",
        "hypothesis": "Cold-target performance remains above the predefined baseline.",
        "protocol_id": "osf:protocol-001",
        "preregistered": True,
        "ethics_review": "not-human-subjects determination",
        "consent_or_exemption": "exempt",
        "contributors": [{"name": "A Scientist", "role": "Conceptualization"}],
        "methods": "Frozen pipeline and predefined endpoints",
        "parameters": {"seed": 42},
        "data_identifier": "doi:10.1234/data",
        "data_license": "CC-BY-4.0",
        "data_availability_statement": "Controlled access repository",
        "software_identifier": "swh:1:dir:abc",
        "environment_lock": "requirements.lock",
        "reproducibility_bundle_verified": True,
        "statistical_plan": "Bootstrap CI and permutation testing",
        "multiple_testing_policy": "Benjamini-Hochberg",
        "limitations": "Assay-domain shift remains possible",
        "reporting_checklist": "TRIPOD-AI style checklist",
        "negative_results_policy": "Report all predefined endpoints",
    })
    assert report.score == 10.0


def test_pharma_readiness_complete_package_scores_ten() -> None:
    report = evaluate_pharma_readiness({
        "intended_use": "Research prioritization only",
        "decision_context": "Preclinical target triage",
        "protocol_id": "PROT-001",
        "protocol_status": "approved",
        "randomization": True,
        "blinding": True,
        "controls": ["positive", "negative"],
        "assay_ontology_id": "BAO:0000015",
        "acceptance_criteria": {"z_prime": ">=0.5"},
        "replicate_plan": {"technical": 3, "biological": 3},
        "sample_chain_of_custody": True,
        "compound_identity_controls": True,
        "audit_chain_verified": True,
        "electronic_signatures_verified": True,
        "controlled_records": True,
        "independent_validation": True,
        "prospective_validation": True,
        "leakage_audit": True,
        "deviation_process": True,
        "capa_process": True,
        "change_control": True,
        "independent_qa_review": True,
        "scientific_review": True,
        "signed_evidence_manifest": True,
        "release_gate_passed": True,
        "limitations_disclosed": True,
    })
    assert report.score == 10.0


def test_all_requested_maturity_implementation_frameworks_score_ten() -> None:
    report = build_maturity_readiness(ROOT)
    assert report["all_implementation_targets_complete"] is True, report
    assert report["implementation_average"] == 10.0
    assert len(report["areas"]) >= 16
    assert all(item["implementation_score"] == 10.0 for item in report["areas"])
    scientific = next(item for item in report["areas"] if item["key"] == "scientific_credibility_framework")
    assert scientific["evidence_score"] < scientific["implementation_score"]


def test_maturity_compliance_and_research_api_endpoints() -> None:
    from fastapi.testclient import TestClient

    from biointel.api.main import app

    client = TestClient(app)
    maturity = client.get("/quality/maturity-readiness")
    assert maturity.status_code == 200
    assert maturity.json()["all_implementation_targets_complete"] is True

    controls = client.get("/compliance/controls")
    assert controls.status_code == 200
    assert controls.json()["count"] >= 16

    fair = client.post("/quality/fair-evaluate", json=_complete_fair_metadata())
    assert fair.status_code == 200
    assert fair.json()["score"] == 10.0
