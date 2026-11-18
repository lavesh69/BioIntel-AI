from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from sklearn.metrics import (
    balanced_accuracy_score,
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
)


@dataclass(frozen=True)
class BenchmarkResult:
    name: str
    task: str
    rows: int
    dataset_sha256: str
    metrics: dict[str, float]
    generated_at_utc: str
    metadata: dict[str, Any]

def _sha(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def evaluate_benchmark(
    dataset_path: str | Path,
    *,
    name: str,
    task: str,
    prediction_function: Callable[[pd.DataFrame], Any],
    label_column: str,
    metadata: dict[str, Any] | None = None,
) -> BenchmarkResult:
    path = Path(dataset_path).resolve()
    frame = pd.read_csv(path)
    if label_column not in frame.columns:
        raise ValueError(f"Benchmark is missing label column {label_column!r}.")
    predictions = prediction_function(frame)
    truth = frame[label_column].to_numpy()
    task_key = task.strip().lower()
    if task_key == "classification":
        probabilities = predictions if getattr(predictions, "ndim", 1) == 1 else predictions[:, -1]
        labels = (probabilities >= 0.5).astype(int)
        metrics = {
            "roc_auc": float(roc_auc_score(truth, probabilities)),
            "balanced_accuracy": float(balanced_accuracy_score(truth, labels)),
        }
    elif task_key == "regression":
        metrics = {
            "rmse": float(mean_squared_error(truth, predictions) ** 0.5),
            "mae": float(mean_absolute_error(truth, predictions)),
        }
    else:
        raise ValueError("task must be classification or regression.")
    return BenchmarkResult(name, task_key, len(frame), _sha(path), metrics, datetime.now(UTC).isoformat(timespec="seconds"), metadata or {})

def save_benchmark_result(result: BenchmarkResult, path: str | Path) -> Path:
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(asdict(result), indent=2, sort_keys=True, default=str), encoding="utf-8")
    return destination
