from __future__ import annotations

import json
from pathlib import Path

import pytest

from biointel.science_pulse.canvas_studio import (
    CANVAS_SCHEMA_VERSION,
    SciencePlusCanvasStore,
    TEMPLATES,
    TEMPLATE_CATEGORIES,
    workspace_markdown,
    workspace_validation,
)
from biointel.science_pulse.ui import PRIMARY_NAVIGATION


def test_canvas_template_catalog_is_complete_and_unique() -> None:
    assert len(TEMPLATES) == 35
    assert len({template.key for template in TEMPLATES}) == len(TEMPLATES)
    assert len({template.title for template in TEMPLATES}) == len(TEMPLATES)
    assert set(TEMPLATE_CATEGORIES) == {
        "Core Research",
        "Evidence & Literature",
        "Omics & Genomics",
        "Molecular & Drug Discovery",
        "Clinical & Regulatory",
        "Public Health & Ecology",
        "Publishing & Communication",
        "Intelligence & Operations",
    }
    for template in TEMPLATES:
        assert template.columns
        assert template.starter_cards
        assert template.workflow
        assert all(card["column"] in template.columns for card in template.starter_cards)
        assert all(card["status"] == "Prompt" for card in template.starter_cards)
        assert all(not card["notes"] for card in template.starter_cards)


def test_canvas_store_is_local_scoped_atomic_and_exportable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path / "user-data"))
    store = SciencePlusCanvasStore(tmp_path, tenant_id="Institution A", user_id="Researcher/1")
    created = store.create("systematic-review")

    assert created["schema_version"] == CANVAS_SCHEMA_VERSION
    assert created["template_key"] == "systematic-review"
    assert store.load(created["canvas_id"]) == created
    assert store.base.is_relative_to(tmp_path / "user-data")
    assert not list(store.base.glob("*.tmp"))

    created["objective"] = "Assess source-linked evidence for a bounded review question."
    created["cards"][0]["notes"] = "Protocol drafted; registration identifier pending."
    saved = store.save(created)
    assert saved["objective"].startswith("Assess source-linked")

    markdown = workspace_markdown(saved)
    assert "# Systematic Review / PRISMA Canvas" in markdown
    assert "## Protocol" in markdown
    assert "Scientific interpretation requires domain review" in markdown

    duplicate = store.duplicate(saved["canvas_id"])
    assert duplicate["canvas_id"] != saved["canvas_id"]
    assert duplicate["title"].endswith("— Copy")
    assert len(store.list()) == 2

    package = json.loads((store.base / f"{saved['canvas_id']}.json").read_text(encoding="utf-8"))
    assert package["schema_version"] == CANVAS_SCHEMA_VERSION
    store.delete(saved["canvas_id"])
    assert store.load(saved["canvas_id"]) is None


def test_canvas_store_rejects_path_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIOINTEL_USER_DATA_DIR", str(tmp_path / "user-data"))
    store = SciencePlusCanvasStore(tmp_path, tenant_id="local", user_id="user")
    with pytest.raises(ValueError, match="Invalid canvas identifier"):
        store.load("../outside")


def test_readiness_checks_are_truthful() -> None:
    workspace = {
        "objective": "",
        "cards": [
            {"status": "Blocked", "evidence_ids": []},
            {"status": "Complete", "evidence_ids": ["spi-1"]},
        ],
    }
    checks = {row["Check"]: row for row in workspace_validation(workspace)}
    assert checks["Objective"]["State"] == "Needs attention"
    assert checks["Evidence linkage"]["Detail"].startswith("1 card")
    assert checks["Open blockers"]["State"] == "Needs attention"


def test_canvas_studio_is_part_of_science_plus_navigation() -> None:
    assert "Canvas Studio" in PRIMARY_NAVIGATION
    assert PRIMARY_NAVIGATION.index("Canvas Studio") < PRIMARY_NAVIGATION.index("Trends & Intelligence")
