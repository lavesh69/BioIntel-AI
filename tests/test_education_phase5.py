from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from biointel.education.phase5 import EducationPhase5Service
from biointel.education.platform import Conflict, Denied, EducationPlatform


@pytest.fixture()
def phase5():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        platform = EducationPlatform(root / "education.sqlite3", root / "media")
        admin, registrar, teacher, student = "admin", "registrar", "teacher", "student"
        institution = platform.create_institution(admin, "Phase 5 University")["id"]
        platform.add_member(admin, institution, registrar, "registrar")
        platform.add_member(admin, institution, teacher, "subject_teacher")
        platform.add_member(admin, institution, student, "university_student")
        unit = platform.create_unit(admin, institution, "School of Life Sciences", "school")
        subject = platform.create_subject(admin, institution, "BIO-501", "Systems Biology", unit["id"])
        platform.assign_teacher(admin, institution, subject["id"], teacher)
        platform.enroll(admin, institution, subject["id"], student)
        service = EducationPhase5Service(platform, root=root)
        yield root, platform, service, admin, registrar, teacher, student, institution, unit, subject


def test_multi_campus_hierarchy_and_tenant_isolation(phase5):
    _, platform, service, admin, _, _, _, institution, unit, _ = phase5
    campus = service.create_campus(admin, institution, "MAIN", "Main Campus", address={"city": "Delhi"})
    service.link_unit_to_campus(admin, campus["id"], unit["id"])
    hierarchy = service.hierarchy(admin, institution)
    assert hierarchy["campuses"][0]["unit_ids"] == [unit["id"]]
    other = platform.create_institution("other-admin", "Other University")["id"]
    other_unit = platform.create_unit("other-admin", other, "Other School", "school")
    with pytest.raises(Denied):
        service.link_unit_to_campus(admin, campus["id"], other_unit["id"])


def test_identity_config_never_accepts_inline_secrets_and_mfa_policy(phase5):
    _, _, service, admin, _, _, _, institution, _, _ = phase5
    with pytest.raises(Denied):
        service.configure_identity_provider(admin, institution, "oidc", "Unsafe", issuer_url="https://id.example", secret_reference="client_secret=plain")
    with pytest.raises(Conflict):
        service.configure_identity_provider(admin, institution, "oidc", "Draft", issuer_url="https://id.example", activate=True)
    posture = service.configure_identity_provider(admin, institution, "oidc", "University SSO", issuer_url="https://id.example", client_id="biointel", secret_reference="env:BIOINTEL_OIDC_SECRET", allowed_domains=["university.edu"], activate=True)
    assert posture["providers"][0]["secret_reference"] == "configured"
    posture = service.save_mfa_policy(admin, institution, required_roles=["institution_administrator", "registrar"], methods=["totp", "webauthn"])
    assert posture["readiness_score"] == 100
    assert posture["external_login_verified"] is False


def test_storage_dedupe_and_safe_tenant_paths(phase5):
    root, _, service, admin, _, teacher, _, institution, _, _ = phase5
    source = root / "report.txt"
    source.write_text("institution report", encoding="utf-8")
    first = service.store_local_object(teacher, institution, source)
    second = service.store_local_object(teacher, institution, source)
    assert first["sha256"] == second["sha256"]
    assert second["deduplicated"] is True
    with pytest.raises(Denied):
        service.store_local_object(teacher, institution, source, object_key="../escape.txt")


def test_verified_backup_and_non_destructive_restore_rehearsal(phase5):
    _, platform, service, admin, _, _, _, institution, _, _ = phase5
    backup = service.create_backup(admin, institution, "nightly")
    assert backup["integrity_valid"] is True
    rehearsal = service.restore_rehearsal(admin, backup["id"])
    assert rehearsal["integrity"] == "ok"
    assert rehearsal["live_database_replaced"] is False
    assert Path(rehearsal["rehearsal_path"]).is_file()
    assert platform.db.quick_check()


