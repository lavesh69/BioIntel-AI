from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from biointel.education.phase23_30.agents import PROHIBITED_AUTONOMOUS_ACTIONS
from biointel.education.phase23_30.mcp_server import MCPApplication
from biointel.education.phase23_30.pilot import ONBOARDING_STEPS
from biointel.education.phase23_30.schema import MIGRATION_ID
from biointel.education.phase23_30.service import EducationEnterprisePlatform
from biointel.education.platform import (
    Conflict,
    Denied,
    EducationError,
    EducationPlatform,
    Missing,
)


@pytest.fixture()
def enterprise(tmp_path: Path):
    platform = EducationPlatform(
        tmp_path / "education.sqlite3",
        tmp_path / "media",
    )
    institution = platform.create_institution("admin", "Phase 30 Institute")
    platform.add_member("admin", institution["id"], "teacher", "subject_teacher")
    platform.add_member("admin", institution["id"], "reviewer", "content_moderator")
    platform.add_member("admin", institution["id"], "student", "university_student")
    platform.add_member("admin", institution["id"], "parent", "parent_guardian")
    other = platform.create_institution("other-admin", "Other Institute")
    service = EducationEnterprisePlatform(platform, root=str(tmp_path))
    return service, platform, institution["id"], other["id"], tmp_path


def test_migration_registry_labs_and_schema(enterprise):
    service, _, institution_id, _, _ = enterprise
    inventory = service.database_inventory()
    assert service.migrate() == MIGRATION_ID
    assert inventory["table_count"] == 57
    assert inventory["index_count"] >= 20
    assert len(service.agent_registry("admin", institution_id)) == 8
    catalog = service.lab_catalog("student", institution_id)
    assert len(catalog) == 23
    assert {
        row["capability_class"] for row in catalog
    } == {"calculation_simulation", "structured_guided_workflow"}


def test_pilot_onboarding_lifecycle_and_export(enterprise):
    service, _, institution_id, _, _ = enterprise
    pilot = service.register_pilot(
        "admin",
        institution_id,
        name="Controlled pilot",
        terms_version="1.0",
        terms_accepted=True,
        user_limit=500,
    )
    completed = service.save_onboarding(
        "admin",
        pilot["id"],
        "admin",
        "institution_administrator",
        completed_steps=ONBOARDING_STEPS["institution_administrator"],
    )
    assert completed["progress_percent"] == 100
    service.approve_onboarding("admin", completed["id"])
    statuses = [
        "technical_validation",
        "institution_onboarding",
        "data_import",
        "staff_training",
        "student_activation",
        "controlled_live_pilot",
        "pilot_review",
        "acceptance_or_remediation",
        "production_readiness_decision",
    ]
    for status in statuses:
        pilot = service.transition_pilot(
            "admin",
            pilot["id"],
            status,
            readiness_decision="accepted" if status == statuses[-1] else "",
        )
    assert pilot["readiness_decision"] == "accepted"
    exported = service.export_pilot("admin", pilot["id"])
    assert Path(exported["path"]).is_file()
    assert len(exported["sha256"]) == 64


def test_import_template_dry_run_commit_and_rollback(enterprise, tmp_path: Path):
    service, platform, institution_id, _, _ = enterprise
    template = service.generate_import_template(
        "admin",
        institution_id,
        "courses",
        file_format="xlsx",
    )
    assert Path(template["path"]).suffix == ".xlsx"
    source = tmp_path / "पाठ्यक्रम.csv"
    source.write_text(
        "external_key,code,name\ncourse-one,BIO101,जीव विज्ञान\n",
        encoding="utf-8-sig",
    )
    job = service.dry_run_import(
        "admin",
        institution_id,
        "courses",
        source,
    )
    assert job["state"] == "validated"
    committed = service.commit_import(
        "admin",
        job["id"],
        confirmation_digest=job["confirmation_digest"],
    )
    assert committed["state"] == "committed"
    assert platform._one(
        "SELECT name FROM subjects WHERE institution_id=? AND code='BIO101'",
        (institution_id,),
    )["name"] == "जीव विज्ञान"
    invalid = tmp_path / "invalid.csv"
    invalid.write_text(
        "external_key,student_id,subject_code\nbad,missing,NOPE\n",
        encoding="utf-8",
    )
    invalid_job = service.dry_run_import(
        "admin",
        institution_id,
        "enrolments",
        invalid,
    )
    with pytest.raises(Conflict):
        service.commit_import(
            "admin",
            invalid_job["id"],
            confirmation_digest=invalid_job["confirmation_digest"],
        )


