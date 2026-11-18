from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from biointel.ui.navigation import CATEGORIES, CATEGORY_META, PAGE_BY_KEY, PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def test_step46_category_metadata_covers_every_domain() -> None:
    assert set(CATEGORY_META) == set(CATEGORIES)
    assert all(icon.strip() and description.strip() for icon, description in CATEGORY_META.values())


def test_step46_global_design_contract_is_present() -> None:
    theme = (ROOT / "src" / "biointel" / "ui" / "theme.py").read_text(encoding="utf-8")
    required = (
        "Step 46 professional UI excellence shell",
        "bio-skip-link",
        "focus-visible",
        "prefers-color-scheme: light",
        "Find modules",
        "Pinned & recent",
        "_bio_pin_",
        "Typo-tolerant matching is enabled",
    )
    assert all(token in theme for token in required)


def test_step46_all_registered_streamlit_pages_use_the_shared_design_system() -> None:
    for page in PAGE_CATALOG:
        source = (ROOT / page.path).read_text(encoding="utf-8")
        assert "apply_theme()" in source, page.path
        assert any(
            token in source
            for token in ("hero(", "compact_module_header(", "render_expansion_module(", "render_nextgen_module(")
        ), page.path


def test_step46_catalogue_is_unique_and_task_searchable() -> None:
    assert len(PAGE_CATALOG) >= 89
    assert len({page.key for page in PAGE_CATALOG}) == len(PAGE_CATALOG)
    assert len({page.path for page in PAGE_CATALOG}) == len(PAGE_CATALOG)
    assert all(page.key in PAGE_BY_KEY for page in PAGE_CATALOG)
    assert all(page.description.strip() and page.keywords for page in PAGE_CATALOG)


def test_step46_representative_pages_render_without_streamlit_exceptions() -> None:
    for source in (
        "app.py",
        "pages/70_BioIntel_Studio.py",
        "pages/1_Sequence_Analyzer.py",
        "pages/71_Platform_Quality_Center.py",
    ):
        app = AppTest.from_file(str(ROOT / source), default_timeout=120).run()
        assert not app.exception, source
        assert len(app.markdown) > 0, source
