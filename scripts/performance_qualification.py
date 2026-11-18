from __future__ import annotations

# ruff: noqa: E402, I001

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.dti.predictor import batch_predict_dti
from biointel.observability.performance import (
    measure_operation,
    save_performance_report,
)
from biointel.training.model_artifact import load_model_artifact_cached


def main() -> int:
    model_path = ROOT / "models" / "demo_classification_model.joblib"
    sample_path = ROOT / "data" / "packs" / "batch_prediction_sample_250.csv"
    if not sample_path.is_file():
        sample_path = ROOT / "data" / "examples" / "synthetic_dti_demo.csv"
    artifact = load_model_artifact_cached(model_path, trusted_root=ROOT / "models")
    dataframe = pd.read_csv(sample_path).head(250)
    columns = ["canonical_smiles", "protein_sequence"]
    dataframe = dataframe[columns].copy()
    dataframe["sample_id"] = range(1, len(dataframe) + 1)
    cache_path = ROOT / "reports" / "performance_feature_cache.sqlite3"

    measurements = []
    _, cold = measure_operation(
        "batch_prediction_cold_cache",
        lambda: batch_predict_dti(
            artifact,
            dataframe,
            max_rows=1000,
            n_jobs=4,
            feature_cache_path=cache_path,
        ),
        rows=len(dataframe),
        budget_seconds=30.0,
    )
    measurements.append(cold)
    _, warm = measure_operation(
        "batch_prediction_warm_cache",
        lambda: batch_predict_dti(
            artifact,
            dataframe,
            max_rows=1000,
            n_jobs=4,
            feature_cache_path=cache_path,
        ),
        rows=len(dataframe),
        budget_seconds=10.0,
    )
    measurements.append(warm)
    output = save_performance_report(
        measurements,
        ROOT / "reports" / "generated" / "performance_qualification.json",
    )
    print(output)
    for item in measurements:
        print(
            f"{item.name}: {item.elapsed_seconds:.3f}s, "
            f"{item.rows_per_second:.1f} rows/s, budget={item.passed_budget}"
        )
    return 0 if all(item.passed_budget for item in measurements) else 1


if __name__ == "__main__":
    raise SystemExit(main())
