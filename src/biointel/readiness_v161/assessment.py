from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from biointel.quality_v160 import assess_module_quality
from biointel.scientific_depth.native_workflows import native_workflow_spec
from biointel.scientific_depth.profiles import MODULE_PROFILES
from biointel.scientific_depth.toolchain_readiness import reference_readiness

from .catalog import module_runtime_path_matrix, runtime_detection_matrix, runtime_recipe_catalog
from .reference_kits import development_reference_readiness
from .validation_protocols import validation_protocol_readiness


@dataclass(frozen=True)
class ModuleUpgradeAssessment:
    module_key: str
    title: str
    native_family: str
    internal_quality_score: float
    execution_path_score: float
    development_reference_score: float
    validation_protocol_score: float
    step161_upgrade_score: float
    specialist_engines_installed: int
    specialist_engines_required: int
    production_references_qualified: int
    production_references_required: int
    external_evidence_score: float
    real_world_release_eligible: bool
    upgrade_status: str
    remaining_external_blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _score(passed: int, total: int) -> float:
    return round(10.0 if total == 0 else 10.0 * passed / total, 1)


def assess_module_upgrade(
    root: str | Path,
    module_key: str,
    *,
    evidence: Mapping[str, Any] | None = None,
    runtime_matrix: pd.DataFrame | None = None,
    production_references: pd.DataFrame | None = None,
    development_references: pd.DataFrame | None = None,
    protocols: pd.DataFrame | None = None,
) -> ModuleUpgradeAssessment:
    root_path = Path(root).expanduser().resolve()
    profile = MODULE_PROFILES[module_key]
    base = assess_module_quality(root_path, module_key, evidence=evidence)

    module_paths = module_runtime_path_matrix(module_key) if runtime_matrix is None else runtime_matrix
    if "module_key" in module_paths.columns:
        module_paths = module_paths.loc[module_paths["module_key"].astype(str) == module_key]
    execution_total = int(len(module_paths))
    execution_ready = int(module_paths["operational_path_ready"].astype(bool).sum()) if execution_total else 0
    installed = int(module_paths["installed"].astype(bool).sum()) if execution_total and "installed" in module_paths.columns else 0
    specialist_required = int((module_paths["engine"].astype(str) != "biointel_native").sum()) if execution_total else 0
    if specialist_required == 0:
        installed = 0

    dev_rows = development_reference_readiness(root_path, [module_key]) if development_references is None else development_references
    if "module_key" in dev_rows.columns:
        dev_rows = dev_rows.loc[dev_rows["module_key"].astype(str) == module_key]
    dev_total = int(len(dev_rows))
    dev_ready = int(dev_rows["development_qualified"].astype(bool).sum()) if dev_total else 0

    protocol_rows = validation_protocol_readiness(root_path, [module_key]) if protocols is None else protocols
    if "module_key" in protocol_rows.columns:
        protocol_rows = protocol_rows.loc[protocol_rows["module_key"].astype(str) == module_key]
    protocol_ready = int(protocol_rows["protocol_ready"].astype(bool).sum()) if not protocol_rows.empty else 0
    protocol_total = max(1, int(len(protocol_rows)))

    prod_rows = reference_readiness(root_path, [module_key]) if production_references is None else production_references
    if "module_key" in prod_rows.columns:
        prod_rows = prod_rows.loc[prod_rows["module_key"].astype(str) == module_key]
    prod_total = len(profile.references)
    prod_ready = int(prod_rows["qualified_for_use"].astype(bool).sum()) if not prod_rows.empty else 0

    execution_score = _score(execution_ready, execution_total)
    dev_score = _score(dev_ready, dev_total)
    protocol_score = _score(protocol_ready, protocol_total)
    upgrade_score = round((base.internal_quality_score + execution_score + dev_score + protocol_score) / 4.0, 1)

    blockers: list[str] = []
    if installed < specialist_required:
        blockers.append(f"Installed specialist runtimes: {installed}/{specialist_required}")
    if prod_ready < prod_total:
        blockers.append(f"Production references qualified: {prod_ready}/{prod_total}")
    if base.external_evidence_score < 100.0:
        blockers.append(f"External evidence score: {base.external_evidence_score:.1f}/100")

    release_eligible = bool(
        upgrade_score == 10.0
        and installed == specialist_required
        and prod_ready == prod_total
        and base.external_evidence_score == 100.0
    )
    return ModuleUpgradeAssessment(
        module_key=module_key,
        title=profile.title,
        native_family=native_workflow_spec(module_key).family,
        internal_quality_score=base.internal_quality_score,
        execution_path_score=execution_score,
        development_reference_score=dev_score,
        validation_protocol_score=protocol_score,
        step161_upgrade_score=upgrade_score,
        specialist_engines_installed=installed,
        specialist_engines_required=specialist_required,
        production_references_qualified=prod_ready,
        production_references_required=prod_total,
        external_evidence_score=base.external_evidence_score,
        real_world_release_eligible=release_eligible,
        upgrade_status="10/10 software upgrade complete" if upgrade_score == 10.0 else "Software upgrade review required",
        remaining_external_blockers=tuple(blockers),
    )


def portfolio_upgrade_matrix(
    root: str | Path,
    *,
    evidence_by_module: Mapping[str, Mapping[str, Any]] | None = None,
    detect_runtime: bool = True,
) -> pd.DataFrame:
    root_path = Path(root).expanduser().resolve()
    recipes = runtime_recipe_catalog()
    detected = runtime_detection_matrix() if detect_runtime else recipes.assign(installed=False, operational_path_ready=recipes["recipe_complete"])
    production_refs = reference_readiness(root_path)
    development_refs = development_reference_readiness(root_path)
    protocols = validation_protocol_readiness(root_path)
    rows: list[dict[str, Any]] = []
    for module_key in sorted(MODULE_PROFILES):
        profile = MODULE_PROFILES[module_key]
        engines = [engine.lower() for engine in profile.engines if not engine.startswith("biointel_native::")]
        if engines:
            module_runtime = detected.loc[detected["engine"].astype(str).isin(engines)].copy()
            module_runtime.insert(0, "module_key", module_key)
        else:
            module_runtime = module_runtime_path_matrix(module_key)
        record = assess_module_upgrade(
            root_path,
            module_key,
            evidence=(evidence_by_module or {}).get(module_key),
            runtime_matrix=module_runtime,
            production_references=production_refs,
            development_references=development_refs,
            protocols=protocols,
        )
        row = record.to_dict()
        row["remaining_external_blockers"] = " | ".join(record.remaining_external_blockers)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["step161_upgrade_score", "real_world_release_eligible", "module_key"],
        ascending=[True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)


def portfolio_upgrade_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"modules": 0, "step161_10_of_10": 0, "real_world_release_eligible": 0}
    return {
        "schema": "biointel.step161.portfolio-upgrade-summary.v1",
        "modules": int(len(frame)),
        "step161_10_of_10": int(frame["step161_upgrade_score"].eq(10.0).sum()),
        "execution_paths_10_of_10": int(frame["execution_path_score"].eq(10.0).sum()),
        "development_references_10_of_10": int(frame["development_reference_score"].eq(10.0).sum()),
        "validation_protocols_10_of_10": int(frame["validation_protocol_score"].eq(10.0).sum()),
        "real_world_release_eligible": int(frame["real_world_release_eligible"].astype(bool).sum()),
        "software_upgrade_and_external_validation_are_separate": True,
    }


__all__ = [
    "ModuleUpgradeAssessment",
    "assess_module_upgrade",
    "portfolio_upgrade_matrix",
    "portfolio_upgrade_summary",
]
