from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from biointel.education.phase15 import EducationPhase15Service
from biointel.education.phase15_runtime.service import _decode, _endpoint, _environment_secret
from biointel.education.platform import Conflict, Denied, EducationError, Missing, EducationPlatform, ident, now


class Response:
    def __init__(self, payload: dict, status: int = 200):
        self.payload = json.dumps(payload).encode()
        self.status = status
        self.headers = {"Content-Type": "application/json"}
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self, _limit=-1): return self.payload


class OpenAICompatible:
    def __call__(self, request, timeout=15):  # noqa: ANN001
        if request.full_url.endswith("/v1/models"):
            return Response({"data": [{"id": "local-model"}]})
        if request.full_url.endswith("/v1/chat/completions"):
            return Response({"choices": [{"message": {"content": "Local compatible answer"}}]})
        raise AssertionError(request.full_url)


class FailingOpener:
    def __call__(self, request, timeout=15):  # noqa: ANN001
        raise OSError("offline")


def build(tmp_path: Path, opener=None, provider=None):
    platform = EducationPlatform(tmp_path / "e.sqlite3", tmp_path / "media")
    institution = platform.create_institution("admin", "Edge University")["id"]
    platform.add_member("admin", institution, "teacher", "subject_teacher")
    platform.add_member("admin", institution, "student", "university_student")
    service = EducationPhase15Service(platform, root=tmp_path, http_opener=opener, provider_opener=provider)
    return platform, service, institution


def test_helpers_and_endpoint_validation(monkeypatch):
    assert _decode({"x": 1}, {}) == {"x": 1}
    assert _decode("bad", {"fallback": True}) == {"fallback": True}
    assert _environment_secret("") == ""
    with pytest.raises(Conflict): _environment_secret("plain-secret")
    with pytest.raises(EducationError): _environment_secret("env:BAD-NAME")
    with pytest.raises(Conflict): _environment_secret("env:MISSING_PHASE15_SECRET")
    monkeypatch.setenv("PHASE15_SECRET", "token")
    assert _environment_secret("env:PHASE15_SECRET") == "token"
    with pytest.raises(EducationError): _endpoint("http://user:pass@localhost:1")
    with pytest.raises(EducationError): _endpoint("https://localhost:11434")
    with pytest.raises(EducationError): _endpoint("http://example.com", resolve=False)
    parsed, local = _endpoint("https://example.com", resolve=False)
    assert parsed.hostname == "example.com" and local is False


