from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import pandas as pd

from .catalog import TARGET_MODULES, TARGET_PROFILES
from .validators import validate_step184_module


def step184_rating_matrix(root: str | Path) -> pd.DataFrame:
    rows = []
    for key in TARGET_MODULES:
        profile = TARGET_PROFILES[key]
        result = validate_step184_module(root, key)
        rows.append({
            "module_key": key,
            "module_title": profile.title,
            "before_demo_rating": profile.before_demo_rating,
            "after_demo_assurance_rating": result.rating if result.qualified_10_of_10 else profile.before_demo_rating,
            "improvement_points": round((result.rating if result.qualified_10_of_10 else profile.before_demo_rating) - profile.before_demo_rating, 2),
            "qualified_10_of_10": result.qualified_10_of_10,
            "dimensions_passed": result.dimensions_passed,
            "dimensions_total": result.dimensions_total,
            "real_external_rating": profile.baseline_practical_rating,
            "real_external_rating_changed": False,
            "controlled_release_eligible": False,
            "blockers": list(result.blockers),
        })
    return pd.DataFrame(rows)


def step184_validation_matrix(root: str | Path) -> pd.DataFrame:
    return pd.DataFrame([asdict(validate_step184_module(root, key)) for key in TARGET_MODULES])


__all__ = ["step184_rating_matrix", "step184_validation_matrix"]
