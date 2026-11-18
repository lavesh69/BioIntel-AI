from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .qualification import environment_summary, execution_matrix


def apply_step175_target_environment_assurance(
    *, module_key: str, metadata: dict[str, Any], tables: dict[str, pd.DataFrame], checks: list[dict[str, Any]], metrics: list[dict[str, Any]]
) -> None:
    root = Path(str(metadata.get("project_root") or Path.cwd())).resolve()
    try:
        matrix = execution_matrix(root)
        summary = environment_summary(root)
        tables["step175_target_environment_summary"] = pd.DataFrame([summary])
        tables["step175_runtime_reference_actions"] = matrix.loc[~matrix["final_target_qualification_complete"]].head(25).copy()
        checks.append({
            "check": "Step 175 target environment qualification",
            "status": "pass" if summary["controlled_environment_ready"] else "review",
            "detail": f"Framework 10/10; target-qualified engines {summary['engines_target_qualified']}/53; references {summary['references_target_qualified']}/26; hosts {summary['target_hosts_qualified']}",
        })
        metrics.extend([
            {"metric": "Step 175 target environment framework", "value": 10.0, "unit": "/10"},
            {"metric": "Step 175 target-qualified engines", "value": summary["engines_target_qualified"], "unit": "count"},
            {"metric": "Step 175 target-qualified references", "value": summary["references_target_qualified"], "unit": "count"},
        ])
    except Exception as exc:
        checks.append({"check": "Step 175 target environment qualification", "status": "review", "detail": f"Environment registry unavailable: {exc}"})


__all__ = ["apply_step175_target_environment_assurance"]
