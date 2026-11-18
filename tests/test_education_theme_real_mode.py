from __future__ import annotations

import inspect
from pathlib import Path

from biointel.education import ui
from biointel.education.intelligence_ui import render_education_intelligence_hub

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_PAGES = {
    "pages/339_BioIntel_Education_Home.py": "render_education_home(ROOT)",
    "pages/340_BioIntel_Classroom.py": "render_classroom(ROOT)",
    "pages/342_BioIntel_Academy_and_Lecture_Studio.py": "render_academy(ROOT)",
    "pages/344_BioIntel_Examination_Command_Center.py": "render_examinations(ROOT)",
    "pages/345_BioIntel_Education_Intelligence_Hub.py": (
        "render_education_intelligence_hub(ROOT)"
    ),
}


def test_five_active_pages_apply_biointel_theme_before_rendering() -> None:
    for relative, renderer_call in ACTIVE_PAGES.items():
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "from biointel.ui.theme import apply_theme" in source
        assert source.count("apply_theme()") == 1
        assert source.index("st.set_page_config(") < source.index("apply_theme()")
        assert source.index("apply_theme()") < source.index(renderer_call)


def test_five_selected_renderers_are_production_only() -> None:
    renderers = (
        ui.render_education_home,
        ui.render_classroom,
        ui.render_academy,
        ui.render_examinations,
        render_education_intelligence_hub,
    )
    expected_contexts = (
        "education-home",
        "classroom",
        "academy",
        "examinations",
        "education-intelligence",
    )
    for renderer, page_key in zip(renderers, expected_contexts, strict=True):
        source = inspect.getsource(renderer)
        assert f'_production_only_context(platform, "{page_key}")' in source
        assert "_platform(str(root))" in source
        assert "_demo_controls" not in source
        assert "_page_platform" not in source
        assert "demo_mode" not in source


def test_selected_compatibility_aliases_resolve_to_real_renderers() -> None:
    assert ui.render_education_home_r8 is ui.render_education_home
    assert ui.render_classroom_r8 is ui.render_classroom
    assert ui.render_examinations_r8 is ui.render_examinations


def test_active_pages_expose_no_demo_entry_point() -> None:
    for relative in ACTIVE_PAGES:
        source = (ROOT / relative).read_text(encoding="utf-8").casefold()
        assert "demo" not in source
        assert "synthetic" not in source
        assert "seed_demo" not in source

