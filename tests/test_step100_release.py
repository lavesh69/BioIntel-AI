from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_step100_version_is_synchronized():
    assert (ROOT / "VERSION").read_text().strip() == "13.2.0"
    assert 'version = "13.2.0"' in (ROOT / "pyproject.toml").read_text()
    assert '__version__ = "13.2.0"' in (ROOT / "src/biointel/__init__.py").read_text()
    assert json.loads((ROOT / "platform/desktop/package.json").read_text())["version"] == "13.2.0"
    assert json.loads((ROOT / "store/release-manifest.json").read_text())["release_version"] == "13.2.0"


def test_step100_professional_layers_are_present_in_all_eleven_pages():
    expected = {
        94: "render_pangenome_professional",
        95: "render_long_read_professional",
        96: "render_protein_design_professional",
        97: "render_crispr_professional",
        98: "render_outbreak_professional",
        99: "render_synthetic_biology_professional",
        100: "render_rare_disease_professional",
        101: "render_knowledge_graph_professional",
        102: "render_biomarker_professional",
        103: "render_workflow_professional",
        104: "render_innovation_hub_professional",
    }
    for number, function in expected.items():
        page = next((ROOT / "pages").glob(f"{number}_*.py"))
        text = page.read_text()
        assert function in text
        assert "Step 100 professional integration" in text


def test_step100_manifests_expand_tools_and_assets_without_claiming_bundling():
    tools = json.loads((ROOT / "config/advanced_tools_manifest.json").read_text())
    assert len(tools["tools"]) >= 56
    ids = {tool["id"] for tool in tools["tools"]}
    assert {"racon", "medaka", "merqury", "gubbins", "raxml_ng", "bagel", "jacks"}.issubset(ids)
    assets = json.loads((ROOT / "config/reference_assets_manifest.json").read_text())
    template_ids = {item["id"] for item in assets["templates"]}
    assert {"clinvar-vcf", "gnomad-sites", "proteinmpnn-weights", "rfdiffusion-weights", "vg-graph-index"}.issubset(template_ids)
    assert assets["policy"]["large_assets_outside_application"] is True


def test_step100_source_and_config_files_exist():
    assert (ROOT / "src/biointel/innovation/professional_engines.py").is_file()
    assert (ROOT / "src/biointel/innovation/professional_ui.py").is_file()
    assert (ROOT / "config/step100_professional_integration.json").is_file()
