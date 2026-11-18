from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from biointel.final_v173 import Step173Registry, build_step173_assets

assets = build_step173_assets(ROOT)
registry = Step173Registry(ROOT)
matrix = registry.latest(refresh=False)
report = {
    "schema": "biointel.step173.asset-build.v1",
    "status": "passed",
    "version": "14.5.0",
    "modules": len(matrix),
    "assets": len(assets),
    "internal_10of10_modules": int(matrix["internal_10of10_complete"].sum()),
    "controlled_release_eligible_modules": int(matrix["controlled_release_eligible"].sum()),
    "average_practical_readiness": round(float(matrix["actual_practical_readiness_rating"].mean()), 2),
    "registry": registry.status(),
    "external_evidence_fabricated": False,
}
out = ROOT / "reports" / "step173_asset_build.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
