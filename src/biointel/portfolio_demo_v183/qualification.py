from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import pandas as pd

from .catalog import PROFILES, TARGET_MODULES
from .validators import validate_module_demo


@dataclass(frozen=True)
class PortfolioDemoReadiness:
    module_key: str
    module_title: str
    source_step: int
    baseline_practical_rating: float
    internal_software_rating: float
    demo_operational_rating: float
    demo_improvement_points: float
    demo_improvement_percent: float
    demo_ready: bool
    execution_mode: str
    real_external_rating: float
    real_external_rating_changed: bool
    controlled_release_eligible: bool
    decision: str


def evaluate_module(root: str | Path, module_key: str) -> PortfolioDemoReadiness:
    profile = PROFILES[module_key]
    validation = validate_module_demo(root, module_key)
    rating = profile.demo_operational_rating if validation.demo_ready else profile.baseline_practical_rating
    return PortfolioDemoReadiness(
        module_key=module_key,
        module_title=profile.title,
        source_step=profile.source_step,
        baseline_practical_rating=profile.baseline_practical_rating,
        internal_software_rating=10.0,
        demo_operational_rating=rating,
        demo_improvement_points=round(rating - profile.baseline_practical_rating, 2),
        demo_improvement_percent=round(100 * (rating - profile.baseline_practical_rating) / profile.baseline_practical_rating, 1),
        demo_ready=validation.demo_ready,
        execution_mode=validation.execution_mode,
        real_external_rating=profile.baseline_practical_rating,
        real_external_rating_changed=False,
        controlled_release_eligible=False,
        decision="demo-operationally-ready-real-evidence-pending" if validation.demo_ready else "demo-incomplete",
    )


def portfolio_demo_matrix(root: str | Path) -> pd.DataFrame:
    return pd.DataFrame([asdict(evaluate_module(root, key)) for key in TARGET_MODULES])


def portfolio_demo_detail_matrix(root: str | Path) -> pd.DataFrame:
    rows = []
    for key in TARGET_MODULES:
        profile = PROFILES[key]
        result = validate_module_demo(root, key)
        rows.append({
            "module_key": key,
            "module_title": profile.title,
            "source_step": profile.source_step,
            "demo_ready": result.demo_ready,
            "execution_mode": result.execution_mode,
            "input_records": result.input_records,
            "manifest_passed": result.manifest_passed,
            "negative_cases_passed": result.negative_cases_passed,
            "expected_outputs_passed": result.expected_outputs_passed,
            "hashes_passed": result.hashes_passed,
            "real_external_evidence": False,
            "controlled_release_eligible": False,
            "blockers": list(result.blockers),
            "path": result.path,
        })
    return pd.DataFrame(rows)


__all__ = ["PortfolioDemoReadiness", "evaluate_module", "portfolio_demo_matrix", "portfolio_demo_detail_matrix"]
