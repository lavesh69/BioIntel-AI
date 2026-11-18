from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from biointel.api.main import app
from biointel.reports.workspace_report import (
    build_workspace_report_html,
)
from biointel.ui.navigation import (
    PAGE_BY_KEY,
    PAGE_CATALOG,
    search_pages,
)
from biointel.ui.preferences import (
    UiPreferences,
    load_preferences,
    record_recent_page,
    save_preferences,
    toggle_favourite,
)

ROOT = Path(__file__).resolve().parents[1]


def test_navigation_catalog_has_unique_keys_and_paths() -> None:
    assert len(PAGE_CATALOG) >= 71
    assert len({page.key for page in PAGE_CATALOG}) == len(PAGE_CATALOG)
    assert len({page.path for page in PAGE_CATALOG}) == len(PAGE_CATALOG)
    assert PAGE_BY_KEY["command_center"].path.endswith("25_Command_Center.py")
    assert PAGE_BY_KEY["report_studio"].path.endswith("26_Research_Report_Studio.py")


def test_navigation_search_and_category_filter() -> None:
    results = search_pages("protein")
    keys = {page.key for page in results}
    assert "sequence_analyzer" in keys
    assert "dti_features" in keys

    modelling = search_pages(
        query="",
        category="Modelling",
    )
    assert modelling
    assert all(page.category == "Modelling" for page in modelling)


def test_favourites_rank_first_in_search() -> None:
    results = search_pages(
        query="",
        favourites={"diagnostics"},
    )
    assert results[0].key == "diagnostics"


def test_preferences_persist_and_normalise(
    tmp_path: Path,
) -> None:
    preferences = UiPreferences(
        palette="Ocean",
        font_family="Georgia",
        compact=True,
        reduce_motion=True,
        high_contrast=True,
        favourites=["command_center", "missing"],
        recent_pages=["report_studio", "missing"],
    )
    saved = save_preferences(tmp_path, preferences)
    assert saved.is_file()

    loaded = load_preferences(tmp_path)
    assert loaded.palette == "Ocean"
    assert loaded.font_family == "Georgia"
    assert loaded.compact is True
    assert loaded.reduce_motion is True
    assert loaded.high_contrast is True
    assert loaded.favourites == ["command_center"]
    assert loaded.recent_pages == ["report_studio"]


def test_invalid_theme_and_font_fall_back_to_safe_defaults(tmp_path: Path) -> None:
    save_preferences(
        tmp_path,
        UiPreferences(palette="Not a theme", font_family="Remote Font"),
    )
    loaded = load_preferences(tmp_path)
    assert loaded.palette == "Executive"
    assert loaded.font_family == "Inter"


def test_favourite_toggle_and_recent_order() -> None:
    preferences = UiPreferences()

    toggle_favourite(preferences, "command_center")
    assert preferences.favourites == ["command_center"]

    toggle_favourite(preferences, "command_center")
    assert preferences.favourites == []

    record_recent_page(preferences, "quick_start")
    record_recent_page(preferences, "report_studio")
    record_recent_page(preferences, "quick_start")
    assert preferences.recent_pages[:2] == [
        "quick_start",
        "report_studio",
    ]


def test_workspace_report_html_escapes_notes_and_title() -> None:
    report = {
        "title": "<script>alert(1)</script>",
        "generated_at_utc": "2026-07-04T00:00:00+00:00",
        "notes": "<b>unsafe note</b>",
        "workflow_status": {
            "datasets": {"total": 1},
            "models": {"total": 1},
            "experiments": {"total": 1},
        },
        "models": [],
        "datasets": [],
        "experiments": [],
        "diagnostics": {
            "summary": {"overall": "PASS"},
            "checks": [],
        },
    }

    rendered = build_workspace_report_html(report)
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "<b>unsafe note</b>" not in rendered
    assert "&lt;b&gt;unsafe note&lt;/b&gt;" in rendered


def test_step12_pages_apply_theme() -> None:
    for filename in (
        "25_Command_Center.py",
        "26_Research_Report_Studio.py",
    ):
        path = ROOT / "pages" / filename
        assert path.is_file()
        text = path.read_text(encoding="utf-8")
        assert "apply_theme()" in text
        assert "hero(" in text


def test_ui_catalog_api_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/ui/catalog")
    assert response.status_code == 200
    tools = response.json()["tools"]
    assert len(tools) == len(PAGE_CATALOG)
    assert any(tool["key"] == "command_center" for tool in tools)


def test_workflow_report_data_api_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/workflow/report-data")
    assert response.status_code == 200
    payload = response.json()
    assert "workflow_status" in payload
    assert "diagnostics" in payload


def test_windows_report_export_script_exists() -> None:
    script = ROOT / "EXPORT_WORKSPACE_REPORT_WINDOWS.bat"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "workspace-report" in text
    assert "reports\\generated" in text


def test_quick_dock_and_persistent_preferences_are_present() -> None:
    theme_source = (ROOT / "src" / "biointel" / "ui" / "theme.py").read_text(encoding="utf-8")
    assert "Quick Dock" in theme_source
    assert "persist_ui_preferences" in theme_source
    assert "ui_recent_pages" in theme_source

    appearance_source = (ROOT / "pages" / "24_Appearance_Studio.py").read_text(encoding="utf-8")
    assert "reports/ui_profiles/<profile>/preferences.json" in appearance_source
    assert "Reset to Executive defaults" in appearance_source


def test_preference_json_is_non_sensitive() -> None:
    payload = json.dumps(
        UiPreferences().__dict__,
        sort_keys=True,
    )
    assert "sequence" not in payload
    assert "smiles" not in payload
    assert "password" not in payload
