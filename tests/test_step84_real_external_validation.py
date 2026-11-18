from __future__ import annotations

from pathlib import Path

import pytest

from biointel.clinical import (
    ClinicalValidationRegistry,
    build_real_external_validation_framework_readiness,
    build_validation_dossier,
    evaluate_real_external_validation,
    verify_validation_dossier,
)


def _file(root: Path, name: str, content: bytes = b"controlled artifact") -> Path:
    path = root / name
    path.write_bytes(content)
    return path


def _program(registry: ClinicalValidationRegistry) -> dict:
    return registry.create_program(
        title="Independent real-world external validation",
        claim_profile="clinical_decision_support",
        intended_use="Expert-reviewed clinical decision support within the authorized scope.",
        decision_context="Non-autonomous clinical decision support.",
        target_population="Prospectively predefined eligible cases.",
        jurisdictions=["India", "United States", "European Union"],
        risk_classification="regulated clinical software candidate",
        prohibited_uses=["Autonomous diagnosis", "Autonomous treatment", "Unapproved use"],
        owner="sponsor",
        quality_owner="independent-qa",
        actor="sponsor",
    )


def _approve_artifact(
    registry: ClinicalValidationRegistry,
    *,
    program_id: str,
    domain: str,
    title: str,
    organization: str,
    source_type: str,
    external_identifier: str,
    metadata: dict,
    index: int,
    test_fixture: bool = False,
) -> dict:
    row = registry.register_external_validation_artifact(
        program_id=program_id,
        domain=domain,
        title=title,
        source_organization=organization,
        source_type=source_type,
        external_identifier=external_identifier,
        content=f"authentic controlled artifact {domain} {index}".encode(),
        original_filename=f"{domain}-{index}.pdf",
        mime_type="application/pdf",
        issued_at="2026-01-15T00:00:00+00:00",
        submitted_by=f"custodian-{index}",
        independent=True,
        jurisdiction="India",
        source_url=f"https://official.example/{external_identifier}",
        metadata=metadata,
        test_fixture=test_fixture,
    )
    registry.review_external_validation_artifact(
        row["artifact_id"],
        reviewer=f"independent-reviewer-{index}",
        status="approved",
        verification_method="direct_issuer_confirmation",
        notes="Issuer identity, identifier, content and checksum independently verified.",
    )
    return row