def test_observability_support_and_diagnostic_privacy(enterprise):
    service, _, institution_id, _, _ = enterprise
    service.record_health(
        institution_id,
        "api",
        "fastapi",
        "healthy",
        latency_ms=12,
        metrics={"requests": 2},
    )
    with pytest.raises(Denied):
        service.record_health(
            institution_id,
            "classroom",
            "content",
            "healthy",
            sensitive_content_collected=True,
        )
    diagnostic = service.create_diagnostic_bundle("admin", institution_id)
    assert diagnostic["contains_sensitive_student_content"] is False
    assert Path(diagnostic["path"]).is_file()
    ticket = service.create_support_ticket(
        "student",
        institution_id,
        module="virtual_lab",
        severity="high",
        title="Attempt issue",
        description="The measurement was rejected.",
    )
    updated = service.update_support_ticket(
        "admin",
        ticket["id"],
        state="resolved",
        resolution="Protocol clarified.",
        comment="Resolved after review.",
        internal_only=True,
    )
    assert updated["state"] == "resolved"


def test_agent_approval_safety_evidence_and_partial_failure(enterprise):
    service, _, institution_id, _, _ = enterprise
    task = service.create_agent_task(
        "admin",
        institution_id,
        agent_key="teacher_assistant",
        task_input={"topic": "DNA replication"},
        idempotency_key="teacher-dna",
    )
    assert task["state"] == "awaiting_approval"
    with pytest.raises(Denied):
        service.approve_agent_task("admin", task["id"], decision="approved")
    service.approve_agent_task("reviewer", task["id"], decision="approved")
    completed = service.execute_agent_task("admin", task["id"])
    assert completed["state"] == "completed"
    output = json.loads(completed["output_json"])
    assert output["safety"]["publication_performed"] is False
    research = service.create_agent_task(
        "teacher",
        institution_id,
        agent_key="research_assistant",
        task_input={"topic": "CRISPR safety"},
        requested_tools=["search_science_pulse"],
        idempotency_key="research-no-evidence",
    )
    research = service.execute_agent_task("teacher", research["id"])
    assert research["state"] == "partially_completed"
    with pytest.raises(Denied):
        service.create_agent_task(
            "admin",
            institution_id,
            agent_key="examination_authoring",
            task_input={"requested_action": "publish_official_grades"},
            idempotency_key="unsafe",
        )
    assert "publish_official_grades" in PROHIBITED_AUTONOMOUS_ACTIONS


def _complete_lab_attempt(
    service: EducationEnterprisePlatform,
    institution_id: str,
) -> tuple[dict, dict]:
    attempt = service.start_lab_attempt(
        "student",
        institution_id,
        "lab_dilution_calculations",
        scenario_seed=7,
    )
    actions = [
        ("review", False),
        ("confirm_safety", True),
        ("prepare", False),
        ("perform", False),
        ("measure", False),
        ("interpret", False),
        ("cleanup", True),
    ]
    for action, safety in actions:
        step = service.record_lab_step(
            "student",
            attempt["id"],
            action=action,
            values={"value": 10.0, "unit": "ml"},
            safety_acknowledged=safety,
        )
        assert step["valid"] == 1
    service.add_lab_notebook_entry(
        "student",
        attempt["id"],
        entry_type="observation",
        body="Measured dilution and recorded uncertainty.",
    )
    submitted = service.submit_lab_attempt(
        "student",
        attempt["id"],
        results={"final_volume_ml": 100},
        discussion="The dilution equation was applied.",
        references=[{"label": "Institution protocol"}],
    )
    assessment = service.assess_lab_attempt(
        "teacher",
        attempt["id"],
        procedural_score=85,
        calculation_score=90,
        safety_score=95,
        interpretation_score=80,
        rubric_score=85,
    )
    return submitted, assessment


