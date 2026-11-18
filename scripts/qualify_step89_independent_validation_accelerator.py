from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.clinical import build_independent_validation_accelerator_readiness


def main() -> int:
    report = build_independent_validation_accelerator_readiness(ROOT)
    output = ROOT / "reports" / "generated" / "step89_independent_validation_accelerator_readiness.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    print(f"Step 89 independent validation accelerator: {report.score:.1f}/10")
    print(f"Controls passed: {report.passed_controls}/{report.total_controls}")
    print(f"Report: {output}")
    return 0 if report.score == 10.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
