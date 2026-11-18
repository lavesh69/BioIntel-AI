from __future__ import annotations

from pathlib import Path

from biointel.training.model_artifact import ModelArtifact


def export_artifact_to_onnx(
    artifact: ModelArtifact,
    path: str | Path,
    *,
    opset: int = 17,
) -> Path:
    """Export compatible scikit-learn estimators when optional ONNX tools exist."""

    try:
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import FloatTensorType
    except ImportError as exc:
        raise RuntimeError(
            "ONNX export requires optional packages skl2onnx and onnxruntime."
        ) from exc
    output = Path(path).resolve().with_suffix(".onnx")
    output.parent.mkdir(parents=True, exist_ok=True)
    initial_types = [("features", FloatTensorType([None, artifact.feature_schema.feature_count]))]
    model = convert_sklearn(
        artifact.estimator,
        initial_types=initial_types,
        target_opset=opset,
    )
    output.write_bytes(model.SerializeToString())
    return output
