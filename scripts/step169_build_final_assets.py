from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.final_v169 import ensure_step169_assets, ensure_step169_registry, final_consolidation_matrix


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    written = ensure_step169_assets(root)
    db = ensure_step169_registry(root)
    matrix = final_consolidation_matrix(root)
    matrix.to_csv(reports / "step169_final_consolidation_matrix.csv", index=False)
    payload = {
        "schema": "biointel.step169.asset-build.v1",
        "status": "passed",
        "product_version": "14.1.0",
        "modules": len(matrix),
        "contracts_written": len(written),
        "registry": str(db.relative_to(root)),
        "internal_10of10": int((matrix.internal_software_rating == 10).sum()),
        "controlled_release_eligible": int(matrix.controlled_release_eligible.sum()),
        "external_claims_inferred": False,
    }
    (reports / "step169_asset_build.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
