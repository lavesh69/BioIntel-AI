from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from biointel.education.phase6 import EducationPhase6Service
from biointel.education.platform import Conflict, Denied, EducationPlatform


def build(tmp_path: Path):
    platform = EducationPlatform(tmp_path / "education.sqlite3", tmp_path / "media")
    admin, teacher, student = "admin", "teacher", "student"
    institution = platform.create_institution(admin, "Phase 6 University")["id"]
    platform.add_member(admin, institution, teacher, "subject_teacher")
    platform.add_member(admin, institution, student, "university_student")
    unit = platform.create_unit(admin, institution, "School", "school")
    subject = platform.create_subject(admin, institution, "BIO-601", "Visual Biology", unit["id"])
    platform.assign_teacher(admin, institution, subject["id"], teacher)
    platform.enroll(admin, institution, subject["id"], student)
    service = EducationPhase6Service(platform, root=tmp_path)
    return platform, service, admin, teacher, student, institution, subject


def test_preferences_navigation_and_saved_view(tmp_path: Path):
    _, service, _, teacher, _, institution, _ = build(tmp_path)
    saved = service.save_preferences(teacher, institution, theme="light", density="compact", font_scale=1.2, high_contrast=True)
    assert saved["theme"] == "light"
    assert saved["font_scale"] == pytest.approx(1.2)
    service.record_visit(teacher, institution, "classroom")
    assert service.toggle_favorite(teacher, institution, "classroom") is True
    nav = service.navigation_state(teacher, institution)
    assert nav["favorites"] == ["classroom"]
    assert nav["recent"][0] == "classroom"
    view = service.save_view(teacher, institution, "gradebook", "Needs support", {"below": 60}, ["student_id", "overall_percent"])
    assert view["name"] == "Needs support"


def test_calendar_gradebook_and_attendance_visual_data(tmp_path: Path):
    platform, service, admin, teacher, student, institution, subject = build(tmp_path)
    start = datetime.now(timezone.utc) + timedelta(days=1)
    platform.create_timetable(admin, institution, subject["id"], teacher, "BIO-A", "LAB-1", start.isoformat(), (start + timedelta(hours=1)).isoformat())
    calendar = service.timetable_calendar(student, institution, start_day=start.date(), days=7)
    assert len(calendar["entries"]) == 1
    assignment = platform.create_assignment(teacher, institution, subject["id"], "Visual assignment", "Explain", (start + timedelta(days=3)).isoformat(), 20)
    submission = platform.submit_assignment(student, assignment["id"], "Answer", final=True)
    platform.grade_submission(teacher, submission["id"], 16, "Good")
    gradebook = service.gradebook(teacher, institution, subject["id"])
    assert gradebook["rows"][0]["overall_percent"] == 80.0
    session = platform.attendance_session(teacher, institution, subject["id"], start.date().isoformat(), "P1")
    platform.mark_attendance(teacher, session["id"], student, "present")
    heat = service.attendance_heatmap(teacher, institution, subject_id=subject["id"])
    assert heat["summary"][0]["attendance_percent"] == 100.0


def test_exam_analytics_and_student_denial(tmp_path: Path):
    _, service, admin, teacher, student, institution, subject = build(tmp_path)
    start = datetime.now(timezone.utc) + timedelta(minutes=5)
    exam = service.exams.create_exam(teacher, institution, subject["id"], "Analytics exam", 10, start.isoformat(), (start + timedelta(hours=1)).isoformat(), duration_minutes=30)
    service.exams.add_question(teacher, exam["id"], "single_choice", "A?", 10, options=["A", "B"], correct_answer="A", bloom_level="apply", difficulty="medium")
    service.permissions.set_override(admin, institution, "subject_teacher", "exam.publish", "allow")
    service.exams.publish_exam(teacher, exam["id"])
    analytics = service.exam_analytics(teacher, exam["id"])
    assert analytics["difficulty_distribution"] == {"medium": 1}
    with pytest.raises(Denied):
        service.exam_analytics(student, exam["id"])


