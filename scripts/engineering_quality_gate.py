from __future__ import annotations

import argparse
import json
from pathlib import Path

from biointel.engineering import build_engineering_readiness, run_engineering_gates

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--json-output", default="reports/engineering_quality.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    gates = run_engineering_gates(root)
    readiness = build_engineering_readiness(root)
    report = {
        "gates": gates,
        "readiness": readiness,
        "passed": gates["passed"] and readiness["all_targets_complete"],
    }
    out = root / args.json_output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
