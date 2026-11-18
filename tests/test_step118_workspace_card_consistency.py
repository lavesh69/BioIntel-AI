from __future__ import annotations

import hashlib
from pathlib import Path

import biointel.ui.module_experience_2_9 as module_experience

ROOT = Path(__file__).resolve().parents[1]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_step118_version_and_renderer_state() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "13.2.0"
    source = (ROOT / "src/biointel/ui/module_experience_2_9.py").read_text(encoding="utf-8")
    assert '"version": "13.2.0"' in source
    assert 'id="biointel-module-experience-v2"' in source
    assert 'data-biointel-module-workspace="summary"' in source


def test_workspace_css_is_emitted_on_every_page_render(monkeypatch) -> None:
    rendered: list[tuple[str, bool]] = []

    def capture(body: str, *, unsafe_allow_html: bool = False, **_: object) -> None:
        rendered.append((body, unsafe_allow_html))

    monkeypatch.setattr(module_experience.st, "markdown", capture)
    module_experience._inject_css()
    module_experience._inject_css()

    assert len(rendered) == 2
    assert all(flag for _, flag in rendered)
    assert all('id="biointel-module-experience-v2"' in body for body, _ in rendered)


def test_workspace_css_has_resilient_card_layout_and_responsive_fallbacks() -> None:
    source = (ROOT / "src/biointel/ui/module_experience_2_9.py").read_text(encoding="utf-8")
    assert '_step116_module_experience_css' not in source
    assert '.mx-grid{display:grid!important' in source
    assert '.mx-card{display:block!important' in source
    assert '.mx-title{display:block!important' in source
    assert '@media(max-width:760px)' in source
    assert '@media(max-width:480px)' in source
    assert '@media(forced-colors:active)' in source


def test_all_embedded_module_pages_share_the_fixed_renderer() -> None:
    pages = []
    for path in sorted((ROOT / "pages").glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if '_render_step116_module_experience(' in text:
            pages.append(path)
            assert "from biointel.ui.module_experience_2_9 import render_module_experience" in text
    assert len(pages) == 77
    assert len(module_experience.MODULE_EXPERIENCE_CATALOG) == 78


def test_representative_pages_render_without_streamlit_exceptions() -> None:
    from streamlit.testing.v1 import AppTest

    for relative in ("pages/1_Sequence_Analyzer.py", "pages/16_Batch_Sequence_Analysis.py"):
        result = AppTest.from_file(str(ROOT / relative), default_timeout=180).run(timeout=180)
        assert not result.exception, relative
        markdown_text = "\n".join(getattr(item, "value", "") for item in result.markdown)
        assert "Interactive Scientific Workspace" in markdown_text
        assert "biointel-module-experience-v2" in markdown_text
        assert "data-biointel-module-workspace=\"summary\"" in markdown_text


def test_excluded_pages_remain_byte_identical() -> None:
    expected = {
        "pages/6_DTI_Predictor.py": "10767f9c1654df364b2321b743117f9367e24f1d17c6642ace8e378c2fedcf1a",
        "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
        "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "85e7812ef3eb05351a0ae28da1a78dc4428b23fe8e8f04e5b41c250363df996f",
        "pages/109_Lab_Instrument_Import_Center.py": "6b8b24f0549593cbe96e6baabc1929b208772d21f48e92ec4630c6835a91d73f",
        "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
    }
    for relative, digest in expected.items():
        assert _sha(ROOT / relative) == digest
