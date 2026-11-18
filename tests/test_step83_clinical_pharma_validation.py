from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from biointel.clinical import (
    ClinicalValidationRegistry,
    build_clinical_pharma_framework_readiness,
    build_validation_dossier,
    build_validation_template_pack,
    evaluate_clinical_pharma_readiness,
    verify_validation_dossier,
)

ROOT = Path(__file__).resolve().parents[1]


def _artifact(path: Path, name: str, payload: bytes | None = None) -> Path:
    target = path / name
    target.write_bytes(payload or f"controlled-{name}".encode())
    return target


def _program(registry: ClinicalValidationRegistry, claim_profile: str = "pharma_r_and_d") -> dict:
    return registry.create_program(
        title="Independent prospective BioIntel validation",
        claim_profile=claim_profile,
        intended_use="Rank molecular candidates for expert pharmaceutical R&D review.",
        decision_context="Non-autonomous, expert-reviewed candidate prioritisation.",
        target_population="Predefined assay-compatible molecular candidates.",
        jurisdictions=["India", "European Union", "United States"],
        risk_classification="High scientific decision risk; no patient-care authorization",
        prohibited_uses=[
            "Autonomous diagnosis or treatment",
            "Patient-specific clinical decisions",
            "Use outside the frozen model and protocol",
        ],
        owner="sponsor-science",
        quality_owner="independent-qa",
        actor="validation-author",
    )


def test_incomplete_program_remains_research_only(tmp_path: Path) -> None:
    registry = ClinicalValidationRegistry(tmp_path / "registry.sqlite3")
    program = _program(registry)
    report = evaluate_clinical_pharma_readiness(registry, program["program_id"])
    assert report.release_eligible is False
    assert report.total_score < 10.0
    assert "Research/demo use only" in report.permitted_claim
    assert "Approved controlled protocol" in report.blockers


def test_model_freeze_requires_approved_protocol(tmp_path: Path) -> None:
    registry = ClinicalValidationRegistry(tmp_path / "registry.sqlite3")
    program = _program(registry)
    protocol = registry.create_protocol(
        program_id=program["program_id"],
        protocol_id="CPV-001",
        title="Prospective validation",
        primary_endpoint="AUROC",
        success_criterion="Lower 95% CI >= 0.70",
        sample_size=100,
        statistical_plan="Bootstrap 95% CI with locked analysis code",
        preregistration_reference="OSF:CPV-001",
        ethics_reference="IEC:EXEMPT-001",
        data_management_plan="DMP-001",
        payload={"negative_results": "reported"},
        actor="protocol-author",
    )
    artifact = _artifact(tmp_path, "model.bin")
    with pytest.raises(ValueError, match="approved protocol"):
        registry.freeze_model(
            program_id=program["program_id"],
            protocol_version_id=protocol["protocol_version_id"],
            model_id="MODEL-001",
            model_path=artifact,
            dataset_path=artifact,
            code_path=artifact,
            environment_path=artifact,
            feature_spec_path=artifact,
            intended_use=program["intended_use"],
            actor="ml-owner",
        )


