from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.realworld import build_step41_realworld_readiness  # noqa: E402


def main() -> int:
    report = build_step41_realworld_readiness(ROOT)
    output = ROOT / "reports" / "step41_realworld_qualification.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "implementation_average": report["implementation_average"],
                "evidence_average": report["evidence_average"],
                "integrity": report["integrity"],
            },
            indent=2,
        )
    )
    return 0 if report["implementation_average"] == 10 and report["integrity"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
