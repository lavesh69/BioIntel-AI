from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from biointel.readiness_v161 import (
    development_reference_readiness,
    portfolio_upgrade_matrix,
    portfolio_upgrade_summary,
    runtime_recipe_catalog,
    validation_protocol_readiness,
)
from biointel.scientific_depth import MODULE_PROFILES, native_input_template, run_native_workflow
from biointel.stability_v159.module_health import page_source_health
from biointel.ui.navigation import PAGE_BY_KEY


def test_all_external_engines_have_complete_managed_runtime_recipes() -> None:
    recipes = runtime_recipe_catalog()
    assert len(recipes) == 53
    assert recipes["recipe_complete"].all()
    assert recipes["protected_plan_available"].all()
    assert recipes["checksum_required"].all()
    assert recipes["version_probe_required"].all()


def test_all_required_references_have_checksum_verified_development_kits() -> None:
    matrix = development_reference_readiness(ROOT)
    assert len(matrix) == sum(len(profile.references) for profile in MODULE_PROFILES.values())
    assert matrix["development_qualified"].all()
    assert matrix["checksum_verified"].all()
    assert (~matrix["production_use_allowed"]).all()
    assert matrix["replacement_required_for_confirmatory_use"].all()


def test_every_module_has_a_versioned_external_validation_protocol() -> None:
    matrix = validation_protocol_readiness(ROOT)
    assert len(matrix) == 80
    assert matrix["protocol_ready"].all()
    assert matrix["protocol_version"].eq("1.0.0").all()
    assert (~matrix["external_evidence_attached"]).all()
    assert (~matrix["release_eligible"]).all()


def test_all_modules_reach_step161_software_upgrade_10of10() -> None:
    matrix = portfolio_upgrade_matrix(ROOT, detect_runtime=False)
    summary = portfolio_upgrade_summary(matrix)
    assert len(matrix) == 80
    assert summary["step161_10_of_10"] == 80
    assert matrix["step161_upgrade_score"].eq(10.0).all()
    assert matrix["execution_path_score"].eq(10.0).all()
    assert matrix["development_reference_score"].eq(10.0).all()
    assert matrix["validation_protocol_score"].eq(10.0).all()
    assert not matrix["real_world_release_eligible"].any()


def test_native_results_include_step161_operational_tables() -> None:
    for module_key in (
        "docking_dynamics",
        "immunoinformatics_vaccine",
        "single_cell_trajectory",
        "amr_surveillance",
    ):
        result = run_native_workflow(
            module_key,
            native_input_template(module_key, demonstration=True),
            metadata={"analysis_mode": "interactive", "project_root": str(ROOT)},
        )
        assert result.status in {"pass", "review"}
        assert result.summary["step161_software_upgrade_score"] == 10.0
        assert result.summary["specialist_runtime_installed_inferred"] is False
        assert result.summary["production_reference_qualification_inferred"] is False
        assert {
            "step161_execution_paths",
            "step161_development_reference_kits",
            "step161_external_validation_protocol",
        }.issubset(result.tables)


def test_step161_command_center_is_registered_and_all_pages_compile() -> None:
    page = PAGE_BY_KEY["all_module_10of10_upgrade_center"]
    assert page.path == "pages/230_All_Module_10of10_Upgrade_Center.py"
    pages = page_source_health(ROOT)
    assert len(pages) >= 232
    assert pages["exists"].all()
    assert pages["syntax_ok"].all()


def test_step161_release_manifest_preserves_external_boundary() -> None:
    payload = json.loads((ROOT / "STEP161_RELEASE.json").read_text(encoding="utf-8"))
    assert payload["step"] == 161
    assert payload["software_upgrade_10of10_modules"] == 80
    assert payload["managed_runtime_recipes"] == 53
    assert payload["development_reference_assets"] == 257
    assert payload["validation_protocols"] == 80
    assert payload["external_release_eligible_modules"] == 0
    assert payload["external_claims_not_inferred"] is True
