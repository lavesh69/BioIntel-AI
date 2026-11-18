from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/biointel/ui/non_chart_scientific_visuals.py"


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    checks = {
        "version_preserved": (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "13.2.0",
        "rerun_css_guard_removed": "_step115_non_chart_css_loaded" not in text,
        "stable_style_id": 'biointel-non-chart-scientific-visuals-v2' in text,
        "shell_display_hardened": ".nc-shell{display:block!important" in text,
        "grid_display_hardened": ".nc-grid{display:grid!important" in text,
        "lane_display_hardened": ".nc-lane{display:block!important" in text,
        "segment_display_hardened": ".nc-seg{display:block!important" in text,
        "all_15_canvases_preserved": text.count('"') > 0 and len(__import__("biointel.ui.non_chart_scientific_visuals", fromlist=["NON_CHART_VISUAL_CATALOG"]).NON_CHART_VISUAL_CATALOG) == 15,
    }
    payload = {
        "release": "13.2.0",
        "hotfix": "canvas-rerun-consistency",
        "checks": checks,
        "passed": sum(checks.values()),
        "total": len(checks),
    }
    out = ROOT / "reports/step124_canvas_hotfix_verification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"{payload['passed']}/{payload['total']} checks passed")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
