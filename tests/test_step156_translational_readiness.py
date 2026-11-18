from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from biointel.native.engines import ENGINE_REGISTRY, build_engine_plan, plan_catalog
from biointel.scientific_depth.native_workflows import native_input_template, native_portfolio_manifest, run_native_workflow


def test_antibody_adds_liability_and_pairing_audits() -> None:
    frame = pd.DataFrame({
        "candidate_id": ["Ab1-H", "Ab1-L"],
        "pair_id": ["Ab1", "Ab1"],
        "chain": ["heavy", "light"],
        "sequence": [
            "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEWVSAISGSGGSTYYADSVKGRFTISRDNSKNTLYLQMNSLRAEDTAVYYCAK",
            "DIQMTQSPSSLSASVGDRVTITCRASQGISNYLAWYQQKPGKAPKLLIYAASTLQSGVPSRFSGSGSGTDFTLTISSLQPEDFATYYCQQYNSYPYTFGQGTKLEIK",
        ],
    })
    result = run_native_workflow("antibody_biologics", frame)
    assert {"antibody_sequence_liability_audit", "antibody_chain_pairing_audit"}.issubset(result.tables)
    assert result.tables["antibody_chain_pairing_audit"].paired.all()


def test_vaccine_adds_population_coverage_and_safe_binder_priority() -> None:
    frame = native_input_template("immunoinformatics_vaccine", demonstration=True)
    result = run_native_workflow(
        "immunoinformatics_vaccine",
        frame,
        metadata={"hla_frequencies": {"HLA-A*02:01": 0.42}, "host_reference_peptides": ["AAAAAAAAA"]},
    )
    table = result.tables["vaccine_candidate_prioritization"]
    assert {"strong_binder", "safety_pass", "candidate_score", "hla_frequency"}.issubset(table.columns)
    assert "hla_coverage_summary" in result.tables
    assert table.loc[table.peptide_clean == "AAAAAAAAA", "safety_pass"].eq(False).all()


def test_pharmacogenomics_adds_traceable_evidence_completeness() -> None:
    frame = pd.DataFrame({
        "sample_id": ["S1", "S2"], "gene": ["CYP2C19", "CYP2D6"], "variant_id": ["v1", "v2"],
        "genotype": ["0|1", "1|1"], "diplotype": ["*1/*2", "*1/*4"],
        "predicted_phenotype": ["intermediate", "poor"], "copy_number": [2, 2],
        "phased": [True, True], "guideline_version": ["CPIC-2025", "CPIC-2025"], "genome_build": ["GRCh38", "GRCh38"],
    })
    result = run_native_workflow("pharmacogenomics", frame)
    assert {"pharmacogenomics_evidence_completeness", "diplotype_phenotype_consistency"}.issubset(result.tables)
    assert int(result.tables["pharmacogenomics_evidence_completeness"].present.sum()) >= 9


def test_structural_variant_adds_read_support_and_caller_consensus() -> None:
    frame = pd.DataFrame({
        "sample_id": ["S1", "S1", "S2"], "variant_id": ["SV1", "SV1", "SV2"], "chrom": ["1", "1", "2"],
        "start": [100, 100, 300], "end": [250, 250, 500], "svtype": ["DEL", "DEL", "DUP"],
        "split_reads": [5, 6, 1], "paired_reads": [4, 3, 1], "depth_support": [3, 2, 0], "caller": ["Sniffles", "CuteSV", "Sniffles"],
    })
    result = run_native_workflow("structural_variant_repeat", frame)
    assert {"structural_variant_evidence_audit", "structural_variant_caller_consensus"}.issubset(result.tables)
    consensus = result.tables["structural_variant_caller_consensus"]
    assert consensus.independent_callers.max() == 2


def test_gene_therapy_blocks_vector_over_capacity() -> None:
    frame = pd.DataFrame({"construct_id": ["AAV-OK", "AAV-LONG"], "serotype": ["AAV9", "AAV9"], "dna_sequence": ["ATG" + "GCC" * 100 + "TAA", "ATG" + "GCC" * 1700 + "TAA"]})
    result = run_native_workflow("gene_therapy_vector", frame)
    table = result.tables["gene_therapy_vector_risk_audit"]
    assert table.within_packaging_limit.tolist() == [True, False]
    check = result.checks[result.checks.check == "Vector packaging capacity"]
    assert check.iloc[0].status == "fail"


def test_cell_therapy_adds_configurable_benefit_risk_gate() -> None:
    result = run_native_workflow("cell_therapy_cart", native_input_template("cell_therapy_cart", demonstration=True))
    table = result.tables["cell_therapy_benefit_risk_audit"]
    assert {"off_tumour_pass", "potency_pass", "overall_preclinical_gate", "benefit_risk_score"}.issubset(table.columns)


def test_docking_adds_pose_consensus_and_md_convergence() -> None:
    frame = pd.DataFrame({
        "compound": ["C1"] * 6, "pose_id": [1, 2, 3, 4, 5, 6], "docking_score": [-7.0, -7.1, -6.9, -7.0, -7.2, -7.1],
        "rmsd": [1.2, 1.3, 1.4, 1.4, 1.45, 1.46], "strain_energy": [3.0] * 6,
        "time_ns": [0, 10, 20, 30, 40, 50], "potential_energy": [-100, -101, -100.8, -100.7, -100.6, -100.5],
    })
    result = run_native_workflow("docking_dynamics", frame)
    assert {"docking_pose_consensus_audit", "molecular_dynamics_convergence_audit"}.issubset(result.tables)


