from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
THEME_PATH = ROOT / "src" / "biointel" / "ui" / "theme.py"


def test_theme_self_heals_missing_widget_state(tmp_path: Path) -> None:
    app = tmp_path / "theme_recovery_app.py"
    app.write_text(
        f'''
from pathlib import Path
import sys
import streamlit as st
ROOT = Path({str(ROOT)!r})
sys.path.insert(0, str(ROOT / "src"))
from biointel.ui.theme import apply_theme
st.set_page_config(page_title="Theme recovery")
st.session_state["ui_preferences_loaded"] = True
for key in [
    "ui_palette", "ui_font_family", "ui_compact", "ui_reduce_motion", "ui_high_contrast",
    "ui_appearance_mode", "ui_font_scale", "ui_color_vision", "ui_language",
    "ui_favourites", "ui_recent_pages", "ui_onboarding_dismissed",
]:
    if key in st.session_state:
        del st.session_state[key]
apply_theme()
st.success("theme recovered")
''',
        encoding="utf-8",
    )
    result = AppTest.from_file(str(app), default_timeout=60).run(timeout=60)
    assert not result.exception
    assert [message.value for message in result.success] == ["theme recovered"]


def test_professional_shell_css_uses_streamlit_html_injection() -> None:
    source = THEME_PATH.read_text(encoding="utf-8")
    marker = "Step 46 professional UI excellence shell"
    marker_index = source.index(marker)
    nearby = source[max(0, marker_index - 500): marker_index + 1500]
    assert "st.html(" in nearby
    assert "st.markdown(\n        \"\"\"\n        <a class=\"bio-skip-link\"" not in source


def test_reported_pages_render_without_global_theme_error() -> None:
    reported_pages = [
        "pages/25_Command_Center.py",
        "pages/5_Model_Training.py",
        "pages/68_Alignment_Phylogeny.py",
        "pages/66_Omics_Integration_Hub.py",
    ]
    for relative_path in reported_pages:
        result = AppTest.from_file(str(ROOT / relative_path), default_timeout=90).run(timeout=90)
        assert not result.exception, relative_path
