from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from biointel.genomics.fastq import (
    FastqRecord,
    detect_phred_offset,
    read_level_metrics,
    trim_record_advanced,
)
from biointel.genomics.phylogeny_advanced import (
    bootstrap_tree,
    build_tree,
    model_distance_matrix,
    progressive_star_alignment,
    root_tree,
    tree_newick,
    trim_alignment,
)
from biointel.genomics.variant_advanced import (
    genome_build_audit,
    normalize_alleles,
    normalize_variant_frame,
    structural_variant_table,
    trio_mendelian_audit,
    validate_reference_alleles,
)
from biointel.omics.integration import (
    canonical_correlation,
    integrate_omics_advanced,
    integrated_nmf,
)
from biointel.projects.cancer_advanced import (
    annotate_research_gene_pack,
    estimate_cancer_cell_fraction,
    expanded_cancer_gene_reference,
    matched_normal_population_filter,
    sample_specific_tmb,
    trinucleotide_signature_matrix,
    validate_cnv_table,
    validate_sv_fusion_table,
)
from biointel.projects.cancer_genomics import demo_cancer_variants, run_cancer_genomics_pipeline
from biointel.projects.comparative_genomics import GenomeRecord
from biointel.projects.pathogen_advanced import (
    alignment_ani,
    gene_pangenome,
    validate_marker_reference_pack,
    window_divergence_scan,
)
from biointel.projects.single_cell import demo_single_cell_counts, run_single_cell_pipeline
from biointel.projects.single_cell_advanced import (
    ambient_rna_audit,
    batch_residualized_embedding,
    cell_cycle_scores,
    graph_cluster_cells,
    graph_cluster_stability,
    simulated_doublet_scores,
)
from biointel.proteomics.advanced import (
    differential_protein_abundance,
    peptide_sequence_coverage,
    scan_domain_signatures,
    tryptic_digest,
    validate_quantitative_proteomics,
)
from biointel.sequence.advanced import (
    alignment_event_table,
    auto_orient_alignment,
    circular_restriction_fragments,
    deduplicate_records,
    motif_search_both_strands,
    near_duplicate_clusters,
    semiglobal_alignment,
    sequence_qc_profile,
)
from biointel.sequence.parser import ParsedSequence
from biointel.structural.advanced import (
    chain_interface_contacts,
    experimental_metadata,
    ramachandran_table,
    residue_contact_network,
    solvent_accessibility,
    structure_quality_report,
)
from biointel.systems.pathways import (
    pathway_enrichment,
    pathway_pack,
    preranked_gsea,
)
from biointel.transcriptomics.advanced import negative_binomial_de, sample_diagnostics

ROOT = Path(__file__).resolve().parents[1]


def test_pathway_universe_is_statistically_valid_and_organism_specific() -> None:
    human = pathway_pack("Homo sapiens")
    mouse = pathway_pack("Mus musculus")
    assert human and mouse
    assert "Murine innate immune sensing" in mouse and "Murine innate immune sensing" not in human
    background = {"TP53", "BRCA1", "BRCA2", "ATM", "KRAS", "EGFR"}
    result = pathway_enrichment({"TP53", "BRCA1"}, pathways=human, universe=background)
    assert not result.empty
    assert result["p_value"].between(0, 1).all()
    assert (result.loc[result["overlap_count"] == 0, "p_value"] == 1).all()
    ranked = pd.DataFrame({"gene": list(background), "score": [4, 3, 2, 1, -1, -2]})
    gsea = preranked_gsea(ranked, pathways=human, permutations=40, random_state=7)
    assert gsea["fdr_bh"].between(0, 1).all()


def test_omics_duplicate_ids_are_blocked_and_multiview_methods_work() -> None:
    duplicate = pd.DataFrame({"sample": ["S1", "S1"], "A": [1, 2]})
    right = pd.DataFrame({"sample": ["S1", "S2"], "B": [2, 3]})
    with pytest.raises(ValueError, match="duplicate sample"):
        integrate_omics_advanced({"RNA": duplicate, "Protein": right})
    left = pd.DataFrame({"sample": ["S1", "S2", "S3", "S4"], "A": [1, 2, 3, 4], "B": [4, 3, 2, 1]})
    right = pd.DataFrame({"sample": ["S1", "S2", "S3", "S5"], "C": [2, 4, 6, 8], "D": [1, 1, 2, 3]})
    integrated = integrate_omics_advanced({"RNA": left, "Protein": right}, join="outer")
    assert len(integrated.sample_audit) == 5
    scores, loadings = integrated_nmf(integrated.integrated, components=2)
    assert len(scores) == 5 and not loadings.empty
    cca_scores, correlations = canonical_correlation(left.iloc[:3], right.iloc[:3])
    assert len(cca_scores) == 3 and correlations["canonical_correlation"].abs().le(1.000001).all()


