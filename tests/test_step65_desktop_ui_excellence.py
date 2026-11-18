from pathlib import Path

from biointel.ui.navigation import PAGE_BY_KEY, SIDEBAR_WORK_MODES

ROOT = Path(__file__).resolve().parents[1]


def test_mobile_themes_and_fonts_preserved():
    from biointel.ui.style_catalog import FONTS, THEMES
    assert len(THEMES) >= 17
    assert len(FONTS) >= 11


def test_outcome_lanes_and_complete_navigation():
    labels = {label for _, label in SIDEBAR_WORK_MODES}
    assert "Analyse biological data" in labels
    assert "Discover compounds" in labels
    assert "Train & validate models" in labels
    assert all(key in PAGE_BY_KEY for key, _ in SIDEBAR_WORK_MODES)


def test_desktop_ux_layer_and_compact_context_present():
    theme = (ROOT / "src/biointel/ui/theme.py").read_text(encoding="utf-8")
    css = (ROOT / "src/biointel/ui/desktop_ux.css").read_text(encoding="utf-8")
    assert "bio-compact-breadcrumb" in theme
    assert "bio-workspace-context" in theme
    assert "bio-page-context{display:none" in css
    assert "for page in visible_pages:" in theme


def test_reusable_research_components_exist():
    source = (ROOT / "src/biointel/ui/components.py").read_text(encoding="utf-8")
    for name in ("scientific_table", "scientific_chart_card", "recovery_actions", "set_workspace_context", "notify"):
        assert f"def {name}(" in source
