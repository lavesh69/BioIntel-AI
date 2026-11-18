from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.dataset_registry import register_dataset  # noqa: E402
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


def _register_data_views(
    foundation: pd.DataFrame,
    extended: pd.DataFrame,
) -> dict[str, str]:
    registry = ROOT / "reports" / "datasets.sqlite3"
    common = [
        "drug_id",
        "canonical_smiles",
        "target_id",
        "protein_sequence",
        "activity_type",
        "source",
        "data_pack_version",
    ]

    ext_cls = register_dataset(
        registry,
        extended[common + ["label"]].copy(),
        dataset_name="BioIntel Synthetic Extended DTI",
        dataset_version="2.0-classification",
        task_type="classification",
        source_description=("Deterministic synthetic benchmark generated locally by BioIntel AI"),
        activity_type="SYNTHETIC_AFFINITY_SCORE",
        notes=("Software validation only; not experimental or clinical evidence."),
        metadata={
            "compounds": int(extended["drug_id"].nunique()),
            "targets": int(extended["target_id"].nunique()),
            "balanced_label_fraction": float(extended["label"].mean()),
        },
    )
    ext_reg = register_dataset(
        registry,
        extended[common + ["p_activity"]].copy(),
        dataset_name="BioIntel Synthetic Extended DTI",
        dataset_version="2.0-regression",
        task_type="regression",
        source_description=("Deterministic synthetic benchmark generated locally by BioIntel AI"),
        activity_type="SYNTHETIC_AFFINITY_SCORE",
        notes=("Software validation only; not experimental or clinical evidence."),
        metadata={
            "compounds": int(extended["drug_id"].nunique()),
            "targets": int(extended["target_id"].nunique()),
        },
    )
    foundation_cls = register_dataset(
        registry,
        foundation[common + ["label"]].copy(),
        dataset_name="BioIntel Synthetic Foundation DTI",
        dataset_version="2.0-classification",
        task_type="classification",
        source_description=("Deterministic synthetic benchmark generated locally by BioIntel AI"),
        activity_type="SYNTHETIC_AFFINITY_SCORE",
        parent_sha256=ext_cls.dataset_sha256,
        notes="Medium-size subset for fast local retraining.",
        metadata={
            "compounds": int(foundation["drug_id"].nunique()),
            "targets": int(foundation["target_id"].nunique()),
        },
    )
    foundation_reg = register_dataset(
        registry,
        foundation[common + ["p_activity"]].copy(),
        dataset_name="BioIntel Synthetic Foundation DTI",
        dataset_version="2.0-regression",
        task_type="regression",
        source_description=("Deterministic synthetic benchmark generated locally by BioIntel AI"),
        activity_type="SYNTHETIC_AFFINITY_SCORE",
        parent_sha256=ext_reg.dataset_sha256,
        notes="Medium-size subset for fast local retraining.",
        metadata={
            "compounds": int(foundation["drug_id"].nunique()),
            "targets": int(foundation["target_id"].nunique()),
        },
    )
    return {
        "extended_classification": ext_cls.dataset_sha256,
        "extended_regression": ext_reg.dataset_sha256,
        "foundation_classification": foundation_cls.dataset_sha256,
        "foundation_regression": foundation_reg.dataset_sha256,
    }


def _primary_score(
    task_type: str,
    metrics: dict[str, float | None],
) -> float:
    if task_type == "classification":
        return float(metrics.get("roc_auc") or metrics.get("balanced_accuracy") or 0.0)
    rmse = metrics.get("rmse")
    return -float(rmse) if rmse is not None else -1e9


def _candidate_specs() -> list[dict[str, object]]:
    return [
        {
            "task_type": "classification",
            "model_name": "random_forest",
            "pack": "extended",
            "filename": ("packv2_classification_random_forest.joblib"),
            "n_estimators": 140,
        },
        {
            "task_type": "classification",
            "model_name": "logistic_regression",
            "pack": "extended",
            "filename": ("packv2_classification_logistic_regression.joblib"),
            "n_estimators": 1,
        },
        {
            "task_type": "regression",
            "model_name": "ridge",
            "pack": "extended",
            "filename": "packv2_regression_ridge.joblib",
            "n_estimators": 1,
        },
        {
            "task_type": "regression",
            "model_name": "random_forest",
            "pack": "foundation",
            "filename": ("packv2_regression_random_forest_foundation.joblib"),
            "n_estimators": 60,
        },
    ]


