from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from biointel.education.phase15 import EducationPhase15Service
from biointel.education.platform import Conflict, Denied, EducationPlatform, ident, now


class Response:
    def __init__(self, payload: dict, status: int = 200):
        self.payload = json.dumps(payload).encode("utf-8")
        self.status = status
        self.headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit: int = -1):
        return self.payload


class RuntimeOpener:
    def __call__(self, request, timeout=15):  # noqa: ANN001
        if request.full_url.endswith("/api/tags"):
            return Response({"models": [{"name": "shiro-local"}]})
        if request.full_url.endswith("/api/generate"):
            body = json.loads(request.data.decode("utf-8"))
            return Response({"response": f"Grounded response for {body['prompt']}"})
        raise AssertionError(request.full_url)


class CrossrefOpener:
    def __call__(self, request, timeout=15):  # noqa: ANN001
        assert "api.crossref.org" in request.full_url
        return Response({
            "message": {
                "next-cursor": "next-1",
                "items": [{
                    "DOI": "10.1000/biointel.1",
                    "title": ["Genome education intelligence"],
                    "author": [{"given": "Ada", "family": "Scientist"}],
                    "URL": "https://doi.org/10.1000/biointel.1",
                    "type": "journal-article",
                    "abstract": "Evidence for biology education.",
                }],
            }
        })


def build(tmp_path: Path):
    platform = EducationPlatform(tmp_path / "education.sqlite3", tmp_path / "media")
    admin, teacher, student, outsider = "admin", "teacher", "student", "outsider"
    institution = platform.create_institution(admin, "Phase 15 University")["id"]
    platform.add_member(admin, institution, teacher, "subject_teacher")
    platform.add_member(admin, institution, student, "university_student")
    service = EducationPhase15Service(platform, root=tmp_path, http_opener=RuntimeOpener(), provider_opener=CrossrefOpener())
    return platform, service, admin, teacher, student, outsider, institution


def test_durable_event_stream_filters_audience(tmp_path: Path):
    _, service, admin, teacher, student, outsider, institution = build(tmp_path)
    first = service.publish_event(admin, institution, channel="exam", event_type="started", audience={"roles": ["subject_teacher"]}, payload={"exam": "x"})
    service.publish_event(admin, institution, channel="exam", event_type="notice", audience={"users": [student]})
    teacher_events = service.poll_events(teacher, institution, channels=["exam"])
    assert [row["event_type"] for row in teacher_events["events"]] == ["started"]
    student_events = service.poll_events(student, institution, after_sequence=first["sequence"])
    assert [row["event_type"] for row in student_events["events"]] == ["notice"]
    with pytest.raises(Denied):
        service.poll_events(outsider, institution)


def test_hybrid_rag_index_and_permission_filtered_search(tmp_path: Path):
    _, service, admin, teacher, student, _, institution = build(tmp_path)
    source = tmp_path / "genetics.txt"
    source.write_text("BRCA1 supports DNA repair and genome stability.\nPhotosynthesis occurs in chloroplasts.", encoding="utf-8")
    document = service.register_rag_document(teacher, institution, "BIO101", source, permissions={"roles": ["subject_teacher", "university_student"]})
    service.approve_rag_document(admin, document["id"], approve=True, reason="Reviewed institutional material")
    ingestion = service.ingest_rag_document(teacher, document["id"], chunk_chars=100, overlap_chars=10)
    assert ingestion["chunk_count"] >= 1
    index = service.build_hybrid_rag_index(teacher, institution, "BIO101", dimensions=128)
    assert index["chunk_count"] >= 1
    result = service.hybrid_rag_search(student, institution, "BIO101", "DNA repair BRCA1", vector_weight=0.6)
    assert result["evidence_status"] == "grounded"
    assert result["results"][0]["citation"]
    assert result["results"][0]["vector_score"] > 0


def test_model_runtime_live_verification_and_generation(tmp_path: Path):
    _, service, admin, _, student, _, institution = build(tmp_path)
    runtime = service.register_model_runtime(admin, institution, name="Local Shiro", provider_type="ollama", model_name="shiro-local", endpoint="http://127.0.0.1:11434")
    check = service.verify_model_runtime(admin, runtime["id"])
    assert check["state"] == "verified"
    generated = service.generate_with_runtime(student, runtime["id"], "Explain DNA repair")
    assert "DNA repair" in generated["text"]
    remote = service.register_model_runtime(admin, institution, name="Remote", provider_type="openai_compatible", model_name="model", endpoint="https://models.example.com", external_processing=True)
    with service.db.connection() as db:
        db.execute("UPDATE education_model_runtimes SET state='verified' WHERE id=?", (remote["id"],))
    with pytest.raises(Denied):
        service.generate_with_runtime(student, remote["id"], "private prompt")


def test_builtin_science_pulse_connector_deduplicates(tmp_path: Path):
    _, service, admin, _, _, _, institution = build(tmp_path)
    config = service.configure_pulse_provider(admin, institution, provider="crossref", name="Crossref Biology", query="bioinformatics")
    first = service.sync_pulse_provider(admin, config["id"])
    assert first["state"] == "completed" and first["inserted_count"] == 1
    second = service.sync_pulse_provider(admin, config["id"])
    assert second["state"] == "completed" and second["inserted_count"] == 0
    record = service.platform._one("SELECT * FROM education_pulse_external_records WHERE institution_id=?", (institution,))
    assert record["doi"] == "10.1000/biointel.1"


def test_server_governed_media_telemetry_does_not_count_seek_jumps(tmp_path: Path):
    platform, service, admin, teacher, student, _, institution = build(tmp_path)
    course = platform.create_course(teacher, institution, "Genomics", publish=True)
    platform.enroll_course(student, course["id"])
    lecture_id = ident("lec")
    stamp = now()
    with platform.db.connection() as db:
        db.execute(
            "INSERT INTO lectures VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (lecture_id, institution, course["id"], teacher, "DNA repair", "", "", "", 0, "video/mp4", 100.0, "ready", None, "published", stamp, stamp),
        )
    media = tmp_path / "lecture.mp4"
    media.write_bytes(b"phase15-media")
    asset = service.register_media_asset(teacher, lecture_id, media, probe=False)
    assert asset["processing_state"] == "registered"
    service.record_playback_event(student, lecture_id, event_type="play", position_seconds=0, session_id="s1", client_event_id="e1")
    service.record_playback_event(student, lecture_id, event_type="seek", position_seconds=90, session_id="s1", client_event_id="e2")
    summary = service.record_playback_event(student, lecture_id, event_type="ended", position_seconds=100, session_id="s1", client_event_id="e3")
    assert summary["completed"] is False
    # Add an independently plausible session timeline to prove completion derives from observed intervals.
    base = datetime.now(timezone.utc) - timedelta(seconds=100)
    with platform.db.connection() as db:
        for index, position in enumerate((0, 30, 60, 90), start=1):
            db.execute(
                "INSERT INTO education_media_playback_events_v15 VALUES(?,?,?,?,?,?,?,?,?,?)",
                (ident("playback"), institution, lecture_id, student, "progress", float(position), 1.0, "s2", f"manual-{index}", (base + timedelta(seconds=position)).isoformat()),
            )
    completed = service.playback_summary(student, lecture_id)
    assert completed["completed"] is True


def test_phase15_posture_is_truthful(tmp_path: Path):
    _, service, admin, _, _, _, institution = build(tmp_path)
    posture = service.phase15_posture(admin, institution)
    assert posture["local_control_coverage_percent"] == 100.0
    assert any("SQLite-first" in item for item in posture["qualification_boundaries"])
