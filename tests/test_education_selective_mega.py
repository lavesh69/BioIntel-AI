from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from biointel.education.classroom_service import ClassroomService
from biointel.education.examination_service import ExaminationService
from biointel.education.platform import Conflict, Denied, EducationError, EducationPlatform
from biointel.education.selective_mega import EducationMegaService


@pytest.fixture()
def mega(tmp_path: Path) -> tuple[EducationMegaService, EducationPlatform, str]:
    platform = EducationPlatform(tmp_path / "education.sqlite3", tmp_path / "media")
    institution_id = platform.create_institution("admin", "R9 Test University")["id"]
    for user, role in (
        ("teacher", "teacher"),
        ("student", "student"),
        ("controller", "examination_controller"),
        ("viewer", "viewer"),
    ):
        platform.add_member("admin", institution_id, user, role)
    root = Path(__file__).resolve().parents[1]
    return (
        EducationMegaService(platform, root / "config" / "education_official_sources.json"),
        platform,
        institution_id,
    )


def test_additive_migration_and_rbac(
    mega: tuple[EducationMegaService, EducationPlatform, str],
) -> None:
    service, platform, institution_id = mega
    with platform.db.connection() as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        migration = db.execute(
            "SELECT id FROM education_migrations WHERE id='education_selective_mega_r9_v1'"
        ).fetchone()
    assert migration
    assert {
        "education_entities",
        "education_classes_r9",
        "education_question_bank_r9",
        "education_official_records_r9",
    } <= tables
    campus = service.create_entity("admin", institution_id, "campus", "North Campus", code="NORTH")
    assert campus["state"] == "active"
    assert service.list_entities("viewer", institution_id, "campus")[0]["id"] == campus["id"]
    with pytest.raises(Denied):
        service.create_entity("viewer", institution_id, "campus", "Forbidden")


def test_persistent_class_stream_and_classwork(
    mega: tuple[EducationMegaService, EducationPlatform, str],
) -> None:
    service, platform, institution_id = mega
    classroom = service.create_class(
        "teacher", institution_id, "Biology", "BIO-2026", visibility="code"
    )
    with pytest.raises(Conflict):
        service.create_class("teacher", institution_id, "Duplicate", "BIO-2026")
    invitation = service.invite_class_member(
        "teacher", institution_id, classroom["id"], "student", "student"
    )
    assert invitation["state"] == "invited"
    with platform.db.connection() as db:
        db.execute(
            "UPDATE education_class_members_r9 SET state='active' WHERE id=?", (invitation["id"],)
        )
    assert service.class_access("student", institution_id, classroom["id"])["id"] == classroom["id"]
    with pytest.raises(Denied):
        service.class_access("student", institution_id, classroom["id"], write=True)
    post = service.add_stream_post(
        "teacher", institution_id, classroom["id"], "Welcome", title="Start here"
    )
    classwork = service.create_classwork(
        "teacher",
        institution_id,
        classroom["id"],
        "assignment",
        "Cell model",
        max_marks=20,
        state="published",
    )
    assert post["published_at"]
    assert classwork["state"] == "published"
    assert service.module_snapshot("teacher", institution_id)["pending_classwork"] == 1


def test_exam_registration_schedule_evaluation_results_and_privacy(
    mega: tuple[EducationMegaService, EducationPlatform, str],
) -> None:
    service, _, institution_id = mega
    registration = service.register_exam(
        "student", institution_id, "exam-1", ["BIO101"], {"attendance_ok": True}
    )
    approved = service.decide_exam_registration(
        "controller", institution_id, registration["id"], True
    )
    assert approved["state"] == "approved"
    question = service.add_question(
        "teacher",
        institution_id,
        "BIO101",
        "multiple_choice",
        "What is DNA?",
        answer={"correct": "A"},
    )
    assert question["state"] == "draft"
    with pytest.raises(Conflict):
        service.add_question(
            "teacher", institution_id, "BIO101", "multiple_choice", "  WHAT   IS DNA? "
        )
    schedule = service.schedule_exam(
        "controller",
        institution_id,
        "exam-1",
        "R-101",
        1,
        "2026-09-01T09:00:00+05:30",
        "2026-09-01T10:00:00+05:30",
        invigilators=["inv-1"],
    )
    with pytest.raises(Conflict):
        service.schedule_exam(
            "controller",
            institution_id,
            "exam-2",
            "R-101",
            30,
            "2026-09-01T09:30:00+05:30",
            "2026-09-01T11:00:00+05:30",
        )
    assert (
        service.allocate_seat("controller", institution_id, schedule["id"], "student", "A1")[
            "seat_label"
        ]
        == "A1"
    )
    with pytest.raises(Conflict):
        service.allocate_seat("controller", institution_id, schedule["id"], "another-student", "A2")
    card = service.issue_admit_card(
        "controller", institution_id, registration["id"], {"room": "R-101"}
    )
    assert card["reference_code"].startswith("BIO-")
    evaluation = service.save_evaluation(
        "controller", institution_id, "exam-1", "student", {"Q1": 18, "Q2": 22}, submit=True
    )
    assert evaluation["total_marks"] == 40
    rules = {
        "maximum_marks": 50,
        "pass_percentage": 50,
        "grade_boundaries": [{"minimum": 80, "grade": "A"}, {"minimum": 0, "grade": "F"}],
    }
    first = service.process_result(
        "controller", institution_id, "exam-1", "student", 40, rules, publish=True
    )
    second = service.process_result(
        "controller", institution_id, "exam-1", "student", 42, rules, reason="moderation"
    )
    assert (first["version"], second["version"]) == (1, 2)
    policy = service.set_proctor_policy("controller", institution_id, "exam-1")
    assert policy["enabled"] == 0
    with pytest.raises(EducationError):
        service.set_proctor_policy(
            "controller", institution_id, "exam-1", enabled=True, camera=True
        )
    enabled = service.set_proctor_policy(
        "controller",
        institution_id,
        "exam-1",
        enabled=True,
        camera=True,
        retention_days=30,
        consent_text="I understand the optional camera adapter and retention policy.",
    )
    assert enabled["enabled"] == 1 and enabled["camera"] == 1


