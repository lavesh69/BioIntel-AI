from pathlib import Path
import pandas as pd

from biointel.priority_v166 import ensure_step166_assets, six_module_matrix
from biointel.scientific_depth import native_input_template, run_native_workflow

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    "epigenomics_chromatin",
    "long_read_core",
    "one_health_environmental",
    "pangenome_core",
    "strain_microbiome",
    "structural_variant_repeat",
)
EXPECTED = {
    "epigenomics_chromatin": "step166_epigenomics_consensus_peaks",
    "long_read_core": "step166_long_read_read_quality_summary",
    "one_health_environmental": "step166_one_health_contamination_screen",
    "pangenome_core": "step166_pangenome_input_and_graph_readiness",
    "strain_microbiome": "step166_strain_confidence_and_contamination",
    "structural_variant_repeat": "step166_structural_variant_evidence_summary",
}


def test_step166_assets_and_matrix() -> None:
    written = ensure_step166_assets(ROOT)
    matrix = six_module_matrix(ROOT)
    assert len(written) == 18
    assert len(matrix) == 6
    assert (matrix["software_score"] == 10.0).all()
    assert (matrix["native_research_depth_score"] == 10.0).all()
    assert not matrix["controlled_release_eligible"].any()


def test_step166_demo_runs_emit_focused_outputs() -> None:
    for key in TARGETS:
        result = run_native_workflow(key, native_input_template(key, demonstration=True), metadata={"project_root": str(ROOT)})
        assert result.status in {"pass", "review"}
        assert "step166_six_module_excellence_gate" in result.tables
        assert EXPECTED[key] in result.tables
        assert result.summary["step166_six_module_software_score"] == 10.0
        assert result.summary["step166_native_research_depth_score"] == 10.0
        assert result.summary["step166_controlled_release_eligible"] is False


def test_step166_epigenomics_differential_and_consensus() -> None:
    rows = []
    for rep in ("R1", "R2"):
        for condition, signal in (("Control", 10.0), ("Case", 24.0)):
            rows.append({"chrom": "chr1", "start": 100, "end": 300, "replicate": rep + condition, "condition": condition, "q_value": 0.01, "signal": signal})
            rows.append({"chrom": "chr1", "start": 500, "end": 700, "replicate": rep + condition, "condition": condition, "q_value": 0.02, "signal": signal / 2})
    result = run_native_workflow("epigenomics_chromatin", pd.DataFrame(rows), metadata={"project_root": str(ROOT)})
    assert "step166_epigenomics_differential_accessibility" in result.tables
    assert result.tables["step166_epigenomics_consensus_peaks"]["step166_consensus_peak"].all()


def test_step166_pangenome_classification_and_graph() -> None:
    frame = pd.DataFrame({
        "genome": ["G1", "G2", "G3", "G1", "G2", "G3", "G1"],
        "gene": ["coreA", "coreA", "coreA", "shellB", "shellB", "cloudC", "cloudD"],
        "present": [1, 1, 1, 1, 1, 1, 1],
    })
    result = run_native_workflow("pangenome_core", frame, metadata={"project_root": str(ROOT), "reference_path": "G1"})
    assert "step166_pangenome_core_accessory_classification" in result.tables
    classes = set(result.tables["step166_pangenome_core_accessory_classification"]["pangenome_class"])
    assert "core" in classes


def test_step166_strain_confidence_and_structural_variant() -> None:
    strain = pd.DataFrame({
        "sample_id": ["S1", "S1", "S2", "S2", "NC", "NC"],
        "taxon": ["A", "B", "A", "B", "A", "B"],
        "abundance": [90, 10, 80, 20, 1, 1],
        "negative_control": [False, False, False, False, True, True],
        "marker_breadth": [0.95] * 6,
        "marker_depth": [20] * 6,
        "ani": [0.99] * 6,
    })
    result = run_native_workflow("strain_microbiome", strain, metadata={"project_root": str(ROOT)})
    assert result.tables["step166_strain_confidence_and_contamination"]["step166_strain_confidence_score"].between(0, 1).all()
    sv = pd.DataFrame({
        "variant_id": ["SV1", "SV1", "SV2", "SV2"],
        "sample_id": ["S1", "S2", "S1", "S2"],
        "genotype": ["0/1", "0/0", "1/1", "0/1"],
        "svtype": ["DEL", "DEL", "INS", "INS"],
        "start": [100, 100, 500, 500],
        "end": [300, 300, 900, 900],
        "split_reads": [8, 4, 10, 7],
        "discordant_pairs": [12, 8, 15, 10],
        "caller_count": [3, 2, 3, 2],
    })
    result = run_native_workflow("structural_variant_repeat", sv, metadata={"project_root": str(ROOT)})
    assert result.tables["step166_structural_variant_evidence_summary"]["step166_high_confidence_research_sv"].all()
