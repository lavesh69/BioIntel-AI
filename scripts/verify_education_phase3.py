from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from biointel.education.examination import SecureExaminationService
from biointel.education.permissions import PermissionService
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
    with tempfile.TemporaryDirectory(prefix="biointel-phase3-") as tmp:
        tmp_root = Path(tmp)
        platform = EducationPlatform(tmp_root / "education.db", tmp_root / "media")
        admin, teacher, student, outsider = "admin", "teacher", "student", "outsider"
        institution = platform.create_institution(admin, "Phase 3 Verification University")["id"]
        platform.add_member(admin, institution, teacher, "subject_teacher")
        platform.add_member(admin, institution, student, "university_student")
        subject = platform.create_subject(admin, institution, "BIO-301", "Molecular Biology")["id"]
        platform.assign_teacher(admin, institution, subject, teacher)
        platform.enroll(admin, institution, subject, student)
        permissions = PermissionService(platform)
        service = SecureExaminationService(platform)

        controls.append(("database-quick-check", platform.db.quick_check()))
        controls.append(("rbac-defaults", permissions.has(teacher, institution, "exam.create") and not permissions.has(teacher, institution, "exam.publish")))
        permissions.set_override(admin, institution, "subject_teacher", "exam.publish", "allow")
        controls.append(("rbac-tenant-override", permissions.has(teacher, institution, "exam.publish")))

        start = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        exam = service.create_exam(teacher, institution, subject, "Secure Verification Exam", 10, start, end, duration_minutes=30, attempts_allowed=1, access_code="VERIFY")
        q1 = service.add_question(teacher, exam["id"], "single_choice", "DNA base?", 5, options=["A", "B", "C"], correct_answer="A", negative_marks=1)
        q2 = service.add_question(teacher, exam["id"], "short_text", "Central dogma starts with?", 5, correct_answer="DNA")
        service.publish_exam(teacher, exam["id"])
        controls.append(("blueprint-publication", service._exam(exam["id"])["state"] == "published"))
        controls.append(("access-code-rejection", expect_error(Denied, lambda: service.start_exam(student, exam["id"], access_code="WRONG"))))
        session = service.start_exam(student, exam["id"], access_code="VERIFY")
        controls.append(("server-authoritative-timer", int(session["remaining_seconds"]) > 0))
        first = service.save_answer(student, session["id"], q1["id"], "B")
        second = service.save_answer(student, session["id"], q1["id"], "A")
        service.save_answer(student, session["id"], q2["id"], "dna")
        controls.append(("answer-version-history", first["version"] == 1 and second["version"] == 2))
        controls.append(("session-ownership", expect_error(Denied, lambda: service.session_view(outsider, session["id"]))))
        score = service.submit_exam(student, session["id"])
        controls.append(("objective-scoring", score["grading_state"] == "completed" and float(score["final_score"]) == 10.0))
        controls.append(("sealed-submission", expect_error(Conflict, lambda: service.save_answer(student, session["id"], q1["id"], "C"))))
        controls.append(("attempt-limit", expect_error(Conflict, lambda: service.start_exam(student, exam["id"], access_code="VERIFY"))))
        service.publish_scores(admin, exam["id"])
        result = platform._one("SELECT published,locked FROM results WHERE examination_id=? AND student_id=?", (exam["id"], student)) or {}
        controls.append(("locked-result-publication", result.get("published") == 1 and result.get("locked") == 1))

    required = [
        root / "pages/339_BioIntel_Education_Home.py",
        root / "pages/344_BioIntel_Examination_Command_Center.py",
        root / "src/biointel/education/experience.py",
        root / "src/biointel/education/examination_ui.py",
    ]
    controls.append(("education-app-pages", all(path.is_file() for path in required)))
    css = (root / "src/biointel/education/experience.py").read_text(encoding="utf-8")
    controls.append(("responsive-design-system", "@media (max-width: 700px)" in css and "edu-app-hero" in css and "edu-card-grid" in css))
    navigation = (root / "src/biointel/ui/navigation.py").read_text(encoding="utf-8")
    controls.append(("primary-navigation", "biointel_education_home" in navigation and "biointel_examinations" in navigation))

    failed = [name for name, passed in controls if not passed]
    print(f"Education Phase 3 verification {'passed' if not failed else 'failed'}: {len(controls) - len(failed)}/{len(controls)} controls")
    for name, passed in controls:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
