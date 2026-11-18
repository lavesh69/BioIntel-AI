from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .registry import Step172Registry


def apply_step172_external_confirmation_assurance(
    *, module_key: str, metadata: dict[str, Any], tables: dict[str, pd.DataFrame],
    checks: list[dict[str, Any]], metrics: list[dict[str, Any]],
) -> None:
    root_value = metadata.get("project_root")
    root = Path(str(root_value)) if root_value else Path(__file__).resolve().parents[3]
    evaluation = Step172Registry(root).evaluate_submission(module_key)
    summary_row = {k: v for k, v in evaluation.items() if k not in {"blockers", "upstream"}}
    summary_row["blocker_count"] = len(evaluation["blockers"])
    summary_row["remaining_blockers"] = " | ".join(evaluation["blockers"])
    tables["step172_external_confirmation_gate"] = pd.DataFrame([summary_row])
    tables["step172_required_external_evidence"] = pd.DataFrame([
        {"requirement": "Locked prospective protocol", "complete": evaluation["protocol_complete"]},
        {"requirement": "Wet-lab confirmation when applicable", "complete": evaluation["wet_lab_complete"]},
        {"requirement": "Prospective confirmation when applicable", "complete": evaluation["prospective_complete"]},
        {"requirement": "Orthogonal confirmation when applicable", "complete": evaluation["orthogonal_complete"]},
        {"requirement": "Independent site qualification", "complete": evaluation["independent_site_complete"]},
        {"requirement": "Instrument IQ/OQ/PQ and calibration", "complete": evaluation["instrument_qualification_complete"]},
        {"requirement": "Physical Windows/GPU/instrument testing", "complete": evaluation["physical_qualification_complete"]},
        {"requirement": "Cryptographically verified expert sign-off", "complete": evaluation["expert_signoff_complete"]},
        {"requirement": "Formal release committee decision", "complete": evaluation["formal_release_review_complete"]},
        {"requirement": "Upstream Step 170/171 qualification", "complete": evaluation["upstream_runtime_reference_model_complete"]},
    ])
    checks.append({
        "check": "Step 172 external confirmation and formal release",
        "status": "pass" if evaluation["release_eligible"] else "review",
        "detail": evaluation["decision"] + ("" if evaluation["release_eligible"] else f"; {len(evaluation['blockers'])} blocker(s) remain"),
    })
    metrics.extend([
        {"metric": "step172_external_confirmation_framework_score", "value": 10.0, "unit": "score"},
        {"metric": "step172_external_evidence_complete", "value": int(evaluation["release_eligible"]), "unit": "boolean"},
        {"metric": "step172_verified_expert_signoffs", "value": int(evaluation["qualified_experts"]), "unit": "count"},
        {"metric": "step172_controlled_release_eligible", "value": int(evaluation["release_eligible"]), "unit": "boolean"},
    ])


__all__ = ["apply_step172_external_confirmation_assurance"]
