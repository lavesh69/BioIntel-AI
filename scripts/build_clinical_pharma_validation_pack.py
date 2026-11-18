from __future__ import annotations

import argparse
import json
from pathlib import Path

from biointel.clinical import build_validation_template_pack


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build blank controlled clinical/pharma templates."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="data/clinical_pharma/templates")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    destination = Path(args.output)
    if not destination.is_absolute():
        destination = root / destination
    output = build_validation_template_pack(
        destination,
        metadata={
            "project": "BioIntel AI",
            "milestone": "83",
            "contains_real_validation_evidence": False,
            "claim_boundary": "execution templates only; authentic sponsor/site evidence required",
        },
    )
    files = sorted(path.name for path in output.iterdir() if path.is_file())
    print(json.dumps({"output": str(output), "file_count": len(files), "files": files}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
