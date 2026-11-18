from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.data_packs import (  # noqa: E402
    register_bundled_data_packs,
)
from biointel.training.experiment_registry import (  # noqa: E402
    register_experiment,
)
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


def _primary_score(
    task_type: str,
    metrics: dict[str, float | None],
) -> float:
    if task_type == "classification":
        return float(metrics.get("roc_auc") or metrics.get("balanced_accuracy") or 0.0)
    rmse = metrics.get("rmse")
    return -float(rmse) if rmse is not None else -1e9


def _specs() -> list[dict[str, object]]:
    return [
        {
            "task_type": "classification",
            "model_name": "sgd_logistic",
            "filename": ("packv5_5x_classification_sgd_logistic.joblib"),
            "n_estimators": 1,
        },
        {
            "task_type": "regression",
            "model_name": "ridge",
            "filename": "packv5_5x_regression_ridge.joblib",
            "n_estimators": 1,
        },
        {
            "task_type": "regression",
            "model_name": "sgd_regression",
            "filename": "packv5_5x_regression_sgd.joblib",
            "n_estimators": 1,
        },
        {
            "task_type": "classification",
            "model_name": "extra_trees",
            "filename": ("packv5_5x_classification_extra_trees.joblib"),
            "n_estimators": 20,
        },
        {
            "task_type": "classification",
            "model_name": "random_forest",
            "filename": ("packv5_5x_classification_random_forest.joblib"),
            "n_estimators": 20,
        },
        {
            "task_type": "regression",
            "model_name": "extra_trees",
            "filename": ("packv5_5x_regression_extra_trees.joblib"),
            "n_estimators": 20,
        },
    ]


def _result_from_artifact(
    spec: dict[str, object],
) -> dict[str, object]:
    filename = str(spec["filename"])
    artifact = load_model_artifact(
        ROOT / "models" / filename,
        trusted_root=ROOT / "models",
    )
    split_summary = artifact.metadata.data_quality_summary.get(
        "split_summary",
        {},
    )
    return {
        "task_type": str(spec["task_type"]),
        "model_name": str(spec["model_name"]),
        "training_pack": "five_x_ultra",
        "source_rows": 160000,
        "filename": filename,
        "primary_score": _primary_score(
            str(spec["task_type"]),
            artifact.metadata.metrics,
        ),
        "validation_metrics": (artifact.metadata.validation_metrics),
        "test_metrics": artifact.metadata.metrics,
        "train_rows": artifact.metadata.train_rows,
        "validation_rows": (artifact.metadata.validation_rows),
        "test_rows": artifact.metadata.test_rows,
        "feature_cache": (
            artifact.metadata.data_quality_summary.get(
                "feature_cache",
                {},
            )
        ),
        "split_summary": split_summary,
        "experiment_id": artifact.metadata.experiment_id,
        "dataset_sha256": (artifact.metadata.dataset_sha256),
        "training_seconds": None,
        "reused": True,
    }


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
        random_seed=20260719,
        decision_threshold=0.5,
        threshold_strategy=("optimize_balanced" if task_type == "classification" else "fixed"),
        calibration_method="none",
        fingerprint_radius=2,
        fingerprint_bits=64,
        use_chirality=True,
        include_dipeptides=False,
        dataset_name="biointel_synthetic_5x_ultra_dti_v5",
        dataset_version="5.0",
        model_version="5.0.0-full-data",
        activity_type="SYNTHETIC_AFFINITY_SCORE",
        synthetic_demo=True,
        n_estimators=int(spec["n_estimators"]),
        tree_max_depth=18,
        tree_min_samples_leaf=12,
        tree_max_features="sqrt",
        tree_max_samples=(0.60 if model_name == "random_forest" else None),
        bootstrap_iterations=25,
        source_description=("BioIntel deterministic synthetic 5X Ultra 160,000-pair DTI benchmark"),
        conformal_alpha=0.10,
    )
    started = time.perf_counter()
    result = train_dti_model(
        dataframe,
        config,
    )
    training_seconds = time.perf_counter() - started
    output = ROOT / "models" / filename
    save_model_artifact(
        result.artifact,
        output,
    )
    register_experiment(
        ROOT / "reports" / "experiments.sqlite3",
        result.artifact,
        output.name,
    )
    split_summary = result.data_quality_summary.get(
        "split_summary",
        {},
    )
    if split_summary.get("group_overlap"):
        raise RuntimeError(f"Grouped split overlap detected for {filename}.")
    return {
        "task_type": task_type,
        "model_name": model_name,
        "training_pack": "five_x_ultra",
        "source_rows": len(dataframe),
        "filename": filename,
        "primary_score": _primary_score(
            task_type,
            result.metrics,
        ),
        "validation_metrics": result.validation_metrics,
        "test_metrics": result.metrics,
        "train_rows": result.train_rows,
        "validation_rows": result.validation_rows,
        "test_rows": result.test_rows,
        "feature_cache": (
            result.data_quality_summary.get(
                "feature_cache",
                {},
            )
        ),
        "split_summary": split_summary,
        "experiment_id": (result.artifact.metadata.experiment_id),
        "dataset_sha256": (result.artifact.metadata.dataset_sha256),
        "training_seconds": round(
            training_seconds,
            3,
        ),
        "reused": False,
    }


