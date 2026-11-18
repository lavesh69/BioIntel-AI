from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd

from biointel.scientific_depth import (
    MODULE_PROFILES,
    detect_specialist_toolchains,
    native_input_template,
    native_portfolio_manifest,
    native_workflow_catalog,
    reference_readiness,
    run_native_workflow,
    toolchain_summary,
)


def test_native_format_metadata_is_always_tuple() -> None:
    assert len(MODULE_PROFILES) == 80
    for key, profile in MODULE_PROFILES.items():
        assert isinstance(profile.native_formats, tuple), key
        assert profile.native_formats, key
        assert all(isinstance(item, str) and item.strip() for item in profile.native_formats), key


def test_step153_family_map_is_collision_free_and_more_domain_specific() -> None:
    catalog = native_workflow_catalog()
    assert len(catalog) == 80
    assert catalog["workflow_key"].is_unique
    assert catalog["family"].nunique() >= 36
    expected = {
        "genome_editing_safety": "crispr-safety",
        "antibody_biologics": "antibody-engineering",
        "immunoinformatics_vaccine": "vaccine-design",
        "glycomics_glycoproteomics": "glycomics",
        "proteogenomics_neoantigen": "proteogenomics",
        "digital_pathology_foundation": "pathology-ai",
        "pharmacogenomics": "genomic-variant",
        "single_cell_core": "single-cell",
        "epigenomics_chromatin": "epigenomics",
        "amr_surveillance": "amr-analysis",
        "gene_therapy_vector": "gene-therapy",
        "cell_therapy_cart": "cell-therapy",
        "protein_language_design": "protein-design",
        "enzyme_pathway_design": "enzyme-design",
        "structural_bioinformatics_core": "structural-protein",
        "virology_evolution": "virology-evolution",
        "synthetic_biology_core": "synthetic-biology",
    }
    actual = dict(zip(catalog.module_key, catalog.family))
    assert {key: actual[key] for key in expected} == expected


def test_portfolio_availability_semantics_are_honest() -> None:
    manifest = native_portfolio_manifest()
    assert manifest["all_locally_available"] is False
    assert manifest["native_fallbacks_locally_available"] is True
    assert manifest["specialist_toolchains_bundled"] is False
    assert manifest["policy"]["specialist_confirmatory_pipeline_still_required"] is True
    assert "third-party" in manifest["policy"]["availability_field_semantics"]


def test_all_domain_demos_execute_without_unhandled_failure() -> None:
    failures: dict[str, str] = {}
    families: set[str] = set()
    for key in MODULE_PROFILES:
        demo = native_input_template(key, demonstration=True)
        result = run_native_workflow(key, demo)
        families.add(result.family)
        if result.status == "fail":
            failures[key] = "; ".join(
                result.checks.loc[result.checks.status == "fail", "detail"].astype(str).tolist()
            )
        assert result.provenance["engine_version"] == "2.0.0"
        assert result.provenance["schema"] == "biointel.step153.native-provenance.v1"
        assert result.summary["rows_analyzed"] > 0
    assert failures == {}
    assert len(families) >= 36


def test_specialist_domain_outputs_are_generated() -> None:
    cases = {
        "genome_editing_safety": "guide_safety_screen",
        "antibody_biologics": "antibody_developability",
        "immunoinformatics_vaccine": "epitope_candidates",
        "long_read_core": "long_read_summary",
        "rna_isoform_splicing": "isoform_evidence",
        "single_cell_core": "cell_qc",
        "epigenomics_chromatin": "peak_qc",
        "population_gwas": "variant_qc",
        "digital_pathology_foundation": "image_summary",
        "glycomics_glycoproteomics": "psm_fdr",
        "proteogenomics_neoantigen": "psm_fdr",
        "amr_surveillance": "amr_prevalence",
        "gene_therapy_vector": "vector_design_qc",
        "cell_therapy_cart": "cell_therapy_candidate_review",
        "protein_language_design": "protein_design_candidate_qc",
        "enzyme_pathway_design": "enzyme_pathway_feasibility",
        "structural_bioinformatics_core": "structure_validation",
        "virology_evolution": "lineage_summary",
        "synthetic_biology_core": "circuit_evidence",
    }
    for key, table_name in cases.items():
        result = run_native_workflow(key, native_input_template(key, demonstration=True))
        assert table_name in result.tables, key
        assert not result.tables[table_name].empty, key


def test_genomic_variant_workflow_preserves_hwe_and_domain_gates() -> None:
    result = run_native_workflow("population_gwas", native_input_template("population_gwas", demonstration=True))
    table = result.tables["variant_qc"]
    assert {"call_rate", "maf", "hwe_p"}.issubset(table.columns)
    assert table.hwe_p.between(0, 1).all()
    check_names = set(result.checks["check"])
    assert "Population-structure covariates" in check_names
    assert "Genome-build provenance" in check_names


def test_toolchain_readiness_never_counts_native_fallback_as_specialist_tool() -> None:
    frame = detect_specialist_toolchains()
    summary = toolchain_summary(frame)
    assert not frame.empty
    assert not frame.engine.str.startswith("biointel_native::").any()
    assert summary["engines"] == len(frame)
    assert summary["native_fallbacks_are_not_counted_as_specialist_tools"] is True
    assert summary["available"] + summary["missing"] == summary["engines"]


def test_reference_readiness_is_explicitly_unqualified() -> None:
    root = Path(__file__).resolve().parents[1]
    frame = reference_readiness(root, ["population_gwas", "metabolomics_lipidomics"])
    assert not frame.empty
    assert frame["qualification_required"].all()
    assert {"module_key", "reference", "local_candidate_detected", "candidate_paths"}.issubset(frame.columns)


def test_no_duplicate_dictionary_key_for_family_outputs() -> None:
    source = Path("src/biointel/scientific_depth/native_workflows.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        target = node.target if isinstance(node, ast.AnnAssign) else None
        if isinstance(target, ast.Name) and target.id == "_FAMILY_OUTPUTS":
            assert isinstance(node.value, ast.Dict)
            keys = [ast.literal_eval(key) for key in node.value.keys]
            assert len(keys) == len(set(keys))
            break
    else:
        raise AssertionError("_FAMILY_OUTPUTS was not found")


def test_survival_adds_univariate_cox_and_ph_diagnostics() -> None:
    result = run_native_workflow("clinical_biomarker_survival", native_input_template("clinical_biomarker_survival", demonstration=True))
    cox = result.tables["cox_univariate"]
    assert not cox.empty
    assert {"hazard_ratio_per_sd", "ci95_low", "ci95_high", "ph_schoenfeld_p"}.issubset(cox.columns)
    assert (cox["hazard_ratio_per_sd"] > 0).all()


def test_pharmacovigilance_adds_transparent_shrinkage_and_provenance_gates() -> None:
    result = run_native_workflow(
        "pharmacovigilance_intelligence",
        native_input_template("pharmacovigilance_intelligence", demonstration=True),
        metadata={"coding_dictionary_version": "demo-v1"},
    )
    table = result.tables["disproportionality_signals"]
    assert {"shrunk_ror_proxy", "shrinkage_weight"}.issubset(table.columns)
    assert table["shrinkage_weight"].between(0, 1).all()
    assert "Coding dictionary version" in set(result.checks["check"])
    assert "Exposure denominator" in set(result.checks["check"])
