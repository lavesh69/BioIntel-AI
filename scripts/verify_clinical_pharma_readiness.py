from __future__ import annotations

import argparse
import json
from pathlib import Path

from biointel.clinical import ClinicalValidationRegistry, evaluate_clinical_pharma_readiness


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate one controlled validation program.")
    parser.add_argument("registry", type=Path)
    parser.add_argument("program_id")
    args = parser.parse_args()
    registry = ClinicalValidationRegistry(args.registry)
    report = evaluate_clinical_pharma_readiness(registry, args.program_id)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.release_eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
