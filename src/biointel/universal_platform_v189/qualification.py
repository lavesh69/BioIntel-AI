from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .catalog import PLATFORM_DIMENSIONS, PROFILES, TARGET_MODULES
from .generator import module_folder
from .platform import digest_path


@dataclass(frozen=True)
class QualificationResult:
    module_key: str
    rating: float
    qualified_10_of_10: bool
    dimensions_passed: int
    dimensions_total: int
    blockers: tuple[str, ...]
    path: str


REQUIRED_FILES: tuple[str, ...] = (
    "demo_input.csv", "analysis_results.csv", "analysis_summary.json", "engine_status.csv",
    "reference_status.csv", "preflight.json", "job_record.json", "provenance_verification.json",
    "handoff_contract.json", "review_status.json", "monitoring_snapshot.json", "redacted_support_bundle.zip",
    "performance_benchmark.csv", "negative_security_cases.csv", "project_snapshot.json",
    "portable_project.zip", "capability_matrix.csv", "ui_contract.json", "release_boundary.json",
    "reports/report.pdf", "reports/report.docx", "reports/report.html", "reports/report.csv",
    "reports/report.json", "reports/report.md", "reports/report_bundle.zip", "reports/report_manifest.json",
    "qualification_manifest.json", "file_manifest.json",
)


def validate_module(root: Path, module_key: str) -> QualificationResult:
    folder = module_folder(Path(root), module_key)
    blockers: list[str] = []
    if not folder.is_dir():
        return QualificationResult(module_key, 0.0, False, 0, len(PLATFORM_DIMENSIONS), ("missing_module_folder",), str(folder))
    for name in REQUIRED_FILES:
        path = folder / name
        if not path.is_file() or path.stat().st_size <= 0:
            blockers.append(f"missing_or_empty:{name}")
    try:
        q = json.loads((folder / "qualification_manifest.json").read_text(encoding="utf-8"))
        dimensions = q["dimensions"]
        if tuple(x["dimension"] for x in dimensions) != PLATFORM_DIMENSIONS:
            blockers.append("dimension_order_or_scope_mismatch")
        dimensions_passed = sum(int(bool(x["passed"])) for x in dimensions)
    except Exception as exc:
        blockers.append(f"invalid_qualification_manifest:{exc}")
        dimensions_passed = 0
    try:
        preflight = json.loads((folder / "preflight.json").read_text(encoding="utf-8"))
        if preflight.get("decision") != "READY":
            blockers.append("preflight_not_ready")
    except Exception as exc:
        blockers.append(f"invalid_preflight:{exc}")
    try:
        negative = pd.read_csv(folder / "negative_security_cases.csv")
        if len(negative) < 6 or not negative["passed"].astype(bool).all():
            blockers.append("negative_security_cases_failed")
    except Exception as exc:
        blockers.append(f"invalid_negative_cases:{exc}")
    try:
        performance = pd.read_csv(folder / "performance_benchmark.csv")
        if set(performance["records"].astype(int)) != {250, 2500, 10000} or not performance["status"].eq("pass").all():
            blockers.append("performance_benchmark_failed")
    except Exception as exc:
        blockers.append(f"invalid_performance:{exc}")
    try:
        provenance = json.loads((folder / "provenance_verification.json").read_text(encoding="utf-8"))
        if not provenance.get("valid"):
            blockers.append("provenance_chain_invalid")
    except Exception as exc:
        blockers.append(f"invalid_provenance:{exc}")
    try:
        release = json.loads((folder / "release_boundary.json").read_text(encoding="utf-8"))
        if release.get("controlled_release_eligible") is not False:
            blockers.append("controlled_release_must_remain_fail_closed")
    except Exception as exc:
        blockers.append(f"invalid_release_boundary:{exc}")
    rating = round(dimensions_passed / len(PLATFORM_DIMENSIONS) * 10, 2)
    qualified = not blockers and dimensions_passed == len(PLATFORM_DIMENSIONS)
    return QualificationResult(module_key, 10.0 if qualified else rating, qualified, dimensions_passed, len(PLATFORM_DIMENSIONS), tuple(blockers), str(folder))


def rating_matrix(root: Path) -> pd.DataFrame:
    rows = []
    for key in TARGET_MODULES:
        result = validate_module(root, key)
        profile = PROFILES[key]
        rows.append({
            "module_key": key, "title": profile.title, "category": profile.category,
            "before_step189_rating": 10.0, "after_step189_rating": result.rating,
            "rating_gain": round(result.rating - 10.0, 2), "qualified_10_of_10": result.qualified_10_of_10,
            "dimensions_passed": result.dimensions_passed, "dimensions_total": result.dimensions_total,
            "controlled_release_eligible": False, "blockers": ";".join(result.blockers),
        })
    return pd.DataFrame(rows)


__all__ = ["QualificationResult", "validate_module", "rating_matrix", "REQUIRED_FILES"]