def test_sequence_suite_handles_circular_strands_orientation_and_deduplication() -> None:
    qc = sequence_qc_profile("AAAAACGTNNNNACGT")
    assert qc.ambiguous_fraction > 0 and qc.longest_homopolymer >= 5
    motifs = motif_search_both_strands("AAAACGTTTT", "ACGT", strands="both")
    assert {"+", "-"}.issubset(set(motifs["strand"]))
    orientation = auto_orient_alignment("ATGCCG", "CGGCAT", sequence_type="dna", mode="global")
    assert orientation["orientation"] == "reverse-complement"
    aligned = semiglobal_alignment("AAACCC", "CCCGGG")
    events = alignment_event_table(aligned["aligned_query"], aligned["aligned_target"])
    assert isinstance(events, pd.DataFrame)
    records = [
        ParsedSequence("a", "AAAA"),
        ParsedSequence("b", "AAAA"),
        ParsedSequence("c", "AAAT"),
    ]
    audit, unique = deduplicate_records(records)
    assert len(unique) == 2 and int(audit["duplicate"].sum()) == 1
    clusters = near_duplicate_clusters(records, identity_threshold=0.70, k=2)
    assert clusters["cluster"].nunique() >= 1
    assert sum(circular_restriction_fragments(100, [10, 60])) == 100


def test_fastq_advanced_encoding_metrics_and_trimming() -> None:
    records = [
        FastqRecord("r1", "ACGTAAAAAA", "IIIIIIIIII"),
        FastqRecord("r2", "NNNNACGT", "!!!!!!!!"),
    ]
    encoding = detect_phred_offset(records)
    assert encoding["offset"] == 33
    metrics = read_level_metrics(records)
    assert {"expected_errors", "gc_percent"}.issubset(metrics.columns)
    trimmed, audit = trim_record_advanced(
        records[0], minimum_quality=30, trim_poly_x=True, poly_x_minimum_run=5, minimum_length=4
    )
    assert trimmed is not None and len(trimmed.sequence) < len(records[0].sequence)
    assert audit["poly_x_trimmed"] == "A"


def test_variant_normalization_reference_sv_and_trio_audits() -> None:
    assert normalize_alleles(10, "AC", "AT") == (11, "C", "T")
    frame = pd.DataFrame(
        {
            "chrom": ["chr1", "1"],
            "pos": [2, 5],
            "ref": ["C", "N"],
            "alt": ["T", "<DEL>"],
            "sample": ["S1", "S1"],
            "samples": [
                {"father": "0/0", "mother": "0/0", "child": "1/1"},
                {"father": "0/1", "mother": "0/1", "child": "0/1"},
            ],
        }
    )
    normalized, normalization_audit = normalize_variant_frame(frame)
    assert len(normalization_audit) == len(frame)
    reference_audit, summary = validate_reference_alleles(normalized, {"1": "ACGTACGT"})
    assert summary.variants_checked >= 1 and not reference_audit.empty
    assert len(structural_variant_table(normalized)) == 1
    build_audit = genome_build_audit(normalized, "GRCh38")
    assert build_audit["canonical_for_build"].all()
    trio = trio_mendelian_audit(normalized, father="father", mother="mother", child="child")
    assert (trio["mendelian_status"] == "violation").sum() == 1


def test_transcriptomics_negative_binomial_model_and_sample_diagnostics() -> None:
    rng = np.random.default_rng(4)
    genes = [f"G{i}" for i in range(60)]
    samples = [f"S{i}" for i in range(8)]
    matrix = rng.poisson(30, size=(60, 8))
    matrix[:5, 4:] += rng.poisson(80, size=(5, 4))
    counts = pd.DataFrame(matrix, columns=samples)
    counts.insert(0, "gene", genes)
    groups = {sample: ("A" if index < 4 else "B") for index, sample in enumerate(samples)}
    results, audit = negative_binomial_de(counts, groups, reference_group="A", comparison_group="B")
    assert audit.full_rank and results["fdr_bh"].between(0, 1).all()
    assert results.set_index("gene").loc["G0", "log2_fold_change"] > 0
    diagnostics, correlation, distance = sample_diagnostics(counts)
    assert len(diagnostics) == 8 and correlation.shape == distance.shape == (8, 8)


