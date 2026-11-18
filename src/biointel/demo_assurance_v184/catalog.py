from __future__ import annotations

from dataclasses import dataclass

from biointel.portfolio_demo_v183.catalog import PROFILES as V183_PROFILES


@dataclass(frozen=True)
class DemoAssuranceProfile:
    module_key: str
    title: str
    page: str
    source_step: int
    before_demo_rating: float
    target_demo_rating: float
    baseline_practical_rating: float
    boundary: str


TARGET_PROFILES: dict[str, DemoAssuranceProfile] = {
    key: DemoAssuranceProfile(
        module_key=key,
        title=profile.title,
        page=profile.page,
        source_step=profile.source_step,
        before_demo_rating=profile.demo_operational_rating,
        target_demo_rating=10.0,
        baseline_practical_rating=profile.baseline_practical_rating,
        boundary=profile.boundary,
    )
    for key, profile in V183_PROFILES.items()
    if profile.demo_operational_rating < 8.0
}
TARGET_MODULES: tuple[str, ...] = tuple(TARGET_PROFILES)

assert len(TARGET_PROFILES) == 43
assert len(set(TARGET_MODULES)) == 43

ASSURANCE_DIMENSIONS: tuple[str, ...] = (
    "deterministic_execution",
    "golden_output_contract",
    "negative_and_security_cases",
    "boundary_and_stress_execution",
    "performance_benchmark",
    "repeatability_hash_match",
    "offline_fallback",
    "provenance_manifest",
    "reproducible_report_export",
    "module_page_integration",
)

__all__ = ["DemoAssuranceProfile", "TARGET_PROFILES", "TARGET_MODULES", "ASSURANCE_DIMENSIONS"]