def _complete_clinical_execution(
    registry: ClinicalValidationRegistry, root: Path, program_id: str
) -> None:
    sites = []
    for index in (1, 2):
        site = registry.register_site(
            program_id=program_id,
            site_name=f"Independent Site {index}",
            organization=f"External Lab {index}",
            country="India",
            independent=True,
            principal_investigator=f"PI-{index}",
            qa_contact=f"QA-{index}",
            laboratory_accreditation=f"ACCREDITED-SCOPE-{index}",
            actor="site-manager",
        )
        registry.qualify_site(site["site_id"], actor="independent-qa", reason="Qualified")
        sites.append(site)

    protocol = registry.create_protocol(
        program_id=program_id,
        protocol_id="REAL-EXT-001",
        title="Prospective multisite external validation",
        primary_endpoint="AUROC",
        success_criterion="Lower 95% CI >= 0.70",
        sample_size=4,
        statistical_plan="Locked analysis with confidence intervals and per-site results.",
        preregistration_reference="TRIAL-REGISTRY:REAL-EXT-001",
        ethics_reference="IEC:APPROVED-001",
        data_management_plan="DMP-REAL-EXT-001",
        payload={"negative_results": True},
        actor="protocol-author",
    )
    registry.approve_protocol(
        protocol["protocol_version_id"], approver="independent-qa", reason="Approved"
    )
    artifacts = {
        name: _file(root, name, name.encode())
        for name in ("model.bin", "dataset.csv", "analysis.py", "environment.lock", "features.json")
    }
    freeze = registry.freeze_model(
        program_id=program_id,
        protocol_version_id=protocol["protocol_version_id"],
        model_id="MODEL-REAL-001",
        model_path=artifacts["model.bin"],
        dataset_path=artifacts["dataset.csv"],
        code_path=artifacts["analysis.py"],
        environment_path=artifacts["environment.lock"],
        feature_spec_path=artifacts["features.json"],
        intended_use="Expert-reviewed clinical decision support within the authorized scope.",
        actor="configuration-manager",
    )
    for index, site in enumerate(sites, start=1):
        prediction = registry.lock_prediction_batch(
            program_id=program_id,
            freeze_id=freeze["freeze_id"],
            site_id=site["site_id"],
            batch_label=f"LOCKED-{index}",
            predictions_path=_file(root, f"predictions-{index}.csv", b"id,p\na,0.9\nb,0.8\n"),
            sample_count=2,
            blinded=True,
            sample_code_scheme=f"BLIND-{index}",
            actor="independent-statistician",
        )
        registry.register_outcome_batch(
            program_id=program_id,
            prediction_batch_id=prediction["batch_id"],
            outcomes_path=_file(root, f"outcomes-{index}.csv", b"id,y\na,1\nb,1\n"),
            sample_count=2,
            endpoint_name="Adjudicated endpoint",
            adjudicated=True,
            actor="outcome-adjudicator",
        )
        site_result = registry.record_analysis_result(
            program_id=program_id,
            protocol_version_id=protocol["protocol_version_id"],
            result_scope="site",
            site_id=site["site_id"],
            metric_name="AUROC",
            metric_value=0.84,
            lower_ci=0.72,
            upper_ci=0.94,
            success_criterion="Lower 95% CI >= 0.70",
            passed=True,
            analysis_content=f"site result {index}".encode(),
            analyst="independent-statistician",
        )
        registry.review_analysis_result(
            site_result["analysis_result_id"],
            reviewer="independent-qa",
            status="approved",
            reason="Verified",
        )
    primary = registry.record_analysis_result(
        program_id=program_id,
        protocol_version_id=protocol["protocol_version_id"],
        result_scope="primary",
        metric_name="AUROC",
        metric_value=0.86,
        lower_ci=0.75,
        upper_ci=0.95,
        success_criterion="Lower 95% CI >= 0.70",
        passed=True,
        analysis_content=b"primary locked result",
        analyst="independent-statistician",
    )
    registry.review_analysis_result(
        primary["analysis_result_id"],
        reviewer="independent-qa",
        status="approved",
        reason="Verified",
    )
    for index in (1, 2):
        registry.record_training(
            program_id=program_id,
            person_id=f"PERSON-{index}",
            role_name="qualified-user",
            curriculum_id="SOP-REAL-EXT",
            completed_at="2026-01-01T00:00:00+00:00",
            result="passed",
            evidence=f"training-{index}".encode(),
            actor="training-admin",
        )


def test_blank_program_scores_zero(tmp_path: Path) -> None:
    registry = ClinicalValidationRegistry(tmp_path / "registry.sqlite3")
    program = _program(registry)
    report = evaluate_real_external_validation(registry, program["program_id"])
    assert report.actual_external_validation_score == 0.0
    assert report.domains_at_10 == 0
    assert report.release_eligible is False


def test_test_fixture_never_increases_authentic_score(tmp_path: Path) -> None:
    registry = ClinicalValidationRegistry(tmp_path / "registry.sqlite3")
    program = _program(registry)
    _approve_artifact(
        registry,
        program_id=program["program_id"],
        domain="peer_reviewed_publication",
        title="Fixture publication",
        organization="Fixture Publisher",
        source_type="journal_article",
        external_identifier="doi:10.0000/fixture",
        metadata={
            "peer_reviewed": True,
            "publication_status": "published",
            "limitations_reported": True,
        },
        index=1,
        test_fixture=True,
    )
    report = evaluate_real_external_validation(registry, program["program_id"])
    assert report.actual_external_validation_score == 0.0
    assert report.authentic_artifact_count == 0
    assert report.excluded_artifact_count == 1


