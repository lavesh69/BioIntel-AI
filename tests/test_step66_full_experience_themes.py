from __future__ import annotations

from pathlib import Path

from biointel.ui.experience_themes import EXPERIENCES, experience_for, experience_theme_css
from biointel.ui.style_catalog import FONTS, THEMES

ROOT = Path(__file__).resolve().parents[1]


def test_every_palette_has_a_complete_experience_profile() -> None:
    assert set(EXPERIENCES) == set(THEMES)
    assert len(EXPERIENCES) == 55
    for name, profile in EXPERIENCES.items():
        assert profile.title
        assert profile.archetype
        assert profile.audience
        assert profile.summary
        assert profile.hero_css
        assert profile.surface_css
        assert profile.button_css
        assert profile.nav_active_css
        assert profile.pattern_css
        assert experience_for(name) is profile


def test_theme_profiles_change_structure_not_only_colour() -> None:
    structural_signatures = {
        (
            profile.max_width,
            profile.sidebar_width,
            profile.hero_radius,
            profile.card_radius,
            profile.control_radius,
            profile.shadow,
            profile.hero_css,
            profile.surface_css,
            profile.button_css,
        )
        for profile in EXPERIENCES.values()
    }
    assert len(structural_signatures) == len(EXPERIENCES)
    assert len({profile.title for profile in EXPERIENCES.values()}) == len(EXPERIENCES)
    assert len({profile.archetype for profile in EXPERIENCES.values()}) == len(EXPERIENCES)


def test_requested_professional_personality_themes_exist() -> None:
    assert experience_for("Rose").archetype == "Feminine professional"
    assert experience_for("Sakura Research").archetype == "Feminine modern"
    assert experience_for("Midnight Graphite").archetype == "Masculine professional"
    assert experience_for("Ember Forge").archetype == "Masculine industrial"
    assert experience_for("Nordic Frost").archetype == "Minimalist"
    assert experience_for("Arctic Glass").archetype == "Modern glass"
    assert experience_for("Deep Space").archetype == "Futuristic technology"


def test_experience_layer_is_desktop_only_and_changes_full_component_system() -> None:
    css = experience_theme_css(THEMES["Arctic Glass"])
    assert "@media (min-width: 761px)" in css
    for token in (
        "--bio-exp-max-width",
        "--bio-exp-sidebar-width",
        "--bio-exp-hero-radius",
        "--bio-exp-card-radius",
        "--bio-exp-control-radius",
        ".bio-hero",
        ".bio-card",
        '[data-testid="stSidebar"]',
        '[data-testid="stButton"]',
        '[data-testid="stDataFrame"]',
        '[data-baseweb="tab-list"]',
    ):
        assert token in css


def test_existing_theme_and_font_options_are_preserved() -> None:
    assert len(THEMES) == 55
    assert len(FONTS) == 11


def test_theme_layer_is_applied_after_legacy_aesthetic() -> None:
    source = (ROOT / "src/biointel/ui/theme.py").read_text(encoding="utf-8")
    assert source.index("apply_premium_aesthetic(") < source.index("experience_theme_css(")
    assert "desktop-only experience layer" in source


def test_appearance_studio_explains_full_experience_themes() -> None:
    source = (ROOT / "pages/24_Appearance_Studio.py").read_text(encoding="utf-8")
    assert "55 full-experience themes" in source
    assert "30+ distinct layout systems" in source
    assert "Experience:" in source
    assert "Designed for:" in source


def test_generated_theme_css_parses_for_every_profile() -> None:
    import tinycss2

    for palette in THEMES.values():
        css = experience_theme_css(palette)
        raw = css.split("<style", 1)[1].split(">", 1)[1].rsplit("</style>", 1)[0]
        rules = tinycss2.parse_stylesheet(raw, skip_comments=True, skip_whitespace=True)
        errors = [rule for rule in rules if getattr(rule, "type", "") == "error"]
        assert not errors, palette.name


def test_representative_experience_themes_render_without_streamlit_errors() -> None:
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages/24_Appearance_Studio.py"
    for theme_name in (
        "Nordic Frost",
        "Arctic Glass",
        "Deep Space",
        "Rose",
        "Midnight Graphite",
        "Solarized Lab",
        "BioMatrix",
        "Monochrome Pro",
    ):
        app = AppTest.from_file(str(page), default_timeout=90)
        app.session_state["ui_palette"] = theme_name
        app.session_state["ui_preferences_loaded"] = True
        result = app.run(timeout=90)
        assert not result.exception, theme_name


def test_full_experience_layer_preserves_light_and_system_appearance_modes() -> None:
    light_css = experience_theme_css(THEMES["Rose"], appearance_mode="Light")
    system_css = experience_theme_css(THEMES["Deep Space"], appearance_mode="System")
    assert "linear-gradient(145deg,#FFF5F8,#FCE8EF" in light_css
    assert "color:#4B1E31!important" in light_css
    assert "@media (prefers-color-scheme: light)" in system_css
