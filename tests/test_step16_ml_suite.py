from __future__ import annotations

from pathlib import Path

import pandas as pd

from biointel.data.data_packs import (
    data_library_summary,
    verify_data_pack_integrity,
)
from biointel.dti.predictor import _predict_estimator, predict_dti_pair
from biointel.training.model_artifact import load_model_artifact
from biointel.training.model_catalog import default_model_path
from biointel.ui.navigation import PAGE_BY_KEY, PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def test_estimator_prediction_uses_one_worker_and_restores_configuration() -> None:
    class Estimator:
        n_jobs = -1

        def predict(self, values):
            assert self.n_jobs == 1
            return values

    estimator = Estimator()
    values = [[1.0]]
    assert _predict_estimator(estimator, "predict", values) is values
    assert estimator.n_jobs == -1


def test_ultra_pack_and_templates() -> None:
    ultra = pd.read_csv(ROOT / "data" / "packs" / "synthetic_ultra_dti_v3.csv")
    assert len(ultra) == 16000
    assert ultra["drug_id"].nunique() == 400
    assert ultra["target_id"].nunique() == 40
    assert 0.49 <= float(ultra["label"].mean()) <= 0.51
    for name in (
        "classification_training_template.csv",
        "regression_training_template.csv",
        "prediction_input_template.csv",
    ):
        path = ROOT / "data" / "templates" / name
        assert path.is_file()
        assert len(pd.read_csv(path)) == 100


def test_step16_models_and_champions() -> None:
    summary = data_library_summary(ROOT)
    ranking = summary["benchmark"]["ranking"]
    assert len(ranking) >= 9
    files = {item["filename"] for item in ranking}
    assert {
        "packv3_classification_extra_trees.joblib",
        "packv3_classification_sgd_logistic.joblib",
        "packv3_regression_elastic_net.joblib",
        "packv3_regression_sgd.joblib",
        "packv3_regression_extra_trees_foundation.joblib",
    } <= files
    assert default_model_path(ROOT / "models").name == (
        "packv5_5x_classification_extra_trees.joblib"
    )


def test_step16_best_models_predict() -> None:
    summary = data_library_summary(ROOT)
    sample = pd.read_csv(ROOT / "data" / "packs" / "synthetic_ultra_dti_v3.csv").iloc[0]
    for task in ("classification", "regression"):
        filename = summary["benchmark"]["best_models"][task]["filename"]
        artifact = load_model_artifact(
            ROOT / "models" / filename,
            trusted_root=ROOT / "models",
        )
        result = predict_dti_pair(
            artifact,
            str(sample["canonical_smiles"]),
            str(sample["protein_sequence"]),
        )
        assert result.task_type == task


def test_step16_integrity_and_navigation() -> None:
    integrity = verify_data_pack_integrity(ROOT)
    assert integrity["valid"] is True
    assert integrity["total_rows"] == 223930
    assert len(PAGE_CATALOG) >= 71
    assert PAGE_BY_KEY["ml_autolab"].path.endswith("34_ML_AutoLab.py")
    assert (ROOT / "pages" / "34_ML_AutoLab.py").is_file()


def test_step16_windows_builder_contains_ml_suite() -> None:
    content = (ROOT / "BUILD_DATA_AND_MODELS_WINDOWS.bat").read_text()
    assert "train_step16_ml_suite.py" in content
    assert "generate_data_packs.py" in content
