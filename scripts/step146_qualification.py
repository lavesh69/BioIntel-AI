from __future__ import annotations

import argparse
import json
import sys
sys.dont_write_bytecode = True
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.engineering.module_reliability import reliability_summary, runtime_residue
from biointel.research_planning.lifecycle_engines import (
    LIFECYCLE_ENGINE_CATALOG,
    ethics_consent_workbench,
    fair_data_management_workbench,
    interim_monitoring_safety_workbench,
    publication_dissemination_workbench,
)
from biointel.ui.navigation import PAGE_CATALOG
from biointel.utils.atomic_io import atomic_write_json


TEMPLATES = {
    "research_ethics_consent": ("research_ethics_consent_template.csv", ethics_consent_workbench),
    "research_data_fair_planning": ("research_data_fair_planning_template.csv", fair_data_management_workbench),
    "research_interim_monitoring_safety": ("research_interim_monitoring_safety_template.csv", interim_monitoring_safety_workbench),
    "research_publication_dissemination": ("research_publication_dissemination_template.csv", publication_dissemination_workbench),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    template_root = root / "data" / "research_planning_templates"

    engines: list[dict[str, object]] = []
    for key, (filename, function) in TEMPLATES.items():
        row: dict[str, object] = {"module_key": key, "template": filename}
        try:
            frame = pd.read_csv(template_root / filename)
            output = function(frame)
            row.update({
                "passed": True,
                "rows": len(output.primary),
                "tables": len(output.all_tables()),
                "manifest_sha256": output.manifest()["manifest_sha256"],
            })
        except Exception as exc:
            row.update({"passed": False, "error": f"{type(exc).__name__}: {exc}"})
        engines.append(row)

    planning_pages = [page for page in PAGE_CATALOG if page.category == "Research Planning"]
    missing_pages = [page.path for page in planning_pages if not (root / page.path).is_file()]
    reliability = reliability_summary(root)
    payload = {
        "schema": "biointel.step146.research-lifecycle.qualification.v1",
        "planning_modules": len(planning_pages),
        "lifecycle_engines": len(LIFECYCLE_ENGINE_CATALOG),
        "engine_checks": engines,
        "missing_pages": missing_pages,
        "reliability": reliability,
        "runtime_residue": runtime_residue(root),
    }
    payload["passed"] = (
        len(planning_pages) == 24
        and not missing_pages
        and all(bool(row.get("passed")) for row in engines)
        and bool(reliability.get("passed"))
    )
    output = root / "reports" / "step146_research_lifecycle_qualification.json"
    atomic_write_json(output, payload, indent=2, sort_keys=False)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
