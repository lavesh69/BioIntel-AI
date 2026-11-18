from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from biointel.portfolio_demo_v183.catalog import PROFILES as PORTFOLIO_PROFILES


@dataclass(frozen=True)
class MajorModuleProfile:
    module_key: str
    title: str
    page: str
    source_step: int
    module_class: str
    workflow: tuple[str, ...]
    quality_gates: tuple[str, ...]
    required_outputs: tuple[str, ...]
    boundary: str


STANDARD_TABS: tuple[str, ...] = (
    "Overview",
    "Demo",
    "Inputs",
    "QC",
    "Analysis",
    "Results",
    "Visuals",
    "Validation",
    "Interpretation",
    "Report",
    "History",
    "Qualification",
)

COMPULSORY_DIMENSIONS: tuple[str, ...] = (
    "intended_use_scope_and_limitations",
    "supported_inputs_schema_and_batch_contract",
    "data_quality_sample_level_pass_warn_fail",
    "native_deterministic_analysis_execution",
    "golden_expected_output_and_hash_contract",
    "scientific_visualisation_and_drilldown_contract",
    "interpretation_confidence_and_uncertainty",
    "reproducible_report_and_machine_exports",
    "input_parameter_engine_database_model_provenance",
    "background_progress_cancel_checkpoint_recovery",
    "negative_boundary_corruption_and_security_tests",
    "performance_memory_scale_and_timeout_benchmarks",
    "offline_fallback_and_fail_closed_dependency_handling",
    "privacy_permissions_audit_and_secret_redaction",
    "accessibility_keyboard_labels_and_help_contract",
    "history_rerun_comparison_and_change_tracking",
    "validation_controls_metrics_thresholds_and_subgroups",
    "expert_review_approval_and_release_boundary",
    "cross_module_project_and_workflow_handoff",
    "twelve_tab_ui_and_central_qualification_integration",
)

PROFILES: dict[str, MajorModuleProfile] = {
    key: MajorModuleProfile(
        module_key=key,
        title=str(profile.title),
        page=str(profile.page),
        source_step=int(profile.source_step),
        module_class=str(profile.module_class),
        workflow=tuple(str(x) for x in profile.workflow),
        quality_gates=tuple(str(x) for x in profile.quality_gates),
        required_outputs=tuple(str(x) for x in profile.required_outputs),
        boundary=str(profile.boundary),
    )
    for key, profile in PORTFOLIO_PROFILES.items()
}
TARGET_MODULES: tuple[str, ...] = tuple(PROFILES)
PAGE_TO_MODULES: dict[str, tuple[str, ...]] = {}
for _key, _profile in PROFILES.items():
    PAGE_TO_MODULES.setdefault(Path(_profile.page).name, tuple())
    PAGE_TO_MODULES[Path(_profile.page).name] = PAGE_TO_MODULES[Path(_profile.page).name] + (_key,)

assert len(PROFILES) == 80
assert len(set(profile.page for profile in PROFILES.values())) == 79
assert len(STANDARD_TABS) == 12
assert len(COMPULSORY_DIMENSIONS) == 20

__all__ = [
    "MajorModuleProfile",
    "PROFILES",
    "TARGET_MODULES",
    "PAGE_TO_MODULES",
    "STANDARD_TABS",
    "COMPULSORY_DIMENSIONS",
]