def _rank(
    rows: list[dict[str, object]],
) -> tuple[
    list[dict[str, object]],
    dict[str, dict[str, object]],
]:
    ranked: list[dict[str, object]] = []
    best_models: dict[str, dict[str, object]] = {}
    for task_type in ("classification", "regression"):
        task_rows = [dict(row) for row in rows if row.get("task_type") == task_type]
        task_rows.sort(
            key=lambda row: (
                -float(row.get("test_roc_auc") or 0.0)
                if task_type == "classification"
                else float(row.get("test_rmse") if row.get("test_rmse") is not None else 1e9)
            )
        )
        for rank, row in enumerate(
            task_rows,
            start=1,
        ):
            row["rank"] = rank
            row["is_best"] = rank == 1
            ranked.append(row)

        leader = task_rows[0]
        best_models[task_type] = {
            "filename": leader["filename"],
            "model_name": leader["model_name"],
            "training_pack": leader["training_pack"],
            "source_rows": leader["source_rows"],
            "test_metrics": {
                key.removeprefix("test_"): value
                for key, value in leader.items()
                if key.startswith("test_")
            },
        }
    return ranked, best_models


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        help=(
            "Train or verify one exact model filename. "
            "Benchmark finalizes automatically when all "
            "Step 19 artifacts exist."
        ),
    )
    args = parser.parse_args()

    dataframe = pd.read_csv(ROOT / "data" / "packs" / "synthetic_5x_ultra_dti_v5.csv")
    assert len(dataframe) == 160000
    assert dataframe["drug_id"].nunique() == 1000
    assert dataframe["target_id"].nunique() == 160
    assert 0.49 <= float(dataframe["label"].mean()) <= 0.51

    specs = _specs()
    if args.only and args.only not in {str(spec["filename"]) for spec in specs}:
        raise SystemExit(f"Unknown Step 19 model filename: {args.only}")

    for spec in specs:
        filename = str(spec["filename"])
        if args.only and filename != args.only:
            continue
        model_path = ROOT / "models" / filename
        if model_path.is_file():
            result = _result_from_artifact(spec)
            print(
                f"Verified existing {model_path.name}",
                flush=True,
            )
        else:
            print(
                f"Training {spec['task_type']} {spec['model_name']} on 160,000 rows",
                flush=True,
            )
            result = _train(
                dataframe,
                spec,
            )
        print(
            json.dumps(
                {
                    "filename": result["filename"],
                    "training_seconds": (result["training_seconds"]),
                    "test_metrics": result["test_metrics"],
                    "split_summary": (result["split_summary"]),
                    "feature_cache": (result["feature_cache"]),
                },
                indent=2,
                default=str,
            ),
            flush=True,
        )
        gc.collect()

    completed_specs = [
        spec for spec in specs if (ROOT / "models" / str(spec["filename"])).is_file()
    ]
    print(
        f"Step 19 artifacts complete: {len(completed_specs)}/{len(specs)}",
        flush=True,
    )
    if len(completed_specs) != len(specs):
        return

    register_bundled_data_packs(ROOT)

    results = [_result_from_artifact(spec) for spec in specs]
    benchmark_path = ROOT / "data" / "packs" / "model_benchmark_summary.json"
    existing = json.loads(benchmark_path.read_text(encoding="utf-8"))
    prior_rows = [
        dict(row)
        for row in existing.get("ranking", [])
        if not str(row.get("filename", "")).startswith("packv5_5x_")
    ]
    new_rows = [
        {
            "task_type": item["task_type"],
            "model_name": item["model_name"],
            "training_pack": item["training_pack"],
            "source_rows": item["source_rows"],
            "filename": item["filename"],
            **{f"test_{key}": value for key, value in item["test_metrics"].items()},
        }
        for item in results
    ]
    ranking, best_models = _rank(prior_rows + new_rows)

    models_directory = ROOT / "models"
    sync_model_catalog(models_directory)
    best_classifier = best_models["classification"]["filename"]
    leader_files = {value["filename"] for value in best_models.values()}
    for row in ranking:
        filename = str(row["filename"])
        if not (models_directory / filename).is_file():
            continue
        is_leader = filename in leader_files
        update_model_catalog(
            models_directory,
            filename,
            state="active" if is_leader else "candidate",
            is_default=filename == best_classifier,
            notes=("Global held-out benchmark champion." if is_leader else "Benchmark candidate.")
            + " Synthetic software benchmark only.",
        )

    payload = {
        "data_pack_version": "5.0",
        "five_x_rows": 160000,
        "unique_compounds": 1000,
        "unique_targets": 160,
        "best_models": best_models,
        "ranking": ranking,
        "step19_results": results,
        "warning": (
            "All models use deterministic synthetic "
            "benchmark data and are not biological or "
            "clinical evidence."
        ),
    }
    benchmark_path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    generated = ROOT / "reports" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / "step19_5x_ml_benchmark.json").write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    pd.DataFrame(ranking).to_csv(
        generated / "step19_5x_ml_benchmark.csv",
        index=False,
    )
    print(
        "Step 19 5X full-data ML training complete",
        flush=True,
    )


if __name__ == "__main__":
    main()
