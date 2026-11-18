from __future__ import annotations

from pathlib import Path

from biointel.ui.aesthetic import AESTHETIC_LAYER_ID, premium_aesthetic_css
from biointel.ui.style_catalog import FONTS, THEMES

ROOT = Path(__file__).resolve().parents[1]


def test_premium_aesthetic_layer_covers_core_ui_surfaces() -> None:
    css = premium_aesthetic_css(THEMES["Executive"], FONTS["Inter"])

    required_markers = (
        AESTHETIC_LAYER_ID,
        "Step 58 · premium adaptive visual system",
        ".bio-hero",
        ".bio-shell-bar",
        '[data-testid="stSidebar"]',
        '[data-testid="stMetric"]',
        '[data-testid="stFileUploaderDropzone"]',
        '[data-testid="stPlotlyChart"]',
        '[data-testid="stDataFrame"]',
        '[data-testid="stDialog"]',
        "@media (max-width: 760px)",
    )
    assert all(marker in css for marker in required_markers)


def test_premium_aesthetic_respects_motion_and_accessibility_modes() -> None:
    css = premium_aesthetic_css(
        THEMES["Clinical"],
        FONTS["Segoe UI"],
        reduce_motion=True,
        high_contrast=True,
    )

    assert "animation-duration: 0.001ms !important" in css
    assert "--bio58-border: rgba(148,163,184,.27)" in css
    assert "@keyframes bio58-hero-shift" not in css
    assert ":focus-visible" in css


def test_light_and_system_modes_keep_charts_and_overlays_readable() -> None:
    light = premium_aesthetic_css(
        THEMES["Nordic Frost"],
        FONTS["Aptos"],
        appearance_mode="Light",
    )
    system = premium_aesthetic_css(
        THEMES["Nordic Frost"],
        FONTS["Aptos"],
        appearance_mode="System",
    )

    assert "--bio58-page: #F4F7FB" in light
    assert ".js-plotly-plot .plotly text" in light
    assert '[role="listbox"]' in light
    assert "@media (prefers-color-scheme: light)" in system


def test_theme_applies_final_aesthetic_after_legacy_compatibility_styles() -> None:
    source = (ROOT / "src" / "biointel" / "ui" / "theme.py").read_text(encoding="utf-8")

    assert "from biointel.ui.aesthetic import apply_premium_aesthetic" in source
    assert source.index("apply_premium_aesthetic(") > source.index("Step 46 professional UI")
    assert source.index("apply_premium_aesthetic(") < source.index("active_key = current_page_key()")


def test_every_streamlit_screen_uses_global_theme_and_professional_hero() -> None:
    screens = [ROOT / "app.py", *sorted((ROOT / "pages").glob("*.py"))]

    assert len(screens) >= 89
    for screen in screens:
        source = screen.read_text(encoding="utf-8")
        assert "apply_theme()" in source, screen.name
        assert any(
            token in source
            for token in ("hero(", "compact_module_header(", "render_expansion_module(", "render_nextgen_module(")
        ), screen.name
