from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

from biointel.clinical import (
    ClinicalValidationRegistry,
    build_generic_independent_validation_starter_pack,
    build_independent_validation_accelerator_readiness,
    build_independent_validation_partner_pack,
    build_validation_action_plan,
    evaluate_real_external_validation,
    projected_score_from_control_completion,
)


def _blank_report(tmp_path: Path):
    registry = ClinicalValidationRegistry(tmp_path / "clinical.sqlite3")
    program = registry.create_program(
        title="Independent validation qualification",
        intended_use="Research-only model evaluation",
        claim_profile="research_only",
        decision_context="Scientific research support",
        target_population="Retrospective research datasets",
        jurisdictions=["Research only"],
        risk_classification="Non-clinical research",
        prohibited_uses=["Diagnosis", "Treatment", "Autonomous patient-care decisions"],
        owner="Qualification owner",
        quality_owner="Independent quality owner",
        actor="qualification-runner",
    )
    report = evaluate_real_external_validation(registry, program["program_id"])
    return registry, program, report


def test_accelerator_framework_scores_ten() -> None:
    root = Path(__file__).resolve().parents[1]
    readiness = build_independent_validation_accelerator_readiness(root)
    assert readiness.score == 10.0
    assert readiness.passed_controls == readiness.total_controls


def test_action_plan_covers_all_domains(tmp_path: Path) -> None:
    _, _, report = _blank_report(tmp_path)
    actions = build_validation_action_plan(report)
    assert {item.domain for item in actions} == {item.domain for item in report.ratings}
    assert all(item.software_can_complete is False for item in actions)
    assert all(item.required_owner and item.required_artifact for item in actions)


def test_projection_never_changes_actual_score(tmp_path: Path) -> None:
    registry, program, report = _blank_report(tmp_path)
    completion = {item.domain: item.total_controls for item in report.ratings}
    projection = projected_score_from_control_completion(report, completion)
    assert projection["projected_score"] == 10.0
    assert projection["actual_score"] == report.actual_external_validation_score
    assert projection["projection_only"] is True
    fresh = evaluate_real_external_validation(registry, program["program_id"])
    assert fresh.actual_external_validation_score == report.actual_external_validation_score
    assert fresh.release_eligible is False


def test_partner_pack_is_uncompressed_and_checksum_manifested(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    _, program, report = _blank_report(tmp_path)
    payload = build_independent_validation_partner_pack(
        root,
        report,
        program_title=program["title"],
    )
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "MANIFEST.json" in names
        assert "00_CURRENT_AUTHENTIC_SCORECARD.json" in names
        assert "01_DOMAIN_ACTION_PLAN.csv" in names
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())
        manifest = json.loads(archive.read("MANIFEST.json"))
        assert manifest["contains_preapproved_evidence"] is False
        assert manifest["actual_external_validation_score"] == report.actual_external_validation_score
        assert len(manifest["files"]) >= 9


def test_generic_starter_pack_is_available_before_program_creation() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = build_generic_independent_validation_starter_pack(root)
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        assert "MANIFEST.json" in archive.namelist()
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())
        manifest = json.loads(archive.read("MANIFEST.json"))
        assert manifest["program_specific"] is False
        assert manifest["contains_preapproved_evidence"] is False