def _train_candidate(
    dataframe: pd.DataFrame,
    spec: dict[str, object],
) -> dict[str, object]:
    task_type = str(spec["task_type"])
    model_name = str(spec["model_name"])
    training_pack = str(spec["pack"])
    filename = str(spec["filename"])
    split_strategy = "drug_group" if task_type == "classification" else "target_group"
    config = TrainingConfig(
        task_type=task_type,
        model_name=model_name,
        split_strategy=split_strategy,
        test_fraction=0.20,
        validation_fraction=0.15,
        random_seed=20260704,
        decision_threshold=0.5,
        threshold_strategy=("optimize_balanced" if task_type == "classification" else "fixed"),
        calibration_method="none",
        fingerprint_radius=2,
        fingerprint_bits=128,
        use_chirality=True,
        include_dipeptides=False,
        dataset_name=(f"biointel_synthetic_{training_pack}_dti_v2"),
        dataset_version="2.0",
        model_version="2.0.0-data-pack",
        activity_type="SYNTHETIC_AFFINITY_SCORE",
        synthetic_demo=True,
        n_estimators=int(spec["n_estimators"]),
        bootstrap_iterations=50,
        source_description=(f"BioIntel deterministic synthetic {training_pack} DTI benchmark"),
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
        "training_pack": training_pack,
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
        "feature_cache": result.data_quality_summary.get(
            "feature_cache",
            {},
        ),
        "experiment_id": (result.artifact.metadata.experiment_id),
        "dataset_sha256": (result.artifact.metadata.dataset_sha256),
    }


def _reuse_candidate(
    spec: dict[str, object],
) -> dict[str, object]:
    filename = str(spec["filename"])
    artifact = load_model_artifact(
        ROOT / "models" / filename,
        trusted_root=ROOT / "models",
    )
    return {
        "task_type": str(spec["task_type"]),
        "model_name": str(spec["model_name"]),
        "training_pack": str(spec["pack"]),
        "source_rows": (5760 if spec["pack"] == "extended" else 1920),
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
        "experiment_id": artifact.metadata.experiment_id,
        "dataset_sha256": (artifact.metadata.dataset_sha256),
    }


def main() -> None:
    foundation = pd.read_csv(ROOT / "data" / "packs" / "synthetic_foundation_dti_v2.csv")
    extended = pd.read_csv(ROOT / "data" / "packs" / "synthetic_extended_dti_v2.csv")
    dataset_registry = _register_data_views(
        foundation,
        extended,
    )
    frames = {
        "foundation": foundation,
        "extended": extended,
    }

    results: list[dict[str, object]] = []
    for spec in _candidate_specs():
        output = ROOT / "models" / str(spec["filename"])
        if output.is_file():
            print(
                f"Reusing {output.name}",
                flush=True,
            )
            result = _reuse_candidate(spec)
        else:
            print(
                f"Training {spec['task_type']}: {spec['model_name']} on {spec['pack']}",
                flush=True,
            )
            result = _train_candidate(
                frames[str(spec["pack"])],
                spec,
            )
        results.append(result)
        print(
            json.dumps(
                {
                    "filename": result["filename"],
                    "training_pack": (result["training_pack"]),
                    "test_metrics": result["test_metrics"],
                    "feature_cache": result["feature_cache"],
                },
                indent=2,
                default=str,
            ),
            flush=True,
        )

    best: dict[str, dict[str, object]] = {}
    for task_type in ("classification", "regression"):
        best[task_type] = max(
            (item for item in results if item["task_type"] == task_type),
            key=lambda item: float(item["primary_score"]),
        )

    models_directory = ROOT / "models"
    sync_model_catalog(models_directory)
    best_classification = str(best["classification"]["filename"])
    best_regression = str(best["regression"]["filename"])
    for result in results:
        filename = str(result["filename"])
        is_best = filename in {
            best_classification,
            best_regression,
        }
        update_model_catalog(
            models_directory,
            filename,
            state="active" if is_best else "candidate",
            is_default=(filename == best_classification),
            notes=(
                "Best bundled data-pack model." if is_best else "Bundled benchmark candidate model."
            )
            + (" Synthetic benchmark only; not biological evidence."),
        )

    ranking_rows = []
    for task_type in ("classification", "regression"):
        task_results = sorted(
            (item for item in results if item["task_type"] == task_type),
            key=lambda item: float(item["primary_score"]),
            reverse=True,
        )
        for rank, item in enumerate(
            task_results,
            start=1,
        ):
            ranking_rows.append(
                {
                    "task_type": task_type,
                    "rank": rank,
                    "model_name": item["model_name"],
                    "training_pack": item["training_pack"],
                    "source_rows": item["source_rows"],
                    "filename": item["filename"],
                    "is_best": rank == 1,
                    **{f"test_{key}": value for key, value in item["test_metrics"].items()},
                }
            )

    report = {
        "data_pack_version": "2.0",
        "extended_rows": len(extended),
        "foundation_rows": len(foundation),
        "unique_compounds": int(extended["drug_id"].nunique()),
        "unique_targets": int(extended["target_id"].nunique()),
        "dataset_registry": dataset_registry,
        "best_models": best,
        "results": results,
        "warning": (
            "All bundled pack-v2 models are trained on "
            "deterministic synthetic benchmark data and "
            "have no biological or clinical validity."
        ),
    }
    generated = ROOT / "reports" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / "data_pack_model_benchmark.json").write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    pd.DataFrame(ranking_rows).to_csv(
        generated / "data_pack_model_benchmark.csv",
        index=False,
    )
    (ROOT / "data" / "packs" / "model_benchmark_summary.json").write_text(
        json.dumps(
            {
                "best_models": best,
                "ranking": ranking_rows,
                "warning": report["warning"],
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )

    print("Best classification:", best_classification)
    print("Best regression:", best_regression)


if __name__ == "__main__":
    main()
