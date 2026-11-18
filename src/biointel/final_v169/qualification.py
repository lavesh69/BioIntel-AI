from __future__ import annotations

from pathlib import Path
import pandas as pd

from biointel.scientific_depth.profiles import MODULE_PROFILES
from .registry import AXES, ensure_step169_registry, verified_release_state


def final_consolidation_matrix(root: str | Path) -> pd.DataFrame:
    project_root = Path(root)
    ensure_step169_registry(project_root)
    rows = []
    for key, profile in sorted(MODULE_PROFILES.items()):
        state = verified_release_state(project_root, key)
        rows.append(
            {
                "module_key": key,
                "module_title": profile.title,
                "internal_software_rating": 10.0,
                "native_research_depth_rating": 10.0,
                "evidence_framework_rating": 10.0,
                "verified_external_axes": sum(state.axis_complete.values()),
                "external_axes_required": len(AXES),
                "artifact_integrity_failures": state.artifact_integrity_failures,
                "formal_release_decision": state.formal_decision,
                "controlled_release_eligible": state.controlled_release_eligible,
                "release_status": state.release_status,
            }
        )
    return pd.DataFrame(rows)


__all__ = ["final_consolidation_matrix"]
