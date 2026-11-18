from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.cli import main as cli_main
from biointel.data.dataset_registry import (
    delete_dataset_record,
    get_dataset,
    lineage_edges,
    list_datasets,
    register_dataset,
)
from biointel.data.profiling import profile_dataframe
from biointel.dti.batch_pipeline import run_chunked_batch_prediction
from biointel.training.model_artifact import (
    load_model_artifact,
)
from biointel.training.model_catalog import (
    default_model_path,
    list_model_catalog,
    sync_model_catalog,
    update_model_catalog,
)
from biointel.utils.local_data import list_managed_files
from biointel.utils.workspace_backup import (
    create_workspace_backup,
    inspect_workspace_backup,
    restore_workspace_backup,
)

ROOT = Path(__file__).resolve().parents[1]


def test_dataset_registry_and_lineage(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "datasets.sqlite3"
    parent_frame = pd.DataFrame(
        {
            "canonical_smiles": ["CCO", "CCN"],
            "protein_sequence": ["ACDE", "ACDE"],
            "label": [1, 0],
        }
    )
    child_frame = parent_frame.copy()
    child_frame.loc[1, "label"] = 1

    parent = register_dataset(
        registry,
        parent_frame,
        dataset_name="demo",
        dataset_version="1.0",
        task_type="classification",
        source_description="unit test",
    )
    child = register_dataset(
        registry,
        child_frame,
        dataset_name="demo",
        dataset_version="2.0",
        task_type="classification",
        source_description="unit test",
        parent_sha256=parent.dataset_sha256,
    )

    records = list_datasets(registry)
    assert len(records) == 2
    assert get_dataset(registry, child.dataset_sha256) is not None

    edges = lineage_edges(registry)
    assert edges == [
        {
            "parent": parent.dataset_sha256,
            "child": child.dataset_sha256,
            "parent_known": "True",
        }
    ]

    assert delete_dataset_record(
        registry,
        child.dataset_sha256,
    )
    assert len(list_datasets(registry)) == 1


def test_dataset_profile_reports_quality_issues() -> None:
    dataframe = pd.DataFrame(
        {
            "label": [0, 0, 0, 0, 1, np.nan],
            "value": [1, 1, 1, 1, 100, 2],
        }
    )
    profile = profile_dataframe(dataframe)
    assert profile.row_count == 6
    assert profile.total_missing_values == 1
    assert profile.duplicate_rows >= 2
    assert not profile.column_profile.empty
    assert "value" in set(profile.numeric_outliers["column"])
    assert profile.warnings


def test_model_catalog_lifecycle_and_default(
    tmp_path: Path,
) -> None:
    models = tmp_path / "models"
    models.mkdir()
    first = models / "first.joblib"
    second = models / "second.joblib"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    entries = sync_model_catalog(models)
    assert len(entries) == 2
    assert all(entry.state == "candidate" for entry in entries)

    updated = update_model_catalog(
        models,
        "first.joblib",
        state="active",
        is_default=True,
        notes="primary",
    )
    assert updated.is_default
    assert updated.state == "active"
    assert default_model_path(models) == first.resolve()

    update_model_catalog(
        models,
        "second.joblib",
        state="archived",
    )
    catalog = {entry.filename: entry for entry in list_model_catalog(models)}
    assert catalog["second.joblib"].state == "archived"


def test_model_catalog_rejects_missing_file(
    tmp_path: Path,
) -> None:
    models = tmp_path / "models"
    models.mkdir()
    with pytest.raises(ValueError, match="not present"):
        update_model_catalog(
            models,
            "missing.joblib",
            state="active",
        )


def test_chunked_batch_prediction_resume(
    tmp_path: Path,
) -> None:
    model_path = ROOT / "models" / "demo_classification_model.joblib"
    artifact = load_model_artifact(
        model_path,
        trusted_root=ROOT / "models",
    )
    dataframe = pd.DataFrame(
        {
            "sample_id": ["a", "b", "c"],
            "canonical_smiles": ["CCO", "CCN", "CCC"],
            "protein_sequence": [
                "ACDEFGHIKLMNPQRSTVWY",
                "ACDEFGHIKLMNPQRSTVWY",
                "ACDEFGHIKLMNPQRSTVWY",
            ],
        }
    )
    checkpoint = tmp_path / "checkpoint.csv"

    output, summary = run_chunked_batch_prediction(
        artifact,
        dataframe,
        chunk_size=2,
        checkpoint_path=checkpoint,
    )
    assert len(output) == 3
    assert summary.processed_rows == 3
    assert checkpoint.is_file()

    resumed, resumed_summary = run_chunked_batch_prediction(
        artifact,
        dataframe,
        chunk_size=1,
        checkpoint_path=checkpoint,
        resume=True,
    )
    assert len(resumed) == 3
    assert resumed_summary.processed_rows == 3
    assert set(resumed["sample_id"].astype(str)) == {"a", "b", "c"}


def test_chunked_batch_rejects_missing_columns() -> None:
    model_path = ROOT / "models" / "demo_classification_model.joblib"
    artifact = load_model_artifact(
        model_path,
        trusted_root=ROOT / "models",
    )
    with pytest.raises(ValueError, match="Missing required columns"):
        run_chunked_batch_prediction(
            artifact,
            pd.DataFrame({"canonical_smiles": ["CCO"]}),
        )


def test_recursive_reports_are_listed_and_backed_up(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    (root / "models").mkdir(parents=True)
    nested = root / "reports" / "batch_jobs"
    nested.mkdir(parents=True)
    (root / "cache" / "external").mkdir(parents=True)
    nested_file = nested / "job.csv"
    nested_file.write_text("sample_id,prediction\n1,1\n", encoding="utf-8")

    managed = list_managed_files(root)
    assert any(item.relative_path == "reports/batch_jobs/job.csv" for item in managed)

    backup = create_workspace_backup(root)
    summary = inspect_workspace_backup(backup)
    assert "reports/batch_jobs/job.csv" in summary.files

    target = tmp_path / "target"
    (target / "models").mkdir(parents=True)
    (target / "reports").mkdir()
    restore_workspace_backup(target, backup)
    assert (target / "reports" / "batch_jobs" / "job.csv").is_file()


def test_api_catalog_and_workflow_endpoints() -> None:
    client = TestClient(app)
    for endpoint in (
        "/catalog/models",
        "/catalog/datasets",
        "/workflow/status",
    ):
        response = client.get(endpoint)
        assert response.status_code == 200

    models = client.get("/catalog/models").json()["models"]
    assert isinstance(models, list)
    status = client.get("/workflow/status").json()
    assert "models" in status
    assert "datasets" in status


def test_cli_dataset_registry_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "project"
    (root / "models").mkdir(parents=True)
    (root / "reports").mkdir()
    (root / "config").mkdir()

    dataframe = pd.DataFrame(
        {
            "canonical_smiles": ["CCO"],
            "protein_sequence": ["ACDE"],
            "label": [1],
        }
    )
    csv_path = root / "dataset.csv"
    dataframe.to_csv(csv_path, index=False)

    monkeypatch.chdir(root)
    assert (
        cli_main(
            [
                "dataset-register",
                "--csv",
                str(csv_path),
                "--name",
                "cli-demo",
                "--task",
                "classification",
            ]
        )
        == 0
    )
    register_output = json.loads(capsys.readouterr().out)
    assert register_output["dataset_name"] == "cli-demo"

    assert cli_main(["dataset-list"]) == 0
    list_output = json.loads(capsys.readouterr().out)
    assert len(list_output["datasets"]) == 1


def test_cli_model_catalog_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "project"
    models = root / "models"
    models.mkdir(parents=True)
    (root / "reports").mkdir()
    (root / "config").mkdir()
    (models / "example.joblib").write_bytes(b"example")

    monkeypatch.chdir(root)
    assert cli_main(["model-catalog"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["models"][0]["filename"] == "example.joblib"
