from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.data.data_packs import verify_data_pack_integrity
from biointel.training.model_artifact import (
    clear_model_artifact_cache,
    load_model_artifact_cached,
    model_artifact_cache_info,
)
from biointel.utils.integrity_cache import verify_manifest_files
from biointel.utils.runtime_cache import (
    clear_runtime_caches,
    load_json_cached,
    read_csv_cached,
    runtime_cache_info,
)

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_json_cache_invalidates_on_signature_change(tmp_path: Path) -> None:
    clear_runtime_caches()
    path = tmp_path / "payload.json"
    path.write_text('{"value": 1}', encoding="utf-8")
    assert load_json_cached(path)["value"] == 1
    assert load_json_cached(path)["value"] == 1
    assert runtime_cache_info()["json"]["hits"] >= 1

    time.sleep(0.002)
    path.write_text('{"value": 2}', encoding="utf-8")
    assert load_json_cached(path)["value"] == 2


def test_csv_preview_cache_and_defensive_frame(tmp_path: Path) -> None:
    clear_runtime_caches()
    path = tmp_path / "data.csv"
    pd.DataFrame({"a": range(1000), "b": range(1000)}).to_csv(path, index=False)
    first = read_csv_cached(path, nrows=10)
    second = read_csv_cached(path, nrows=10)
    assert len(first) == 10
    assert len(second) == 10
    assert runtime_cache_info()["csv"]["hits"] >= 1


def test_integrity_cache_reuses_unchanged_hashes(tmp_path: Path) -> None:
    data = tmp_path / "data.txt"
    data.write_text("biointel", encoding="utf-8")
    import hashlib

    expected = hashlib.sha256(data.read_bytes()).hexdigest()
    items = [{"filename": "data.txt", "sha256": expected}]
    first = verify_manifest_files(tmp_path, items, cache_name="cache.json")
    second = verify_manifest_files(tmp_path, items, cache_name="cache.json")
    assert first["computed_hashes"] == 1
    assert second["computed_hashes"] == 0
    assert second["reused_hashes"] == 1


def test_packaged_integrity_cache_is_fast_and_valid() -> None:
    first = verify_data_pack_integrity(ROOT)
    second = verify_data_pack_integrity(ROOT)
    assert first["valid"] is True
    assert second["valid"] is True
    assert second["computed_hashes"] == 0
    assert second["reused_hashes"] == second["checked_files"]


def test_model_artifact_cache_reuses_object() -> None:
    clear_model_artifact_cache()
    path = ROOT / "models" / "packv5_5x_classification_extra_trees.joblib"
    first = load_model_artifact_cached(path, trusted_root=ROOT / "models")
    second = load_model_artifact_cached(path, trusted_root=ROOT / "models")
    assert first is second
    assert model_artifact_cache_info()["hits"] >= 1


def test_large_pages_use_lazy_preview_and_download() -> None:
    five_x = (ROOT / "pages" / "37_5X_Data_ML.py").read_text(encoding="utf-8")
    library = (ROOT / "pages" / "33_Data_Model_Library.py").read_text(encoding="utf-8")
    training = (ROOT / "pages" / "5_Model_Training.py").read_text(encoding="utf-8")
    diagnostics = (ROOT / "pages" / "19_System_Diagnostics.py").read_text(encoding="utf-8")

    assert "read_csv_cached(\n            dataset_path,\n            nrows=100" in five_x
    assert "Prepare complete 80 MB dataset download" in five_x
    assert "Prepare download —" in library
    assert "index=3" in training
    assert 'if "diagnostic_checks" not in st.session_state' in diagnostics
    assert 'st.session_state.get(\n    "diagnostic_checks",\n    run_diagnostics' not in diagnostics


def test_cache_status_api() -> None:
    response = TestClient(app).get("/system/cache-status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["invalidation"] == "path_mtime_size"
    assert {"json", "csv", "text"} <= set(payload["file_caches"])
    assert "model_cache" in payload


def test_step20_benchmark_report_exists() -> None:
    path = ROOT / "reports" / "generated" / "step20_optimization_benchmark.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["integrity"]["speedup"] > 10
    assert payload["five_x_page"]["full_rows"] == 160000
    assert payload["five_x_page"]["preview_rows"] == 100
