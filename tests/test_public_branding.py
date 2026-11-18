from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from biointel.ui.public_branding import (
    brand_download_payload,
    brand_public_text,
    brand_public_value,
    public_engine_key,
    public_engine_name,
)

ROOT = Path(__file__).resolve().parents[1]


def test_alias_catalog_is_complete_and_unique() -> None:
    payload = json.loads((ROOT / "config" / "public_engine_aliases.json").read_text(encoding="utf-8"))
    records = payload["records"]
    assert len(records) >= 100
    assert len({row["public_key"] for row in records}) == len(records)
    assert len({row["public_name"] for row in records}) == len(records)
    assert all(row["public_key"].startswith("BI-") for row in records)
    assert all(row["public_name"].startswith("BioIntel ") for row in records)


def test_advanced_manifest_uses_biointel_public_labels() -> None:
    payload = json.loads((ROOT / "config" / "advanced_tools_manifest.json").read_text(encoding="utf-8"))
    tools = payload["tools"]
    assert len(tools) >= 80
    assert all(row["label"].startswith("BioIntel ") for row in tools)
    assert all(row["public_label"] == row["label"] for row in tools)
    assert all(row["public_key"].startswith("BI-") for row in tools)


def test_public_identity_replaces_component_names_and_repository_urls() -> None:
    value = "Scanpy and RDKit from https://github.com/example/project are ready as external engines."
    branded = str(brand_public_text(value))
    assert "Scanpy" not in branded
    assert "RDKit" not in branded
    assert "github.com" not in branded
    assert "external engine" not in branded.casefold()
    assert branded.count("BioIntel") >= 3


def test_public_identity_preserves_internal_lookup_values() -> None:
    assert public_engine_name("scanpy").startswith("BioIntel ")
    assert public_engine_name("vina").startswith("BioIntel ")
    assert public_engine_key("scanpy").startswith("BI-")
    assert public_engine_key("vina").startswith("BI-")


def test_sensitive_dataframe_fields_are_hidden() -> None:
    frame = pd.DataFrame(
        [
            {
                "engine": "kraken2",
                "official_url": "https://github.com/example/project",
                "executable": "C:/tools/kraken2.exe",
                "status": "ready",
            }
        ]
    )
    branded = brand_public_value(frame)
    assert "BioIntel" in str(branded.loc[0, "engine"])
    assert branded.loc[0, "BioIntel official source"] == "Managed internally by BioIntel"
    assert branded.loc[0, "BioIntel runtime location"] == "Managed internally by BioIntel"


def test_legal_mode_preserves_required_attribution() -> None:
    text = "RDKit source: https://github.com/rdkit/rdkit"
    assert brand_public_text(text, allow_legal=True) == text
    notices = json.loads((ROOT / "docs" / "legal" / "THIRD_PARTY_NOTICES.json").read_text(encoding="utf-8"))
    assert len(notices["components"]) >= 70
    assert all(item["upstream_component"] for item in notices["components"])
    assert all(item["licence"] for item in notices["components"])


def test_text_downloads_are_white_labelled() -> None:
    payload = b'{"engine":"Biopython","repository":"https://github.com/example/project"}'
    branded = brand_download_payload(payload, mime="application/json")
    assert b"Biopython" not in branded
    assert b"github.com" not in branded
    assert b"BioIntel" in branded


def test_public_routes_and_setup_entrypoint_exist() -> None:
    assert (ROOT / "pages" / "277_BioIntel_Engine_Status.py").is_file()
    assert not (ROOT / "pages" / "277_External_Engines_Status.py").exists()
    assert (ROOT / "pages" / "108_BioIntel_Model_Qualification.py").is_file()
    assert not (ROOT / "pages" / "108_External_Model_Qualification.py").exists()
    assert (ROOT / "BIOINTEL_ENGINE_SETUP.bat").is_file()
