from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import pandas as pd

@dataclass(frozen=True)
class PageProfile:
    page_number: int
    page_title: str
    file_name: str
    category: str
    before_rating: float

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "STEP187_TARGET_PAGE_CATALOG.csv"
_frame = pd.read_csv(CATALOG_PATH)
TARGET_PROFILES = {
    str(row.file_name): PageProfile(
        page_number=int(row.page_number),
        page_title=str(row.page_title),
        file_name=str(row.file_name),
        category=str(row.category),
        before_rating=float(row.internal_demo_operational_rating),
    )
    for row in _frame.itertuples(index=False)
}
TARGET_PAGES = tuple(TARGET_PROFILES)
DEEP_TARGETS = {
    "234_Priority_Three_Module_Excellence_Center.py",
    "235_Six_Module_Scientific_Excellence_Center.py",
    "236_Priority_Module_Scientific_Excellence_Center.py",
    "67_Bioinformatics_Capability_Center.py",
    "193_Visual_Review_Approval_Center.py",
    "237_Remaining_Modules_and_External_Evidence_10of10_Center.py",
    "255_Step185_19_Module_Operational_Assurance_Center.py",
    "256_Step186_18_Module_Platform_Completion_Center.py",
    "108_BioIntel_Model_Qualification.py",
    "192_Validation_Cohort_Manager.py",
}
ASSURANCE_DIMENSIONS = (
    "source_compilation_and_ast_integrity",
    "page_identity_and_configuration_contract",
    "deterministic_page_specific_demo_fixture",
    "native_demo_analysis_and_golden_output",
    "input_schema_and_boundary_validation",
    "negative_corruption_and_security_cases",
    "export_report_and_download_contract",
    "performance_scale_latency_and_memory",
    "three_run_repeatability_hashes",
    "state_recovery_and_safe_failure_contract",
    "accessibility_keyboard_and_label_contract",
    "provenance_version_and_source_hashes",
    "privacy_secret_and_formula_injection_redaction",
    "direct_parameterised_test_coverage",
    "page_hook_and_central_dashboard_integration",
    "category_specific_operational_assurance",
)
assert len(TARGET_PAGES) == 177
__all__ = ["PageProfile", "TARGET_PROFILES", "TARGET_PAGES", "DEEP_TARGETS", "ASSURANCE_DIMENSIONS"]
