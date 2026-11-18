from __future__ import annotations

from dataclasses import dataclass
from biointel.scientific_execution_v190.catalog import PROFILES as STEP190_PROFILES

RELEASE_STEP = 193
RELEASE_VERSION = "15.1.0"

MANDATORY_DIMENSIONS: tuple[str, ...] = (
    "intended_use_and_safety_boundary",
    "input_schema_and_identifier_contract",
    "data_classification_and_sensitive_data_handling",
    "consent_permission_and_licence_gate",
    "retention_deletion_and_archive_policy",
    "sample_identity_and_cross_module_consistency",
    "autosave_snapshot_and_state_recovery",
    "session_isolation_and_concurrency_guard",
    "resource_budget_and_large_input_guard",
    "dependency_engine_and_reference_health",
    "confidence_uncertainty_and_limitations",
    "abstention_and_fail_closed_release",
    "signed_export_and_result_integrity",
    "tamper_evident_provenance_chain",
    "review_approval_and_change_control",
    "feature_flags_deprecation_and_compatibility",
    "schema_migration_and_upgrade_readiness",
    "backup_restore_and_disaster_recovery",
    "accessibility_keyboard_and_localisation",
    "security_redaction_and_injection_protection",
    "audit_log_and_support_diagnostics",
    "monitoring_slo_and_alert_ownership",
    "module_specific_mandatory_capabilities",
    "page_hook_regression_and_install_validation",
)

CATEGORY_MANDATORY: dict[str, tuple[str, ...]] = {
    "genomics": ("reference-build lock", "variant/sample identity", "truth-set metric", "genome evidence export"),
    "single_cell_multiomics": ("patient/sample split", "batch/QC contract", "annotation confidence", "processed object export"),
    "microbiome": ("negative controls", "contamination gate", "database version lock", "ambiguous-call abstention"),
    "protein_molecular": ("sequence/structure sanity", "model/engine provenance", "design confidence", "experimental-evidence boundary"),
    "imaging_spatial": ("pixel/magnification metadata", "tiled memory guard", "scanner/site drift", "annotation provenance"),
    "ai_ml": ("model card", "leakage/OOD controls", "calibration/abstention", "rollback/retirement"),
    "clinical_pharma": ("intended-use lock", "patient-level split", "subgroup safety", "controlled-release gate"),
    "lab_bioprocess": ("instrument identity", "calibration/lot traceability", "process drift", "execution state machine"),
    "knowledge_documents": ("source localisation", "claim-source link", "retraction/conflict gate", "citation snapshot"),
    "platform_workflow": ("typed interfaces", "isolation/permissions", "checkpoint/rollback", "portable manifest"),
    "general_scientific": ("domain input contract", "QC threshold", "confidence/limitations", "independent-evidence gate"),
}

@dataclass(frozen=True)
class MandatoryProfile:
    module_key: str
    title: str
    page: str
    category: str
    mandatory_capabilities: tuple[str, ...]

PROFILES: dict[str, MandatoryProfile] = {
    key: MandatoryProfile(
        module_key=key,
        title=p.title,
        page=p.page,
        category=p.category,
        mandatory_capabilities=CATEGORY_MANDATORY[p.category],
    )
    for key, p in STEP190_PROFILES.items()
}
TARGET_MODULES: tuple[str, ...] = tuple(PROFILES)
PAGE_TO_MODULES: dict[str, tuple[str, ...]] = {}
for key, profile in PROFILES.items():
    name = profile.page.split("/")[-1]
    PAGE_TO_MODULES[name] = (*PAGE_TO_MODULES.get(name, ()), key)

__all__ = [
    "RELEASE_STEP", "RELEASE_VERSION", "MANDATORY_DIMENSIONS", "CATEGORY_MANDATORY",
    "MandatoryProfile", "PROFILES", "TARGET_MODULES", "PAGE_TO_MODULES",
]