def test_federated_adds_equity_poisoning_and_authentication_checks() -> None:
    frame = native_input_template("federated_biomedical_ai", demonstration=True)
    frame["update_norm"] = np.linspace(1.0, 1.5, len(frame))
    frame.loc[frame.index[-1], "update_norm"] = 100.0
    frame["signed_update"] = True
    result = run_native_workflow("federated_biomedical_ai", frame)
    assert {"federated_site_equity_audit", "federated_update_poisoning_audit"}.issubset(result.tables)
    assert result.tables["federated_update_poisoning_audit"].poisoning_outlier.any()


def test_pharmacovigilance_adds_duplicate_and_temporal_signal_audit() -> None:
    frame = pd.DataFrame({
        "report_id": ["R1", "R1", "R2", "R3"], "drug": ["D", "D", "D", "D"], "event": ["E", "E", "E", "E"],
        "report_date": ["2026-01-01", "2026-01-01", "2026-02-01", "2026-03-01"], "onset_date": ["2025-12-30", "2025-12-30", "2026-01-30", "2026-02-25"],
    })
    result = run_native_workflow("pharmacovigilance_intelligence", frame)
    assert {"pharmacovigilance_case_quality_audit", "pharmacovigilance_temporal_signal"}.issubset(result.tables)
    assert result.tables["pharmacovigilance_case_quality_audit"].potential_duplicate.any()


def test_autonomous_lab_protocol_is_fail_closed_without_approval_or_safe_deck() -> None:
    frame = pd.DataFrame({
        "step_id": ["S1", "S2", "S3"], "predecessor": ["", "S1", "S2"], "resource": ["robot", "robot", "reader"],
        "deck_slot": ["A1", "A1", "B1"], "volume_ul": [10, 250, 0], "capacity_ul": [100, 100, 100],
        "duration_min": [2, 3, 5], "human_approved": [True, False, True],
    })
    result = run_native_workflow("autonomous_lab_planner", frame)
    assert {"autonomous_lab_protocol_safety_audit", "autonomous_lab_topological_schedule"}.issubset(result.tables)
    assert result.status == "fail"


def test_step156_protected_plans_cover_all_registered_engine_families(tmp_path: Path) -> None:
    files = {
        "source.vcf": "##fileformat=VCFv4.2\n", "reference.fa": ">chr1\nACGT\n", "reads.fastq": "@r\nACGT\n+\n!!!!\n",
        "reads2.fastq": "@r\nTGCA\n+\n!!!!\n", "ligand.smi": "CCO\n", "slide.svs": "demo", "input.h5ad": "demo",
        "wrapper.py": "print('ok')\n", "spectra.mzML": "demo", "database.fasta": ">p\nMAAA\n", "assembly.fa": ">c\nACGT\n",
        "model.gguf": "model", "prompt.txt": "Summarize approved evidence only.\n",
    }
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    cases = {
        "bgzip_compress": {"source": tmp_path / "source.vcf"},
        "minimap2_align": {"reference": tmp_path / "reference.fa", "reads": tmp_path / "reads.fastq"},
        "bwa_mem_align": {"reference": tmp_path / "reference.fa", "reads1": tmp_path / "reads.fastq", "reads2": tmp_path / "reads2.fastq"},
        "obabel_prepare_ligand": {"ligand": tmp_path / "ligand.smi"},
        "openslide_inspect": {"wrapper_script": tmp_path / "wrapper.py", "input": tmp_path / "slide.svs"},
        "scanpy_analyze": {"wrapper_script": tmp_path / "wrapper.py", "input": tmp_path / "input.h5ad"},
        "scvelo_velocity": {"wrapper_script": tmp_path / "wrapper.py", "input": tmp_path / "input.h5ad"},
        "cellrank_fates": {"wrapper_script": tmp_path / "wrapper.py", "input": tmp_path / "input.h5ad"},
        "msgfplus_search": {"spectra": tmp_path / "spectra.mzML", "database_fasta": tmp_path / "database.fasta"},
        "abricate_screen": {"assembly": tmp_path / "assembly.fa"},
        "llama_cpp_infer": {"model": tmp_path / "model.gguf", "prompt_file": tmp_path / "prompt.txt"},
    }
    for key, arguments in cases.items():
        plan = build_engine_plan(key, workdir=tmp_path, **arguments)
        assert plan.command
        assert plan.cwd == str(tmp_path.resolve())
        assert all(Path(item).is_relative_to(tmp_path.resolve()) for item in plan.inputs)
    assert len(plan_catalog()) >= 66
    plan_engine_labels = set(plan_catalog().Engine)
    assert all(spec.label in plan_engine_labels for spec in ENGINE_REGISTRY.values())


def test_step156_manifest_declares_new_depth_layers() -> None:
    manifest = native_portfolio_manifest()
    assert manifest["step156_translational_evidence_engines"] is True
    assert manifest["step156_operational_safety_engines"] is True
    assert manifest["schema"] == "biointel.step156.native-portfolio.v4"
