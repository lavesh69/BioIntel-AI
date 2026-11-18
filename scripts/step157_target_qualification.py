from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.validation.target_qualification import qualify_target, save_target_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BioIntel AI Step 157 target-machine qualification.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--output", default="reports/step157_target_qualification.json")
    parser.add_argument("--skip-manifest", action="store_true")
    parser.add_argument("--ui", action="store_true", help="Run representative Streamlit AppTest scenarios")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    pages = (
        "app.py",
        "pages/0_Quick_Start.py",
        "pages/105_Scientific_Execution_Quality_Center.py",
        "pages/110_Reliability_Optimization_Center.py",
        "pages/227_Scientific_Readiness_Command_Center.py",
    ) if args.ui else ()
    report = qualify_target(root, app_test_pages=pages, verify_manifest=not args.skip_manifest)
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    save_target_report(report, output)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    print(f"REPORT_PATH={output}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
