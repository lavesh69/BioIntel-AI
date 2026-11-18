from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_family_genetics_detects_denovo_compound_het_and_identity() -> None:
    from biointel.step121.family_genetics import analyse_family_variants

    pedigree = pd.DataFrame(
        [
            ["F1", "F", "0", "0", 1, 1],
            ["F1", "M", "0", "0", 2, 1],
            ["F1", "C", "F", "M", 1, 2],
        ],
        columns=["family_id", "individual_id", "father_id", "mother_id", "sex", "phenotype"],
    )
    variants = pd.DataFrame(
        [
            ["v1", "G1", "F", "0/0", 30, 0.00, 0.0001],
            ["v1", "G1", "M", "0/0", 30, 0.00, 0.0001],
            ["v1", "G1", "C", "0/1", 40, 0.50, 0.0001],
            ["v2", "G2", "F", "0/1", 30, 0.50, 0.001],
            ["v2", "G2", "M", "0/0", 30, 0.00, 0.001],
            ["v2", "G2", "C", "0/1", 40, 0.50, 0.001],
            ["v3", "G2", "F", "0/0", 30, 0.00, 0.001],
            ["v3", "G2", "M", "0/1", 30, 0.50, 0.001],
            ["v3", "G2", "C", "0/1", 40, 0.50, 0.001],
        ],
        columns=["variant_id", "gene", "sample_id", "genotype", "depth", "alt_fraction", "population_af"],
    )
    result = analyse_family_variants(pedigree, variants)
    assert len(result.de_novo_candidates) == 1
    assert result.de_novo_candidates.iloc[0]["variant_id"] == "v1"
    assert len(result.compound_heterozygous) == 1
    assert set(result.compound_heterozygous.iloc[0][["maternal_variant", "paternal_variant"]]) == {"v2", "v3"}
    assert result.release_gate["diagnostic_release_ready"] is False
    assert result.manifest["schema"] == "biointel.step121.family_genetics.v1"


def test_model_assurance_outputs_calibration_ood_stability_and_safeguards() -> None:
    from biointel.step121.model_assurance import run_assurance_suite

    rng = np.random.default_rng(7)
    n = 180
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    group = rng.choice(["A", "B"], n)
    target = (1.2 * x1 - 0.7 * x2 + 0.4 * (group == "B") + rng.normal(0, 0.5, n) > 0).astype(int)
    frame = pd.DataFrame({"x1": x1, "x2": x2, "group": group, "target": target})
    result = run_assurance_suite(frame, target_column="target", group_column="group", stability_repeats=3)
    assert result.task == "classification"
    assert {"roc_auc", "balanced_accuracy", "brier"}.issubset(result.metrics.columns)
    assert not result.calibration.empty
    assert not result.ood_scores.empty
    assert not result.explanation_stability.empty
    assert not result.feature_effects.empty
    assert result.release_gate["production_release_ready"] is False
    assert "causality" in result.release_gate["boundary"].lower()


def test_microbiology_isolate_calls_typing_genes_and_concordance() -> None:
    from biointel.step121.microbiology_isolate import analyse_isolate, parse_fasta_text

    locus_a = "ATGCGTACGTAGCTAGCTAGCGGATCCGATCGATCGATCGATCG"
    locus_b = "TTGCAACCGGTTAACCGGTTAACCGGTTAGCTAGCTAGCTAGCTA"
    amr = "GGTACCGGTACCGGTACCGGTACCGGTACCGGTACC"
    fasta = f">c1\n{locus_a * 4}{amr * 3}\n>c2\n{locus_b * 4}\n"
    taxonomy = pd.DataFrame([["Taxon A", locus_a * 3 + locus_b * 3]], columns=["taxon", "sequence"])
    alleles = pd.DataFrame([["abc", "1", locus_a], ["xyz", "4", locus_b]], columns=["locus", "allele", "sequence"])
    profiles = pd.DataFrame([["ST1", "1", "4"]], columns=["sequence_type", "abc", "xyz"])
    genes = pd.DataFrame([["geneA", amr, "AMR", "drugx", "2026.1"]], columns=["gene", "sequence", "category", "phenotype", "database_release"])
    phenotype = pd.DataFrame([["drugx", "resistant"]], columns=["drug", "phenotype"])
    result = analyse_isolate(
        parse_fasta_text(fasta),
        taxonomy_references=taxonomy,
        allele_catalog=alleles,
        mlst_profiles=profiles,
        gene_catalog=genes,
        phenotype=phenotype,
    )
    assert set(result.mlst_calls["call_status"]) == {"called"}
    assert set(result.mlst_calls["sequence_type"]) == {"ST1"}
    assert bool(result.gene_hits.iloc[0]["present"])
    assert bool(result.concordance.iloc[0]["concordant"])
    assert result.release_gate["confirmatory_release_ready"] is False


def test_resource_bounded_automl_is_leakage_safe_and_exports_artifact() -> None:
    from biointel.step121.automl import resource_bounded_automl

    rng = np.random.default_rng(9)
    n = 140
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    category = rng.choice(["A", "B"], n)
    target = (x1 - 0.8 * x2 + 0.5 * (category == "B") > 0).astype(int)
    frame = pd.DataFrame({"x1": x1, "x2": x2, "category": category, "target": target})
    result = resource_bounded_automl(frame, target_column="target", cv_folds=3, max_candidates=2, max_rows=500)
    assert len(result.leaderboard) == 2
    assert list(result.leaderboard["rank"]) == [1, 2]
    assert len(result.artifact_bytes) > 500
    assert result.search_manifest["optuna_used"] is False
    assert result.search_manifest["artifact_sha256"]
    assert result.model_card["release_ready"] is False
    assert not result.feature_importance.empty


