from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.step122.protein_design import register_model_asset


def main() -> int:
    parser = argparse.ArgumentParser(description="Register a local protein-model asset with checksum and licence evidence")
    parser.add_argument("backend", choices=["proteinmpnn", "rfdiffusion", "colabfold_batch", "foldx", "rosetta_scripts"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--workspace", type=Path, default=ROOT / "workspace" / "protein_design_runs")
    parser.add_argument("--sha256", default="")
    parser.add_argument("--license-accepted", action="store_true", required=True)
    args = parser.parse_args()
    record = register_model_asset(
        args.backend,
        args.path,
        workspace=args.workspace,
        expected_sha256=args.sha256,
        license_accepted=args.license_accepted,
    )
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
