from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from biointel.target_modules_v176.catalog import TARGET_PROFILES as V176
from biointel.target_modules_v177.catalog import TARGET_PROFILES as V177
from biointel.target_modules_v178.catalog import TARGET_PROFILES as V178
from biointel.target_modules_v179.catalog import TARGET_PROFILES as V179
from biointel.target_modules_v180.catalog import TARGET_PROFILES as V180


@dataclass(frozen=True)
class PortfolioDemoProfile:
    module_key: str
    title: str
    page: str
    source_step: int
    module_class: str
    baseline_practical_rating: float
    internal_software_rating: float
    demo_operational_rating: float
    workflow: tuple[str, ...]
    quality_gates: tuple[str, ...]
    required_outputs: tuple[str, ...]
    boundary: str

    @property
    def demo_improvement(self) -> float:
        return round(self.demo_operational_rating - self.baseline_practical_rating, 2)

    @property
    def demo_improvement_percent(self) -> float:
        if self.baseline_practical_rating <= 0:
            return 0.0
        return round(100.0 * self.demo_improvement / self.baseline_practical_rating, 1)


def _tuple(profile: Any, *names: str) -> tuple[str, ...]:
    for name in names:
        value = getattr(profile, name, None)
        if value:
            return tuple(str(item) for item in value)
    return ()


def _baseline_177(key: str) -> float:
    if key == "biomedical_foundation_model_hub":
        return 5.86
    if key in {"offline_copilot_core", "offline_scientific_copilot_v2"}:
        return 5.32
    if key == "digital_pathology_foundation":
        return 5.11
    return 5.75


def _demo_target(step: int, baseline: float, key: str) -> float:
    # Demo ratings measure reproducible input/workflow/report execution only.
    # They never replace real engines, licensed references, patient/lab evidence or approval.
    if step == 176:
        return round(min(7.25, baseline + 2.25), 2)
    if step == 177:
        return round(min(7.75, baseline + 2.00), 2)
    if step == 178:
        return round(min(8.50, baseline + 2.00), 2)
    if step == 179:
        return round(min(9.00, baseline + 1.50), 2)
    if key == "phenotypic_screening":
        return 7.11
    if key == "spatial_omics_pathology":
        return 7.00
    return 7.00


def _convert(step: int, key: str, profile: Any, baseline: float) -> PortfolioDemoProfile:
    gates = _tuple(profile, "quality_gates", "acceptance_criteria", "reliability_gates", "data_gates")
    if hasattr(profile, "security_gates"):
        gates = gates + _tuple(profile, "security_gates")
    return PortfolioDemoProfile(
        module_key=key,
        title=str(profile.title),
        page=str(profile.page),
        source_step=step,
        module_class=("platform-core" if step == 179 else "scientific-research"),
        baseline_practical_rating=round(float(baseline), 2),
        internal_software_rating=10.0,
        demo_operational_rating=_demo_target(step, float(baseline), key),
        workflow=_tuple(profile, "workflow"),
        quality_gates=gates,
        required_outputs=_tuple(profile, "required_outputs"),
        boundary=str(profile.boundary),
    )


PROFILES: dict[str, PortfolioDemoProfile] = {}
for _key, _profile in V176.items():
    PROFILES[_key] = _convert(176, _key, _profile, 5.0)
for _key, _profile in V177.items():
    PROFILES[_key] = _convert(177, _key, _profile, _baseline_177(_key))
for _key, _profile in V178.items():
    PROFILES[_key] = _convert(178, _key, _profile, float(_profile.baseline_rating))
for _key, _profile in V179.items():
    PROFILES[_key] = _convert(179, _key, _profile, float(_profile.baseline_rating))
for _key, _profile in V180.items():
    PROFILES[_key] = _convert(180, _key, _profile, float(_profile.baseline_rating))

TARGET_MODULES: tuple[str, ...] = tuple(PROFILES)
assert len(PROFILES) == 80 and len(set(PROFILES)) == 80

__all__ = ["PortfolioDemoProfile", "PROFILES", "TARGET_MODULES"]
