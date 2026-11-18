from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_real_data_catalog_is_complete_and_checksum_bound() -> None:
    catalog = json.loads(
        (ROOT / "data/real_scientific_pack/catalog.json").read_text(encoding="utf-8")
    )
    assert catalog["software_version"] == "8.2.6"
    assert catalog["dataset_count"] == 14
    assert len(catalog["datasets"]) == 14
    for dataset in catalog["datasets"]:
        assert dataset["provider"] and dataset["release"]
        assert dataset["licence"] and dataset["scope"]
        assert dataset["modules"] and dataset["file_metadata"]
        assert dataset["scientific_release_eligible"] is False
        for metadata in dataset["file_metadata"]:
            path = ROOT / metadata["path"]
            assert path.is_file()
            assert path.stat().st_size == metadata["size_bytes"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == metadata["sha256"]


def test_only_wdbc_is_training_eligible() -> None:
    catalog = json.loads(
        (ROOT / "data/real_scientific_pack/catalog.json").read_text(encoding="utf-8")
    )
    eligible = [item["id"] for item in catalog["datasets"] if item["training_eligible"]]
    assert eligible == ["uci_wdbc"]


def test_registry_contains_all_real_public_datasets() -> None:
    catalog = json.loads(
        (ROOT / "data/real_scientific_pack/catalog.json").read_text(encoding="utf-8")
    )
    with sqlite3.connect(ROOT / "reports/datasets.sqlite3") as connection:
        rows = connection.execute("SELECT metadata_json FROM datasets").fetchall()
    real_records = [
        json.loads(row[0] or "{}")
        for row in rows
        if json.loads(row[0] or "{}").get("real_public_data")
    ]
    assert len(real_records) == len(catalog["datasets"])
    assert all(
        item.get("scientific_release_eligible") is False for item in real_records
    )


def test_ui_exposes_separate_verified_real_data_panel() -> None:
    source = (ROOT / "src/biointel/ui/starter_kits.py").read_text(encoding="utf-8")
    assert "Verified Real Public Data" in source
    assert "real_scientific_pack" in source
    assert "constitute clinical validation" in source
