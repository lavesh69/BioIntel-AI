"""Execute durable, locally planned Education lecture-transcription jobs."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.paths import education_paths  # noqa: E402
from biointel.education.phase16 import EducationPhase16Service  # noqa: E402
from biointel.education.platform import EducationPlatform  # noqa: E402


def run_batch(service: EducationPhase16Service, *, limit: int) -> dict[str, object]:
    jobs = service.platform._all(
        """SELECT id,created_by FROM education_transcription_jobs_v16
           WHERE state IN ('planned','failed') ORDER BY created_at LIMIT ?""",
        (max(1, min(int(limit), 100)),),
    )
    review_required, failed = [], []
    for job in jobs:
        try:
            result = service.execute_lecture_transcription(job["created_by"], job["id"])
            review_required.append({"id": job["id"], "state": result["state"], "human_review_required": True})
        except Exception as exc:
            failed.append({"id": job["id"], "error": f"{type(exc).__name__}: {exc}"[:500]})
    return {"considered": len(jobs), "review_required": review_required, "failed": failed}


def main() -> int:
    parser = argparse.ArgumentParser(description="BioIntel offline lecture-transcription worker")
    parser.add_argument("--project-root", default=str(ROOT))
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()
    database, media = education_paths(project_root)
    platform = EducationPlatform(database, media)
    service = EducationPhase16Service(platform, root=project_root)
    while True:
        result = run_batch(service, limit=args.limit)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if args.once:
            return 0 if not result["failed"] else 1
        if not result["considered"]:
            time.sleep(max(1.0, float(args.poll_seconds)))


if __name__ == "__main__":
    raise SystemExit(main())