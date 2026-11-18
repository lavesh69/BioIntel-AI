from __future__ import annotations

import json
from pathlib import Path

from biointel.integrations import integration_catalog, integration_status_rows, integration_summary

ROOT = Path(__file__).resolve().parents[1]


def test_twenty_biointel_integration_profiles_are_registered() -> None:
    catalog = integration_catalog()
    assert len(catalog) == 20
    assert len({item.integration_id for item in catalog}) == 20
    assert len({item.public_key for item in catalog}) == 20
    assert all(item.public_name.startswith("BioIntel ") for item in catalog)
    assert all(item.target_modules for item in catalog)
    assert all(item.capabilities for item in catalog)


def test_public_status_does_not_expose_internal_probe_fields() -> None:
    rows = integration_status_rows()
    assert len(rows) == 20
    forbidden_keys = {"python_modules", "distributions", "tool_ids", "integration_id"}
    for row in rows:
        assert forbidden_keys.isdisjoint(row)
        assert row["name"].startswith("BioIntel ")
        assert row["public_key"].startswith("BI-INT-")
        assert row["state"] in {"Ready", "Setup required", "Runtime ready · assets require qualification"}


def test_summary_is_public_and_fail_safe() -> None:
    summary = integration_summary()
    assert summary["total"] == 20
    assert summary["ready"] + summary["setup_required"] == 20
    serialized = json.dumps(summary).casefold()
    assert "python_modules" not in serialized
    assert "tool_ids" not in serialized
    assert "github.com" not in serialized


def test_integration_center_and_catalog_exist() -> None:
    assert (ROOT / "config" / "biointel_scientific_integrations.json").is_file()
    assert (ROOT / "pages" / "356_BioIntel_Scientific_Integration_Center.py").is_file()