def test_virtual_lab_state_calculation_notebook_assessment_and_pdf(enterprise):
    service, _, institution_id, _, _ = enterprise
    assert service.convert_unit(1, "ml", "ul") == 1000
    assert service.dilution_result(1, 10, 0.1) == 100
    attempt = service.start_lab_attempt(
        "student",
        institution_id,
        "lab_micropipetting",
        scenario_seed=1,
    )
    invalid = service.record_lab_step(
        "student",
        attempt["id"],
        action="perform",
    )
    assert invalid["valid"] == 0
    submitted, assessment = _complete_lab_attempt(service, institution_id)
    assert submitted["state"] == "submitted"
    assert assessment["total_score"] > 80
    report = service.export_lab_report("student", submitted["id"])
    assert Path(report["path"]).read_bytes().startswith(b"%PDF")


def test_mastery_explanations_spaced_repetition_and_cycle_control(enterprise):
    service, _, institution_id, _, _ = enterprise
    policy = service.ensure_mastery_policy("teacher", institution_id)
    concept = service.create_concept(
        "teacher",
        institution_id,
        key="dna-replication",
        name="DNA replication",
    )
    prerequisite = service.create_concept(
        "teacher",
        institution_id,
        key="nucleotide-structure",
        name="Nucleotide structure",
    )
    service.link_concepts(
        "teacher",
        institution_id,
        prerequisite["id"],
        concept["id"],
    )
    with pytest.raises(Conflict):
        service.link_concepts(
            "teacher",
            institution_id,
            concept["id"],
            prerequisite["id"],
        )
    for index, score in enumerate((0.5, 0.75, 0.9), start=1):
        service.record_mastery_evidence(
            "student",
            institution_id,
            "student",
            concept["id"],
            evidence_type="practice",
            correctness=score,
            confidence=0.7,
            difficulty=0.6,
            source_id=f"practice-{index}",
        )
    record = service._one(
        "SELECT * FROM education_p30_mastery_records WHERE student_id='student' AND concept_id=?",
        (concept["id"],),
    )
    assert record["policy_id"] == policy["id"]
    assert "RULE_BASED_NOT_VALIDATED_AI" in json.loads(
        record["explanation_codes_json"]
    )
    recommendation = service.recommend_next(
        "student",
        institution_id,
        "student",
        concept["id"],
    )
    assert recommendation["explanation"]
    schedule = service.schedule_review(
        "student",
        institution_id,
        "student",
        concept["id"],
        algorithm="sm2",
        quality=4,
    )
    assert schedule["algorithm_version"] == "1.0"


def test_research_provenance_review_publish_and_retraction_warning(enterprise):
    service, _, institution_id, _, _ = enterprise
    paper = service.ingest_research_paper(
        "teacher",
        institution_id,
        title="Verified study",
        doi="10.1000/example",
        findings="Observed result.",
        limitations="Small sample.",
    )
    service.verify_paper(
        "reviewer",
        paper["id"],
        verification_state="verified_metadata",
        retraction_state="none",
    )
    asset = service.transform_research_asset(
        "teacher",
        institution_id,
        asset_type="lecture_outline",
        title="Evidence lecture",
        paper_ids=[paper["id"]],
    )
    asset = service.review_research_asset(
        "reviewer",
        asset["id"],
        decision="evidence_verified",
    )
    assert asset["review_state"] == "faculty_review"
    asset = service.review_research_asset(
        "teacher",
        asset["id"],
        decision="faculty_approved",
    )
    published = service.publish_research_asset(
        "teacher",
        asset["id"],
        target="academy",
    )
    assert published["publishing_state"] == "published"
    service.verify_paper(
        "reviewer",
        paper["id"],
        verification_state="verified_metadata",
        retraction_state="retracted",
    )
    assert service._one(
        "SELECT review_state FROM education_p30_research_assets WHERE id=?",
        (asset["id"],),
    )["review_state"] == "needs_revision"


