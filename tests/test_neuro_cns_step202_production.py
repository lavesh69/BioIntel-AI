from __future__ import annotations

import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd

from biointel.neuro_cns import PRODUCTION_FEATURES, __version__
from biointel.neuro_cns.catalog import MODULES
from biointel.neuro_cns.demo_showcase import run_complete_demo_showcase
from biointel.neuro_cns.production import (
    authorize_action,
    compute_qualification_profile,
    controlled_release_status,
    crash_diagnostics_bundle,
    create_review_record,
    create_update_snapshot,
    demo_pack_zip,
    official_resource_plan,
    publication_export_pack,
    role_access_matrix,
    specialist_engine_installation_plan,
    validate_benchmark_registry,
    verify_demo_pack,
)
from biointel.neuro_cns.provenance import STEP_VERSION, resource_registry_rows

ROOT = Path(__file__).resolve().parents[1]


def test_step202_registry_and_version() -> None:
    assert __version__ == "208.0"
    assert STEP_VERSION == "202"
    assert len(PRODUCTION_FEATURES) == 10
    assert len({row[2] for row in PRODUCTION_FEATURES}) == 10


def test_demo_pack_is_hash_verified_and_downloadable() -> None:
    status = verify_demo_pack(ROOT)
    assert status["passed"] is True
    assert status["dataset_count"] >= 20
    data = demo_pack_zip(ROOT)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert any(name.endswith("manifest.json") for name in archive.namelist())
        assert any(name.endswith("brain_volume.npy") for name in archive.namelist())


def test_complete_demo_runs_all_catalog_modules() -> None:
    results = run_complete_demo_showcase()
    expected_module_keys = {module.key for module in MODULES}
    assert len(results) == len(expected_module_keys)
    assert set(results) == expected_module_keys


def test_official_resource_plan_covers_every_module() -> None:
    output = official_resource_plan()
    assert output["resource_count"] >= 12
    assert output["all_modules_covered"] is True
    assert output["release_eligible"] is False


def test_specialist_engine_plan_is_fail_closed() -> None:
    output = specialist_engine_installation_plan(run_version_checks=False)
    assert len(output["plan"]) >= 10
    assert output["release_eligible"] is False
    assert set(output["plan"]["next_action"].astype(str))


def test_benchmark_registry_requires_external_evidence() -> None:
    output = validate_benchmark_registry([
        {"module_key": "bbb_permeability", "positive_cases": 20, "negative_cases": 20, "external_sites": 2, "calibration_passed": True, "leakage_audit_passed": True},
        {"module_key": "aggregation_risk", "positive_cases": 3, "negative_cases": 2, "external_sites": 0, "calibration_passed": False, "leakage_audit_passed": True},
    ])
    assert output["qualified_modules"] == 1
    assert output["controlled_release_eligible"] is False
    assert bool(output["benchmarks"].loc[output["benchmarks"]["module_key"] == "aggregation_risk", "qualified"].iloc[0]) is False


def test_role_access_and_review_record() -> None:
    assert authorize_action("researcher", "run_modules")["allowed"] is True
    assert authorize_action("viewer", "approve_release")["allowed"] is False
    matrix = role_access_matrix()
    assert {"viewer", "administrator"} <= set(matrix["role"])
    record = create_review_record(reviewer="Reviewer A", role="reviewer", decision="acknowledge_exploratory", module_keys=["bbb_permeability"], comments="demo", evidence={"x": 1})
    assert len(record["record_fingerprint_sha256"]) == 64


def test_compute_profile_moves_heavy_work_to_background() -> None:
    output = compute_qualification_profile(rows=100_000, columns=100, byte_size=150 * 1024 * 1024, workload="neuroimaging", available_ram_gb=32, cpu_count=8)
    assert output["recommended_mode"] == "background"
    assert output["streaming_recommended"] is True
    assert output["recommended_worker_limit"] <= 4


def test_snapshot_and_diagnostics_are_valid_zip_files() -> None:
    snapshot = create_update_snapshot(ROOT, include_paths=["src/biointel/neuro_cns/production.py", "data/neuro_cns/step202_production_feature_registry.json"])
    with zipfile.ZipFile(io.BytesIO(snapshot)) as archive:
        assert "SNAPSHOT_MANIFEST.json" in archive.namelist()
    diagnostics = crash_diagnostics_bundle(ROOT, error_message="demo failure")
    with zipfile.ZipFile(io.BytesIO(diagnostics)) as archive:
        payload = json.loads(archive.read("diagnostics.json"))
        assert payload["error_message"] == "demo failure"


def test_release_status_remains_fail_closed_without_real_gates() -> None:
    results = {"bbb_permeability": {"classification": "likely_permeable"}}
    status = controlled_release_status(results=results, test_failures=0, native_windows_qualified=False)
    assert status["controlled_release_eligible"] is False
    assert status["release_tier"] in {"Exploratory Research", "Research Qualified"}


def test_publication_pack_contains_report_and_release_status() -> None:
    results = {"bbb_permeability": {"classification": "likely_permeable"}}
    data = publication_export_pack(results, project_name="Unit test", methods="Methods", limitations="Limitations")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        assert {"report/results.json", "report/results.pdf", "publication/RELEASE_STATUS.json", "publication/METHODS.md"} <= names


def test_step202_resources_are_registered() -> None:
    resource_ids = {row["resource_id"] for row in resource_registry_rows()}
    assert {"step202_feature_registry", "step202_demo_pack"} <= resource_ids


def test_step202_source_preflight_passes_builder_mode(tmp_path: Path) -> None:
    output = tmp_path / "preflight.json"
    completed = subprocess.run([sys.executable, "scripts/step202_preflight.py", "--root", ".", "--allow-non-cp311", "--output", str(output)], cwd=ROOT, check=False)
    assert completed.returncode == 0
    assert json.loads(output.read_text())["passed"] is True