def test_official_import_provenance_idempotency_and_private_rejection(
    mega: tuple[EducationMegaService, EducationPlatform, str],
) -> None:
    service, _, institution_id = mega
    records = [
        {
            "official_id": "AISHE-1",
            "name": "Public Science College",
            "state_ut": "Uttarakhand",
            "district": "Dehradun",
            "dataset_year": "2025-26",
        },
        {
            "official_id": "PRIVATE-1",
            "name": "Rejected private row",
            "student_name": "Do not import",
        },
    ]
    first = service.import_official_records(
        "admin", institution_id, "aishe_directory", records, dataset_year="2025-26"
    )
    second = service.import_official_records(
        "admin", institution_id, "aishe_directory", records, dataset_year="2025-26"
    )
    assert first["records_imported"] == 1
    assert first["records_rejected"] == 1
    assert second["idempotent"] is True
    with service.platform.db.connection() as db:
        stored = dict(
            db.execute(
                "SELECT * FROM education_official_records_r9 WHERE official_id='AISHE-1'"
            ).fetchone()
        )
    assert stored["verification_status"] == "source_asserted_pending_review"
    assert stored["source_url"].startswith("https://")
    assert stored["dataset_year"] == "2025-26"
    coverage = service.directory_coverage()
    assert coverage["coverage_claim"] == "partial_authorised_imports_only"
    assert coverage["totals"]["imported"] == 1
    aishe = next(row for row in coverage["sources"] if row["id"] == "aishe_directory")
    assert aishe["scope"].startswith("Universities, colleges")
    directory = service.list_directory_records(source_id="aishe_directory", query="Dehradun")
    assert len(directory) == 1
    assert directory[0]["name"] == "Public Science College"
    assert directory[0]["source_name"] == "AISHE higher education institution directory"
    assert service.list_directory_records(query="not-present") == []


def test_csv_upload_export_and_search(
    mega: tuple[EducationMegaService, EducationPlatform, str],
) -> None:
    service, _, institution_id = mega
    csv_bytes = b"official_id,name,state_ut,district\nUGC-1,Example University,Delhi,New Delhi\n"
    result = service.import_csv(
        "admin", institution_id, "ugc_directory", csv_bytes, dataset_year="2026"
    )
    assert result["records_imported"] == 1
    assert service.search("viewer", institution_id, "Example")[0]["subtitle"] == "UGC-1"
    with pytest.raises(EducationError):
        service.import_csv("admin", institution_id, "ugc_directory", b"MZ-not-a-csv")
    assert (
        EducationMegaService.validate_upload("report.pdf", b"%PDF-1.7\n")["mime_type"]
        == "application/pdf"
    )
    with pytest.raises(EducationError):
        EducationMegaService.validate_upload("../report.pdf", b"%PDF-1.7\n")
    rows = [{"name": "One", "tags": ["verified"]}]
    output = service.export_csv(rows)
    assert list(csv.DictReader(io.StringIO(output.decode("utf-8-sig"))))[0]["name"] == "One"


def test_legacy_service_compatibility_and_configurable_pass_mark(tmp_path: Path) -> None:
    examination = ExaminationService(str(tmp_path / "legacy-exam"))
    created = examination.create_exam("Biology", "BIO", 60, [], passing_score=55)
    assert created["proctoring_enabled"] is False
    assert (
        examination.submit_exam(created["exam_id"], "student", "Student", {}, 54)["passed"] is False
    )
    assert (
        examination.submit_exam(created["exam_id"], "student", "Student", {}, 55)["passed"] is True
    )
    classroom = ClassroomService(str(tmp_path / "legacy-class"))
    created_class = classroom.add_class(
        "Biology", "2026", "Science", "Teacher", institution_id="institution-1"
    )
    assert created_class["institution_id"] == "institution-1"
    assert classroom.list_classes()[0]["institution_id"] == "institution-1"