def test_portfolio_credential_verify_revoke_and_private_share(enterprise):
    service, _, institution_id, _, _ = enterprise
    portfolio = service.get_or_create_portfolio("student", institution_id)
    assert portfolio["visibility"] == "private"
    credential = service.issue_credential(
        "teacher",
        institution_id,
        "student",
        credential_type="micro_credential",
        title="Bioinformatics foundations",
        criteria={"course_complete": True},
        evidence=[
            {
                "type": "assessment",
                "id": "assessment-1",
                "verification_state": "passed",
            }
        ],
    )
    assert Path(credential["certificate_path"]).read_bytes().startswith(b"%PDF")
    verified = service.verify_credential(credential["unique_code"])
    assert verified["valid"] is True
    item = service.add_portfolio_item(
        "student",
        portfolio["id"],
        item_type="credential",
        title=credential["title"],
        evidence_type="credential",
        evidence_id=credential["id"],
    )
    assert item["verification_state"] == "verified"
    share = service.create_portfolio_share(
        "student",
        portfolio["id"],
        audience="institution",
        item_ids=[item["id"]],
    )
    resolved = service.resolve_portfolio_share(share["token"])
    assert [row["id"] for row in resolved["items"]] == [item["id"]]
    service.revoke_credential(
        "teacher",
        credential["id"],
        reason="Evidence corrected.",
    )
    assert service.verify_credential(credential["unique_code"])["valid"] is False


def test_api_key_scope_rate_and_cross_tenant(enterprise):
    service, _, institution_id, other_id, _ = enterprise
    created = service.create_api_key(
        "admin",
        institution_id,
        name="Read client",
        scopes=["courses:read"],
    )
    auth = service.authenticate_api_key(
        created["key"],
        required_scope="courses:read",
    )
    assert auth["institution_id"] == institution_id
    with pytest.raises(Denied):
        service.authenticate_api_key(
            created["key"],
            required_scope="credentials:read",
        )
    with pytest.raises(Denied):
        service.get_or_create_portfolio("admin", other_id)


def test_sql_injection_idor_rate_limit_and_path_traversal_boundaries(
    enterprise,
    tmp_path: Path,
):
    service, _, institution_id, _, _ = enterprise
    with pytest.raises((Denied, Missing)):
        service.get_or_create_portfolio("admin", "' OR 1=1 --")
    created = service.create_api_key(
        "admin",
        institution_id,
        name="Rate boundary",
        scopes=["courses:read"],
    )
    auth = service.authenticate_api_key(
        created["key"],
        required_scope="courses:read",
        rate_limit_per_minute=1,
    )
    service.record_api_usage(
        auth,
        route="/courses",
        method="GET",
        status_code=200,
        latency_ms=1,
        request_id="rate-one",
    )
    with pytest.raises(Denied):
        service.authenticate_api_key(
            created["key"],
            required_scope="courses:read",
            rate_limit_per_minute=1,
        )
    source = tmp_path / "evidence.json"
    source.write_text('{"safe":true}', encoding="utf-8")
    stored = service.store_object(
        "student",
        institution_id,
        source,
        tenant_key="../../outside/../../evidence",
        content_type="application/json",
    )
    managed = Path(stored["storage_path"]).resolve()
    assert managed.is_relative_to(service.storage.resolve())
    blocked = tmp_path / "blocked.exe"
    blocked.write_bytes(b"MZ")
    with pytest.raises(EducationError):
        service.store_object(
            "student",
            institution_id,
            blocked,
            tenant_key="blocked",
        )


