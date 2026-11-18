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
from biointel.education.phase12 import EducationPhase12Service  # noqa: E402
from biointel.education.platform import Conflict, EducationPlatform  # noqa: E402


def execute_job(service: EducationPhase12Service, actor: str, worker_id: str, job: dict[str, Any]) -> dict[str, Any]:
    payload = dict(job.get("payload") or {})
    institution_id = job["institution_id"]
    token = job["lock_token"]
    service.update_job_progress(institution_id, worker_id, job["id"], token, 10, "Phase 12 job accepted")
    job_type = job["job_type"]
    if job_type == "phase12_database_migration_export":
        service.update_job_progress(institution_id, worker_id, job["id"], token, 45, "Creating portable tenant-scoped migration bundle")
        return service.create_database_migration_export(actor, institution_id, profile_id=str(payload.get("profile_id", "")))
    if job_type == "phase12_release_posture":
        service.update_job_progress(institution_id, worker_id, job["id"], token, 60, "Calculating code and external qualification posture")
        return service.final_completion_posture(actor, institution_id)
    if job_type == "phase12_originality_analysis":
        service.update_job_progress(institution_id, worker_id, job["id"], token, 55, "Computing bounded local similarity evidence")
        return service.analyze_submission_originality(actor, str(payload["submission_id"]), threshold=float(payload.get("threshold", .35)))
    if job_type == "phase12_rag_evaluation":
        service.update_job_progress(institution_id, worker_id, job["id"], token, 55, "Evaluating retrieval and citation grounding")
        return service.record_rag_evaluation(
            actor, institution_id, str(payload["project_id"]), str(payload["query_text"]),
            expected_refs=list(payload.get("expected_refs") or []),
            retrieved_refs=list(payload.get("retrieved_refs") or []),
            cited_refs=list(payload.get("cited_refs") or []),
        )
    if job_type == "phase11_generate_report":
        return service.generate_report(actor, institution_id, str(payload.get("report_type", "attendance")), parameters=dict(payload.get("parameters") or {}), output_format=str(payload.get("output_format", "json")))
    if job_type == "phase11_health_snapshot":
        return service.record_health_snapshot(actor, institution_id)
    if job_type == "phase11_security_chain":
        return service.verify_security_chain(actor, institution_id)
    raise Conflict(f"No Phase 12 worker handler is registered for {job_type}.")


def deliver_one_notification(service: EducationPhase12Service, worker_id: str, channel: str) -> bool:
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
    service.complete_notification(worker_id, item["id"], token, state="failed", error_text=f"No live {channel} adapter is configured; provider qualification remains pending.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="BioIntel Education Phase 12 final-completion worker")
    parser.add_argument("--actor", required=True, help="Institution administrator used for governed worker actions")
    parser.add_argument("--worker-id", default=f"{socket.gethostname()}-{os.getpid()}")
    parser.add_argument("--queue", default="default")
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--project-root", default=str(ROOT))
    args = parser.parse_args()

    database, media = education_paths(args.project_root)
    platform = EducationPlatform(database, media)
    service = EducationPhase12Service(platform, root=args.project_root)
    while True:
        did_work = False
        job = service.phase5.claim_job(args.worker_id, queue_name=args.queue)
        if job:
            did_work = True
            institution_id = job["institution_id"]
            try:
                try:
                    service.register_worker(args.actor, institution_id, args.worker_id, queues=[args.queue], version="phase12")
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
