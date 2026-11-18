from __future__ import annotations

import json
from pathlib import Path

from biointel.ui.appearance_engine import (
    CHART_PROFILES,
    LIGHT_THEMES,
    THEME_META,
    TYPOGRAPHY_PAIRINGS,
    accessible_button_palette,
    contrast_ratio,
    font_detection_html,
    mini_theme_preview_html,
    theme_variable_override_css,
)
from biointel.ui.experience_themes import experience_theme_css
from biointel.ui.preferences import (
    UiPreferences,
    delete_named_preset,
    delete_profile,
    list_profiles,
    load_named_presets,
    load_profile_preferences,
    preferences_from_json,
    save_named_preset,
    save_profile_copy,
)
from biointel.ui.report_appearance import apply_report_appearance
from biointel.ui.style_catalog import FONTS, THEMES

ROOT = Path(__file__).resolve().parents[1]


def test_all_preserved_themes_have_unique_light_chart_and_metadata_profiles() -> None:
    assert len(THEMES) == 55
    assert len(FONTS) == 11
    assert set(LIGHT_THEMES) == set(THEMES)
    assert set(CHART_PROFILES) == set(THEMES)
    assert set(THEME_META) == set(THEMES)
    assert len(set(LIGHT_THEMES.values())) == len(THEMES)
    assert len(set(CHART_PROFILES.values())) == len(THEMES)


def test_every_primary_button_palette_meets_wcag_aa() -> None:
    for theme in THEMES.values():
        foreground, start, end = accessible_button_palette(theme)
        assert contrast_ratio(foreground, start) >= 4.5, theme.name
        assert contrast_ratio(foreground, end) >= 4.5, theme.name


def test_typography_pairings_only_use_preserved_font_catalogue() -> None:
    assert "Custom" in TYPOGRAPHY_PAIRINGS
    for pairing in TYPOGRAPHY_PAIRINGS.values():
        assert pairing.heading_font in FONTS
        assert pairing.body_font in FONTS
        assert pairing.data_font in FONTS


def test_theme_css_covers_extended_streamlit_components_and_dedicated_light_palette() -> None:
    css = experience_theme_css(THEMES["Arctic Glass"], appearance_mode="Light")
    for token in (
        '[data-testid="stSlider"]',
        '[data-testid="stToggle"]',
        '[data-testid="stFileUploaderDropzone"]',
        '[data-testid="stToast"]',
        '[data-testid="stProgress"]',
        "#F1FBFD",
        "#E4F5F8",
    ):
        assert token in css


def test_font_detection_and_mini_preview_are_browser_renderable() -> None:
    detector = font_detection_html(FONTS)
    assert "document.fonts.check" in detector
    assert "Fallback active" in detector
    preview = mini_theme_preview_html(THEMES["Deep Space"])
    assert "bio-mini-theme" in preview
    assert "Run analysis" in preview


def test_variable_override_supports_font_pairing_and_reduced_effects() -> None:
    css = theme_variable_override_css(
        THEMES["Rose"],
        heading_font=FONTS["Century Gothic"],
        body_font=FONTS["Inter"],
        data_font=FONTS["Courier New"],
        appearance_mode="Light",
        reduce_effects=True,
    )
    assert "--bio-heading-font" in css
    assert "--bio-body-font" in css
    assert "--bio-data-font" in css
    assert "backdrop-filter:none" in css
    assert "--bio-button-start" in css


def test_preference_import_and_named_presets_roundtrip(tmp_path: Path) -> None:
    preferences = UiPreferences(
        palette="Sakura Research",
        font_family="Verdana",
        heading_font_family="Trebuchet MS",
        data_font_family="Courier New",
        typography_preset="Custom",
        reduce_effects=True,
        apply_appearance_to_reports=True,
        report_style="Journal monochrome",
    )
    loaded = preferences_from_json(json.dumps(preferences.__dict__))
    assert loaded == preferences
    save_named_preset(tmp_path, "My Lab Setup", preferences)
    presets = load_named_presets(tmp_path)
    assert presets["My Lab Setup"]["palette"] == "Sakura Research"
    delete_named_preset(tmp_path, "My Lab Setup")
    assert load_named_presets(tmp_path) == {}


def test_local_profile_manager_roundtrip(tmp_path: Path) -> None:
    preferences = UiPreferences(palette="Deep Space", reduce_effects=True)
    save_profile_copy(tmp_path, "ML Engineer", preferences)
    assert "ML_Engineer" in list_profiles(tmp_path)
    loaded = load_profile_preferences(tmp_path, "ML_Engineer")
    assert loaded.palette == "Deep Space"
    delete_profile(tmp_path, "ML_Engineer")
    assert "ML_Engineer" not in list_profiles(tmp_path)


def test_report_appearance_injects_selected_theme_without_changing_evidence() -> None:
    preferences = UiPreferences(
        palette="Ocean",
        heading_font_family="Georgia",
        font_family="Aptos",
        data_font_family="Courier New",
        apply_appearance_to_reports=True,
        report_style="Executive presentation",
    )
    html = "<html><head><title>Evidence</title></head><body><p>Scientific evidence</p></body></html>"
    styled = apply_report_appearance(html, preferences)
    assert "biointel-report-appearance-v67" in styled
    assert "Scientific evidence" in styled
    assert styled.index("biointel-report-appearance-v67") < styled.index("</head>")


def test_appearance_studio_exposes_preview_import_undo_and_presets() -> None:
    source = (ROOT / "pages/24_Appearance_Studio.py").read_text(encoding="utf-8")
    for text in (
        "Preview entire studio",
        "Undo last apply",
        "Browser font availability",
        "Import preferences",
        "Named appearance presets",
        "Reduce effects",
        "Heading font",
        "Data and code font",
    ):
        assert text in source


def test_appearance_studio_renders_without_streamlit_exception() -> None:
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(ROOT / "pages/24_Appearance_Studio.py"), default_timeout=120)
    result = app.run(timeout=120)
    assert not result.exception
