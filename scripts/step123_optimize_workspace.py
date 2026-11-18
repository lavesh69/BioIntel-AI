from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.step123.optimization import optimize_workspace, runtime_audit
from biointel.utils.atomic_io import atomic_write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely optimize a BioIntel AI workspace.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--output", default="reports/step123_runtime_optimization.json")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    payload = (
        {"schema": "biointel.step123.audit.v1", "audit": runtime_audit(root).__dict__, "passed": True}
        if args.audit_only
        else optimize_workspace(root)
    )
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    atomic_write_json(output, payload)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload.get("passed", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
