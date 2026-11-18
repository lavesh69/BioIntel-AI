from pathlib import Path
import pandas as pd

from biointel.priority_v167 import ensure_step167_assets, priority_matrix
from biointel.priority_v167.assurance import TARGETS
from biointel.scientific_depth import native_input_template, run_native_workflow

ROOT = Path(__file__).resolve().parents[1]

EXPECTED = {
    "docking_dynamics": "step167_docking_pose_consensus",
    "genome_editing_safety": "step167_genome_editing_guide_safety",
    "metagenomics_core": "step167_metagenomics_sample_qc",
    "pathogen_outbreak_core": "step167_outbreak_profile_clusters",
    "pharmacogenomics": "step167_pharmacogenomics_variant_qc",
    "phenotypic_screening": "step167_phenotypic_performance",
    "population_gwas": "step167_gwas_variant_qc",
    "protein_language_design": "step167_protein_language_design_ranking",
    "proteogenomics_neoantigen": "step167_proteogenomics_psm_fdr",
    "single_cell_core": "step167_single_cell_cell_qc",
    "single_cell_trajectory": "step167_trajectory_cell_qc",
    "spatial_omics_pathology": "step167_spatial_neighbourhood_analysis",
    "structural_bioinformatics_core": "step167_structural_quality_dashboard",
    "virology_evolution": "step167_virology_lineage_dynamics",
    "federated_biomedical_ai": "step167_federated_round_summary",
    "cell_atlas_mapping": "step167_cell_atlas_mapping_confidence",
    "enzyme_pathway_design": "step167_enzyme_pathway_candidate_ranking",
    "explainable_ai_assurance": "step167_explainable_ai_assurance_card",
    "glycomics_glycoproteomics": "step167_glycomics_psm_fdr",
    "metabolomics_lipidomics": "step167_metabolomics_feature_qc_differential",
    "model_registry_v2": "step167_model_lifecycle_card",
}


def test_step167_assets_and_matrix() -> None:
    written = ensure_step167_assets(ROOT)
    matrix = priority_matrix(ROOT)
    assert len(written) == 63
    assert len(matrix) == 21
    assert (matrix["software_score"] == 10.0).all()
    assert (matrix["native_research_depth_score"] == 10.0).all()
    assert not matrix["controlled_release_eligible"].any()


def test_step167_all_priority_demo_runs() -> None:
    for key in sorted(TARGETS):
        result = run_native_workflow(key, native_input_template(key, demonstration=True), metadata={"project_root": str(ROOT)})
        assert result.status in {"pass", "review"}
        assert "step167_priority_module_excellence_gate" in result.tables
        assert EXPECTED[key] in result.tables
        assert result.summary["step167_priority_module_software_score"] == 10.0
        assert result.summary["step167_native_research_depth_score"] == 10.0
        assert result.summary["step167_controlled_release_eligible"] is False


def test_step167_docking_and_editing_ranking() -> None:
    docking = pd.DataFrame({
        "compound": ["A", "A", "B", "B"], "pose_id": [1, 2, 1, 2],
        "docking_score": [-9.0, -8.7, -6.0, -5.5], "rmsd": [1.0, 1.5, 3.5, 4.0],
        "strain_energy": [2.0, 3.0, 12.0, 14.0],
    })
    r = run_native_workflow("docking_dynamics", docking, metadata={"project_root": str(ROOT)})
    out = r.tables["step167_docking_pose_consensus"]
    assert out.iloc[0]["compound"] == "A"
    assert bool(out.iloc[0]["step167_pose_reproducible"])

    guides = pd.DataFrame({
        "guide_id": ["good", "bad"], "guide": ["GCGTACGATCGTACGATCGA", "AAAAAAAAAAAAAAAAAAAA"],
        "pam": ["NGG", "NGG"], "off_target_hits": [0, 12], "variant_overlap": [False, True],
    })
    r = run_native_workflow("genome_editing_safety", guides, metadata={"project_root": str(ROOT)})
    out = r.tables["step167_genome_editing_guide_safety"]
    assert out.iloc[0]["guide_id"] == "good"
    assert out.iloc[0]["step167_editing_risk_score"] < out.iloc[-1]["step167_editing_risk_score"]


def test_step167_genetics_and_omics_controls() -> None:
    gwas = pd.DataFrame({
        "variant_id": ["v1"] * 8 + ["v2"] * 8,
        "sample_id": [f"S{i}" for i in range(8)] * 2,
        "genotype": ["0/0", "0/0", "0/1", "0/1", "1/1", "0/1", "0/0", "1/1"] * 2,
        "phenotype": [0, 0, 0, 1, 1, 1, 0, 1] * 2,
        "PC1": [0.1 * i for i in range(8)] * 2,
        "genome_build": ["GRCh38"] * 16,
    })
    r = run_native_workflow("population_gwas", gwas, metadata={"project_root": str(ROOT)})
    assert r.tables["step167_gwas_variant_qc"]["call_rate"].eq(1.0).all()

    metabol = pd.DataFrame({
        "feature": ["F1"] * 8 + ["F2"] * 8,
        "sample": [f"S{i}" for i in range(8)] * 2,
        "group": ["A"] * 4 + ["B"] * 4 + ["A"] * 4 + ["B"] * 4,
        "sample_type": ["sample"] * 16,
        "injection_order": list(range(8)) * 2,
        "intensity": [10, 11, 9, 10, 40, 42, 38, 41] + [20, 21, 19, 20, 21, 20, 22, 19],
    })
    r = run_native_workflow("metabolomics_lipidomics", metabol, metadata={"project_root": str(ROOT)})
    out = r.tables["step167_metabolomics_feature_qc_differential"]
    assert abs(float(out.loc[out.feature == "F1", "log2_group_difference"].iloc[0])) > 1


def test_step167_single_cell_spatial_and_federated() -> None:
    sc = native_input_template("single_cell_trajectory", demonstration=True)
    r = run_native_workflow("single_cell_trajectory", sc, metadata={"project_root": str(ROOT)})
    assert r.tables["step167_single_cell_trajectory"]["step167_pseudotime"].between(0, 1).all()

    spatial = native_input_template("spatial_omics_pathology", demonstration=True)
    r = run_native_workflow("spatial_omics_pathology", spatial, metadata={"project_root": str(ROOT)})
    assert r.tables["step167_spatial_neighbourhood_analysis"]["step167_coordinate_valid"].all()

    fed = native_input_template("federated_biomedical_ai", demonstration=True)
    r = run_native_workflow("federated_biomedical_ai", fed, metadata={"project_root": str(ROOT)})
    assert r.tables["step167_federated_round_summary"]["participating_sites"].min() >= 2


def test_step167_model_and_proteomics_guards() -> None:
    model = native_input_template("explainable_ai_assurance", demonstration=True)
    r = run_native_workflow("explainable_ai_assurance", model, metadata={"project_root": str(ROOT)})
    card = r.tables["step167_explainable_ai_assurance_card"].iloc[0]
    assert 0 <= card["brier"] <= 1
    assert card["controlled_release_eligible"] is False or not bool(card["controlled_release_eligible"])

    psm = native_input_template("proteogenomics_neoantigen", demonstration=True)
    r = run_native_workflow("proteogenomics_neoantigen", psm, metadata={"project_root": str(ROOT)})
    assert r.tables["step167_proteogenomics_psm_fdr"]["step167_q_value"].between(0, 1).all()
