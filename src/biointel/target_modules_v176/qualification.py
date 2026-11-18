from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .catalog import TARGET_MODULES, TARGET_PROFILES
from .runtime import probe_engines, probe_references, required_engines, required_references


@dataclass(frozen=True)
class ModuleQualification:
    module_key: str
    module_title: str
    internal_upgrade_rating: float
    workflow_contract_complete: bool
    quality_gate_contract_complete: bool
    output_contract_complete: bool
    ui_hook_present: bool
    engine_plan_complete: bool
    reference_plan_complete: bool
    engine_discovery_fraction: float
    reference_qualification_fraction: float
    controlled_release_eligible: bool
    decision: str
    remaining_blockers: tuple[str, ...]


def _fraction(values: list[bool]) -> float:
    return 1.0 if not values else sum(values) / len(values)


def evaluate_module(root: str | Path, module_key: str, *, execute_smoke_tests: bool = False) -> ModuleQualification:
    root_path = Path(root).resolve()
    profile = TARGET_PROFILES[module_key]
    page = root_path / profile.page
    page_text = page.read_text(encoding="utf-8-sig") if page.is_file() else ""
    ui_hook = "render_target_module_upgrade" in page_text and module_key in page_text
    engine_plan = required_engines(module_key)
    reference_plan = required_references(module_key)
    engines = probe_engines(module_key, execute_smoke_tests=execute_smoke_tests)
    references = probe_references(root_path, module_key)
    engine_fraction = _fraction(engines.get("probe_status", pd.Series(dtype=str)).eq("pass").tolist()) if execute_smoke_tests else _fraction(engines.get("discovered", pd.Series(dtype=bool)).astype(bool).tolist())
    reference_fraction = _fraction(references.get("qualification_status", pd.Series(dtype=str)).eq("qualified").tolist())
    contract_checks = [
        len(profile.workflow) >= 5,
        len(profile.quality_gates) >= 5,
        len(profile.required_outputs) >= 5,
        bool(profile.boundary),
        ui_hook,
        len(engine_plan) > 0,
        len(reference_plan) > 0,
    ]
    internal_rating = round(10.0 * sum(contract_checks) / len(contract_checks), 2)
    release_eligible = bool(internal_rating == 10.0 and engine_fraction == 1.0 and reference_fraction == 1.0)
    blockers: list[str] = []
    if not ui_hook:
        blockers.append("module UI hook missing")
    if engine_fraction < 1.0:
        blockers.append("one or more specialist engines are not discovered/smoke-qualified")
    if reference_fraction < 1.0:
        blockers.append("one or more production references lack complete qualification manifests")
    blockers.extend([
        "independent cohort/site confirmation is not automatically inferable",
        "wet-lab/orthogonal evidence must be attached where applicable",
        "expert sign-off and formal release review must be completed externally",
    ])
    return ModuleQualification(
        module_key=module_key,
        module_title=profile.title,
        internal_upgrade_rating=internal_rating,
        workflow_contract_complete=len(profile.workflow) >= 5,
        quality_gate_contract_complete=len(profile.quality_gates) >= 5,
        output_contract_complete=len(profile.required_outputs) >= 5,
        ui_hook_present=ui_hook,
        engine_plan_complete=len(engine_plan) > 0,
        reference_plan_complete=len(reference_plan) > 0,
        engine_discovery_fraction=round(engine_fraction, 4),
        reference_qualification_fraction=round(reference_fraction, 4),
        controlled_release_eligible=release_eligible,
        decision="controlled-runtime-ready; external evidence still required" if release_eligible else "research-only-fail-closed",
        remaining_blockers=tuple(dict.fromkeys(blockers)),
    )


def qualification_matrix(root: str | Path, *, execute_smoke_tests: bool = False) -> pd.DataFrame:
    return pd.DataFrame([asdict(evaluate_module(root, key, execute_smoke_tests=execute_smoke_tests)) for key in TARGET_MODULES])


__all__ = ["ModuleQualification", "evaluate_module", "qualification_matrix"]
