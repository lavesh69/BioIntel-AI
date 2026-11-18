from __future__ import annotations

from pathlib import Path

import pandas as pd

from biointel.ui.advanced_scientific_viewers import (
    ADVANCED_VIEWER_CATALOG,
    build_advanced_viewer_visuals,
)
from biointel.ui.navigation import PAGE_BY_KEY

ROOT = Path(__file__).resolve().parents[1]


def test_step110_catalog_has_all_advanced_viewers() -> None:
    expected = {
        "genome_browser", "molecular_3d", "pathology", "microscopy", "flow_gating",
        "mass_spectrometry", "phylogenetic_tree", "plate_map", "pedigree", "outbreak_map",
        "pangenome_graph", "single_cell", "sequence_track", "multiomics", "bioprocess_live",
        "workflow_dag", "freezer_map", "static_reporting", "visual_regression",
    }
    assert set(ADVANCED_VIEWER_CATALOG) == expected
    assert len(ADVANCED_VIEWER_CATALOG) == 19


def test_all_advanced_viewer_builders_are_deterministic_and_nonempty() -> None:
    for key in ADVANCED_VIEWER_CATALOG:
        first = build_advanced_viewer_visuals(key)
        second = build_advanced_viewer_visuals(key)
        assert 3 <= len(first) <= 5
        assert [item.title for item in first] == [item.title for item in second]
        for visual in first:
            assert visual.title
            assert visual.interpretation
            assert visual.method
            assert visual.figure is not None
            assert isinstance(visual.data, pd.DataFrame)
            assert not visual.data.empty


def test_advanced_viewer_page_is_registered() -> None:
    page = PAGE_BY_KEY["advanced_scientific_viewers"]
    assert page.path == "pages/165_Advanced_Scientific_Viewers.py"
    assert page.category == "Intelligence"
    assert page.featured is True
    assert (ROOT / page.path).exists()


def test_relevant_pages_receive_embedded_viewers() -> None:
    expected_markers = {
        "pages/57_Variant_Annotation_Workbench.py": "genome_browser",
        "pages/61_Structural_Bioinformatics.py": "molecular_3d",
        "pages/64_Wet_Lab_Biotechnology.py": "flow_gating",
        "pages/68_Alignment_Phylogeny.py": "phylogenetic_tree",
        "pages/94_Pangenome_Variation_Graph_Studio.py": "pangenome_graph",
        "pages/100_Rare_Disease_Genome_Interpretation.py": "pedigree",
        "pages/118_Spatial_Omics_and_Digital_Pathology_Studio.py": "pathology",
        "pages/120_Bioimage_and_Microscopy_AI_Lab.py": "microscopy",
        "pages/125_Bioprocess_and_Fermentation_Optimization_Studio.py": "bioprocess_live",
        "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "freezer_map",
        "pages/164_Visual_Interaction_Accessibility_Workspace.py": "visual_regression",
    }
    for relative, viewer_key in expected_markers.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "Step 110 advanced scientific viewers" in text
        assert f'"{viewer_key}"' in text


def test_step110_version_surfaces() -> None:
    version = tuple(int(part) for part in (ROOT / "VERSION").read_text(encoding="utf-8").strip().split("."))
    assert version >= (11, 0, 0)
    version_text = ".".join(str(part) for part in version)
    assert f'version = "{version_text}"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'__version__ = "{version_text}"' in (ROOT / "src/biointel/__init__.py").read_text(encoding="utf-8")
