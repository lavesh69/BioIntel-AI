from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.phase14 import EducationPhase14Service  # noqa: E402
from biointel.education.platform import Denied, EducationPlatform  # noqa: E402


class Verifier:
    def __init__(self) -> None:
        self.controls: list[dict[str, Any]] = []

    def require(self, name: str, condition: bool, detail: Any = None) -> None:
        if not condition:
            raise AssertionError(f"{name} failed: {detail}")
        self.controls.append({"name": name, "passed": True, "detail": detail})

    def check(self, name: str, fn: Callable[[], Any]) -> Any:
        try:
            detail = fn()
            self.controls.append({"name": name, "passed": True, "detail": detail})
            return detail
        except Exception as exc:
            self.controls.append({"name": name, "passed": False, "error": f"{type(exc).__name__}: {exc}"})
            return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify BioIntel Education Phase 14 academic intelligence")
    parser.add_argument("--output", default=str(ROOT / "EDUCATION_PHASE14_VERIFICATION.json"))
    args = parser.parse_args()
    verifier = Verifier()

    with tempfile.TemporaryDirectory(prefix="biointel-phase14-verify-") as temp:
        root = Path(temp)
        platform = EducationPlatform(root / "education.sqlite3", root / "media")
        admin, teacher, reviewer = "admin", "teacher", "reviewer"
        students = [f"student-{index}" for index in range(1, 6)]
        institution = platform.create_institution(admin, "Phase 14 Verification University")["id"]
        platform.add_member(admin, institution, teacher, "subject_teacher")
        platform.add_member(admin, institution, reviewer, "department_head")
        for student in students:
            platform.add_member(admin, institution, student, "university_student")
        unit = platform.create_unit(admin, institution, "School of Bioscience", "school")
        subject = platform.create_subject(admin, institution, "BIO-P14", "Academic Intelligence Biology", unit["id"])
        platform.assign_teacher(admin, institution, subject["id"], teacher)
        platform.assign_teacher(admin, institution, subject["id"], reviewer)
        for student in students:
            platform.enroll(admin, institution, subject["id"], student)
        service = EducationPhase14Service(platform, root=root)

        required_tables = {
            "education_learning_outcomes", "education_outcome_relationships",
            "education_outcome_assessment_mappings", "education_outcome_evidence",
            "education_outcome_attainment_runs", "education_quality_cycles",
            "education_improvement_actions", "education_psychometric_runs",
            "education_question_statistics", "education_student_success_snapshots",
            "education_intervention_cases", "education_calendar_details",
            "education_calendar_exports",
        }
        tables = {row["name"] for row in platform._all("SELECT name FROM sqlite_master WHERE type='table'")}
        verifier.require("phase14_schema", required_tables <= tables, sorted(required_tables - tables))

        course = service.create_learning_outcome(teacher, institution, code="CO1", title="Explain molecular inheritance", subject_id=subject["id"], bloom_level="understand", target_percent=65)
        program = service.create_learning_outcome(admin, institution, code="PO1", title="Apply evidence-led biological reasoning", outcome_level="program", unit_id=unit["id"], bloom_level="apply")
        verifier.require("outcome_levels", course["outcome_level"] == "course" and program["outcome_level"] == "program")
        relation = service.map_outcome_relationship(teacher, course["id"], program["id"], strength=3, rationale="Course supports program reasoning")
        verifier.require("outcome_relationship", relation["strength"] == 3)
        cross_tenant = platform.create_institution("other-admin", "Other University")["id"]
        other_outcome = service.create_learning_outcome("other-admin", cross_tenant, code="OTHER", title="Other outcome", outcome_level="institution")
        denied = False
        try:
            service.map_outcome_relationship(teacher, course["id"], other_outcome["id"])
        except Denied:
            denied = True
        verifier.require("outcome_tenant_isolation", denied)

        due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        assignment = platform.create_assignment(teacher, institution, subject["id"], "Inheritance evidence", "Explain with evidence", due, 10, publish=True)
        for index, student in enumerate(students[:3]):
            submission = platform.submit_assignment(student, assignment["id"], body="Evidence response", final=True)
            platform.grade_submission(teacher, submission["id"], 6 + index, "Reviewed")
        mapping = service.map_assessment_to_outcome(teacher, course["id"], assessment_type="assignment", assessment_id=assignment["id"], weight=1)
        verifier.require("assessment_mapping", mapping["assessment_type"] == "assignment")
        evidence = service.submit_outcome_evidence(teacher, course["id"], evidence_type="assessment", title="Assignment result evidence", target_type="assignment", target_id=assignment["id"])
        verifier.require("evidence_pending_review", evidence["review_decision"] == "pending")
        reviewed = service.review_outcome_evidence(reviewer, evidence["id"], decision="approve", note="Verified against released grades")
        verifier.require("independent_evidence_review", reviewed["review_decision"] == "approve" and reviewed["reviewed_by"] == reviewer)
        attainment = service.calculate_outcome_attainment(teacher, course["id"])
        verifier.require("bounded_attainment", round(float(attainment["attainment_percent"]), 2) == 70.0 and attainment["detail"]["no_accreditation_claim"] is True, attainment)
        matrix = service.accreditation_evidence_matrix(reviewer, institution, subject_id=subject["id"])
        verifier.require("evidence_matrix", matrix["summary"]["mapped"] == 1 and matrix["summary"]["with_approved_evidence"] == 1, matrix["summary"])
        verifier.require("no_accreditation_claim", "does not claim external accreditation" in matrix["qualification_statement"].lower())

        cycle = service.create_quality_cycle(admin, institution, title="Annual quality cycle", period_start="2026-01-01T00:00:00+00:00", period_end="2026-12-31T23:59:59+00:00")
        action = service.create_improvement_action(admin, cycle["id"], title="Improve assessment evidence", rationale="One outcome lacks multiple evidence sources", owner_id=teacher, outcome_id=course["id"], due_at="2026-12-01T00:00:00+00:00", priority="high")
        completed = service.update_improvement_action(teacher, action["id"], state="completed", completion_evidence="Updated mapping and review minutes")
        verifier.require("quality_improvement_evidence", completed["state"] == "completed" and bool(completed["completion_evidence"]))

        start = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        exam = service.exams.create_exam(teacher, institution, subject["id"], "Psychometric biology test", 2, start, end, duration_minutes=60, shuffle_questions=False, shuffle_options=False)
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
        verifier.require("psychometric_sessions", psych["session_count"] == 5 and psych["question_count"] == 2)
        verifier.require("psychometric_question_metrics", all(row["difficulty_index"] is not None and "flags" in row for row in psych["questions"]), psych["questions"])
        verifier.require("psychometric_human_review", psych["detail"]["human_review_required"] is True and psych["detail"]["not_for_automatic_student_decisions"] is True)
        fetched = service.psychometric_run(teacher, psych["id"])
        verifier.require("psychometric_persistence", len(fetched["questions"]) == 2)

        session = platform.attendance_session(teacher, institution, subject["id"], date.today().isoformat(), "P1")
        platform.mark_attendance(teacher, session["id"], students[0], "absent")
        snapshot = service.calculate_student_success_snapshot(teacher, institution, students[0], subject["id"])
        verifier.require("support_transparency", snapshot["explanation"]["human_review_required"] is True and snapshot["explanation"]["no_automatic_penalty"] is True)
        verifier.require("support_sensitive_attributes_excluded", "health" in snapshot["explanation"]["excluded_inputs"] and "race" in snapshot["explanation"]["excluded_inputs"])
        intervention = service.create_intervention_case(teacher, snapshot["id"], reason="Attendance support", action_plan="Meet learner and agree recovery steps", assigned_to=teacher, priority="medium")
        verifier.require("human_intervention_plan", intervention["state"] == "open" and bool(intervention["action_plan"]))
        closed = service.update_intervention_case(teacher, intervention["id"], state="completed", review_note="Support review completed")
        verifier.require("intervention_lifecycle", closed["state"] == "completed" and bool(closed["closed_at"]))

        event = service.create_calendar_event(teacher, institution, title="Bioinformatics seminar", event_type="seminar", starts_at="2026-08-10T10:00:00+00:00", ends_at="2026-08-10T11:00:00+00:00", location="Auditorium", audience={"roles": ["university_student"]})
        verifier.require("calendar_event", event["location"] == "Auditorium" and event["audience"]["roles"] == ["university_student"])
        service.create_calendar_event(teacher, institution, title="Private admin review", event_type="governance", starts_at="2026-08-11T10:00:00+00:00", ends_at="2026-08-11T11:00:00+00:00", audience={"roles": ["institution_administrator"]})
        calendar = service.academic_calendar(students[0], institution, start_at="2026-08-01T00:00:00+00:00", end_at="2026-09-01T00:00:00+00:00")
        verifier.require("calendar_audience_enforcement", calendar["event_count"] == 1 and calendar["events"][0]["title"] == "Bioinformatics seminar", calendar)
        export = service.export_calendar_ics(teacher, institution, start_at="2026-08-01T00:00:00+00:00", end_at="2026-09-01T00:00:00+00:00")
        export_path = Path(export["output_path"])
        verifier.require("ics_export", export_path.is_file() and "BEGIN:VEVENT" in export_path.read_text(encoding="utf-8"))
        verifier.require("ics_sha256", hashlib.sha256(export_path.read_bytes()).hexdigest() == export["sha256"])

        posture = service.phase14_posture(admin, institution)
        verifier.require("phase14_honest_posture", posture["local_control_coverage_percent"] == 100.0 and len(posture["qualification_boundaries"]) >= 4, posture)
        verifier.require("phase14_page", (ROOT / "pages" / "352_BioIntel_Academic_Quality_and_Intelligence_Center.py").is_file())
        verifier.require("phase14_ui", (SRC / "biointel" / "education" / "phase14_ui.py").is_file())
        verifier.require("phase14_worker", (ROOT / "scripts" / "run_education_phase14_worker.py").is_file())
        verifier.require("phase14_navigation", "352_BioIntel_Academic_Quality_and_Intelligence_Center.py" in (SRC / "biointel" / "education" / "experience.py").read_text(encoding="utf-8"))
        api_text = (SRC / "biointel" / "education" / "api.py").read_text(encoding="utf-8")
        routes = [
            "phase14/outcomes", "phase14/evidence-matrix", "phase14/quality-cycles",
            "phase14/exams/{exam_id}/psychometrics", "phase14/success-snapshots",
            "phase14/calendar-events", "phase14/calendar-export", "phase14/posture",
        ]
        verifier.require("phase14_api_contract", all(route in api_text for route in routes), routes)

    passed = sum(1 for item in verifier.controls if item["passed"])
    report = {
        "schema": "biointel.education-phase14-verification.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed == len(verifier.controls),
        "passed_controls": passed,
        "total_controls": len(verifier.controls),
        "controls": verifier.controls,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "passed_controls", "total_controls")}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
