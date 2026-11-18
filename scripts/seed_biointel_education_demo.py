from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.demo import seed_demo


def main() -> int:
    parser = argparse.ArgumentParser(description="Load the isolated synthetic BioIntel Education workspace.")
    parser.add_argument("--project-root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(seed_demo(args.project_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
