from __future__ import annotations

import pandas as pd
import pytest

from biointel.biotech.assays import (
    bioprocess_yields,
    enzyme_kinetics,
    growth_metrics,
    qpcr_delta_delta_ct,
    quantify_elisa,
)
from biointel.genomics.phylogeny import consensus_sequence
from biointel.genomics.variants import mask_low_quality_genotypes, parse_vcf, variant_summary
from biointel.projects.cancer_genomics import sample_variant_qc, threshold_sensitivity
from biointel.projects.comparative_genomics import (
    GenomeRecord,
    clean_dna,
    pairwise_variant_table,
    reverse_complement,
)
from biointel.projects.metagenomics_pipeline import (
    differential_abundance_permutation,
    rarefaction_curve,
)
from biointel.projects.ppi import (
    bootstrap_classification_metrics,
    cold_start_validation,
    demo_ppi_pairs,
    train_ppi_classifier,
)
from biointel.proteomics.annotation import annotate_protein
from biointel.systems.pathways import pathway_enrichment
from biointel.transcriptomics.expression import (
    differential_expression,
    filter_low_count_genes,
    normalize_cpm,
)


def test_ppi_threshold_is_reused_and_identifier_conflicts_are_blocked():
    training = demo_ppi_pairs(120)
    result = train_ppi_classifier(training, decision_threshold=0.8)
    assert set(result.predictions["decision_threshold"]) == {0.8}
    intervals = bootstrap_classification_metrics(result.predictions, samples=100)
    assert set(intervals["decision_threshold"]) == {0.8}
    metrics, predictions = cold_start_validation(training, decision_threshold=0.8)
    assert float(metrics.iloc[0]["decision_threshold"]) == 0.8
    assert set(predictions["decision_threshold"]) == {0.8}

    conflicting = training.copy()
    conflicting.loc[1, "protein_a"] = conflicting.loc[0, "protein_a"]
    conflicting.loc[1, "sequence_a"] = conflicting.loc[0, "sequence_a"][::-1]
    with pytest.raises(ValueError, match="exactly one amino-acid sequence"):
        train_ppi_classifier(conflicting)


def test_transcriptomics_uses_selected_normalization_and_batch_design():
    counts = pd.DataFrame(
        {
            "gene": ["G1", "G2", "G3"],
            "A1": [100, 10, 0],
            "A2": [120, 8, 1],
            "B1": [400, 12, 0],
            "B2": [450, 9, 1],
            "C1": [5, 5, 5],
            "C2": [5, 5, 5],
        }
    )
    filtered = filter_low_count_genes(counts, minimum_count=5, minimum_samples=2)
    normalized = normalize_cpm(filtered)
    groups = {"A1": "A", "A2": "A", "B1": "B", "B2": "B", "C1": "C", "C2": "C"}
    batches = {"A1": "X", "A2": "Y", "B1": "X", "B2": "Y", "C1": "X", "C2": "Y"}
    result = differential_expression(
        normalized,
        groups,
        group_a="A",
        group_b="B",
        values_are_log2=True,
        batches=batches,
    )
    assert result["batch_adjusted"].all()
    assert set(result["reference_group"]) == {"A"}
    assert set(result["comparison_group"]) == {"B"}
    with pytest.raises(ValueError, match="must be different"):
        differential_expression(normalized, groups, group_a="A", group_b="A", values_are_log2=True)


def _cancer_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "chromosome": ["1", "1", "1"],
            "position": [1, 2, 3],
            "ref": ["A", "C", "G"],
            "alt": ["G", "T", "A"],
            "gene": ["TP53", "KRAS", "BRAF"],
            "consequence": ["missense_variant"] * 3,
            "vaf": [0.2, 0.2, 0.2],
            "depth": [100, 100, 100],
            "sample": ["S1"] * 3,
            "filter": ["PASS", ".", "TRUE"],
        }
    )


def test_cancer_filter_semantics_are_consistent():
    sensitivity = threshold_sensitivity(_cancer_frame(), depth_values=(20,), vaf_values=(0.05,))
    assert int(sensitivity.iloc[0]["passing_variants"]) == 3
    qc = sample_variant_qc(_cancer_frame())
    assert float(qc.iloc[0]["pass_filter_percent"]) == 100.0