def test_protein_annotation_digest_coverage_and_quantitative_de() -> None:
    sequence = "MAVAIKAAAAAAAHRDAAAAAADFGAAGDSGGPAAAAKPEPTIDER"
    domains = scan_domain_signatures(sequence)
    assert not domains.empty
    peptides = tryptic_digest(sequence, minimum_length=3, maximum_length=30)
    assert not peptides.empty
    coverage_rows, coverage = peptide_sequence_coverage(sequence, peptides["peptide"].head(3))
    assert not coverage_rows.empty and 0 <= coverage["coverage_percent"] <= 100
    quant = pd.DataFrame(
        {
            "protein": ["P1"] * 6 + ["P2"] * 6,
            "sample": [f"S{i}" for i in range(6)] * 2,
            "condition": ["A"] * 3 + ["B"] * 3 + ["A"] * 3 + ["B"] * 3,
            "intensity": [10, 11, 9, 30, 31, 29, 20, 21, 19, 20, 21, 19],
        }
    )
    validated = validate_quantitative_proteomics(quant)
    metadata = pd.DataFrame({"sample": [f"S{i}" for i in range(6)], "group": ["A"] * 3 + ["B"] * 3})
    de = differential_protein_abundance(validated, metadata, group_a="A", group_b="B")
    assert de.set_index("protein").loc["P1", "log2_fold_change"] > 1


def test_structural_quality_geometry_and_interfaces() -> None:
    pdb_text = (ROOT / "data/bioinformatics_demo/structures/reference_complex_01.pdb").read_text()
    metadata = experimental_metadata(pdb_text, format_hint="pdb")
    quality, quality_summary = structure_quality_report(pdb_text, format_hint="pdb")
    rama = ramachandran_table(pdb_text, format_hint="pdb")
    sasa, sasa_summary = solvent_accessibility(pdb_text, format_hint="pdb")
    contacts, interface_summary = chain_interface_contacts(pdb_text, format_hint="pdb")
    edges, nodes = residue_contact_network(pdb_text, format_hint="pdb")
    assert metadata["format"] == "PDB"
    assert not quality.empty and not sasa.empty and quality_summary["atoms"] > 0
    assert (
        isinstance(rama, pd.DataFrame)
        and isinstance(contacts, pd.DataFrame)
        and isinstance(edges, pd.DataFrame)
    )
    assert (
        isinstance(sasa_summary, pd.DataFrame)
        and isinstance(interface_summary, pd.DataFrame)
        and isinstance(nodes, pd.DataFrame)
    )


def test_phylogeny_alignment_models_bootstrap_and_rooting() -> None:
    raw = {"A": "ACGTACGT", "B": "ACGTTCGT", "C": "ACGACGT", "D": "TCGTACGA"}
    aligned = progressive_star_alignment(raw)
    assert len({len(value) for value in aligned.values()}) == 1
    trimmed, audit = trim_alignment(aligned, maximum_gap_fraction=0.75)
    assert int(audit["kept"].sum()) > 0
    matrix = model_distance_matrix(trimmed, model="jukes-cantor")
    assert matrix.shape == (4, 4) and np.allclose(np.diag(matrix), 0.0)
    tree = build_tree(trimmed, method="neighbor-joining", model="jukes-cantor")
    tree, support = bootstrap_tree(
        trimmed, method="neighbor-joining", model="p-distance", replicates=10, random_state=3
    )
    rooted = root_tree(tree, outgroup="D")
    assert "D" in tree_newick(rooted) and not support.empty


def test_pathogen_ani_marker_provenance_pangenome_and_divergence() -> None:
    reference = GenomeRecord("R", "ATG" + "GCT" * 30 + "TAA")
    query = GenomeRecord("Q", "ATG" + "GCT" * 28 + "GTTGCTTAA")
    ani = alignment_ani(query, reference)
    assert 0 <= ani.aligned_identity_percent <= 100
    markers = pd.DataFrame(
        {
            "marker_id": ["m1"],
            "marker_name": ["demo"],
            "sequence": ["ATGGCTAA"],
            "organism": ["research"],
            "marker_type": ["identity"],
            "source": ["local"],
            "source_version": ["1"],
            "accession": ["LOCAL-DEMO-001"],
            "review_status": ["demo"],
        }
    )
    assert validate_marker_reference_pack(markers).loc[0, "provenance_complete"]
    assignments, presence, summary = gene_pangenome(
        [reference, query], minimum_amino_acids=5
    )
    assert not assignments.empty and not presence.empty and not summary.empty
    assert {"R", "Q"}.issubset(presence.columns)
    divergence = window_divergence_scan(query, reference, window=30, step=15)
    assert not divergence.empty


