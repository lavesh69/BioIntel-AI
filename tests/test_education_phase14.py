from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from biointel.education.phase14 import EducationPhase14Service
from biointel.education.platform import EducationPlatform


def build(tmp_path: Path):
    platform = EducationPlatform(tmp_path / "education.sqlite3", tmp_path / "media")
    admin, teacher, reviewer = "admin", "teacher", "reviewer"
    students = ["student1", "student2", "student3", "student4", "student5"]
    institution = platform.create_institution(admin, "Phase 14 University")["id"]
    platform.add_member(admin, institution, teacher, "subject_teacher")
    platform.add_member(admin, institution, reviewer, "department_head")
    for student in students:
        platform.add_member(admin, institution, student, "university_student")
    unit = platform.create_unit(admin, institution, "Science", "school")
    subject = platform.create_subject(admin, institution, "BIO-1401", "Academic Intelligence", unit["id"])
    platform.assign_teacher(admin, institution, subject["id"], teacher)
    platform.assign_teacher(admin, institution, subject["id"], reviewer)
    for student in students:
        platform.enroll(admin, institution, subject["id"], student)
    service = EducationPhase14Service(platform, root=tmp_path)
    return platform, service, admin, teacher, reviewer, students, institution, unit, subject


def test_outcome_mapping_evidence_and_attainment(tmp_path: Path):
    platform, service, admin, teacher, reviewer, students, institution, unit, subject = build(tmp_path)
    course = service.create_learning_outcome(teacher, institution, code="CO1", title="Explain inheritance", subject_id=subject["id"], bloom_level="understand")
    program = service.create_learning_outcome(admin, institution, code="PO1", title="Apply biological reasoning", outcome_level="program", unit_id=unit["id"], bloom_level="apply")
    relation = service.map_outcome_relationship(teacher, course["id"], program["id"], strength=2, rationale="Course evidence supports program reasoning")
    assert relation["strength"] == 2

    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    assignment = platform.create_assignment(teacher, institution, subject["id"], "Inheritance evidence", "Explain", due, 10, publish=True)
    for index, student in enumerate(students[:3]):
        submission = platform.submit_assignment(student, assignment["id"], body="Evidence", final=True)
        platform.grade_submission(teacher, submission["id"], 6 + index, "Reviewed")
    service.map_assessment_to_outcome(teacher, course["id"], assessment_type="assignment", assessment_id=assignment["id"], weight=1)
    evidence = service.submit_outcome_evidence(teacher, course["id"], evidence_type="assessment", title="Assignment grades", target_type="assignment", target_id=assignment["id"])
    approved = service.review_outcome_evidence(reviewer, evidence["id"], decision="approve", note="Verified")
    assert approved["state"] == "approved"
    attainment = service.calculate_outcome_attainment(teacher, course["id"])
    assert round(float(attainment["attainment_percent"]), 2) == 70.0
    matrix = service.accreditation_evidence_matrix(reviewer, institution, subject_id=subject["id"])
    assert matrix["summary"]["mapped"] == 1
    assert matrix["summary"]["with_approved_evidence"] == 1


def test_psychometrics_and_transparent_student_support(tmp_path: Path):
    platform, service, admin, teacher, reviewer, students, institution, _, subject = build(tmp_path)
    start = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    exam = service.exams.create_exam(teacher, institution, subject["id"], "Biology test", 2, start, end, duration_minutes=60, shuffle_questions=False, shuffle_options=False)
    q1 = service.exams.add_question(teacher, exam["id"], "single_choice", "DNA base?", marks=1, options=["A", "B"], correct_answer="A")
    q2 = service.exams.add_question(teacher, exam["id"], "true_false", "DNA carries heredity", marks=1, options=["True", "False"], correct_answer="True")
    service.exams.publish_exam(admin, exam["id"])
    patterns = [("A", "True"), ("A", "True"), ("A", "False"), ("B", "True"), ("B", "False")]
    for student, answers in zip(students, patterns):
        session = service.exams.start_exam(student, exam["id"])
        service.exams.save_answer(student, session["id"], q1["id"], answers[0])
        service.exams.save_answer(student, session["id"], q2["id"], answers[1])
        service.exams.submit_exam(student, session["id"])
    psych = service.run_exam_psychometrics(teacher, exam["id"])
    assert psych["session_count"] == 5
    assert len(psych["questions"]) == 2
    assert all("difficulty_index" in row for row in psych["questions"])

    attendance = platform.attendance_session(teacher, institution, subject["id"], date.today().isoformat(), "P1")
    platform.mark_attendance(teacher, attendance["id"], students[0], "absent")
    snapshot = service.calculate_student_success_snapshot(teacher, institution, students[0], subject["id"])
    assert snapshot["risk_level"] in {"watch", "priority_support", "on_track", "insufficient_evidence"}
    assert snapshot["explanation"]["no_automatic_penalty"] is True
    case = service.create_intervention_case(teacher, snapshot["id"], reason="Attendance support", action_plan="Meet learner and agree a recovery plan", assigned_to=teacher)
    assert case["state"] == "open"
    closed = service.update_intervention_case(teacher, case["id"], state="completed", review_note="Plan completed")
    assert closed["state"] == "completed"


def test_quality_cycle_and_ics_export(tmp_path: Path):
    _, service, admin, teacher, _, _, institution, _, subject = build(tmp_path)
    cycle = service.create_quality_cycle(admin, institution, title="Annual quality review", period_start="2026-01-01T00:00:00+00:00", period_end="2026-12-31T23:59:59+00:00")
    action = service.create_improvement_action(admin, cycle["id"], title="Improve evidence coverage", rationale="Outcome evidence incomplete", owner_id=teacher, due_at="2026-12-01T00:00:00+00:00")
    completed = service.update_improvement_action(teacher, action["id"], state="completed", completion_evidence="Review minutes and updated mapping")
    assert completed["state"] == "completed"

    event = service.create_calendar_event(teacher, institution, title="Bioinformatics seminar", event_type="seminar", starts_at="2026-08-10T10:00:00+00:00", ends_at="2026-08-10T11:00:00+00:00", location="Auditorium", audience={"roles": ["university_student"]})
    assert event["location"] == "Auditorium"
    export = service.export_calendar_ics(teacher, institution, start_at="2026-08-01T00:00:00+00:00", end_at="2026-09-01T00:00:00+00:00")
    path = Path(export["output_path"])
    assert path.is_file()
    assert "BEGIN:VEVENT" in path.read_text(encoding="utf-8")
    posture = service.phase14_posture(admin, institution)
    assert posture["local_control_coverage_percent"] == 100.0
