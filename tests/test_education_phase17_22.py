from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from biointel.connect.services import build_connect_services
from biointel.education.phase17_22 import api as os_api
from biointel.education.phase17_22.schema import MIGRATION_ID
from biointel.education.phase17_22.service import EducationOS
from biointel.education.platform import Conflict, Denied, EducationPlatform, ident, now
from biointel.shiro.core.orchestrator import ShiroOrchestrator
from scripts.run_education_phase17_22_worker import PidLease


def build(tmp_path: Path):
    root = tmp_path / "Unicode path शिक्षा BioIntel"
    platform = EducationPlatform(root / "data" / "education.sqlite3", root / "tenant media")
    admin, teacher, reviewer, student = "admin", "teacher", "reviewer", "student"
    institution = platform.create_institution(admin, "Phase 17-22 University")["id"]
    platform.add_member(admin, institution, teacher, "subject_teacher")
    platform.add_member(admin, institution, reviewer, "content_moderator")
    platform.add_member(admin, institution, student, "university_student")
    connect = build_connect_services(
        root,
        database_path=root / "connect data" / "connect.sqlite3",
        storage_root=root / "connect media",
    )
    shiro = ShiroOrchestrator(root=root, data_dir=root / "shiro data")
    service = EducationOS(platform, root=root, shiro=shiro, connect=connect)
    return service, platform, admin, teacher, reviewer, student, institution, root


def workspace(service: EducationOS, admin: str, teacher: str, institution: str):
    return service.create_learning_workspace(
        admin,
        institution,
        program_name="MSc Biomedical AI",
        course_code="BIO-501",
        course_name="Genome Stability",
        classroom_name="Section A",
        teacher_id=teacher,
        academic_year="2026-27",
    )


def test_migration_is_repeatable_and_path_with_spaces(tmp_path: Path):
    service, platform, *_ = build(tmp_path)
    assert service.migrate() == MIGRATION_ID
    assert service.migrate() == MIGRATION_ID
    assert platform.db.quick_check()
    assert "शिक्षा BioIntel" in str(platform.db.path)
    with platform.db.connection() as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"education_resource_registry", "education_outbox", "education_studio_projects"} <= tables


def test_tenant_and_resource_isolation(tmp_path: Path):
    service, platform, admin, teacher, _, student, institution, _ = build(tmp_path)
    flow = workspace(service, admin, teacher, institution)
    service.enroll_student(teacher, flow["workflow_id"], student)

    other_admin = "other-admin"
    other = platform.create_institution(other_admin, "Other University")["id"]
    assert service.authorize(student, institution, "view", resource_type="course", resource_id=flow["course"]["id"]).allowed
    with pytest.raises(Denied):
        service.authorize(other_admin, other, "view", resource_type="course", resource_id=flow["course"]["id"])
    with pytest.raises(Denied):
        service.ask_shiro(other_admin, flow["shiro_scope"]["id"], "What is BRCA1?")


def test_learning_shiro_connect_and_restart_workflow(tmp_path: Path):
    service, platform, admin, teacher, _, student, institution, root = build(tmp_path)
    flow = workspace(service, admin, teacher, institution)
    service.enroll_student(teacher, flow["workflow_id"], student)
    source = root / "course material.md"
    source.write_text(
        "BRCA1 supports homologous recombination DNA repair. TP53 regulates cell-cycle checkpoints.",
        encoding="utf-8",
    )
    material = service.publish_material(teacher, flow["workflow_id"], title="Genome repair", source_path=source)
    assert material["shiro"]["evidence_status"] == "approved_indexed"
    answer = service.ask_shiro(student, flow["shiro_scope"]["id"], "How does BRCA1 support DNA repair?")
    assert answer["evidence_status"] == "grounded"
    assert answer["citations"] and answer["citations"][0]["source_id"]
    unsupported = service.ask_shiro(student, flow["shiro_scope"]["id"], "What is the capital of Mars?")
    assert unsupported["evidence_status"] in {"insufficient_evidence", "low_evidence"}

    assignment = service.create_assignment(
        teacher,
        flow["workflow_id"],
        title="Repair mechanisms",
        instructions="Explain homologous recombination.",
        due_at="2099-01-01T00:00:00+00:00",
    )["assignment"]
    first = service.submit_assignment(
        student,
        assignment["id"],
        body="BRCA1 coordinates repair.",
        idempotency_key="submission-1",
    )
    replay = service.submit_assignment(
        student,
        assignment["id"],
        body="BRCA1 coordinates repair.",
        idempotency_key="submission-1",
    )
    assert replay["id"] == first["id"]
    with pytest.raises(Conflict):
        service.submit_assignment(student, assignment["id"], body="changed", idempotency_key="submission-1")

    result = service.grade_submission(teacher, first["id"], marks=42, feedback="Review repair pathways")
    assert result["grade"]["marks"] == 42
    delivered = service.dispatch_outbox(admin, institution)
    assert delivered["failed"] == 0 and delivered["delivered"] >= 1
    assert service.unread_connect_count(student, institution) >= 1

    restarted_platform = EducationPlatform(platform.db.path, platform.storage)
    restarted = EducationOS(
        restarted_platform,
        root=root,
        shiro=service.shiro,
        connect=service.connect,
    )
    home = restarted.home_snapshot(student, institution)
    assert home["data_status"] == "persistent_local"
    persisted = restarted_platform._one("SELECT * FROM grades WHERE submission_id=?", (first["id"],))
    assert persisted and persisted["marks"] == 42


