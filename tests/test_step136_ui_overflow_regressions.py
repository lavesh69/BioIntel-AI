from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reactive_visual_is_css_isolated_in_iframe() -> None:
    source = (ROOT / "src/biointel/ui/reactive_scientific_workspace.py").read_text(encoding="utf-8")
    assert "st.iframe(html_block" in source
    assert "st.html(html_block" not in source


def test_data_readiness_uses_compact_summary_without_metric_columns() -> None:
    source = (ROOT / "src/biointel/ui/workbench.py").read_text(encoding="utf-8")
    section = source[source.index("def render_data_readiness"):source.index("def render_analysis_controls")]
    assert "bio-readiness-inline" in section
    assert "metric_cards(" not in section


def test_import_preview_is_open_by_default() -> None:
    for relative in ("src/biointel/expansion/renderer.py", "src/biointel/nextgen/renderer.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert 'with st.expander("Preview imported records", expanded=True):' in source


def test_shell_ratio_and_svg_guards_are_present() -> None:
    theme = (ROOT / "src/biointel/ui/theme.py").read_text(encoding="utf-8")
    css = (ROOT / "src/biointel/ui/desktop_ux.css").read_text(encoding="utf-8")
    assert "[1.00, 1.62, 1.78]" in theme
    assert "Step 136.1 UI overflow" in css
    assert "Step 136.2 visual-data visibility" in css
    assert '[data-testid="stMarkdownContainer"] h4 svg' in css
    assert '[data-testid="stPopover"]>button p' in css
