from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify BioIntel AI Step216 release readiness.")
    parser.add_argument("--root", default=".", help="Extracted BioIntel AI project root.")
    parser.add_argument("--output", help="Optional JSON report path.")
    parser.add_argument("--deep-hashes", action="store_true", help="Verify source and wheelhouse hashes.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from biointel.release_readiness_v216 import scan_release_readiness, write_readiness_report

    report = scan_release_readiness(root, deep_hashes=args.deep_hashes)
    output = write_readiness_report(root, output=args.output, deep_hashes=args.deep_hashes)
    report["report_path"] = str(output)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())