from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.scientific.excellence import build_scientific_excellence_readiness


def main() -> int:
    report = build_scientific_excellence_readiness(ROOT)
    output = ROOT / "reports" / "step38_scientific_qualification.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["implementation_average"] == 10.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
