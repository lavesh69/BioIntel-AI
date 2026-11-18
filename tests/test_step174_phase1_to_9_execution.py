from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from biointel.final_v173 import ALL_MODULES
from biointel.realworld_v174 import (
    PHASES,
    Step174ExecutionRegistry,
    build_phase_execution_matrix,
    build_step174_assets,
    phase_catalog,
)
from biointel.scientific_depth.native_workflows import run_native_workflow

ROOT = Path(__file__).resolve().parents[1]


def test_step174_has_exactly_nine_ordered_phases() -> None:
    frame = phase_catalog()
    assert len(PHASES) == len(frame) == 9
    assert frame["phase_number"].tolist() == list(range(1, 10))
    assert frame["external_evidence_required"].map(len).min() > 0


def test_step174_matrix_covers_all_modules_without_fake_completion() -> None:
    matrix = build_phase_execution_matrix(ROOT)
    assert len(matrix) == len(ALL_MODULES) == 80
    assert (matrix["software_phase_automation_rating"] == 10.0).all()
    assert matrix["all_phase_software_automation_available"].all()
    assert (matrix["external_evidence_fabricated"] == False).all()
    assert (matrix["completed_phases"] <= matrix["required_phases"]).all()
    assert (matrix.loc[~matrix["controlled_release_eligible"], "decision"] == "research-only-fail-closed").all()


def test_step174_assets_cover_every_module_and_phase() -> None:
    assets = build_step174_assets(ROOT)
    assert len(assets) >= 960
    base = ROOT / "data" / "step174" / "module_execution_packages"
    for key in ALL_MODULES:
        folder = base / key
        assert (folder / "execution_manifest.json").is_file()
        assert (folder / "evidence_inventory.csv").is_file()
        assert (folder / "README.md").is_file()
        assert len(list(folder.glob("phase_*.json"))) == 9


def test_step174_registry_integrity_and_audit_chain() -> None:
    registry = Step174ExecutionRegistry(ROOT)
    matrix = registry.latest(refresh=True)
    assert len(matrix) == 80
    status = registry.status()
    assert status["database_integrity"] == "ok"
    assert status["foreign_key_violations"] == 0
    assert status["audit_chain_valid"] is True


def test_native_results_include_step174_phase_execution() -> None:
    frame = pd.DataFrame({"sample_id": ["S1", "S2", "S3", "S4"], "value": [1.0, 2.0, 3.0, 4.0]})
    result = run_native_workflow("flow_cytometry", frame, metadata={"project_root": str(ROOT)})
    assert "step174_phase1_to_9_execution" in result.tables
    gate = result.tables["step174_phase1_to_9_execution"].iloc[0]
    assert gate["software_phase_automation_rating"] == 10.0
    assert not bool(gate["external_evidence_fabricated"])


def test_step174_release_navigation_version_and_windows_scripts() -> None:
    release = json.loads((ROOT / "STEP174_RELEASE.json").read_text(encoding="utf-8"))
    assert release["version"] == "14.6.0"
    from packaging.version import Version
    assert Version((ROOT / "VERSION").read_text(encoding="utf-8").strip()) >= Version("14.6.0")
    assert (ROOT / "pages" / "243_Phase_1_to_9_Real_World_Qualification_Execution.py").is_file()
    navigation = (ROOT / "src" / "biointel" / "ui" / "navigation.py").read_text(encoding="utf-8")
    assert "phase1_to_9_real_world_qualification_execution" in navigation
    for name in (
        "RUN_STEP174_PHASE1_TO_9_WINDOWS.bat",
        "VERIFY_STEP174_WINDOWS.bat",
        "RUN_STEP174_RELEASE_DOCTOR_WINDOWS.bat",
        "PREPARE_STEP174_ALL_WORKSPACES_WINDOWS.bat",
    ):
        assert (ROOT / name).is_file()