def complete_pharma_execution_package(tmp_path: Path) -> tuple[ClinicalValidationRegistry, str]:
    registry = ClinicalValidationRegistry(tmp_path / "registry.sqlite3")
    program = _program(registry)
    program_id = program["program_id"]

    sites: list[dict] = []
    for index in (1, 2):
        site = registry.register_site(
            program_id=program_id,
            site_name=f"Independent Site {index}",
            organization=f"External Laboratory {index}",
            country="India" if index == 1 else "Germany",
            independent=True,
            principal_investigator=f"PI-{index}",
            qa_contact=f"QA-{index}",
            laboratory_accreditation=f"ISO-17025-SCOPE-{index}",
            actor="site-manager",
        )
        registry.qualify_site(
            site["site_id"], actor="independent-qa", reason="Qualification approved"
        )
        sites.append(site)

    protocol = registry.create_protocol(
        program_id=program_id,
        protocol_id="CPV-PHARMA-001",
        title="Locked multisite prospective pharmaceutical R&D validation",
        primary_endpoint="AUROC on independently adjudicated outcomes",
        success_criterion="AUROC lower 95% confidence limit >= 0.70",
        sample_size=100,
        statistical_plan=(
            "Locked bootstrap confidence intervals; site heterogeneity; calibration; "
            "predefined missing-data and negative-result reporting"
        ),
        preregistration_reference="OSF:CPV-PHARMA-001",
        ethics_reference="IEC:NON-CLINICAL-ASSAY-DETERMINATION-001",
        data_management_plan="DMP-CPV-001",
        payload={"site_analysis": True, "subgroups": ["assay-platform"], "alpha": 0.05},
        actor="protocol-author",
    )
    registry.approve_protocol(
        protocol["protocol_version_id"],
        approver="independent-qa",
        reason="Protocol and statistical plan approved before outcomes",
    )

    frozen = {
        name: _artifact(tmp_path, name)
        for name in ("model.bin", "dataset.csv", "analysis.py", "environment.lock", "features.json")
    }
    freeze = registry.freeze_model(
        program_id=program_id,
        protocol_version_id=protocol["protocol_version_id"],
        model_id="BIOINTEL-PHARMA-001",
        model_path=frozen["model.bin"],
        dataset_path=frozen["dataset.csv"],
        code_path=frozen["analysis.py"],
        environment_path=frozen["environment.lock"],
        feature_spec_path=frozen["features.json"],
        intended_use=program["intended_use"],
        actor="configuration-manager",
    )

    for index, site in enumerate(sites, start=1):
        predictions = _artifact(
            tmp_path, f"predictions-{index}.csv", b"sample,prediction\n" + b"x,0.8\n" * 50
        )
        prediction = registry.lock_prediction_batch(
            program_id=program_id,
            freeze_id=freeze["freeze_id"],
            site_id=site["site_id"],
            batch_label=f"SITE-{index}-BLINDED",
            predictions_path=predictions,
            sample_count=50,
            blinded=True,
            sample_code_scheme=f"BLIND-{index}",
            actor="independent-statistician",
        )
        outcomes = _artifact(tmp_path, f"outcomes-{index}.csv", b"sample,outcome\n" + b"x,1\n" * 50)
        registry.register_outcome_batch(
            program_id=program_id,
            prediction_batch_id=prediction["batch_id"],
            outcomes_path=outcomes,
            sample_count=50,
            endpoint_name="Independently adjudicated activity",
            adjudicated=True,
            actor="outcome-adjudicator",
        )

    primary = registry.record_analysis_result(
        program_id=program_id,
        protocol_version_id=protocol["protocol_version_id"],
        result_scope="primary",
        metric_name="AUROC",
        metric_value=0.84,
        lower_ci=0.76,
        upper_ci=0.91,
        success_criterion="Lower 95% CI >= 0.70",
        passed=True,
        analysis_content=b"locked primary analysis output",
        analyst="independent-statistician",
    )
    registry.review_analysis_result(
        primary["analysis_result_id"],
        reviewer="independent-qa",
        status="approved",
        reason="Verified",
    )
    for index, site in enumerate(sites, start=1):
        result = registry.record_analysis_result(
            program_id=program_id,
            protocol_version_id=protocol["protocol_version_id"],
            result_scope="site",
            site_id=site["site_id"],
            metric_name="AUROC",
            metric_value=0.82 + 0.01 * index,
            lower_ci=0.71,
            upper_ci=0.93,
            success_criterion="Lower 95% CI >= 0.70",
            passed=True,
            analysis_content=f"site-{index}-locked-analysis".encode(),
            analyst="independent-statistician",
        )
        registry.review_analysis_result(
            result["analysis_result_id"],
            reviewer="independent-qa",
            status="approved",
            reason="Verified",
        )

    for category in (
        "assay_validation",
        "independent_external_validation",
        "prospective_validation",
        "quality_assurance",
        "data_integrity",
        "model_validation",
        "supplier_qualification",
    ):
        evidence = registry.add_evidence(
            program_id=program_id,
            category=category,
            evidence_type="independently reviewed controlled report",
            reference=f"EVIDENCE:{category}",
            source_organization=f"Independent source for {category}",
            independent=True,
            content=f"authentic-placeholder-fixture-{category}".encode(),
            owner="evidence-custodian",
            actor="evidence-custodian",
            metadata={"test_fixture": True, "not_bundled_as_real_evidence": True},
        )
        registry.review_evidence(
            evidence["evidence_id"],
            reviewer="independent-qa",
            status="approved",
            reason="Fixture review",
        )

    event = registry.open_quality_event(
        program_id=program_id,
        event_type="capa",
        severity="major",
        title="Reconcile transfer checksum",
        description="Controlled test CAPA for end-to-end gate verification.",
        owner="quality-owner",
        actor="quality-owner",
    )
    registry.close_quality_event(
        event["quality_event_id"],
        root_cause="Initial transfer manifest omitted a checksum field.",
        action_plan="Regenerate manifest and add automated verification.",
        effectiveness_verified=True,
        actor="independent-qa",
        reason="Effectiveness challenge passed",
    )
    for index, role in enumerate(("site-operator", "quality-reviewer"), start=1):
        registry.record_training(
            program_id=program_id,
            person_id=f"PERSON-{index}",
            role_name=role,
            curriculum_id="CPV-SOP-001",
            completed_at="2026-07-08T10:00:00+00:00",
            result="passed",
            evidence=f"training-{index}".encode(),
            actor="training-admin",
        )

    summary_hash = hashlib.sha256(b"approved validation summary").hexdigest()
    signature = registry.sign_object(
        program_id=program_id,
        object_type="validation_summary_report",
        object_id="VSR-CPV-PHARMA-001",
        object_sha256=summary_hash,
        signer="independent-quality-approver",
        meaning="Approval",
        reason="All predefined release criteria passed in this controlled fixture",
        signing_secret="qualified-test-signing-secret-83",
    )
    assert registry.verify_signature(
        signature["signature_id"], signing_secret="qualified-test-signing-secret-83"
    )
    registry.set_program_status(
        program_id,
        "completed",
        actor="independent-quality-approver",
        reason="Controlled fixture complete",
    )
    return registry, program_id


