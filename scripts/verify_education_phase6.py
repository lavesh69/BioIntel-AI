from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from biointel.education.phase6 import EducationPhase6Service
from biointel.education.platform import Denied, EducationError, EducationPlatform


def expect_error(error_type, fn) -> bool:
    try:
        fn()
    except error_type:
        return True
    return False


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    controls: list[tuple[str, bool]] = []

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        platform = EducationPlatform(work / "education.sqlite3", work / "media")
        admin, teacher, student = "admin", "teacher", "student"
        institution = platform.create_institution(admin, "Phase 6 Verification University")["id"]
        platform.add_member(admin, institution, teacher, "subject_teacher")
        platform.add_member(admin, institution, student, "university_student")
        unit = platform.create_unit(admin, institution, "School of Biosciences", "school")
        subject = platform.create_subject(admin, institution, "BIO-601", "Visual Biology", unit["id"])
        platform.assign_teacher(admin, institution, subject["id"], teacher)
        platform.enroll(admin, institution, subject["id"], student)
        service = EducationPhase6Service(platform, root=work)

        controls.append(("database-quick-check", platform.db.quick_check()))
        tables = {row["name"] for row in platform._all("SELECT name FROM sqlite_master WHERE type='table'")}
        expected_tables = {
            "education_ui_preferences", "education_page_activity", "education_page_favorites",
            "education_shiro_conversations", "education_shiro_messages", "education_workers",
            "education_job_progress", "education_backup_schedules", "education_integration_sync_runs",
            "education_saved_views", "education_external_qualifications",
        }
        controls.append(("phase6-schema", expected_tables.issubset(tables)))

        prefs = service.save_preferences(
            teacher, institution, theme="light", density="compact", font_scale=1.2,
            high_contrast=True, reduced_motion=True, dyslexia_mode=True,
        )
        controls.append(("persisted-ui-preferences", prefs["theme"] == "light" and prefs["high_contrast"] == 1 and prefs["reduced_motion"] == 1))
        service.record_visit(teacher, institution, "classroom")
        favorite = service.toggle_favorite(teacher, institution, "classroom")
        nav = service.navigation_state(teacher, institution)
        controls.append(("favorites-and-recent-navigation", favorite and nav["favorites"] == ["classroom"] and nav["recent"][0] == "classroom"))
        view = service.save_view(teacher, institution, "gradebook", "Needs support", {"below": 60}, ["student_id", "overall_percent"])
        controls.append(("saved-data-view", view["name"] == "Needs support"))

        start = datetime.now(timezone.utc) + timedelta(days=1)
        platform.create_timetable(admin, institution, subject["id"], teacher, "BIO-A", "LAB-1", start.isoformat(), (start + timedelta(hours=1)).isoformat())
        calendar = service.timetable_calendar(student, institution, start_day=start.date(), days=7)
        controls.append(("visual-calendar-data", len(calendar["entries"]) == 1 and calendar["entries"][0]["room"] == "LAB-1"))

        assignment = platform.create_assignment(teacher, institution, subject["id"], "Visual assignment", "Explain cells", (start + timedelta(days=3)).isoformat(), 20)
        submission = platform.submit_assignment(student, assignment["id"], "Cells are functional units.", final=True)
        platform.grade_submission(teacher, submission["id"], 16, "Good")
        gradebook = service.gradebook(teacher, institution, subject["id"])
        controls.append(("gradebook-aggregation", gradebook["rows"][0]["overall_percent"] == 80.0))

        attendance_session = platform.attendance_session(teacher, institution, subject["id"], start.date().isoformat(), "P1")
        platform.mark_attendance(teacher, attendance_session["id"], student, "present")
        heatmap = service.attendance_heatmap(teacher, institution, subject_id=subject["id"])
        controls.append(("attendance-heatmap-data", heatmap["summary"][0]["attendance_percent"] == 100.0))

        exam = service.exams.create_exam(
            teacher, institution, subject["id"], "Visual analytics examination", 10,
            (start + timedelta(hours=2)).isoformat(), (start + timedelta(hours=3)).isoformat(),
            duration_minutes=30,
        )
        service.exams.add_question(
            teacher, exam["id"], "single_choice", "Cell unit?", 10,
            options=["Cell", "Atom"], correct_answer="Cell", bloom_level="apply", difficulty="medium",
        )
        service.permissions.set_override(admin, institution, "subject_teacher", "exam.publish", "allow")
        service.exams.publish_exam(teacher, exam["id"])
        analytics = service.exam_analytics(teacher, exam["id"])
        controls.append(("exam-analytics", analytics["difficulty_distribution"] == {"medium": 1} and analytics["bloom_distribution"] == {"apply": 1}))
        controls.append(("exam-analytics-student-denial", expect_error(Denied, lambda: service.exam_analytics(student, exam["id"]))))

        service.phase4.index_subject_text(teacher, institution, subject["id"], "Cell evidence", "Cells are the basic structural and functional units of life.")
        controls.append(("shiro-subject-grounding-required", expect_error(EducationError, lambda: service.create_conversation(student, institution, subject_id=None, title="Unsafe"))))
        conversation = service.create_conversation(student, institution, subject_id=subject["id"], title="Cell revision", mode="guided_learning", language="English")
        updated = service.ask_conversation(student, conversation["id"], "What is a cell?")
        controls.append(("persistent-shiro-chat", len(updated["messages"]) == 2 and updated["messages"][1]["role"] == "assistant"))
        controls.append(("shiro-mode-validation", expect_error(EducationError, lambda: service.create_conversation(student, institution, subject_id=subject["id"], title="Bad", mode="unrestricted"))))
        graph = service.knowledge_graph(student, institution, student_id=student, subject_id=subject["id"])
        controls.append(("knowledge-graph-contract", "nodes" in graph and "edges" in graph and "recommendations" in graph))

        worker = service.register_worker(admin, institution, "worker-1", queues=["default", "reports"], version="6.0")
        controls.append(("worker-registry", worker["state"] == "online" and "reports" in worker["queue_names_json"]))
        job = service.phase5.enqueue_job(teacher, institution, "generate_report", {"student_id": student})
        claimed = service.phase5.claim_job("worker-1")
        progress = service.update_job_progress(institution, "worker-1", job["id"], claimed["lock_token"], 45, "Building report")
        controls.append(("job-progress", progress["progress_percent"] == 45))
        cancelled = service.cancel_job(admin, institution, job["id"])
        controls.append(("running-job-cancellation", cancelled["cancel_requested"] == 1))
        service.phase5.fail_job("worker-1", job["id"], claimed["lock_token"], "cancelled", retry_delay_seconds=0)
        claimed = service.phase5.claim_job("worker-1")
        service.phase5.fail_job("worker-1", job["id"], claimed["lock_token"], "permanent", retry_delay_seconds=0)
        claimed = service.phase5.claim_job("worker-1")
        failed = service.phase5.fail_job("worker-1", job["id"], claimed["lock_token"], "permanent", retry_delay_seconds=0)
        requeued = service.requeue_job(admin, institution, failed["id"])
        controls.append(("failed-job-requeue", failed["state"] == "failed" and requeued["state"] == "queued"))
        operations = service.job_operations(admin, institution)
        controls.append(("queue-operations-dashboard", bool(operations["workers"]) and bool(operations["jobs"])))

        schedule = service.create_backup_schedule(admin, institution, "Daily verified backup", frequency="daily", hour_utc=0, retention_count=14)
        controls.append(("backup-schedule", schedule["frequency"] == "daily" and schedule["retention_count"] == 14))
        due = service.enqueue_due_backups(admin, institution)
        controls.append(("scheduled-backup-queue-contract", isinstance(due, dict) and "scheduled" in due and "jobs" in due))

        integration = service.phase5.configure_integration(admin, institution, "moodle", "Moodle", base_url="https://lms.example", secret_reference="vault:moodle", activate=True)
        service.phase5.test_integration_readiness(admin, integration["id"])
        sync = service.start_integration_sync(admin, integration["id"], direction="pull", entity_type="courses")
        sync_ops = service.integration_operations(admin, institution)
        controls.append(("integration-sync-run", sync["state"] == "queued" and sync_ops["runs"][0]["id"] == sync["id"]))

        profile = service.phase5.configure_database_profile(admin, institution, "sqlite", "Local DB", activate=True)
        qualification = service.external.verify_database_profile(admin, profile["id"])
        controls.append(("bounded-database-qualification", qualification["state"] == "verified" and qualification["evidence"]["quick_check"] is True))
        posture = service.phase5.configure_identity_provider(
            admin, institution, "oidc", "Blocked local issuer", issuer_url="https://127.0.0.1",
            client_id="biointel", secret_reference="env:TEST_IDP_SECRET", activate=True,
        )
        provider_id = posture["providers"][0]["id"]
        blocked = service.external.verify_identity_provider(admin, provider_id)
        controls.append(("external-ssrf-boundary", blocked["state"] == "failed" and ("Private" in blocked["error_text"] or "loopback" in blocked["error_text"])))
        controls.append(("qualification-evidence-history", len(service.external.history(admin, institution)) == 2))

        dashboard = service.visual_dashboard(admin, institution)
        controls.append(("visual-dashboard-contract", all(key in dashboard for key in ("calendar", "notifications", "recent_activity", "navigation"))))

    required = [
        root / "pages/347_BioIntel_Education_Visual_Command_Center.py",
        root / "src/biointel/education/phase6.py",
        root / "src/biointel/education/phase6_visuals.py",
        root / "src/biointel/education/phase6_adapters.py",
        root / "src/biointel/education/visual_command_ui.py",
        root / "scripts/run_education_phase6_worker.py",
        root / "RUN_EDUCATION_PHASE6_WORKER_WINDOWS.bat",
        root / "tests/test_education_phase6.py",
    ]
    controls.append(("phase6-app-and-worker-files", all(path.is_file() for path in required)))

    visual_text = (root / "src/biointel/education/phase6_visuals.py").read_text(encoding="utf-8")
    controls.append(("domain-visual-workspaces", all(marker in visual_text for marker in ("timetable_calendar", "attendance_heatmap", "mastery_graph", "exam_monitor_grid", "organization_tree", "queue_board", "integration_topology"))))
    controls.append(("responsive-accessibility-css", all(marker in visual_text for marker in ("@media(max-width:700px)", "prefers-reduced-motion", "edu-high-contrast", "focus-visible"))))

    experience = (root / "src/biointel/education/experience.py").read_text(encoding="utf-8")
    controls.append(("permission-aware-navigation", "PAGE_PERMISSIONS" in experience and "resolver.has" in experience))
    controls.append(("accessibility-toolbar", "render_accessibility_toolbar" in experience and "education_dyslexia_mode" in experience and "font_scale" in experience))

    navigation = (root / "src/biointel/ui/navigation.py").read_text(encoding="utf-8")
    controls.append(("phase6-primary-navigation", "biointel_education_visual_command" in navigation))

    api = (root / "src/biointel/education/api.py").read_text(encoding="utf-8")
    api_markers = (
        "/phase6/preferences", "/phase6/dashboard", "/phase6/calendar", "/phase6/gradebook/",
        "/phase6/attendance-heatmap", "/phase6/exams/", "/phase6/conversations",
        "/phase6/workers", "/phase6/backup-schedules", "/phase6/integrations/",
        "/phase6/qualification-history",
    )
    controls.append(("phase6-typed-api", all(marker in api for marker in api_markers)))

    worker_text = (root / "scripts/run_education_phase6_worker.py").read_text(encoding="utf-8")
    controls.append(("durable-worker-handlers", all(marker in worker_text for marker in ("scheduled_backup", "generate_report", "integration_sync", "notification_reminders", "verify_backup"))))

    failed = [name for name, passed in controls if not passed]
    print(f"Education Phase 6 verification {'passed' if not failed else 'failed'}: {len(controls) - len(failed)}/{len(controls)} controls")
    for name, passed in controls:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
