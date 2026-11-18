from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.training.experiment_registry import register_experiment  # noqa: E402
from biointel.training.model_artifact import save_model_artifact  # noqa: E402
from biointel.training.model_catalog import (  # noqa: E402
    default_model_path,
    sync_model_catalog,
    update_model_catalog,
)
from biointel.training.trainers import TrainingConfig, train_dti_model  # noqa: E402


def train(task_type: str) -> None:
    dataset = pd.read_csv(ROOT / "data" / "examples" / "synthetic_dti_demo.csv")
    config = TrainingConfig(
        task_type=task_type,
        model_name="random_forest",
        split_strategy="random_pair",
        test_fraction=0.25,
        random_seed=42,
        fingerprint_bits=256,
        include_dipeptides=False,
        dataset_name="synthetic_dti_demo",
        dataset_version="1.0",
        model_version="1.0.0-demo",
        activity_type="SYNTHETIC_SCORE" if task_type == "regression" else None,
        synthetic_demo=True,
        n_estimators=80,
    )
    result = train_dti_model(dataset, config)
    output = ROOT / "models" / f"demo_{task_type}_model.joblib"
    save_model_artifact(result.artifact, output)
    register_experiment(
        ROOT / "reports" / "experiments.sqlite3",
        result.artifact,
        output.name,
    )
    sync_model_catalog(ROOT / "models")
    make_default = default_model_path(ROOT / "models") is None
    update_model_catalog(
        ROOT / "models",
        output.name,
        state="active" if make_default else "candidate",
        is_default=make_default,
        notes="Bundled synthetic demonstration model.",
    )
    print(f"Saved {task_type} demo model to {output}")
    print(result.metrics)


def main() -> None:
    train("classification")
    train("regression")


if __name__ == "__main__":
    main()
