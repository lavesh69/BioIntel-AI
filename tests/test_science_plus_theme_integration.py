from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_science_plus_page_uses_shared_biointel_shell() -> None:
    page = (ROOT / "pages/341_BioIntel_Science_Pulse.py").read_text(encoding="utf-8")
    assert "apply_theme()" in page
    assert page.index("apply_theme()") < page.index("render_pulse(ROOT)")
    assert 'branded_page_title("Science Plus")' in page


def test_science_plus_styles_follow_active_theme_tokens() -> None:
    source = (ROOT / "src/biointel/science_pulse/ui.py").read_text(encoding="utf-8")
    for token in (
        "var(--bio-primary)",
        "var(--bio-secondary)",
        "var(--bio-surface)",
        "var(--bio-border)",
        "var(--bio-text)",
    ):
        assert token in source
    assert "Science Plus — live scientific intelligence." in source
    assert "science-plus-command-deck" in source
    assert "NAVIGATION_GROUPS" in source
    assert '"Command": ("Overview", "Live Science News", "Trends & Intelligence")' in source
    assert '"Workspace": ("Canvas Studio", "Saved Library", "Alerts")' in source


def test_science_plus_navigation_is_grouped_and_contextual() -> None:
    source = (ROOT / "src/biointel/science_pulse/ui.py").read_text(encoding="utf-8")
    assert "Science Plus workspace family" in source
    assert "Workspace surface" in source
    assert "Workspace command deck" in source
    assert "SECTION_META" in source
    assert "Science Plus ·" in source


def test_live_news_uses_compact_status_and_structured_filters() -> None:
    news = (ROOT / "src/biointel/science_pulse/news_ui.py").read_text(encoding="utf-8")
    status_block = news.split("def _status_header", 1)[1].split("def _more_menu", 1)[0]
    filters_block = news.split("def _filters", 1)[1].split("def render_live_news", 1)[0]
    assert "science-plus-live-strip" in status_block
    assert "st.metric(" not in status_block
    assert "Search, category and advanced filters" in filters_block
    assert "Apply filters" in filters_block
    assert "Reset" in filters_block
    assert "st.pills(" not in filters_block
    assert "science-plus-filter-summary" in filters_block


def test_canvas_studio_has_active_context_and_readiness_controls() -> None:
    canvas = (ROOT / "src/biointel/science_pulse/canvas_studio.py").read_text(encoding="utf-8")
    render_canvas = canvas.split("def render_canvas_studio", 1)[1]
    assert "science-plus-canvas-context" in render_canvas
    assert "Governance readiness" in render_canvas
    assert "Canvas readiness" in render_canvas
    assert "Link evidence" in render_canvas
    assert "Review exports" in render_canvas


def test_science_plus_removes_duplicate_section_titles() -> None:
    news = (ROOT / "src/biointel/science_pulse/news_ui.py").read_text(encoding="utf-8")
    canvas = (ROOT / "src/biointel/science_pulse/canvas_studio.py").read_text(encoding="utf-8")
    render_news = news.split("def render_live_news", 1)[1]
    render_canvas = canvas.split("def render_canvas_studio", 1)[1]
    assert 'st.title("Live Science News"' not in render_news
    assert 'st.title("Science Plus Canvas Studio"' not in render_canvas


def test_stateful_segmented_controls_avoid_default_key_conflicts() -> None:
    ui = (ROOT / "src/biointel/science_pulse/ui.py").read_text(encoding="utf-8")
    canvas = (ROOT / "src/biointel/science_pulse/canvas_studio.py").read_text(encoding="utf-8")
    assert "group_default = current_group if group_key not in st.session_state else None" in ui
    assert "studio_default = studio_fallback if \"science_plus_studio_view\" not in st.session_state else None" in canvas
    assert "canvas_view_default = \"Board\" if canvas_view_key not in st.session_state else None" in canvas


def test_news_actions_and_safe_refresh_contract_are_preserved() -> None:
    news = (ROOT / "src/biointel/science_pulse/news_ui.py").read_text(encoding="utf-8")
    ui = (ROOT / "src/biointel/science_pulse/ui.py").read_text(encoding="utf-8")
    for label in ("Read Full Story", "Save", "Share", "More", "Original Source", "AI-Generated Summary"):
        assert label in news
    assert "Queue safe refresh" in news
    assert "service.test_connection" not in news + ui
