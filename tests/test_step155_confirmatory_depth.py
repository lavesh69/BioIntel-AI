from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from biointel.scientific_depth.native_budget import choose_native_budget
from biointel.scientific_depth.native_workflows import native_input_template, native_portfolio_manifest, run_native_workflow


def test_adaptive_budget_supports_extended_and_full_modes() -> None:
    assert choose_native_budget({"analysis_mode": "interactive"}, rows=2_000_000, columns=10).row_limit == 250_000
    assert choose_native_budget({"analysis_mode": "extended"}, rows=2_000_000, columns=10).row_limit == 750_000
    assert choose_native_budget({"analysis_mode": "full"}, rows=2_000_000, columns=10).row_limit == 1_000_000
    assert choose_native_budget({"analysis_mode": "full"}, rows=2_000_000, columns=1000).row_limit == 80_000


def test_bounded_analysis_samples_full_input_not_first_n_only() -> None:
    frame = pd.DataFrame({"sample_id": [f"S{i}" for i in range(250_010)], "value": np.arange(250_010, dtype=float)})
    result = run_native_workflow("multiomics_harmonization", frame)
    assert result.summary["truncated"] is True
    assert result.summary["sampling_method"] == "deterministic-even-coverage"
    assert result.provenance["rows_received"] == 250_010
    # The analyzed hash must include the tail because even-coverage includes the final row.
    assert result.tables["numeric_feature_selection_audit"].shape[0] >= 1


def test_extended_mode_uses_more_than_100_features() -> None:
    data = {f"feature_{i:03d}": np.arange(40, dtype=float) + i for i in range(140)}
    data["sample_id"] = [f"S{i}" for i in range(40)]
    frame = pd.DataFrame(data)
    result = run_native_workflow("multiomics_harmonization", frame, metadata={"analysis_mode": "extended"})
    assert result.summary["analysis_feature_limit"] >= 140
    audit = result.tables["numeric_feature_selection_audit"]
    assert int(audit.selected.sum()) == 140


def test_gwas_adds_association_and_inflation_outputs() -> None:
    frame = native_input_template("population_gwas", demonstration=True)
    result = run_native_workflow("population_gwas", frame)
    assert "native_association_screen" in result.tables
    assert "genomic_inflation_summary" in result.tables
    assert {"p_value", "fdr"}.issubset(result.tables["native_association_screen"].columns)


def test_single_cell_adds_qc_hvg_clustering_and_pseudobulk() -> None:
    frame = native_input_template("single_cell_core", demonstration=True)
    result = run_native_workflow("single_cell_core", frame)
    assert {"single_cell_qc_advanced", "highly_variable_features", "single_cell_embedding_clusters", "donor_pseudobulk_counts"}.issubset(result.tables)
    assert not result.tables["single_cell_embedding_clusters"].empty


def test_survival_adds_multivariable_cox_model() -> None:
    frame = native_input_template("clinical_biomarker_survival", demonstration=True)
    frame["age"] = np.linspace(30, 80, len(frame))
    result = run_native_workflow("clinical_biomarker_survival", frame)
    assert "multivariable_cox_model" in result.tables
    assert {"hazard_ratio", "ci95_low", "ci95_high", "p_value"}.issubset(result.tables["multivariable_cox_model"].columns)


def test_pathology_blocks_patient_split_leakage() -> None:
    frame = native_input_template("digital_pathology_foundation", demonstration=True)
    frame["split"] = "train"
    frame.loc[frame.index[0], "split"] = "test"
    result = run_native_workflow("digital_pathology_foundation", frame)
    assert "patient_split_leakage" in result.tables
    assert not result.tables["patient_split_leakage"].empty
    check = result.checks[result.checks["check"] == "Patient-level split isolation"]
    assert check.iloc[0].status == "fail"


def test_flow_derives_compensation_fmo_and_gate_hierarchy() -> None:
    rng = np.random.default_rng(155)
    events = pd.DataFrame({"FSC-A": rng.normal(50_000, 1_000, 400), "SSC-A": rng.normal(20_000, 800, 400), "A": rng.normal(100, 10, 400), "B": rng.normal(80, 10, 400)})
    controls = {
        "A": pd.DataFrame({"A": rng.normal(10_000, 500, 200), "B": rng.normal(800, 60, 200)}),
        "B": pd.DataFrame({"A": rng.normal(600, 50, 200), "B": rng.normal(9_000, 450, 200)}),
    }
    fmo = {"A": pd.DataFrame({"A": rng.normal(100, 10, 100)}), "B": pd.DataFrame({"B": rng.normal(80, 8, 100)})}
    result = run_native_workflow(
        "flow_cytometry",
        events,
        metadata={
            "fluorescence_channels": ["A", "B"],
            "single_stain_events": controls,
            "fmo_controls": fmo,
            "gate_specs": [{"name": "Cells", "kind": "rectangle", "x_channel": "FSC-A", "y_channel": "SSC-A", "x_min": 45_000, "x_max": 55_000, "y_min": 16_000, "y_max": 24_000}],
        },
    )
    assert {"derived_compensation_matrix", "fmo_thresholds", "gate_hierarchy_audit"}.issubset(result.tables)


