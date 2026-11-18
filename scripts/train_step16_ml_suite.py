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


def _score(
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
            "model_name": "extra_trees",
            "pack": "ultra",
            "filename": "packv3_classification_extra_trees.joblib",
            "n_estimators": 120,
        },
        {
            "task_type": "classification",
            "model_name": "sgd_logistic",
            "pack": "ultra",
            "filename": "packv3_classification_sgd_logistic.joblib",
            "n_estimators": 1,
        },
        {
            "task_type": "regression",
            "model_name": "elastic_net",
            "pack": "extended",
            "filename": "packv3_regression_elastic_net.joblib",
            "n_estimators": 1,
        },
        {
            "task_type": "regression",
            "model_name": "sgd_regression",
            "pack": "extended",
            "filename": "packv3_regression_sgd.joblib",
            "n_estimators": 1,
        },
        {
            "task_type": "regression",
            "model_name": "extra_trees",
            "pack": "foundation",
            "filename": "packv3_regression_extra_trees_foundation.joblib",
            "n_estimators": 80,
        },
    ]


def _frame(pack: str) -> pd.DataFrame:
    files = {
        "foundation": "synthetic_foundation_dti_v2.csv",
        "extended": "synthetic_extended_dti_v2.csv",
        "ultra": "synthetic_ultra_dti_v3.csv",
    }
    return pd.read_csv(ROOT / "data" / "packs" / files[pack])


def _train(spec: dict[str, object]) -> dict[str, object]:
    task_type = str(spec["task_type"])
    model_name = str(spec["model_name"])
    pack = str(spec["pack"])
    filename = str(spec["filename"])
    dataframe = _frame(pack)
    config = TrainingConfig(
        task_type=task_type,
        model_name=model_name,
        split_strategy=("drug_group" if task_type == "classification" else "target_group"),
        test_fraction=0.20,
        validation_fraction=0.15,
        random_seed=20260716,
        decision_threshold=0.5,
        threshold_strategy=("optimize_balanced" if task_type == "classification" else "fixed"),
        calibration_method="none",
        fingerprint_radius=2,
        fingerprint_bits=128,
        use_chirality=True,
        include_dipeptides=False,
        dataset_name=f"biointel_synthetic_{pack}_dti_v3",
        dataset_version="3.0",
        model_version="3.0.0-ml-suite",
        activity_type="SYNTHETIC_AFFINITY_SCORE",
        synthetic_demo=True,
        n_estimators=int(spec["n_estimators"]),
        bootstrap_iterations=40,
        source_description=(f"BioIntel deterministic synthetic {pack} DTI benchmark"),
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
        "training_pack": pack,
        "source_rows": len(dataframe),
        "filename": filename,
        "primary_score": _score(
            task_type,
            result.metrics,
        ),
        "validation_metrics": result.validation_metrics,
        "test_metrics": result.metrics,
        "train_rows": result.train_rows,
        "validation_rows": result.validation_rows,
        "test_rows": result.test_rows,
        "feature_cache": result.data_quality_summary.get(
            "feature_cache",
            {},
        ),
        "experiment_id": (result.artifact.metadata.experiment_id),
        "dataset_sha256": (result.artifact.metadata.dataset_sha256),
    }


def _reuse(spec: dict[str, object]) -> dict[str, object]:
    filename = str(spec["filename"])
    artifact = load_model_artifact(
        ROOT / "models" / filename,
        trusted_root=ROOT / "models",
    )
    rows = {
        "foundation": 1920,
        "extended": 5760,
        "ultra": 16000,
    }[str(spec["pack"])]
    return {
        "task_type": str(spec["task_type"]),
        "model_name": str(spec["model_name"]),
        "training_pack": str(spec["pack"]),
        "source_rows": rows,
        "filename": filename,
        "primary_score": _score(
            str(spec["task_type"]),
            artifact.metadata.metrics,
        ),
        "validation_metrics": (artifact.metadata.validation_metrics),
        "test_metrics": artifact.metadata.metrics,
        "train_rows": artifact.metadata.train_rows,
        "validation_rows": artifact.metadata.validation_rows,
        "test_rows": artifact.metadata.test_rows,
        "feature_cache": (
            artifact.metadata.data_quality_summary.get(
                "feature_cache",
                {},
            )
        ),
        "experiment_id": artifact.metadata.experiment_id,
        "dataset_sha256": artifact.metadata.dataset_sha256,
    }


