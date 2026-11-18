from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.phase16 import EducationPhase16Service  # noqa: E402
from biointel.education.platform import EducationPlatform, ident, now  # noqa: E402


class Verifier:
    def __init__(self): self.controls: list[dict] = []
    def require(self, name: str, condition: bool, evidence=None):
        self.controls.append({"name": name, "passed": bool(condition), "evidence": evidence})
        if not condition: raise AssertionError(name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "EDUCATION_PHASE16_VERIFICATION.json"))
    args = parser.parse_args(); verifier = Verifier()
    with tempfile.TemporaryDirectory(prefix="biointel-phase16-") as temporary:
        temp = Path(temporary)
        platform = EducationPlatform(temp / "education.sqlite3", temp / "media")
        admin, teacher, student = "admin", "teacher", "student"
        institution = platform.create_institution(admin, "Phase 16 Qualification University")["id"]
        platform.add_member(admin, institution, teacher, "subject_teacher")
        platform.add_member(admin, institution, student, "university_student")
        service = EducationPhase16Service(platform, root=temp)
        verifier.require("migration_applied", platform._one("SELECT id FROM education_migrations WHERE id='education_phase16_completion_v1'") is not None)

        consumer = service.register_event_consumer(teacher, institution, consumer_key="desktop")
        verifier.require("consumer_registered", consumer["state"] == "active", consumer)
        service.publish_event(admin, institution, channel="exam", event_type="started", audience={"roles": ["subject_teacher"]})
        consumed = service.consume_events(teacher, consumer["id"], channels=["exam"])
        verifier.require("consumer_received_event", consumed["event_count"] == 1, consumed)
        verifier.require("consumer_ack_cursor", service.consume_events(teacher, consumer["id"], channels=["exam"])["event_count"] == 0)
        verifier.require("consumer_heartbeat", service.heartbeat_event_consumer(teacher, consumer["id"])["heartbeat_at"])
        verifier.require("event_cleanup", service.cleanup_event_stream(admin, institution, retention_days=14)["retention_days"] == 14)

        source = temp / "evidence.txt"
        source.write_text("BRCA1 participates in DNA repair and genome stability. TP53 controls checkpoints. Chloroplasts perform photosynthesis.", encoding="utf-8")
        document = service.register_rag_document(teacher, institution, "BIO101", source, permissions={"roles": ["subject_teacher", "university_student"]})
        service.approve_rag_document(admin, document["id"], approve=True, reason="Reviewed")
        service.ingest_rag_document(teacher, document["id"], chunk_chars=70, overlap_chars=5)
        service.build_hybrid_rag_index(teacher, institution, "BIO101", dimensions=128)
        search = service.advanced_rag_search(student, institution, "BIO101", "BRCA1 DNA repair", limit=3)
        verifier.require("mmr_search_grounded", search["evidence_status"] == "grounded", search)
        verifier.require("mmr_rank_and_score", search["results"][0]["rank"] == 1 and "mmr_score" in search["results"][0])
        case = service.create_rag_evaluation_case(teacher, institution, project_id="BIO101", query="BRCA1 DNA repair", expected_document_ids=[document["id"]])
        verifier.require("rag_eval_case", bool(case["id"]), case)
        evaluation = service.run_rag_evaluation(teacher, institution, "BIO101", top_k=3)
        verifier.require("rag_recall", evaluation["recall_at_k"] == 1.0, evaluation)
        verifier.require("rag_mrr", evaluation["mean_reciprocal_rank"] > 0, evaluation)

        record_id, stamp = ident("pulse"), now()
        with platform.db.connection() as db:
            db.execute("INSERT INTO education_pulse_external_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (record_id, institution, "crossref", "x1", "10.1/x", "", "CRISPR genome editing", "CRISPR evidence", "[]", "https://example.org", stamp, "journal", "{}", stamp, stamp))
        rule = service.create_pulse_alert_rule(teacher, institution, name="CRISPR watch", query_terms=["crispr"], providers=["crossref"])
        verifier.require("pulse_rule", rule["state"] == "active", rule)
        matched = service.evaluate_pulse_alerts(teacher, institution)
        verifier.require("pulse_alert_match", matched["new_hits"] == 1, matched)
        hits = service.pulse_alert_hits(student, institution, unread_only=True)
        verifier.require("pulse_alert_visible", len(hits) == 1, hits)
        verifier.require("pulse_alert_read", service.mark_pulse_alert_read(student, hits[0]["id"])["state"] == "read")

        fasta = temp / "sequences.fasta"
        fasta.write_text(">seq1\nATGAAATTTGGGCCCTAA\n>seq2\nATGAAATTCGGGCCCTAA\n", encoding="utf-8")
        dataset = service.register_scientific_dataset(teacher, institution, fasta, name="DNA demo")
        verifier.require("scientific_dataset", dataset["record_count"] == 2, dataset)
        qc = service.run_sequence_analysis(student, dataset["id"], analysis_type="qc")
        verifier.require("scientific_qc", qc["result"]["record_count"] == 2 and qc["artifact_sha256"], qc)
        translation = service.run_sequence_analysis(student, dataset["id"], analysis_type="translate")
        verifier.require("scientific_translation", translation["result"]["protein"].startswith("MKF"), translation)
        kmer = service.run_sequence_analysis(student, dataset["id"], analysis_type="kmer", parameters={"k": 3})
        verifier.require("scientific_kmer", bool(kmer["result"]["profile"]), kmer)
        alignment = service.run_sequence_analysis(student, dataset["id"], analysis_type="alignment")
        verifier.require("scientific_alignment", alignment["result"]["identity_percent"] > 80, alignment)

        course = platform.create_course(teacher, institution, "Media", publish=True)
        lecture_id = ident("lec")
        with platform.db.connection() as db:
            db.execute("INSERT INTO lectures VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (lecture_id, institution, course["id"], teacher, "Lecture", "", "", "", 0, "video/mp4", 60.0, "ready", None, "published", stamp, stamp))
        media = temp / "lecture.mp4"; media.write_bytes(b"phase16-media")
        asset = service.register_media_asset(teacher, lecture_id, media, probe=False)
        job = service.plan_media_processing(teacher, asset["id"], profile="thumbnail")
        verifier.require("media_job_planned", job["state"] == "planned", job)
        verifier.require("media_command_evidence", "ffmpeg" in job["command_json"], job["command_json"])

        posture = service.phase16_posture(admin, institution)
        verifier.require("posture_100", posture["local_control_coverage_percent"] == 100.0, posture)
        verifier.require("truth_boundaries", len(posture["qualification_boundaries"]) >= 4, posture)
        verifier.require("phase16_page", (ROOT / "pages" / "354_BioIntel_Final_Runtime_Evidence_and_Scientific_Workbench_Center.py").is_file())
        verifier.require("phase16_ui", (SRC / "biointel" / "education" / "phase16_ui.py").is_file())
        verifier.require("phase16_worker", (ROOT / "scripts" / "run_education_phase16_worker.py").is_file())
        verifier.require("phase16_navigation", "354_BioIntel_Final_Runtime_Evidence_and_Scientific_Workbench_Center.py" in (SRC / "biointel" / "education" / "experience.py").read_text(encoding="utf-8"))
        api_text = (SRC / "biointel" / "education" / "api.py").read_text(encoding="utf-8")
        routes = ["phase16/event-consumers", "phase16/rag-search", "phase16/rag-evaluation-cases", "phase16/pulse-alert-rules", "phase16/scientific-datasets", "phase16/media-assets", "phase16/posture"]
        verifier.require("phase16_api_contract", all(route in api_text for route in routes), routes)
        verifier.require("phase16_modular_architecture", all((SRC / "biointel" / "education" / "phase16_runtime" / name).is_file() for name in ("schema.py", "scientific.py", "service.py")))

    passed = sum(1 for row in verifier.controls if row["passed"])
    report = {"schema": "biointel.education-phase16-verification.v1", "generated_at": datetime.now(timezone.utc).isoformat(), "passed": passed == len(verifier.controls), "passed_controls": passed, "total_controls": len(verifier.controls), "controls": verifier.controls}
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "passed_controls", "total_controls")}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__": raise SystemExit(main())
