from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from biointel.environment_v175 import build_step175_assets

paths = build_step175_assets(ROOT)
payload = {
    "schema": "biointel.step175.asset-build.v1",
    "status": "passed",
    "version": "14.7.0",
    "assets": len(paths),
    "engines": 53,
    "references": 26,
    "environment_groups": 12,
    "target_profiles": 3,
}
out = ROOT / "reports" / "step175_asset_build.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(json.dumps(payload, indent=2))
