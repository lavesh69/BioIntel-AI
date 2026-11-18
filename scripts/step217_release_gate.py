from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.production_enablement_v217 import scan_production_enablement


def _read_json(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{relative} must contain a JSON object.")
    return value


def run_gate(*, require_external_evidence: bool = False) -> dict[str, Any]:
    readiness = scan_production_enablement(ROOT)
    errors: list[str] = []

    workflow_config = _read_json("config/step217/native_workflows.json")
    workflows = workflow_config.get("workflows", [])
    if not isinstance(workflows, list) or len(workflows) < 9:
        errors.append("Native workflow catalogue must define at least nine priority workflows.")
    required_stages = {
        "raw_input",
        "quality_control",
        "native_engine_execution",
        "native_result_parsing",
        "provenance",
        "report",
    }
    for workflow in workflows if isinstance(workflows, list) else []:
        stages = set(workflow.get("stages", [])) if isinstance(workflow, dict) else set()
        if stages != required_stages:
            errors.append(f"Workflow stage contract is incomplete: {workflow.get('workflow_id', '<unknown>')}")

    model_policy = _read_json("config/step217/model_candidate_policy.json")
    if model_policy.get("automatic_qualification") is not False:
        errors.append("Model candidate policy must disable automatic qualification.")

    plugin_policy = _read_json("config/step217/plugin_policy.json")
    if plugin_policy.get("signature_algorithm") != "Ed25519":
        errors.append("Plugin policy must require Ed25519 signatures.")

    from biointel.ui.navigation import PAGE_BY_KEY, catalogue_integrity

    page = PAGE_BY_KEY.get("production_enablement")
    if page is None or page.path != "pages/269_Production_Enablement_Center.py":
        errors.append("Production Enablement Center is not registered in navigation.")
    catalogue = catalogue_integrity(ROOT)
    if not catalogue.get("healthy"):
        errors.append("Navigation catalogue integrity failed.")

    page_source = (ROOT / "pages/269_Production_Enablement_Center.py").read_text(encoding="utf-8")
    if "use_container_width" in page_source:
        errors.append("Step217 page uses deprecated use_container_width.")
    if "st.segmented_control" not in page_source:
        errors.append("Step217 page is missing the view segmented control.")

    software_controls_passed = (
        readiness["internal_controls_ready"] == readiness["capability_count"]
        and not errors
    )
    production_evidence_passed = bool(readiness["passed"])
    passed = production_evidence_passed if require_external_evidence else software_controls_passed
    return {
        "schema": "biointel.step217.release-gate.v1",
        "passed": passed,
        "software_controls_passed": software_controls_passed,
        "production_evidence_passed": production_evidence_passed,
        "require_external_evidence": require_external_evidence,
        "errors": errors,
        "workflow_count": len(workflows) if isinstance(workflows, list) else 0,
        "readiness": readiness,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify BioIntel Step217 production-enablement controls.")
    parser.add_argument("--output", default="reports/step217_release_gate.json")
    parser.add_argument("--require-external-evidence", action="store_true")
    args = parser.parse_args()
    report = run_gate(require_external_evidence=args.require_external_evidence)
    destination = (ROOT / args.output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "software_controls_passed": report["software_controls_passed"],
                "production_evidence_passed": report["production_evidence_passed"],
                "workflow_count": report["workflow_count"],
                "errors": report["errors"],
                "output": str(destination),
            },
            indent=2,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
