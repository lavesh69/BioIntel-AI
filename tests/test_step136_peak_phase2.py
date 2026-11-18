from __future__ import annotations

from pathlib import Path

import pandas as pd

from biointel.peak_potential.workflow import (
    interpretation_summary,
    performance_profile,
    requirements_for,
    workflow_stage_rows,
)
from biointel.ui.performance import bounded_frame_for_display, frame_fingerprint

ROOT = Path(__file__).resolve().parents[1]


def test_eight_stage_workflow_and_interpretation_are_deterministic() -> None:
    frame_audits = {"results": {"blockers": [], "warnings": ["Review batch effect"]}}
    visual_audits = {"main": {"has_data": True}}
    rows = workflow_stage_rows(
        upload_profile={"sha256": "abc"},
        run_manifest={"status": "completed", "completed_at_utc": "2026-07-12T00:00:00Z"},
        frame_audits=frame_audits,
        visual_audits=visual_audits,
        export_prepared=True,
    )
    assert [row["Stage"] for row in rows] == [
        "Input", "Validation", "Configuration", "Run", "Results", "Interpretation", "Evidence", "Export"
    ]
    assert all(row["Status"] == "Complete" for row in rows)
    requirements = requirements_for("dti_predictor", "BioIntel Discovery")
    result = interpretation_summary(
        title="DTI Predictor",
        domain="BioIntel Discovery",
        run_manifest={"status": "completed"},
        frame_audits=frame_audits,
        visual_audits=visual_audits,
        requirements=requirements,
    )
    assert result["finding"]
    assert result["confidence"].startswith("Moderate")
    assert result["recommended_next_actions"]
    assert len(result["interpretation_sha256"]) == 64


def test_domain_capability_contracts_cover_requested_scientific_areas() -> None:
    expected = {
        "fastq_genomics_qc": ("BioIntel Genomics & Bioinformatics", "Per-cycle quality"),
        "variant_annotation": ("BioIntel Genomics & Bioinformatics", "Chromosome"),
        "transcriptomics_expression": ("BioIntel Omics & Next-Generation Biology", "Normalization"),
        "single_cell_heterogeneity": ("BioIntel Omics & Next-Generation Biology", "pseudobulk"),
        "rare_disease_board": ("BioIntel Genomics & Bioinformatics", "HPO"),
        "dti_predictor": ("BioIntel Discovery", "Cold-drug"),
        "structural_bioinformatics": ("BioIntel Discovery", "Chains"),
        "admet_discovery": ("BioIntel Discovery", "Batch structure"),
        "protein_design_lab": ("BioIntel Discovery", "Epistasis"),
        "multiomics_biomarker": ("BioIntel Omics & Next-Generation Biology", "Nested evaluation"),
        "digital_pathology_foundation": ("BioIntel Omics & Next-Generation Biology", "stain"),
        "spatial_medicine_tme": ("BioIntel Omics & Next-Generation Biology", "neighbourhood"),
        "long_read_epigenome": ("BioIntel Omics & Next-Generation Biology", "haplotype"),
        "wetlab_biotechnology": ("BioIntel Lab", "LLOQ"),
        "gene_therapy_vector": ("Therapy & Translational", "tropism"),
        "cell_therapy_cart": ("Therapy & Translational", "off-tumour"),
        "clinical_biomarker_survival": ("Therapy & Translational", "Survival"),
        "synthetic_cohort_trial": ("Therapy & Translational", "Simulation"),
    }
    for key, (domain, phrase) in expected.items():
        text = " ".join(item.requirement for item in requirements_for(key, domain)).lower()
        assert phrase.lower() in text, (key, phrase, text)
        assert performance_profile(key, domain)["cache_invalidation"].startswith("input checksum")