def test_webhook_hmac_replay_and_https_control(enterprise):
    service, _, institution_id, _, _ = enterprise
    with pytest.raises(Denied):
        service.register_webhook(
            "admin",
            institution_id,
            name="unsafe",
            target_url="http://example.org/hook",
            event_types=["credential.issued"],
        )
    created = service.register_webhook(
        "admin",
        institution_id,
        name="local",
        target_url="http://127.0.0.1:9000/hook",
        event_types=["credential.issued"],
    )
    timestamp = service._one(
        "SELECT created_at FROM education_p30_webhooks WHERE id=?",
        (created["id"],),
    )["created_at"]
    payload = '{"credential":"one"}'
    signature = service.webhook_signature(
        created["signing_secret"],
        timestamp,
        "nonce",
        payload,
    )
    assert service.verify_webhook_signature(
        created["signing_secret"],
        timestamp,
        "nonce",
        payload,
        signature,
    )
    assert not service.verify_webhook_signature(
        created["signing_secret"],
        "2000-01-01T00:00:00+00:00",
        "nonce",
        payload,
        signature,
    )


def test_plugin_permissions_and_mcp_write_approval(enterprise):
    service, _, institution_id, _, _ = enterprise
    with pytest.raises(Denied):
        service.register_plugin(
            "admin",
            institution_id,
            {
                "key": "unsafe",
                "name": "Unsafe",
                "version": "1",
                "compatibility": ">=15.6",
                "permissions": ["filesystem.unrestricted"],
            },
        )
    plugin = service.register_plugin(
        "admin",
        institution_id,
        {
            "key": "lesson-helper",
            "name": "Lesson helper",
            "version": "1.0",
            "compatibility": ">=15.6",
            "permissions": ["education.draft"],
        },
    )
    with pytest.raises(Conflict):
        service.set_plugin_state("admin", plugin["id"], enabled=True)
    service.grant_plugin_permission(
        "admin",
        plugin["id"],
        "education.draft",
        granted=True,
    )
    assert service.set_plugin_state(
        "admin",
        plugin["id"],
        enabled=True,
    )["state"] == "enabled"
    service.set_mcp_policy(
        "admin",
        institution_id,
        principal_id="teacher",
        tool_key="create_draft_lesson",
        allowed=True,
        write_approval_required=True,
    )
    with pytest.raises(Denied):
        service.call_mcp_tool(
            "teacher",
            institution_id,
            "create_draft_lesson",
            {"title": "Draft"},
        )
    called = service.call_mcp_tool(
        "teacher",
        institution_id,
        "create_draft_lesson",
        {"title": "Draft"},
        human_approved=True,
    )
    assert called["result"]["published"] is False


def test_mcp_protocol_scoped_auth(enterprise):
    service, _, institution_id, _, _ = enterprise
    api_key = service.create_api_key(
        "admin",
        institution_id,
        name="MCP",
        scopes=["courses:read"],
    )
    service.set_mcp_policy(
        "admin",
        institution_id,
        principal_id="teacher",
        tool_key="search_courses",
        allowed=True,
        write_approval_required=False,
    )
    application = MCPApplication(
        platform=service,
        principal_id="teacher",
        institution_id=institution_id,
        api_key=api_key["key"],
    )
    initialized = application.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert initialized["result"]["serverInfo"]["name"].startswith("biointel")
    listed = application.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert [tool["name"] for tool in listed["result"]["tools"]] == ["search_courses"]
    called = application.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "search_courses", "arguments": {"query": "biology"}},
        }
    )
    assert called["result"]["isError"] is False