def test_citation_engine_normalizes_deduplicates_conflicts_and_exports() -> None:
    from biointel.step121.citations import build_citation_workspace, export_bibtex, export_ris

    frame = pd.DataFrame(
        [
            ["C1", "Exact claim", "https://doi.org/10.1000/ABC.1", "", "Study A", 2024, "cohort", "support", "high", False],
            ["C1", "Exact claim", "10.1000/abc.1", "", "Study A duplicate", 2024, "cohort", "support", "medium", False],
            ["C1", "Exact claim", "10.1000/abc.2", "", "Study B", 2025, "case-control", "oppose", "medium", False],
        ],
        columns=["claim_id", "claim_text", "doi", "pmid", "title", "year", "study_design", "evidence_direction", "confidence", "retracted"],
    )
    result = build_citation_workspace(frame)
    assert result.citations["record_key"].nunique() == 2
    assert int(result.citations["duplicate_count"].max()) == 2
    assert bool(result.claim_summary.iloc[0]["conflict_present"])
    assert not result.conflict_review.empty
    assert "@article" in export_bibtex(result.citations)
    assert "TY  - JOUR" in export_ris(result.citations)
    assert result.release_gate["publication_release_ready"] is False


def test_organoid_plate_normalization_dose_response_and_embedding() -> None:
    from biointel.step121.organoid import analyse_organoid_experiment

    rng = np.random.default_rng(12)
    rows = []
    for plate_row in list("ABCD"):
        for plate_column in range(1, 9):
            concentration = [0.01, 0.1, 1.0, 10.0][(plate_column - 1) % 4]
            compound = "Drug" if plate_column > 2 else "Vehicle"
            for obj in range(3):
                response = 12000 / (1 + concentration / 0.8) if compound == "Drug" else 12000
                rows.append(
                    {
                        "object_id": f"{plate_row}{plate_column}_{obj}",
                        "well": f"{plate_row}{plate_column:02d}",
                        "plate_row": plate_row,
                        "plate_column": plate_column,
                        "compound": compound,
                        "concentration": concentration,
                        "control_type": "negative" if compound == "Vehicle" else "sample",
                        "volume_um3": response + rng.normal(0, 250),
                        "sphericity": rng.normal(0.8, 0.03),
                        "intensity": rng.normal(1000, 80),
                        "image_id": f"IMG-{plate_row}{plate_column}",
                        "replicate": obj + 1,
                    }
                )
    result = analyse_organoid_experiment(pd.DataFrame(rows), value_column="volume_um3")
    assert "plate_normalized_value" in result.normalized_measurements.columns
    assert "robust_z" in result.normalized_measurements.columns
    assert not result.morphology_embedding.empty
    assert not result.dose_response.empty
    assert result.release_gate["scientific_release_ready"] is False


def test_cross_domain_evidence_adjudication_and_release_gate() -> None:
    from biointel.step121.evidence import build_evidence_workspace

    frame = pd.DataFrame(
        [
            ["E1", "genomics", "V1", "Claim", "support", "cohort", "doi:x", "v1", True, "R1", "accepted", "CC-BY"],
            ["E1", "genomics", "V1", "Claim", "support", "cohort", "doi:x", "v1", True, "R2", "accepted", "CC-BY"],
            ["E2", "imaging", "I1", "Other", "oppose", "imaging study", "local:y", "v2", False, "R1", "pending", "internal"],
        ],
        columns=["evidence_id", "domain", "subject_id", "claim", "direction", "study_design", "source", "version", "independent", "reviewer_id", "review_decision", "license"],
    )
    result = build_evidence_workspace(frame)
    adjudicated = result.adjudication.set_index("evidence_id")
    assert adjudicated.loc["E1", "adjudication_status"] == "accepted_by_independent_reviewers"
    assert set(result.domain_summary["domain"]) == {"genomics", "imaging"}
    assert not result.graph_edges.empty
    assert result.release_gate["scientific_release_ready"] is False


def test_step121_capability_contracts_and_page_integration() -> None:
    from biointel.scientific_depth.capability import CAPABILITY_SPECS

    keys = {
        "rare_variant_family",
        "explainable_ai_assurance",
        "microbiology_metagenomics",
        "ml_autolab",
        "evidence_citation_engine",
        "organoid_3d",
        "real_evidence_studio",
    }
    assert keys.issubset(CAPABILITY_SPECS)
    for key in keys:
        spec = CAPABILITY_SPECS[key]
        assert len(spec.stages) >= 6
        assert any(stage.mode == "external-validation" for stage in spec.stages)
        assert spec.release_blockers

    pages = {
        "147_Rare_Variant_Burden_Family_Genetics_Lab.py": "render_family_genetics_upgrade",
        "128_Explainable_AI_and_Model_Assurance_Center.py": "render_model_assurance_upgrade",
        "65_Microbiology_Metagenomics.py": "render_microbiology_isolate_upgrade",
        "34_ML_AutoLab.py": "render_automl_upgrade",
        "155_Scientific_Evidence_Citation_Engine.py": "render_citation_upgrade",
        "142_Organoid_3D_Cell_Model_Analytics.py": "render_organoid_upgrade",
        "46_Real_Evidence_Studio.py": "render_real_evidence_upgrade",
    }
    for filename, token in pages.items():
        assert token in (ROOT / "pages" / filename).read_text(encoding="utf-8")
