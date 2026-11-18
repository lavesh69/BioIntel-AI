from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.demo_workspace import seed_demo_workspace
from biointel.runtime_paths import runtime_report_path


def main() -> None:
    result = seed_demo_workspace(ROOT)
    output = runtime_report_path(ROOT, "generated", "step28_demo_workspace_summary.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
