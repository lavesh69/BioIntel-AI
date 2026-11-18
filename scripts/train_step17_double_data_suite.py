from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.training.experiment_registry import register_experiment  # noqa: E402
from biointel.training.model_artifact import (  # noqa: E402
    load_model_artifact,
    save_model_artifact,
)
from biointel.training.model_catalog import (  # noqa: E402
    sync_model_catalog,
    update_model_catalog,
)
from biointel.training.trainers import (  # noqa: E402
    TrainingConfig,
    train_dti_model,
)

DATASET_FILE = "synthetic_double_ultra_dti_v4.csv"
SOURCE_ROWS = 32000


def _primary_score(task_type: str, metrics: dict[str, float | None]) -> float:
    if task_type == "classification":
        return float(metrics.get("roc_auc") or metrics.get("balanced_accuracy") or 0.0)
    rmse = metrics.get("rmse")
    return -float(rmse) if rmse is not None else -1e9


def _specs() -> list[dict[str, object]]:
    return [
        {
            "task_type": "classification",
            "model_name": "extra_trees",
            "filename": "packv4_double_classification_extra_trees.joblib",
            "n_estimators": 160,
        },
        {
            "task_type": "classification",
            "model_name": "random_forest",
            "filename": "packv4_double_classification_random_forest.joblib",
            "n_estimators": 120,
        },
        {
            "task_type": "classification",
            "model_name": "sgd_logistic",
            "filename": "packv4_double_classification_sgd_logistic.joblib",
            "n_estimators": 1,
        },
        {
            "task_type": "regression",
            "model_name": "extra_trees",
            "filename": "packv4_double_regression_extra_trees.joblib",
            "n_estimators": 80,
        },
        {
            "task_type": "regression",
            "model_name": "ridge",
            "filename": "packv4_double_regression_ridge.joblib",
            "n_estimators": 1,
        },
        {
            "task_type": "regression",
            "model_name": "sgd_regression",
            "filename": "packv4_double_regression_sgd.joblib",
            "n_estimators": 1,
        },
    ]


def _train(
    dataframe: pd.DataFrame,
    spec: dict[str, object],
) -> dict[str, object]:
    task_type = str(spec["task_type"])
    model_name = str(spec["model_name"])
    filename = str(spec["filename"])
    config = TrainingConfig(
        task_type=task_type,
        model_name=model_name,
        split_strategy=("drug_group" if task_type == "classification" else "target_group"),
        test_fraction=0.20,
        validation_fraction=0.15,
        random_seed=20260717,
        decision_threshold=0.5,
        threshold_strategy=("optimize_balanced" if task_type == "classification" else "fixed"),
        calibration_method="none",
        fingerprint_radius=2,
        fingerprint_bits=128,
        use_chirality=True,
        include_dipeptides=False,
        dataset_name="biointel_synthetic_double_ultra_dti_v4",
        dataset_version="4.0",
        model_version="4.0.0-double-data",
        activity_type="SYNTHETIC_AFFINITY_SCORE",
        synthetic_demo=True,
        n_estimators=int(spec["n_estimators"]),
        bootstrap_iterations=30,
        source_description=(
            "BioIntel deterministic synthetic Double Ultra 32,000-pair DTI benchmark"
        ),
        conformal_alpha=0.10,
    )
    result = train_dti_model(dataframe, config)
    output = ROOT / "models" / filename
    save_model_artifact(result.artifact, output)
    register_experiment(
        ROOT / "reports" / "experiments.sqlite3",
        result.artifact,
        output.name,
    )
    return {
        "task_type": task_type,
        "model_name": model_name,
        "training_pack": "double_ultra",
        "source_rows": len(dataframe),
        "filename": filename,
        "primary_score": _primary_score(task_type, result.metrics),
        "validation_metrics": result.validation_metrics,
        "test_metrics": result.metrics,
        "train_rows": result.train_rows,
        "validation_rows": result.validation_rows,
        "test_rows": result.test_rows,
        "feature_cache": result.data_quality_summary.get(
            "feature_cache",
            {},
        ),
        "experiment_id": result.artifact.metadata.experiment_id,
        "dataset_sha256": result.artifact.metadata.dataset_sha256,
    }


