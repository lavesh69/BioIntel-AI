from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from biointel.authenticity_v162 import (
    legacy_model_authenticity,
    portfolio_authenticity_matrix,
    portfolio_authenticity_summary,
    provider_contract_matrix,
    verify_public_benchmark_suite,
)
from biointel.scientific_depth import native_input_template, run_native_workflow

ROOT = Path(__file__).resolve().parents[1]


def test_public_benchmark_models_are_checksum_and_inference_verified() -> None:
    frame = verify_public_benchmark_suite(ROOT)
    assert len(frame) == 5
    assert frame["passed"].astype(bool).all(), frame.to_dict(orient="records")
    assert int(frame["files_verified"].min()) >= 9


def test_legacy_synthetic_models_are_quarantined_and_not_defaults() -> None:
    frame = legacy_model_authenticity(ROOT)
    assert len(frame) >= 25
    synthetic = frame.loc[frame["synthetic_demo"].astype(bool)]
    assert len(synthetic) >= 23
    assert not synthetic["default_scientific_inference_allowed"].astype(bool).any()
    catalog = json.loads((ROOT / "models" / "catalog.json").read_text(encoding="utf-8"))
    operational_default = [name for name, item in catalog.items() if bool(item.get("is_default"))]
    assert operational_default == ["packv5_5x_classification_extra_trees.joblib"]
    assert all(
        str(catalog[name]["notes"]).startswith("[DEMO-ONLY QUARANTINED]")
        for name in synthetic["artifact"].tolist()
    )


def test_provider_contracts_are_honest_and_checksum_protected() -> None:
    frame = provider_contract_matrix(ROOT)
    assert len(frame) == 14
    assert frame["source_descriptor_verified"].astype(bool).all()
    assert int(frame["local_snapshot_checksum_verified"].astype(bool).sum()) >= 7
    assert not frame["production_reference_qualified"].astype(bool).any()


def test_all_module_authenticity_contracts_are_present() -> None:
    frame = portfolio_authenticity_matrix(ROOT)
    summary = portfolio_authenticity_summary(frame)
    assert len(frame) == 80
    assert summary["software_authenticity_10_of_10"] == 80
    assert summary["public_benchmark_models_verified"] == 5
    assert summary["legacy_synthetic_models_quarantined"] >= 23
    assert summary["domain_model_release_eligible"] == 0


def test_native_result_includes_step162_tables_and_boundaries() -> None:
    result = run_native_workflow(
        "docking_dynamics",
        native_input_template("docking_dynamics", demonstration=True),
        metadata={"analysis_mode": "interactive", "project_root": str(ROOT)},
    )
    assert result.status in {"pass", "review"}
    assert "step162_model_authenticity_contract" in result.tables
    assert "step162_production_reference_requirements" in result.tables
    assert result.summary["step162_software_authenticity_score"] == 10.0
    assert result.summary["step162_domain_model_release_eligible"] is False


def test_release_metadata_and_page_exist() -> None:
    release = json.loads((ROOT / "STEP162_RELEASE.json").read_text(encoding="utf-8"))
    assert release["product_version"] == "13.4.0"
    assert release["public_data_benchmark_models_verified"] == 5
    assert release["synthetic_demo_models_quarantined"] == 23
    assert (ROOT / "pages" / "231_Model_Authenticity_10of10_Center.py").is_file()
    matrix = pd.read_csv(ROOT / "reports" / "step162_module_authenticity_matrix.csv")
    assert len(matrix) == 80
