from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import pandas as pd

from biointel.external_readiness_v181 import PROFILES, TARGET_MODULES
from .validators import validate_demo_folder


@dataclass(frozen=True)
class DemoModuleReadiness:
    module_key: str
    module_title: str
    demo_packs_required: int
    demo_packs_ready: int
    demo_completion_fraction: float
    demo_execution_ready: bool
    real_evidence_packs: int
    controlled_release_eligible: bool
    decision: str


def evaluate_demo_module(root: str | Path, module_key: str) -> DemoModuleReadiness:
    profile = PROFILES[module_key]
    results = [validate_demo_folder(root, module_key, req) for req in profile.requirements]
    ready = sum(result.demo_ready for result in results)
    required = len(results)
    return DemoModuleReadiness(
        module_key=module_key,
        module_title=profile.title,
        demo_packs_required=required,
        demo_packs_ready=ready,
        demo_completion_fraction=round(ready / required if required else 1.0, 4),
        demo_execution_ready=ready == required and required > 0,
        real_evidence_packs=0,
        controlled_release_eligible=False,
        decision="demo-ready-real-evidence-pending" if ready == required else "demo-files-incomplete",
    )


def demo_qualification_matrix(root: str | Path) -> pd.DataFrame:
    return pd.DataFrame([asdict(evaluate_demo_module(root, key)) for key in TARGET_MODULES])


def demo_detail_matrix(root: str | Path, module_key: str | None = None) -> pd.DataFrame:
    keys = (module_key,) if module_key else TARGET_MODULES
    rows = []
    for key in keys:
        profile = PROFILES[key]
        for req in profile.requirements:
            result = validate_demo_folder(root, key, req)
            rows.append({
                "module_key": key, "module_title": profile.title,
                "evidence_id": req.evidence_id, "evidence_title": req.title,
                "manifest_passed": result.manifest_passed,
                "data_passed": result.data_passed, "demo_ready": result.demo_ready,
                "real_evidence": False, "controlled_release_eligible": False,
                "record_count": result.record_count, "metrics": result.metrics,
                "blockers": result.blockers, "path": result.path,
            })
    return pd.DataFrame(rows)


__all__ = ["DemoModuleReadiness", "evaluate_demo_module", "demo_qualification_matrix", "demo_detail_matrix"]
