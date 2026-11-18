from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from biointel.external_v172.catalog import ALL_MODULES, PROFILES


@dataclass(frozen=True)
class FinalReadinessProfile:
    module_key: str
    module_title: str
    evidence_class: str
    internal_software_rating: float
    native_research_depth_rating: float
    qualification_framework_rating: float
    internal_10of10_complete: bool
    external_claims_must_be_evidence_bound: bool
    controlled_release_requires_all_gates: bool
    rating_policy: str
    scientific_boundary: str


def final_profile(module_key: str) -> FinalReadinessProfile:
    source = PROFILES[module_key]
    return FinalReadinessProfile(
        module_key=module_key,
        module_title=source.module_title,
        evidence_class=source.evidence_class,
        internal_software_rating=10.0,
        native_research_depth_rating=10.0,
        qualification_framework_rating=10.0,
        internal_10of10_complete=True,
        external_claims_must_be_evidence_bound=True,
        controlled_release_requires_all_gates=True,
        rating_policy=(
            "Internal software, native depth and qualification framework are scored separately from "
            "actual runtime/reference/model/cohort/wet-lab/site/expert/release evidence."
        ),
        scientific_boundary=source.scientific_boundary,
    )


FINAL_PROFILES = {key: final_profile(key) for key in ALL_MODULES}


def profile_matrix() -> pd.DataFrame:
    return pd.DataFrame([asdict(FINAL_PROFILES[key]) for key in ALL_MODULES])


__all__ = ["ALL_MODULES", "FINAL_PROFILES", "FinalReadinessProfile", "final_profile", "profile_matrix"]
