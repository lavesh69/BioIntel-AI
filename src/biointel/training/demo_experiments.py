from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from biointel.data.readiness import initialize_readiness_schema
from biointel.data.scientific_registry import initialize_scientific_registries
from biointel.database.core import transaction
from biointel.runtime_paths import runtime_database_path
from biointel.training.experiment_registry import initialize_registry


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model_metadata_files(models: Path) -> list[tuple[Path, Path, dict[str, Any]]]:
    records: list[tuple[Path, Path, dict[str, Any]]] = []
    if not models.is_dir():
        return records
    for metadata_path in sorted(models.glob("*.json")):
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        required = {
            "experiment_id",
            "trained_at_utc",
            "model_name",
            "model_version",
            "task_type",
            "dataset_name",
            "dataset_version",
            "dataset_sha256",
            "split_strategy",
            "synthetic_demo",
            "train_rows",
            "validation_rows",
            "test_rows",
            "metrics",
            "validation_metrics",
        }
        if not required.issubset(payload):
            continue
        artifact_path = metadata_path.with_suffix(".joblib")
        if not artifact_path.is_file():
            continue
        records.append((metadata_path, artifact_path, payload))
    return records


def seed_bundled_demo_experiments(root: str | Path) -> dict[str, int]:
    """Register bundled model metadata as honest, demo-only experiment history.

    The function never labels these synthetic records as scientific evidence or
    external validation. Dataset hashes are preserved exactly from the bundled
    model metadata; unresolved historical dataset references are surfaced by the
    relationship integrity registry instead of being silently remapped.
    """

    project_root = Path(root).resolve()
    registry = runtime_database_path(project_root, "experiments.sqlite3")
    initialize_registry(registry)
    initialize_scientific_registries(project_root)
    initialize_readiness_schema(project_root)
    records = _model_metadata_files(project_root / "models")
    now = _utc_now()

    counts = {
        "experiments": 0,
        "folds": 0,
        "trials": 0,
        "runtime_metrics": 0,
        "events": 0,
        "dataset_bindings": 0,
        "artifacts": 0,
        "validation_requirements": 0,
    }

    with transaction(registry) as connection:
        for metadata_path, artifact_path, payload in records:
            experiment_id = str(payload["experiment_id"])
            task_type = str(payload["task_type"])
            dataset_sha256 = str(payload["dataset_sha256"])
            metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
            validation_metrics = (
                payload.get("validation_metrics")
                if isinstance(payload.get("validation_metrics"), dict)
                else {}
            )
            enriched = dict(payload)
            enriched.update(
                {
                    "registry_seed": "bundled_model_metadata",
                    "demo_only": True,
                    "scientific_release_eligible": False,
                    "external_validation_claimed": False,
                    "source_metadata_file": f"models/{metadata_path.name}",
                    "notice": (
                        "Synthetic/demo training metadata bundled for UI and workflow demonstration. "
                        "It is not provider-retrieved scientific evidence or clinical validation."
                    ),
                }
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO experiments(
                    experiment_id,trained_at_utc,model_file,model_name,model_version,
                    task_type,dataset_name,dataset_version,dataset_sha256,split_strategy,
                    synthetic_demo,train_rows,validation_rows,test_rows,metrics_json,
                    validation_metrics_json,metadata_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    experiment_id,
                    str(payload["trained_at_utc"]),
                    artifact_path.name,
                    str(payload["model_name"]),
                    str(payload["model_version"]),
                    task_type,
                    str(payload["dataset_name"]),
                    str(payload["dataset_version"]),
                    dataset_sha256,
                    str(payload["split_strategy"]),
                    1,
                    int(payload["train_rows"]),
                    int(payload["validation_rows"]),
                    int(payload["test_rows"]),
                    json.dumps(metrics, sort_keys=True, default=str),
                    json.dumps(validation_metrics, sort_keys=True, default=str),
                    json.dumps(enriched, sort_keys=True, default=str),
                ),
            )
            counts["experiments"] += 1

            split_summary = payload.get("data_quality_summary", {}).get("split_summary", {})
            connection.execute(
                """
                INSERT OR REPLACE INTO experiment_folds(
                    experiment_id,fold_index,train_rows,validation_rows,test_rows,
                    metrics_json,validation_metrics_json,split_metadata_json,created_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    experiment_id,
                    0,
                    int(payload["train_rows"]),
                    int(payload["validation_rows"]),
                    int(payload["test_rows"]),
                    json.dumps(metrics, sort_keys=True, default=str),
                    json.dumps(validation_metrics, sort_keys=True, default=str),
                    json.dumps(
                        {
                            "demo_only": True,
                            "source": "bundled_model_metadata",
                            "split_summary": split_summary,
                        },
                        sort_keys=True,
                        default=str,
                    ),
                    now,
                ),
            )
            counts["folds"] += 1

            training_config = (
                payload.get("training_config")
                if isinstance(payload.get("training_config"), dict)
                else {}
            )
            objective_name = "balanced_accuracy" if task_type == "classification" else "rmse"
            objective_value = metrics.get(objective_name)
            trial_id = hashlib.sha256(f"{experiment_id}|bundled-trial-0".encode()).hexdigest()[:32]
            connection.execute(
                """
                INSERT OR REPLACE INTO hyperparameter_trials(
                    trial_id,experiment_id,trial_number,parameters_json,objective_name,
                    objective_value,state,duration_seconds,metadata_json,created_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    trial_id,
                    experiment_id,
                    0,
                    json.dumps(training_config, sort_keys=True, default=str),
                    objective_name,
                    float(objective_value) if isinstance(objective_value, (int, float)) else None,
                    "demo_reference",
                    None,
                    json.dumps(
                        {
                            "demo_only": True,
                            "scientific_release_eligible": False,
                            "source": "bundled_model_metadata",
                        },
                        sort_keys=True,
                    ),
                    now,
                ),
            )
            counts["trials"] += 1

            runtime_metrics = {
                "artifact_size_bytes": (float(artifact_path.stat().st_size), "bytes"),
                "train_rows": (float(payload["train_rows"]), "rows"),
                "validation_rows": (float(payload["validation_rows"]), "rows"),
                "test_rows": (float(payload["test_rows"]), "rows"),
            }
            for metric_name, (value, unit) in runtime_metrics.items():
                connection.execute(
                    """
                    INSERT OR REPLACE INTO experiment_runtime_metrics(
                        experiment_id,metric_name,metric_value,unit,hardware,created_at_utc
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (experiment_id, metric_name, value, unit, "bundled_metadata", now),
                )
                counts["runtime_metrics"] += 1

            event_id = hashlib.sha256(f"{experiment_id}|bundled-registration".encode()).hexdigest()[:32]
            connection.execute(
                """
                INSERT OR REPLACE INTO experiment_events(
                    event_id,experiment_id,event_type,message,payload_json,created_at_utc
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    event_id,
                    experiment_id,
                    "demo_metadata_registered",
                    "Bundled synthetic model metadata registered for local demonstration.",
                    json.dumps(
                        {
                            "demo_only": True,
                            "release_eligible": False,
                            "metadata_file": f"models/{metadata_path.name}",
                        },
                        sort_keys=True,
                    ),
                    now,
                ),
            )
            counts["events"] += 1

            connection.execute(
                """
                INSERT OR REPLACE INTO experiment_dataset_bindings(
                    experiment_id,dataset_sha256,binding_role,verified,verification_message,
                    created_at_utc,resolved_dataset_sha256,resolution_type
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    experiment_id,
                    dataset_sha256,
                    "training",
                    0,
                    "Historical synthetic dataset hash preserved; no silent remapping performed.",
                    now,
                    None,
                    "unresolved_historical_reference",
                ),
            )
            counts["dataset_bindings"] += 1

            artifact_sha = _sha256_file(artifact_path)
            artifact_id = hashlib.sha256(
                f"{experiment_id}|model|{artifact_path.name}|{artifact_sha}".encode()
            ).hexdigest()[:32]
            connection.execute(
                """
                INSERT OR REPLACE INTO experiment_artifacts(
                    artifact_id,experiment_id,artifact_type,relative_path,sha256,size_bytes,
                    status,metadata_json,created_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    artifact_id,
                    experiment_id,
                    "model",
                    f"models/{artifact_path.name}",
                    artifact_sha,
                    artifact_path.stat().st_size,
                    "bundled_demo",
                    json.dumps(
                        {
                            "demo_only": True,
                            "scientific_release_eligible": False,
                            "metadata_path": f"models/{metadata_path.name}",
                        },
                        sort_keys=True,
                    ),
                    now,
                ),
            )
            counts["artifacts"] += 1

            requirements = (
                (
                    "synthetic_demo_boundary",
                    "Synthetic/demo boundary",
                    "blocked",
                    "Synthetic records cannot satisfy scientific or clinical release requirements.",
                ),
                (
                    "independent_external_validation",
                    "Independent external validation",
                    "missing",
                    "No independent external validation is claimed by this bundled demo record.",
                ),
                (
                    "dataset_lineage_resolution",
                    "Dataset lineage resolution",
                    "review_required",
                    "Historical dataset hash is preserved and must be independently resolved before reuse.",
                ),
            )
            for key, label, status, message in requirements:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO experiment_validation_requirements(
                        experiment_id,requirement_key,requirement_label,status,message,
                        evidence_reference,checked_at_utc
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (experiment_id, key, label, status, message, None, now),
                )
                counts["validation_requirements"] += 1

    return counts


__all__ = ["seed_bundled_demo_experiments"]