def _reuse(spec: dict[str, object]) -> dict[str, object]:
    filename = str(spec["filename"])
    artifact = load_model_artifact(
        ROOT / "models" / filename,
        trusted_root=ROOT / "models",
    )
    return {
        "task_type": str(spec["task_type"]),
        "model_name": str(spec["model_name"]),
        "training_pack": "double_ultra",
        "source_rows": SOURCE_ROWS,
        "filename": filename,
        "primary_score": _primary_score(
            str(spec["task_type"]),
            artifact.metadata.metrics,
        ),
        "validation_metrics": artifact.metadata.validation_metrics,
        "test_metrics": artifact.metadata.metrics,
        "train_rows": artifact.metadata.train_rows,
        "validation_rows": artifact.metadata.validation_rows,
        "test_rows": artifact.metadata.test_rows,
        "feature_cache": artifact.metadata.data_quality_summary.get(
            "feature_cache",
            {},
        ),
        "experiment_id": artifact.metadata.experiment_id,
        "dataset_sha256": artifact.metadata.dataset_sha256,
    }


def _ranking_row(item: dict[str, object]) -> dict[str, object]:
    return {
        "task_type": item["task_type"],
        "model_name": item["model_name"],
        "training_pack": item["training_pack"],
        "source_rows": item["source_rows"],
        "filename": item["filename"],
        **{f"test_{key}": value for key, value in dict(item["test_metrics"]).items()},
    }


def main() -> None:
    dataframe = pd.read_csv(ROOT / "data" / "packs" / DATASET_FILE)
    if len(dataframe) != SOURCE_ROWS:
        raise RuntimeError(f"Expected {SOURCE_ROWS} rows, found {len(dataframe)}.")

    results: list[dict[str, object]] = []
    for spec in _specs():
        model_path = ROOT / "models" / str(spec["filename"])
        if model_path.is_file():
            result = _reuse(spec)
            print(f"Reused {model_path.name}", flush=True)
        else:
            print(
                f"Training {spec['task_type']} {spec['model_name']} "
                "on 32,000-row Double Ultra pack",
                flush=True,
            )
            result = _train(dataframe, spec)
        results.append(result)
        print(
            json.dumps(
                {
                    "filename": result["filename"],
                    "test_metrics": result["test_metrics"],
                    "feature_cache": result["feature_cache"],
                },
                indent=2,
                default=str,
            ),
            flush=True,
        )

    benchmark_path = ROOT / "data" / "packs" / "model_benchmark_summary.json"
    existing = json.loads(benchmark_path.read_text(encoding="utf-8"))
    prior_ranking = [
        row
        for row in existing.get("ranking", [])
        if not str(row.get("filename", "")).startswith("packv4_double_")
    ]
    combined = prior_ranking + [_ranking_row(item) for item in results]

    best_models: dict[str, dict[str, object]] = {}
    for task_type in ("classification", "regression"):
        rows = [row for row in combined if row.get("task_type") == task_type]
        if task_type == "classification":
            rows.sort(
                key=lambda row: float(row.get("test_roc_auc") or 0.0),
                reverse=True,
            )
        else:
            rows.sort(
                key=lambda row: float(
                    row.get("test_rmse") if row.get("test_rmse") is not None else 1e9
                )
            )
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
            row["is_best"] = rank == 1
        champion = rows[0]
        best_models[task_type] = {
            "filename": champion["filename"],
            "model_name": champion["model_name"],
            "training_pack": champion["training_pack"],
            "source_rows": champion["source_rows"],
            "test_metrics": {
                key.removeprefix("test_"): value
                for key, value in champion.items()
                if key.startswith("test_")
            },
        }

    models_dir = ROOT / "models"
    sync_model_catalog(models_dir)
    default_classifier = best_models["classification"]["filename"]
    champion_files = {item["filename"] for item in best_models.values()}
    for row in combined:
        filename = str(row["filename"])
        if not (models_dir / filename).is_file():
            continue
        is_champion = filename in champion_files
        update_model_catalog(
            models_dir,
            filename,
            state="active" if is_champion else "candidate",
            is_default=filename == default_classifier,
            notes=(
                "Step 17 double-data champion."
                if is_champion
                else "Step 17 combined ML benchmark candidate."
            )
            + " Synthetic benchmark only.",
        )

    payload = {
        "data_pack_version": "4.0",
        "double_ultra_rows": SOURCE_ROWS,
        "unique_compounds": 640,
        "unique_targets": 50,
        "best_models": best_models,
        "ranking": combined,
        "step17_results": results,
        "warning": (
            "All models use deterministic synthetic benchmark data "
            "and are not biological or clinical evidence."
        ),
    }
    benchmark_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    generated = ROOT / "reports" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / "step17_double_data_benchmark.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    pd.DataFrame(combined).to_csv(
        generated / "step17_double_data_benchmark.csv",
        index=False,
    )
    print("Step 17 double-data ML suite complete")


if __name__ == "__main__":
    main()