def test_complete_pharma_execution_package_passes_all_claim_gates(tmp_path: Path) -> None:
    registry, program_id = complete_pharma_execution_package(tmp_path)
    report = evaluate_clinical_pharma_readiness(registry, program_id)
    assert report.release_eligible is True
    assert report.control_readiness_score == 10.0
    assert report.external_evidence_score == 10.0
    assert report.total_score == 10.0
    assert not report.blockers
    assert registry.verify_audit_chain().valid is True
    snapshot = registry.snapshot(program_id)
    assert sum(int(item["sample_count"]) for item in snapshot["prediction_batches"]) == 100
    assert all(item["blinded"] for item in snapshot["prediction_batches"])


def test_dossier_and_blank_template_pack_are_checksum_verified(tmp_path: Path) -> None:
    registry, program_id = complete_pharma_execution_package(tmp_path)
    dossier = build_validation_dossier(registry, program_id, tmp_path / "dossier.zip")
    verification = verify_validation_dossier(dossier)
    assert verification["valid"] is True
    assert verification["checked_files"] >= 10
    templates = build_validation_template_pack(tmp_path / "templates")
    files = sorted(path for path in templates.iterdir() if path.is_file())
    assert len(files) == 26
    assert (
        "contains_real_validation_evidence"
        in (templates / "template_pack_metadata.json").read_text()
    )


def test_framework_readiness_is_complete_and_truthfully_bounded() -> None:
    report = build_clinical_pharma_framework_readiness(ROOT)
    assert report["complete"] is True
    assert report["score"] == 10.0
    assert report["passed"] == report["total"] == 10
    assert "does not certify" in report["boundary"].lower()
