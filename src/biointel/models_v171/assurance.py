from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .catalog import APPLICABLE_MODULES, SPEC_BY_KEY
from .qualification import qualification_matrix


def _check(checks: list[dict[str, Any]], name: str, status: str, detail: str) -> None:
    checks.append({"check": name, "status": status, "detail": detail})


def _metric(metrics: list[dict[str, Any]], name: str, value: Any, unit: str = "") -> None:
    metrics.append({"metric": name, "value": value, "unit": unit})


def apply_step171_model_benchmark_assurance(
    *,
    module_key: str,
    metadata: dict[str, Any],
    tables: dict[str, pd.DataFrame],
    checks: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> None:
    root_value = metadata.get("project_root")
    root = Path(str(root_value)) if root_value else Path(__file__).resolve().parents[3]
    if module_key not in APPLICABLE_MODULES:
        tables["step171_model_benchmark_assurance"] = pd.DataFrame([
            {
                "module_key": module_key,
                "task_specific_model_required": False,
                "software_framework_score": 10.0,
                "research_benchmark_status": "not-applicable",
                "release_eligible": False,
                "release_boundary": "Step 171 model package is not mandatory for this module; universal external evidence gates still apply.",
            }
        ])
        _check(checks, "Step 171 task-model requirement", "pass", "No task-specific predictive model is mandatory for this module.")
        _metric(metrics, "step171_model_qualification_framework_score", 10.0, "score")
        return
    matrix = qualification_matrix(root)
    row = matrix.loc[matrix["module_key"] == module_key].iloc[0].to_dict()
    spec = SPEC_BY_KEY[module_key]
    tables["step171_model_benchmark_assurance"] = pd.DataFrame([row])
    tables["step171_model_claim_boundary"] = pd.DataFrame([
        {
            "module_key": module_key,
            "task_scope": spec.task_scope,
            "synthetic_model_substitution_allowed": False,
            "wrong_domain_model_substitution_allowed": False,
            "independent_external_site_required_for_release": True,
            "expert_signoff_required_for_release": True,
            "current_claim_tier": "research-benchmark" if row["research_benchmark_qualified"] else "framework-only",
            "controlled_release_eligible": bool(row["release_eligible"]),
            "limitations": spec.limitations,
        }
    ])
    status = "pass" if row["research_benchmark_qualified"] else "review"
    _check(
        checks,
        "Step 171 authentic task-model research benchmark",
        status,
        f"{row['decision']}; independent external-site validation and signed expert review remain incomplete.",
    )
    _metric(metrics, "step171_model_qualification_framework_score", 10.0, "score")
    _metric(metrics, "step171_authentic_research_benchmark_present", int(row["research_benchmark_qualified"]), "boolean")
    _metric(metrics, "step171_independent_external_site_complete", int(row["independent_external_site_complete"]), "boolean")
    _metric(metrics, "step171_controlled_release_eligible", int(row["release_eligible"]), "boolean")


__all__ = ["apply_step171_model_benchmark_assurance"]
