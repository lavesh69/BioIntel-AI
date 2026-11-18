from __future__ import annotations

from pathlib import Path

from biointel.education.experience import EDUCATION_PAGES

ROOT = Path(__file__).resolve().parents[1]
HOME_DIRECT_MODULES = (
    "pages/346_BioIntel_Education_Enterprise.py",
    "pages/347_BioIntel_Virtual_Science_Lab.py",
)


def _assert_biointel_theme_bootstrap(relative: str) -> None:
    source = (ROOT / relative).read_text(encoding="utf-8")
    assert "from biointel.ui.theme import apply_theme" in source
    assert source.count("apply_theme()") == 1
    assert source.index("st.set_page_config(") < source.index("apply_theme()")


def test_every_education_home_catalog_module_uses_biointel_theme() -> None:
    assert len(EDUCATION_PAGES) == 16
    paths = [relative for _key, relative, _label, _icon in EDUCATION_PAGES]
    assert len(paths) == len(set(paths))
    for relative in paths:
        _assert_biointel_theme_bootstrap(relative)


def test_home_direct_enterprise_and_virtual_lab_modules_use_theme() -> None:
    for relative in HOME_DIRECT_MODULES:
        _assert_biointel_theme_bootstrap(relative)


def test_education_universe_theme_runs_before_renderer() -> None:
    relative = "pages/343_BioIntel_Education_Universe.py"
    source = (ROOT / relative).read_text(encoding="utf-8")
    assert source.index("apply_theme()") < source.index("render_universe(ROOT)")

