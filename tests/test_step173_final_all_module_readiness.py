from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from packaging.version import Version

from biointel.final_v173 import ALL_MODULES, FINAL_PROFILES, Step173Registry, build_step173_assets, profile_matrix
from biointel.scientific_depth.native_workflows import run_native_workflow

ROOT = Path(__file__).resolve().parents[1]


def test_step173_profiles_cover_all_modules_at_internal_10of10() -> None:
    frame = profile_matrix()
    assert len(ALL_MODULES) == len(FINAL_PROFILES) == len(frame) == 80
    assert set(frame["internal_software_rating"]) == {10.0}
    assert set(frame["native_research_depth_rating"]) == {10.0}
    assert set(frame["qualification_framework_rating"]) == {10.0}
    assert frame["internal_10of10_complete"].all()


def test_step173_assets_matrix_and_registry_are_complete_and_honest() -> None:
    assets = build_step173_assets(ROOT)
    registry = Step173Registry(ROOT)
    matrix = registry.latest(refresh=False)
    assert len(assets) >= 401
    assert len(matrix) == 80
    assert matrix["actual_practical_readiness_rating"].between(0, 10).all()
    assert not matrix["controlled_release_eligible"].any()
    assert (matrix.loc[~matrix["controlled_release_eligible"], "actual_practical_readiness_rating"] < 10.0).all()
    assert set(matrix["decision"]) == {"research-only-fail-closed"}
    status = registry.status()
    assert status["database_integrity"] == "ok"
    assert status["foreign_key_violations"] == 0
    assert status["audit_chain_valid"] is True


def test_step173_each_module_has_five_assets() -> None:
    base = ROOT / "data" / "step173" / "module_packages"
    for key in ALL_MODULES:
        folder = base / key
        assert (folder / "final_readiness_contract.json").is_file()
        assert (folder / "qualification_plan.json").is_file()
        assert (folder / "release_acceptance_checklist.json").is_file()
        assert (folder / "rating_breakdown.json").is_file()
        assert (folder / "README.md").is_file()


def test_native_results_include_step173_final_readiness() -> None:
    frame = pd.DataFrame({"sample_id": ["S1", "S2", "S3", "S4"], "value": [1.0, 2.0, 3.0, 4.0]})
    result = run_native_workflow("flow_cytometry", frame, metadata={"project_root": str(ROOT)})
    assert "step173_final_readiness" in result.tables
    gate = result.tables["step173_final_readiness"].iloc[0]
    assert gate["internal_software_rating"] == 10.0
    assert gate["qualification_framework_rating"] == 10.0
    assert not bool(gate["controlled_release_eligible"])


def test_step173_release_metadata_navigation_and_version() -> None:
    release = json.loads((ROOT / "STEP173_RELEASE.json").read_text(encoding="utf-8"))
    assert release["version"] == "14.5.0"
    assert (ROOT / "pages" / "242_Final_All_Module_10of10_Command_Center.py").is_file()
    navigation = (ROOT / "src" / "biointel" / "ui" / "navigation.py").read_text(encoding="utf-8")
    assert "final_all_module_10of10_command_center" in navigation
    assert Version((ROOT / "VERSION").read_text(encoding="utf-8").strip()) >= Version("14.5.0")
