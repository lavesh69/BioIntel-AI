from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.target_modules_v176 import qualification_matrix


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Step 176 17-module operational excellence layer.")
    parser.add_argument("--execute-smoke-tests", action="store_true", help="Run non-destructive engine version probes.")
    args = parser.parse_args()
    matrix = qualification_matrix(ROOT, execute_smoke_tests=args.execute_smoke_tests)
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    csv_path = reports / "step176_target_module_qualification.csv"
    json_path = reports / "step176_target_module_qualification.json"
    matrix.to_csv(csv_path, index=False)
    payload = {
        "schema": "biointel.step176.target-module-upgrade-report.v1",
        "target_modules": len(matrix),
        "internal_10of10_modules": int(matrix["internal_upgrade_rating"].eq(10.0).sum()),
        "engines_fully_discovered_or_qualified": int(matrix["engine_discovery_fraction"].eq(1.0).sum()),
        "references_fully_qualified": int(matrix["reference_qualification_fraction"].eq(1.0).sum()),
        "controlled_release_eligible": int(matrix["controlled_release_eligible"].sum()),
        "honest_boundary": "External assets/evidence are never auto-marked complete.",
        "rows": matrix.to_dict(orient="records"),
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "rows"}, indent=2))
    return 0 if payload["internal_10of10_modules"] == payload["target_modules"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
