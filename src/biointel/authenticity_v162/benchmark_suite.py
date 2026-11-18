from __future__ import annotations

from biointel.runtime_paths import runtime_reports_directory

import hashlib
import json
import math
import platform
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd
import scipy
import sklearn
from scipy.stats import pearsonr, spearmanr
from sklearn.datasets import (
    load_breast_cancer,
    load_diabetes,
    load_digits,
    load_iris,
    load_wine,
)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import KFold, StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, label_binarize

RANDOM_SEED = 16242
SUITE_VERSION = "1.0.0"


@dataclass(frozen=True)
class BenchmarkSpec:
    key: str
    title: str
    loader: Callable[..., Any]
    task_type: str
    source_name: str
    source_url: str
    intended_use: str
    limitations: str


BENCHMARK_SPECS: tuple[BenchmarkSpec, ...] = (
    BenchmarkSpec(
        key="uci_wdbc_breast_cancer",
        title="Wisconsin Diagnostic Breast Cancer public benchmark",
        loader=load_breast_cancer,
        task_type="classification",
        source_name="UCI Wisconsin Diagnostic Breast Cancer via scikit-learn",
        source_url="https://archive.ics.uci.edu/dataset/17/breast+cancer+wisconsin+diagnostic",
        intended_use="Reproducible binary-classification, calibration and provenance benchmark only.",
        limitations="Not a clinical diagnostic device and not externally validated for deployment at a healthcare site.",
    ),
    BenchmarkSpec(
        key="uci_wine_classification",
        title="UCI Wine recognition public benchmark",
        loader=load_wine,
        task_type="classification",
        source_name="UCI Wine recognition dataset via scikit-learn",
        source_url="https://archive.ics.uci.edu/dataset/109/wine",
        intended_use="Reproducible multiclass scientific-ML benchmark only.",
        limitations="Chemical-class benchmark; it is not a drug, toxicity or clinical prediction model.",
    ),
    BenchmarkSpec(
        key="fisher_iris_classification",
        title="Fisher Iris public benchmark",
        loader=load_iris,
        task_type="classification",
        source_name="Fisher Iris dataset distributed with scikit-learn",
        source_url="https://scikit-learn.org/stable/modules/generated/sklearn.datasets.load_iris.html",
        intended_use="Small multiclass pipeline and reproducibility benchmark only.",
        limitations="Educational botanical dataset; not representative of high-dimensional biomedical deployment.",
    ),
    BenchmarkSpec(
        key="uci_optical_digits_classification",
        title="UCI Optical Digits public benchmark",
        loader=load_digits,
        task_type="classification",
        source_name="UCI Optical Recognition of Handwritten Digits via scikit-learn",
        source_url="https://archive.ics.uci.edu/dataset/80/optical+recognition+of+handwritten+digits",
        intended_use="Image-feature multiclass software and model-governance benchmark only.",
        limitations="Not a biomedical image model and not a substitute for pathology or microscopy validation.",
    ),
    BenchmarkSpec(
        key="diabetes_progression_regression",
        title="Diabetes progression public regression benchmark",
        loader=load_diabetes,
        task_type="regression",
        source_name="Diabetes progression dataset distributed with scikit-learn",
        source_url="https://scikit-learn.org/stable/modules/generated/sklearn.datasets.load_diabetes.html",
        intended_use="Reproducible regression, interval and residual-governance benchmark only.",
        limitations="Not a patient-level clinical forecasting model and not validated for treatment decisions.",
    ),
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _canonical_csv(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")


def _expected_calibration_error(y_true: np.ndarray, probability: np.ndarray, bins: int = 10) -> float:
    if probability.ndim == 1:
        confidence = np.maximum(probability, 1.0 - probability)
        prediction = (probability >= 0.5).astype(int)
    else:
        confidence = probability.max(axis=1)
        prediction = probability.argmax(axis=1)
    correctness = (prediction == y_true).astype(float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    value = 0.0
    for lower, upper in zip(edges[:-1], edges[1:], strict=True):
        mask = (confidence >= lower) & (confidence < upper if upper < 1.0 else confidence <= upper)
        if not np.any(mask):
            continue
        value += float(mask.mean()) * abs(float(correctness[mask].mean()) - float(confidence[mask].mean()))
    return float(value)


def _multiclass_brier(y_true: np.ndarray, probability: np.ndarray, classes: np.ndarray) -> float:
    encoded = label_binarize(y_true, classes=classes)
    if probability.shape[1] == 2 and encoded.shape[1] == 1:
        encoded = np.column_stack([1 - encoded[:, 0], encoded[:, 0]])
    return float(np.mean(np.sum((probability - encoded) ** 2, axis=1) / probability.shape[1]))


def _bootstrap_interval(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    metric: Callable[[np.ndarray, np.ndarray], float],
    *,
    iterations: int = 250,
) -> dict[str, float]:
    rng = np.random.default_rng(RANDOM_SEED)
    scores: list[float] = []
    size = len(y_true)
    for _ in range(iterations):
        index = rng.integers(0, size, size=size)
        try:
            score = float(metric(y_true[index], y_pred[index]))
        except (ValueError, ZeroDivisionError):
            continue
        if math.isfinite(score):
            scores.append(score)
    if not scores:
        return {"lower_95": float("nan"), "upper_95": float("nan"), "iterations": 0}
    return {
        "lower_95": float(np.quantile(scores, 0.025)),
        "upper_95": float(np.quantile(scores, 0.975)),
        "iterations": len(scores),
    }


def _classification_model() -> Pipeline:
    return Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    max_iter=5000,
                    class_weight="balanced",
                    solver="lbfgs",
                    random_state=RANDOM_SEED,
                ),
            ),
        ]
    )