def test_job_idempotency_claim_complete_retry_and_object_storage(
    enterprise,
    tmp_path: Path,
):
    service, _, institution_id, _, _ = enterprise
    first = service.enqueue_job(
        "admin",
        institution_id,
        job_type="analytics_refresh",
        payload={},
        idempotency_key="analytics-one",
    )
    second = service.enqueue_job(
        "admin",
        institution_id,
        job_type="analytics_refresh",
        payload={"duplicate": True},
        idempotency_key="analytics-one",
    )
    assert first["id"] == second["id"]
    claimed = service.claim_job("worker-one")
    completed = service.complete_job(
        "worker-one",
        claimed["id"],
        result={"ok": True},
    )
    assert completed["state"] == "completed"
    retry_job = service.enqueue_job(
        "admin",
        institution_id,
        job_type="notification",
        payload={},
        idempotency_key="notify-one",
        max_retries=0,
    )
    claimed = service.claim_job("worker-one")
    assert claimed["id"] == retry_job["id"]
    failed = service.fail_job("worker-one", claimed["id"], error="offline")
    assert failed["state"] == "dead_letter"
    source = tmp_path / "result.json"
    source.write_text('{"ok":true}', encoding="utf-8")
    stored = service.store_object(
        "admin",
        institution_id,
        source,
        tenant_key="reports/result",
        content_type="application/json",
    )
    assert Path(stored["storage_path"]).is_file()
    assert stored["sha256"]


def test_backup_inspect_unicode_and_windows_scripts(enterprise, tmp_path: Path):
    service, _, institution_id, _, root = enterprise
    from scripts.phase23_30_backup_restore import backup, inspect_backup

    output = tmp_path / "बैकअप phase 30.zip"
    result = backup(root, output)
    assert result["quick_check"] == "ok"
    assert inspect_backup(output)["valid"] is True
    service.ensure_mastery_policy("teacher", institution_id)
    project_root = Path(__file__).resolve().parents[1]
    for name in (
        "RUN_EDUCATION_PHASE23_TO_30_WORKER_WINDOWS.bat",
        "RUN_BIOINTEL_MCP_WINDOWS.bat",
        "DIAGNOSE_EDUCATION_PHASE23_TO_30_WINDOWS.bat",
        "INSTALL_EDUCATION_PHASE23_TO_30_WINDOWS.bat",
        "EXTRACT_INSTALL_RUN_EDUCATION_PHASE23_TO_30_4PART_WINDOWS.bat",
    ):
        text = (project_root / name).read_text(encoding="utf-8")
        assert "%~dp0" in text or "%CD%" in text
        assert "rm -rf" not in text


def test_fastapi_openapi_and_public_scope(enterprise, monkeypatch):
    service, _, institution_id, _, _ = enterprise
    from biointel.education.phase23_30 import api

    monkeypatch.setattr(api, "_SERVICE", service)
    app = FastAPI()
    app.include_router(api.public_router)
    client = TestClient(app)
    key = service.create_api_key(
        "admin",
        institution_id,
        name="Public courses",
        scopes=["courses:read"],
    )
    response = client.get(
        f"/api/v1/institutions/{institution_id}/courses",
        headers={"Authorization": f"Bearer {key['key']}"},
    )
    assert response.status_code == 200
    denied = client.get(
        f"/api/v1/institutions/{institution_id}/science-records",
        headers={"Authorization": f"Bearer {key['key']}"},
    )
    assert denied.status_code == 403
    assert any(
        path.startswith("/api/v1/institutions/")
        for path in client.app.openapi()["paths"]
    )


def test_release_matrix_is_truthful(enterprise):
    service, _, institution_id, _, _ = enterprise
    matrix = service.capability_matrix()
    statuses = {item["status"] for item in matrix.values()}
    assert statuses == {
        "IMPLEMENTED_AND_VERIFIED",
        "IMPLEMENTED_REQUIRES_EXTERNAL_VALIDATION",
        "PARTIALLY_IMPLEMENTED",
        "BLOCKED_WITH_REASON",
    }
    assert matrix["phase26_validated_ai_mastery"]["status"] == "BLOCKED_WITH_REASON"
    assert matrix["phase30_local_desktop"]["status"] == "IMPLEMENTED_AND_VERIFIED"
    qualification = service.release_qualification("admin", institution_id)
    assert qualification["database_quick_check"] is True
    assert qualification["audit_chain"]["passed"] is True
