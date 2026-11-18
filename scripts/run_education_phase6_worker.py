from __future__ import annotations

import argparse
import json
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
from biointel.education.phase6 import EducationPhase6Service  # noqa: E402
from biointel.education.platform import Conflict, EducationPlatform, now  # noqa: E402


def cancelled(service: EducationPhase6Service, job_id: str) -> bool:
    row = service.platform._one("SELECT cancel_requested FROM education_job_progress WHERE job_id=?", (job_id,))
    return bool(row and row["cancel_requested"])


def set_sync(service: EducationPhase6Service, run_id: str, state: str, *, detail: dict[str, Any] | None = None, finished: bool = False) -> None:
    with service.db.connection() as db:
        db.execute(
            "UPDATE education_integration_sync_runs SET state=?,detail_json=?,finished_at=? WHERE id=?",
            (state, json.dumps(detail or {}, sort_keys=True, default=str), now() if finished else None, run_id),
        )


def execute(service: EducationPhase6Service, actor: str, worker_id: str, job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload", {})
    institution_id = job["institution_id"]
    token = job["lock_token"]
    service.update_job_progress(institution_id, worker_id, job["id"], token, 5, "Job accepted")
    if cancelled(service, job["id"]):
        raise Conflict("Job cancellation was requested before execution.")

    if job["job_type"] == "scheduled_backup":
        service.update_job_progress(institution_id, worker_id, job["id"], token, 25, "Creating online database snapshot")
        snapshot = service.phase5.create_backup(actor, institution_id, f"scheduled-{job['id']}")
        service.update_job_progress(institution_id, worker_id, job["id"], token, 85, "Verifying backup integrity")
        verified = service.phase5.verify_backup(actor, snapshot["id"])
        return {"snapshot_id": snapshot["id"], "integrity_valid": bool(verified["integrity_valid"]), "include_media_requested": bool(payload.get("include_media"))}

    if job["job_type"] == "generate_report":
        student_id = str(payload.get("student_id") or "")
        service.update_job_progress(institution_id, worker_id, job["id"], token, 30, "Collecting governed report evidence")
        if student_id:
            report = service.phase4.learner_progress_report(actor, institution_id, student_id)
            return {"student_id": student_id, "summary": report.get("summary", {}), "generated_at": now()}
        report = service.phase5.generate_governance_report(actor, institution_id)
        return {"report_id": report["id"], "sha256": report["sha256"]}

    if job["job_type"] == "integration_sync":
        run_id = str(payload.get("sync_run_id") or "")
        integration_id = str(payload.get("integration_id") or "")
        if not run_id or not integration_id:
            raise Conflict("Integration sync payload is incomplete.")
        set_sync(service, run_id, "running", detail={"job_id": job["id"]})
        service.update_job_progress(institution_id, worker_id, job["id"], token, 35, "Qualifying provider connection")
        qualification = service.external.verify_integration(actor, integration_id)
        if qualification["state"] != "verified":
            set_sync(service, run_id, "configuration_required", detail={"qualification_id": qualification["id"], "error": qualification["error_text"]}, finished=True)
            raise Conflict(qualification["error_text"] or "Provider qualification failed.")
        # Generic provider qualification is real; provider-specific data mapping remains a separate adapter boundary.
        set_sync(service, run_id, "provider_qualified", detail={"qualification_id": qualification["id"], "provider_adapter_required": True}, finished=True)
        return {"sync_run_id": run_id, "provider_qualified": True, "provider_adapter_required": True}

    if job["job_type"] == "notification_reminders":
        service.update_job_progress(institution_id, worker_id, job["id"], token, 50, "Generating governed reminders")
        return service.phase4.generate_due_reminders(actor, institution_id, horizon_hours=int(payload.get("horizon_hours", 48)))

    if job["job_type"] == "verify_backup":
        snapshot_id = str(payload.get("snapshot_id") or "")
        if not snapshot_id:
            raise Conflict("Backup snapshot ID is required.")
        return service.phase5.verify_backup(actor, snapshot_id)

    raise Conflict(f"No Phase 6 worker handler is registered for {job['job_type']}.")


def main() -> int:
    parser = argparse.ArgumentParser(description="BioIntel Education Phase 6 durable background worker")
    parser.add_argument("--actor", required=True, help="Institution member used for governed service actions")
    parser.add_argument("--worker-id", default=f"{socket.gethostname()}-{os.getpid()}")
    parser.add_argument("--queue", default="default")
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--project-root", default=str(ROOT))
    args = parser.parse_args()

    database, media = education_paths(args.project_root)
    platform = EducationPlatform(database, media)
    service = EducationPhase6Service(platform, root=args.project_root)
    processed = 0
    while True:
        job = service.phase5.claim_job(args.worker_id, queue_name=args.queue)
        if not job:
            if args.once:
                return 0
            time.sleep(max(1.0, args.poll_seconds))
            continue
        processed += 1
        institution_id = job["institution_id"]
        try:
            try:
                service.register_worker(args.actor, institution_id, args.worker_id, queues=[args.queue], version="phase6")
            except Exception:
                pass
            try:
                service.worker_heartbeat(institution_id, args.worker_id, current_job_id=job["id"], state="busy")
            except Exception:
                pass
            result = execute(service, args.actor, args.worker_id, job)
            service.update_job_progress(institution_id, args.worker_id, job["id"], job["lock_token"], 100, "Completed")
            service.phase5.complete_job(args.worker_id, job["id"], job["lock_token"], result)
        except Exception as exc:
            service.phase5.fail_job(args.worker_id, job["id"], job["lock_token"], str(exc), retry_delay_seconds=60)
        finally:
            try:
                service.worker_heartbeat(institution_id, args.worker_id, current_job_id="", state="online")
            except Exception:
                pass
        if args.once:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
