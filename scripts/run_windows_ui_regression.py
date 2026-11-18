from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.step101.ui_regression import run_ui_regression


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--mode", choices=["static", "apptest", "full"], default="full")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output_dir).resolve() if args.output_dir else root / "reports" / "ui_regression"
    result = run_ui_regression(root, mode=args.mode, timeout_seconds=args.timeout, output_dir=output)
    print(json.dumps(result, indent=2))
    return 0 if result["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
