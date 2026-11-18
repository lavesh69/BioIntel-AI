from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from biointel.education.phase7 import EducationPhase7Service
from biointel.education.platform import Conflict, Denied, EducationError, EducationPlatform


def expect(error_type, fn) -> bool:
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
        admin, teacher, student, other = "admin", "teacher", "student", "other-admin"
        institution = platform.create_institution(admin, "Phase 7 Qualification University")["id"]
        platform.add_member(admin, institution, teacher, "subject_teacher")
        platform.add_member(admin, institution, student, "university_student")
        platform.add_member(admin, institution, other, "institution_administrator")
        unit = platform.create_unit(admin, institution, "Science", "school")
        subject = platform.create_subject(admin, institution, "BIO-701", "Desktop Biology", unit["id"])
        platform.assign_teacher(admin, institution, subject["id"], teacher)
        platform.enroll(admin, institution, subject["id"], student)
        service = EducationPhase7Service(platform, root=work)

        controls.append(("database-quick-check", platform.db.quick_check()))
        tables = {row["name"] for row in platform._all("SELECT name FROM sqlite_master WHERE type='table'")}
        expected = {
            "education_identity_accounts", "education_desktop_sessions", "education_lecture_chapters",
            "education_lecture_notes", "education_lecture_bookmarks", "education_assignment_rubrics",
            "education_rubric_criteria", "education_rubric_scores", "education_lecture_transcripts",
            "education_exam_thresholds", "education_exam_moderation_events",
        }
        controls.append(("phase7-schema", expected.issubset(tables)))

        service.enroll_identity(admin, institution, admin, "Correct-Horse-7", display_name="Admin")
        service.enroll_identity(admin, institution, other, "Correct-Horse-8", display_name="Other")
        controls.append(("multiple-blank-email-identities", len(service.identity_accounts(institution)) == 2))
        controls.append(("invalid-sign-in-denied", expect(Denied, lambda: service.authenticate(institution, admin, "wrong"))))
        signed = service.authenticate(institution, admin, "Correct-Horse-7", device_label="Qualification desktop")
        session = service.validate_session(signed["token"])
        controls.append(("scrypt-authentication", session["user_id"] == admin and "token_hash" not in session))
        controls.append(("revocable-session-list", len(service.sessions(admin, institution)) == 1))
        service.revoke_session(admin, institution, session["id"])
        controls.append(("revoked-session-denied", expect(Denied, lambda: service.validate_session(signed["token"]))))
        for _ in range(5):
            expect(Denied, lambda: service.authenticate(institution, other, "bad"))
        controls.append(("sign-in-lockout", expect(Conflict, lambda: service.authenticate(institution, other, "Correct-Horse-8"))))

        start = datetime.now(timezone.utc) + timedelta(days=1)
        first = platform.create_timetable(admin, institution, subject["id"], teacher, "A", "R1", start.isoformat(), (start + timedelta(hours=1)).isoformat())
        second = platform.create_timetable(admin, institution, subject["id"], teacher, "B", "R2", (start + timedelta(hours=2)).isoformat(), (start + timedelta(hours=3)).isoformat())
        controls.append(("conflict-safe-timetable-update", expect(Conflict, lambda: service.update_timetable_entry(admin, institution, second["id"], starts_at=(start + timedelta(minutes=15)).isoformat(), ends_at=(start + timedelta(minutes=45)).isoformat(), teacher_id=teacher, student_group="B", room="R2"))))
        moved = service.update_timetable_entry(admin, institution, second["id"], starts_at=(start + timedelta(hours=3)).isoformat(), ends_at=(start + timedelta(hours=4)).isoformat(), teacher_id=teacher, student_group="B", room="R2")
        controls.append(("timetable-update", moved["room"] == "R2" and moved["state"] == "scheduled"))
        controls.append(("cancel-reason-required", expect(EducationError, lambda: service.cancel_timetable_entry(admin, institution, first["id"], ""))))
        controls.append(("audited-timetable-cancel", service.cancel_timetable_entry(admin, institution, first["id"], "Holiday")["state"] == "cancelled"))

        attendance = platform.attendance_session(teacher, institution, subject["id"], start.date().isoformat(), "P1")
        roster = service.attendance_roster(teacher, institution, subject["id"], attendance["id"])
        controls.append(("editable-attendance-roster", roster["rows"] == [{"student_id": student, "status": "present", "note": ""}]))
        saved = service.save_attendance_roster(teacher, attendance["id"], [{"student_id": student, "status": "late", "note": "Transport"}], lock=True)
        controls.append(("bulk-attendance-save-lock", saved["session"]["state"] == "locked" and saved["rows"][0]["status"] == "late"))
        controls.append(("locked-attendance-protected", expect(Conflict, lambda: service.save_attendance_roster(teacher, attendance["id"], [{"student_id": student, "status": "present"}]))))

        assignment = platform.create_assignment(teacher, institution, subject["id"], "Desktop assessment", "Answer", (start + timedelta(days=3)).isoformat(), 20)
        submission = platform.submit_assignment(student, assignment["id"], "Evidence", final=True)
        board = service.assignment_board(teacher, institution, subject["id"])
        controls.append(("assignment-kanban-contract", sum(len(rows) for rows in board["buckets"].values()) == 1))
        edit = service.editable_gradebook(teacher, institution, subject["id"])
        controls.append(("editable-gradebook-contract", edit["rows"][0]["submission_id"] == submission["id"]))
        service.save_gradebook_rows(teacher, institution, [{"submission_id": submission["id"], "marks": 17, "feedback": "Strong"}])
        service.save_gradebook_rows(teacher, institution, [{"submission_id": submission["id"], "marks": 18, "feedback": "Moderated"}], reason="Second review")
        controls.append(("bulk-grade-save", platform._one("SELECT marks FROM grades WHERE submission_id=?", (submission["id"],))["marks"] == 18))
        controls.append(("grade-revision-evidence", len(platform._all("SELECT id FROM grade_revisions WHERE submission_id=?", (submission["id"],))) == 1))
        rubric = service.save_assignment_rubric(
            teacher,
            assignment["id"],
            "Evidence rubric",
            [
                {"title": "Accuracy", "description": "Correct science", "max_marks": 12},
                {"title": "Reasoning", "description": "Clear evidence", "max_marks": 8},
            ],
        )
        controls.append(("rubric-builder", len(rubric["criteria"]) == 2 and sum(float(row["max_marks"]) for row in rubric["criteria"]) == 20))
        rubric_grade = service.grade_with_rubric(
            teacher,
            submission["id"],
            [
                {"criterion_id": rubric["criteria"][0]["id"], "marks": 11, "feedback": "Accurate"},
                {"criterion_id": rubric["criteria"][1]["id"], "marks": 8, "feedback": "Clear"},
            ],
            overall_feedback="Excellent",
            reason="Rubric moderation",
        )
        controls.append(("criterion-grade-evidence", rubric_grade["total_marks"] == 19 and len(platform._all("SELECT id FROM education_rubric_scores WHERE submission_id=?", (submission["id"],))) == 2))
        controls.append(("rubric-total-policy", expect(Conflict, lambda: service.save_assignment_rubric(teacher, assignment["id"], "Bad", [{"title": "Only", "max_marks": 5}]))))

        course = platform.create_course(teacher, institution, "Desktop Course", publish=True)
        section1 = service.create_course_section(teacher, course["id"], "Module 1", position=0)
        section2 = service.create_course_section(teacher, course["id"], "Lesson 1", section_type="lesson", parent_id=section1["id"], position=1)
        curriculum = service.reorder_course_sections(teacher, course["id"], [section2["id"], section1["id"]])
        controls.append(("curriculum-builder", len(curriculum["sections"]) == 2 and curriculum["sections"][0]["id"] == section2["id"]))
        controls.append(("curriculum-complete-reorder", expect(Conflict, lambda: service.reorder_course_sections(teacher, course["id"], [section1["id"]]))))
        stamp = datetime.now(timezone.utc).isoformat()
        lecture_id = "phase7-lecture"
        with platform.db.connection() as db:
            db.execute("INSERT INTO lectures VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (lecture_id, institution, course["id"], teacher, "Lesson", "", "", "", 0, "video/mp4", 600, "ready", None, "published", stamp, stamp))
        service.add_lecture_chapter(teacher, lecture_id, "Introduction", 0)
        service.save_lecture_note(student, lecture_id, "Remember this", position_seconds=12)
        service.add_lecture_bookmark(student, lecture_id, 12, "Review")
        notebook = service.lecture_notebook(student, lecture_id)
        controls.append(("lecture-chapters", len(notebook["chapters"]) == 1))
        controls.append(("lecture-notes", len(notebook["notes"]) == 1))
        controls.append(("lecture-bookmarks", len(notebook["bookmarks"]) == 1))
        transcript = service.save_lecture_transcript(teacher, lecture_id, "DNA stores information. RNA supports expression.", language="English")
        controls.append(("searchable-lecture-transcript", transcript["language"] == "English" and "RNA" in service.lecture_transcripts(student, lecture_id)[0]["body"]))

        service.phase4.index_subject_text(teacher, institution, subject["id"], "Evidence", "DNA stores biological information.")
        conversation = service.create_conversation(student, institution, subject_id=subject["id"], title="DNA")
        controls.append(("conversation-rename", service.rename_conversation(student, conversation["id"], "DNA revision")["title"] == "DNA revision"))
        controls.append(("conversation-archive", service.archive_conversation(student, conversation["id"])["state"] == "archived"))
        service.delete_conversation(student, conversation["id"])
        controls.append(("conversation-delete", platform._one("SELECT id FROM education_shiro_conversations WHERE id=?", (conversation["id"],)) is None))

        exam = service.exams.create_exam(teacher, institution, subject["id"], "Policy exam", 10, (start + timedelta(hours=5)).isoformat(), (start + timedelta(hours=6)).isoformat(), duration_minutes=30)
        service.permissions.set_override(admin, institution, "subject_teacher", "exam.monitor", "allow")
        threshold = service.set_exam_passing_percent(teacher, exam["id"], 60)
        analytics = service.exam_analytics_phase7(teacher, exam["id"])
        controls.append(("configurable-pass-threshold", threshold["passing_percent"] == 60 and analytics["summary"]["passing_percent"] == 60))
        controls.append(("invalid-pass-threshold", expect(EducationError, lambda: service.set_exam_passing_percent(teacher, exam["id"], 101))))
        moderation = service.record_moderation_event(teacher, exam["id"], "review_started")
        controls.append(("moderation-timeline", service.moderation_timeline(teacher, exam["id"])[0]["id"] == moderation["id"]))
        controls.append(("moderation-reason-policy", expect(EducationError, lambda: service.record_moderation_event(teacher, exam["id"], "score_flagged"))))

    required = [
        root / "pages/348_BioIntel_Education_Desktop.py",
        root / "src/biointel/education/phase7.py",
        root / "src/biointel/education/phase7_ui.py",
        root / "tests/test_education_phase7.py",
        root / "scripts/verify_education_phase7.py",
    ]
    controls.append(("phase7-files", all(path.is_file() for path in required)))
    ui = (root / "src/biointel/education/phase7_ui.py").read_text(encoding="utf-8")
    service_text = (root / "src/biointel/education/phase7.py").read_text(encoding="utf-8")
    experience = (root / "src/biointel/education/experience.py").read_text(encoding="utf-8")
    navigation = (root / "src/biointel/ui/navigation.py").read_text(encoding="utf-8")
    api = (root / "src/biointel/education/api.py").read_text(encoding="utf-8")
    controls.append(("lazy-selected-workspace", "Only the selected branch executes" in ui and "edu7-workspace" in ui))
    controls.append(("desktop-editors", all(marker in ui for marker in ("st.data_editor", "Save gradebook changes", "Save and lock session"))))
    controls.append(("rubric-workspace", all(marker in ui for marker in ("Rubric workspace", "Save rubric grade", "criterion_id"))))
    controls.append(("searchable-transcript-ui", all(marker in ui for marker in ("Searchable lecture transcript", "Search transcript", "Save transcript"))))
    controls.append(("desktop-command-palette", "Command palette" in ui and "edu7-command-query" in ui))
    controls.append(("optional-live-refresh", "Auto-refresh every 10 seconds" in ui and "fragment(run_every=timedelta(seconds=10))" in ui))
    controls.append(("native-shiro-chat", all(marker in ui for marker in ("st.chat_message", "st.chat_input", "Evidence details"))))
    controls.append(("interactive-plotly", all(marker in ui for marker in ("st.plotly_chart", "on_select=\"rerun\"", "selection_mode=\"points\""))))
    controls.append(("scientific-viewers", all(marker in ui for marker in ("Nucleotide composition", "Expression heatmap", "Sample PCA", "Volcano plot"))))
    controls.append(("desktop-accessibility", all(marker in ui for marker in ("edu7-skip", "focus", "Skip to workspace"))))
    controls.append(("scrypt-and-token-hashing", "hashlib.scrypt" in service_text and "hashlib.sha256" in service_text and "hmac.compare_digest" in service_text))
    controls.append(("role-aware-desktop-navigation", "pages/348_BioIntel_Education_Desktop.py" in experience and "biointel_education_desktop" in navigation))
    api_markers = ("/phase7/sign-in", "/phase7/gradebook", "/phase7/attendance", "/phase7/conversations", "/phase7/exams", "/rubric", "/transcript")
    controls.append(("phase7-typed-api", all(marker in api for marker in api_markers)))

    failed = [name for name, passed in controls if not passed]
    print(f"Education Phase 7 verification {'passed' if not failed else 'failed'}: {len(controls)-len(failed)}/{len(controls)} controls")
    for name, passed in controls:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