def test_event_validation_and_missing(tmp_path: Path):
    _, service, institution = build(tmp_path)
    with pytest.raises(EducationError):
        service.publish_event("admin", institution, channel="", event_type="x")
    with pytest.raises(EducationError):
        service.publish_event("admin", institution, channel="x", event_type="x", expires_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
    with pytest.raises(Missing): service._event("missing")
    assert service._event_allowed("outsider", institution, "{}") is False


def test_rag_validation_reindex_and_missing_index(tmp_path: Path):
    _, service, institution = build(tmp_path)
    with pytest.raises(EducationError): service.build_hybrid_rag_index("teacher", institution, "none", dimensions=10)
    with pytest.raises(Conflict): service.build_hybrid_rag_index("teacher", institution, "none", dimensions=128)
    with pytest.raises(EducationError): service.hybrid_rag_search("student", institution, "none", " ")
    with pytest.raises(Conflict): service.hybrid_rag_search("student", institution, "none", "query")
    source = tmp_path / "doc.txt"; source.write_text("genome repair evidence", encoding="utf-8")
    doc = service.register_rag_document("teacher", institution, "p", source)
    service.approve_rag_document("admin", doc["id"], approve=True, reason="ok")
    service.ingest_rag_document("teacher", doc["id"])
    first = service.build_hybrid_rag_index("teacher", institution, "p", dimensions=128)
    second = service.build_hybrid_rag_index("teacher", institution, "p", dimensions=128)
    assert first["id"] == second["id"] and second["state"] == "ready"


def test_openai_compatible_runtime_and_consent(tmp_path: Path):
    _, service, institution = build(tmp_path, opener=OpenAICompatible())
    with pytest.raises(EducationError): service.register_model_runtime("admin", institution, name="bad", provider_type="bad", model_name="x")
    with pytest.raises(Conflict): service.register_model_runtime("admin", institution, name="bad-secret", provider_type="ollama", model_name="x", endpoint="http://127.0.0.1:1", secret_reference="plain")
    runtime = service.register_model_runtime("admin", institution, name="compatible", provider_type="openai_compatible", model_name="local-model", endpoint="http://127.0.0.1:8000", external_processing=True)
    with pytest.raises(Conflict): service.generate_with_runtime("student", runtime["id"], "x")
    check = service.verify_model_runtime("admin", runtime["id"])
    assert check["state"] == "verified"
    with pytest.raises(Denied): service.generate_with_runtime("student", runtime["id"], "x")
    result = service.generate_with_runtime("student", runtime["id"], "x", allow_external_processing=True)
    assert result["text"] == "Local compatible answer"


def test_llama_cpp_verification_and_generation_boundary(tmp_path: Path):
    _, service, institution = build(tmp_path)
    if os.name == "nt":
        executable = tmp_path / "llama-cli.cmd"
        executable.write_text("@echo off\r\necho llama.cpp phase15\r\n", encoding="utf-8")
    else:
        executable = tmp_path / "llama-cli"
        executable.write_text("#!/bin/sh\necho llama.cpp phase15\n", encoding="utf-8")
        executable.chmod(0o755)
    runtime = service.register_model_runtime("admin", institution, name="llama", provider_type="llama_cpp", model_name="model.gguf", endpoint=str(executable))
    assert service.verify_model_runtime("admin", runtime["id"])["state"] == "verified"
    with pytest.raises(Conflict): service.generate_with_runtime("student", runtime["id"], "hello")
    with pytest.raises(Missing): service.register_model_runtime("admin", institution, name="missing", provider_type="llama_cpp", model_name="x", endpoint=str(tmp_path / "none"))


def test_runtime_verification_failure_is_evidence(tmp_path: Path):
    _, service, institution = build(tmp_path, opener=FailingOpener())
    runtime = service.register_model_runtime("admin", institution, name="offline", provider_type="ollama", model_name="x", endpoint="http://127.0.0.1:11434")
    check = service.verify_model_runtime("admin", runtime["id"])
    assert check["state"] == "failed" and check["error_text"]
    with pytest.raises(Conflict): service.generate_with_runtime("student", runtime["id"], "x")
    with pytest.raises(Missing): service.verify_model_runtime("admin", "missing")


def test_pulse_validation_and_failure(tmp_path: Path):
    _, service, institution = build(tmp_path, provider=FailingOpener())
    with pytest.raises(EducationError): service.configure_pulse_provider("admin", institution, provider="bad", name="x", query="x")
    config = service.configure_pulse_provider("admin", institution, provider="crossref", name="offline", query="x")
    run = service.sync_pulse_provider("admin", config["id"])
    assert run["state"] == "failed" and run["error_text"]
    with pytest.raises(Missing): service.sync_pulse_provider("admin", "missing")


def test_media_validation_access_and_jump(tmp_path: Path):
    platform, service, institution = build(tmp_path)
    with pytest.raises(Missing): service.register_media_asset("teacher", "missing", tmp_path / "x.mp4")
    course = platform.create_course("teacher", institution, "Course", publish=True)
    lecture_id, stamp = ident("lec"), now()
    with platform.db.connection() as db:
        db.execute("INSERT INTO lectures VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (lecture_id, institution, course["id"], "teacher", "L", "", "", "", 0, "video/mp4", 100.0, "ready", None, "published", stamp, stamp))
    with pytest.raises(EducationError): service.register_media_asset("teacher", lecture_id, tmp_path / "none.mp4", probe=False)
    bad = tmp_path / "bad.txt"; bad.write_text("x")
    with pytest.raises(EducationError): service.register_media_asset("teacher", lecture_id, bad, probe=False)
    video = tmp_path / "v.mp4"; video.write_bytes(b"video")
    service.register_media_asset("teacher", lecture_id, video, probe=False)
    with pytest.raises(Denied): service.playback_summary("student", lecture_id)
    platform.enroll_course("student", course["id"])
    with pytest.raises(EducationError): service.record_playback_event("student", lecture_id, event_type="bad", position_seconds=0, session_id="s", client_event_id="1")
    with pytest.raises(EducationError): service.record_playback_event("student", lecture_id, event_type="play", position_seconds=200, session_id="s", client_event_id="2")
    service.record_playback_event("student", lecture_id, event_type="play", position_seconds=0, session_id="jump", client_event_id="3")
    with pytest.raises(Conflict): service.record_playback_event("student", lecture_id, event_type="progress", position_seconds=80, session_id="jump", client_event_id="4")
    assert service.playback_summary("teacher", lecture_id)["completed"] is False
    with pytest.raises(Missing): service.playback_summary("student", "missing")