def test_metagenomics_explicit_direction_and_without_replacement_rarefaction():
    relative = pd.DataFrame(
        {
            "taxon": ["T1", "T2"],
            "S1": [0.8, 0.2],
            "S2": [0.7, 0.3],
            "S3": [0.2, 0.8],
            "S4": [0.1, 0.9],
        }
    )
    metadata = pd.DataFrame({"sample": ["S3", "S4", "S1", "S2"], "group": ["B", "B", "A", "A"]})
    result = differential_abundance_permutation(
        relative, metadata, group_a="A", group_b="B", permutations=99
    )
    t1 = result.set_index("taxon").loc["T1"]
    assert t1["group_a"] == "A" and t1["group_b"] == "B"
    assert float(t1["difference"]) > 0

    counts = pd.DataFrame(
        {
            "taxon": ["T1", "T2", "T3"],
            "S1": [8, 2, 0],
            "S2": [7, 3, 0],
            "S3": [2, 7, 1],
            "S4": [1, 8, 1],
        }
    )
    curve = rarefaction_curve(counts, steps=3, replicates=4)
    assert curve["mean_observed_taxa"].max() <= 3


def test_motif_wildcards_protein_consensus_and_pathway_warning():
    protein = annotate_protein("M" * 20 + "HGGFH" + "A" * 20 + "GASAG" + "L" * 20)
    assert "metalloprotease-like motif" in protein.family_hints
    assert "serine hydrolase-like motif" in protein.family_hints
    consensus = consensus_sequence({"p1": "ACDE", "p2": "ACDF", "p3": "ACDG"}, minimum_fraction=0.6)
    assert consensus.endswith("X")
    with pytest.raises(ValueError, match="None of the submitted genes"):
        pathway_enrichment(["NOT_A_REAL_GENE"])


def test_multiallelic_vcf_is_split_with_allele_specific_fields_and_call_masking():
    text = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n"
        "1\t10\trs1\tA\tG,T\t50\tPASS\tAF=0.1,0.2;DP=30\tGT:AD:DP:GQ\t1/2:10,8,12:30:40\n"
    )
    frame = parse_vcf(text)
    assert frame["alt"].tolist() == ["G", "T"]
    assert frame["allele_frequency"].tolist() == [0.1, 0.2]
    assert variant_summary(frame).multiallelic == 1
    masked = mask_low_quality_genotypes(frame, minimum_genotype_quality=50)
    assert all(value["S1"].startswith("./.") for value in masked["samples"])


def test_global_alignment_iupac_and_event_level_indel():
    clean_dna("ACGTRYSWKMBDHVN")
    assert reverse_complement("ACGTRY") == "RYACGT"
    variants = pairwise_variant_table(
        GenomeRecord("query", "ACGTTTACGT"),
        GenomeRecord("reference", "ACGTACGT"),
    )
    insertion = variants[variants["variant_type"] == "Insertion"].iloc[0]
    assert insertion["query_allele"] == "TT"
    assert int(insertion["event_length"]) == 2
    assert "Needleman-Wunsch" in insertion["alignment_method"]


def test_wet_lab_uncertainty_and_qc_enhancements():
    qpcr = pd.DataFrame(
        {
            "sample": ["Control", "Control", "Treatment", "Treatment"],
            "target_ct": [25.0, 25.2, 23.0, 23.1],
            "reference_ct": [20.0, 20.1, 20.0, 20.1],
        }
    )
    qpcr_result = qpcr_delta_delta_ct(qpcr, calibrator_sample="Control")
    assert set(qpcr_result["replicate_qc_status"]) == {"Pass"}
    assert "target_ct_sd" in qpcr_result

    kinetics = enzyme_kinetics([0.1, 0.5, 1, 2, 5], [0.18, 0.65, 1.0, 1.35, 1.65])
    assert "vmax_ci95_lower" in kinetics
    growth = growth_metrics([0, 1, 2, 3, 4], [0.1, 0.15, 0.23, 0.34, 0.4])
    assert growth["log_phase_points"] >= 3

    process = pd.DataFrame(
        {"time": [0, 1, 2], "biomass": [1, 2, 3], "substrate": [10, 8, 6], "product": [0, 1, 2]}
    )
    yields = bioprocess_yields(process)
    assert yields["biomass_yield_regression"] is not None

    elisa = quantify_elisa(
        [0.25, 0.5, 1, 2, 5],
        [0.1, 0.2, 0.35, 0.6, 1.1],
        [0.4],
        blank_absorbance=0.05,
        dilution_factors=[2],
    )
    assert elisa["unknown_results"][0]["dilution_factor"] == 2.0
