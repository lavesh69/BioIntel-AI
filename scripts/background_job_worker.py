from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.intelligence.data_intelligence import database_paths
from biointel.jobs.local_queue import LocalJobQueue


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--worker-id", default="background-worker")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    user_data = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or root)
    runtime = user_data / "runtime_logs"
    runtime.mkdir(parents=True, exist_ok=True)
    stop_path = runtime / "background-worker.stop"
    startup_queue = LocalJobQueue(database_paths(root)["jobs"])
    startup_queue.heartbeat(
        args.worker_id,
        status="starting",
        metadata={"service": "persistent-background-worker", "phase": "loading-scientific-modules"},
    )
    worker = None
    pulse_scheduler = None
    print(json.dumps({"event": "worker_starting", "worker_id": args.worker_id, "root": str(root)}), flush=True)
    try:
        from biointel.jobs.worker import LocalWorker
        from biointel.science_pulse.scheduler import SciencePulseScheduler

        worker = LocalWorker(root, worker_id=args.worker_id)
        worker.queue.recover_orphaned_jobs(stale_after_seconds=60)
        pulse_scheduler = SciencePulseScheduler(root, worker_id=args.worker_id)
        print(json.dumps({"event": "worker_started", "worker_id": args.worker_id, "root": str(root)}), flush=True)
        while not stop_path.exists():
            result = worker.run_once()
            pulse_result = pulse_scheduler.tick()
            if not result.processed:
                worker.queue.heartbeat(
                    args.worker_id,
                    status="online",
                    capabilities={"job_types": sorted(worker.handlers), "science_pulse": "persistent-scheduler"},
                    metadata={"service": "persistent-background-worker", "science_pulse": pulse_result["status"]},
                )
                time.sleep(max(0.25, args.poll_seconds))
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        if pulse_scheduler is not None:
            pulse_scheduler.shutdown()
        stop_path.unlink(missing_ok=True)
        queue = worker.queue if worker is not None else startup_queue
        capabilities = {"job_types": sorted(worker.handlers)} if worker is not None else {}
        queue.heartbeat(args.worker_id, status="offline", capabilities=capabilities)
        print(json.dumps({"event": "worker_stopped", "worker_id": args.worker_id}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