def test_single_cell_graph_umap_doublet_ambient_batch_and_stability() -> None:
    counts = demo_single_cell_counts(genes=320, cells=72, clusters=3)
    result = run_single_cell_pipeline(
        counts, min_counts=50, min_genes=20, top_variable_genes=120, n_clusters=3
    )
    graph = graph_cluster_cells(
        result.normalized,
        result.variable_genes,
        neighbors=8,
        resolution=0.8,
        compute_umap=False,
    )
    assert {"UMAP1", "UMAP2", "cluster"}.issubset(graph.embedding.columns)
    doublets = simulated_doublet_scores(result.normalized, result.variable_genes, random_state=4)
    ambient_cells, ambient_genes = ambient_rna_audit(result.filtered_counts)
    cycles = cell_cycle_scores(result.normalized)
    metadata = pd.DataFrame(
        {"cell": graph.embedding["cell"], "batch": ["A", "B"] * (len(graph.embedding) // 2)}
    )
    corrected = batch_residualized_embedding(result.normalized, result.variable_genes, metadata)
    stability = graph_cluster_stability(
        result.normalized, result.variable_genes, neighbors=8, resolution=0.8, random_seeds=(3, 5)
    )
    assert (
        len(doublets) == len(graph.embedding) == len(ambient_cells) == len(cycles) == len(corrected)
    )
    assert not ambient_genes.empty and stability["adjusted_rand_index"].between(-1, 1).all()


def test_cancer_matched_normal_tmb_ccf_cnv_sv_and_sbs96() -> None:
    variants = demo_cancer_variants(samples=3, variants_per_sample=20)
    variants["normal_vaf"] = 0.0
    variants["population_af"] = 0.0001
    variants["trinucleotide_context"] = "ACA"
    base = run_cancer_genomics_pipeline(variants, min_depth=10, min_vaf=0.01)
    annotated = annotate_research_gene_pack(base.variants)
    filtered, audit = matched_normal_population_filter(annotated)
    assert len(expanded_cancer_gene_reference()) >= 100 and audit["variants_flagged"].sum() == 0
    samples = sorted(filtered["sample"].unique())
    territory = pd.DataFrame({"sample": samples, "callable_megabases": [20, 25, 30]})
    tmb = sample_specific_tmb(filtered, territory)
    metadata = pd.DataFrame(
        {
            "sample": samples,
            "purity": [0.6] * 3,
            "total_copy_number": [2] * 3,
            "mutant_copy_number": [1] * 3,
        }
    )
    ccf = estimate_cancer_cell_fraction(filtered, metadata)
    cnv = validate_cnv_table(
        pd.DataFrame(
            {
                "sample": [samples[0]],
                "chromosome": ["1"],
                "start": [1],
                "end": [1000],
                "copy_number": [1],
            }
        )
    )
    sv = validate_sv_fusion_table(
        pd.DataFrame(
            {
                "sample": [samples[0]],
                "event_type": ["fusion"],
                "gene_1": ["EML4"],
                "gene_2": ["ALK"],
                "support": [7],
            }
        )
    )
    signature = trinucleotide_signature_matrix(filtered)
    assert len(tmb) == 3 and ccf["estimated_cancer_cell_fraction"].notna().all()
    assert cnv.loc[0, "event"] == "loss" and sv.loc[0, "passes_support"] and not signature.empty


def test_step59_reference_pack_manifest_is_checksum_complete() -> None:
    root = ROOT / "data/reference_packs/bioinformatics_step59"
    manifest = json.loads((root / "manifest.json").read_text())
    import hashlib

    for item in manifest["files"]:
        payload = (root / item["path"]).read_bytes()
        assert len(payload) == item["bytes"]
        assert hashlib.sha256(payload).hexdigest() == item["sha256"]


@pytest.mark.parametrize(
    "page",
    [
        "pages/1_Sequence_Analyzer.py",
        "pages/2_Sequence_Comparison.py",
        "pages/16_Batch_Sequence_Analysis.py",
        "pages/56_FASTQ_Genomics_QC.py",
        "pages/57_Variant_Annotation_Workbench.py",
        "pages/59_Transcriptomics_Expression_Lab.py",
        "pages/60_Protein_Annotation_Proteomics.py",
        "pages/61_Structural_Bioinformatics.py",
        "pages/63_Pathway_Network_Analysis.py",
        "pages/66_Omics_Integration_Hub.py",
        "pages/68_Alignment_Phylogeny.py",
        "pages/79_Comparative_Pathogen_Genomics.py",
        "pages/80_Single_Cell_Heterogeneity.py",
        "pages/81_Cancer_Genomics.py",
    ],
)
def test_step59_all_bioinformatics_pages_render(page: str) -> None:
    app = AppTest.from_file(str(ROOT / page), default_timeout=180).run()
    assert not app.exception, page
    assert len(app.markdown) > 0, page
