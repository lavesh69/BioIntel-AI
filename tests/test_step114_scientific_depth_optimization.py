from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_depth_profiles_exclude_requested_modules() -> None:
    from biointel.scientific_depth import MODULE_PROFILES

    excluded = {
        "dti_predictor",
        "dti_validation",
        "lims_eln_chain",
        "instrument_integration_v2",
        "lab_instrument_import",
    }
    assert not excluded.intersection(MODULE_PROFILES)
    assert "metabolomics_lipidomics" in MODULE_PROFILES
    assert "population_gwas" in MODULE_PROFILES
    assert "protein_language_design" in MODULE_PROFILES
    assert "scientific_depth_optimization" not in MODULE_PROFILES


def test_metabolomics_depth_qc_and_blank_flags() -> None:
    from biointel.scientific_depth import assess_dataframe

    frame = pd.DataFrame(
        {
            "sample": ["Q1", "Q2", "S1", "S2"],
            "feature": ["M1", "M1", "M2", "M2"],
            "intensity": [100.0, 180.0, 1000.0, 1100.0],
            "blank_intensity": [30.0, 30.0, 10.0, 10.0],
        }
    )
    result = assess_dataframe("metabolomics_lipidomics", frame)
    assert result.summary["records"] == 4
    assert "features_with_cv_gt_30pct" in set(result.metrics["metric"])
    assert "blank_ratio_gt_20pct" in set(result.metrics["metric"])


def test_protein_design_liability_screen() -> None:
    from biointel.scientific_depth import assess_dataframe

    frame = pd.DataFrame(
        {
            "sequence": ["MNNGWWLLLLLL", "ACDEFGHIKLMNPQRSTVWY"],
            "score": [0.8, 0.7],
        }
    )
    result = assess_dataframe("protein_language_design", frame)
    assert "mean_liability_count" in set(result.metrics["metric"])
    assert result.summary["records"] == 2


def test_gwas_qc_and_fdr() -> None:
    from biointel.scientific_depth import assess_dataframe

    frame = pd.DataFrame(
        {
            "variant": ["v1", "v2", "v3"],
            "maf": [0.005, 0.2, 0.3],
            "missingness": [0.01, 0.05, 0.0],
            "p_value": [1e-8, 0.2, 0.8],
        }
    )
    result = assess_dataframe("population_gwas", frame)
    metrics = dict(zip(result.metrics["metric"], result.metrics["value"]))
    assert metrics["variants_maf_lt_1pct"] == 1
    assert metrics["fdr_lt_0_05"] == 1
    assert result.summary["checks_for_review"] >= 1


def test_family_genetics_de_novo_candidate() -> None:
    from biointel.scientific_depth import assess_dataframe

    frame = pd.DataFrame(
        {
            "variant": ["v1", "v2"],
            "proband_gt": ["0/1", "0/0"],
            "mother_gt": ["0/0", "0/0"],
            "father_gt": ["0/0", "0/1"],
        }
    )
    result = assess_dataframe("rare_variant_family", frame)
    metrics = dict(zip(result.metrics["metric"], result.metrics["value"]))
    assert metrics["de_novo_candidates"] == 1


def test_depth_page_and_navigation() -> None:
    assert (ROOT / "pages/168_Scientific_Depth_Optimization_Center.py").is_file()
    navigation = (ROOT / "src/biointel/ui/navigation.py").read_text(encoding="utf-8")
    assert "scientific_depth_optimization" in navigation
    assert "Scientific Depth & Optimization Center" in navigation


def test_excluded_module_sources_are_untouched_from_step113() -> None:
    # Hashes captured from the Step 113 source before Step 114 changes.
    import hashlib

    expected = {
        "pages/6_DTI_Predictor.py": "10767f9c1654df364b2321b743117f9367e24f1d17c6642ace8e378c2fedcf1a",
        "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
        "pages/109_Lab_Instrument_Import_Center.py": "6b8b24f0549593cbe96e6baabc1929b208772d21f48e92ec4630c6835a91d73f",
        "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "85e7812ef3eb05351a0ae28da1a78dc4428b23fe8e8f04e5b41c250363df996f",
        "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
    }
    for relative, digest in expected.items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        assert actual == digest, relative


def test_step114_version() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "13.2.0"


def test_extended_engine_registry_and_safe_plans(tmp_path: Path) -> None:
    from biointel.native.engines import ENGINE_REGISTRY, build_engine_plan

    expected = {
        "vep", "whatshap", "regenie", "saige", "sniffles", "expansionhunter",
        "flye", "hifiasm", "busco", "minigraph", "vg", "odgi", "anarci",
        "scanpy", "scvelo", "cellrank", "msconvert", "llama_cpp",
    }
    assert expected.issubset(ENGINE_REGISTRY)

    reads = tmp_path / "reads.fastq"
    reads.write_text("@r1\nACGT\n+\nIIII\n", encoding="utf-8")
    assembly = tmp_path / "assembly.fasta"
    assembly.write_text(">contig\nACGT\n", encoding="utf-8")
    vcf = tmp_path / "variants.vcf"
    vcf.write_text("##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n", encoding="utf-8")
    antibody = tmp_path / "antibody.fasta"
    antibody.write_text(">ab\nEVQLVESGGGLVQPGGSLRLSCAAS\n", encoding="utf-8")

    flye = build_engine_plan("flye_assemble", workdir=tmp_path, reads=reads, output_dir=tmp_path / "flye", platform="nano-hq", genome_size="5m")
    assert flye.engine_key == "flye"
    assert "--genome-size" in flye.command
    vep = build_engine_plan("vep_annotate", workdir=tmp_path, vcf=vcf, output=tmp_path / "annotated.vcf", assembly="GRCh38")
    assert vep.engine_key == "vep"
    busco = build_engine_plan("busco_assembly", workdir=tmp_path, assembly=assembly, output_parent=tmp_path / "busco", lineage="eukaryota_odb10")
    assert busco.engine_key == "busco"
    anarci = build_engine_plan("anarci_number", workdir=tmp_path, fasta=antibody, output=tmp_path / "numbering.txt")
    assert anarci.engine_key == "anarci"


def test_engine_plan_rejects_unsafe_paths(tmp_path: Path) -> None:
    import pytest
    from biointel.native.engines import build_engine_plan

    outside = tmp_path.parent / "outside.fastq"
    outside.write_text("@r1\nACGT\n+\nIIII\n", encoding="utf-8")
    with pytest.raises(ValueError, match="outside the protected"):
        build_engine_plan("flye_assemble", workdir=tmp_path, reads=outside, output_dir=tmp_path / "flye")
