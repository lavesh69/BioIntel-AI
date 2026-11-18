from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from biointel.education.phase11 import EducationPhase11Service, _totp
from biointel.education.platform import Denied, EducationPlatform


def build(tmp_path: Path):
    platform = EducationPlatform(tmp_path / "education.sqlite3", tmp_path / "media")
    admin, teacher, reviewer, student = "admin", "teacher", "reviewer", "student"
    institution = platform.create_institution(admin, "Phase 11 University")["id"]
    platform.add_member(admin, institution, teacher, "subject_teacher")
    platform.add_member(admin, institution, reviewer, "professor")
    platform.add_member(admin, institution, student, "university_student")
    unit = platform.create_unit(admin, institution, "Science", "school")
    subject = platform.create_subject(admin, institution, "BIO-1101", "Mega Biology", unit["id"])
    platform.assign_teacher(admin, institution, subject["id"], teacher)
    platform.assign_teacher(admin, institution, subject["id"], reviewer)
    platform.enroll(admin, institution, subject["id"], student)
    service = EducationPhase11Service(platform, root=tmp_path)
    return platform, service, admin, teacher, reviewer, student, institution, subject


def test_totp_mfa_and_recovery_auth(tmp_path: Path):
    _, service, admin, _, _, _, institution, _ = build(tmp_path)
    service.enroll_identity(admin, institution, admin, "Correct-Horse-11", display_name="Admin", email="admin@example.edu")
    pending = service.begin_totp_enrollment(admin, institution, admin)
    confirmed = service.confirm_totp_enrollment(admin, institution, admin, _totp(pending["secret"]))
    assert confirmed["enabled"] is True
    begin = service.begin_secure_authentication(institution, "admin@example.edu", "Correct-Horse-11")
    assert begin["status"] == "mfa_required"
    signed = service.complete_secure_authentication(begin["challenge_token"], code=_totp(pending["secret"]))
    assert signed["mfa_verified"] is True
    assert service.validate_session(signed["token"])["user_id"] == admin

    second = service.begin_secure_authentication(institution, admin, "Correct-Horse-11")
    signed2 = service.complete_secure_authentication(second["challenge_token"], recovery_code=confirmed["recovery_codes"][0])
    assert signed2["status"] == "authenticated"
    third = service.begin_secure_authentication(institution, admin, "Correct-Horse-11")
    with pytest.raises(Denied):
        service.complete_secure_authentication(third["challenge_token"], recovery_code=confirmed["recovery_codes"][0])


def test_question_bank_review_blueprint_and_analysis(tmp_path: Path):
    _, service, admin, teacher, reviewer, student, institution, subject = build(tmp_path)
    bank = service.create_question_bank(teacher, institution, "Core Biology", subject_id=subject["id"])
    question = service.create_question(
        teacher,
        bank["id"],
        question_type="single_choice",
        title="DNA role",
        body="What is the primary role of DNA?",
        options=["Energy", "Inheritance", "Digestion", "Movement"],
        answer={"option": "Inheritance"},
        bloom_level="understand",
        difficulty="medium",
        outcome_code="CO1",
        marks=2,
    )
    with pytest.raises(Denied):
        service.review_question(teacher, question["id"], "approve")
    reviewed = service.review_question(reviewer, question["id"], "approve", comments="Scientifically valid")
    assert reviewed["state"] == "approved"
    published = service.publish_question(admin, question["id"])
    assert published["state"] == "published"
    blueprint = service.generate_question_blueprint(
        teacher,
        institution,
        subject_id=subject["id"],
        total_marks=2,
        bloom_distribution={"understand": 100},
        difficulty_distribution={"medium": 100},
    )
    assert blueprint["complete"] is True
    service.record_question_response(student, question["id"], student, is_correct=True, marks_awarded=2, response_seconds=14, option_key="Inheritance")
    analysis = service.question_item_analysis(teacher, question["id"])
    assert analysis["attempts"] == 1
    assert analysis["difficulty_index"] == 1


