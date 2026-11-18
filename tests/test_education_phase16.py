from __future__ import annotations

from pathlib import Path

import pytest

from biointel.media_tools import ffmpeg_executable
from biointel.education.phase16 import EducationPhase16Service
from biointel.education.platform import Conflict, EducationPlatform, ident, now


def build(tmp_path: Path):
    platform = EducationPlatform(tmp_path / "education.sqlite3", tmp_path / "media")
    admin, teacher, student = "admin", "teacher", "student"
    institution = platform.create_institution(admin, "Phase 16 University")["id"]
    platform.add_member(admin, institution, teacher, "subject_teacher")
    platform.add_member(admin, institution, student, "university_student")
    return platform, EducationPhase16Service(platform, root=tmp_path), admin, teacher, student, institution


def test_event_consumer_cursor_and_cleanup(tmp_path: Path):
    _, service, admin, teacher, _, institution = build(tmp_path)
    consumer = service.register_event_consumer(teacher, institution, consumer_key="teacher-desktop")
    service.publish_event(admin, institution, channel="exam", event_type="started", audience={"roles": ["subject_teacher"]})
    first = service.consume_events(teacher, consumer["id"], channels=["exam"])
    assert first["event_count"] == 1 and first["acknowledged"] is True
    second = service.consume_events(teacher, consumer["id"], channels=["exam"])
    assert second["event_count"] == 0
    assert service.heartbeat_event_consumer(teacher, consumer["id"])["state"] == "active"
    cleanup = service.cleanup_event_stream(admin, institution, retention_days=1)
    assert cleanup["retention_days"] == 1


def test_mmr_search_and_rag_evaluation(tmp_path: Path):
    _, service, admin, teacher, student, institution = build(tmp_path)
    source = tmp_path / "evidence.txt"
    source.write_text("BRCA1 participates in DNA repair and genome stability.\nTP53 regulates cell-cycle checkpoints.\nPhotosynthesis occurs in chloroplasts.", encoding="utf-8")
    document = service.register_rag_document(teacher, institution, "BIO101", source, permissions={"roles": ["subject_teacher", "university_student"]})
    service.approve_rag_document(admin, document["id"], approve=True, reason="Reviewed")
    service.ingest_rag_document(teacher, document["id"], chunk_chars=70, overlap_chars=5)
    service.build_hybrid_rag_index(teacher, institution, "BIO101", dimensions=128)
    search = service.advanced_rag_search(student, institution, "BIO101", "BRCA1 DNA repair", limit=3, diversity_weight=0.3)
    assert search["evidence_status"] == "grounded" and search["results"][0]["rank"] == 1
    service.create_rag_evaluation_case(teacher, institution, project_id="BIO101", query="BRCA1 DNA repair", expected_document_ids=[document["id"]])
    evaluation = service.run_rag_evaluation(teacher, institution, "BIO101", top_k=3)
    assert evaluation["recall_at_k"] == 1.0 and evaluation["mean_reciprocal_rank"] > 0


def test_pulse_alert_rules_match_and_read(tmp_path: Path):
    platform, service, admin, teacher, _, institution = build(tmp_path)
    stamp = now(); record_id = ident("pulse")
    with platform.db.connection() as db:
        db.execute("INSERT INTO education_pulse_external_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (record_id, institution, "crossref", "x-1", "10.1/x", "", "CRISPR genome editing in bacteria", "CRISPR evidence", "[]", "https://example.org", stamp, "journal", "{}", stamp, stamp))
    service.create_pulse_alert_rule(teacher, institution, name="CRISPR watch", query_terms=["crispr", "genome"], providers=["crossref"])
    result = service.evaluate_pulse_alerts(teacher, institution)
    assert result["new_hits"] == 1
    hits = service.pulse_alert_hits(teacher, institution, unread_only=True)
    assert len(hits) == 1
    assert service.mark_pulse_alert_read(teacher, hits[0]["id"])["state"] == "read"


def test_scientific_workbench_qc_orf_kmer_alignment(tmp_path: Path):
    _, service, _, teacher, student, institution = build(tmp_path)
    source = tmp_path / "sequences.fasta"
    source.write_text(">seq1\nATGAAATTTGGGCCCTAA\n>seq2\nATGAAATTCGGGCCCTAA\n", encoding="utf-8")
    dataset = service.register_scientific_dataset(teacher, institution, source, name="Demo DNA")
    qc = service.run_sequence_analysis(student, dataset["id"], analysis_type="qc")
    assert qc["result"]["record_count"] == 2 and qc["artifact_sha256"]
    translated = service.run_sequence_analysis(student, dataset["id"], analysis_type="translate")
    assert translated["result"]["protein"].startswith("MKF")
    kmers = service.run_sequence_analysis(student, dataset["id"], analysis_type="kmer", parameters={"k": 3})
    assert kmers["result"]["profile"]
    alignment = service.run_sequence_analysis(student, dataset["id"], analysis_type="alignment")
    assert alignment["result"]["identity_percent"] > 80


def test_media_processing_plan_is_honest(tmp_path: Path):
    platform, service, _, teacher, _, institution = build(tmp_path)
    course = platform.create_course(teacher, institution, "Media", publish=True)
    lecture_id, stamp = ident("lec"), now()
    with platform.db.connection() as db:
        db.execute("INSERT INTO lectures VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (lecture_id, institution, course["id"], teacher, "Lecture", "", "", "", 0, "video/mp4", 60.0, "ready", None, "published", stamp, stamp))
    media = tmp_path / "lecture.mp4"; media.write_bytes(b"not-a-real-video")
    asset = service.register_media_asset(teacher, lecture_id, media, probe=False)
    job = service.plan_media_processing(teacher, asset["id"], profile="thumbnail")
    assert job["state"] == "planned" and "ffmpeg" in job["command_json"]
    if ffmpeg_executable():
        assert service.execute_media_processing(teacher, job["id"])["state"] == "failed"
    else:
        with pytest.raises(Conflict):
            service.execute_media_processing(teacher, job["id"])
