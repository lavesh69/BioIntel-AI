from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.phase15 import EducationPhase15Service  # noqa: E402
from biointel.education.platform import Denied, EducationPlatform, ident, now  # noqa: E402


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
            return Response({"response": f"Verified local answer: {body['prompt']}"})
        raise AssertionError(request.full_url)


class CrossrefOpener:
    def __call__(self, request, timeout=15):  # noqa: ANN001
        return Response({"message": {"next-cursor": "next", "items": [{
            "DOI": "10.1000/phase15.1", "title": ["Phase 15 bioinformatics evidence"],
            "author": [{"given": "A", "family": "Researcher"}],
            "URL": "https://doi.org/10.1000/phase15.1", "type": "journal-article",
            "abstract": "Scientific metadata evidence.",
        }]}})


class Verifier:
    def __init__(self):
        self.controls: list[dict] = []

    def require(self, name: str, condition: bool, evidence=None):
        self.controls.append({"name": name, "passed": bool(condition), "evidence": evidence})
        if not condition:
            raise AssertionError(name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "EDUCATION_PHASE15_VERIFICATION.json"))
    args = parser.parse_args()
    verifier = Verifier()
    with tempfile.TemporaryDirectory(prefix="biointel-phase15-") as temporary:
        temp = Path(temporary)
        platform = EducationPlatform(temp / "education.sqlite3", temp / "media")
        admin, teacher, student = "admin", "teacher", "student"
        institution = platform.create_institution(admin, "Phase 15 Qualification University")["id"]
        platform.add_member(admin, institution, teacher, "subject_teacher")
        platform.add_member(admin, institution, student, "university_student")
        service = EducationPhase15Service(platform, root=temp, http_opener=RuntimeOpener(), provider_opener=CrossrefOpener())

        verifier.require("migration_applied", platform._one("SELECT id FROM education_migrations WHERE id='education_phase15_runtime_intelligence_v1'") is not None)
        event = service.publish_event(admin, institution, channel="exam", event_type="started", audience={"roles": ["subject_teacher"]}, payload={"exam_id": "exam-1"})
        verifier.require("durable_event_sequence", int(event["sequence"]) >= 1, event)
        verifier.require("audience_event_visible", service.poll_events(teacher, institution)["event_count"] == 1)
        verifier.require("audience_event_hidden", service.poll_events(student, institution)["event_count"] == 0)
        try:
            service.poll_events("outsider", institution)
            outsider_blocked = False
        except Denied:
            outsider_blocked = True
        verifier.require("event_tenant_access", outsider_blocked)

        source = temp / "evidence.txt"
        source.write_text("BRCA1 participates in DNA repair and genome stability. Chloroplasts support photosynthesis.", encoding="utf-8")
        document = service.register_rag_document(teacher, institution, "BIO101", source, permissions={"roles": ["subject_teacher", "university_student"]})
        service.approve_rag_document(admin, document["id"], approve=True, reason="Qualified source")
        ingestion = service.ingest_rag_document(teacher, document["id"], chunk_chars=100, overlap_chars=10)
        verifier.require("approved_rag_ingested", ingestion["chunk_count"] >= 1, ingestion)
        index = service.build_hybrid_rag_index(teacher, institution, "BIO101", dimensions=128)
        verifier.require("hybrid_index_ready", index["state"] == "ready" and index["chunk_count"] >= 1, index)
        search = service.hybrid_rag_search(student, institution, "BIO101", "BRCA1 DNA repair", vector_weight=0.6)
        verifier.require("hybrid_search_grounded", search["evidence_status"] == "grounded" and search["result_count"] >= 1, search)
        verifier.require("hybrid_scores_present", all("lexical_score" in row and "vector_score" in row for row in search["results"]))
        verifier.require("citation_hash_present", bool(search["results"][0]["citation"] and search["results"][0]["document_sha256"]))

        runtime = service.register_model_runtime(admin, institution, name="Local Shiro", provider_type="ollama", model_name="shiro-local", endpoint="http://127.0.0.1:11434")
        verifier.require("model_runtime_configured", runtime["state"] == "configured")
        check = service.verify_model_runtime(admin, runtime["id"])
        verifier.require("model_runtime_verified", check["state"] == "verified", check)
        generated = service.generate_with_runtime(student, runtime["id"], "Explain DNA repair")
        verifier.require("model_generation_transport", "DNA repair" in generated["text"] and generated["external_processing"] is False, generated)

        config = service.configure_pulse_provider(admin, institution, provider="crossref", name="Crossref", query="bioinformatics")
        sync = service.sync_pulse_provider(admin, config["id"])
        verifier.require("pulse_provider_completed", sync["state"] == "completed", sync)
        verifier.require("pulse_provider_inserted", sync["inserted_count"] == 1, sync)
        second = service.sync_pulse_provider(admin, config["id"])
        verifier.require("pulse_provider_deduplicated", second["inserted_count"] == 0, second)
        record = platform._one("SELECT * FROM education_pulse_external_records WHERE institution_id=?", (institution,))
        verifier.require("pulse_normalized_record", record["doi"] == "10.1000/phase15.1", record)

        course = platform.create_course(teacher, institution, "Genomics", publish=True)
        platform.enroll_course(student, course["id"])
        lecture_id, stamp = ident("lec"), now()
        with platform.db.connection() as db:
            db.execute("INSERT INTO lectures VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (lecture_id, institution, course["id"], teacher, "Lecture", "", "", "", 0, "video/mp4", 100.0, "ready", None, "published", stamp, stamp))
        media = temp / "lecture.mp4"
        media.write_bytes(b"phase15-media")
        asset = service.register_media_asset(teacher, lecture_id, media, probe=False)
        verifier.require("media_asset_registered", asset["processing_state"] == "registered", asset)
        service.record_playback_event(student, lecture_id, event_type="play", position_seconds=0, session_id="s1", client_event_id="e1")
        service.record_playback_event(student, lecture_id, event_type="seek", position_seconds=90, session_id="s1", client_event_id="e2")
        seek_summary = service.record_playback_event(student, lecture_id, event_type="ended", position_seconds=100, session_id="s1", client_event_id="e3")
        verifier.require("seek_does_not_complete", seek_summary["completed"] is False, seek_summary)
        base = datetime.now(timezone.utc) - timedelta(seconds=100)
        with platform.db.connection() as db:
            for idx, position in enumerate((0, 30, 60, 90), start=1):
                db.execute("INSERT INTO education_media_playback_events_v15 VALUES(?,?,?,?,?,?,?,?,?,?)", (ident("playback"), institution, lecture_id, student, "progress", float(position), 1.0, "s2", f"manual-{idx}", (base + timedelta(seconds=position)).isoformat()))
        summary = service.playback_summary(student, lecture_id)
        verifier.require("observed_playback_completes", summary["completed"] is True, summary)
        verifier.require("playback_policy_visible", "seek-only" in summary["policy"])

        posture = service.phase15_posture(admin, institution)
        verifier.require("phase15_posture_100", posture["local_control_coverage_percent"] == 100.0, posture)
        verifier.require("phase15_truth_boundaries", len(posture["qualification_boundaries"]) >= 5, posture["qualification_boundaries"])

        verifier.require("phase15_page", (ROOT / "pages" / "353_BioIntel_Production_Runtime_and_Research_Intelligence_Center.py").is_file())
        verifier.require("phase15_ui", (SRC / "biointel" / "education" / "phase15_ui.py").is_file())
        verifier.require("phase15_worker", (ROOT / "scripts" / "run_education_phase15_worker.py").is_file())
        verifier.require("phase15_navigation", "353_BioIntel_Production_Runtime_and_Research_Intelligence_Center.py" in (SRC / "biointel" / "education" / "experience.py").read_text(encoding="utf-8"))
        api_text = (SRC / "biointel" / "education" / "api.py").read_text(encoding="utf-8")
        routes = ["phase15/events/stream", "phase15/rag-indexes", "phase15/rag-search", "phase15/model-runtimes", "phase15/pulse-providers", "phase15/lectures/{lecture_id}/playback-events", "phase15/posture"]
        verifier.require("phase15_api_contract", all(route in api_text for route in routes), routes)
        verifier.require("phase15_sse_transport", "text/event-stream" in api_text and "StreamingResponse" in api_text)
        verifier.require("phase15_modular_architecture", all((SRC / "biointel" / "education" / "phase15_runtime" / name).is_file() for name in ("schema.py", "vectors.py", "providers.py", "service.py")))

    passed = sum(1 for item in verifier.controls if item["passed"])
    report = {
        "schema": "biointel.education-phase15-verification.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed == len(verifier.controls),
        "passed_controls": passed,
        "total_controls": len(verifier.controls),
        "controls": verifier.controls,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "passed_controls", "total_controls")}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
