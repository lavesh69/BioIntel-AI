from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.external_demo_v182 import build_demo_evidence, demo_detail_matrix, demo_qualification_matrix


def test_step182_generates_25_demo_packs(tmp_path: Path):
    result = build_demo_evidence(tmp_path)
    assert result["demo_pack_count"] == 25
    details = demo_detail_matrix(tmp_path)
    assert len(details) == 25
    assert details.demo_ready.all()
    assert not details.real_evidence.any()
    assert not details.controlled_release_eligible.any()


def test_step182_all_five_modules_are_demo_ready(tmp_path: Path):
    build_demo_evidence(tmp_path)
    summary = demo_qualification_matrix(tmp_path)
    assert len(summary) == 5
    assert summary.demo_execution_ready.all()
    assert summary.demo_packs_ready.sum() == 25
    assert summary.real_evidence_packs.sum() == 0
    assert not summary.controlled_release_eligible.any()


def test_step182_real_evidence_boundary_is_unchanged(tmp_path: Path):
    build_demo_evidence(tmp_path)
    assert not (tmp_path / "UserData" / "step181" / "evidence").exists()
    assert (tmp_path / "UserData" / "step182" / "demo_evidence").is_dir()


def test_step182_page_hooks_and_windows_scripts():
    pages = [
        "pages/141_Phenotypic_Screening_High_Content_Analysis_Lab.py",
        "pages/118_Spatial_Omics_and_Digital_Pathology_Studio.py",
        "pages/143_Protein_Language_Model_Generative_Design_Lab.py",
        "pages/183_Protein_Ligand_CoDesign_Studio.py",
        "pages/139_Strain_Resolved_Microbiome_Functional_Profiling_Studio.py",
    ]
    for rel in pages:
        text = (ROOT / rel).read_text(encoding="utf-8-sig")
        assert "render_step182_demo_evidence" in text
    for name in (
        "BUILD_STEP182_DEMO_EVIDENCE_WINDOWS.bat",
        "VERIFY_STEP182_DEMO_EVIDENCE_WINDOWS.bat",
        "LOAD_STEP182_DEMO_EVIDENCE_WINDOWS.bat",
        "DEMO_EVIDENCE_DISCLAIMER.txt",
    ):
        assert (ROOT / name).is_file()
