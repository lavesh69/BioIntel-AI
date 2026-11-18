from __future__ import annotations

import tomllib
from pathlib import Path

import plotly.io as pio
import yaml
from streamlit.testing.v1 import AppTest

from biointel.ui import theme
from biointel.ui.navigation import PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def test_palettes_are_complete_and_unique() -> None:
    required_legacy = {
        "Executive",
        "Clinical",
        "Regulatory",
        "Aurora",
        "Ocean",
        "Emerald",
        "Rose",
    }
    required_new = {
        "Midnight Graphite",
        "Nordic Frost",
        "Solarized Lab",
        "Deep Space",
        "BioMatrix",
        "Royal Amethyst",
        "Ember Forge",
        "Arctic Glass",
        "Sakura Research",
        "Monochrome Pro",
    }
    assert required_legacy | required_new <= set(theme.PALETTES)
    assert sum(palette.is_new for palette in theme.PALETTES.values()) >= len(required_new)
    signatures = {
        (palette.primary, palette.secondary, palette.accent, palette.bg_start, palette.bg_end)
        for palette in theme.PALETTES.values()
    }
    assert len(signatures) == len(theme.PALETTES)
    for palette in theme.PALETTES.values():
        assert palette.primary.startswith("#")
        assert palette.secondary.startswith("#")
        assert palette.accent.startswith("#")
        assert palette.bg_start.startswith("#")
        assert palette.description


def _relative_luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first: str, second: str) -> float:
    first_luminance = _relative_luminance(first)
    second_luminance = _relative_luminance(second)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def test_theme_text_tokens_meet_accessible_contrast() -> None:
    for palette in theme.PALETTES.values():
        assert _contrast_ratio(palette.text, palette.bg_start) >= 7.0, palette.name
        assert _contrast_ratio(palette.muted, palette.bg_start) >= 4.5, palette.name


def test_font_catalog_contains_ten_new_local_first_options() -> None:
    assert len(theme.FONTS) == 11
    assert sum(font.is_new for font in theme.FONTS.values()) == 10
    assert "Inter" in theme.FONTS
    assert "Aptos" in theme.FONTS
    assert "Georgia" in theme.FONTS
    assert "Courier New" in theme.FONTS
    for font in theme.FONTS.values():
        assert font.css_stack
        assert font.plotly_family
        assert "http" not in font.css_stack.lower()


def test_theme_and_font_configuration_matches_catalog() -> None:
    payload = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    ui = payload["ui"]
    assert ui["default_palette"] == "Executive"
    assert ui["default_font"] == "Inter"
    assert ui["available_palettes"] == list(theme.PALETTES)
    assert ui["available_fonts"] == list(theme.FONTS)


def test_plotly_template_registration() -> None:
    theme._apply_plotly_template(theme.PALETTES["Aurora"], theme.FONTS["Aptos"])
    assert pio.templates.default == "biointel_step33"
    template = pio.templates["biointel_step33"]
    assert template.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert len(template.layout.colorway) >= 4


def test_hero_escapes_html(
    monkeypatch,
) -> None:
    captured: list[str] = []

    def fake_markdown(
        body: str,
        unsafe_allow_html: bool = False,
    ) -> None:
        assert unsafe_allow_html
        captured.append(body)

    monkeypatch.setattr(theme.st, "markdown", fake_markdown)
    theme.hero(
        "<script>alert(1)</script>",
        "<b>subtitle</b>",
        eyebrow="<unsafe>",
        chips=["<chip>"],
    )

    rendered = captured[0]
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "&lt;b&gt;subtitle&lt;/b&gt;" in rendered
    assert "&lt;chip&gt;" in rendered


def test_all_streamlit_screens_apply_shared_theme() -> None:
    files = [
        ROOT / "app.py",
        *sorted((ROOT / "pages").glob("*.py")),
    ]
    assert len(files) == len(PAGE_CATALOG)
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "from biointel.ui.theme import" in text, path.name
        assert "apply_theme()" in text, path.name
        assert text.index("st.set_page_config(") < text.index("apply_theme()")


def test_appearance_studio_renders_complete_theme_and_font_catalogs() -> None:
    result = AppTest.from_file(
        str(ROOT / "pages" / "24_Appearance_Studio.py"),
        default_timeout=90,
    ).run(timeout=90)
    assert not result.exception
    theme_selector = next(
        selector for selector in result.selectbox if selector.label == "Complete UI theme"
    )
    font_selectors = [selector for selector in result.selectbox if selector.label == "Text font"]
    assert len(theme_selector.options) == 55
    assert any(len(selector.options) == 11 for selector in font_selectors)


def test_streamlit_theme_configuration() -> None:
    config_path = ROOT / ".streamlit" / "config.toml"
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert payload["theme"]["primaryColor"] == "#2563EB"
    assert payload["theme"]["backgroundColor"] == "#070B16"
    assert payload["client"]["toolbarMode"] == "minimal"
    assert payload["browser"]["gatherUsageStats"] is False


def test_appearance_studio_exists() -> None:
    page = ROOT / "pages" / "24_Appearance_Studio.py"
    assert page.is_file()
    text = page.read_text(encoding="utf-8")
    assert "ui_palette" in text
    assert "ui_font_family" in text
    assert "55 full-experience themes" in text
    assert "10 new fonts" in text
    assert "Reduce motion" in text
    assert "Higher contrast" in text
