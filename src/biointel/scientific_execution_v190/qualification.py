from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .catalog import EXECUTION_DIMENSIONS, PROFILES, TARGET_MODULES
from .generator import module_folder


@dataclass(frozen=True)
class QualificationResult:
    module_key: str
    rating: float
    qualified_10_of_10: bool
    dimensions_passed: int
    dimensions_total: int
    blockers: tuple[str, ...]
    controlled_release_eligible: bool


def validate_module(root: Path, module_key: str) -> QualificationResult:
    folder = module_folder(Path(root), module_key)
    path = folder / "qualification_manifest.json"
    blockers: list[str] = []
    if module_key not in PROFILES:
        return QualificationResult(module_key, 0.0, False, 0, len(EXECUTION_DIMENSIONS), ("unknown-module",), False)
    if not path.is_file():
        return QualificationResult(module_key, 0.0, False, 0, len(EXECUTION_DIMENSIONS), ("missing-qualification-manifest",), False)
    payload = json.loads(path.read_text(encoding="utf-8"))
    dimensions = payload.get("dimensions", [])
    if len(dimensions) != len(EXECUTION_DIMENSIONS): blockers.append("dimension-count")
    for row in dimensions:
        if not row.get("passed"): blockers.append(str(row.get("dimension")))
    if not payload.get("benchmark_passed"): blockers.append("truth-benchmark")
    if not payload.get("streaming_passed"): blockers.append("streaming-benchmark")
    required = ["step190_execution_bundle.zip", "native_viewer.html", "truth_benchmark_metrics.csv", "engine_adapter_matrix.csv", "file_manifest.json"]
    for name in required:
        if not (folder / name).is_file(): blockers.append(f"missing:{name}")
    passed = int(payload.get("dimensions_passed", 0))
    total = int(payload.get("dimensions_total", len(EXECUTION_DIMENSIONS)))
    qualified = not blockers and bool(payload.get("qualified_10_of_10"))
    rating = 10.0 if qualified else round(passed / max(1, total) * 10, 2)
    return QualificationResult(module_key, rating, qualified, passed, total, tuple(blockers), False)


def rating_matrix(root: Path) -> pd.DataFrame:
    rows = []
    for key in TARGET_MODULES:
        result = validate_module(root, key)
        p = PROFILES[key]
        rows.append({"module_key": key, "title": p.title, "category": p.category, "before_step190_rating": 10.0,
                     "after_step190_rating": result.rating, "qualified_10_of_10": result.qualified_10_of_10,
                     "dimensions_passed": result.dimensions_passed, "dimensions_total": result.dimensions_total,
                     "controlled_release_eligible": False, "blockers": "; ".join(result.blockers)})
    return pd.DataFrame(rows)


__all__ = ["QualificationResult", "validate_module", "rating_matrix"]
