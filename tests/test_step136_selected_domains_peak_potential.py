from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from biointel.peak_potential.bundle import build_peak_bundle
from biointel.peak_potential.catalog import contract_for, domain_for, is_peak_target
from biointel.peak_potential.quality import audit_frame, audit_plotly_figure, build_manifest
from biointel.ui.navigation import PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def test_only_requested_scientific_domains_are_targeted() -> None:
    assert is_peak_target(page_key="fastq_genomics_qc", category="Bioinformatics", title="FASTQ & Genome QC")
    assert is_peak_target(page_key="discovery_command_center", category="Discovery", title="Discovery Command Center")
    assert is_peak_target(page_key="wetlab_biotechnology", category="Lab Analytics", title="Wet-Lab Biotechnology")
    assert is_peak_target(page_key="multiomics_biomarker", category="AI Lab", title="Multi-Omics Biomarker Discovery")
    assert is_peak_target(page_key="clinical_biomarker_survival", category="Clinical Research", title="Clinical Biomarker & Survival")
    assert not is_peak_target(page_key="appearance_studio", category="Settings", title="Appearance Studio")
    assert not is_peak_target(page_key="governance_hub", category="Governance", title="Governance Hub")
    assert not is_peak_target(page_key="generic_ai", category="AI Lab", title="Generic AI Lab")


def test_product_family_classification_does_not_confuse_genomics_with_omics() -> None:
    assert domain_for(
        page_key="fastq_genomics_qc", category="Bioinformatics", title="FASTQ & Genome QC"
    ) == "BioIntel Genomics & Bioinformatics"
    assert domain_for(
        page_key="pathogen_outbreak", category="Bioinformatics", title="Pathogen Outbreak Genomics"
    ) == "BioIntel Genomics & Bioinformatics"
    assert domain_for(
        page_key="multiomics_biomarker", category="AI Lab", title="Multi-Omics Biomarker"
    ) == "BioIntel Omics & Next-Generation Biology"
    assert domain_for(
        page_key="gene_therapy_vector", category="Lab Analytics", title="Gene Therapy Vector"
    ) == "Therapy & Translational"
    assert domain_for(
        page_key="protein_ligand_codesign", category="Discovery", title="Protein–Ligand Co-Design"
    ) == "BioIntel Discovery"


def test_contracts_have_real_quality_and_handoff_requirements() -> None:
    contract = contract_for(
        page_key="gene_therapy_vector",
        title="Gene Therapy Vector Engineering & Safety Studio",
        category="Lab Analytics",
    )
    assert contract.domain == "Therapy & Translational"
    assert contract.visual_minimum >= 4
    assert len(contract.quality_gates) >= 7
    assert "Portable ZIP evidence bundle" in contract.required_outputs
    assert contract.handoffs
    assert "does not manufacture external validation" in contract.evidence_boundary


def test_frame_audit_is_bounded_and_handles_nested_mixed_data() -> None:
    frame = pd.DataFrame(
        [
            {"sample": "A", "value": 1.0, "meta": {"batch": 1}},
            {"sample": "A", "value": np.inf, "meta": {"batch": 1}},
            {"sample": None, "value": np.nan, "meta": ["unexpected"]},
        ]
    )
    audit = audit_frame(frame, sample_rows=2)
    assert audit.rows == 3
    assert audit.audited_rows == 2
    assert audit.sampled is True
    assert audit.infinite_cells in {0, 1}
    assert audit.missing_cells >= 1
    assert "meta" in audit.mixed_object_columns
    assert audit.blockers or audit.warnings
    assert 0 <= audit.score <= 100


def test_frame_audit_duplicate_columns_never_crashes() -> None:
    frame = pd.DataFrame([[1, 2], [1, np.inf]], columns=["value", "value"])
    audit = audit_frame(frame)
    assert audit.duplicate_columns == ("value",)
    assert audit.infinite_cells == 1
    assert any("Duplicate column" in item for item in audit.blockers)


def test_plotly_audit_accepts_scatter_and_sankey_but_blocks_empty_or_nan_heatmap() -> None:
    scatter = go.Figure(go.Scatter(x=[1, 2], y=[3, 4]))
    assert audit_plotly_figure(scatter).has_data
    sankey = go.Figure(go.Sankey(node={"label": ["A", "B"]}, link={"source": [0], "target": [1], "value": [2]}))
    assert audit_plotly_figure(sankey).has_data
    empty = go.Figure()
    empty_audit = audit_plotly_figure(empty)
    assert not empty_audit.has_data
    assert empty_audit.warnings
    nan_heatmap = go.Figure(go.Heatmap(z=[[np.nan, np.nan], [np.nan, np.nan]]))
    assert not audit_plotly_figure(nan_heatmap).has_data
    large = go.Figure(go.Scatter(x=np.arange(1000), y=np.arange(1000)))
    sampled = audit_plotly_figure(large, max_values=10)
    assert sampled.has_data and sampled.sampled


def test_peak_bundle_is_deterministic_bounded_and_contains_evidence_files() -> None:
    manifest = build_manifest(
        module_key="fastq_genomics_qc",
        title="FASTQ & Genome QC",
        domain="BioIntel Genomics & Bioinformatics",
        software_version="13.2.0",
    )
    manifest["generated_at_utc"] = "2026-07-12T00:00:00+00:00"
    table = pd.DataFrame({"sample": [f"S{i}" for i in range(20)], "reads": np.arange(20)})
    first = build_peak_bundle(
        module_key="fastq_genomics_qc",
        manifest=manifest,
        tables={"results": table},
        max_rows_per_table=5,
    )
    second = build_peak_bundle(
        module_key="fastq_genomics_qc",
        manifest=manifest,
        tables={"results": table},
        max_rows_per_table=5,
    )
    assert first == second
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {
            "manifest.json",
            "README.txt",
            "bundle_index.json",
            "tables/results.csv",
            "tables/results.schema.json",
        }
        payload = json.loads(archive.read("manifest.json"))
        index = json.loads(archive.read("bundle_index.json"))
        assert payload["module_key"] == "fastq_genomics_qc"
        assert index["tables"]["results"]["truncated"] is True
        assert index["tables"]["results"]["exported_rows"] == 5


def test_every_target_module_has_legacy_footer_or_shared_nextgen_assurance() -> None:
    theme = (ROOT / "src/biointel/ui/theme.py").read_text(encoding="utf-8")
    nextgen = (ROOT / "src/biointel/nextgen/renderer.py").read_text(encoding="utf-8")
    assert "render_peak_sidebar_for_page" in theme
    assert "_peak_visual_allowed" in theme
    assert "_install_peak_dataframe_adapter" in theme
    assert "render_peak_assurance_workspace" in nextgen
    assert "Peak scientific assurance" in nextgen

    missing: list[str] = []
    targeted = 0
    for page in PAGE_CATALOG:
        if not is_peak_target(page_key=page.key, category=page.category, title=page.title):
            continue
        targeted += 1
        source = (ROOT / page.path).read_text(encoding="utf-8")
        has_footer = "render_peak_session_footer" in source
        uses_shared_nextgen = "render_nextgen_module" in source
        if not (has_footer or uses_shared_nextgen):
            missing.append(page.key)
    assert targeted >= 70
    assert missing == []
    assert "render_peak_session_footer" not in (ROOT / "pages/24_Appearance_Studio.py").read_text(encoding="utf-8")
    assert "render_peak_session_footer" not in (ROOT / "pages/30_Governance_Hub.py").read_text(encoding="utf-8")
