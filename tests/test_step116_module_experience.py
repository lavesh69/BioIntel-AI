from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

from biointel.ui.module_experience_2_9 import GROUP_LABELS, MODULE_EXPERIENCE_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_step116_version_navigation_and_hub() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "13.2.0"
    navigation = (ROOT / "src/biointel/ui/navigation.py").read_text(encoding="utf-8")
    assert "pages/170_Module_Experience_Canvases_2_to_9.py" in navigation
    assert "Interactive Module Experience Hub" in navigation
    assert (ROOT / "pages/170_Module_Experience_Canvases_2_to_9.py").is_file()


def test_step116_catalog_covers_sections_2_to_9() -> None:
    counts = Counter(spec.group for spec in MODULE_EXPERIENCE_CATALOG.values())
    assert len(MODULE_EXPERIENCE_CATALOG) == 78
    assert set(counts) == set(GROUP_LABELS)
    assert counts == {
        "sequence_genomics": 14,
        "pathogen_longread": 9,
        "omics_spatial": 8,
        "protein_discovery": 12,
        "analytical_imaging": 7,
        "wetlab_design": 5,
        "ai_models": 11,
        "data_evidence": 12,
    }
    assert all(spec.workflow for spec in MODULE_EXPERIENCE_CATALOG.values())
    assert all(len(spec.readiness) >= 5 for spec in MODULE_EXPERIENCE_CATALOG.values())
    assert all(len(spec.handoffs) >= 3 for spec in MODULE_EXPERIENCE_CATALOG.values())


def test_step116_all_catalog_modules_are_embedded() -> None:
    page_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in sorted((ROOT / "pages").glob("*.py"))
    )
    for key in MODULE_EXPERIENCE_CATALOG:
        assert f'_render_step116_module_experience("{key}"' in page_text, key
    assert page_text.count("STEP116_MODULE_EXPERIENCE_2_TO_9") == 77


def test_step116_renderer_is_lazy_and_avoids_eager_tabs() -> None:
    renderer = (ROOT / "src/biointel/ui/module_experience_2_9.py").read_text(encoding="utf-8")
    assert 'st.toggle("Open interactive module workspace"' in renderer
    assert "st.radio(" in renderer
    assert "st.tabs(" not in renderer
    assert "import requests" not in renderer
    assert "urllib.request" not in renderer
    assert "httpx" not in renderer
    assert '"version": "13.2.0"' in renderer


def test_step116_excluded_modules_remain_byte_identical() -> None:
    expected = {
        "pages/6_DTI_Predictor.py": "10767f9c1654df364b2321b743117f9367e24f1d17c6642ace8e378c2fedcf1a",
        "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
        "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "85e7812ef3eb05351a0ae28da1a78dc4428b23fe8e8f04e5b41c250363df996f",
        "pages/109_Lab_Instrument_Import_Center.py": "6b8b24f0549593cbe96e6baabc1929b208772d21f48e92ec4630c6835a91d73f",
        "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
    }
    for rel, digest in expected.items():
        assert _sha(ROOT / rel) == digest


def test_step116_release_policy_declares_safe_defaults() -> None:
    config = (ROOT / "config/step116_module_experience_2_9.json").read_text(encoding="utf-8")
    assert '"module_workspaces": 78' in config
    assert '"default_state": "collapsed"' in config
    assert '"network_dependency": false' in config
    assert '"canvas_type": "bounded deterministic SVG/HTML"' in config
