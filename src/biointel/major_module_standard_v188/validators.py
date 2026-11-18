from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd

from .catalog import COMPULSORY_DIMENSIONS, PROFILES, STANDARD_TABS
from .engine import digest_path, module_folder


@dataclass(frozen=True)
class MajorModuleValidation:
    module_key: str
    qualified_10_of_10: bool
    rating: float
    dimensions_passed: int
    dimensions_total: int
    tabs_passed: int
    tabs_total: int
    blockers: tuple[str, ...]
    path: str


def validate_module(root: str | Path, module_key: str) -> MajorModuleValidation:
    root = Path(root).resolve()
    folder = module_folder(root, module_key)
    blockers: list[str] = []
    required = (
        "demo_input.csv", "input_schema.csv", "qc_checks.csv", "sample_qc.csv",
        "analysis_results.csv", "analysis_summary.json", "workflow_stages.csv",
        "visual_catalog.csv", "validation_matrix.csv", "negative_security_cases.csv",
        "performance_benchmark.csv", "repeatability.csv", "interpretation.md",
        "reproducible_report.md", "run_history.csv", "environment_manifest.json",
        "recovery_contract.json", "security_governance.json", "accessibility_contract.json",
        "integration_contract.json", "tab_contract.json", "file_manifest_sha256.json",
        "qualification_manifest.json",
    )
    for name in required:
        if not (folder / name).is_file():
            blockers.append(f"missing:{name}")
    if blockers:
        return MajorModuleValidation(module_key, False, 0.0, 0, len(COMPULSORY_DIMENSIONS), 0, len(STANDARD_TABS), tuple(blockers), str(folder))
    manifest = json.loads((folder / "qualification_manifest.json").read_text(encoding="utf-8"))
    dimensions = manifest.get("dimensions", [])
    if tuple(x.get("dimension") for x in dimensions) != COMPULSORY_DIMENSIONS:
        blockers.append("dimension_order_or_scope")
    if not all(bool(x.get("passed")) for x in dimensions):
        blockers.append("dimension_failure")
    tabs = json.loads((folder / "tab_contract.json").read_text(encoding="utf-8")).get("tabs", [])
    if tuple(tabs) != STANDARD_TABS:
        blockers.append("tab_contract")
    negative = pd.read_csv(folder / "negative_security_cases.csv")
    performance = pd.read_csv(folder / "performance_benchmark.csv")
    repeatability = pd.read_csv(folder / "repeatability.csv")
    qc = pd.read_csv(folder / "qc_checks.csv")
    validation = pd.read_csv(folder / "validation_matrix.csv")
    if len(negative) < 14 or not negative.passed.astype(bool).all():
        blockers.append("negative_security_cases")
    if set(performance.records.astype(int)) != {250, 2500, 10000} or not performance.status.eq("pass").all():
        blockers.append("performance")
    if len(repeatability) != 3 or not repeatability.passed.astype(bool).all() or repeatability.output_sha256.nunique() != 1:
        blockers.append("repeatability")
    if qc.status.eq("fail").any():
        blockers.append("qc")
    if not validation.status.isin(["pass", "pending"]).all():
        blockers.append("validation")
    file_manifest = json.loads((folder / "file_manifest_sha256.json").read_text(encoding="utf-8"))
    for entry in file_manifest.get("files", []):
        path = folder / entry["path"]
        if not path.is_file() or digest_path(path) != entry["sha256"]:
            blockers.append(f"hash:{entry['path']}")
    page = root / PROFILES[module_key].page
    source = page.read_text(encoding="utf-8-sig") if page.is_file() else ""
    if "STEP188_MAJOR_MODULE_STANDARD_HOOK" not in source:
        blockers.append("page_hook")
    qualified = not blockers
    return MajorModuleValidation(
        module_key=module_key,
        qualified_10_of_10=qualified,
        rating=10.0 if qualified else 0.0,
        dimensions_passed=sum(bool(x.get("passed")) for x in dimensions),
        dimensions_total=len(COMPULSORY_DIMENSIONS),
        tabs_passed=len(tabs) if tuple(tabs) == STANDARD_TABS else 0,
        tabs_total=len(STANDARD_TABS),
        blockers=tuple(blockers),
        path=str(folder),
    )


__all__ = ["MajorModuleValidation", "validate_module"]
