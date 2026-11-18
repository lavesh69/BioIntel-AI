from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.engineering.module_reliability import reliability_summary, runtime_residue
from biointel.stability_v145.maintenance import run_overall_maintenance
from biointel.utils.atomic_io import atomic_write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--skip-database-maintenance", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    payload = {
        "schema": "biointel.step145.qualification.v1",
        "reliability": reliability_summary(root),
        "maintenance": run_overall_maintenance(root, database_maintenance=not args.skip_database_maintenance),
        "runtime_residue": runtime_residue(root),
    }
    payload["passed"] = bool(payload["reliability"]["passed"]) and bool(payload["maintenance"]["passed"])
    output = root / "reports" / "step145_overall_stability_qualification.json"
    atomic_write_json(output, payload, indent=2, sort_keys=False)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
