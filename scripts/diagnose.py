from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.utils.diagnostics import (  # noqa: E402
    diagnostic_summary,
    run_diagnostics,
)


def main() -> int:
    checks = run_diagnostics(ROOT)
    payload = {
        "summary": diagnostic_summary(checks),
        "checks": [check.to_dict() for check in checks],
    }
    print(json.dumps(payload, indent=2, default=str))
    return 1 if payload["summary"]["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
