from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.ui.module_catalogue import catalogue_counts, complete_catalogue
from biointel.ui.navigation import PAGE_CATALOG, catalogue_integrity, search_page_matches
from biointel.ui.style_catalog import THEMES
from biointel.ui.theme_intelligence import theme_health


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(run_ui: bool = True) -> dict[str, object]:
    checks: dict[str, object] = {}
    integrity = catalogue_integrity(ROOT)
    counts = catalogue_counts(ROOT)
    checks["catalogue_integrity"] = integrity
    checks["catalogue_counts"] = counts
    checks["empty_search_count"] = len(search_page_matches("", "All"))
    checks["all_embedded_workspaces_linked"] = all(
        item.page_path
        for item in complete_catalogue(str(ROOT))
        if item.item_type == "Embedded workspace"
    )

    health_rows: list[dict[str, object]] = []
    for appearance in ("Dark", "Light"):
        for name in THEMES:
            health = theme_health(name, appearance)
            health_rows.append(
                {
                    "theme": name,
                    "appearance": appearance,
                    "overall": health.overall,
                    "accessibility": health.accessibility,
                    "body_contrast": health.body_contrast,
                    "muted_contrast": health.muted_contrast,
                    "issues": list(health.issues),
                }
            )
    checks["theme_health_rows"] = len(health_rows)
    checks["minimum_body_contrast"] = min(float(row["body_contrast"]) for row in health_rows)
    checks["theme_health"] = health_rows

    excluded = {
        "pages/6_DTI_Predictor.py": "84b3ecec1356b7239a057459210af4cd130c57c08dd9449b7239d1fe5954e0cc",
        "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
        "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "eadaef1a283a5fa11ce6b243aa561508ba9ceba9f6fdcc207f4853ccf7d86905",
        "pages/109_Lab_Instrument_Import_Center.py": "22b5aba5bfea37bb1ef330ed7cca3773467463f883189602d96a0151311c8f70",
        "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
    }
    checks["excluded_hashes"] = {
        relative: {"expected": expected, "actual": _sha(ROOT / relative)}
        for relative, expected in excluded.items()
    }

    ui_results: dict[str, object] = {}
    if run_ui:
        from streamlit.testing.v1 import AppTest

        for relative in (
            "app.py",
            "pages/24_Appearance_Studio.py",
            "pages/171_Module_Catalogue_Search.py",
        ):
            result = AppTest.from_file(str(ROOT / relative), default_timeout=180).run(timeout=180)
            ui_results[relative] = {
                "exceptions": [exception.message for exception in result.exception],
            }
    checks["ui_results"] = ui_results

    passed = bool(integrity["healthy"])
    passed &= counts["embedded_workspaces"] == counts["linked_workspaces"] == 78
    passed &= checks["empty_search_count"] == len(PAGE_CATALOG)
    passed &= float(checks["minimum_body_contrast"]) >= 4.5
    passed &= all(row["actual"] == row["expected"] for row in checks["excluded_hashes"].values())
    passed &= all(not row["exceptions"] for row in ui_results.values())
    checks["passed"] = passed
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-ui", action="store_true")
    parser.add_argument("--output", default="reports/step117_theme_navigation_verification.json")
    args = parser.parse_args()
    report = verify(run_ui=not args.skip_ui)
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "output": str(output), "catalogue": report["catalogue_counts"]}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