def test_submitter_cannot_approve_own_artifact(tmp_path: Path) -> None:
    registry = ClinicalValidationRegistry(tmp_path / "registry.sqlite3")
    program = _program(registry)
    row = registry.register_external_validation_artifact(
        program_id=program["program_id"],
        domain="regulatory_authorization",
        title="Authorization",
        source_organization="Authority",
        source_type="regulatory_authorization",
        external_identifier="AUTH-1",
        content=b"authorization",
        original_filename="authorization.pdf",
        mime_type="application/pdf",
        issued_at="2026-01-01T00:00:00+00:00",
        submitted_by="same-person",
        independent=True,
        metadata={},
    )
    with pytest.raises(ValueError, match="different from submitter"):
        registry.review_external_validation_artifact(
            row["artifact_id"],
            reviewer="same-person",
            status="approved",
            verification_method="authority_portal",
            notes="Self review is prohibited.",
        )


def test_tampered_artifact_is_excluded(tmp_path: Path) -> None:
    registry = ClinicalValidationRegistry(tmp_path / "registry.sqlite3")
    program = _program(registry)
    row = _approve_artifact(
        registry,
        program_id=program["program_id"],
        domain="peer_reviewed_publication",
        title="Published study",
        organization="Independent Journal",
        source_type="journal_article",
        external_identifier="doi:10.1000/real",
        metadata={
            "peer_reviewed": True,
            "publication_status": "published",
            "limitations_reported": True,
        },
        index=1,
    )
    snapshot = registry.snapshot(program["program_id"])
    artifact = next(
        item for item in snapshot["external_artifacts"] if item["artifact_id"] == row["artifact_id"]
    )
    (registry.path.parent / artifact["artifact_path"]).write_bytes(b"tampered")
    report = evaluate_real_external_validation(registry, program["program_id"])
    assert report.authentic_artifact_count == 0
    assert report.excluded_artifact_count == 1


