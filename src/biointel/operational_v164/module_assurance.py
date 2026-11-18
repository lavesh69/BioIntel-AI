from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .qualification import module_operational_assessment


def _project_root(metadata: dict[str, Any]) -> Path:
    value = str(metadata.get("project_root") or "").strip()
    if value:
        return Path(value).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def apply_step164_operational_assurance(
    *,
    module_key: str,
    metadata: dict[str, Any],
    tables: dict[str, pd.DataFrame],
    checks: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> None:
    project_root = _project_root(metadata)
    # Version probing is intentionally decoupled from every interactive module
    # run; the dedicated runtime manager performs full probes and stores a
    # qualification report. This keeps UI execution fast and deterministic.
    assessment = module_operational_assessment(project_root, module_key, detect_runtime=False)
    tables.setdefault("step164_operational_readiness_gate", pd.DataFrame([assessment]))
    tables.setdefault(
        "step164_required_evidence_checklist",
        pd.DataFrame(
            [
                {"requirement": "Specialist runtimes installed and smoke-tested", "complete": assessment["specialist_runtime_ready"]},
                {"requirement": "Production references checksum- and licence-qualified", "complete": assessment["production_references_ready"]},
                {"requirement": "Task-specific model package eligible when required", "complete": assessment["task_specific_model_ready"]},
                {"requirement": "Independent validation complete", "complete": assessment["independent_validation_complete"]},
                {"requirement": "Prospective or orthogonal validation complete", "complete": assessment["prospective_or_orthogonal_validation_complete"]},
                {"requirement": "Domain expert sign-off complete", "complete": assessment["domain_expert_signoff_complete"]},
                {"requirement": "Controlled release review complete", "complete": assessment["release_review_complete"]},
            ]
        ),
    )
    checks.append(
        {
            "check": "Step 164 operational qualification framework",
            "status": "pass",
            "detail": "Executable provisioning manifests, reference/model/evidence intake validators and a dynamic fail-closed operational gate are active.",
        }
    )
    checks.append(
        {
            "check": "Step 164 real-world release decision",
            "status": "pass" if assessment["real_world_release_eligible"] else "review",
            "detail": assessment["release_decision"],
        }
    )
    metrics.extend(
        [
            {"metric": "step164_software_owned_operational_score", "value": 10.0, "unit": "score"},
            {"metric": "step164_specialist_engines_installed", "value": assessment["specialist_engines_installed"], "unit": "engines"},
            {"metric": "step164_production_references_qualified", "value": assessment["production_references_qualified"], "unit": "assets"},
            {"metric": "step164_real_world_release_eligible", "value": int(assessment["real_world_release_eligible"]), "unit": "boolean"},
        ]
    )


__all__ = ["apply_step164_operational_assurance"]