def test_background_job_lock_retry_and_completion(phase5):
    _, _, service, _, _, teacher, _, institution, _, _ = phase5
    job = service.enqueue_job(teacher, institution, "generate_report", {"student_id": "student"}, priority=90, max_attempts=2)
    claimed = service.claim_job("worker-a")
    assert claimed and claimed["id"] == job["id"] and claimed["attempts"] == 1
    with pytest.raises(Denied):
        service.complete_job("worker-b", job["id"], claimed["lock_token"], {"ok": True})
    retry = service.fail_job("worker-a", job["id"], claimed["lock_token"], "temporary", retry_delay_seconds=0)
    assert retry["state"] == "queued"
    claimed2 = service.claim_job("worker-a")
    done = service.complete_job("worker-a", job["id"], claimed2["lock_token"], {"ok": True})
    assert done["state"] == "succeeded"


def test_integration_readiness_is_honest_about_external_verification(phase5):
    _, _, service, admin, _, _, _, institution, _, _ = phase5
    integration = service.configure_integration(admin, institution, "moodle", "Moodle", base_url="https://lms.example", secret_reference="vault:moodle", activate=True)
    checked = service.test_integration_readiness(admin, integration["id"])
    assert checked["state"] == "configuration_ready"
    assert checked["readiness"]["network_verified"] is False
    assert checked["readiness"]["external_credentials_verified"] is False


def test_transactional_member_and_subject_import(phase5):
    _, platform, service, admin, _, _, _, institution, _, _ = phase5
    invalid = service.preview_import(admin, institution, "members", "members.csv", "user_id,role\nalice,university_student\nbob,bad_role\n")
    assert invalid["invalid_rows"] == 1
    with pytest.raises(Conflict):
        service.commit_import(admin, invalid["id"])
    valid = service.preview_import(admin, institution, "members", "members2.csv", "user_id,role\nalice,university_student\nbob,subject_teacher\n")
    committed = service.commit_import(admin, valid["id"])
    assert committed["state"] == "committed"
    assert platform.membership("alice", institution)[0]["role"] == "university_student"
    subjects = service.preview_import(admin, institution, "subjects", "subjects.csv", "code,name,syllabus\nBIO-502,Computational Biology,Core syllabus\n")
    service.commit_import(admin, subjects["id"])
    assert platform._one("SELECT name FROM subjects WHERE institution_id=? AND code='BIO-502'", (institution,))["name"] == "Computational Biology"


def test_governance_report_has_external_qualification_boundaries(phase5):
    _, _, service, admin, _, _, _, institution, _, _ = phase5
    report = service.generate_governance_report(admin, institution)
    assert report["payload"]["human_review_required"] is True
    assert report["payload"]["external_qualification"]["production_database_verified"] is False
    assert len(report["sha256"]) == 64


def test_storage_backend_and_phase5_ui_smoke(phase5, monkeypatch):
    root, platform, service, admin, _, _, _, institution, _, _ = phase5
    backend = service.configure_storage_backend(admin, institution, "local", "Local governed store", activate=True)
    assert backend["state"] == "ready"
    import biointel.education.institution_ui as ui
    monkeypatch.setattr(ui, "_demo_controls", lambda _root: False)
    monkeypatch.setattr(ui, "_page_platform", lambda _root, _demo: platform)
    monkeypatch.setattr(ui, "_identity_input", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ui, "_institution", lambda _platform: institution)
    monkeypatch.setattr(ui, "_actor", lambda: admin)
    ui.render_education_institution_center(root)
    assert service.dashboard(admin, institution)["external_services_verified"] is False


def test_postgresql_profile_is_configuration_ready_not_falsely_verified(phase5):
    _, _, service, admin, _, _, _, institution, _, _ = phase5
    with pytest.raises(Conflict):
        service.configure_database_profile(admin, institution, "postgresql", "Production", activate=True)
    profile = service.configure_database_profile(admin, institution, "postgresql", "Production", dsn_reference="vault:biointel/postgres-dsn", pool_min=2, pool_max=30, ssl_mode="verify-full", activate=True)
    assert profile["state"] == "configuration_ready"
    assert profile["readiness"]["network_verified"] is False
    posture = service.database_posture(admin, institution)
    assert posture["postgresql_configuration_ready"] is True
    assert posture["production_database_verified"] is False
