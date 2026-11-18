from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from .catalog import PROFILES, TARGET_MODULES
from .validators import validate_evidence_folder


@dataclass(frozen=True)
class ModuleExternalReadiness:
    module_key: str
    module_title: str
    weakness_remediation_workflow_rating: float
    evidence_packs_required: int
    evidence_packs_qualified: int
    evidence_completion_fraction: float
    manifest_completion_fraction: float
    data_validation_fraction: float
    controlled_release_eligible: bool
    decision: str
    remaining_evidence: tuple[str, ...]
    release_boundary: str


def evaluate_module(root: str | Path, module_key: str) -> ModuleExternalReadiness:
    profile = PROFILES[module_key]
    results = [validate_evidence_folder(root, module_key, requirement) for requirement in profile.requirements]
    required = len(results)
    qualified = sum(result.qualified for result in results)
    manifest_fraction = sum(result.manifest_passed for result in results) / required if required else 1.0
    data_fraction = sum(result.data_passed for result in results) / required if required else 1.0
    completion = qualified / required if required else 1.0
    remaining = tuple(
        requirement.title
        for requirement, result in zip(profile.requirements, results)
        if not result.qualified
    )
    eligible = qualified == required and required > 0
    return ModuleExternalReadiness(
        module_key=module_key,
        module_title=profile.title,
        weakness_remediation_workflow_rating=10.0,
        evidence_packs_required=required,
        evidence_packs_qualified=qualified,
        evidence_completion_fraction=round(completion, 4),
        manifest_completion_fraction=round(manifest_fraction, 4),
        data_validation_fraction=round(data_fraction, 4),
        controlled_release_eligible=eligible,
        decision="controlled-release-evidence-complete" if eligible else "operational-workflow-complete-real-evidence-pending",
        remaining_evidence=remaining,
        release_boundary=profile.release_boundary,
    )


def qualification_matrix(root: str | Path) -> pd.DataFrame:
    return pd.DataFrame([asdict(evaluate_module(root, key)) for key in TARGET_MODULES])


def evidence_detail_matrix(root: str | Path, module_key: str | None = None) -> pd.DataFrame:
    keys = (module_key,) if module_key else TARGET_MODULES
    rows: list[dict[str, object]] = []
    for key in keys:
        profile = PROFILES[key]
        for requirement in profile.requirements:
            result = validate_evidence_folder(root, key, requirement)
            rows.append(
                {
                    "module_key": key,
                    "module_title": profile.title,
                    "evidence_id": requirement.evidence_id,
                    "evidence_title": requirement.title,
                    "manifest_passed": result.manifest_passed,
                    "data_passed": result.data_passed,
                    "qualified": result.qualified,
                    "record_count": result.record_count,
                    "metrics": result.metrics,
                    "blockers": result.blockers,
                    "path": result.path,
                    "acceptance_summary": requirement.acceptance_summary,
                }
            )
    return pd.DataFrame(rows)


__all__ = ["ModuleExternalReadiness", "evaluate_module", "qualification_matrix", "evidence_detail_matrix"]