def test_shiro_conversation_is_owner_scoped(tmp_path: Path):
    _, service, admin, teacher, student, institution, subject = build(tmp_path)
    service.phase4.index_subject_text(teacher, institution, subject["id"], "Cell evidence", "Cells are the basic structural and functional units of life.")
    conversation = service.create_conversation(student, institution, subject_id=subject["id"], title="Cell revision", language="English")
    updated = service.ask_conversation(student, conversation["id"], "What is a cell?")
    assert len(updated["messages"]) == 2
    assert updated["messages"][1]["role"] == "assistant"
    assert service.conversation(teacher, conversation["id"])["id"] == conversation["id"]
    assert service.conversation(admin, conversation["id"])["id"] == conversation["id"]


def test_workers_progress_cancel_requeue(tmp_path: Path):
    _, service, admin, teacher, _, institution, _ = build(tmp_path)
    service.register_worker(admin, institution, "worker-1", queues=["default"])
    job = service.phase5.enqueue_job(teacher, institution, "generate_report", {})
    claimed = service.phase5.claim_job("worker-1")
    progress = service.update_job_progress(institution, "worker-1", job["id"], claimed["lock_token"], 45, "Building report")
    assert progress["progress_percent"] == 45
    cancelled = service.cancel_job(admin, institution, job["id"])
    assert cancelled["cancel_requested"] == 1
    failed = service.phase5.fail_job("worker-1", job["id"], claimed["lock_token"], "cancelled", retry_delay_seconds=0)
    assert failed["state"] == "queued"
    claimed = service.phase5.claim_job("worker-1")
    service.phase5.fail_job("worker-1", job["id"], claimed["lock_token"], "permanent", retry_delay_seconds=0)
    claimed = service.phase5.claim_job("worker-1")
    final = service.phase5.fail_job("worker-1", job["id"], claimed["lock_token"], "permanent", retry_delay_seconds=0)
    assert final["state"] == "failed"
    requeued = service.requeue_job(admin, institution, job["id"])
    assert requeued["state"] == "queued"


def test_backup_schedule_and_integration_sync(tmp_path: Path):
    _, service, admin, _, _, institution, _ = build(tmp_path)
    schedule = service.create_backup_schedule(admin, institution, "Daily", hour_utc=0)
    assert schedule["frequency"] == "daily"
    integration = service.phase5.configure_integration(admin, institution, "moodle", "Moodle", base_url="https://lms.example", secret_reference="vault:moodle", activate=True)
    service.phase5.test_integration_readiness(admin, integration["id"])
    sync = service.start_integration_sync(admin, integration["id"], direction="pull", entity_type="courses")
    assert sync["state"] == "queued"
    operations = service.integration_operations(admin, institution)
    assert operations["runs"][0]["id"] == sync["id"]


def test_external_qualification_is_bounded_and_evidenced(tmp_path: Path):
    _, service, admin, _, _, institution, _ = build(tmp_path)
    profile = service.phase5.configure_database_profile(admin, institution, "sqlite", "Local DB", activate=True)
    qualified = service.external.verify_database_profile(admin, profile["id"])
    assert qualified["state"] == "verified"
    assert qualified["evidence"]["quick_check"] is True
    provider_posture = service.phase5.configure_identity_provider(
        admin,
        institution,
        "oidc",
        "Blocked local issuer",
        issuer_url="https://127.0.0.1",
        client_id="biointel",
        secret_reference="env:TEST_IDP_SECRET",
        activate=True,
    )
    provider_id = provider_posture["providers"][0]["id"]
    result = service.external.verify_identity_provider(admin, provider_id)
    assert result["state"] == "failed"
    assert "Private" in result["error_text"] or "loopback" in result["error_text"]
    history = service.external.history(admin, institution)
    assert len(history) == 2
