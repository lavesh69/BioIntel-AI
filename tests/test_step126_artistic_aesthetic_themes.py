from __future__ import annotations

from pathlib import Path

from biointel.ui.appearance_engine import CHART_PROFILES, LIGHT_THEMES, THEME_META
from biointel.ui.experience_themes import EXPERIENCES, experience_theme_css
from biointel.ui.premium_visuals import premium_theme_names
from biointel.ui.style_catalog import THEMES

ROOT = Path(__file__).resolve().parents[1]

ARTISTIC_THEMES = {
    "Lavender Genome",
    "Rose Quartz Laboratory",
    "Emerald Muse",
    "Bronze Anatomy",
    "Obsidian Engineering",
    "Ink & Blueprint",
}


def test_step126_version_and_theme_catalogue() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "13.2.0"
    assert len(THEMES) == 55
    assert ARTISTIC_THEMES <= set(THEMES)
    assert ARTISTIC_THEMES <= set(premium_theme_names())
    assert set(THEMES) == set(LIGHT_THEMES) == set(THEME_META) == set(CHART_PROFILES) == set(EXPERIENCES)


def test_artistic_themes_have_unique_visual_identity() -> None:
    signatures = {
        (
            THEMES[name].primary,
            THEMES[name].secondary,
            THEMES[name].accent,
            EXPERIENCES[name].archetype,
            EXPERIENCES[name].hero_radius,
            EXPERIENCES[name].card_radius,
            EXPERIENCES[name].pattern_css,
            EXPERIENCES[name].hero_css,
        )
        for name in ARTISTIC_THEMES
    }
    assert len(signatures) == len(ARTISTIC_THEMES)
    assert len({EXPERIENCES[name].archetype for name in ARTISTIC_THEMES}) == len(ARTISTIC_THEMES)


def test_artistic_theme_css_contains_full_surface_language() -> None:
    for name in ARTISTIC_THEMES:
        css = experience_theme_css(THEMES[name])
        for token in (
            "--bio-exp-card-radius",
            "--bio-exp-control-radius",
            ".bio-hero",
            ".bio-card",
            '[data-testid="stSidebar"]',
            '[data-testid="stButton"]',
        ):
            assert token in css, (name, token)


def test_appearance_studio_exposes_step126_collection() -> None:
    source = (ROOT / "pages/24_Appearance_Studio.py").read_text(encoding="utf-8")
    assert "55 full-experience themes" in source
    assert "six Step 126 aesthetic and art directions" in source
    for name in ARTISTIC_THEMES:
        assert name in premium_theme_names()


def test_step126_configuration_declares_preservation() -> None:
    import json

    payload = json.loads((ROOT / "config/step126_artistic_theme_collection.json").read_text(encoding="utf-8"))
    assert payload["release"] == "13.2.0"
    assert set(payload["themes_added"]) == ARTISTIC_THEMES
    assert payload["preservation"]["existing_themes_preserved"] == 42
    assert payload["preservation"]["modules_removed"] == 0
    assert payload["preservation"]["scientific_features_removed"] == 0
