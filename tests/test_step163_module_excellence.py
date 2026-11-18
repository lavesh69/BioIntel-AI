from __future__ import annotations

from pathlib import Path

from biointel.excellence_v163 import (
    ensure_step163_assets,
    module_excellence_matrix,
    module_excellence_summary,
)
from biointel.scientific_depth import MODULE_PROFILES, native_input_template, run_native_workflow

ROOT = Path(__file__).resolve().parents[1]


def test_step163_assets_and_matrix_cover_every_module() -> None:
    ensure_step163_assets(ROOT)
    matrix = module_excellence_matrix(ROOT)
    summary = module_excellence_summary(matrix)
    assert len(matrix) == len(MODULE_PROFILES) == 80
    assert summary["software_owned_10of10"] == 80
    assert summary["runtime_paths_10of10"] == 80
    assert summary["benchmark_specs_10of10"] == 80
    assert summary["model_guards_10of10"] == 80
    assert summary["reference_lifecycle_10of10"] == 80
    assert summary["real_world_release_eligible"] == 0


def test_step163_native_result_contains_excellence_tables() -> None:
    for module_key in ["amr_surveillance", "docking_dynamics", "clinical_trial_biomarker", "background_job_engine"]:
        result = run_native_workflow(
            module_key,
            native_input_template(module_key, demonstration=True),
            metadata={"analysis_mode": "interactive", "project_root": str(ROOT)},
        )
        assert result.status in {"pass", "review"}
        assert result.summary["step163_software_owned_module_score"] == 10.0
        assert "step163_module_excellence_contract" in result.tables
        assert "step163_task_specific_benchmark_specification" in result.tables
        assert "step163_reference_acquisition_manifest" in result.tables
        assert "step163_model_eligibility_policy" in result.tables
        assert "step163_claim_and_uncertainty_policy" in result.tables