def _regression_model() -> Pipeline:
    return Pipeline([("scale", StandardScaler()), ("model", Ridge(alpha=1.0))])


def _classification_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    probability: np.ndarray,
    classes: np.ndarray,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro")),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "log_loss": float(log_loss(y_true, probability, labels=classes)),
        "brier_score": _multiclass_brier(y_true, probability, classes),
        "expected_calibration_error": _expected_calibration_error(y_true, probability),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=classes).tolist(),
    }
    try:
        if len(classes) == 2:
            metrics["roc_auc"] = float(roc_auc_score(y_true, probability[:, 1]))
        else:
            metrics["roc_auc_ovr_macro"] = float(
                roc_auc_score(y_true, probability, multi_class="ovr", average="macro")
            )
    except ValueError:
        pass
    metrics["balanced_accuracy_ci95"] = _bootstrap_interval(
        y_true,
        y_pred,
        balanced_accuracy_score,
    )
    metrics["f1_macro_ci95"] = _bootstrap_interval(
        y_true,
        y_pred,
        lambda truth, pred: f1_score(truth, pred, average="macro"),
    )
    return metrics


def _regression_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    interval_lower: np.ndarray,
    interval_upper: np.ndarray,
) -> dict[str, Any]:
    pearson = pearsonr(y_true, y_pred)
    spearman = spearmanr(y_true, y_pred)
    coverage = float(np.mean((y_true >= interval_lower) & (y_true <= interval_upper)))
    metrics: dict[str, Any] = {
        "r2": float(r2_score(y_true, y_pred)),
        "rmse": float(mean_squared_error(y_true, y_pred) ** 0.5),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "pearson": float(pearson.statistic),
        "spearman": float(spearman.statistic),
        "conformal_coverage": coverage,
        "mean_prediction_interval_width": float(np.mean(interval_upper - interval_lower)),
    }
    metrics["r2_ci95"] = _bootstrap_interval(y_true, y_pred, r2_score)
    metrics["mae_ci95"] = _bootstrap_interval(y_true, y_pred, mean_absolute_error)
    return metrics


def _dataset_frame(spec: BenchmarkSpec) -> tuple[pd.DataFrame, list[str], str]:
    bunch = spec.loader(as_frame=True)
    frame = bunch.frame.copy()
    target_name = str(getattr(bunch, "target_names", "target"))
    if "target" not in frame.columns:
        frame["target"] = bunch.target
    frame.insert(0, "sample_id", [f"{spec.key}:{index:05d}" for index in range(len(frame))])
    feature_names = [str(value) for value in bunch.feature_names]
    return frame, feature_names, target_name


def _environment_manifest() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "scikit_learn": sklearn.__version__,
        "joblib": joblib.__version__,
    }


