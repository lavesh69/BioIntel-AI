from pathlib import Path

import pandas as pd

from biointel.training.model_artifact import load_model_artifact, save_model_artifact
from biointel.training.trainers import TrainingConfig, train_dti_model

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "examples" / "synthetic_dti_demo.csv"


def test_classification_training_and_artifact_round_trip(tmp_path):
    data = pd.read_csv(DATASET)
    config = TrainingConfig(
        task_type="classification",
        model_name="random_forest",
        fingerprint_bits=64,
        n_estimators=20,
        synthetic_demo=True,
    )
    result = train_dti_model(data, config)
    assert result.train_rows > result.test_rows > 0
    assert "accuracy" in result.metrics
    assert len(result.predictions) == result.test_rows

    path = save_model_artifact(result.artifact, tmp_path / "model.joblib")
    loaded = load_model_artifact(path)
    assert loaded.metadata.task_type == "classification"
    assert loaded.feature_schema.feature_count == result.artifact.feature_schema.feature_count


def test_regression_training():
    data = pd.read_csv(DATASET)
    config = TrainingConfig(
        task_type="regression",
        model_name="ridge",
        fingerprint_bits=64,
        synthetic_demo=True,
    )
    result = train_dti_model(data, config)
    assert "rmse" in result.metrics
    assert result.metrics["rmse"] is not None
    assert set(result.predictions.columns) == {"actual", "predicted"}
