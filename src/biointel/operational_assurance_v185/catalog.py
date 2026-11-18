from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from biointel.portfolio_demo_v183.catalog import PROFILES as V183_PROFILES


@dataclass(frozen=True)
class OperationalAssuranceProfile:
    module_key: str
    title: str
    page: str
    source_step: int
    before_demo_rating: float
    target_demo_rating: float
    baseline_practical_rating: float
    boundary: str


def _ratings() -> dict[str, float]:
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    frame = pd.read_csv(root / "STEP184_80_MODULE_FINAL_DEMO_RATINGS.csv")
    return {str(row.module_key): float(row.step184_demo_assurance_rating) for row in frame.itertuples()}


_CURRENT = _ratings()
TARGET_PROFILES: dict[str, OperationalAssuranceProfile] = {
    key: OperationalAssuranceProfile(
        module_key=key,
        title=profile.title,
        page=profile.page,
        source_step=profile.source_step,
        before_demo_rating=_CURRENT[key],
        target_demo_rating=10.0,
        baseline_practical_rating=profile.baseline_practical_rating,
        boundary=profile.boundary,
    )
    for key, profile in V183_PROFILES.items()
    if 8.0 <= _CURRENT.get(key, 0.0) < 9.0
}
TARGET_MODULES: tuple[str, ...] = tuple(TARGET_PROFILES)
assert len(TARGET_PROFILES) == 19
assert len(set(TARGET_MODULES)) == 19

ASSURANCE_DIMENSIONS: tuple[str, ...] = (
    "native_demo_execution",
    "golden_output_and_schema_contract",
    "calibration_and_threshold_validation",
    "subgroup_and_fairness_validation",
    "leakage_and_independence_controls",
    "privacy_security_and_permission_controls",
    "failure_recovery_and_rollback",
    "load_memory_and_latency_benchmark",
    "repeatability_and_determinism",
    "drift_monitoring_and_alerting",
    "provenance_and_reproducible_report",
    "module_page_and_dashboard_integration",
)

__all__ = ["OperationalAssuranceProfile", "TARGET_PROFILES", "TARGET_MODULES", "ASSURANCE_DIMENSIONS"]
