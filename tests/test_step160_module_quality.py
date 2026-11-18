from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
from io import BytesIO

ROOT = Path(__file__).resolve().parents[1]

from biointel.quality_v160 import (
    QUALITY_DIMENSIONS,
    assess_module_quality,
    portfolio_quality_matrix,
    portfolio_quality_summary,
    quality_contract_manifest,
)
from biointel.scientific_depth import MODULE_PROFILES, native_input_template, native_portfolio_manifest, run_native_workflow
from biointel.stability_v159.module_health import page_source_health
from biointel.ui.navigation import PAGE_BY_KEY


def test_all_modules_have_ten_point_internal_quality_contract() -> None:
    assert len(MODULE_PROFILES) == 80
    assert len(QUALITY_DIMENSIONS) == 10
    matrix = portfolio_quality_matrix(ROOT, detect_runtime=False)
    summary = portfolio_quality_summary(matrix)
    assert len(matrix) == 80
    assert summary["internal_10_of_10"] == 80
    assert matrix["internal_quality_score"].eq(10.0).all()
    assert matrix["dimensions_passed"].eq(10).all()
    assert matrix["dimensions_total"].eq(10).all()
    assert matrix["external_release_eligible"].eq(False).all()


def test_every_module_has_a_static_quality_contract_manifest() -> None:
    folder = ROOT / "data" / "module_quality_contracts" / "step160"
    files = sorted(folder.glob("*.json"))
    assert len(files) == 80
    for module_key in MODULE_PROFILES:
        path = folder / f"{module_key}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["module_key"] == module_key
        assert payload["release_step"] == 160
        assert len(payload["dimensions"]) == 10
        assert payload["external_claims_not_inferred"] is True


def test_native_runs_include_step160_integrity_and_reproducibility_outputs() -> None:
    for module_key in ("population_gwas", "docking_dynamics", "single_cell_trajectory", "flow_cytometry"):
        result = run_native_workflow(
            module_key,
            native_input_template(module_key, demonstration=True),
            metadata={"analysis_mode": "interactive", "project_root": str(ROOT)},
        )
        assert result.status in {"pass", "review"}
        assert result.summary["step160_internal_quality_score"] == 10.0
        assert result.summary["external_validation_inferred"] is False
        assert result.provenance["release_step"] == 160
        assert result.provenance["step160_quality_assurance_available"] is True
        assert {
            "step160_input_integrity_audit",
            "step160_output_integrity_audit",
            "step160_reproducibility_manifest",
        }.issubset(result.tables)
        with zipfile.ZipFile(BytesIO(result.complete_bundle), "r") as archive:
            names = set(archive.namelist())
            assert "manifest.json" in names
            assert "tables/step160_input_integrity_audit.csv" in names
            assert "tables/step160_output_integrity_audit.csv" in names
            assert "tables/step160_reproducibility_manifest.csv" in names


def test_quality_assessment_keeps_external_readiness_separate() -> None:
    module_key = "immunoinformatics_vaccine"
    assessment = assess_module_quality(ROOT, module_key, toolchains=None)
    assert assessment.internal_quality_score == 10.0
    assert assessment.external_evidence_score == 0.0
    assert assessment.external_release_eligible is False
    assert any("External evidence pending" in blocker for blocker in assessment.blockers)
    manifest = quality_contract_manifest(module_key)
    assert manifest["score_scope"].startswith("Software-owned")


def test_step160_command_center_and_page_catalog_are_clean() -> None:
    assert PAGE_BY_KEY["module_quality_10of10_command_center"].path == "pages/229_Module_Quality_10of10_Command_Center.py"
    pages = page_source_health(ROOT)
    assert len(pages) >= 231
    assert pages["exists"].all()
    assert pages["syntax_ok"].all()


def test_native_portfolio_declares_step160_controls() -> None:
    manifest = native_portfolio_manifest()
    assert manifest["current_schema"] == "biointel.step160.native-portfolio.v6"
    assert manifest["step160_internal_quality_contracts"] is True
    assert manifest["step160_full_input_integrity_audit"] is True
    assert manifest["step160_output_table_integrity_audit"] is True
    assert manifest["step160_reproducibility_signature"] is True


def test_step160_quick_validator() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "step160_validate_installation.py"), "--root", str(ROOT), "--quick"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT / "src")},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
