from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from biointel.education.phase7 import EducationPhase7Service
from biointel.education.platform import Conflict, Denied, EducationPlatform


def build(tmp_path: Path):
    platform = EducationPlatform(tmp_path / "education.sqlite3", tmp_path / "media")
    admin, teacher, student = "admin", "teacher", "student"
    institution = platform.create_institution(admin, "Phase 7 Desktop University")["id"]
    platform.add_member(admin, institution, teacher, "subject_teacher")
    platform.add_member(admin, institution, student, "university_student")
    unit = platform.create_unit(admin, institution, "Science", "school")
    subject = platform.create_subject(admin, institution, "BIO-701", "Desktop Biology", unit["id"])
    platform.assign_teacher(admin, institution, subject["id"], teacher)
    platform.enroll(admin, institution, subject["id"], student)
    service = EducationPhase7Service(platform, root=tmp_path)
    return platform, service, admin, teacher, student, institution, subject


def test_desktop_identity_session_lockout_and_revoke(tmp_path: Path):
    _, service, admin, _, _, institution, _ = build(tmp_path)
    service.enroll_identity(admin, institution, admin, "Correct-Horse-7", display_name="Admin")
    with pytest.raises(Denied):
        service.authenticate(institution, admin, "wrong")
    signed = service.authenticate(institution, admin, "Correct-Horse-7", device_label="Test desktop")
    session = service.validate_session(signed["token"])
    assert session["user_id"] == admin
    service.revoke_session(admin, institution, session["id"])
    with pytest.raises(Denied):
        service.validate_session(signed["token"])


def test_timetable_edit_conflict_and_cancel(tmp_path: Path):
    platform, service, admin, teacher, _, institution, subject = build(tmp_path)
    start = datetime.now(timezone.utc) + timedelta(days=1)
    first = platform.create_timetable(admin, institution, subject["id"], teacher, "A", "R1", start.isoformat(), (start + timedelta(hours=1)).isoformat())
    second = platform.create_timetable(admin, institution, subject["id"], teacher, "B", "R2", (start + timedelta(hours=2)).isoformat(), (start + timedelta(hours=3)).isoformat())
    with pytest.raises(Conflict):
        service.update_timetable_entry(admin, institution, second["id"], starts_at=(start + timedelta(minutes=15)).isoformat(), ends_at=(start + timedelta(minutes=45)).isoformat(), teacher_id=teacher, student_group="B", room="R2")
    updated = service.update_timetable_entry(admin, institution, second["id"], starts_at=(start + timedelta(hours=3)).isoformat(), ends_at=(start + timedelta(hours=4)).isoformat(), teacher_id=teacher, student_group="B", room="R2")
    assert updated["starts_at"].startswith((start + timedelta(hours=3)).date().isoformat())
    cancelled = service.cancel_timetable_entry(admin, institution, first["id"], "Holiday")
    assert cancelled["state"] == "cancelled"


