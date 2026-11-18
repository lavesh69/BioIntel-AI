from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.database.integrity_guards import install_integrity_guards
from biointel.database.migrations import optimize_existing_registries
from biointel.quality.scorecard import build_quality_scorecard


def main() -> None:
    generated = ROOT / "reports" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    guards = install_integrity_guards(ROOT)
    optimized = optimize_existing_registries(ROOT)
    quality = build_quality_scorecard(ROOT)
    payload = {
        "step": 35,
        "integrity_guards": {
            key: {
                "triggers_created": value.triggers_created,
                "trigger_count": value.trigger_count,
                "foreign_key_findings": value.foreign_key_findings,
                "integrity": value.integrity,
            }
            for key, value in guards.items()
        },
        "optimized_databases": optimized,
        "quality": quality,
    }
    destination = generated / "step35_quality_hardening.json"
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "report": str(destination),
                "overall_score": quality["overall_score"],
                "group_scores": quality["group_scores"],
                "release_eligible_models": quality["model_audit"]["release_eligible_models"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
