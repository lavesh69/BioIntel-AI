from __future__ import annotations

import hashlib
import json
from pathlib import Path

from biointel.ui.module_catalogue import catalogue_counts, complete_catalogue, search_catalogue
from biointel.ui.navigation import PAGE_CATALOG, catalogue_integrity, search_page_matches
from biointel.ui.preferences import PREFERENCE_VERSION, UiPreferences, preferences_from_payload
from biointel.ui.style_catalog import THEMES
from biointel.ui.theme_intelligence import (
    DENSITY_MODES,
    PERFORMANCE_MODES,
    sanitise_custom_tokens,
    theme_health,
    theme_runtime_css,
)

ROOT = Path(__file__).resolve().parents[1]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_step117_catalogue_covers_every_page_and_workspace() -> None:
    integrity = catalogue_integrity(ROOT)
    assert integrity["healthy"] is True
    assert integrity["missing_from_catalogue"] == []
    assert integrity["missing_on_disk"] == []
    counts = catalogue_counts(ROOT)
    assert counts["module_pages"] == len(PAGE_CATALOG)
    assert counts["embedded_workspaces"] == 78
    assert counts["linked_workspaces"] == 78
    assert counts["total_searchable_items"] == len(PAGE_CATALOG) + 78
    assert counts["auto_discovered_pages"] == 0


def test_step117_empty_search_returns_full_catalogue_not_ten_items() -> None:
    matches = search_page_matches("", "All")
    assert len(matches) == len(PAGE_CATALOG)
    titles = {match.page.title for match in matches}
    for expected in (
        "Complete Module Catalogue & Search",
        "Interactive Module Experience Hub",
        "Reference Database Lifecycle Manager",
        "Scientific Depth & Optimization Center",
    ):
        assert expected in titles


def test_step117_combined_search_finds_embedded_and_page_items() -> None:
    matches = search_catalogue(ROOT, "entity passport")
    assert any(match.item.item_type == "Embedded workspace" for match in matches)
    matches = search_catalogue(ROOT, "reference lifecycle")
    assert any("Reference Database Lifecycle" in match.item.title for match in matches)
    assert all(item.page_path for item in complete_catalogue(str(ROOT)) if item.item_type == "Embedded workspace")


def test_step117_theme_health_and_runtime_tokens_cover_all_themes() -> None:
    for appearance in ("Dark", "Light"):
        for name in THEMES:
            health = theme_health(name, appearance)
            assert health.body_contrast >= 4.5, (name, appearance, health.body_contrast)
            assert 0 <= health.overall <= 100
            assert 0 <= health.accessibility <= 100
    css = theme_runtime_css(
        density_mode="Dense",
        performance_mode="Performance",
        custom_tokens={"primary": "#123456", "radius": "12px", "bad": "url(evil)"},
    )
    for token in (
        "--bio-density-card-padding",
        "--bio-status-success",
        "@media(forced-colors:active)",
        "@media(min-resolution:1.5dppx)",
        "--bio-primary:#123456",
    ):
        assert token in css
    assert "url(evil)" not in css


def test_step117_preference_schema_migrates_and_sanitises() -> None:
    assert PREFERENCE_VERSION == "2.0"
    imported = preferences_from_payload(
        {
            "theme_schema_version": "2.0",
            "preferences": {
                "palette": "Executive",
                "density_mode": "Dense",
                "performance_mode": "Performance",
                "theme_favourites": ["Executive", "Not a theme"],
                "module_theme_overrides": {"sequence_analyzer": "Genomic Noir", "missing": "Ocean"},
                "custom_theme_tokens": {"primary": "#abcdef", "radius": "14px", "unsafe": "x"},
            },
        }
    )
    assert imported.density_mode == "Dense"
    assert imported.compact is True
    assert imported.performance_mode == "Performance"
    assert imported.theme_favourites == ["Executive"]
    assert imported.module_theme_overrides == {"sequence_analyzer": "Genomic Noir"}
    assert imported.custom_theme_tokens == {"primary": "#ABCDEF", "radius": "14px"}
    assert sanitise_custom_tokens({"background": "#101010", "script": "<script>"}) == {"background": "#101010"}


def test_step117_appearance_and_catalogue_pages_expose_new_controls() -> None:
    appearance = (ROOT / "pages/24_Appearance_Studio.py").read_text(encoding="utf-8")
    for marker in (
        "Theme Intelligence Studio",
        "Theme compare and health score",
        "Smart theme assistant",
        "Module Preview Lab",
        "Safe custom theme builder",
        "Project and module theme overrides",
        "Theme regression matrix",
    ):
        assert marker in appearance
    catalogue = (ROOT / "pages/171_Module_Catalogue_Search.py").read_text(encoding="utf-8")
    assert "Every BioIntel module" in catalogue
    assert "Items per page" in catalogue
    assert "Embedded workspace" in catalogue


def test_step117_excluded_modules_remain_byte_identical() -> None:
    expected = {
        "pages/6_DTI_Predictor.py": "8cf9bd3808f960fd94cf8139f5c2958e409771f310f8de8ec2f0c47d79c0abfc",
        "pages/74_DTI_Validation_Evidence_Center.py": "83413a0e72a15c823b92ee5b184805634973cd1870150c51488b5530ebcd6138",
        "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "a9414d90f056a2b008cf470c339ee178d52053722021285baf054080c08d9a96",
        "pages/109_Lab_Instrument_Import_Center.py": "3fc56e1544915062196c36511986f0e04242c08cdb0cc6ce5d7c1fe59ebc49be",
        "pages/157_Instrument_Integration_Hub_2.py": "1b4a5f9473e028571ce8464ee8beed3663be5dc8d8a0162a87bd85fae380e23c",
    }
    for relative, digest in expected.items():
        assert _sha(ROOT / relative) == digest


def test_step117_pages_render_without_streamlit_exceptions() -> None:
    from streamlit.testing.v1 import AppTest

    for relative in ("pages/24_Appearance_Studio.py", "pages/171_Module_Catalogue_Search.py", "app.py"):
        result = AppTest.from_file(str(ROOT / relative), default_timeout=180).run(timeout=180)
        assert not result.exception, relative
