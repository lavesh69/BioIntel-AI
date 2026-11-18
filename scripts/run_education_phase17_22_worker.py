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
from biointel.education.phase17_22.service import EducationOS  # noqa: E402
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

        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            pid,
        )
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
                    raise RuntimeError(f"Education OS worker is already running with PID {current['pid']}.")
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        if self.path.exists():
            self.path.unlink(missing_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "token": self.token, "host": socket.gethostname()}, handle)
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


def institution_actor(platform: EducationPlatform, institution_id: str, requested: str) -> str:
    if requested:
        roles = {row["role"] for row in platform.membership(requested, institution_id)}
        if roles & ADMIN_ROLES:
            return requested
        raise RuntimeError(f"Actor {requested!r} is not an administrator of institution {institution_id}.")
    row = platform._one(
        "SELECT user_id FROM memberships WHERE institution_id=? AND state='active' "
        "AND role IN ('platform_administrator','institution_administrator','principal','dean','registrar','department_head','examination_controller') "
        "ORDER BY created_at LIMIT 1",
        (institution_id,),
    )
    if not row:
        raise RuntimeError(f"No active institution administrator exists for {institution_id}.")
    return str(row["user_id"])


def main() -> int:
    parser = argparse.ArgumentParser(description="BioIntel Education OS Phase 17-22 durable outbox worker")
    parser.add_argument("--actor", default="", help="Optional institution administrator; auto-discovered when omitted")
    parser.add_argument("--once", action="store_true", help="Process one bounded pass and exit")
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--project-root", default=str(ROOT))
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    database, media = education_paths(project_root)
    platform = EducationPlatform(database, media)
    service = EducationOS(platform, root=project_root)
    pid_file = user_data_root(project_root) / "runtime" / "education-phase17-22-worker.pid"
    signal.signal(signal.SIGINT, stop_worker)
    signal.signal(signal.SIGTERM, stop_worker)

    try:
        with PidLease(pid_file):
            while not _STOP:
                institutions = platform._all("SELECT id FROM institutions WHERE state='active' ORDER BY id")
                processed = delivered = failed = 0
                errors: list[dict[str, str]] = []
                for institution in institutions:
                    institution_id = str(institution["id"])
                    try:
                        actor = institution_actor(platform, institution_id, args.actor)
                        result = service.dispatch_outbox(actor, institution_id, limit=100)
                        processed += int(result["processed"])
                        delivered += int(result["delivered"])
                        failed += int(result["failed"])
                    except Exception as exc:
                        errors.append({"institution_id": institution_id, "error": f"{type(exc).__name__}: {exc}"})
                print(json.dumps({"event": "education_os_worker_pass", "processed": processed, "delivered": delivered, "failed": failed, "errors": errors}, ensure_ascii=True), flush=True)
                if args.once:
                    return 0 if not errors and not failed else 2
                if not processed:
                    time.sleep(max(1.0, min(args.poll_seconds, 60.0)))
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
