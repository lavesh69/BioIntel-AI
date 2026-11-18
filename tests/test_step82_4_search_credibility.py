from __future__ import annotations

import time
from pathlib import Path

from biointel.scientific.credibility import (
    _official_https,
    build_scientific_credibility_audit,
)
from biointel.ui.navigation import search_page_matches, search_pages
from biointel.ui.search_quality import (
    correct_query,
    damerau_levenshtein_distance,
    search_quality_metrics,
    suggest_query,
)

ROOT = Path(__file__).resolve().parents[1]

TYPO_CASES = (
    ("sequece", "sequence_analyzer"),
    ("seqence", "sequence_analyzer"),
    ("sequnce", "sequence_analyzer"),
    ("transriptomics", "transcriptomics_expression"),
    ("transcripomics", "transcriptomics_expression"),
    ("protien", "protein_annotation"),
    ("proteimics", "protein_annotation"),
    ("metgenomics", "metagenomics_pipeline"),
    ("metagenmoics", "metagenomics_pipeline"),
    ("varient", "variant_annotation"),
    ("vairant", "variant_annotation"),
    ("admat", "admet_discovery"),
    ("crisprr", "primer_crispr_codon"),
    ("strcuture", "structural_bioinformatics"),
    ("structral", "structural_bioinformatics"),
    ("singel cell", "single_cell_heterogeneity"),
    ("singlecell", "single_cell_heterogeneity"),
    ("durg target", "dti_predictor"),
    ("drug traget", "dti_predictor"),
    ("fastqc", "fastq_genomics_qc"),
    ("bioinfomatics", "bioinformatics_capabilities"),
    ("bioinformatcs", "bioinformatics_capabilities"),
    ("qpcrr", "wetlab_biotechnology"),
    ("documention", "document_intelligence"),
    ("docmentation", "document_intelligence"),
    ("worklfow", "workflow_dashboard"),
    ("worfklow", "workflow_dashboard"),
    ("relese", "scientific_release_gate"),
    ("moleclue", "drug_analyzer"),
    ("discoverey", "discovery_command_center"),
    ("genmoics", "fastq_genomics_qc"),
    ("microbiom", "microbiology_metagenomics"),
    ("cancergenomics", "cancer_genomics"),
    ("aligment", "sequence_comparison"),
    ("analizer", "sequence_analyzer"),
    ("datset", "dataset_registry"),
    ("modle training", "model_training"),
    ("potein interaction", "ppi_interaction_ml"),
    ("mass spectrometery", "protein_annotation"),
    ("flow cytometery", "lab_analytics_command_center"),
    ("clincal trials", "connected_data_explorer"),
    ("pubmed serch", "connected_data_explorer"),
)


def test_typo_tolerance_matrix_is_perfect_top1() -> None:
    metrics = search_quality_metrics(TYPO_CASES, search_pages)
    assert metrics["cases"] == len(TYPO_CASES)
    assert metrics["catalogue_recall"] == 1.0
    assert metrics["top1_accuracy"] == 1.0
    assert metrics["top3_accuracy"] == 1.0
    assert metrics["mean_reciprocal_rank"] == 1.0


def test_typo_search_is_fast_and_explains_matches() -> None:
    started = time.perf_counter()
    for query, expected in TYPO_CASES:
        matches = search_page_matches(query)
        assert matches and matches[0].page.key == expected
        assert matches[0].score > 0
        assert matches[0].reasons
        assert matches[0].corrected_query
    elapsed = time.perf_counter() - started
    assert elapsed < 1.5


def test_relevance_outranks_favourite_during_active_query() -> None:
    results = search_pages("sequece", favourites={"batch_sequence"})
    assert results[0].key == "sequence_analyzer"


def test_transposition_and_did_you_mean_are_deterministic() -> None:
    assert damerau_levenshtein_distance("traget", "target") == 1
    assert correct_query("Durg Traget") == "drug target"
    assert suggest_query("transriptomics", ["transcriptomics", "proteomics"]) == "transcriptomics"


def test_provider_host_aliases_are_strict() -> None:
    assert _official_https("uniprot", "rest.uniprot.org", "https://www.uniprot.org/uniprotkb/P69905/entry")
    assert _official_https("clinvar", "eutils.ncbi.nlm.nih.gov", "https://www.ncbi.nlm.nih.gov/clinvar/")
    assert _official_https("go", "geneontology.org", "https://go.org")
    assert not _official_https("uniprot", "rest.uniprot.org", "https://uniprot.org.evil.example/data")
    assert not _official_https("clinvar", "eutils.ncbi.nlm.nih.gov", "http://www.ncbi.nlm.nih.gov/clinvar/")


def test_credibility_controls_are_10_but_real_evidence_is_not_inflated() -> None:
    report = build_scientific_credibility_audit(ROOT)
    assert report["credibility_controls_score"] == 10.0
    assert report["implementation_score"] == 10.0
    assert report["summary"]["evidence_chain_ok"] is True
    assert report["summary"]["validation_chain_ok"] is True
    assert report["summary"]["official_https_snapshots"] == report["summary"]["snapshots"]
    assert report["verifiable_evidence_score"] < 10.0
    assert report["combined_credibility_score"] < 10.0
    assert report["release_claim"] != "evidence-qualified"
    assert "Scientific evidence-control implementation" in report["eligible_claims"]
    assert "Independent external DTI validation" in report["blocked_claims"]
    assert "Blinded prospective DTI validation" in report["blocked_claims"]
    assert "Independent wet-lab replication" in report["blocked_claims"]
    assert report["summary"]["strictly_rejected_studies"] >= 1


def test_version_is_current_semantic_release() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert tuple(map(int, version.split("."))) >= (8, 2, 6)
