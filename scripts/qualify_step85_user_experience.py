from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.quality.scorecard import build_quality_scorecard
from biointel.quality.ux_assurance import build_user_experience_assurance


def main() -> int:
    ux = build_user_experience_assurance(ROOT)
    scorecard = build_quality_scorecard(ROOT)
    payload = {
        "schema": "biointel.step85-user-experience-qualification.v1",
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "passed": bool(
            ux["all_targets_complete"]
            and float(scorecard["group_scores"]["User experience"]) == 10.0
        ),
        "user_experience_group_score": scorecard["group_scores"]["User experience"],
        "assurance": ux,
    }
    output = ROOT / "reports" / "step85_user_experience_qualification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
