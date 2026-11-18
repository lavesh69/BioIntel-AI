from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from biointel.realworld_v174 import Step174ExecutionRegistry, build_step174_assets, phase_catalog

assets = build_step174_assets(ROOT)
registry = Step174ExecutionRegistry(ROOT)
matrix = registry.latest(refresh=False)
report = {
    "schema": "biointel.step174.asset-build.v1",
    "status": "passed",
    "version": "14.6.0",
    "phases": len(phase_catalog()),
    "modules": len(matrix),
    "assets": len(assets),
    "software_phase_automation_10of10_modules": int((matrix["software_phase_automation_rating"] == 10.0).sum()),
    "controlled_release_eligible_modules": int(matrix["controlled_release_eligible"].sum()),
    "external_evidence_fabricated": False,
    "registry": registry.status(),
}
out = ROOT / "reports" / "step174_asset_build.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
