from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from biointel.clinical import build_clinical_pharma_framework_readiness


def main() -> int:
    parser = argparse.ArgumentParser(description="Qualify Step 83 software-control framework.")
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--output",
        default="reports/generated/step83_clinical_pharma_framework_readiness.json",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    report = build_clinical_pharma_framework_readiness(root)
    report["qualified_utc"] = datetime.now(UTC).isoformat()
    report["claim_status"] = "research/demo by default; real validation evidence not bundled"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
