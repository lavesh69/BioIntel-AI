from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from biointel.education.examination import SecureExaminationService
from biointel.education.permissions import PermissionService
from biointel.education.platform import Conflict, Denied, EducationPlatform


@pytest.fixture()
def phase3():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        platform = EducationPlatform(root / "education.db", root / "media")
        admin, teacher, student, outsider = "admin", "teacher", "student", "outsider"
        institution = platform.create_institution(admin, "Phase 3 University")["id"]
        platform.add_member(admin, institution, teacher, "subject_teacher")
        platform.add_member(admin, institution, student, "university_student")
        subject = platform.create_subject(admin, institution, "BIO-301", "Molecular Biology")["id"]
        platform.assign_teacher(admin, institution, subject, teacher)
        platform.enroll(admin, institution, subject, student)
        service = SecureExaminationService(platform)
        yield platform, service, admin, teacher, student, outsider, institution, subject


def _exam(service, teacher, institution, subject, *, max_marks=10, attempts=1):
    start = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    return service.create_exam(
        teacher, institution, subject, "Secure Assessment", max_marks, start, end,
        duration_minutes=30, attempts_allowed=attempts, access_code="BIO-ACCESS",
    )


def test_granular_permission_override_has_deny_precedence(phase3):
    platform, _, admin, teacher, *_rest, institution, _subject = phase3
    permissions = PermissionService(platform)
    assert permissions.has(teacher, institution, "exam.create")
    assert not permissions.has(teacher, institution, "exam.publish")
    permissions.set_override(admin, institution, "subject_teacher", "exam.publish", "allow")
    assert permissions.has(teacher, institution, "exam.publish")
    permissions.set_override(admin, institution, "subject_teacher", "exam.publish", "deny")
    assert not permissions.has(teacher, institution, "exam.publish")


def test_secure_exam_randomized_attempt_autosave_and_scoring(phase3):
    platform, service, admin, teacher, student, _, institution, subject = phase3
    exam = _exam(service, teacher, institution, subject)
    q1 = service.add_question(teacher, exam["id"], "single_choice", "DNA base?", 5, options=["A", "B", "C"], correct_answer="A", negative_marks=1)
    q2 = service.add_question(teacher, exam["id"], "short_text", "Central dogma starts with?", 5, correct_answer="DNA")
    service.publish_exam(admin, exam["id"])
    session = service.start_exam(student, exam["id"], access_code="BIO-ACCESS")
    assert session["remaining_seconds"] > 0
    first = service.save_answer(student, session["id"], q1["id"], "B")
    second = service.save_answer(student, session["id"], q1["id"], "A")
    service.save_answer(student, session["id"], q2["id"], "dna")
    assert first["version"] == 1 and second["version"] == 2
    assert platform._one("SELECT COUNT(*) n FROM education_exam_answer_versions WHERE session_id=?", (session["id"],))["n"] == 3
    score = service.submit_exam(student, session["id"])
    assert score["grading_state"] == "completed"
    assert score["final_score"] == pytest.approx(10.0)
    with pytest.raises(Conflict):
        service.save_answer(student, session["id"], q1["id"], "C")
    with pytest.raises(Conflict):
        service.start_exam(student, exam["id"], access_code="BIO-ACCESS")


def test_access_code_tenant_ownership_and_locked_publication(phase3):
    platform, service, admin, teacher, student, outsider, institution, subject = phase3
    exam = _exam(service, teacher, institution, subject, max_marks=4)
    question = service.add_question(teacher, exam["id"], "true_false", "DNA is genetic material.", 4, correct_answer="True")
    service.publish_exam(admin, exam["id"])
    with pytest.raises(Denied):
        service.start_exam(student, exam["id"], access_code="WRONG")
    session = service.start_exam(student, exam["id"], access_code="BIO-ACCESS")
    with pytest.raises(Denied):
        service.session_view(outsider, session["id"])
    service.save_answer(student, session["id"], question["id"], "True")
    service.record_event(student, session["id"], "focus_lost", {"count": 1})
    service.submit_exam(student, session["id"])
    published = service.publish_scores(admin, exam["id"])
    assert published["result_count"] == 1
    result = platform._one("SELECT * FROM results WHERE examination_id=? AND student_id=?", (exam["id"], student))
    assert result["published"] == 1 and result["locked"] == 1
    assert service.monitor(admin, exam["id"])["event_counts"][0]["event_type"] == "focus_lost"


def test_manual_grading_blocks_result_release(phase3):
    platform, service, admin, teacher, student, _, institution, subject = phase3
    exam = _exam(service, teacher, institution, subject, max_marks=6)
    question = service.add_question(teacher, exam["id"], "long_answer", "Explain transcription.", 6)
    service.publish_exam(admin, exam["id"])
    session = service.start_exam(student, exam["id"], access_code="BIO-ACCESS")
    service.save_answer(student, session["id"], question["id"], "RNA polymerase synthesizes RNA from DNA.")
    score = service.submit_exam(student, session["id"])
    assert score["grading_state"] == "pending_manual"
    with pytest.raises(Conflict):
        service.publish_scores(admin, exam["id"])
    score = service.grade_manual_answer(teacher, session["id"], question["id"], 5, "Clear answer")
    assert score["grading_state"] == "completed" and score["final_score"] == 5
    service.publish_scores(admin, exam["id"])
    assert platform._one("SELECT locked FROM results WHERE examination_id=?", (exam["id"],))["locked"] == 1
