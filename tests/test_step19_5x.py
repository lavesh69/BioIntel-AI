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
from biointel.dti.dataset_validation import (
    validate_dti_dataset,
)
from biointel.dti.predictor import predict_dti_pair
from biointel.training.feature_matrix import (
    build_feature_matrix,
)
from biointel.training.model_artifact import (
    load_model_artifact,
)
from biointel.training.model_catalog import (
    default_model_path,
    sync_model_catalog,
)
from biointel.ui.navigation import PAGE_BY_KEY, PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def test_five_x_pack_dimensions_balance_and_inputs() -> None:
    data = pd.read_csv(ROOT / "data" / "packs" / "synthetic_5x_ultra_dti_v5.csv")
    assert len(data) == 160000
    assert data["drug_id"].nunique() == 1000
    assert data["target_id"].nunique() == 160
    assert data["target_family"].nunique() == 6
    assert 0.49 <= float(data["label"].mean()) <= 0.51

    batch = pd.read_csv(ROOT / "data" / "packs" / "batch_prediction_sample_5000.csv")
    assert len(batch) == 5000

    for name, target in (
        (
            "five_x_classification_training_template_500.csv",
            "label",
        ),
        (
            "five_x_regression_training_template_500.csv",
            "p_activity",
        ),
        (
            "five_x_prediction_input_template_500.csv",
            None,
        ),
    ):
        frame = pd.read_csv(ROOT / "data" / "templates" / name)
        assert len(frame) == 500
        assert {
            "canonical_smiles",
            "protein_sequence",
        } <= set(frame.columns)
        if target:
            assert target in frame.columns


def test_five_x_validation_and_feature_pipeline() -> None:
    data = pd.read_csv(ROOT / "data" / "packs" / "synthetic_5x_ultra_dti_v5.csv")
    report = validate_dti_dataset(
        data,
        "classification",
    )
    assert report.valid_rows == 160000
    assert report.invalid_rows == 0
    assert report.summary["unique_smiles_validated"] == 1000
    assert report.summary["unique_proteins_validated"] == 160

    features = build_feature_matrix(
        report.cleaned,
        target_column="label",
        n_bits=64,
    )
    assert features.matrix.shape == (160000, 103)
    assert str(features.matrix.dtype) == "float32"
    assert features.cache_summary["drug_cache_hits"] == 159000
    assert features.cache_summary["protein_cache_hits"] == 159840
    assert features.cache_summary["matrix_bytes"] == 65920000


def test_packv5_models_are_complete_overlap_free() -> None:
    expected = {
        "packv5_5x_classification_extra_trees.joblib",
        "packv5_5x_classification_random_forest.joblib",
        "packv5_5x_classification_sgd_logistic.joblib",
        "packv5_5x_regression_extra_trees.joblib",
        "packv5_5x_regression_ridge.joblib",
        "packv5_5x_regression_sgd.joblib",
    }
    catalog = sync_model_catalog(ROOT / "models")
    assert expected <= {entry.filename for entry in catalog}
    for filename in expected:
        artifact = load_model_artifact(
            ROOT / "models" / filename,
            trusted_root=ROOT / "models",
        )
        total = (
            artifact.metadata.train_rows
            + artifact.metadata.validation_rows
            + artifact.metadata.test_rows
        )
        assert total == 160000
        assert artifact.metadata.dataset_name == ("biointel_synthetic_5x_ultra_dti_v5")
        split = artifact.metadata.data_quality_summary["split_summary"]
        assert split["group_overlap"] is False
        cache = artifact.metadata.data_quality_summary["feature_cache"]
        assert cache["unique_drugs"] == 1000
        assert cache["unique_targets"] == 160
        assert cache["matrix_dtype"] == "float32"


def test_five_x_benchmark_and_default_are_honest() -> None:
    summary = data_library_summary(ROOT)
    benchmark = summary["benchmark"]
    assert benchmark["data_pack_version"] == "5.0"
    rows = [row for row in benchmark["ranking"] if row.get("training_pack") == "five_x_ultra"]
    assert len(rows) == 6
    classification = [row for row in rows if row["task_type"] == "classification"]
    regression = [row for row in rows if row["task_type"] == "regression"]
    assert max(row["test_roc_auc"] for row in classification) > 0.90
    assert min(row["test_rmse"] for row in regression) < 0.32
    assert benchmark["best_models"]["classification"]["filename"] == (
        "packv5_5x_classification_extra_trees.joblib"
    )
    assert default_model_path(ROOT / "models").name == (
        "packv5_5x_classification_extra_trees.joblib"
    )


def test_five_x_models_predict_both_tasks() -> None:
    row = pd.read_csv(
        ROOT / "data" / "packs" / "synthetic_5x_ultra_dti_v5.csv",
        nrows=1,
    ).iloc[0]
    for filename, task in (
        (
            "packv5_5x_classification_extra_trees.joblib",
            "classification",
        ),
        (
            "packv5_5x_regression_extra_trees.joblib",
            "regression",
        ),
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


def test_five_x_registry_integrity_navigation() -> None:
    integrity = verify_data_pack_integrity(ROOT)
    assert integrity["valid"] is True
    assert integrity["checked_files"] == 31
    assert integrity["total_rows"] == 223930

    records = [
        item
        for item in list_datasets(
            ROOT / "reports" / "datasets.sqlite3",
            limit=5000,
        )
        if item.dataset_name.startswith("BioIntel Synthetic")
    ]
    assert len(records) == 10
    five_x_records = [item for item in records if item.dataset_name == "BioIntel Synthetic 5X DTI"]
    assert len(five_x_records) == 2
    assert all(item.parent_sha256 is None for item in five_x_records)

    assert len(PAGE_CATALOG) >= 71
    assert PAGE_BY_KEY["five_x_data_ml"].path.endswith("37_5X_Data_ML.py")


def test_five_x_module_prefill_api_and_cli(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for relative, expected in (
        (
            "pages/5_Model_Training.py",
            "5X Ultra pack — 160,000 rows",
        ),
        (
            "pages/4_DTI_Feature_Builder.py",
            "5X Ultra pack — 160,000 rows",
        ),
        (
            "pages/8_Data_Quality_Activity.py",
            "5X Ultra pack — 160,000 rows",
        ),
        (
            "pages/6_DTI_Predictor.py",
            "Bundled 5,000-row sample",
        ),
        (
            "pages/23_Batch_Prediction_Jobs.py",
            "Bundled 5,000-row sample",
        ),
    ):
        assert expected in (ROOT / relative).read_text(encoding="utf-8")

    client = TestClient(app)
    response = client.get("/models/5x-benchmark")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source_rows"] == 160000
    assert payload["unique_compounds"] == 1000
    assert payload["unique_targets"] == 160
    assert len(payload["ranking"]) == 6

    assert cli_main(["five-x-ml-status"]) == 0
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["five_x_rows"] == 160000
    assert len(cli_payload["five_x_models"]) == 6


def test_step19_windows_builder_and_reports() -> None:
    builder = (ROOT / "BUILD_DATA_AND_MODELS_WINDOWS.bat").read_text(encoding="utf-8")
    assert "train_step19_5x_suite.py" in builder
    assert (ROOT / "reports" / "generated" / "step19_5x_ml_benchmark.json").is_file()
    assert (ROOT / "reports" / "generated" / "step19_5x_ml_benchmark.csv").is_file()
