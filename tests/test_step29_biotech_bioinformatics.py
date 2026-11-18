from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from biointel import __version__
from biointel.api.main import app
from biointel.biotech.assays import (
    bioprocess_yields,
    enzyme_kinetics,
    qpcr_delta_delta_ct,
    quantify_elisa,
)
from biointel.biotech.experimental_design import randomized_assignment, two_group_sample_size
from biointel.chemistry.admet import profile_admet
from biointel.genomics.annotations import annotation_summary, parse_gff
from biointel.genomics.assembly import assembly_metrics
from biointel.genomics.codon import optimize_protein
from biointel.genomics.design import design_primer_pairs, find_crispr_guides
from biointel.genomics.fastq import fastq_qc, parse_fastq, trim_fastq
from biointel.genomics.phylogeny import consensus_sequence, distance_matrix, upgma_newick
from biointel.genomics.variants import filter_variants, parse_vcf, variant_summary
from biointel.microbiology.metagenomics import approximate_ani, diversity_metrics
from biointel.omics.integration import integrate_omics, integrated_pca
from biointel.proteomics.annotation import annotate_protein
from biointel.structural.pdb_analysis import ligand_contacts, structure_summary
from biointel.systems.pathways import pathway_enrichment
from biointel.transcriptomics.expression import (
    differential_expression,
    expression_summary,
    normalize_cpm,
    pca_samples,
)
from biointel.ui.navigation import PAGE_CATALOG

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "bioinformatics_demo"


def test_step29_version_navigation_and_demo_files():
    assert __version__ == (ROOT / "VERSION").read_text().strip()
    assert len(PAGE_CATALOG) >= 71
    assert {p.key for p in PAGE_CATALOG} >= {
        "fastq_genomics_qc",
        "variant_annotation",
        "wetlab_biotechnology",
        "bioinformatics_capabilities",
    }
    assert len(list(DEMO.iterdir())) >= 13


def test_fastq_qc_and_trimming():
    records = parse_fastq((DEMO / "demo_reads.fastq").read_text())
    result = fastq_qc(records)
    assert result.reads == 20000 and result.bases == 3000000
    assert result.q20_percent > 90
    trimmed, summary = trim_fastq(
        records, adapter="AGATCGGAAGAG", minimum_quality=20, minimum_length=30
    )
    assert summary["input_reads"] == 20000
    assert len(trimmed) <= 20000


def test_vcf_and_gff_workflows():
    variants = parse_vcf((DEMO / "demo_variants.vcf").read_text())
    summary = variant_summary(variants)
    assert summary.variants == 5000 and summary.snps > 3000 and summary.indels > 0
    assert len(filter_variants(variants, minimum_quality=20)) < 5000
    features = parse_gff((DEMO / "demo_annotations.gff3").read_text())
    ann = annotation_summary(features)
    assert ann.genes == 2000 and ann.exons == 6000 and ann.cds == 6000


def test_assembly_metrics():
    from biointel.sequence.parser import parse_sequences_text

    records = parse_sequences_text((DEMO / "demo_assembly.fasta").read_text(), max_records=1000)
    metrics = assembly_metrics([r.sequence for r in records])
    assert metrics.sequences == 500 and metrics.n50 >= 5000 and metrics.total_bases > 1500000


def test_primer_crispr_and_codon_design():
    from biointel.sequence.parser import parse_sequences_text

    dna = parse_sequences_text((DEMO / "demo_dna_template.fasta").read_text())[0].sequence
    pairs = design_primer_pairs(dna, minimum_product=100, maximum_product=500, maximum_pairs=10)
    assert pairs and all(100 <= p.product_size <= 500 for p in pairs)
    guides = find_crispr_guides(dna)
    assert guides and all(len(g.sequence) == 20 for g in guides)
    optimized = optimize_protein("MKWVTFISLLFLFSSAYSRG", host="ecoli", avoid_sites=["GAATTC"])
    assert len(optimized.optimized_dna) == len(optimized.protein_sequence) * 3


def test_transcriptomics_workflow():
    frame = pd.read_csv(DEMO / "demo_expression_counts.csv")
    summary = expression_summary(frame)
    assert summary.genes == 5000 and summary.samples == 24
    normalized = normalize_cpm(frame)
    assert normalized.shape == frame.shape
    groups = {
        c: ("control" if c.startswith("CTRL") else "treated") for c in frame.columns if c != "gene"
    }
    de = differential_expression(frame, groups)
    assert len(de) == 5000 and de.iloc[0]["fdr_bh"] <= 1
    pca = pca_samples(frame)
    assert {"PC1", "PC2"} <= set(pca.columns)