def test_complete_authentic_fixture_scores_ten(tmp_path: Path) -> None:
    registry = ClinicalValidationRegistry(tmp_path / "registry.sqlite3")
    program = _program(registry)
    program_id = program["program_id"]
    _complete_clinical_execution(registry, tmp_path, program_id)

    for index, organization in enumerate(("Clinical Network A", "Clinical Network B"), start=1):
        _approve_artifact(
            registry,
            program_id=program_id,
            domain="independent_clinical_evidence",
            title=f"Independent clinical report {index}",
            organization=organization,
            source_type="clinical_study_report",
            external_identifier=f"CSR-{index}",
            metadata={"study_type": "clinical", "final_report": True},
            index=index,
        )
    _approve_artifact(
        registry,
        program_id=program_id,
        domain="prospective_clinical_study",
        title="Final prospective multisite study report",
        organization="Independent CRO",
        source_type="clinical_study_report",
        external_identifier="TRIAL-REGISTRY:REAL-EXT-001",
        metadata={"prospective": True, "primary_endpoint_met": True},
        index=3,
    )
    for index, organization in enumerate(("Pharma Lab A", "Pharma Lab B"), start=4):
        _approve_artifact(
            registry,
            program_id=program_id,
            domain="pharma_laboratory_validation",
            title=f"Laboratory validation report {index}",
            organization=organization,
            source_type="laboratory_validation_report",
            external_identifier=f"LAB-{index}",
            metadata={
                "assay_validated": True,
                "replication_complete": True,
                "raw_data_available": True,
            },
            index=index,
        )
    _approve_artifact(
        registry,
        program_id=program_id,
        domain="peer_reviewed_publication",
        title="Peer-reviewed external validation publication",
        organization="Independent Journal",
        source_type="journal_article",
        external_identifier="doi:10.1000/external-validation",
        metadata={
            "peer_reviewed": True,
            "publication_status": "published",
            "limitations_reported": True,
        },
        index=6,
    )
    _approve_artifact(
        registry,
        program_id=program_id,
        domain="gxp_operating_history",
        title="Twelve-month GCP operating history",
        organization="Independent Quality Auditor",
        source_type="gxp_quality_record",
        external_identifier="GXP-HISTORY-001",
        metadata={"duration_months": 12, "quality_system": "GCP", "audit_complete": True},
        index=7,
    )
    _approve_artifact(
        registry,
        program_id=program_id,
        domain="regulatory_inspection",
        title="Closed regulatory inspection",
        organization="Regulatory Authority",
        source_type="regulatory_inspection_report",
        external_identifier="INSPECTION-001",
        metadata={
            "authority": "Regulatory Authority",
            "outcome": "acceptable",
            "critical_findings_open": 0,
        },
        index=8,
    )
    _approve_artifact(
        registry,
        program_id=program_id,
        domain="regulatory_authorization",
        title="Active regulatory authorization",
        organization="Regulatory Authority",
        source_type="regulatory_authorization",
        external_identifier="AUTHORIZATION-001",
        metadata={
            "authority": "Regulatory Authority",
            "authorization_number": "AUTHORIZATION-001",
            "authorization_status": "active",
            "intended_use_match": True,
        },
        index=9,
    )
    _approve_artifact(
        registry,
        program_id=program_id,
        domain="approved_patient_care_use",
        title="Institutionally approved patient-care deployment",
        organization="Independent Hospital",
        source_type="institutional_deployment_record",
        external_identifier="HOSPITAL-APPROVAL-001",
        metadata={
            "institutional_approval": True,
            "deployed_site_count": 1,
            "use_count": 100,
            "authorized_user_count": 5,
            "human_oversight": True,
        },
        index=10,
    )
    _approve_artifact(
        registry,
        program_id=program_id,
        domain="post_market_clinical_evidence",
        title="Post-market clinical performance report",
        organization="Independent Safety Board",
        source_type="post_market_report",
        external_identifier="PMS-001",
        metadata={
            "monitoring_months": 12,
            "cases_or_uses": 100,
            "drift_monitoring": True,
            "safety_reporting": True,
            "periodic_review_approved": True,
            "unresolved_critical_events": 0,
        },
        index=11,
    )
    registry.set_program_status(
        program_id, "completed", actor="independent-qa", reason="All external evidence approved"
    )
    report = evaluate_real_external_validation(registry, program_id)
    assert report.actual_external_validation_score == 10.0
    assert report.domains_at_10 == report.total_domains == 9
    assert report.release_eligible is True
    assert report.authentic_artifact_count == 11


def test_dossier_includes_checksum_bound_external_artifact(tmp_path: Path) -> None:
    import zipfile

    registry = ClinicalValidationRegistry(tmp_path / "registry.sqlite3")
    program = _program(registry)
    row = _approve_artifact(
        registry,
        program_id=program["program_id"],
        domain="peer_reviewed_publication",
        title="Controlled publication",
        organization="Independent Journal",
        source_type="journal_article",
        external_identifier="doi:10.1000/dossier",
        metadata={
            "peer_reviewed": True,
            "publication_status": "published",
            "limitations_reported": True,
        },
        index=99,
        test_fixture=True,
    )
    dossier = build_validation_dossier(
        registry, program["program_id"], tmp_path / "validation_dossier.zip"
    )
    verification = verify_validation_dossier(dossier)
    assert verification["valid"] is True
    with zipfile.ZipFile(dossier) as archive:
        names = set(archive.namelist())
    assert "external_artifact_integrity.json" in names
    assert any(name.startswith(f"external_artifacts/{row['artifact_id']}") for name in names)


def test_step84_framework_is_complete() -> None:
    root = Path(__file__).resolve().parents[1]
    report = build_real_external_validation_framework_readiness(root)
    assert report["complete"] is True
    assert report["score"] == 10.0
