from __future__ import annotations

from pathlib import Path

from biointel.ui.appearance_engine import (
    CHART_PROFILES,
    LIGHT_THEMES,
    THEME_META,
    accessible_button_palette,
    contrast_ratio,
)
from biointel.ui.experience_themes import EXPERIENCES, experience_theme_css
from biointel.ui.style_catalog import FONTS, THEMES

ROOT = Path(__file__).resolve().parents[1]

STEP148_THEMES = {
    "Solar Helix",
    "Black Diamond",
    "Crimson Genome",
    "Electric Lime",
    "Velvet Neon",
    "Copper Eclipse",
}


def test_step148_adds_six_complete_theme_experiences_without_removal() -> None:
    assert len(THEMES) == 55
    assert len(FONTS) == 11
    assert STEP148_THEMES <= set(THEMES)
    premium_source = (ROOT / "src/biointel/ui/premium_visuals.py").read_text(encoding="utf-8")
    assert all(name in premium_source for name in STEP148_THEMES)
    assert set(THEMES) == set(LIGHT_THEMES) == set(THEME_META) == set(CHART_PROFILES) == set(EXPERIENCES)


def test_requested_yellow_black_and_red_directions_are_explicit() -> None:
    assert THEMES["Solar Helix"].primary == "#FFD60A"
    assert THEMES["Black Diamond"].bg_start == "#000000"
    assert THEMES["Crimson Genome"].primary == "#EF233C"


def test_step148_themes_have_unique_full_interface_identity() -> None:
    signatures = {
        (
            THEMES[name].primary,
            THEMES[name].secondary,
            THEMES[name].accent,
            EXPERIENCES[name].archetype,
            EXPERIENCES[name].max_width,
            EXPERIENCES[name].hero_radius,
            EXPERIENCES[name].card_radius,
            EXPERIENCES[name].pattern_css,
            EXPERIENCES[name].hero_css,
        )
        for name in STEP148_THEMES
    }
    assert len(signatures) == len(STEP148_THEMES)
    assert len({EXPERIENCES[name].archetype for name in STEP148_THEMES}) == len(STEP148_THEMES)


def test_step148_dark_and_light_primary_actions_remain_readable() -> None:
    for name in STEP148_THEMES:
        foreground, start, end = accessible_button_palette(THEMES[name])
        assert contrast_ratio(foreground, start) >= 4.5, name
        assert contrast_ratio(foreground, end) >= 4.5, name
        assert LIGHT_THEMES[name].text
        assert LIGHT_THEMES[name].border


def test_step148_css_covers_full_component_system() -> None:
    for name in STEP148_THEMES:
        css = experience_theme_css(THEMES[name])
        for token in (
            "--bio-exp-max-width",
            "--bio-exp-card-radius",
            ".bio-hero",
            ".bio-card",
            '[data-testid="stSidebar"]',
            '[data-testid="stButton"]',
            '[data-testid="stDataFrame"]',
        ):
            assert token in css, (name, token)


def test_appearance_studio_introduces_the_collection() -> None:
    source = (ROOT / "pages/24_Appearance_Studio.py").read_text(encoding="utf-8")
    assert "55 full-experience themes" in source
    assert "Step 148 creative colour collection" in source
    for name in STEP148_THEMES:
        assert name in source or name in (ROOT / "src/biointel/ui/premium_visuals.py").read_text(encoding="utf-8")
