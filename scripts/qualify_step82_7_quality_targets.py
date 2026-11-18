from __future__ import annotations

import argparse
import json
from pathlib import Path

from biointel.quality.scorecard import build_quality_scorecard
from biointel.quality.target_assurance import build_target_assurance


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="reports/step82_7_quality_targets.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    assurance = build_target_assurance(root)
    scorecard = build_quality_scorecard(root)
    requested = {
        item["key"]: item
        for item in scorecard["dimensions"]
        if item["key"]
        in {
            "code_maintainability",
            "accessibility",
            "frontend_performance",
            "ml_model_quality",
            "model_validation",
        }
        and item["group"] in {"Engineering", "User experience", "ML and validation"}
    }
    payload = {
        "version": "8.4.0",
        "headline": "Maintainability, accessibility, frontend and ML validation quality targets",
        "passed": assurance["all_targets_complete"]
        and all(float(item["score"]) == 10.0 for item in requested.values()),
        "assurance": assurance,
        "requested_scorecard_dimensions": requested,
        "scientific_evidence_boundary": assurance["dual_score_policy"],
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
