from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.engine_audit_v196 import audit_catalog, audit_summary, write_audit_reports


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the Step212 audit for all registered specialist engines.")
    parser.add_argument("--output-dir", default=str(ROOT / "reports" / "step212_engine_audit"))
    parser.add_argument("--probe-runtime", action="store_true", help="Run non-destructive local --version probes.")
    args = parser.parse_args()

    paths = write_audit_reports(args.output_dir, probe_runtime=args.probe_runtime)
    frame = audit_catalog(probe_runtime=args.probe_runtime)
    summary = audit_summary(frame)
    print(json.dumps({"status": "passed", "summary": summary, "outputs": {k: str(v) for k, v in paths.items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
