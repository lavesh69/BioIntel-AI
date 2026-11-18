from __future__ import annotations

from pathlib import Path

from biointel.expansion.catalog import EXPANSION_MODULES
from biointel.nextgen.catalog import NEXTGEN_MODULES
from biointel.nextgen.biomedical_expansion import NEW_BIOMEDICAL_KEYS
from biointel.ui.workbench import INTERACTIVE_UPLOAD_BYTES, MAX_UPLOAD_BYTES

ROOT = Path(__file__).resolve().parents[1]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_upload_limits_and_background_large_file_handler() -> None:
    assert MAX_UPLOAD_BYTES == 1024 * 1024 * 1024
    assert INTERACTIVE_UPLOAD_BYTES == 100 * 1024 * 1024
    worker = _text("src/biointel/jobs/worker.py")
    assert '"scientific_large_file_inspect": self._scientific_large_file_inspect' in worker
    assert "source.relative_to(allowed)" in worker
    assert "if size > 1024 * 1024 * 1024" in worker


def test_workbench_css_is_loaded_as_final_theme_layer() -> None:
    theme = _text("src/biointel/ui/theme.py")
    assert 'with_name("workbench.css")' in theme
    assert "Final scientific-workbench layer" in theme
    css = _text("src/biointel/ui/workbench.css")
    assert '[data-testid="stFileUploaderDropzone"]' in css
    assert "opacity:1 !important" in css
    assert ".bio-wb-header" in css


def test_all_scientific_expansion_modules_use_one_run_workbench() -> None:
    assert len(EXPANSION_MODULES) == 21
    scientific_nextgen = [item for item in NEXTGEN_MODULES if item.kind == "scientific"]
    assert len(scientific_nextgen) == 14 + len(NEW_BIOMEDICAL_KEYS)
    expansion = _text("src/biointel/expansion/renderer.py")
    nextgen = _text("src/biointel/nextgen/renderer.py")
    for text in (expansion, nextgen):
        assert "render_source_selector(" in text
        assert "render_data_readiness(" in text
        assert "run_analysis_once(" in text
        assert "render_results_workbench(" in text
        assert "render_export_panel(" in text
    workbench = _text("src/biointel/ui/workbench.py")
    assert '"Run analysis"' in workbench
    assert "Existing results are marked outdated" in workbench
    assert "Download complete ZIP" in workbench


def test_module_hubs_use_product_facing_names() -> None:
    expansion_hub = _text("pages/133_Scientific_Expansion_Hub.py")
    platform_hub = _text("pages/163_Step104_Scientific_and_Platform_Expansion_Hub.py")
    assert "Advanced Scientific Workbenches" in expansion_hub
    assert "Scientific Platform Services" in platform_hub
    assert "Step 104" not in platform_hub


def test_heavy_legacy_workspaces_are_grouped_and_conditional() -> None:
    metagenomics = _text("pages/82_Metagenomics_Pipeline.py")
    discovery = _text("pages/88_Discovery_Command_Center.py")
    registry = _text("pages/21_Dataset_Registry_Lineage.py")
    assert 'st.tabs(["Overview", "Quality & composition", "Diversity & inference", "Advanced assurance", "Export"])' in metagenomics
    assert 'key="meta_quality_view"' in metagenomics
    assert 'key="meta_diversity_view"' in metagenomics
    assert 'st.tabs(["Workflow", "Targets & compounds", "Discovery analytics", "Evidence & export", "Capability map"])' in discovery
    assert 'key="discovery_assets_view"' in discovery
    assert 'key="discovery_analytics_view"' in discovery
    assert 'key="dataset_registry_detail_view"' in registry
    assert "detail_tabs = st.tabs" not in registry


def test_navigation_has_focus_area_grouping() -> None:
    theme = _text("src/biointel/ui/theme.py")
    assert '"Focus area"' in theme
    assert '"All focus areas"' in theme
    navigation = _text("src/biointel/ui/navigation.py")
    assert "Advanced Scientific Workbenches" in navigation
    assert "Scientific Platform Services" in navigation


def test_duplicate_platform_labels_are_disambiguated() -> None:
    catalog = _text("src/biointel/nextgen/catalog.py")
    for label in (
        "Scientific Workflow Automation Builder",
        "Reference Version & Lifecycle Manager",
        "Model Registry & Deployment Governance",
        "Instrument Connector & Watch-Folder Hub",
        "Cross-Module Research Workspace",
    ):
        assert label in catalog
