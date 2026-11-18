from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib

from biointel.dti.feature_combiner import FeatureSchema
from biointel.utils.runtime_cache import file_signature
from biointel.utils.exceptions import (
    FeatureSchemaMismatchError,
    ModelNotFoundError,
)

ARTIFACT_VERSION = "7.0.0"


@dataclass(frozen=True)
class ModelMetadata:
    """Human-readable metadata stored with every DTI model."""

    artifact_version: str
    experiment_id: str
    model_version: str
    model_name: str
    task_type: str
    trained_at_utc: str
    dataset_name: str
    dataset_version: str
    dataset_sha256: str
    split_strategy: str
    threshold_strategy: str
    calibration_method: str
    decision_threshold: float | None
    positive_class_name: str | None
    activity_type: str | None
    synthetic_demo: bool
    train_rows: int
    validation_rows: int
    test_rows: int
    metrics: dict[str, float | None]
    validation_metrics: dict[str, float | None]
    confidence_intervals: dict[str, object]
    data_quality_summary: dict[str, object]
    training_config: dict[str, object]
    software_versions: dict[str, str]
    uncertainty_calibration: dict[str, object] = field(default_factory=dict)


@dataclass
class ModelArtifact:
    """Serializable estimator and reproducibility information."""

    estimator: Any
    feature_schema: FeatureSchema
    feature_names: tuple[str, ...]
    metadata: ModelMetadata
    applicability_statistics: dict[str, Any]

    def validate_feature_schema(
        self,
        schema: FeatureSchema,
        names: tuple[str, ...],
    ) -> None:
        if schema.feature_hash != self.feature_schema.feature_hash:
            raise FeatureSchemaMismatchError(
                "Feature schema hash does not match the trained model. "
                "Use the model's feature settings."
            )
        if schema.feature_count != self.feature_schema.feature_count:
            raise FeatureSchemaMismatchError("Feature count does not match the trained model.")
        if names != self.feature_names:
            raise FeatureSchemaMismatchError("Feature names/order do not match the trained model.")

    def metadata_json(self) -> str:
        payload = asdict(self.metadata)
        payload["feature_schema"] = asdict(self.feature_schema)
        return json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            default=str,
        )


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def save_model_artifact(
    artifact: ModelArtifact,
    path: str | Path,
    metadata_path: str | Path | None = None,
) -> Path:
    """Save an artifact, JSON metadata and a Markdown model card."""

    from biointel.reports.model_card import build_model_card_markdown

    output = Path(path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix != ".joblib":
        output = output.with_suffix(".joblib")

    joblib.dump(artifact, output, compress=3)
    sidecar = Path(metadata_path).resolve() if metadata_path else output.with_suffix(".json")
    sidecar.write_text(
        artifact.metadata_json(),
        encoding="utf-8",
    )
    output.with_suffix(".model_card.md").write_text(
        build_model_card_markdown(artifact),
        encoding="utf-8",
    )
    return output


def load_model_artifact(
    path: str | Path,
    trusted_root: str | Path | None = None,
    max_size_mb: int = 500,
) -> ModelArtifact:
    """Load only a trusted local artifact; never pass arbitrary uploads."""

    model_path = Path(path).resolve()
    if trusted_root is not None:
        root = Path(trusted_root).resolve()
        if root not in model_path.parents:
            raise ModelNotFoundError("Model path is outside the trusted models directory.")

    if not model_path.exists() or not model_path.is_file():
        raise ModelNotFoundError(f"Model artifact not found: {model_path.name}")
    if model_path.suffix.lower() != ".joblib":
        raise ModelNotFoundError("Only .joblib BioIntel model artifacts are supported.")
    if model_path.stat().st_size > max_size_mb * 1024 * 1024:
        raise ModelNotFoundError(f"Model artifact exceeds the {max_size_mb} MB safety limit.")

    try:
        loaded = joblib.load(model_path)
    except Exception as exc:
        raise FeatureSchemaMismatchError(
            f"Model artifact {model_path.name} is corrupt, incomplete or incompatible: {exc}"
        ) from exc
    if not isinstance(loaded, ModelArtifact):
        raise FeatureSchemaMismatchError("File is not a compatible BioIntel model artifact.")
    if loaded.metadata.artifact_version != ARTIFACT_VERSION:
        raise FeatureSchemaMismatchError(
            "Model artifact version is incompatible. Retrain the model."
        )
    return loaded


@lru_cache(maxsize=12)
def _load_model_artifact_cached(
    path_string: str,
    modification_ns: int,
    size_bytes: int,
    change_ns: int,
    content_fingerprint: str,
    trusted_root_string: str | None,
    max_size_mb: int,
) -> ModelArtifact:
    del modification_ns, size_bytes, change_ns, content_fingerprint
    return load_model_artifact(
        path_string,
        trusted_root=trusted_root_string,
        max_size_mb=max_size_mb,
    )


def load_model_artifact_cached(
    path: str | Path,
    trusted_root: str | Path | None = None,
    max_size_mb: int = 500,
) -> ModelArtifact:
    """Load a trusted model once per path, mtime and file-size signature."""

    model_path = Path(path).resolve()
    if not model_path.exists() or not model_path.is_file():
        raise ModelNotFoundError(f"Model artifact not found: {model_path.name}")
    try:
        signature = file_signature(model_path)
    except OSError as exc:
        raise ModelNotFoundError(f"Model artifact cannot be accessed: {model_path.name}") from exc
    trusted = str(Path(trusted_root).resolve()) if trusted_root is not None else None
    return _load_model_artifact_cached(
        *signature,
        trusted,
        max_size_mb,
    )


@lru_cache(maxsize=16)
def _discover_compatible_model_artifacts_cached(
    root_string: str,
    signature: tuple[tuple[str, int, int, int, str], ...],
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    root = Path(root_string)
    compatible: list[str] = []
    rejected: list[tuple[str, str]] = []
    for name, _mtime_ns, _size_bytes, _change_ns, _fingerprint in signature:
        path = root / name
        try:
            load_model_artifact_cached(path, trusted_root=root)
            compatible.append(name)
        except Exception as exc:  # trusted local files; report without crashing UI
            rejected.append((name, str(exc)))
    return tuple(compatible), tuple(rejected)



@lru_cache(maxsize=16)
def _discover_model_artifact_candidates_cached(
    root_string: str,
    signature: tuple[tuple[str, int, int, int, str, int, int, int, str], ...],
    max_size_mb: int,
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Validate lightweight JSON envelopes without deserialising every estimator.

    This is intended for catalogue/release-gate page loading. The selected model
    is still fully deserialised and type-checked immediately before use.
    """

    root = Path(root_string)
    compatible: list[str] = []
    rejected: list[tuple[str, str]] = []
    limit = int(max_size_mb) * 1024 * 1024
    for (
        name,
        _model_mtime,
        model_size,
        _model_change,
        _model_fingerprint,
        _sidecar_mtime,
        _sidecar_size,
        _sidecar_change,
        _sidecar_fingerprint,
    ) in signature:
        model_path = root / name
        sidecar = model_path.with_suffix(".json")
        if model_size > limit:
            rejected.append((name, f"Model exceeds the {max_size_mb} MB safety limit."))
            continue
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            rejected.append((name, f"Missing or invalid metadata sidecar: {exc}"))
            continue
        if not isinstance(payload, dict):
            rejected.append((name, "Metadata sidecar must contain a JSON object."))
            continue
        if str(payload.get("artifact_version", "")) != ARTIFACT_VERSION:
            rejected.append((name, "Model artifact version is incompatible."))
            continue
        schema = payload.get("feature_schema")
        if not isinstance(schema, dict) or not schema.get("feature_hash"):
            rejected.append((name, "Metadata sidecar is missing a valid feature schema."))
            continue
        compatible.append(name)
    return tuple(compatible), tuple(rejected)


def discover_model_artifact_candidates(
    models_directory: str | Path,
    *,
    max_size_mb: int = 500,
) -> tuple[list[Path], dict[str, str]]:
    """Return lightweight compatible candidates for selectors and catalogues.

    Unlike :func:`discover_compatible_model_artifacts`, this function does not
    load every estimator into memory. It validates the local model file and its
    checksum-friendly JSON envelope, then full loading remains mandatory before
    prediction, evaluation or release decisions.
    """

    root = Path(models_directory).resolve()
    signature_rows: list[tuple[str, int, int, int, str, int, int, int, str]] = []
    rejected: dict[str, str] = {}
    for model_path in sorted(root.glob("*.joblib")):
        sidecar = model_path.with_suffix(".json")
        if not sidecar.is_file():
            rejected[model_path.name] = "Missing BioIntel JSON metadata sidecar."
            continue
        try:
            model_signature = file_signature(model_path)
            sidecar_signature = file_signature(sidecar)
        except OSError as exc:
            rejected[model_path.name] = f"Model metadata cannot be accessed: {exc}"
            continue
        signature_rows.append((
            model_path.name,
            model_signature[1],
            model_signature[2],
            model_signature[3],
            model_signature[4],
            sidecar_signature[1],
            sidecar_signature[2],
            sidecar_signature[3],
            sidecar_signature[4],
        ))
    compatible_names, rejected_items = _discover_model_artifact_candidates_cached(
        str(root), tuple(signature_rows), int(max_size_mb)
    )
    rejected.update(dict(rejected_items))
    return [root / name for name in compatible_names], rejected

def discover_compatible_model_artifacts(
    models_directory: str | Path,
) -> tuple[list[Path], dict[str, str]]:
    """Return compatible BioIntel envelopes using a change-aware directory cache.

    Independent benchmark estimators may also use ``.joblib`` but do not carry
    BioIntel feature schemas. The cache is invalidated by file name, size or
    modification time, so repeated Streamlit reruns avoid reopening unchanged
    artifacts without hiding model updates.
    """

    root = Path(models_directory).resolve()
    signature = tuple(
        (path.name, *file_signature(path)[1:])
        for path in sorted(root.glob("*.joblib"))
    )
    compatible_names, rejected_items = _discover_compatible_model_artifacts_cached(
        str(root), signature
    )
    return [root / name for name in compatible_names], dict(rejected_items)


def clear_model_artifact_cache() -> None:
    """Clear cached model objects and compatibility discovery results."""

    _load_model_artifact_cached.cache_clear()
    _discover_compatible_model_artifacts_cached.cache_clear()
    _discover_model_artifact_candidates_cached.cache_clear()


def model_artifact_cache_info() -> dict[str, int | None]:
    """Return process-level model-cache statistics."""

    return _load_model_artifact_cached.cache_info()._asdict()


def preload_model_directory(
    models_directory: str | Path,
    *,
    limit: int = 12,
) -> dict[str, object]:
    """Warm the trusted model cache without failing application startup."""

    root = Path(models_directory).resolve()
    loaded: list[str] = []
    failed: dict[str, str] = {}
    for path in sorted(root.glob("*.joblib"))[: max(0, int(limit))]:
        try:
            load_model_artifact_cached(path, trusted_root=root)
            loaded.append(path.name)
        except Exception as exc:
            failed[path.name] = str(exc)
    return {
        "loaded": loaded,
        "failed": failed,
        "requested_limit": int(limit),
        "cache": model_artifact_cache_info(),
    }
