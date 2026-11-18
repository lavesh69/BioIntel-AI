from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.phase11 import EducationPhase11Service, _totp  # noqa: E402
from biointel.education.platform import Denied, EducationPlatform  # noqa: E402


class Verifier:
    def __init__(self) -> None:
        self.controls: list[dict[str, Any]] = []

    def check(self, name: str, fn: Callable[[], Any]) -> Any:
        try:
            detail = fn()
            self.controls.append({"name": name, "passed": True, "detail": detail})
            return detail
        except Exception as exc:
            self.controls.append({"name": name, "passed": False, "error": f"{type(exc).__name__}: {exc}"})
            return None

    def require(self, name: str, condition: bool, detail: Any = None) -> None:
        if not condition:
            raise AssertionError(f"{name} failed: {detail}")
        self.controls.append({"name": name, "passed": True, "detail": detail})


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify BioIntel Education Phase 11 Mega Core")
    parser.add_argument("--output", default=str(ROOT / "EDUCATION_PHASE11_VERIFICATION.json"))
    args = parser.parse_args()
    verifier = Verifier()
    with tempfile.TemporaryDirectory(prefix="biointel-phase11-verify-") as temp:
        root = Path(temp)
        platform = EducationPlatform(root / "education.sqlite3", root / "media")
        admin, teacher, reviewer, student = "admin", "teacher", "reviewer", "student"
        institution = platform.create_institution(admin, "Phase 11 Verification University")["id"]
        platform.add_member(admin, institution, teacher, "subject_teacher")
        platform.add_member(admin, institution, reviewer, "professor")
        platform.add_member(admin, institution, student, "university_student")
        unit = platform.create_unit(admin, institution, "Science", "school")
        subject = platform.create_subject(admin, institution, "BIO-VERIFY", "Verification Biology", unit["id"])
        platform.assign_teacher(admin, institution, subject["id"], teacher)
        platform.assign_teacher(admin, institution, subject["id"], reviewer)
        platform.enroll(admin, institution, subject["id"], student)
        service = EducationPhase11Service(platform, root=root)

        tables = {row["name"] for row in platform._all("SELECT name FROM sqlite_master WHERE type='table'")}
        required_tables = {
            "education_mfa_enrollments", "education_security_events", "education_question_banks",
            "education_questions", "education_question_versions", "education_question_reviews",
            "education_grade_schemes", "education_transcript_entries", "education_credentials",
            "education_notification_outbox", "education_report_runs", "education_health_snapshots",
            "education_incidents", "education_retention_policies", "education_privacy_requests",
            "education_full_backups",
        }
        verifier.require("phase11_schema", required_tables <= tables, sorted(required_tables - tables))
        verifier.require("totp_rfc_vector", _totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", at_time=59, digits=8) == "94287082")

        service.enroll_identity(admin, institution, admin, "Correct-Horse-Phase11", display_name="Admin", email="admin@verify.edu")
        pending = service.begin_totp_enrollment(admin, institution, admin)
        verifier.require("mfa_secret_encrypted_at_rest", bool(platform._one("SELECT secret_cipher FROM education_mfa_enrollments WHERE user_id=?", (admin,))["secret_cipher"] != pending["secret"]))
        confirmed = service.confirm_totp_enrollment(admin, institution, admin, _totp(pending["secret"]))
        verifier.require("mfa_recovery_codes_issued", len(confirmed["recovery_codes"]) == 10)
        auth = service.begin_secure_authentication(institution, "admin@verify.edu", "Correct-Horse-Phase11")
        verifier.require("mfa_challenge_required", auth["status"] == "mfa_required")
        signed = service.complete_secure_authentication(auth["challenge_token"], code=_totp(pending["secret"]))
        verifier.require("mfa_session_created", service.validate_session(signed["token"])["user_id"] == admin)
        recovery_auth = service.begin_secure_authentication(institution, admin, "Correct-Horse-Phase11")
        recovered = service.complete_secure_authentication(recovery_auth["challenge_token"], recovery_code=confirmed["recovery_codes"][0])
        verifier.require("single_use_recovery_code", recovered["status"] == "authenticated")
        replay = service.begin_secure_authentication(institution, admin, "Correct-Horse-Phase11")
        replay_blocked = False
        try:
            service.complete_secure_authentication(replay["challenge_token"], recovery_code=confirmed["recovery_codes"][0])
        except Denied:
            replay_blocked = True
        verifier.require("recovery_replay_blocked", replay_blocked)
        posture = service.mfa_posture(admin, institution)
        verifier.require("mfa_posture", posture["enabled"] == 1 and posture["coverage_percent"] > 0, posture)

        service.security_event(institution, "verification_start", actor_id=admin)
        service.security_event(institution, "verification_security", actor_id=admin, severity="high")
        verifier.require("security_chain", service.verify_security_chain(admin, institution)["passed"])
        service.enforce_rate_limit("verify", limit=2, window_seconds=60)
        service.enforce_rate_limit("verify", limit=2, window_seconds=60)
        limited = False
        try:
            service.enforce_rate_limit("verify", limit=2, window_seconds=60)
        except Denied:
            limited = True
        verifier.require("rate_limit", limited)

        bank = service.create_question_bank(teacher, institution, "Verification Bank", subject_id=subject["id"])
        verifier.require("question_bank", bank["state"] == "active")
        question = service.create_question(
            teacher, bank["id"], question_type="single_choice", title="DNA", body="DNA primarily supports?",
            options=["Inheritance", "Digestion"], answer={"option": "Inheritance"}, bloom_level="understand",
            difficulty="medium", outcome_code="CO1", marks=2,
        )
        verifier.require("question_version_one", question["current_version"] == 1)
        self_approval_blocked = False
        try:
            service.review_question(teacher, question["id"], "approve")
        except Denied:
            self_approval_blocked = True
        verifier.require("question_self_approval_blocked", self_approval_blocked)
        service.review_question(reviewer, question["id"], "approve", comments="Independent review")
        published = service.publish_question(admin, question["id"])
        verifier.require("question_independent_publish", published["state"] == "published")
        blueprint = service.generate_question_blueprint(
            teacher, institution, subject_id=subject["id"], total_marks=2,
            bloom_distribution={"understand": 100}, difficulty_distribution={"medium": 100},
        )
        verifier.require("question_blueprint", blueprint["complete"] and blueprint["selected_marks"] == 2, blueprint)
        service.record_question_response(student, question["id"], student, is_correct=True, marks_awarded=2, response_seconds=12, option_key="Inheritance")
        analysis = service.question_item_analysis(teacher, question["id"])
        verifier.require("question_item_analysis", analysis["attempts"] == 1 and analysis["difficulty_index"] == 1, analysis)

        scheme = service.create_grade_scheme(
            admin, institution, "Verification Scheme", subject_id=subject["id"],
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
        grade = service.calculate_grade(admin, scheme["id"], student, {"Assignments": [90, 80], "Examination": 75})
        verifier.require("weighted_grade_scheme", grade["percentage"] == 79 and grade["grade_label"] == "B", grade)
        service.upsert_transcript_entry(
            admin, institution, student, academic_year="2026-27", term="Semester 1",
            subject_code="BIO-VERIFY", subject_name="Verification Biology", credits=4,
            marks_percent=grade["percentage"], grade_label=grade["grade_label"], grade_points=grade["grade_points"],
        )
        transcript = service.transcript(student, institution, student)
        verifier.require("transcript_cgpa", transcript["total_credits"] == 4 and transcript["cgpa"] == 3, transcript)
        credential = service.issue_credential(admin, institution, student, credential_type="verification", title="Phase 11 Verified", evidence={"cgpa": transcript["cgpa"]})
        verifier.require("signed_credential", service.verify_credential(credential["serial_number"])["valid"])
        service.revoke_credential(admin, credential["id"], reason="Qualification revocation test")
        verifier.require("credential_revocation", not service.verify_credential(credential["serial_number"])["valid"])

        template = service.save_notification_template(admin, institution, "verify", channel="in_app", body_template="Hello {{name}}")
        verifier.require("notification_template", template["state"] == "active")
        queued = service.queue_notification(teacher, institution, student, template_key="verify", context={"name": "Student"}, idempotency_key="verify-1")
        duplicate = service.queue_notification(teacher, institution, student, template_key="verify", context={"name": "Student"}, idempotency_key="verify-1")
        verifier.require("notification_idempotency", queued["id"] == duplicate["id"])
        claimed = service.claim_notification("verify-worker", channel="in_app")
        verifier.require("notification_claim", claimed is not None and claimed["state"] == "processing")
        delivered = service.complete_notification("verify-worker", claimed["id"], claimed["lock_token_plain"], state="delivered")
        verifier.require("notification_delivery", delivered["state"] == "delivered")

        session = platform.attendance_session(teacher, institution, subject["id"], datetime.now(timezone.utc).date().isoformat(), "P1")
        platform.mark_attendance(teacher, session["id"], student, "present")
        report = service.generate_report(admin, institution, "attendance", output_format="csv")
        verifier.require("report_sha256", Path(report["output_path"]).is_file() and len(report["sha256"]) == 64, report)

        tenant_file = Path(platform.storage) / institution / "materials" / "evidence.txt"
        tenant_file.parent.mkdir(parents=True, exist_ok=True)
        tenant_file.write_text("phase11 evidence", encoding="utf-8")
        full_backup = service.create_full_backup(admin, institution, "verification")
        verifier.require("encrypted_full_backup", full_backup["integrity_valid"] and full_backup["encrypted"] == 1, full_backup)
        rehearsal = service.full_backup_restore_rehearsal(admin, full_backup["id"])
        verifier.require("restore_rehearsal", rehearsal["integrity"] == "ok" and rehearsal["live_data_replaced"] is False, rehearsal)

        health = service.record_health_snapshot(admin, institution)
        verifier.require("health_snapshot", health["database_ok"] == 1 and health["storage_ok"] == 1, health)
        incident = service.open_incident(admin, institution, "Qualification incident", severity="medium", summary="Exercise")
        resolved = service.update_incident(admin, incident["id"], status="resolved", detail="Recovered")
        verifier.require("incident_lifecycle", resolved["status"] == "resolved" and len(resolved["events"]) == 2, resolved)
        policy = service.save_retention_policy(admin, institution, "education_records", retention_days=2555, action="archive")
        verifier.require("retention_policy", policy["retention_days"] == 2555)
        privacy = service.create_privacy_request(student, institution, student, request_type="export", reason="Qualification")
        completed = service.decide_privacy_request(admin, privacy["id"], state="completed", note="Delivered")
        verifier.require("privacy_request", completed["state"] == "completed")

        dependency = service.external_dependency_posture(admin, institution)
        verifier.require("external_honesty_boundary", "Configured is not equivalent" in dependency["qualification_rule"], dependency["qualification_rule"])

        from biointel.education.api import router
        routes = [route.path for route in router.routes]
        verifier.require("phase11_api_routes", len([path for path in routes if "phase11" in path]) >= 32)
        verifier.require("phase11_page", (ROOT / "pages" / "349_BioIntel_Mega_Production_and_Academic_Center.py").is_file())
        verifier.require("phase11_worker", (ROOT / "scripts" / "run_education_phase11_worker.py").is_file())
        verifier.require("phase11_navigation", "349_BioIntel_Mega_Production_and_Academic_Center.py" in (SRC / "biointel" / "education" / "experience.py").read_text(encoding="utf-8"))

    passed = sum(1 for item in verifier.controls if item["passed"])
    report = {
        "schema": "biointel.education-phase11-verification.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed == len(verifier.controls),
        "passed_controls": passed,
        "total_controls": len(verifier.controls),
        "controls": verifier.controls,
    }
    output = Path(args.output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "passed_controls", "total_controls")}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
