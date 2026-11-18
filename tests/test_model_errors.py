import pytest

from biointel.training.model_artifact import load_model_artifact
from biointel.utils.exceptions import ModelNotFoundError


def test_missing_model_has_clear_error(tmp_path):
    with pytest.raises(ModelNotFoundError):
        load_model_artifact(tmp_path / "missing.joblib")