def test_protein_structure_and_admet():
    protein = (DEMO / "demo_protein.fasta").read_text().splitlines()[1]
    annotation = annotate_protein(protein)
    assert annotation.length == len(protein)
    pdb = (DEMO / "demo_structure.pdb").read_text()
    structure = structure_summary(pdb)
    assert structure.atoms > 30 and structure.ligands.get("LIG") == 1
    assert ligand_contacts(pdb)
    admet = profile_admet("CC(=O)OC1=CC=CC=C1C(=O)O")
    assert admet.lipinski_pass is True and admet.molecular_weight > 100


def test_pathway_biotech_microbiology_and_multiomics():
    enrich = pathway_enrichment(["TP53", "BRCA1", "ATM", "RAD51", "AKT1", "PTEN"])
    assert len(enrich) >= 5 and enrich.iloc[0]["overlap_count"] > 0
    qpcr = qpcr_delta_delta_ct(pd.read_csv(DEMO / "demo_qpcr.csv"), calibrator_sample="CTRL")
    assert "relative_expression" in qpcr.columns
    kinetics = pd.read_csv(DEMO / "demo_enzyme_kinetics.csv")
    baseline = (
        kinetics[kinetics["inhibitor_condition"] == "none"]
        .groupby("substrate_mM", as_index=False)["velocity"]
        .mean()
    )
    fit = enzyme_kinetics(baseline["substrate_mM"], baseline["velocity"])
    assert fit["vmax"] > fit["km"] and fit["r_squared"] > 0.9
    elisa = pd.read_csv(DEMO / "demo_elisa.csv")
    standards = elisa[elisa["type"] == "standard"]
    unknown = elisa[elisa["type"] == "unknown"]
    quantified = quantify_elisa(
        standards["concentration"], standards["absorbance"], unknown["absorbance"]
    )
    assert quantified["fit"]["r_squared"] > 0.99 and len(quantified["unknown_concentrations"]) == 72
    design = two_group_sample_size(0.8)
    assert design["total"] > 10
    assignment = randomized_assignment([f"S{i}" for i in range(12)], ["Control", "Treatment"])
    assert len(assignment) == 12
    yields = bioprocess_yields(pd.read_csv(DEMO / "demo_bioprocess.csv"))
    assert yields["substrate_consumed"] > 0 and yields["product_gain"] > 0
    diversity = diversity_metrics(pd.read_csv(DEMO / "demo_taxonomy.csv"))
    assert len(diversity) == 40 and (diversity["shannon"] > 0).all()
    ani = approximate_ani("ATGCGTACGTAGCTAGC" * 5, "ATGCGTACGTAGTTAGC" * 5, k=5)
    assert 0 < ani["ani_proxy_percent"] <= 100
    integrated = integrate_omics(
        {
            "rna": pd.read_csv(DEMO / "demo_transcriptomics.csv"),
            "protein": pd.read_csv(DEMO / "demo_proteomics.csv"),
        }
    )
    assert len(integrated) == 24
    assert len(integrated_pca(integrated)) == 24


def test_phylogeny_workflow():
    from biointel.sequence.parser import parse_sequences_text

    records = parse_sequences_text((DEMO / "demo_alignment.fasta").read_text())
    sequences = {r.header: r.sequence for r in records}
    assert len(consensus_sequence(sequences)) == len(records[0].sequence)
    matrix = distance_matrix(sequences)
    assert set(matrix) == set(sequences)
    assert upgma_newick(sequences).endswith(";")


def test_step29_api_endpoints():
    client = TestClient(app)
    fq = client.post(
        "/bioinformatics/fastq/qc",
        json={
            "fastq_text": (DEMO / "demo_reads.fastq").read_text(),
            "minimum_quality": 20,
            "minimum_length": 30,
        },
    )
    assert fq.status_code == 200 and fq.json()["qc"]["reads"] == 20000
    vcf = client.post(
        "/bioinformatics/variants/summary",
        json={"vcf_text": (DEMO / "demo_variants.vcf").read_text(), "minimum_quality": 20},
    )
    assert vcf.status_code == 200 and vcf.json()["summary"]["variants"] == 5000
    admet = client.post("/bioinformatics/admet/profile", json={"smiles": "CCO"})
    assert admet.status_code == 200 and admet.json()["canonical_smiles"] == "CCO"
    pathways = client.post(
        "/bioinformatics/pathways/enrichment", json={"genes": ["TP53", "BRCA1", "ATM"]}
    )
    assert pathways.status_code == 200 and len(pathways.json()["rows"]) >= 5
    aligned = {"a": "ACGTACGT", "b": "ACGTTCGT", "c": "ACGTACGA"}
    phylo = client.post("/bioinformatics/phylogeny", json={"sequences": aligned})
    assert phylo.status_code == 200 and phylo.json()["newick"].endswith(";")
    capabilities = client.get("/bioinformatics/capabilities")
    assert capabilities.status_code == 200 and capabilities.json()["total"] >= 10