def main() -> None:
    results: list[dict[str, object]] = []
    for spec in _specs():
        path = ROOT / "models" / str(spec["filename"])
        if path.is_file():
            result = _reuse(spec)
            print(f"Reused {path.name}", flush=True)
        else:
            print(
                f"Training {spec['task_type']} {spec['model_name']} on {spec['pack']}",
                flush=True,
            )
            result = _train(spec)
        results.append(result)
        print(
            json.dumps(
                {
                    "filename": result["filename"],
                    "metrics": result["test_metrics"],
                    "cache": result["feature_cache"],
                },
                indent=2,
                default=str,
            ),
            flush=True,
        )

    existing_path = ROOT / "data" / "packs" / "model_benchmark_summary.json"
    existing = json.loads(existing_path.read_text(encoding="utf-8"))
    prior_ranking = list(existing.get("ranking", []))
    prior_files = {str(item.get("filename")) for item in prior_ranking}

    combined_rows = prior_ranking + [
        {
            "task_type": item["task_type"],
            "model_name": item["model_name"],
            "training_pack": item["training_pack"],
            "source_rows": item["source_rows"],
            "filename": item["filename"],
            **{f"test_{key}": value for key, value in item["test_metrics"].items()},
        }
        for item in results
        if str(item["filename"]) not in prior_files
    ]

    best_models: dict[str, dict[str, object]] = {}
    for task_type in ("classification", "regression"):
        task_rows = [row for row in combined_rows if row.get("task_type") == task_type]
        if task_type == "classification":
            best_row = max(
                task_rows,
                key=lambda row: float(row.get("test_roc_auc") or 0.0),
            )
        else:
            best_row = min(
                task_rows,
                key=lambda row: float(
                    row.get("test_rmse") if row.get("test_rmse") is not None else 1e9
                ),
            )
        best_models[task_type] = {
            "filename": best_row["filename"],
            "model_name": best_row["model_name"],
            "training_pack": best_row["training_pack"],
            "source_rows": best_row["source_rows"],
            "test_metrics": {
                key.removeprefix("test_"): value
                for key, value in best_row.items()
                if key.startswith("test_")
            },
        }

    for task_type in ("classification", "regression"):
        task_rows = [row for row in combined_rows if row.get("task_type") == task_type]
        task_rows.sort(
            key=lambda row: (
                -float(row.get("test_roc_auc") or 0.0)
                if task_type == "classification"
                else float(row.get("test_rmse") if row.get("test_rmse") is not None else 1e9)
            )
        )
        for rank, row in enumerate(task_rows, start=1):
            row["rank"] = rank
            row["is_best"] = row["filename"] == best_models[task_type]["filename"]

    models = ROOT / "models"
    sync_model_catalog(models)
    best_classifier = best_models["classification"]["filename"]
    for row in combined_rows:
        filename = str(row["filename"])
        if not (models / filename).is_file():
            continue
        is_best = any(filename == item["filename"] for item in best_models.values())
        update_model_catalog(
            models,
            filename,
            state="active" if is_best else "candidate",
            is_default=filename == best_classifier,
            notes=("Step 16 benchmark champion." if is_best else "Step 16 ML benchmark candidate.")
            + " Synthetic benchmark only.",
        )

    payload = {
        "data_pack_version": "3.0",
        "ultra_rows": 16000,
        "unique_compounds": 400,
        "unique_targets": 40,
        "best_models": best_models,
        "ranking": combined_rows,
        "step16_results": results,
        "warning": (
            "All models use deterministic synthetic benchmark "
            "data and are not biological or clinical evidence."
        ),
    }
    existing_path.write_text(
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
    (generated / "step16_ml_suite_benchmark.json").write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    pd.DataFrame(combined_rows).to_csv(
        generated / "step16_ml_suite_benchmark.csv",
        index=False,
    )
    print("Step 16 ML suite training complete")


if __name__ == "__main__":
    main()
