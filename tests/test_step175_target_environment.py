from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from biointel.environment_v175 import (
    Step175Registry,
    build_step175_assets,
    engine_execution_catalog,
    environment_groups,
    environment_summary,
    execution_matrix,
    reference_execution_catalog,
    target_profiles,
)
from biointel.scientific_depth.native_workflows import run_native_workflow

ROOT = Path(__file__).resolve().parents[1]


def test_step175_catalogs_cover_exact_scope() -> None:
    engines = engine_execution_catalog()
    refs = reference_execution_catalog()
    assert len(engines) == engines["engine"].nunique() == 53
    assert len(refs) == refs["reference_id"].nunique() == 26
    assert len(environment_groups()) == 12
    assert len(target_profiles()) == 3
    assert engines["environment_group"].notna().all()
    assert (engines["step175_framework_score"] == 10.0).all()
    assert (refs["step175_framework_score"] == 10.0).all()


def test_step175_assets_include_all_engines_references_and_environments() -> None:
    assets = build_step175_assets(ROOT)
    assert len(assets) >= 180
    base = ROOT / "data" / "step175"
    assert len(list((base / "engine_fixtures").glob("*/fixture_spec.json"))) == 53
    assert len(list((base / "reference_kits").glob("*/intake.json"))) == 26
    assert len(list((base / "environments").glob("*.yml"))) == 12
    assert len(list((base / "manual_provider_kits").glob("*/intake.json"))) == 5


def test_step175_matrix_is_fail_closed() -> None:
    matrix = execution_matrix(ROOT)
    assert len(matrix) == 79
    assert (matrix["step175_framework_score"] == 10.0).all()
    assert (
        ~matrix["final_target_qualification_complete"]
        | (matrix["artifact_qualified"] & matrix["target_host_qualified"])
    ).all()
    summary = environment_summary(ROOT)
    assert summary["software_framework_score"] == 10.0
    assert summary["engines_total"] == 53
    assert summary["references_total"] == 26
    assert summary["external_installation_fabricated"] is False


def test_step175_registry_integrity() -> None:
    status = Step175Registry(ROOT).status()
    assert status["database_integrity"] == "ok"
    assert status["foreign_key_violations"] == 0
    assert status["audit_chain_valid"] is True


def test_native_results_include_step175_environment_assurance() -> None:
    frame = pd.DataFrame({"sample_id": ["S1", "S2", "S3", "S4"], "value": [1.0, 2.0, 3.0, 4.0]})
    result = run_native_workflow("flow_cytometry", frame, metadata={"project_root": str(ROOT)})
    assert "step175_target_environment_summary" in result.tables
    row = result.tables["step175_target_environment_summary"].iloc[0]
    assert row["software_framework_score"] == 10.0
    assert not bool(row["external_installation_fabricated"])


def test_step175_release_navigation_version_and_scripts() -> None:
    release = json.loads((ROOT / "STEP175_RELEASE.json").read_text(encoding="utf-8"))
    assert release["version"] == "14.7.0"
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "14.7.0"
    assert (ROOT / "pages" / "244_Target_Environment_Engine_Reference_Qualification.py").is_file()
    navigation = (ROOT / "src" / "biointel" / "ui" / "navigation.py").read_text(encoding="utf-8")
    assert "target_environment_engine_reference_qualification" in navigation
    for name in (
        "RUN_STEP175_TARGET_ENVIRONMENT_WINDOWS.bat",
        "VERIFY_STEP175_WINDOWS.bat",
        "RUN_STEP175_RELEASE_DOCTOR_WINDOWS.bat",
        "BUILD_STEP175_ENVIRONMENT_ASSETS_WINDOWS.bat",
    ):
        assert (ROOT / name).is_file()
