from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import biointel.education.local_transcription as local_module
import biointel.education.phase16_runtime.service as service_module
from biointel.education.local_transcription import local_transcription_readiness
from biointel.education.phase16 import EducationPhase16Service
from biointel.education.platform import Conflict, Denied, EducationPlatform, ident, now


def build(tmp_path: Path):
    platform = EducationPlatform(tmp_path / "education.sqlite3", tmp_path / "media")
    admin, teacher, student = "admin", "teacher", "student"
    institution = platform.create_institution(admin, "Full Local University")["id"]
    platform.add_member(admin, institution, teacher, "subject_teacher")
    platform.add_member(admin, institution, student, "university_student")
    course = platform.create_course(teacher, institution, "Real Lectures", publish=True)
    lecture_id, stamp = ident("lecture"), now()
    with platform.db.connection() as db:
        db.execute(
            "INSERT INTO lectures VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (lecture_id, institution, course["id"], teacher, "Lecture", "", "", "", 0,
             "video/mp4", 12.0, "ready", None, "published", stamp, stamp),
        )
    source = tmp_path / "lecture.mp4"
    source.write_bytes(b"real-uploaded-media-evidence")
    service = EducationPhase16Service(platform, root=tmp_path)
    asset = service.register_media_asset(teacher, lecture_id, source, probe=False)
    return platform, service, admin, teacher, student, institution, lecture_id, asset, source


def fake_readiness(root: object = None) -> dict[str, object]:
    return {
        "provider": "local_faster_whisper", "state": "ready", "ready": True,
        "credential_required": False, "network_required_at_runtime": False,
        "ffmpeg_path": "bundled-ffmpeg", "package_version": "1.2.1",
        "model_path": str(Path(str(root or ".")) / "model"),
        "model_manifest_sha256": "model-manifest-sha", "model_revision": "revision",
        "model_license": "MIT", "supported_language_modes": ["auto", "english", "hindi", "hinglish"],
        "reason": "",
    }


def test_readiness_verifies_every_model_file_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    model = tmp_path / "model"
    model.mkdir()
    rows = []
    for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
        path = model / name
        path.write_bytes((name + "-verified").encode())
        rows.append({"path": name, "size_bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (model / "MODEL_MANIFEST_SHA256.json").write_text(json.dumps({
        "model_manifest_sha256": "verified-model-manifest", "revision": "r1", "license": "MIT", "files": rows,
    }), encoding="utf-8")
    monkeypatch.setenv("BIOINTEL_TRANSCRIPTION_MODEL", str(model))
    monkeypatch.setattr(local_module.metadata, "version", lambda _: "1.2.1")
    monkeypatch.setattr(local_module, "ffmpeg_executable", lambda: "C:/bundled/ffmpeg.exe")
    readiness = local_transcription_readiness(tmp_path)
    assert readiness["ready"] is True
    assert readiness["network_required_at_runtime"] is False
    assert readiness["model_manifest_sha256"] == "verified-model-manifest"
    (model / "model.bin").write_bytes(b"tampered")
    (model / "MODEL_MANIFEST_SHA256.json").touch()
    tampered = local_transcription_readiness(tmp_path)
    assert tampered["ready"] is False
    assert "hash mismatch" in tampered["reason"].lower()


