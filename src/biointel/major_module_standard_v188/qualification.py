from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import pandas as pd

from .catalog import PROFILES, TARGET_MODULES
from .validators import validate_module


def step188_rating_matrix(root: str | Path) -> pd.DataFrame:
    rows = []
    for key in TARGET_MODULES:
        result = validate_module(root, key)
        rows.append({
            **asdict(result),
            "module_title": PROFILES[key].title,
            "page": PROFILES[key].page,
            "before_internal_demo_rating": 10.0,
            "after_step188_rating": result.rating,
            "controlled_release_eligible": False,
        })
    return pd.DataFrame(rows)


__all__ = ["step188_rating_matrix"]
