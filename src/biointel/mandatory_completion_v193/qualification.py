from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import pandas as pd

from .catalog import MANDATORY_DIMENSIONS, PROFILES
from .engine import module_folder

@dataclass(frozen=True)
class Qualification:
    module_key: str
    rating: float
    passed: int
    total: int
    qualified: bool
    blockers: tuple[str, ...]
    path: str

REQUIRED_FILES = (
    "intended_use.json", "input_and_identity.json", "data_governance.json",
    "autosave_recovery.json", "session_resource_policy.json", "dependency_health.json",
    "confidence_and_release.json", "integrity_and_provenance.json",
    "review_and_change_control.json", "feature_and_migration.json",
    "accessibility_security_support.json", "monitoring_and_capabilities.json",
    "qualification_manifest.json", "MANDATORY_COMPLETION_REPORT.md",
)

def validate_module(root: Path, module_key: str) -> Qualification:
    folder = module_folder(root, module_key)
    blockers = [name for name in REQUIRED_FILES if not (folder / name).is_file()]
    passed = 0
    total = len(MANDATORY_DIMENSIONS)
    if not blockers:
        try:
            manifest = json.loads((folder / "qualification_manifest.json").read_text(encoding="utf-8"))
            rows = manifest.get("dimensions", [])
            if tuple(x.get("dimension") for x in rows) != MANDATORY_DIMENSIONS:
                blockers.append("dimension_order_or_scope")
            passed = sum(bool(x.get("passed")) for x in rows)
            if passed != total:
                blockers.append("dimension_failure")
            if manifest.get("controlled_release_eligible"):
                blockers.append("unsafe_external_release_claim")
        except Exception as exc:
            blockers.append(f"manifest_unreadable:{type(exc).__name__}")
    qualified = not blockers and passed == total
    return Qualification(module_key, 10.0 if qualified else round(10.0 * passed / max(total, 1), 2), passed, total, qualified, tuple(blockers), str(folder))


def rating_matrix(root: Path) -> pd.DataFrame:
    rows=[]
    for key, profile in PROFILES.items():
        q=validate_module(root,key)
        rows.append({"module_key":key,"title":profile.title,"category":profile.category,"page":profile.page,"before_step193_rating":10.0,"after_step193_rating":q.rating,"checks_passed":q.passed,"checks_total":q.total,"qualified":q.qualified,"controlled_release_eligible":False})
    return pd.DataFrame(rows)

__all__=["Qualification","validate_module","rating_matrix","REQUIRED_FILES"]