def test_real_job_contract_persists_transcript_artifact_and_review_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    platform, service, _, teacher, student, institution, lecture_id, asset, source = build(tmp_path)
    monkeypatch.setattr(service_module, "local_transcription_readiness", fake_readiness)
    monkeypatch.setattr(service_module, "transcribe_local", lambda *args, **kwargs: {
        "schema": "biointel.education.local-transcription.v1", "provider": "local_faster_whisper",
        "provider_version": "1.2.1", "model_path": "model", "model_manifest_sha256": "model-manifest-sha",
        "model_revision": "revision", "requested_language": "auto", "detected_language": "en",
        "language_probability": 0.99, "duration_seconds": 12.0, "duration_after_vad_seconds": 10.0,
        "source_path": str(source), "source_size_bytes": source.stat().st_size,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "compute_type": "int8",
        "cpu_threads": 2, "beam_size": 3, "text": "DNA stores hereditary information.",
        "segments": [{"id": 0, "start": 0.0, "end": 3.0, "text": "DNA stores hereditary information.", "words": []}],
        "segment_count": 1, "generated_at": now(), "network_used": False,
    })
    job = service.plan_lecture_transcription(teacher, lecture_id, language="auto")
    assert job["state"] == "planned" and job["asset_id"] == asset["id"]
    with pytest.raises(Denied):
        service.plan_lecture_transcription(student, lecture_id)
    candidate_job = service.execute_lecture_transcription(teacher, job["id"])
    assert candidate_job["state"] == "review_required" and candidate_job["progress"] == 90
    assert candidate_job["transcript_id"] == ""
    assert platform._one("SELECT COUNT(*) n FROM education_lecture_transcripts WHERE lecture_id=?", (lecture_id,))["n"] == 0
    candidate = service.transcription_candidate(teacher, job["id"])
    assert candidate["text"] == "DNA stores hereditary information."
    approved = service.approve_lecture_transcription(teacher, job["id"])
    assert approved["state"] == "completed" and approved["progress"] == 100
    transcript = platform._one("SELECT * FROM education_lecture_transcripts WHERE id=?", (approved["transcript_id"],))
    assert transcript["body"] == "DNA stores hereditary information."
    evidence = json.loads(approved["evidence_json"])
    artifact = Path(evidence["artifact_path"])
    assert evidence["educator_review_required"] is True and evidence["review_state"] == "approved"
    assert artifact.is_file() and hashlib.sha256(artifact.read_bytes()).hexdigest() == evidence["artifact_sha256"]
    assert json.loads(artifact.read_text(encoding="utf-8"))["segments"][0]["start"] == 0.0

    replacement = service.plan_lecture_transcription(teacher, lecture_id, language="auto")
    service.execute_lecture_transcription(teacher, replacement["id"])
    with pytest.raises(Conflict, match="explicit replacement"):
        service.approve_lecture_transcription(teacher, replacement["id"])
    assert service.approve_lecture_transcription(teacher, replacement["id"], replace_existing=True)["state"] == "completed"


def test_transcription_failure_is_durable_and_never_fabricates_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    platform, service, _, teacher, _, _, lecture_id, _, _ = build(tmp_path)
    monkeypatch.setattr(service_module, "local_transcription_readiness", fake_readiness)
    def fail(*args, **kwargs):
        raise RuntimeError("No speech was detected; no transcript was persisted.")
    monkeypatch.setattr(service_module, "transcribe_local", fail)
    job = service.plan_lecture_transcription(teacher, lecture_id)
    with pytest.raises(RuntimeError, match="No speech"):
        service.execute_lecture_transcription(teacher, job["id"])
    failed = platform._one("SELECT * FROM education_transcription_jobs_v16 WHERE id=?", (job["id"],))
    assert failed["state"] == "failed" and failed["transcript_id"] == ""
    assert platform._one("SELECT COUNT(*) n FROM education_lecture_transcripts WHERE lecture_id=?", (lecture_id,))["n"] == 0


def test_full_upgrade_surfaces_are_real_and_api_accessible():
    root = Path(__file__).resolve().parents[1]
    academy = (root / "src/biointel/education/academy_ui.py").read_text(encoding="utf-8")
    phase16 = (root / "src/biointel/education/phase16_ui.py").read_text(encoding="utf-8")
    api = (root / "src/biointel/education/api.py").read_text(encoding="utf-8")
    worker = (root / "scripts/run_education_transcription_worker.py").read_text(encoding="utf-8")
    assert "plan_lecture_transcription" in academy
    assert "execute_lecture_transcription" in phase16
    assert "educator review" in phase16.lower()
    assert "/phase16/transcription-jobs/{job_id}/execute" in api
    assert "/phase16/transcription-jobs/{job_id}/approve" in api
    assert "execute_lecture_transcription" in worker
    assert "demo transcript" not in (academy + phase16).lower()

def test_r15_packager_keeps_required_installer_seed_manifest():
    root = Path(__file__).resolve().parents[1]
    packager = (root / "scripts/package_education_full_upgrade_r15.py").read_text(encoding="utf-8")
    installer = (root / "scripts/install_windows_step206.py").read_text(encoding="utf-8")
    required = "release/USER_DATA_SEED_MANIFEST_SHA256.json"
    assert required in packager
    assert "SEED_MANIFEST" in packager
    assert required in installer