from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.jobs.worker import LocalWorker


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the BioIntel Step 33 local background worker."
    )
    parser.add_argument("--worker-id", default="local-worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    worker = LocalWorker(ROOT, worker_id=args.worker_id)
    if args.once:
        print(json.dumps(asdict(worker.run_once()), indent=2, sort_keys=True))
        return
    worker.run_forever(poll_seconds=args.poll_seconds)


if __name__ == "__main__":
    main()
