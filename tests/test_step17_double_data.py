from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.cli import main as cli_main
from biointel.data.data_packs import (
    data_library_summary,
    verify_data_pack_integrity,
)
from biointel.data.dataset_registry import list_datasets
from biointel.dti.predictor import predict_dti_pair
from biointel.training.model_artifact import load_model_artifact
from biointel.training.model_catalog import default_model_path, sync_model_catalog
from biointel.ui.navigation import PAGE_BY_KEY, PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def test_double_ultra_pack_dimensions_and_balance() -> None:
    frame = pd.read_csv(ROOT / "data" / "packs" / "synthetic_double_ultra_dti_v4.csv")
    assert len(frame) == 32000
    assert frame["drug_id"].nunique() == 640
    assert frame["target_id"].nunique() == 50
    assert frame["target_family"].nunique() == 6
    assert 0.49 <= float(frame["label"].mean()) <= 0.51


def test_double_data_inputs_are_ready() -> None:
    batch = pd.read_csv(ROOT / "data" / "packs" / "batch_prediction_sample_2000.csv")
    assert len(batch) == 2000
    for name, target_column in (
        ("double_classification_training_template_250.csv", "label"),
        ("double_regression_training_template_250.csv", "p_activity"),
        ("double_prediction_input_template_250.csv", None),
    ):
        frame = pd.read_csv(ROOT / "data" / "templates" / name)
        assert len(frame) == 250
        assert {"canonical_smiles", "protein_sequence"} <= set(frame.columns)
        if target_column:
            assert target_column in frame.columns


def test_packv4_models_are_trained_on_32000_rows() -> None:
    expected = {
        "packv4_double_classification_extra_trees.joblib",
        "packv4_double_classification_random_forest.joblib",
        "packv4_double_classification_sgd_logistic.joblib",
        "packv4_double_regression_extra_trees.joblib",
        "packv4_double_regression_ridge.joblib",
        "packv4_double_regression_sgd.joblib",
    }
    catalog = sync_model_catalog(ROOT / "models")
    filenames = {item.filename for item in catalog}
    assert expected <= filenames
    for filename in expected:
        artifact = load_model_artifact(
            ROOT / "models" / filename,
            trusted_root=ROOT / "models",
        )
        assert artifact.metadata.dataset_name == ("biointel_synthetic_double_ultra_dti_v4")
        total = (
            artifact.metadata.train_rows
            + artifact.metadata.validation_rows
            + artifact.metadata.test_rows
        )
        assert total == 32000
        cache = artifact.metadata.data_quality_summary["feature_cache"]
        assert cache["unique_drugs"] == 640
        assert cache["unique_targets"] == 50
        assert cache["drug_cache_hits"] == 31360
        assert cache["protein_cache_hits"] == 31950


def test_double_models_predict_both_tasks() -> None:
    row = pd.read_csv(ROOT / "data" / "packs" / "synthetic_double_ultra_dti_v4.csv").iloc[0]
    for filename, task in (
        ("packv4_double_classification_random_forest.joblib", "classification"),
        ("packv4_double_regression_extra_trees.joblib", "regression"),
    ):
        artifact = load_model_artifact(
            ROOT / "models" / filename,
            trusted_root=ROOT / "models",
        )
        result = predict_dti_pair(
            artifact,
            str(row["canonical_smiles"]),
            str(row["protein_sequence"]),
        )
        assert result.task_type == task


def test_double_benchmark_is_honest_and_complete() -> None:
    summary = data_library_summary(ROOT)
    benchmark = summary["benchmark"]
    assert benchmark["data_pack_version"] == "5.0"
    double_rows = [
        item for item in benchmark["ranking"] if item.get("training_pack") == "double_ultra"
    ]
    assert len(double_rows) == 6
    classification = [item for item in double_rows if item["task_type"] == "classification"]
    regression = [item for item in double_rows if item["task_type"] == "regression"]
    assert max(item["test_roc_auc"] for item in classification) > 0.87
    assert min(item["test_rmse"] for item in regression) < 0.45
    assert benchmark["best_models"]["classification"]["filename"] == (
        "packv5_5x_classification_extra_trees.joblib"
    )
    assert default_model_path(ROOT / "models").name == (
        "packv5_5x_classification_extra_trees.joblib"
    )


def test_step17_registry_lineage_and_integrity() -> None:
    integrity = verify_data_pack_integrity(ROOT)
    assert integrity["valid"] is True
    assert integrity["checked_files"] == 31
    assert integrity["total_rows"] == 223930
    records = [
        item
        for item in list_datasets(ROOT / "reports" / "datasets.sqlite3")
        if item.dataset_name.startswith("BioIntel Synthetic")
    ]
    assert len(records) == 10
    double_records = [
        item for item in records if item.dataset_name == "BioIntel Synthetic Double DTI"
    ]
    assert len(double_records) == 2
    assert all(item.parent_sha256 is not None for item in double_records)


def test_step17_navigation_and_module_prefill() -> None:
    assert len(PAGE_CATALOG) >= 71
    assert PAGE_BY_KEY["double_data_ml"].path.endswith("35_Double_Data_ML.py")
    for relative, expected in (
        ("pages/5_Model_Training.py", "Double Ultra pack — 32,000 rows"),
        ("pages/4_DTI_Feature_Builder.py", "Double Ultra pack — 32,000 rows"),
        ("pages/8_Data_Quality_Activity.py", "Double Ultra pack — 32,000 rows"),
        ("pages/6_DTI_Predictor.py", "Bundled 2,000-row sample"),
        ("pages/23_Batch_Prediction_Jobs.py", "Bundled 2,000-row sample"),
    ):
        assert expected in (ROOT / relative).read_text(encoding="utf-8")


def test_step17_api_and_cli(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = TestClient(app)
    response = client.get("/models/double-benchmark")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source_rows"] == 32000
    assert len(payload["ranking"]) == 6

    assert cli_main(["double-ml-status"]) == 0
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["double_ultra_rows"] == 32000
    assert len(cli_payload["double_models"]) == 6


def test_step17_windows_builder_and_reports() -> None:
    builder = (ROOT / "BUILD_DATA_AND_MODELS_WINDOWS.bat").read_text()
    assert "train_step17_double_data_suite.py" in builder
    assert (ROOT / "reports" / "generated" / "step17_double_data_benchmark.json").is_file()
    assert (ROOT / "reports" / "generated" / "step17_double_data_benchmark.csv").is_file()
