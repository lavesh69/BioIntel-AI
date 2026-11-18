from __future__ import annotations

import hashlib
from pathlib import Path

from biointel.ui.non_chart_scientific_visuals import (
    MODULE_NON_CHART_CONTEXTS,
    NON_CHART_VISUAL_CATALOG,
)

ROOT = Path(__file__).resolve().parents[1]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_step115_version_and_navigation() -> None:
    assert (ROOT / "VERSION").read_text().strip() == "13.2.0"
    navigation = (ROOT / "src/biointel/ui/navigation.py").read_text(encoding="utf-8")
    assert "pages/169_Non_Chart_Scientific_Visuals.py" in navigation
    assert "Non-Chart Scientific Visuals" in navigation


def test_step115_visual_catalog_complete() -> None:
    expected = {
        "genome_track",
        "molecular_scene",
        "microscopy_editor",
        "pathology_canvas",
        "flow_gating_canvas",
        "plate_map_editor",
        "mass_spectrum_inspector",
        "sequence_feature_track",
        "pedigree_canvas",
        "phylogeny_canvas",
        "outbreak_map_canvas",
        "pangenome_canvas",
        "single_cell_canvas",
        "multiomics_canvas",
        "bioprocess_board",
    }
    assert set(NON_CHART_VISUAL_CATALOG) == expected
    assert all(spec.modules for spec in NON_CHART_VISUAL_CATALOG.values())
    assert all(spec.interaction for spec in NON_CHART_VISUAL_CATALOG.values())


def test_step115_module_specific_workspaces_complete() -> None:
    expected = {
        "fastq",
        "variant",
        "transcriptomics",
        "crispr",
        "admet",
        "antibody",
        "rare_disease",
        "clinical_biomarker",
        "reference_db",
        "background_jobs",
        "workflow",
        "dataset_registry",
        "model_registry",
    }
    assert set(MODULE_NON_CHART_CONTEXTS) == expected
    assert all(len(config["items"]) >= 6 for config in MODULE_NON_CHART_CONTEXTS.values())


def test_step115_embedded_module_pages_present() -> None:
    required = {
        "pages/56_FASTQ_Genomics_QC.py": "_render_step115_module_non_chart(\"fastq\"",
        "pages/57_Variant_Annotation_Workbench.py": "_render_step115_module_non_chart(\"variant\"",
        "pages/59_Transcriptomics_Expression_Lab.py": "_render_step115_module_non_chart(\"transcriptomics\"",
        "pages/58_Primer_CRISPR_Codon_Studio.py": "_render_step115_module_non_chart(\"crispr\"",
        "pages/62_ADMET_Drug_Discovery.py": "_render_step115_module_non_chart(\"admet\"",
        "pages/115_Antibody_and_Biologics_Engineering_Studio.py": "_render_step115_module_non_chart(\"antibody\"",
        "pages/100_Rare_Disease_Genome_Interpretation.py": "_render_step115_module_non_chart(\"rare_disease\"",
        "pages/122_Clinical_Trial_Biomarker_and_Patient_Stratification_Studio.py": "_render_step115_module_non_chart(\"clinical_biomarker\"",
        "pages/153_Reference_Database_Lifecycle_Manager_2.py": "_render_step115_module_non_chart(\"reference_db\"",
        "pages/151_Real_Background_Job_Queue_Engine.py": "_render_step115_module_non_chart(\"background_jobs\"",
        "pages/150_Visual_Scientific_Workflow_Builder_2.py": "_render_step115_module_non_chart(\"workflow\"",
        "pages/21_Dataset_Registry_Lineage.py": "_render_step115_module_non_chart(\"dataset_registry\"",
        "pages/156_Model_Registry_ML_Lifecycle_Center_2.py": "_render_step115_module_non_chart(\"model_registry\"",
    }
    for rel, needle in required.items():
        assert needle in (ROOT / rel).read_text(encoding="utf-8")


def test_step115_all_15_visuals_are_embedded() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (ROOT / "pages").glob("*.py")
    )
    for key in NON_CHART_VISUAL_CATALOG:
        assert f'_render_step115_non_chart("{key}"' in combined


def test_step115_excluded_modules_unchanged() -> None:
    expected = {
        "pages/6_DTI_Predictor.py": "10767f9c1654df364b2321b743117f9367e24f1d17c6642ace8e378c2fedcf1a",
        "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
        "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "85e7812ef3eb05351a0ae28da1a78dc4428b23fe8e8f04e5b41c250363df996f",
        "pages/109_Lab_Instrument_Import_Center.py": "6b8b24f0549593cbe96e6baabc1929b208772d21f48e92ec4630c6835a91d73f",
        "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
    }
    for rel, digest in expected.items():
        assert _sha(ROOT / rel) == digest
