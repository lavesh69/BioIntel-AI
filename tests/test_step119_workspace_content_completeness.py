from __future__ import annotations

import hashlib
from pathlib import Path

import biointel.ui.module_experience_2_9 as module_experience

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TITLES = {
    "Primary canvas",
    "Focus entity",
    "Workflow coverage",
    "Readiness checks",
    "Handoff targets",
    "Evidence boundary",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_step119_version_and_release_artifacts() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "13.2.0"
    assert 'version = "13.2.0"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "13.2.0"' in (ROOT / "src/biointel/__init__.py").read_text(encoding="utf-8")
    assert (ROOT / "STEP119_RELEASE.json").exists()
    assert (ROOT / "STEP119_WORKSPACE_CONTENT_COMPLETENESS_REPORT.md").exists()
    assert (ROOT / "VERIFY_STEP119_WINDOWS.bat").exists()


def test_all_workspace_summaries_are_complete_and_module_specific() -> None:
    assert len(module_experience.MODULE_EXPERIENCE_CATALOG) == 78
    total_cards = 0
    fingerprints: set[tuple[str, ...]] = set()
    for key, spec in module_experience.MODULE_EXPERIENCE_CATALOG.items():
        cards = module_experience.workspace_summary_cards(spec)
        total_cards += len(cards)
        assert not module_experience.validate_workspace_summary(spec), key
        assert len(cards) == 6
        assert {title for title, _ in cards} == EXPECTED_TITLES
        values = {title: value for title, value in cards}
        assert values["Primary canvas"] == spec.primary_canvas
        assert values["Focus entity"] == spec.entity_type
        assert all(step in values["Workflow coverage"] for step in spec.workflow)
        assert all(target in values["Handoff targets"] for target in spec.handoffs)
        assert values["Evidence boundary"] == spec.evidence_level
        fingerprints.add(tuple(value for _, value in cards))
    assert total_cards == 468
    # Every module has a unique metadata fingerprint, rather than six repeated generic cards.
    assert len(fingerprints) == 78


def test_card_html_has_stable_diagnostic_and_accessibility_attributes() -> None:
    spec = module_experience.MODULE_EXPERIENCE_CATALOG["sequence_analyzer"]
    html = module_experience._cards(
        module_experience.workspace_summary_cards(spec),
        module_key=spec.key,
        surface="summary",
    )
    assert html.count('class="mx-card"') == 6
    assert html.count('role="group"') == 6
    assert html.count('data-biointel-card-surface="summary"') == 6
    assert 'data-biointel-card-id="sequence_analyzer-summary-01"' in html
    assert 'aria-label="Primary canvas"' in html
    assert "Sequence or ORF" in html
    assert "Sequence Comparison" in html


def test_step119_summary_schema_and_overflow_safeguards_are_present() -> None:
    source = (ROOT / "src/biointel/ui/module_experience_2_9.py").read_text(encoding="utf-8")
    assert 'data-biointel-summary-schema="v2"' in source
    assert 'data-biointel-module-key="{_safe(spec.key)}"' in source
    assert "min-width:0;height:100%;overflow:hidden" in source
    assert "white-space:normal" in source
    assert "workspace_summary_cards(spec)" in source
    assert '"version": "13.2.0"' in source


def test_all_integrated_pages_continue_to_use_one_shared_renderer() -> None:
    integrated = []
    for path in sorted((ROOT / "pages").glob("*.py")):
        source = path.read_text(encoding="utf-8", errors="ignore")
        if "_render_step116_module_experience(" in source:
            integrated.append(path)
            assert "from biointel.ui.module_experience_2_9 import render_module_experience" in source
    assert len(integrated) == 77


def test_representative_pages_render_complete_step119_summaries() -> None:
    from streamlit.testing.v1 import AppTest

    for relative in (
        "pages/1_Sequence_Analyzer.py",
        "pages/16_Batch_Sequence_Analysis.py",
        "pages/120_Bioimage_and_Microscopy_AI_Lab.py",
    ):
        result = AppTest.from_file(str(ROOT / relative), default_timeout=180).run(timeout=180)
        assert not result.exception, relative
        markdown_text = "\n".join(getattr(item, "value", "") for item in result.markdown)
        assert 'data-biointel-summary-schema="v2"' in markdown_text
        assert 'data-biointel-card-surface="summary"' in markdown_text
        assert "Focus entity" in markdown_text
        assert "Workflow coverage" in markdown_text
        assert "Handoff targets" in markdown_text


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
