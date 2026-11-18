from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from biointel.education.examination import SecureExaminationService
from biointel.education.phase4 import EducationPhase4Service
from biointel.education.platform import Conflict, Denied, EducationPlatform


@pytest.fixture()
def phase4():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        platform = EducationPlatform(root / "education.db", root / "media")
        admin, teacher, student, guardian = "admin", "teacher", "student", "guardian"
        institution = platform.create_institution(admin, "Phase 4 University")["id"]
        platform.add_member(admin, institution, teacher, "subject_teacher")
        platform.add_member(admin, institution, student, "university_student")
        platform.add_member(admin, institution, guardian, "parent_guardian")
        subject = platform.create_subject(admin, institution, "BIO-401", "Genomics")["id"]
        platform.assign_teacher(admin, institution, subject, teacher)
        platform.enroll(admin, institution, subject, student)
        service = EducationPhase4Service(platform, root=root, shiro_data_dir=root / "shiro")
        yield root, platform, service, admin, teacher, student, guardian, institution, subject


def test_mastery_knowledge_graph_and_recommendations(phase4):
    _, _, service, _, teacher, student, _, institution, subject = phase4
    foundation = service.create_concept(teacher, institution, subject, "DNA-01", "DNA structure", difficulty="foundation")
    advanced = service.create_concept(teacher, institution, subject, "VAR-01", "Variant interpretation", prerequisites=[foundation["id"]], difficulty="advanced")
    first = service.record_mastery_evidence(student, institution, student, foundation["id"], 0.4, evidence_type="practice")
    assert 0.39 <= first["state"]["mastery"] <= 0.41
    second = service.record_mastery_evidence(teacher, institution, student, foundation["id"], 0.9, evidence_type="quiz", weight=2)
    assert second["state"]["mastery"] > first["state"]["mastery"]
    snapshot = service.learner_snapshot(student, institution, student, subject)
    assert len(snapshot["concepts"]) == 2
    assert snapshot["recommendations"]
    assert advanced["id"] in snapshot["concepts"][1]["concept_id"]
    with pytest.raises(Denied):
        service.record_mastery_evidence(student, institution, student, foundation["id"], 1, evidence_type="examination")


def test_recurring_timetable_is_atomic_and_detects_all_conflicts(phase4):
    _, platform, service, _, teacher, _, _, institution, subject = phase4
    start = datetime.now(timezone.utc) + timedelta(days=2)
    end = start + timedelta(hours=1)
    created = service.create_weekly_timetable(teacher, institution, subject, teacher, "BSC-A", "LAB-1", start.isoformat(), end.isoformat(), weeks=3)
    assert created["occurrence_count"] == 3
    assert platform._one("SELECT COUNT(*) n FROM timetable_entries WHERE institution_id=?", (institution,))["n"] == 3
    with pytest.raises(Conflict):
        service.create_weekly_timetable(teacher, institution, subject, teacher, "BSC-B", "LAB-2", start.isoformat(), end.isoformat(), weeks=2)
    assert platform._one("SELECT COUNT(*) n FROM timetable_entries WHERE institution_id=?", (institution,))["n"] == 3


def test_attendance_automation_and_shortage_alerts(phase4):
    _, platform, service, _, teacher, student, _, institution, subject = phase4
    start = datetime.now(timezone.utc) + timedelta(days=1)
    series = service.create_weekly_timetable(teacher, institution, subject, teacher, "BSC-A", "LAB-1", start.isoformat(), (start + timedelta(hours=1)).isoformat(), weeks=1)
    session = service.create_attendance_from_timetable(teacher, series["entry_ids"][0])
    saved = service.bulk_mark_attendance(teacher, session["id"], {student: "absent"})
    assert saved["saved"] == 1
    alerts = service.attendance_shortage_alerts(teacher, institution, threshold=0.75)
    assert len(alerts) == 1 and alerts[0]["student_id"] == student
    assert platform._one("SELECT COUNT(*) n FROM education_attendance_alerts WHERE state='open'")["n"] == 1


def test_notification_preferences_dedupe_and_recipient_ownership(phase4):
    _, _, service, admin, _, student, guardian, institution, _ = phase4
    first = service.emit_notification(admin, institution, student, "general", "Welcome", "Education workspace is ready.", dedupe_key="welcome:student")
    second = service.emit_notification(admin, institution, student, "general", "Welcome duplicate", "Should dedupe.", dedupe_key="welcome:student")
    assert first["id"] == second["id"]
    assert len(service.notification_inbox(student, institution, unread_only=True)) == 1
    with pytest.raises(Denied):
        service.mark_notification_read(guardian, first["id"])
    assert service.mark_notification_read(student, first["id"])["state"] == "read"
    service.save_notification_preference(student, institution, event_type="assignment_due", enabled=False)
    suppressed = service.emit_notification(admin, institution, student, "assignment_due", "Due", "Soon")
    assert suppressed["suppressed"] is True


def test_shiro_tutor_is_grounded_and_locked_during_active_exam(phase4):
    _, platform, service, admin, teacher, student, _, institution, subject = phase4
    indexed = service.index_subject_text(teacher, institution, subject, "Genomics notes", "DNA stores hereditary information. A gene is a functional sequence of DNA. Variants are changes in nucleotide sequence.")
    assert indexed["chunks_indexed"] >= 1
    answer = service.ask_tutor(student, institution, subject, "What is a gene?", response_language="English")
    assert answer["evidence_status"] == "grounded"
    assert answer["citations"]
    exam_service = SecureExaminationService(platform)
    start = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    exam = exam_service.create_exam(teacher, institution, subject, "Genomics Test", 5, start, end, duration_minutes=20)
    exam_service.add_question(teacher, exam["id"], "true_false", "Genes are made of DNA.", 5, correct_answer="True")
    exam_service.publish_exam(admin, exam["id"])
    exam_service.start_exam(student, exam["id"])
    with pytest.raises(Conflict):
        service.ask_tutor(student, institution, subject, "Give me the answer to the exam question")


def test_unified_learner_progress_report(phase4):
    _, _, service, _, teacher, student, guardian, institution, subject = phase4
    concept = service.create_concept(teacher, institution, subject, "GENE-01", "Gene basics")
    service.record_mastery_evidence(teacher, institution, student, concept["id"], 0.8, evidence_type="teacher_observation")
    report = service.learner_progress_report(student, institution, student)
    assert report["student_id"] == student
    assert report["summary"]["average_concept_mastery"] > 0
    with pytest.raises(Denied):
        service.learner_progress_report(guardian, institution, student)


def test_phase4_intelligence_ui_smoke(phase4, monkeypatch):
    root, platform, _, _, _, student, _, institution, _ = phase4
    import biointel.education.intelligence_ui as ui

    monkeypatch.setattr(ui, "_platform", lambda _root: platform)
    monkeypatch.setattr(ui, "_production_only_context", lambda *_args: True)
    monkeypatch.setattr(ui, "_identity_input", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ui, "_institution", lambda _platform: institution)
    monkeypatch.setattr(ui, "_actor", lambda: student)
    ui.render_education_intelligence_hub(root)
    assert (root.parent / "unused").exists() is False