def test_bulk_attendance_and_gradebook(tmp_path: Path):
    platform, service, _, teacher, student, institution, subject = build(tmp_path)
    session = platform.attendance_session(teacher, institution, subject["id"], datetime.now(timezone.utc).date().isoformat(), "P1")
    saved = service.save_attendance_roster(teacher, session["id"], [{"student_id": student, "status": "late", "note": "Bus delay"}], lock=True)
    assert saved["session"]["state"] == "locked"
    assignment = platform.create_assignment(teacher, institution, subject["id"], "Desktop assessment", "Answer", (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(), 20)
    submission = platform.submit_assignment(student, assignment["id"], "Evidence", final=True)
    result = service.save_gradebook_rows(teacher, institution, [{"submission_id": submission["id"], "marks": 17, "feedback": "Strong"}])
    assert result["updated"] == 1
    result = service.save_gradebook_rows(teacher, institution, [{"submission_id": submission["id"], "marks": 18, "feedback": "Rechecked"}], reason="Moderation")
    assert result["updated"] == 1
    revisions = platform._all("SELECT * FROM grade_revisions WHERE submission_id=?", (submission["id"],))
    assert len(revisions) == 1


def test_curriculum_notebook_and_shiro_lifecycle(tmp_path: Path):
    platform, service, _, teacher, student, institution, subject = build(tmp_path)
    course = platform.create_course(teacher, institution, "Desktop Course", publish=True)
    section = service.create_course_section(teacher, course["id"], "Module 1", position=0)
    assert service.curriculum(teacher, course["id"])["sections"][0]["id"] == section["id"]
    # Direct lecture fixture keeps the test independent of ffprobe/media availability.
    stamp = datetime.now(timezone.utc).isoformat()
    lecture_id = "lecture-test"
    with platform.db.connection() as db:
        db.execute(
            "INSERT INTO lectures VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (lecture_id, institution, course["id"], teacher, "Lesson", "", "", "", 0, "video/mp4", 600, "ready", None, "published", stamp, stamp),
        )
    service.add_lecture_chapter(teacher, lecture_id, "Introduction", 0)
    service.save_lecture_note(student, lecture_id, "Key point", position_seconds=12)
    service.add_lecture_bookmark(student, lecture_id, 12, "Review")
    notebook = service.lecture_notebook(student, lecture_id)
    assert len(notebook["chapters"]) == len(notebook["notes"]) == len(notebook["bookmarks"]) == 1
    service.phase4.index_subject_text(teacher, institution, subject["id"], "Evidence", "DNA stores biological information.")
    conversation = service.create_conversation(student, institution, subject_id=subject["id"], title="DNA")
    renamed = service.rename_conversation(student, conversation["id"], "DNA revision")
    assert renamed["title"] == "DNA revision"
    assert service.archive_conversation(student, conversation["id"])["state"] == "archived"


def test_configurable_exam_passing_threshold_and_moderation(tmp_path: Path):
    _, service, admin, teacher, _, institution, subject = build(tmp_path)
    start = datetime.now(timezone.utc) + timedelta(minutes=5)
    exam = service.exams.create_exam(teacher, institution, subject["id"], "Policy exam", 10, start.isoformat(), (start + timedelta(hours=1)).isoformat(), duration_minutes=30)
    service.permissions.set_override(admin, institution, "subject_teacher", "exam.monitor", "allow")
    threshold = service.set_exam_passing_percent(teacher, exam["id"], 60)
    assert threshold["passing_percent"] == 60
    analytics = service.exam_analytics_phase7(teacher, exam["id"])
    assert analytics["summary"]["passing_percent"] == 60
    event = service.record_moderation_event(teacher, exam["id"], "review_started")
    assert event["event_type"] == "review_started"


def test_rubric_grading_and_searchable_transcript(tmp_path: Path):
    platform, service, _, teacher, student, institution, subject = build(tmp_path)
    assignment = platform.create_assignment(
        teacher,
        institution,
        subject["id"],
        "Rubric assessment",
        "Explain the evidence.",
        (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        20,
    )
    rubric = service.save_assignment_rubric(
        teacher,
        assignment["id"],
        "Evidence rubric",
        [
            {"title": "Scientific accuracy", "description": "Uses correct biology.", "max_marks": 12},
            {"title": "Evidence and clarity", "description": "Explains supporting evidence.", "max_marks": 8},
        ],
    )
    assert sum(float(item["max_marks"]) for item in rubric["criteria"]) == 20
    submission = platform.submit_assignment(student, assignment["id"], "DNA stores inherited information.", final=True)
    graded = service.grade_with_rubric(
        teacher,
        submission["id"],
        [
            {"criterion_id": rubric["criteria"][0]["id"], "marks": 10, "feedback": "Accurate."},
            {"criterion_id": rubric["criteria"][1]["id"], "marks": 7, "feedback": "Clear evidence."},
        ],
        overall_feedback="Strong response.",
    )
    assert graded["total_marks"] == 17
    assert len(platform._all("SELECT * FROM education_rubric_scores WHERE submission_id=?", (submission["id"],))) == 2

    course = platform.create_course(teacher, institution, "Transcript Course", publish=True)
    stamp = datetime.now(timezone.utc).isoformat()
    lecture_id = "lecture-transcript-test"
    with platform.db.connection() as db:
        db.execute(
            "INSERT INTO lectures VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (lecture_id, institution, course["id"], teacher, "DNA Evidence", "", "", "", 0, "video/mp4", 600, "ready", None, "published", stamp, stamp),
        )
    transcript = service.save_lecture_transcript(
        teacher,
        lecture_id,
        "DNA stores biological information. RNA helps express that information.",
        language="English",
    )
    assert transcript["language"] == "English"
    assert "RNA" in service.lecture_transcripts(student, lecture_id)[0]["body"]
