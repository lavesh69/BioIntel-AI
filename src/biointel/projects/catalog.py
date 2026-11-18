from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BiotechnologyProject:
    code: str
    key: str
    title: str
    short_title: str
    icon: str
    domain: str
    objective: str
    workflow: tuple[str, ...]
    deliverables: tuple[str, ...]
    tags: tuple[str, ...]


PROJECT_CATALOG: tuple[BiotechnologyProject, ...] = (
    BiotechnologyProject(
        code="BIO-PPI-ML",
        key="ppi_interaction_ml",
        title="Machine-Learning Algorithms for Predicting Protein–Protein Interactions",
        short_title="Protein Interaction ML",
        icon="🔗",
        domain="AI Lab",
        objective=(
            "Engineer sequence-derived pair features, train leakage-aware classifiers, compare "
            "algorithms and score candidate protein interactions with calibrated research outputs."
        ),
        workflow=("Audit pair dataset", "Benchmark pair and cold-protein generalization", "Calibrate, quantify uncertainty and audit OOD", "Score candidates, inspect network and register run"),
        deliverables=("QC/leakage/OOD audit", "ROC/PR/calibration/bootstrap evidence", "Cold-start and decision-curve validation", "Network + method card + HTML report + verified bundle"),
        tags=("ppi", "protein", "machine-learning", "classification", "network-biology"),
    ),
    BiotechnologyProject(
        code="BIO-CG-PATH",
        key="comparative_pathogen_genomics",
        title="Comparative Genomics for Pathogen Detection and Characterization",
        short_title="Comparative Pathogen Genomics",
        icon="🧫",
        domain="Bioinformatics",
        objective=(
            "Compare assembled genomes or contigs against a controlled reference panel, quantify "
            "k-mer similarity and genomic composition, and screen configurable characterization markers."
        ),
        workflow=("Validate query/reference FASTA", "Rank references with bootstrap support", "Audit windows, ORFs, GC-skew and pangenome", "Characterize markers and register evidence"),
        deliverables=("Genome QC + composition", "Bootstrap/window assignment evidence", "UPGMA + variants + ORF/GC-skew screens", "Method card + HTML report + verified bundle"),
        tags=("comparative-genomics", "pathogen", "kmer", "fasta", "characterization"),
    ),
    BiotechnologyProject(
        code="BIO-SCRNA",
        key="single_cell_heterogeneity",
        title="Single-Cell RNA Sequencing Analysis to Uncover Cellular Heterogeneity",
        short_title="Single-Cell Heterogeneity",
        icon="🧬",
        domain="Bioinformatics",
        objective=(
            "Perform cell-level quality control, normalization, highly-variable-gene selection, "
            "dimensionality reduction, clustering and marker-gene screening on scRNA-seq count matrices."
        ),
        workflow=("Validate counts and cell metadata", "QC, normalize and audit dropout/doublets", "Cluster, stabilize, inspect batch and annotate", "Build pseudobulk/trajectory screens and register run"),
        deliverables=("QC + doublet/dropout evidence", "PCA + cluster quality + batch audit", "Marker specificity + provisional annotation", "Pseudobulk + method card + verified bundle"),
        tags=("single-cell", "scrna-seq", "pca", "clustering", "marker-genes"),
    ),
    BiotechnologyProject(
        code="BIO-CANCER-GX",
        key="cancer_genomics",
        title="Bioinformatics Approaches to Cancer Genomics",
        short_title="Cancer Genomics",
        icon="🎗️",
        domain="Bioinformatics",
        objective=(
            "Prioritize somatic variants, summarize tumor mutational burden, inspect variant allele "
            "fractions, map altered genes to pathways and produce a transparent research-only evidence table."
        ),
        workflow=("Validate variants and samples", "Prioritize with VAF uncertainty", "Profile burden, recurrence and associations", "Review cohort structure and register evidence"),
        deliverables=("Variant/sample quality tiers", "Priority + threshold + VAF CI evidence", "Hotspots + six-class spectrum + associations", "Method card + HTML report + verified bundle"),
        tags=("cancer", "somatic-variants", "oncogenomics", "driver", "pathway"),
    ),
    BiotechnologyProject(
        code="BIO-META-PIPE",
        key="metagenomics_pipeline",
        title="Development of a Bioinformatics Pipeline for Metagenomics",
        short_title="Metagenomics Pipeline",
        icon="🦠",
        domain="Lab Analytics",
        objective=(
            "Run a reproducible abundance-table workflow covering quality checks, prevalence filtering, "
            "normalization, alpha/beta diversity, ordination and group-aware differential abundance screening."
        ),
        workflow=("Validate abundance and metadata", "Audit filtering and compositional transforms", "Calculate diversity, dispersion and stability", "Run permutation/FDR screens and register evidence"),
        deliverables=("Sample QC + prevalence sensitivity", "Composition + core/indicator taxa", "Bray-Curtis/Aitchison + PERMANOVA/dispersion", "FDR screen + method card + verified bundle"),
        tags=("metagenomics", "microbiome", "diversity", "ordination", "taxonomy"),
    ),
)

PROJECT_BY_KEY = {project.key: project for project in PROJECT_CATALOG}
