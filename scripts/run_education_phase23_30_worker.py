from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.paths import education_paths, user_data_root  # noqa: E402
from biointel.education.phase23_30.service import (  # noqa: E402
    EducationEnterprisePlatform,
)
from biointel.education.platform import EducationPlatform  # noqa: E402

ADMIN_ROLES = {
    "platform_administrator",
    "institution_administrator",
    "principal",
    "dean",
    "registrar",
    "department_head",
    "examination_controller",
}
_STOP = False


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class PidLease:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.token = uuid.uuid4().hex

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                current = json.loads(self.path.read_text(encoding="utf-8"))
                if pid_alive(int(current.get("pid", 0))):
                    raise RuntimeError(
                        f"Phase 23-30 worker is already running with PID {current['pid']}."
                    )
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
            self.path.unlink(missing_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "pid": os.getpid(),
                    "token": self.token,
                    "host": socket.gethostname(),
                },
                handle,
            )
        return self

    def __exit__(self, *_):
        try:
            current = json.loads(self.path.read_text(encoding="utf-8"))
            if current.get("token") == self.token:
                self.path.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError):
            pass


def stop_worker(*_args) -> None:
    global _STOP
    _STOP = True


def institution_actor(
    platform: EducationPlatform,
    institution_id: str,
    requested: str,
) -> str:
    if requested:
        roles = {
            row["role"]
            for row in platform.membership(requested, institution_id)
        }
        if roles.intersection(ADMIN_ROLES):
            return requested
        raise RuntimeError(f"Actor {requested!r} is not an institution administrator.")
    row = platform._one(
        """SELECT user_id FROM memberships WHERE institution_id=?
        AND state='active' AND role IN
        ('platform_administrator','institution_administrator','principal','dean',
        'registrar','department_head','examination_controller')
        ORDER BY created_at LIMIT 1""",
        (institution_id,),
    )
    if not row:
        raise RuntimeError(f"No active administrator exists for {institution_id}.")
    return str(row["user_id"])


def execute_claimed(
    service: EducationEnterprisePlatform,
    worker_id: str,
    job: dict[str, object],
    actor: str,
) -> dict[str, object]:
    payload = json.loads(str(job["payload_json"]))
    job_type = str(job["job_type"])
    if job_type == "analytics_refresh":
        result = {
            "database": service.database_inventory(),
            "refreshed": True,
        }
    elif job_type == "report_generation":
        result = service.release_qualification(
            actor,
            str(job["institution_id"]),
        )
    elif job_type == "ai_task":
        task_id = str(payload.get("task_id", ""))
        if not task_id:
            raise RuntimeError("AI task job requires task_id.")
        result = service.execute_agent_task(actor, task_id)
    elif job_type in {
        "scientific_source_sync",
        "notification",
        "webhook_delivery",
    }:
        raise RuntimeError(
            f"{job_type} requires a configured and externally validated adapter."
        )
    else:
        raise RuntimeError(
            f"No safe local executor is registered for {job_type}; job retained for retry."
        )
    return service.complete_job(worker_id, str(job["id"]), result=result)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="BioIntel Education Phase 23-30 background worker"
    )
    parser.add_argument("--actor", default="")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--queue", default="default")
    parser.add_argument("--project-root", default=str(ROOT))
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    database, media = education_paths(project_root)
    platform = EducationPlatform(database, media)
    service = EducationEnterprisePlatform(platform, root=str(project_root))
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    pid_file = (
        user_data_root(project_root)
        / "runtime"
        / "education-phase23-30-worker.pid"
    )
    signal.signal(signal.SIGINT, stop_worker)
    signal.signal(signal.SIGTERM, stop_worker)
    try:
        with PidLease(pid_file):
            while not _STOP:
                claimed = service.claim_job(worker_id, queue=args.queue)
                event: dict[str, object] = {
                    "event": "phase23_30_worker_pass",
                    "worker_id": worker_id,
                    "claimed": bool(claimed),
                }
                if claimed:
                    try:
                        actor = institution_actor(
                            platform,
                            str(claimed["institution_id"]),
                            args.actor,
                        )
                        completed = execute_claimed(
                            service,
                            worker_id,
                            claimed,
                            actor,
                        )
                        event.update(
                            {
                                "job_id": completed["id"],
                                "state": completed["state"],
                            }
                        )
                    except Exception as exc:
                        failed = service.fail_job(
                            worker_id,
                            str(claimed["id"]),
                            error=f"{type(exc).__name__}: {exc}",
                        )
                        event.update(
                            {
                                "job_id": failed["id"],
                                "state": failed["state"],
                                "error": str(exc),
                            }
                        )
                print(json.dumps(event, ensure_ascii=True), flush=True)
                if args.once:
                    return 0
                if not claimed:
                    time.sleep(max(1.0, min(args.poll_seconds, 60.0)))
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

