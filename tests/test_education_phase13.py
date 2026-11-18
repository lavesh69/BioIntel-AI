from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from biointel.education.phase13 import EducationPhase13Service
from biointel.education.platform import EducationPlatform


def build(tmp_path: Path, *, clock=None):
    platform = EducationPlatform(tmp_path / "education.sqlite3", tmp_path / "media")
    admin, teacher, student = "admin", "teacher", "student"
    institution = platform.create_institution(admin, "Phase 13 University")["id"]
    platform.add_member(admin, institution, teacher, "subject_teacher")
    platform.add_member(admin, institution, student, "university_student")
    unit = platform.create_unit(admin, institution, "Science", "school")
    subject = platform.create_subject(admin, institution, "BIO-1301", "Autonomous Biology", unit["id"])
    platform.assign_teacher(admin, institution, subject["id"], teacher)
    platform.enroll(admin, institution, subject["id"], student)
    service = EducationPhase13Service(platform, root=tmp_path, clock=clock)
    return platform, service, admin, teacher, student, institution, subject


def test_governed_rag_ingestion_search_and_context(tmp_path: Path):
    _, service, admin, teacher, student, institution, _ = build(tmp_path)
    source = tmp_path / "evidence.md"
    source.write_text(
        "# Molecular inheritance\nDNA stores hereditary information.\n"
        "Replication preserves genetic information before cell division.\n"
        "RNA supports transcription and translation.",
        encoding="utf-8",
    )
    registered = service.register_rag_document(teacher, institution, "bio-course", source, permissions={"roles": ["subject_teacher", "university_student"]})
    service.approve_rag_document(admin, registered["id"], approve=True, reason="Approved course evidence")
    ingestion = service.ingest_rag_document(teacher, registered["id"], chunk_chars=350, overlap_chars=30)
    assert ingestion["state"] == "completed"
    assert ingestion["chunk_count"] >= 1
    search = service.search_rag(student, institution, "bio-course", "What preserves genetic information?")
    assert search["evidence_status"] == "grounded"
    assert search["results"][0]["source_name"] == "evidence.md"
    bundle = service.rag_context_bundle(student, institution, "bio-course", "DNA inheritance")
    assert bundle["safe_to_answer"] is True
    assert bundle["citations"]


def test_automatic_timetable_preview_and_atomic_commit(tmp_path: Path):
    platform, service, admin, teacher, _, institution, subject = build(tmp_path)
    start = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
    requirements = [{
        "subject_id": subject["id"],
        "teacher_id": teacher,
        "student_group": "BSc-Bio-A",
        "room_candidates": ["LAB-1", "ROOM-2"],
        "sessions_per_week": 2,
        "duration_minutes": 60,
        "priority": 90,
    }]
    preview = service.generate_timetable_plan(admin, institution, term_start=start, weeks=4, requirements=requirements, commit=False)
    assert preview["state"] == "preview_ready"
    assert preview["planned_sessions_per_week"] == 2
    committed = service.generate_timetable_plan(admin, institution, term_start=start, weeks=4, requirements=requirements, commit=True)
    assert committed["state"] == "committed"
    assert len(committed["committed_series"]) == 2
    count = platform._one("SELECT COUNT(*) count FROM timetable_entries WHERE institution_id=?", (institution,))
    assert count["count"] == 8


def test_notification_policy_quiet_hours_digest_and_requeue(tmp_path: Path):
    fixed_now = datetime(2026, 7, 28, 23, 30, tzinfo=timezone.utc)
    platform, service, admin, teacher, student, institution, _ = build(tmp_path, clock=lambda: fixed_now)
    service.phase4.save_notification_preference(
        student, institution, event_type="assignment_due", channel="in_app", enabled=True,
        digest_mode="daily", quiet_start="22:00", quiet_end="07:00",
    )
    queued = service.queue_policy_notification(
        teacher, institution, student, event_type="assignment_due", channel="in_app",
        subject="Assignment due", body="Evidence review is due.", idempotency_key="phase13-due-1",
        requested_at="2026-07-28T23:30:00+00:00",
    )
    assert queued["plan"]["decision"] == "daily_digest"
    assert queued["outbox"]["state"] == "queued"
    claimed = service.claim_notification("worker", channel="in_app")
    # Daily digest is scheduled in the future, so direct claim may be empty.
    assert claimed is None
    with platform.db.connection() as db:
        db.execute("UPDATE education_notification_outbox SET state='failed' WHERE id=?", (queued["outbox"]["id"],))
    assert service.requeue_failed_notifications(admin, institution)["requeued"] == 1


def test_retention_dry_run_execute_and_support_bundle(tmp_path: Path):
    platform, service, admin, teacher, student, institution, _ = build(tmp_path)
    service.save_retention_policy(admin, institution, "notifications", retention_days=1, action="archive")
    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    queued = service.queue_notification(teacher, institution, student, body="Old notification")
    with platform.db.connection() as db:
        db.execute("UPDATE education_notification_outbox SET updated_at=? WHERE id=?", (old, queued["id"]))
    preview = service.execute_retention_policy(admin, institution, "notifications", dry_run=True)
    assert preview["candidate_count"] == 1
    executed = service.execute_retention_policy(admin, institution, "notifications", dry_run=False, confirmation="EXECUTE notifications 1")
    assert executed["affected_count"] == 1
    assert Path(executed["archive_path"]).is_file()
    bundle = service.create_support_bundle(admin, institution)
    assert bundle["contains_personal_content"] is False
    assert service.verify_support_bundle(admin, bundle["id"])["valid"] is True


def test_phase13_posture_reports_local_controls(tmp_path: Path):
    _, service, admin, _, _, institution, _ = build(tmp_path)
    posture = service.phase13_posture(admin, institution)
    assert posture["local_control_coverage_percent"] == 100.0
    assert posture["local_controls"]["multi_format_rag_ingestion"] is True
    assert "external_posture" in posture