def test_intervention_requires_data_and_human_review(tmp_path: Path):
    service, _, admin, teacher, _, student, institution, _ = build(tmp_path)
    flow = workspace(service, admin, teacher, institution)
    service.enroll_student(teacher, flow["workflow_id"], student)
    rows = service.refresh_interventions(teacher, institution, student, flow["course"]["id"])
    assert rows
    assert all(row["model_kind"] == "rule_based_indicator" for row in rows)
    assert all(row["state"] == "pending_review" for row in rows)
    reviewed = service.review_intervention(teacher, rows[0]["id"], decision="dismissed", note="Insufficient observations")
    assert reviewed["state"] == "dismissed" and reviewed["reviewed_by"] == teacher


def test_studio_version_review_publish_and_truthful_export(tmp_path: Path):
    service, _, admin, teacher, reviewer, _, institution, _ = build(tmp_path)
    flow = workspace(service, admin, teacher, institution)
    project = service.create_studio_project(
        teacher,
        institution,
        title="DNA Repair Lecture",
        project_type="presentation",
    )
    version = service.save_studio_version(
        teacher,
        project["id"],
        {"slides": [{"title": "BRCA1", "body": "DNA repair"}]},
        expected_version=0,
    )
    assert version["version_number"] == 1
    with pytest.raises(Conflict):
        service.save_studio_version(teacher, project["id"], {"slides": []}, expected_version=0)
    service.submit_studio_review(teacher, project["id"])
    approved = service.review_studio_project(reviewer, project["id"], decision="approved", comment="Evidence checked")
    assert approved["state"] == "approved"
    publication = service.publish_studio_project(
        teacher,
        project["id"],
        target_type="classroom",
        target_id=flow["classroom"]["id"],
    )
    assert publication["state"] == "queued"
    exported = service.export_studio_bundle(teacher, project["id"])
    assert exported["verified"] is True
    with zipfile.ZipFile(exported["path"]) as archive:
        manifest = json.loads(archive.read("project.json"))
    assert manifest["schema"] == "biointel-studio-project-1.0"
    capabilities = service.studio_capabilities()
    assert capabilities["structured_project_bundle"]["verified_locally"] is True
    assert capabilities["pdf"]["available"] is False


def test_science_pulse_dedup_health_and_release_evidence(tmp_path: Path):
    service, platform, admin, *_rest, institution, _root = build(tmp_path)
    stamp = now()
    rows = [
        (ident("pulse"), institution, "crossref", "crossref-1", "10.1000/example", "", "Genome repair in BRCA1 cells", "Evidence", "[]", "https://doi.org/10.1000/example", stamp, "journal", "{}", stamp, stamp),
        (ident("pulse"), institution, "europe_pmc", "pmc-1", "10.1000/EXAMPLE", "123", "Genome repair in BRCA1 cells", "Evidence", "[]", "https://europepmc.org/article/123", stamp, "journal", "{}", stamp, stamp),
    ]
    with platform.db.connection() as db:
        db.executemany("INSERT INTO education_pulse_external_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    dedup = service.canonicalize_pulse_records(admin, institution)
    assert dedup == {"records": 2, "canonical": 1, "duplicates": 1}
    health = service.run_health_checks(admin, institution)
    assert health["overall"] == "healthy"
    qualification = service.release_qualification(admin, institution)
    statuses = {row["check"]: row["status"] for row in qualification["checks"]}
    assert statuses["tenant_scoped_registry"] == "implemented_verified"
    assert statuses["turn_public_calling"] == "implemented_external_verification_required"
    assert {
        "biointel_connect",
        "course_aware_shiro",
        "education_home",
        "education_classroom",
        "science_pulse",
        "academy_lecture_studio",
        "education_universe",
        "examination_command_center",
        "education_intelligence_hub",
        "biointel_studio",
    } <= {key for key, status in statuses.items() if status == "implemented_verified"}


def test_api_schema_and_safe_error_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service, _, admin, teacher, _, _, institution, _ = build(tmp_path)
    monkeypatch.setattr(os_api, "_SERVICE", service)
    app = FastAPI()
    app.include_router(os_api.router, prefix="/api/v1/education")
    client = TestClient(app)
    response = client.post(
        "/api/v1/education/os/workflows",
        json={
            "actor": admin,
            "institution_id": institution,
            "program_name": "MSc",
            "course_code": "BIO-API",
            "course_name": "API Biology",
            "classroom_name": "API Section",
            "teacher_id": teacher,
        },
    )
    assert response.status_code == 200
    denied = client.get(f"/api/v1/education/os/home/{institution}", params={"actor": "unknown"})
    assert denied.status_code == 403
    schema = client.get("/openapi.json").json()
    assert "/api/v1/education/os/workflows" in schema["paths"]

def test_worker_pid_lease_prevents_duplicate_launch(tmp_path: Path):
    pid_file = tmp_path / "runtime path" / "worker.pid"
    with PidLease(pid_file):
        assert pid_file.is_file()
        with pytest.raises(RuntimeError, match="already running"):
            with PidLease(pid_file):
                pass
    assert not pid_file.exists()
