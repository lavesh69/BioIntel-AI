from pathlib import Path
import pandas as pd
from biointel.priority_v165 import ensure_step165_assets, priority_matrix
from biointel.scientific_depth import native_input_template, run_native_workflow

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("amr_surveillance", "protein_ligand_codesign", "long_read_epigenome")

def test_step165_assets_and_matrix() -> None:
    written = ensure_step165_assets(ROOT)
    matrix = priority_matrix(ROOT)
    assert len(written) == 9
    assert len(matrix) == 3
    assert (matrix["software_score"] == 10.0).all()
    assert not matrix["controlled_release_eligible"].any()

def test_step165_target_modules_emit_focused_gates() -> None:
    expected = {
        "amr_surveillance": "step165_amr_confirmatory_metrics",
        "protein_ligand_codesign": "step165_codesign_consensus_ranking",
        "long_read_epigenome": "step165_long_read_input_readiness",
    }
    for key in TARGETS:
        result = run_native_workflow(key, native_input_template(key, demonstration=True), metadata={"project_root": str(ROOT)})
        assert result.status in {"pass", "review"}
        assert "step165_priority_module_gate" in result.tables
        assert expected[key] in result.tables
        assert result.summary["step165_priority_module_software_score"] == 10.0
        assert result.summary["step165_controlled_release_eligible"] == 0

def test_step165_long_read_methylation_depth() -> None:
    rows=[]
    for sample in ("S1","S2"):
        for condition, offset in (("Control",0.0),("Case",0.25)):
            for hap in ("H1","H2"):
                rows.append({"sample": sample+condition, "region":"DMR1", "condition":condition, "haplotype":hap, "methylation_fraction":0.35+offset+(0.1 if hap=="H2" else 0), "coverage":40, "read_length":12000})
    result=run_native_workflow("long_read_epigenome", pd.DataFrame(rows), metadata={"project_root":str(ROOT)})
    assert "step165_methylation_credible_intervals" in result.tables
    assert "step165_long_read_region_evidence_gate" in result.tables
    assert "step165_haplotype_imbalance_review" in result.tables

def test_step165_codesign_selectivity() -> None:
    frame=pd.DataFrame({"candidate":["A","B","C"],"protein_score":[.8,.7,.9],"ligand_score":[.7,.8,.6],"interface_score":[.9,.6,.8],"selectivity_risk":[.1,.4,.2],"target_score":[.9,.7,.8],"antitarget_score":[.2,.5,.4]})
    result=run_native_workflow("protein_ligand_codesign",frame,metadata={"project_root":str(ROOT)})
    assert "step165_codesign_selectivity_panel" in result.tables
    assert result.tables["step165_codesign_consensus_ranking"]["step165_consensus_score"].between(0,1).all()
