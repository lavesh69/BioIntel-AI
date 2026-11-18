from __future__ import annotations

from pathlib import Path

from biointel.education.database import EducationDatabase
from biointel.education.lecture_intelligence import LectureIntelligenceEngine
from biointel.education.phase4 import EducationPhase4Service
from biointel.education.phase7 import EducationPhase7Service
from biointel.education.platform import Denied, EducationPlatform, ident, now


ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8-sig")


def test_current_and_legacy_education_routes_use_theme_and_real_renderers():
    routes = {
        "pages/141_Shiro_AI_Studio.py": "render_page(ROOT)",
        "pages/150_BioIntel_Education_Home_v17.py": "render_education_home(ROOT)",
        "pages/151_BioIntel_Classroom_v17.py": "render_classroom(ROOT)",
        "pages/153_BioIntel_Academy_Lecture_Studio.py": "render_academy(ROOT)",
        "pages/155_Education_Intelligence_Hub.py": "render_education_intelligence_hub(ROOT)",
        "pages/172_Multilingual_Lecture_Intelligence.py": "render_academy(ROOT)",
        "pages/273_Shiro_AI.py": "render_page(ROOT)",
        "pages/339_BioIntel_Education_Home.py": "render_education_home(ROOT)",
        "pages/340_BioIntel_Classroom.py": "render_classroom(ROOT)",
        "pages/342_BioIntel_Academy_and_Lecture_Studio.py": "render_academy(ROOT)",
        "pages/343_BioIntel_Education_Universe.py": "render_universe(ROOT)",
        "pages/344_BioIntel_Examination_Command_Center.py": "render_examinations(ROOT)",
        "pages/345_BioIntel_Education_Intelligence_Hub.py": "render_education_intelligence_hub(ROOT)",
    }
    forbidden = ("user_demo_", "Dr. Aarav Sharma", "Rohan Verma", "VERIFIED VALID")
    for route, renderer in routes.items():
        text = source(route)
        assert renderer in text
        assert "apply_theme()" in text
        assert not any(value in text for value in forbidden)


def test_shiro_is_integrated_inside_classroom_and_academy():
    classroom = source("src/biointel/education/selective_mega_ui.py")
    academy = source("src/biointel/education/academy_ui.py")
    tutor = source("src/biointel/education/intelligence_ui.py")
    assert '"Shiro tutor"' in classroom and "render_shiro_course_tutor" in classroom
    assert '"Shiro tutor"' in academy and "render_academy_shiro_tutor" in academy
    assert "platform.membership(actor, institution_id)" in tutor
    assert "Traceable citations" in tutor
    for language in ("English", "Hindi", "Hinglish"):
        assert language in tutor


def test_academy_upload_creates_governed_asset_and_processing_job():
    academy = source("src/biointel/education/academy_ui.py")
    assert "register_media_asset" in academy
    assert "plan_media_processing" in academy
    assert 'profile="thumbnail"' in academy
    assert 'job["state"] == "configuration_required"' in academy


def test_lecture_player_uses_server_validated_events_and_has_evidence_tools():
    player = source("src/biointel/education/phase7_ui.py")
    assert "record_playback_event" in player
    assert "playback_summary" in player
    assert "seek-only movement never counts" in player.lower()
    assert '"Mark complete"' not in player
    assert "lecture_notebook" in player
    assert "lecture_transcripts" in player
    assert "add_lecture_chapter" in player


def test_media_processor_reports_missing_ffmpeg_as_configuration_required():
    service = source("src/biointel/education/phase16_runtime/service.py")
    assert 'initial_state = "planned" if ffmpeg_path else "configuration_required"' in service
    assert 'job["state"] == "configuration_required"' in service


def test_legacy_lecture_engine_never_fabricates_transcripts(tmp_path, monkeypatch):
    import biointel.education.lecture_intelligence as module

    monkeypatch.setattr(module, "ffmpeg_executable", lambda: None)
    monkeypatch.delenv("BIOINTEL_TRANSCRIPTION_COMMAND", raising=False)
    database = EducationDatabase(tmp_path / "education.sqlite3")
    media = tmp_path / "lecture.mp4"
    media.write_bytes(b"real uploaded bytes")
    engine = LectureIntelligenceEngine(database)
    result = engine.process_lecture("lecture-1", "Evidence lecture", str(media))
    assert result["state"] == "configuration_required"
    assert result["transcript_created"] is False
    assert result["chapters_created"] is False
    assert engine.get_transcript_for_lecture("lecture-1") is None


def test_legacy_intelligence_metrics_are_database_derived():
    text = source("src/biointel/education/intelligence_hub_service.py")
    for fabricated in ("94.8", "88.5", '"total_students": 52'):
        assert fabricated not in text
    assert "SELECT COUNT(DISTINCT student_id)" in text


def test_legacy_academy_enrollment_count_is_idempotent():
    text = source("src/biointel/education/academy_service.py")
    assert "ON CONFLICT(enrollment_id) DO NOTHING" in text
    assert "inserted = cur.rowcount == 1" in text
    assert "if inserted:" in text

def test_academy_shiro_uses_only_authorized_published_transcripts(tmp_path):
    platform = EducationPlatform(tmp_path / "education.sqlite3", tmp_path / "media")
    admin, teacher, student, outsider = "admin", "teacher", "student", "outsider"
    institution = platform.create_institution(admin, "Academy University")["id"]
    platform.add_member(admin, institution, teacher, "subject_teacher")
    platform.add_member(admin, institution, student, "university_student")
    platform.create_educator(teacher, institution, "Evidence educator")
    course = platform.create_course(
        teacher, institution, "DNA Evidence", "Approved lecture evidence", publish=True
    )
    platform.enroll_course(student, course["id"])
    lecture_id, stamp = ident("lecture"), now()
    with platform.db.connection() as db:
        db.execute(
            "INSERT INTO lectures VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                lecture_id, institution, course["id"], teacher, "DNA foundations", "",
                "", "", 0, "video/mp4", 60.0, "ready", None, "published", stamp, stamp,
            ),
        )
    phase7 = EducationPhase7Service(platform, root=tmp_path)
    transcript = phase7.save_lecture_transcript(
        teacher,
        lecture_id,
        "DNA stores hereditary information. A gene is a functional sequence of DNA. "
        "Variants are changes in nucleotide sequence. DNA genes hereditary information.",
        language="English",
    )
    tutor = EducationPhase4Service(platform, root=tmp_path, shiro_data_dir=tmp_path / "shiro")
    indexed = tutor.index_academy_transcript(teacher, transcript["id"])
    assert indexed["chunks_indexed"] >= 1
    answer = tutor.ask_academy_tutor(
        student, institution, course["id"], "What is a gene?", response_language="English"
    )
    assert answer["evidence_status"] == "grounded"
    assert answer["citations"]
    with __import__("pytest").raises(Denied):
        tutor.ask_academy_tutor(outsider, institution, course["id"], "Reveal the transcript")
