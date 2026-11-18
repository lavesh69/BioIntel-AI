from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.scientific.prospective import ProspectiveStudyRegistry


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pre-register a blinded prospective validation study."
    )
    parser.add_argument("--title", required=True)
    parser.add_argument("--hypothesis", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--success", required=True)
    parser.add_argument("--model-sha256", required=True)
    parser.add_argument("--dataset-sha256", required=True)
    args = parser.parse_args()
    registry = ProspectiveStudyRegistry(ROOT / "reports" / "prospective_validation.sqlite3")
    result = registry.register(
        title=args.title,
        hypothesis=args.hypothesis,
        primary_endpoint=args.endpoint,
        success_criterion=args.success,
        model_sha256=args.model_sha256,
        dataset_sha256=args.dataset_sha256,
    )
    print(json.dumps(result.__dict__, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
