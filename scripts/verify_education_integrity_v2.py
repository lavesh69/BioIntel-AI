"""Dependency-light verification for Education Phase 2 integrity controls."""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from biointel.education.module_engines import EducationModuleEngines
from biointel.education.platform import Conflict, Denied, EducationPlatform
from biointel.education.universe import EducationUniverse
from biointel.ui.dragon_universe.theme_manager import DRAGON_PALETTE, generate_dragon_universe_css


def expect(error: type[Exception], operation, label: str) -> None:
    try:
        operation()
    except error:
        return
    raise AssertionError(f"Expected {error.__name__}: {label}")


def main() -> int:
    checks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="biointel-education-v2-") as temporary:
        root = Path(temporary)
        platform = EducationPlatform(root / "education.db", root / "media")
        admin, teacher, student, guardian, outsider = "admin", "teacher", "student", "guardian", "outsider"
        institution = platform.create_institution(admin, "Verification University")["id"]
        for user, role in ((teacher, "subject_teacher"), (student, "university_student"), (guardian, "parent_guardian")):
            platform.add_member(admin, institution, user, role)
        subject = platform.create_subject(admin, institution, "BIO-V2", "Integrity Biology")["id"]
        platform.assign_teacher(admin, institution, subject, teacher)
        platform.enroll(admin, institution, subject, student)

        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        expired = platform.create_assignment(teacher, institution, subject, "Expired", "Answer", past, 10, late_policy="reject")
        expect(Conflict, lambda: platform.submit_assignment(student, expired["id"], "late"), "deadline enforcement")
        checks.append("deadline-policy")

        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        current = platform.create_assignment(teacher, institution, subject, "Current", "Answer", future, 10)
        submission = platform.submit_assignment(student, current["id"], "final answer")
        expect(Conflict, lambda: platform.submit_assignment(student, current["id"], "overwrite"), "immutable final")
        platform.grade_submission(teacher, submission["id"], 8, "Good")
        expect(Conflict, lambda: platform.grade_submission(teacher, submission["id"], 9, "Changed"), "grade reason")
        platform.grade_submission(teacher, submission["id"], 9, "Changed", "Rechecked rubric")
        assert platform._one("SELECT COUNT(*) n FROM grade_revisions")["n"] == 1
        checks.extend(("immutable-submission", "grade-history"))

        platform.add_guardian_link(admin, institution, guardian, student, True)
        expect(Denied, lambda: platform.student_attendance(guardian, institution, student), "guardian pending consent")
        platform.approve_guardian_link(student, institution, guardian)
        assert platform._guardian_can(guardian, institution, student)
        checks.append("student-consent")

        circular = platform.create_circular(admin, institution, "FAC-1", "Faculty", "Restricted", ["teachers"])
        platform.publish_circular(admin, circular["id"])
        expect(Denied, lambda: platform.acknowledge_circular(student, circular["id"]), "circular audience")
        checks.append("circular-audience")

        examination = platform.create_examination(teacher, institution, subject, "Exam", 100, "2030-01-01T09:00+00:00", "2030-01-01T12:00+00:00")
        result = platform.set_result(teacher, examination["id"], student, 80, "A")
        platform.publish_results(admin, examination["id"])
        expect(Conflict, lambda: platform.set_result(teacher, examination["id"], student, 90, "A+"), "result lock")
        platform.unlock_result(admin, result["id"], "Approved correction")
        platform.set_result(teacher, examination["id"], student, 90, "A+", "Recalculated total")
        assert platform._one("SELECT COUNT(*) n FROM result_revisions")["n"] == 1
        checks.append("result-revisions")

        platform.create_institution(outsider, "Other Institution")
        source = platform.add_pulse_source(admin, "Crossref", "publication_api", "https://api.crossref.org", False, institution)
        expect(Denied, lambda: platform.sync_pulse_source(outsider, source["id"]), "Pulse tenant isolation")
        checks.append("tenant-isolation")

        platform.create_educator(teacher, institution, "Educator", verified=True)
        assert not platform._one("SELECT verified FROM educator_profiles WHERE user_id=?", (teacher,))["verified"]
        platform.verify_educator(admin, institution, teacher)
        checks.append("educator-verification")

        engines = EducationModuleEngines(platform)
        assert engines.bioinformatics_sandbox(student, institution, "fasta_stats", "ACGTGC")["result"]["gc_percent"] > 0
        assert engines.virtual_lab(student, institution, "enzyme_kinetics", {"substrate": 2, "vmax": 1, "km": 0.5})["simulation_only"]
        assert engines.assessment_blueprint(teacher, institution, subject, ["Explain", "Apply"], 100)["review_required"]
        checks.append("bounded-live-engines")

        universe = EducationUniverse(platform)
        universe.create_record(teacher, institution, "question_bank", "question", "Protected", {"subject": "BIO-V2", "learning_outcome": "Explain", "review_status": "draft"})
        dashboard = universe.dashboard(student, institution)
        assert all(row["module_key"] != "question_bank" for row in dashboard["stored_counts"])
        checks.append("restricted-aggregate-privacy")

        css = generate_dragon_universe_css()
        assert DRAGON_PALETTE["electric_cyan"] == "#00D9FF" and "bio-dragon-divider" in css and "glassmorphism" in css
        checks.append("dragon-theme")

        assert platform.db.quick_check()
        checks.append("database-quick-check")

    print(f"Education Phase 2 integrity verification passed: {len(checks)} controls")
    for item in checks:
        print(f"  [PASS] {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
