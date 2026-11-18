from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.cli import main as cli_main
from biointel.data.data_packs import (
    build_molecule_library,
    build_protein_library,
    data_library_summary,
    verify_data_pack_integrity,
    write_data_packs,
)
from biointel.data.dataset_registry import list_datasets
from biointel.dti.predictor import predict_dti_pair
from biointel.training.feature_matrix import build_feature_matrix
from biointel.training.model_artifact import load_model_artifact
from biointel.training.model_catalog import (
    default_model_path,
    sync_model_catalog,
)
from biointel.ui.navigation import PAGE_BY_KEY, PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def test_data_pack_generation_is_balanced_and_reproducible(
    tmp_path: Path,
) -> None:
    generated_root = tmp_path / "generated"
    generated = write_data_packs(generated_root)

    assert [item.rows for item in generated] == [
        1920,
        5760,
        250,
        16000,
        1000,
        32000,
        2000,
        160000,
        5000,
    ]

    packaged = data_library_summary(ROOT)["manifest"]
    packaged_hashes = {item["key"]: item["sha256"] for item in packaged["packs"]}
    assert {item.key: item.sha256 for item in generated} == packaged_hashes

    extended = pd.read_csv(generated_root / "data" / "packs" / "synthetic_extended_dti_v2.csv")
    assert len(extended) == 5760
    assert extended["drug_id"].nunique() == 240
    assert extended["target_id"].nunique() == 24
    assert 0.49 <= float(extended["label"].mean()) <= 0.51


def test_bundled_molecule_and_protein_libraries() -> None:
    molecules = build_molecule_library()
    proteins = build_protein_library()
    assert len(molecules) == 240
    assert molecules["canonical_smiles"].nunique() == 240
    assert len(proteins) == 24
    assert proteins["target_family"].nunique() == 6
    assert proteins["protein_sequence"].str.len().min() >= 220


def test_feature_matrix_uses_unique_entity_cache() -> None:
    dataframe = pd.read_csv(ROOT / "data" / "packs" / "synthetic_foundation_dti_v2.csv").head(160)
    result = build_feature_matrix(
        dataframe,
        target_column="label",
        n_bits=128,
    )
    assert result.matrix.shape[0] == 160
    assert result.cache_summary["unique_drugs"] < 160
    assert result.cache_summary["unique_targets"] < 160
    assert result.cache_summary["drug_cache_hits"] > 0
    assert result.cache_summary["protein_cache_hits"] > 0


def test_bundled_data_pack_integrity() -> None:
    result = verify_data_pack_integrity(ROOT)
    assert result["valid"] is True
    assert result["checked_files"] >= 13
    assert result["total_rows"] == 223930
    assert result["errors"] == []


def test_data_library_manifest_and_benchmark_are_complete() -> None:
    summary = data_library_summary(ROOT)
    manifest = summary["manifest"]
    benchmark = summary["benchmark"]
    assert manifest["data_pack_version"] == "5.0"
    assert len(manifest["packs"]) == 9
    assert len(benchmark["ranking"]) >= 21
    assert benchmark["best_models"]["classification"]["filename"]
    assert benchmark["best_models"]["regression"]["filename"]


def test_packv2_models_load_and_predict() -> None:
    summary = data_library_summary(ROOT)
    sample = pd.read_csv(ROOT / "data" / "packs" / "synthetic_extended_dti_v2.csv").iloc[0]

    for task_type in ("classification", "regression"):
        filename = summary["benchmark"]["best_models"][task_type]["filename"]
        artifact = load_model_artifact(
            ROOT / "models" / filename,
            trusted_root=ROOT / "models",
        )
        prediction = predict_dti_pair(
            artifact,
            str(sample["canonical_smiles"]),
            str(sample["protein_sequence"]),
        )
        assert prediction.task_type == task_type
        assert artifact.metadata.synthetic_demo is True


def test_packv2_model_catalog_and_dataset_registry() -> None:
    entries = sync_model_catalog(ROOT / "models")
    filenames = {entry.filename for entry in entries}
    assert {
        "packv2_classification_random_forest.joblib",
        "packv2_classification_logistic_regression.joblib",
        "packv2_regression_ridge.joblib",
        "packv2_regression_random_forest_foundation.joblib",
    } <= filenames
    assert default_model_path(ROOT / "models").name == "packv5_5x_classification_extra_trees.joblib"

    datasets = list_datasets(ROOT / "reports" / "datasets.sqlite3")
    pack_records = [item for item in datasets if item.dataset_name.startswith("BioIntel Synthetic")]
    assert len(pack_records) == 10


def test_step15_navigation_and_prefilled_modules() -> None:
    assert len(PAGE_CATALOG) >= 71
    page = PAGE_BY_KEY["data_library"]
    assert page.path.endswith("33_Data_Model_Library.py")

    for relative, expected in (
        (
            "pages/5_Model_Training.py",
            "Extended pack — 5,760 rows",
        ),
        (
            "pages/6_DTI_Predictor.py",
            "Bundled library example",
        ),
        (
            "pages/23_Batch_Prediction_Jobs.py",
            "Bundled 250-row sample",
        ),
        (
            "pages/13_ChEMBL_Dataset_Builder.py",
            "Starter target recipe",
        ),
    ):
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert expected in content


def test_step15_api_endpoints() -> None:
    client = TestClient(app)
    data_response = client.get("/data/packs")
    assert data_response.status_code == 200
    assert len(data_response.json()["manifest"]["packs"]) == 9

    model_response = client.get("/models/benchmark")
    assert model_response.status_code == 200
    assert len(model_response.json()["ranking"]) >= 21


def test_step15_cli_data_pack_commands(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(ROOT)

    assert cli_main(["data-pack-status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert len(status["manifest"]["packs"]) == 9
    assert status["manifest"]["data_pack_version"] == "5.0"
    assert len(status["benchmark"]["ranking"]) >= 21


def test_step15_windows_builder_exists() -> None:
    script = ROOT / "BUILD_DATA_AND_MODELS_WINDOWS.bat"
    assert script.is_file()
    content = script.read_text(encoding="utf-8")
    assert "generate_data_packs.py" in content
    assert "train_data_pack_models.py" in content
    assert "data_pack_smoke_test.py" in content


def test_chembl_starter_recipe_file() -> None:
    recipes = pd.read_csv(ROOT / "data" / "recipes" / "chembl_starter_targets.csv")
    assert {
        "CHEMBL203",
        "CHEMBL279",
        "CHEMBL1862",
        "CHEMBL240",
        "CHEMBL204",
    } == set(recipes["target_chembl_id"])
    assert recipes["manual_review_required"].all()
