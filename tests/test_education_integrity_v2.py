from __future__ import annotations

import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from biointel.media_tools import ffmpeg_executable
from biointel.education.module_engines import EducationModuleEngines
from biointel.education.platform import Conflict, Denied, EducationPlatform
from biointel.education.universe import EducationUniverse


@pytest.fixture()
def ecosystem():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        p = EducationPlatform(root / "education.db", root / "media")
        admin, teacher, student, guardian = "admin", "teacher", "student", "guardian"
        inst = p.create_institution(admin, "Integrity University")["id"]
        for user, role in ((teacher, "subject_teacher"), (student, "university_student"), (guardian, "parent_guardian")):
            p.add_member(admin, inst, user, role)
        subject = p.create_subject(admin, inst, "BIO-1", "Biology")["id"]
        p.assign_teacher(admin, inst, subject, teacher)
        p.enroll(admin, inst, subject, student)
        yield root, p, admin, teacher, student, guardian, inst, subject


def test_deadline_final_immutability_and_grade_history(ecosystem):
    _, p, _, teacher, student, _, inst, subject = ecosystem
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assignment = p.create_assignment(teacher, inst, subject, "Past due", "Answer", past, 10, late_policy="reject")
    with pytest.raises(Conflict):
        p.submit_assignment(student, assignment["id"], "late")
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assignment = p.create_assignment(teacher, inst, subject, "Current", "Answer", future, 10)
    submission = p.submit_assignment(student, assignment["id"], "first")
    with pytest.raises(Conflict):
        p.submit_assignment(student, assignment["id"], "overwrite")
    p.grade_submission(teacher, submission["id"], 8, "Good")
    with pytest.raises(Conflict):
        p.grade_submission(teacher, submission["id"], 9, "Better")
    p.grade_submission(teacher, submission["id"], 9, "Better", "Rechecked rubric")
    assert p._one("SELECT COUNT(*) n FROM grade_revisions")["n"] == 1
    assert p._one("SELECT COUNT(*) n FROM submission_versions")["n"] == 1


def test_guardian_consent_circular_audience_and_result_lock(ecosystem):
    _, p, admin, teacher, student, guardian, inst, subject = ecosystem
    p.add_guardian_link(admin, inst, guardian, student, True)
    with pytest.raises(Denied):
        p.student_attendance(guardian, inst, student)
    p.approve_guardian_link(student, inst, guardian)
    assert p._guardian_can(guardian, inst, student)
    teacher_notice = p.create_circular(admin, inst, "T-1", "Faculty only", "Private", ["teachers"])
    p.publish_circular(admin, teacher_notice["id"])
    with pytest.raises(Denied):
        p.acknowledge_circular(student, teacher_notice["id"])
    exam = p.create_examination(teacher, inst, subject, "Exam", 100, "2030-01-01T09:00+00:00", "2030-01-01T12:00+00:00")
    result = p.set_result(teacher, exam["id"], student, 80, "A")
    p.publish_results(admin, exam["id"])
    with pytest.raises(Conflict):
        p.set_result(teacher, exam["id"], student, 90, "A+")
    p.unlock_result(admin, result["id"], "Approved correction")
    p.set_result(teacher, exam["id"], student, 90, "A+", "Recalculated total")
    assert p._one("SELECT COUNT(*) n FROM result_revisions")["n"] == 1


def test_tenant_source_certificate_and_real_engines(ecosystem):
    root, p, admin, teacher, student, _, inst, subject = ecosystem
    outsider = "outsider"
    other = p.create_institution(outsider, "Other")["id"]
    source = p.add_pulse_source(admin, "Crossref", "publication_api", "https://api.crossref.org", False, inst)
    with pytest.raises(Denied):
        p.sync_pulse_source(outsider, source["id"])
    p.create_educator(teacher, inst, "Educator", verified=True)
    assert not p._one("SELECT verified FROM educator_profiles WHERE user_id=?", (teacher,))["verified"]
    p.verify_educator(admin, inst, teacher)
    course = p.create_course(teacher, inst, "Course", publish=True)
    rights = p.confirm_rights(teacher, inst, "Teacher", "CC-BY-4.0")
    video = root / "valid.mp4"
    subprocess.run([ffmpeg_executable(), "-y", "-f", "lavfi", "-i", "color=c=black:s=160x120:d=1", "-pix_fmt", "yuv420p", str(video)], check=True, capture_output=True)
    lecture = p.upload_lecture(teacher, course["id"], "Lecture", video, rights["id"])
    p.enroll_course(student, course["id"])
    p.update_watch(student, lecture["id"], lecture["duration_seconds"], True)
    q1 = p.create_quiz(teacher, course["id"], "Q1", [{"prompt": "A", "answer": "a"}])
    p.create_quiz(teacher, course["id"], "Q2", [{"prompt": "B", "answer": "b"}])
    p.attempt_quiz(student, q1["id"], ["a"])
    with pytest.raises(Conflict):
        p.issue_certificate(teacher, course["id"], student)
    q2 = p._one("SELECT id FROM quizzes WHERE title='Q2'")
    p.attempt_quiz(student, q2["id"], ["b"])
    cert = p.issue_certificate(teacher, course["id"], student)
    assert p.verify_certificate(cert["verification_code"])["valid"]
    engines = EducationModuleEngines(p)
    assert engines.bioinformatics_sandbox(student, inst, "fasta_stats", "ACGTGC")["result"]["gc_percent"] > 0
    assert engines.virtual_lab(student, inst, "enzyme_kinetics", {"substrate": 2, "vmax": 1, "km": 0.5})["simulation_only"]
    assert engines.assessment_blueprint(teacher, inst, subject, ["Explain", "Apply"], 100)["review_required"]
    universe = EducationUniverse(p)
    question = universe.create_record(teacher, inst, "question_bank", "question", "Protected", {"subject":"BIO-1","learning_outcome":"Explain","review_status":"draft"})
    dashboard = universe.dashboard(student, inst)
    assert all(row["module_key"] != "question_bank" for row in dashboard["stored_counts"])
