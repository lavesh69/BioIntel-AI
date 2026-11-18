from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .orchestrator import Step174ExecutionRegistry


def apply_step174_phase_execution_assurance(
    *, module_key: str, metadata: dict[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]
) -> None:
    root = Path(str(metadata.get("project_root") or Path.cwd())).resolve()
    try:
        matrix = Step174ExecutionRegistry(root).latest(refresh=False)
        row = matrix.loc[matrix["module_key"] == module_key]
        if row.empty:
            return
        value = row.iloc[0].to_dict()
        tables["step174_phase1_to_9_execution"] = pd.DataFrame([value])
        checks.append({
            "check": "Step 174 Phase 1–9 execution",
            "status": "pass" if value["controlled_release_eligible"] else "review",
            "detail": f"Software automation 10/10; externally completed phases {value['completed_phases']}/{value['required_phases']}; next phase {value['next_phase']}",
        })
        metrics.extend([
            {"metric": "Step 174 software phase automation", "value": 10.0, "unit": "/10"},
            {"metric": "Step 174 completed external phases", "value": int(value["completed_phases"]), "unit": "count"},
            {"metric": "Step 174 required external phases", "value": int(value["required_phases"]), "unit": "count"},
        ])
    except Exception as exc:
        checks.append({"check": "Step 174 Phase 1–9 execution", "status": "review", "detail": f"Execution registry unavailable: {exc}"})


__all__ = ["apply_step174_phase_execution_assurance"]
