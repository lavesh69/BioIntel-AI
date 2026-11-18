from __future__ import annotations

from pathlib import Path
from typing import Any

from biointel.engineering import build_engineering_readiness
from biointel.maturity import build_maturity_readiness
from biointel.scientific import build_scientific_excellence_readiness


def build_target_capability_readiness(root: str | Path) -> dict[str, Any]:
    """Return the unified dual-score maturity and engineering matrix.

    ``implementation_score`` measures whether repository-level controls, tests, policies,
    CI and documentation exist. Scientific/regulatory evidence remains separate because
    authentic validation and operating history cannot be created by code alone.
    """

    base = Path(root)
    maturity = build_maturity_readiness(base)
    engineering = build_engineering_readiness(base)
    scientific = build_scientific_excellence_readiness(base)
    capabilities: list[dict[str, Any]] = []
    for area in maturity["areas"]:
        capabilities.append(
            {
                "key": area["key"],
                "label": area["label"],
                "implementation_score": area["implementation_score"],
                "implementation_status": area["implementation_status"],
                "evidence_score": area["evidence_score"],
                "evidence_status": area["evidence_status"],
                "controls": area["passed_controls"],
                "missing": area["failed_controls"],
                "boundary": area["boundary"],
                "program": "Scientific, compliance and enterprise maturity",
            }
        )
    for area in scientific["capabilities"]:
        capabilities.append(
            {
                "key": area["key"],
                "label": area["label"],
                "implementation_score": area["implementation_score"],
                "implementation_status": area["implementation_status"],
                "evidence_score": area["evidence_score"],
                "evidence_status": area["evidence_status"],
                "controls": area["controls"],
                "missing": area["missing"],
                "boundary": area["certification_boundary"],
                "program": "Scientific evidence excellence",
            }
        )
    for area in engineering["areas"]:
        capabilities.append(
            {
                "key": area["key"],
                "label": area["label"],
                "implementation_score": area["implementation_score"],
                "implementation_status": area["status"],
                "evidence_score": None,
                "evidence_status": "environment_qualification_required",
                "controls": area["passed_controls"],
                "missing": area["failed_controls"],
                "boundary": area["evidence_boundary"],
                "program": "Engineering excellence",
            }
        )
    average = round(
        sum(float(item["implementation_score"]) for item in capabilities) / max(len(capabilities), 1),
        1,
    )
    return {
        "capabilities": capabilities,
        "implementation_average": average,
        "all_implementation_targets_complete": all(
            float(item["implementation_score"]) == 10.0 for item in capabilities
        ),
        "evidence_average": round((maturity["evidence_average"] + scientific["evidence_average"]) / 2.0, 1),
        "scientific_boundary": maturity["dual_score_policy"],
        "engineering_control_count": engineering["control_count"],
        "programs": {
            "maturity": len(maturity["areas"]),
            "engineering_excellence": len(engineering["areas"]),
            "scientific_evidence_excellence": len(scientific["capabilities"]),
        },
    }