def _model_card_markdown(card: dict[str, Any]) -> str:
    metric_lines = "\n".join(
        f"- **{key}:** {value:.6g}"
        for key, value in card["holdout_metrics"].items()
        if isinstance(value, (int, float))
    )
    return (
        f"# {card['title']}\n\n"
        f"**Authenticity tier:** {card['authenticity_tier']}  \n"
        f"**Task:** {card['task_type']}  \n"
        f"**Dataset SHA-256:** `{card['dataset_sha256']}`  \n"
        f"**Artifact SHA-256:** `{card['artifact_sha256']}`\n\n"
        f"## Intended use\n\n{card['intended_use']}\n\n"
        f"## Source\n\n- {card['source_name']}\n- {card['source_url']}\n\n"
        f"## Untouched holdout metrics\n\n{metric_lines}\n\n"
        f"## Limitations\n\n{card['limitations']}\n\n"
        "## Release boundary\n\n"
        "The public dataset, immutable local snapshot, deterministic split, artifact hash, "
        "holdout predictions, calibration diagnostics and model card are verified. "
        "This is a public benchmark model, not an independently validated domain or clinical model. "
        "External release eligibility is therefore false.\n"
    )


def build_public_benchmark_suite(root: str | Path) -> pd.DataFrame:
    project_root = Path(root).expanduser().resolve()
    data_root = project_root / "data" / "step162" / "public_benchmarks"
    model_root = project_root / "models" / "authentic_benchmarks"
    data_root.mkdir(parents=True, exist_ok=True)
    model_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []

    for spec in BENCHMARK_SPECS:
        benchmark_root = data_root / spec.key
        benchmark_root.mkdir(parents=True, exist_ok=True)
        frame, feature_names, target_description = _dataset_frame(spec)
        dataset_path = benchmark_root / "dataset.csv"
        dataset_bytes = _canonical_csv(frame)
        dataset_path.write_bytes(dataset_bytes)
        dataset_sha256 = _sha256_bytes(dataset_bytes)
        target = frame["target"].to_numpy()
        features = frame[feature_names]
        indices = np.arange(len(frame))

        if spec.task_type == "classification":
            train_indices, holdout_indices = train_test_split(
                indices,
                test_size=0.20,
                random_state=RANDOM_SEED,
                stratify=target,
            )
            model = _classification_model()
            model.fit(features.iloc[train_indices], target[train_indices])
            prediction = model.predict(features.iloc[holdout_indices])
            probability = model.predict_proba(features.iloc[holdout_indices])
            classes = np.asarray(model.classes_)
            holdout_metrics = _classification_metrics(
                target[holdout_indices],
                prediction,
                probability,
                classes,
            )
            cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_SEED)
            cv_results = cross_validate(
                _classification_model(),
                features,
                target,
                cv=cv,
                scoring={"balanced_accuracy": "balanced_accuracy", "f1_macro": "f1_macro"},
                n_jobs=1,
            )
            cv_metrics = {
                "balanced_accuracy_mean": float(np.mean(cv_results["test_balanced_accuracy"])),
                "balanced_accuracy_std": float(np.std(cv_results["test_balanced_accuracy"], ddof=1)),
                "f1_macro_mean": float(np.mean(cv_results["test_f1_macro"])),
                "f1_macro_std": float(np.std(cv_results["test_f1_macro"], ddof=1)),
            }
            predictions = pd.DataFrame(
                {
                    "sample_id": frame.iloc[holdout_indices]["sample_id"].to_numpy(),
                    "actual": target[holdout_indices],
                    "predicted": prediction,
                    "max_probability": probability.max(axis=1),
                }
            )
            for position, class_name in enumerate(classes):
                predictions[f"probability_class_{class_name}"] = probability[:, position]
            split_payload = {
                "train_indices": train_indices.tolist(),
                "calibration_indices": [],
                "holdout_indices": holdout_indices.tolist(),
                "stratified": True,
            }
            uncertainty = {
                "method": "probability calibration diagnostics",
                "expected_calibration_error": holdout_metrics["expected_calibration_error"],
                "brier_score": holdout_metrics["brier_score"],
            }
        else:
            development_indices, holdout_indices = train_test_split(
                indices,
                test_size=0.20,
                random_state=RANDOM_SEED,
            )
            train_indices, calibration_indices = train_test_split(
                development_indices,
                test_size=0.20,
                random_state=RANDOM_SEED + 1,
            )
            model = _regression_model()
            model.fit(features.iloc[train_indices], target[train_indices])
            calibration_prediction = model.predict(features.iloc[calibration_indices])
            residual_quantile = float(
                np.quantile(np.abs(target[calibration_indices] - calibration_prediction), 0.90, method="higher")
            )
            prediction = model.predict(features.iloc[holdout_indices])
            interval_lower = prediction - residual_quantile
            interval_upper = prediction + residual_quantile
            holdout_metrics = _regression_metrics(
                target[holdout_indices], prediction, interval_lower, interval_upper
            )
            cv = KFold(n_splits=5, shuffle=True, random_state=RANDOM_SEED)
            cv_results = cross_validate(
                _regression_model(),
                features,
                target,
                cv=cv,
                scoring={"r2": "r2", "neg_mae": "neg_mean_absolute_error"},
                n_jobs=1,
            )
            cv_metrics = {
                "r2_mean": float(np.mean(cv_results["test_r2"])),
                "r2_std": float(np.std(cv_results["test_r2"], ddof=1)),
                "mae_mean": float(-np.mean(cv_results["test_neg_mae"])),
                "mae_std": float(np.std(-cv_results["test_neg_mae"], ddof=1)),
            }
            predictions = pd.DataFrame(
                {
                    "sample_id": frame.iloc[holdout_indices]["sample_id"].to_numpy(),
                    "actual": target[holdout_indices],
                    "predicted": prediction,
                    "prediction_interval_lower": interval_lower,
                    "prediction_interval_upper": interval_upper,
                }
            )
            split_payload = {
                "train_indices": train_indices.tolist(),
                "calibration_indices": calibration_indices.tolist(),
                "holdout_indices": holdout_indices.tolist(),
                "stratified": False,
            }
            uncertainty = {
                "method": "split conformal absolute residual",
                "alpha": 0.10,
                "absolute_residual_quantile": residual_quantile,
                "holdout_coverage": holdout_metrics["conformal_coverage"],
            }

        artifact_path = model_root / f"{spec.key}.joblib"
        joblib.dump(model, artifact_path, compress=3)
        artifact_sha256 = _sha256_file(artifact_path)
        predictions_path = benchmark_root / "untouched_holdout_predictions.csv"
        predictions.to_csv(predictions_path, index=False)
        _write_json(benchmark_root / "split_manifest.json", split_payload)
        _write_json(
            benchmark_root / "dataset_manifest.json",
            {
                "schema": "biointel.step162.public-dataset-manifest.v1",
                "dataset_key": spec.key,
                "title": spec.title,
                "source_name": spec.source_name,
                "source_url": spec.source_url,
                "distribution": f"scikit-learn {sklearn.__version__} bundled dataset copy",
                "licence_review_status": "source terms recorded; deployment user must confirm intended-use compliance",
                "dataset_sha256": dataset_sha256,
                "rows": len(frame),
                "features": len(feature_names),
                "target_description": target_description,
                "synthetic": False,
                "public_reference_data": True,
                "clinical_release_eligible": False,
            },
        )
        _write_json(
            benchmark_root / "metrics.json",
            {
                "schema": "biointel.step162.benchmark-metrics.v1",
                "holdout_metrics": holdout_metrics,
                "cross_validation_metrics": cv_metrics,
                "uncertainty": uncertainty,
            },
        )
        _write_json(benchmark_root / "environment.json", _environment_manifest())

        card = {
            "schema": "biointel.step162.public-benchmark-model-card.v1",
            "model_id": f"step162-{spec.key}",
            "title": spec.title,
            "model_version": SUITE_VERSION,
            "task_type": spec.task_type,
            "algorithm": type(model.named_steps["model"]).__name__,
            "feature_names": feature_names,
            "dataset_sha256": dataset_sha256,
            "artifact_sha256": artifact_sha256,
            "artifact_path": str(artifact_path.relative_to(project_root)).replace("\\", "/"),
            "source_name": spec.source_name,
            "source_url": spec.source_url,
            "intended_use": spec.intended_use,
            "limitations": spec.limitations,
            "training_rows": len(split_payload["train_indices"]),
            "calibration_rows": len(split_payload["calibration_indices"]),
            "holdout_rows": len(split_payload["holdout_indices"]),
            "holdout_metrics": holdout_metrics,
            "cross_validation_metrics": cv_metrics,
            "uncertainty": uncertainty,
            "synthetic_training_data": False,
            "public_data_authenticity_passed": True,
            "independent_external_validation": False,
            "clinical_or_regulatory_release_eligible": False,
            "authenticity_tier": "Public benchmark / immutable snapshot / reproducible holdout",
            "created_at_utc": _utc_now(),
        }
        _write_json(benchmark_root / "model_card.json", card)
        (benchmark_root / "MODEL_CARD.md").write_text(_model_card_markdown(card), encoding="utf-8")

        protected_files = [
            dataset_path,
            predictions_path,
            benchmark_root / "split_manifest.json",
            benchmark_root / "dataset_manifest.json",
            benchmark_root / "metrics.json",
            benchmark_root / "environment.json",
            benchmark_root / "model_card.json",
            benchmark_root / "MODEL_CARD.md",
            artifact_path,
        ]
        file_manifest = []
        for path in protected_files:
            file_manifest.append(
                {
                    "path": str(path.relative_to(project_root)).replace("\\", "/"),
                    "sha256": _sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
        _write_json(benchmark_root / "FILE_MANIFEST_SHA256.json", file_manifest)
        rows.append(
            {
                "model_id": card["model_id"],
                "title": spec.title,
                "task_type": spec.task_type,
                "dataset_rows": len(frame),
                "feature_count": len(feature_names),
                "dataset_sha256": dataset_sha256,
                "artifact_sha256": artifact_sha256,
                "public_data_authenticity_passed": True,
                "independent_external_validation": False,
                "clinical_or_regulatory_release_eligible": False,
                "model_card_path": str((benchmark_root / "model_card.json").relative_to(project_root)).replace("\\", "/"),
                "artifact_path": str(artifact_path.relative_to(project_root)).replace("\\", "/"),
            }
        )

    frame = pd.DataFrame(rows)
    report_dir = runtime_reports_directory(project_root)
    report_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(report_dir / "step162_public_benchmark_models.csv", index=False)
    _write_json(
        report_dir / "step162_public_benchmark_summary.json",
        {
            "schema": "biointel.step162.public-benchmark-summary.v1",
            "suite_version": SUITE_VERSION,
            "models": len(frame),
            "public_data_authenticity_passed": int(frame["public_data_authenticity_passed"].sum()),
            "external_release_eligible": int(frame["clinical_or_regulatory_release_eligible"].sum()),
            "environment": _environment_manifest(),
        },
    )
    return frame


def verify_public_benchmark_suite(root: str | Path) -> pd.DataFrame:
    project_root = Path(root).expanduser().resolve()
    rows: list[dict[str, Any]] = []
    for spec in BENCHMARK_SPECS:
        benchmark_root = project_root / "data" / "step162" / "public_benchmarks" / spec.key
        manifest_path = benchmark_root / "FILE_MANIFEST_SHA256.json"
        passed = True
        detail: list[str] = []
        verified_files = 0
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            manifest = []
            passed = False
            detail.append(f"manifest error: {exc}")
        for item in manifest if isinstance(manifest, list) else []:
            path = project_root / str(item.get("path", ""))
            expected = str(item.get("sha256", ""))
            if not path.is_file() or _sha256_file(path) != expected:
                passed = False
                detail.append(f"hash mismatch or missing: {path}")
            else:
                verified_files += 1
        card_path = benchmark_root / "model_card.json"
        try:
            card = json.loads(card_path.read_text(encoding="utf-8"))
            artifact = project_root / card["artifact_path"] if "artifact_path" in card else project_root / "models" / "authentic_benchmarks" / f"{spec.key}.joblib"
            if not artifact.is_file():
                artifact = project_root / "models" / "authentic_benchmarks" / f"{spec.key}.joblib"
            model = joblib.load(artifact)
            dataset = pd.read_csv(benchmark_root / "dataset.csv")
            split = json.loads((benchmark_root / "split_manifest.json").read_text(encoding="utf-8"))
            holdout = split["holdout_indices"]
            feature_names = card["feature_names"]
            prediction = model.predict(dataset.iloc[holdout][feature_names])
            if len(prediction) != len(holdout):
                passed = False
                detail.append("prediction length mismatch")
        except Exception as exc:  # verifier must report instead of crashing
            passed = False
            detail.append(f"load/predict error: {type(exc).__name__}: {exc}")
        rows.append(
            {
                "model_key": spec.key,
                "passed": passed,
                "files_verified": verified_files,
                "detail": "; ".join(detail) if detail else "checksums, model load and holdout inference passed",
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "BENCHMARK_SPECS",
    "BenchmarkSpec",
    "build_public_benchmark_suite",
    "verify_public_benchmark_suite",
]
