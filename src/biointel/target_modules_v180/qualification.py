from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from .catalog import TARGET_MODULES, TARGET_PROFILES
from .checks import smoke_passed
from .runtime import (
    probe_cohorts,
    probe_components,
    probe_external_evidence,
    probe_fixtures,
    probe_governance,
    probe_models,
    probe_references,
    required_cohorts,
    required_components,
    required_models,
    required_references,
)


@dataclass(frozen=True)
class ModuleQualification:
    module_key: str
    module_title: str
    baseline_rating: float
    internal_after_rating: float
    rating_improvement: float
    improvement_percent: float
    workflow_contract_complete: bool
    data_contract_complete: bool
    model_contract_complete: bool
    scientific_contract_complete: bool
    acceptance_contract_complete: bool
    output_contract_complete: bool
    risk_contract_complete: bool
    monitoring_contract_complete: bool
    ui_hook_present: bool
    component_plan_complete: bool
    reference_plan_complete: bool
    model_plan_complete: bool
    cohort_plan_complete: bool
    fixture_plan_complete: bool
    governance_plan_complete: bool
    deterministic_scientific_smoke_passed: bool
    component_qualification_fraction: float
    reference_qualification_fraction: float
    model_qualification_fraction: float
    cohort_qualification_fraction: float
    fixture_qualification_fraction: float
    governance_qualification_fraction: float
    external_evidence_fraction: float
    controlled_release_eligible: bool
    decision: str
    remaining_blockers: tuple[str, ...]


def _fraction(frame: pd.DataFrame, column: str, value: object) -> float:
    return 1.0 if frame.empty else float(frame[column].eq(value).mean())


def evaluate_module(root: str | Path, module_key: str, execute_component_probes: bool = False) -> ModuleQualification:
    root = Path(root).resolve()
    profile = TARGET_PROFILES[module_key]
    page = root / profile.page
    page_text = page.read_text(encoding="utf-8-sig") if page.is_file() else ""
    hook = "render_step180_module_upgrade" in page_text and module_key in page_text

    components_plan = required_components(module_key)
    references_plan = required_references(module_key)
    models_plan = required_models(module_key)
    cohorts_plan = required_cohorts(module_key)

    components = probe_components(module_key, execute_component_probes)
    references = probe_references(root, module_key)
    models = probe_models(root, module_key)
    cohorts = probe_cohorts(root, module_key)
    fixtures = probe_fixtures(root, module_key)
    governance = probe_governance(root, module_key)
    external = probe_external_evidence(root, module_key)
    smoke = smoke_passed(module_key)

    internal_checks = [
        len(profile.workflow) >= 6,
        len(profile.data_gates) >= 6,
        len(profile.model_gates) >= 6,
        len(profile.scientific_gates) >= 7,
        len(profile.acceptance_criteria) >= 6,
        len(profile.required_outputs) >= 6,
        len(profile.risk_controls) >= 6,
        len(profile.monitoring_metrics) >= 5,
        hook,
        not components_plan.empty,
        not references_plan.empty,
        not models_plan.empty,
        not cohorts_plan.empty,
        len(profile.validation_fixtures) >= 5,
        len(profile.governance_assets) >= 3,
        smoke,
    ]
    internal = round(10.0 * sum(internal_checks) / len(internal_checks), 2)
    improvement = round(internal - profile.baseline_rating, 2)
    improvement_percent = round(100.0 * improvement / profile.baseline_rating, 1)

    component_fraction = _fraction(components, "probe_status", "pass" if execute_component_probes else "discovered")
    reference_fraction = _fraction(references, "qualification_status", "qualified")
    model_fraction = _fraction(models, "qualification_status", "qualified")
    cohort_fraction = _fraction(cohorts, "qualification_status", "qualified")
    fixture_fraction = _fraction(fixtures, "qualification_status", "qualified")
    governance_fraction = _fraction(governance, "qualification_status", "qualified")
    external_fraction = sum(external.values()) / len(external)

    eligible = bool(
        internal == 10.0
        and component_fraction == 1.0
        and reference_fraction == 1.0
        and model_fraction == 1.0
        and cohort_fraction == 1.0
        and fixture_fraction == 1.0
        and governance_fraction == 1.0
        and external_fraction == 1.0
    )

    blockers: list[str] = []
    if component_fraction < 1.0:
        blockers.append("specialist engines are not fully discovered and smoke-qualified on the target Windows environment")
    if reference_fraction < 1.0:
        blockers.append("reference assets lack complete release, checksum, licence, schema, provenance or owner approval")
    if model_fraction < 1.0:
        blockers.append("authentic model weights lack complete provider, release, checksum, licence, preprocessing, calibration or model-card qualification")
    if cohort_fraction < 1.0:
        blockers.append("independent cohorts lack complete permissions, identity, subgroup, checksum or leakage-audit qualification")
    if fixture_fraction < 1.0:
        blockers.append("golden, negative, corruption, leakage, sensitivity and reproducibility fixtures are not externally executed and approved")
    if governance_fraction < 1.0:
        blockers.append("risk, biosafety/security, privacy, acceptance, monitoring, rollback or expert governance remains incomplete")
    if external_fraction < 1.0:
        blockers.append("independent-site, prospective/temporal, orthogonal/wet-lab, physical-environment, expert, operating-history or formal-release evidence remains incomplete")

    return ModuleQualification(
        module_key=module_key,
        module_title=profile.title,
        baseline_rating=profile.baseline_rating,
        internal_after_rating=internal,
        rating_improvement=improvement,
        improvement_percent=improvement_percent,
        workflow_contract_complete=internal_checks[0],
        data_contract_complete=internal_checks[1],
        model_contract_complete=internal_checks[2],
        scientific_contract_complete=internal_checks[3],
        acceptance_contract_complete=internal_checks[4],
        output_contract_complete=internal_checks[5],
        risk_contract_complete=internal_checks[6],
        monitoring_contract_complete=internal_checks[7],
        ui_hook_present=internal_checks[8],
        component_plan_complete=internal_checks[9],
        reference_plan_complete=internal_checks[10],
        model_plan_complete=internal_checks[11],
        cohort_plan_complete=internal_checks[12],
        fixture_plan_complete=internal_checks[13],
        governance_plan_complete=internal_checks[14],
        deterministic_scientific_smoke_passed=internal_checks[15],
        component_qualification_fraction=round(component_fraction, 4),
        reference_qualification_fraction=round(reference_fraction, 4),
        model_qualification_fraction=round(model_fraction, 4),
        cohort_qualification_fraction=round(cohort_fraction, 4),
        fixture_qualification_fraction=round(fixture_fraction, 4),
        governance_qualification_fraction=round(governance_fraction, 4),
        external_evidence_fraction=round(external_fraction, 4),
        controlled_release_eligible=eligible,
        decision="controlled-release-qualified" if eligible else "internal-10of10-external-fail-closed",
        remaining_blockers=tuple(blockers),
    )


def qualification_matrix(root: str | Path, execute_component_probes: bool = False) -> pd.DataFrame:
    return pd.DataFrame([asdict(evaluate_module(root, key, execute_component_probes)) for key in TARGET_MODULES])


__all__ = ["ModuleQualification", "evaluate_module", "qualification_matrix"]