def test_grade_scheme_transcript_and_signed_credential(tmp_path: Path):
    _, service, admin, _, _, student, institution, subject = build(tmp_path)
    scheme = service.create_grade_scheme(
        admin,
        institution,
        "Semester Scheme",
        subject_id=subject["id"],
        categories=[
            {"name": "Assignments", "source_type": "assignment", "weight_percent": 40},
            {"name": "Examination", "source_type": "examination", "weight_percent": 60},
        ],
        bands=[
            {"label": "A", "minimum_percent": 80, "grade_points": 4},
            {"label": "B", "minimum_percent": 60, "grade_points": 3},
            {"label": "F", "minimum_percent": 0, "grade_points": 0},
        ],
    )
    grade = service.calculate_grade(admin, scheme["id"], student, {"Assignments": [80, 90], "Examination": 75})
    assert grade["grade_label"] == "B"
    service.upsert_transcript_entry(
        admin,
        institution,
        student,
        academic_year="2026-27",
        term="Semester 1",
        subject_code="BIO-1101",
        subject_name="Mega Biology",
        credits=4,
        marks_percent=grade["percentage"],
        grade_label=grade["grade_label"],
        grade_points=grade["grade_points"],
    )
    transcript = service.transcript(student, institution, student)
    assert transcript["total_credits"] == 4
    credential = service.issue_credential(admin, institution, student, credential_type="transcript_award", title="Semester 1 Completion", evidence={"cgpa": transcript["cgpa"]})
    verified = service.verify_credential(credential["serial_number"])
    assert verified["valid"] is True
    service.revoke_credential(admin, credential["id"], reason="Reissued")
    assert service.verify_credential(credential["serial_number"])["valid"] is False


def test_notification_reports_health_incident_and_privacy(tmp_path: Path):
    platform, service, admin, teacher, _, student, institution, subject = build(tmp_path)
    template = service.save_notification_template(
        admin,
        institution,
        "assignment_due",
        channel="in_app",
        subject_template="Assignment {{title}}",
        body_template="{{title}} is due on {{due}}.",
    )
    assert template["template_key"] == "assignment_due"
    queued = service.queue_notification(
        teacher,
        institution,
        student,
        template_key="assignment_due",
        context={"title": "Evidence Review", "due": "Friday"},
        idempotency_key="due-1",
    )
    claimed = service.claim_notification("worker-1")
    assert claimed and claimed["id"] == queued["id"]
    delivered = service.complete_notification("worker-1", claimed["id"], claimed["lock_token_plain"], state="delivered")
    assert delivered["state"] == "delivered"

    session = platform.attendance_session(teacher, institution, subject["id"], datetime.now(timezone.utc).date().isoformat(), "P1")
    platform.mark_attendance(teacher, session["id"], student, "present")
    report = service.generate_report(admin, institution, "attendance", output_format="csv")
    assert Path(report["output_path"]).is_file()
    health = service.record_health_snapshot(admin, institution)
    assert health["database_ok"] == 1 and health["storage_ok"] == 1
    incident = service.open_incident(admin, institution, "Test incident", severity="medium", summary="Qualification exercise")
    resolved = service.update_incident(admin, incident["id"], status="resolved", detail="Recovered")
    assert resolved["status"] == "resolved"
    privacy = service.create_privacy_request(student, institution, student, request_type="export", reason="Personal copy")
    assert privacy["state"] == "pending"
    assert service.decide_privacy_request(admin, privacy["id"], state="completed", note="Export delivered")["state"] == "completed"


def test_security_event_chain_and_rate_limit(tmp_path: Path):
    _, service, admin, _, _, _, institution, _ = build(tmp_path)
    service.security_event(institution, "first", actor_id=admin)
    service.security_event(institution, "second", actor_id=admin, severity="high")
    assert service.verify_security_chain(admin, institution)["passed"] is True
    service.enforce_rate_limit("test", limit=2, window_seconds=60)
    service.enforce_rate_limit("test", limit=2, window_seconds=60)
    with pytest.raises(Denied):
        service.enforce_rate_limit("test", limit=2, window_seconds=60)


def test_encrypted_full_backup_and_restore_rehearsal(tmp_path: Path):
    platform, service, admin, _, _, _, institution, _ = build(tmp_path)
    tenant_file = Path(platform.storage) / institution / "materials" / "evidence.txt"
    tenant_file.parent.mkdir(parents=True, exist_ok=True)
    tenant_file.write_text("verified evidence", encoding="utf-8")
    backup = service.create_full_backup(admin, institution, "mega-checkpoint")
    assert backup["integrity_valid"] is True
    assert Path(backup["archive_path"]).suffix == ".biointel-backup"
    rehearsal = service.full_backup_restore_rehearsal(admin, backup["id"])
    assert rehearsal["integrity"] == "ok"
    assert rehearsal["live_data_replaced"] is False