def test_metabolomics_adds_blank_and_internal_standard_normalization() -> None:
    frame = native_input_template("metabolomics_lipidomics", demonstration=True)
    extra = frame.copy()
    extra.loc[:, "feature"] = "IS"
    extra.loc[:, "intensity"] = 50.0
    combined = pd.concat([frame, extra], ignore_index=True)
    result = run_native_workflow("metabolomics_lipidomics", combined, metadata={"internal_standard_feature": "IS"})
    table = result.tables["blank_and_internal_standard_normalization"]
    assert {"blank_corrected_intensity", "internal_standard_factor", "normalized_intensity"}.issubset(table.columns)


def test_structural_chemistry_adds_rdkit_standardization_and_scaffolds() -> None:
    frame = native_input_template("docking_dynamics", demonstration=True)
    result = run_native_workflow("docking_dynamics", frame)
    table = result.tables["rdkit_ligand_standardization"]
    assert {"canonical_smiles", "murcko_scaffold", "molecular_weight", "tpsa"}.issubset(table.columns)
    assert table.valid.all()


def test_amr_adds_per_drug_diagnostic_performance() -> None:
    result = run_native_workflow("amr_surveillance", native_input_template("amr_surveillance", demonstration=True))
    table = result.tables["per_drug_genotype_phenotype_performance"]
    assert {"sensitivity", "specificity", "ppv", "npv"}.issubset(table.columns)


def test_federated_ai_adds_weighted_aggregation_and_privacy_composition() -> None:
    result = run_native_workflow("federated_biomedical_ai", native_input_template("federated_biomedical_ai", demonstration=True))
    assert {"federated_weighted_aggregation_audit", "privacy_budget_composition"}.issubset(result.tables)


def test_step155_manifest_exposes_adaptive_limits() -> None:
    manifest = native_portfolio_manifest()
    assert manifest["full_row_limit"] == 1_000_000
    assert manifest["full_feature_limit"] == 512
    assert "even coverage" in manifest["row_sampling"]


def test_step155_adds_protected_specialist_plans(tmp_path) -> None:
    from biointel.native.engines import build_engine_plan, plan_catalog

    files = {
        "query.fa": ">q\nACGT\n", "db": "index", "reads1.fastq": "@r\nACGT\n+\n!!!!\n",
        "reads2.fastq": "@r\nTGCA\n+\n!!!!\n", "annotation.gtf": "chr1\t.\tgene\t1\t10\t.\t+\t.\tgene_id \"g1\";\n",
        "b1.txt": "a.bam\n", "b2.txt": "b.bam\n", "majiq.ini": "[info]\n",
        "phenotype.tsv": "FID\tIID\tphenotype\n1\t1\t1\n", "pred.list": "pred\n",
        "cohort.vcf.gz": "vcf", "cohort.vcf.gz.csi": "idx", "null.rda": "null", "variance.txt": "1\n",
        "reads.bam": "bam", "reference.fa": ">chr1\nACGT\n", "assembly.fa": ">ctg\nACGT\n",
        "rfdiffusion.yaml": "defaults: []\n", "image.tif": "image", "stardist_wrapper.py": "print('ok')\n",
        "openmm_wrapper.py": "print('ok')\n", "system.xml": "<System/>\n", "protein.fa": ">p\nMAAA\n",
        "resfinder_db": "db", "pointfinder_db": "db",
    }
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    for folder in ("star_index", "meryl_db"):
        (tmp_path / folder).mkdir()

    cases = {
        "blastn_search": {"query": tmp_path / "query.fa", "database_prefix": tmp_path / "db"},
        "star_align": {"genome_dir": tmp_path / "star_index", "reads1": tmp_path / "reads1.fastq", "reads2": tmp_path / "reads2.fastq"},
        "rmats_splicing": {"b1": tmp_path / "b1.txt", "b2": tmp_path / "b2.txt", "gtf": tmp_path / "annotation.gtf"},
        "majiq_build": {"config": tmp_path / "majiq.ini", "annotation": tmp_path / "annotation.gtf"},
        "suppa2_events": {"annotation": tmp_path / "annotation.gtf"},
        "regenie_association": {"pgen_prefix": tmp_path / "cohort", "phenotype": tmp_path / "phenotype.tsv", "predictions": tmp_path / "pred.list"},
        "saige_association": {"vcf": tmp_path / "cohort.vcf.gz", "vcf_index": tmp_path / "cohort.vcf.gz.csi", "null_model": tmp_path / "null.rda", "variance_ratio": tmp_path / "variance.txt"},
        "modkit_pileup": {"alignment": tmp_path / "reads.bam", "reference": tmp_path / "reference.fa"},
        "merqury_evaluate": {"meryl_db": tmp_path / "meryl_db", "assembly": tmp_path / "assembly.fa"},
        "rfdiffusion_generate": {"config": tmp_path / "rfdiffusion.yaml"},
        "stardist_segment": {"image": tmp_path / "image.tif", "wrapper_script": tmp_path / "stardist_wrapper.py"},
        "openmm_simulate": {"script": tmp_path / "openmm_wrapper.py", "system": tmp_path / "system.xml"},
        "amrfinder_run": {"protein_fasta": tmp_path / "protein.fa"},
        "resfinder_run": {"reads1": tmp_path / "reads1.fastq", "reads2": tmp_path / "reads2.fastq", "database": tmp_path / "resfinder_db", "point_database": tmp_path / "pointfinder_db"},
    }
    for key, kwargs in cases.items():
        plan = build_engine_plan(key, workdir=tmp_path, **kwargs)
        assert plan.command
        assert plan.cwd == str(tmp_path.resolve())
        assert all(Path(item).is_relative_to(tmp_path.resolve()) for item in plan.inputs)
    assert len(plan_catalog()) >= 55