def test_large_table_display_is_bounded_without_first_chunk_bias() -> None:
    frame = pd.DataFrame({"row": range(100_000), "value": range(100_000)})
    display, profile = bounded_frame_for_display(frame, max_rows=1000, max_cells=2000)
    assert len(display) == 1000
    assert display.iloc[0]["row"] == 0
    assert display.iloc[-1]["row"] == 99_999
    assert profile["sampled"] is True
    assert frame_fingerprint(frame) == frame_fingerprint(frame.copy())


def test_home_and_shell_use_branded_icons_without_page_emoji_arguments() -> None:
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    theme = (ROOT / "src/biointel/ui/theme.py").read_text(encoding="utf-8")
    workbench = (ROOT / "src/biointel/ui/workbench.py").read_text(encoding="utf-8")
    css = (ROOT / "src/biointel/ui/desktop_ux.css").read_text(encoding="utf-8")
    assert 'page_icon=str(ROOT / "assets" / "brand" / "biointel-icon-256.png")' in app
    assert "icon=page.icon" not in app
    assert "icon=page.icon" not in theme
    assert "svg_icon_html(title=title, hint=icon" in theme
    assert "bio-wb-header-svg" in workbench
    assert "bio-section-svg" in css
    assert "white-space:nowrap" in css
    # Protected scientific pages remain byte-identical; the runtime adapter strips
    # legacy page-link emoji arguments without mutating those qualified sources.
    assert "_install_branded_page_link_adapter" in theme
    assert 'kwargs.pop("icon", None)' in theme
    protected = {Path("pages/74_DTI_Validation_Evidence_Center.py")}
    offenders = []
    for candidate in [ROOT / "app.py", *sorted((ROOT / "pages").glob("*.py")), *sorted((ROOT / "src/biointel").rglob("*.py"))]:
        relative = candidate.relative_to(ROOT)
        if relative in protected:
            continue
        text = candidate.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if "st.page_link" in line and "icon=" in line:
                offenders.append(f"{relative}:{line_number}")
    assert not offenders


def test_evidence_exports_are_on_demand_and_bounded() -> None:
    peak_ui = (ROOT / "src/biointel/peak_potential/ui.py").read_text(encoding="utf-8")
    workbench = (ROOT / "src/biointel/ui/workbench.py").read_text(encoding="utf-8")
    assert "Prepare assurance bundle" in peak_ui
    assert "Prepare evidence shell" in peak_ui
    assert "Prepare complete ZIP" in workbench
    assert "max_rows_per_table: int = 100_000" in workbench
    assert 'archive.writestr("bundle_index.json"' in workbench


def test_requested_module_sources_contain_peak_features() -> None:
    checks = {
        "pages/56_FASTQ_Genomics_QC.py": ("Per-cycle GC percentage", "Synchronized quality and adapter trimming"),
        "pages/57_Variant_Annotation_Workbench.py": ("genotype_matrix", "Variants by chromosome"),
        "pages/59_Transcriptomics_Expression_Lab.py": ("Sample PCA", "minus_log10_fdr"),
        "pages/80_Single_Cell_Heterogeneity.py": ("simulated_doublet_scores", "pseudobulk_expression", "trajectory_screen"),
        "pages/100_Rare_Disease_Genome_Interpretation.py": ("HPO terms", "ACMG boundary"),
        "pages/6_DTI_Predictor.py": ("applicability_status", "conformal uncertainty"),
        "pages/61_Structural_Bioinformatics.py": ("3D structure display options", "Download interactive 3D view"),
        "pages/62_ADMET_Drug_Discovery.py": ("Batch screening", "applicability_domain", "not assessed"),
        "pages/96_AI_Protein_Design_Lab.py": ("proteinmpnn", "rfdiffusion", "epistasis"),
        "pages/64_Wet_Lab_Biotechnology.py": ("Long-format qPCR CSV/TSV/Excel/RDML", "LLOQ", "OPC-UA"),
    }
    for relative, tokens in checks.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for token in tokens:
            assert token.lower() in text.lower(), (relative, token)
