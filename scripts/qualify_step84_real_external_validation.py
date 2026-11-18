from __future__ import annotations

import argparse
import json
from pathlib import Path

from biointel.clinical import (
    ClinicalValidationRegistry,
    build_real_external_validation_framework_readiness,
    evaluate_real_external_validation,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Qualify Step 84 real external-validation execution controls."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--database", default="data/clinical_pharma/clinical_validation.sqlite3")
    parser.add_argument(
        "--output", default="reports/generated/step84_real_external_validation_readiness.json"
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    registry = ClinicalValidationRegistry(root / args.database)
    framework = build_real_external_validation_framework_readiness(root)
    programs = []
    for program in registry.list_programs():
        report = evaluate_real_external_validation(registry, program["program_id"])
        programs.append(
            {
                "program_id": program["program_id"],
                "title": program["title"],
                "status": program["status"],
                "actual_external_validation_score": report.actual_external_validation_score,
                "domains_at_10": report.domains_at_10,
                "total_domains": report.total_domains,
                "release_eligible": report.release_eligible,
                "permitted_claim": report.permitted_claim,
            }
        )
    payload = {
        "schema": "biointel.step84-qualification.v1",
        "framework": framework,
        "programs": programs,
        "boundary": (
            "Qualification proves the software controls. Actual external-validation scores require "
            "authentic independent evidence and are never raised by test fixtures."
        ),
    }
    target = root / args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if framework["complete"] and framework["score"] == 10.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
