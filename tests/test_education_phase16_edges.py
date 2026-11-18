from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from biointel.education.phase16 import EducationPhase16Service
from biointel.education.phase16_runtime.scientific import (
    find_orfs, global_alignment, kmer_profile, parse_fasta, parse_fastq,
    reverse_complement, sequence_qc,
)
from biointel.education.platform import Conflict, Denied, EducationError, Missing, EducationPlatform, ident, now


def build(tmp_path: Path):
    platform = EducationPlatform(tmp_path / "education.sqlite3", tmp_path / "media")
    institution = platform.create_institution("admin", "Edge University")["id"]
    platform.add_member("admin", institution, "teacher", "subject_teacher")
    platform.add_member("admin", institution, "student", "university_student")
    return platform, EducationPhase16Service(platform, root=tmp_path), institution


def test_scientific_parser_and_validation_edges():
    assert parse_fasta("ACGU\n") == [{"name": "sequence-1", "sequence": "ACGT"}]
    fastq = parse_fastq("@r1\nACGT\n+\nIIII\n")
    qc = sequence_qc(fastq)
    assert qc["mean_phred"] == 40 and qc["q30_percent"] == 100
    with pytest.raises(ValueError): parse_fastq("@r\nACG\n+")
    with pytest.raises(ValueError): parse_fastq("r\nACG\n+\nIII")
    with pytest.raises(ValueError): parse_fastq("@r\nACG\n+\nII")
    assert reverse_complement("ATGC") == "GCAT"
    assert find_orfs("ATG" + "AAA" * 25 + "TAA", 20)[0]["aa_length"] >= 26
    with pytest.raises(ValueError): kmer_profile("ACGT", 13)
    with pytest.raises(ValueError): global_alignment("", "ACG")
    with pytest.raises(ValueError): global_alignment("A" * 2001, "A")
    assert "-" in global_alignment("ACGT", "AGT")["right"] or "-" in global_alignment("ACGT", "AGT")["left"]


def test_consumer_validation_and_ownership(tmp_path: Path):
    _, service, institution = build(tmp_path)
    with pytest.raises(EducationError): service.register_event_consumer("teacher", institution, consumer_key="")
    consumer = service.register_event_consumer("teacher", institution, consumer_key="desktop")
    with pytest.raises(Denied): service.consume_events("student", consumer["id"])
    with pytest.raises(Denied): service.heartbeat_event_consumer("student", consumer["id"])
    service.publish_event("admin", institution, channel="x", event_type="y", audience={"roles": ["subject_teacher"]})
    peek = service.consume_events("teacher", consumer["id"], acknowledge=False)
    assert peek["event_count"] == 1 and peek["acknowledged"] is False
    assert service.consume_events("teacher", consumer["id"])["event_count"] == 1


def test_rag_and_alert_error_paths(tmp_path: Path):
    platform, service, institution = build(tmp_path)
    with pytest.raises(EducationError): service.create_rag_evaluation_case("teacher", institution, project_id="x", query="?", expected_document_ids=[])
    with pytest.raises(Conflict): service.run_rag_evaluation("teacher", institution, "x")
    rule = service.create_pulse_alert_rule("teacher", institution, name="Only PubMed", query_terms=["genome"], providers=["pubmed"])
    assert rule["state"] == "active"
    stamp = now()
    with platform.db.connection() as db:
        db.execute("INSERT INTO education_pulse_external_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (ident("p"), institution, "crossref", "x", "", "", "Genome paper", "", "[]", "https://example.org", stamp, "journal", "{}", stamp, stamp))
    assert service.evaluate_pulse_alerts("teacher", institution)["new_hits"] == 0
    with pytest.raises(Missing): service.mark_pulse_alert_read("student", "missing")


def test_dataset_fastq_duplicate_tamper_and_analysis_errors(tmp_path: Path):
    _, service, institution = build(tmp_path)
    bad = tmp_path / "data.bin"; bad.write_bytes(b"x")
    with pytest.raises(EducationError): service.register_scientific_dataset("teacher", institution, bad)
    fastq = tmp_path / "reads.fastq"; fastq.write_text("@r1\nATGAAATAG\n+\nIIIIIIIII\n", encoding="utf-8")
    dataset = service.register_scientific_dataset("teacher", institution, fastq)
    assert service.register_scientific_dataset("teacher", institution, fastq)["id"] == dataset["id"]
    orfs = service.run_sequence_analysis("student", dataset["id"], analysis_type="orf", parameters={"minimum_aa": 2})
    assert "orfs" in orfs["result"]
    with pytest.raises(Conflict): service.run_sequence_analysis("student", dataset["id"], analysis_type="alignment")
    with pytest.raises(EducationError): service.run_sequence_analysis("student", dataset["id"], analysis_type="unknown")
    Path(dataset["stored_path"]).write_text("tampered", encoding="utf-8")
    with pytest.raises(Conflict): service.run_sequence_analysis("student", dataset["id"], analysis_type="qc")
    with pytest.raises(Missing): service.run_sequence_analysis("student", "missing", analysis_type="qc")


def test_media_plan_and_execution_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    platform, service, institution = build(tmp_path)
    with pytest.raises(Missing): service.plan_media_processing("teacher", "missing", profile="thumbnail")
    course = platform.create_course("teacher", institution, "Media", publish=True)
    lecture_id, stamp = ident("lec"), now()
    with platform.db.connection() as db:
        db.execute("INSERT INTO lectures VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (lecture_id, institution, course["id"], "teacher", "Lecture", "", "", "", 0, "video/mp4", 60.0, "ready", None, "published", stamp, stamp))
    media = tmp_path / "lecture.mp4"; media.write_bytes(b"media")
    asset = service.register_media_asset("teacher", lecture_id, media, probe=False)
    with pytest.raises(EducationError): service.plan_media_processing("teacher", asset["id"], profile="bad")
    for profile in ("mp4_720p", "hls_720p"):
        assert service.plan_media_processing("teacher", asset["id"], profile=profile)["profile"] == profile

    import biointel.education.phase16_runtime.service as module
    monkeypatch.setattr(module.shutil, "which", lambda _name: "/fake/ffmpeg")
    job = service.plan_media_processing("teacher", asset["id"], profile="thumbnail")
    def fake_run(command, **_kwargs):
        Path(command[-1]).write_bytes(b"image")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    completed = service.execute_media_processing("teacher", job["id"])
    assert completed["state"] == "completed" and completed["progress"] == 100
    with pytest.raises(Missing): service.execute_media_processing("teacher", "missing")
