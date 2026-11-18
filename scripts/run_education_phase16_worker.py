from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.paths import education_paths  # noqa: E402
from biointel.education.phase16 import EducationPhase16Service  # noqa: E402
from biointel.education.platform import Conflict, EducationPlatform  # noqa: E402


def execute_job(service: EducationPhase16Service, actor: str, worker_id: str, job: dict[str, Any]) -> dict[str, Any]:
    payload = dict(job.get("payload") or {})
    institution_id = job["institution_id"]
    token = job["lock_token"]
    service.update_job_progress(institution_id, worker_id, job["id"], token, 10, "Phase 16 job accepted")
    job_type = job["job_type"]
    if job_type == "phase15_rag_index":
        service.update_job_progress(institution_id, worker_id, job["id"], token, 40, "Building local semantic vectors")
        return service.build_hybrid_rag_index(actor, institution_id, str(payload["project_id"]), model_name=str(payload.get("model_name", "biointel-hash-embedding-v1")), dimensions=int(payload.get("dimensions", 384)))
    if job_type == "phase15_pulse_sync":
        service.update_job_progress(institution_id, worker_id, job["id"], token, 35, "Synchronizing normalized scientific metadata")
        return service.sync_pulse_provider(actor, str(payload["config_id"]), limit=int(payload.get("limit", 20)))
    if job_type == "phase15_media_probe":
        service.update_job_progress(institution_id, worker_id, job["id"], token, 45, "Probing governed lecture media")
        return service.register_media_asset(actor, str(payload["lecture_id"]), str(payload["source_path"]), probe=True)
    if job_type == "phase15_model_verify":
        return service.verify_model_runtime(actor, str(payload["runtime_id"]))
    if job_type == "phase15_posture":
        return service.phase15_posture(actor, institution_id)
    if job_type == "phase16_rag_evaluation":
        return service.run_rag_evaluation(actor, institution_id, str(payload["project_id"]), top_k=int(payload.get("top_k", 5)))
    if job_type == "phase16_pulse_alerts":
        return service.evaluate_pulse_alerts(actor, institution_id)
    if job_type == "phase16_scientific_analysis":
        return service.run_sequence_analysis(actor, str(payload["dataset_id"]), analysis_type=str(payload["analysis_type"]), parameters=dict(payload.get("parameters") or {}))
    if job_type == "phase16_media_execute":
        return service.execute_media_processing(actor, str(payload["job_id"]), timeout_seconds=int(payload.get("timeout_seconds", 900)))
    if job_type == "phase16_event_cleanup":
        return service.cleanup_event_stream(actor, institution_id, retention_days=int(payload.get("retention_days", 14)))
    if job_type == "phase16_posture":
        return service.phase16_posture(actor, institution_id)
    # Preserve prior worker contracts.
    if job_type == "phase14_outcome_attainment":
        return service.calculate_outcome_attainment(actor, str(payload["outcome_id"]), period_start=payload.get("period_start"), period_end=payload.get("period_end"))
    if job_type == "phase14_psychometrics":
        return service.run_exam_psychometrics(actor, str(payload["exam_id"]))
    if job_type == "phase13_rag_ingest":
        return service.ingest_rag_document(actor, str(payload["document_id"]), chunk_chars=int(payload.get("chunk_chars", 1400)), overlap_chars=int(payload.get("overlap_chars", 180)))
    if job_type == "phase13_timetable_plan":
        return service.generate_timetable_plan(actor, institution_id, **payload)
    if job_type == "phase11_full_backup":
        return service.create_full_backup(actor, institution_id, str(payload.get("label", "scheduled-backup")))
    if job_type == "phase11_generate_report":
        return service.generate_report(actor, institution_id, str(payload.get("report_type", "attendance")), parameters=dict(payload.get("parameters") or {}), output_format=str(payload.get("output_format", "json")))
    if job_type == "phase11_health_snapshot":
        return service.record_health_snapshot(actor, institution_id)
    raise Conflict(f"No Phase 16 worker handler is registered for {job_type}.")


def deliver_one_notification(service: EducationPhase16Service, worker_id: str, channel: str) -> bool:
    item = service.claim_notification(worker_id, channel=channel)
    if not item:
        return False
    token = item["lock_token_plain"]
    if channel in {"in_app", "desktop"}:
        service.complete_notification(worker_id, item["id"], token, state="delivered", response={"transport": channel, "local": True})
        return True
    if channel == "email":
        host = os.environ.get("BIOINTEL_SMTP_HOST", "")
        sender = os.environ.get("BIOINTEL_SMTP_SENDER", "")
        if not host or not sender:
            service.complete_notification(worker_id, item["id"], token, state="failed", error_text="SMTP configuration is missing.")
            return True
        service.deliver_smtp_notification(
            worker_id, item["id"], token, host=host,
            port=int(os.environ.get("BIOINTEL_SMTP_PORT", "587")),
            username=os.environ.get("BIOINTEL_SMTP_USERNAME", ""),
            password_env="BIOINTEL_SMTP_PASSWORD", sender=sender,
            use_tls=os.environ.get("BIOINTEL_SMTP_TLS", "1") not in {"0", "false", "False"},
        )
        return True
    service.complete_notification(worker_id, item["id"], token, state="failed", error_text=f"No live {channel} delivery adapter is configured.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="BioIntel Education Phase 16 production-runtime worker")
    parser.add_argument("--actor", required=True, help="Institution administrator used for governed worker actions")
    parser.add_argument("--worker-id", default=f"{socket.gethostname()}-{os.getpid()}")
    parser.add_argument("--queue", default="default")
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--project-root", default=str(ROOT))
    args = parser.parse_args()

    database, media = education_paths(args.project_root)
    platform = EducationPlatform(database, media)
    service = EducationPhase16Service(platform, root=args.project_root)
    while True:
        did_work = False
        job = service.phase5.claim_job(args.worker_id, queue_name=args.queue)
        if job:
            did_work = True
            institution_id = job["institution_id"]
            try:
                try:
                    service.register_worker(args.actor, institution_id, args.worker_id, queues=[args.queue], version="phase16")
                    service.worker_heartbeat(institution_id, args.worker_id, current_job_id=job["id"], state="busy")
                except Exception:
                    pass
                result = execute_job(service, args.actor, args.worker_id, job)
                service.update_job_progress(institution_id, args.worker_id, job["id"], job["lock_token"], 100, "Completed")
                service.phase5.complete_job(args.worker_id, job["id"], job["lock_token"], result)
            except Exception as exc:
                service.phase5.fail_job(args.worker_id, job["id"], job["lock_token"], str(exc), retry_delay_seconds=60)
            finally:
                try:
                    service.worker_heartbeat(institution_id, args.worker_id, current_job_id="", state="online")
                except Exception:
                    pass
        for channel in ("in_app", "desktop", "email", "sms", "whatsapp"):
            try:
                did_work = deliver_one_notification(service, args.worker_id, channel) or did_work
            except Exception:
                did_work = True
        if args.once:
            return 0
        if not did_work:
            time.sleep(max(1.0, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
