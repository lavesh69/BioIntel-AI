from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from biointel.education.examination import SecureExaminationService
from biointel.education.phase4 import EducationPhase4Service
from biointel.education.platform import Conflict, Denied, EducationPlatform


def expect_error(kind, fn) -> bool:
    try:
        fn()
    except kind:
        return True
    return False


def main() -> int:
    controls: list[tuple[str, bool]] = []
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="biointel-phase4-") as tmp:
        tmp_root = Path(tmp)
        platform = EducationPlatform(tmp_root / "education.db", tmp_root / "media")
        admin, teacher, student, guardian = "admin", "teacher", "student", "guardian"
        institution = platform.create_institution(admin, "Phase 4 Verification University")["id"]
        platform.add_member(admin, institution, teacher, "subject_teacher")
        platform.add_member(admin, institution, student, "university_student")
        platform.add_member(admin, institution, guardian, "parent_guardian")
        subject = platform.create_subject(admin, institution, "BIO-401", "Genomics")["id"]
        platform.assign_teacher(admin, institution, subject, teacher)
        platform.enroll(admin, institution, subject, student)
        service = EducationPhase4Service(platform, root=tmp_root, shiro_data_dir=tmp_root / "shiro")

        controls.append(("database-quick-check", platform.db.quick_check()))
        controls.append(("phase4-permissions", service.permissions.has(teacher, institution, "learning.manage") and service.permissions.has(student, institution, "shiro.tutor")))

        concept = service.create_concept(teacher, institution, subject, "DNA-01", "DNA structure", difficulty="foundation")
        low = service.record_mastery_evidence(student, institution, student, concept["id"], 0.4, evidence_type="self_check", weight=0.5)
        high = service.record_mastery_evidence(teacher, institution, student, concept["id"], 0.9, evidence_type="quiz", weight=2)
        controls.append(("knowledge-graph", concept["code"] == "DNA-01"))
        controls.append(("recency-weighted-mastery", float(high["state"]["mastery"]) > float(low["state"]["mastery"])))
        controls.append(("student-evidence-boundary", expect_error(Denied, lambda: service.record_mastery_evidence(student, institution, student, concept["id"], 1, evidence_type="examination"))))
        snapshot = service.learner_snapshot(student, institution, student, subject)
        controls.append(("spaced-review-recommendation", bool(snapshot["recommendations"]) and bool(snapshot["concepts"][0]["next_review_at"])))

        start = datetime.now(timezone.utc) + timedelta(days=1)
        series = service.create_weekly_timetable(teacher, institution, subject, teacher, "BSC-A", "LAB-1", start.isoformat(), (start + timedelta(hours=1)).isoformat(), weeks=2)
        controls.append(("recurring-timetable", len(series["entry_ids"]) == 2))
        before = platform._one("SELECT COUNT(*) n FROM timetable_entries WHERE institution_id=?", (institution,))["n"]
        blocked = expect_error(Conflict, lambda: service.create_weekly_timetable(teacher, institution, subject, teacher, "BSC-B", "LAB-2", start.isoformat(), (start + timedelta(hours=1)).isoformat(), weeks=2))
        after = platform._one("SELECT COUNT(*) n FROM timetable_entries WHERE institution_id=?", (institution,))["n"]
        controls.append(("conflict-atomicity", blocked and before == after))
        attendance = service.create_attendance_from_timetable(teacher, series["entry_ids"][0])
        service.bulk_mark_attendance(teacher, attendance["id"], {student: "absent"})
        alerts = service.attendance_shortage_alerts(teacher, institution)
        controls.append(("attendance-shortage-alert", len(alerts) == 1 and alerts[0]["student_id"] == student))

        first = service.emit_notification(admin, institution, student, "general", "Welcome", "Workspace ready", dedupe_key="welcome")
        second = service.emit_notification(admin, institution, student, "general", "Duplicate", "Should dedupe", dedupe_key="welcome")
        controls.append(("notification-deduplication", first["id"] == second["id"]))
        controls.append(("notification-ownership", expect_error(Denied, lambda: service.mark_notification_read(guardian, first["id"]))))
        service.save_notification_preference(student, institution, event_type="assignment_due", enabled=False)
        controls.append(("notification-preference", bool(service.emit_notification(admin, institution, student, "assignment_due", "Due", "Soon").get("suppressed"))))

        indexed = service.index_subject_text(teacher, institution, subject, "Genomics notes", "DNA stores hereditary information. A gene is a functional sequence of DNA. Variants are nucleotide changes.")
        response = service.ask_tutor(student, institution, subject, "What is a gene?", response_language="English")
        controls.append(("local-course-index", indexed["chunks_indexed"] >= 1))
        controls.append(("citation-grounded-tutor", response["evidence_status"] == "grounded" and bool(response["citations"])))

        exams = SecureExaminationService(platform)
        exam = exams.create_exam(teacher, institution, subject, "Integrity exam", 5, (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), duration_minutes=20)
        exams.add_question(teacher, exam["id"], "true_false", "Genes are made of DNA.", 5, correct_answer="True")
        exams.publish_exam(admin, exam["id"])
        exams.start_exam(student, exam["id"])
        controls.append(("active-exam-tutor-lock", expect_error(Conflict, lambda: service.ask_tutor(student, institution, subject, "Answer the exam"))))

        report = service.learner_progress_report(student, institution, student)
        controls.append(("governed-progress-report", report["student_id"] == student and report["governance"]["human_review_required"]))

    required = [
        root / "pages/345_BioIntel_Education_Intelligence_Hub.py",
        root / "src/biointel/education/phase4.py",
        root / "src/biointel/education/intelligence_ui.py",
        root / "src/biointel/education/_streamlit_compat.py",
    ]
    controls.append(("phase4-app-files", all(path.is_file() for path in required)))
    css = (root / "src/biointel/education/experience.py").read_text(encoding="utf-8")
    controls.append(("phase4-responsive-design", "edu-module-card" in css and "edu-split-grid" in css and "@media (max-width: 700px)" in css))
    navigation = (root / "src/biointel/ui/navigation.py").read_text(encoding="utf-8")
    controls.append(("phase4-primary-navigation", "biointel_intelligence_hub" in navigation))
    api = (root / "src/biointel/education/api.py").read_text(encoding="utf-8")
    controls.append(("phase4-typed-api", "class TutorQuestionData" in api and "/tutor/chat" in api and "class ConceptData" in api))

    failed = [name for name, passed in controls if not passed]
    print(f"Education Phase 4 verification {'passed' if not failed else 'failed'}: {len(controls) - len(failed)}/{len(controls)} controls")
    for name, passed in controls:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
