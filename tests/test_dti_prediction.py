from pathlib import Path

import pandas as pd
import pytest

from biointel.dti.feature_combiner import combine_dti_features
from biointel.dti.predictor import batch_predict_dti, predict_dti_pair
from biointel.training.trainers import TrainingConfig, train_dti_model
from biointel.utils.exceptions import FeatureSchemaMismatchError

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "examples" / "synthetic_dti_demo.csv"


@pytest.fixture(scope="module")
def classifier_artifact():
    data = pd.read_csv(DATASET)
    result = train_dti_model(
        data,
        TrainingConfig(
            task_type="classification",
            model_name="random_forest",
            fingerprint_bits=64,
            n_estimators=20,
            synthetic_demo=True,
        ),
    )
    return result.artifact


def test_single_prediction_is_model_backed(classifier_artifact):
    prediction = predict_dti_pair(
        classifier_artifact,
        "CCO",
        "MKWVTFISLLFLFSSAYSRGVFRRDTHKSEIAHRFKDLGE",
    )
    assert prediction.predicted_class in {0, 1}
    assert 0.0 <= prediction.positive_probability <= 1.0
    assert prediction.synthetic_demo_model is True


def test_batch_prediction_isolates_invalid_rows(classifier_artifact):
    batch = pd.DataFrame(
        [
            {
                "sample_id": "good",
                "canonical_smiles": "CCO",
                "protein_sequence": "MKWVTFISLLFLFSSAYSRGVFRRDTHKSEIAHRFKDLGE",
            },
            {
                "sample_id": "bad",
                "canonical_smiles": "not-smiles",
                "protein_sequence": "MKWVTFISLLFLFSSAYSRGVFRRDTHKSEIAHRFKDLGE",
            },
        ]
    )
    output = batch_predict_dti(classifier_artifact, batch)
    assert output.loc[0, "error"] == ""
    assert output.loc[1, "error"] != ""


def test_schema_mismatch_is_rejected(classifier_artifact):
    incompatible = combine_dti_features(
        "CCO",
        "MKWVTFISLLFLFSSAYSRGVFRRDTHKSEIAHRFKDLGE",
        n_bits=128,
    )
    with pytest.raises(FeatureSchemaMismatchError):
        classifier_artifact.validate_feature_schema(incompatible.schema, incompatible.names)
