from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class BioinformaticsPeakModule:
    key: str
    title: str
    short_title: str
    category: str
    summary: str
    purpose: str
    required_columns: tuple[str, ...]
    accepted_inputs: tuple[str, ...]
    workflow: tuple[str, ...]
    outputs: tuple[str, ...]
    visuals: tuple[str, ...]
    boundary: str
    handoffs: tuple[str, ...]
    existing_page: str | None = None


MODULES: tuple[BioinformaticsPeakModule, ...] = (
    BioinformaticsPeakModule(
        "population_gwas_peak", "Population Genetics, GWAS & PRS Studio", "GWAS & PRS Studio", "Bioinformatics",
        "Cohort QC, ancestry structure, association screening, regional review and polygenic-risk exploration in one reproducible workflow.",
        "Use genotype, phenotype and covariate data to identify quality problems, population structure and association candidates before specialist mixed-model validation.",
        ("sample", "variant", "chrom", "position", "genotype", "phenotype"),
        ("CSV", "TSV", "VCF", "VCF.GZ", "PLINK-exported table"),
        ("Import and harmonise", "Sample and variant QC", "Ancestry structure", "Association screening", "LD and regional review", "PRS exploration", "Evidence export"),
        ("variant QC", "association table", "sample ancestry scores", "PRS scores", "evidence bundle"),
        ("Manhattan plot", "QQ plot", "Ancestry PCA", "LD heatmap", "Regional association", "PRS distribution", "Subgroup forest", "QC dashboard"),
        "Exploratory screening does not replace validated PLINK, SAIGE or REGENIE pipelines, imputation, ancestry-matched validation or clinical interpretation.",
        ("Variant Workbench", "Pathway Analysis", "Clinical Biomarker Studio"),
        "pages/134_Population_Genetics_GWAS_Studio.py",
    ),
    BioinformaticsPeakModule(
        "epigenomics_peak", "Epigenomics & Chromatin Accessibility Workbench", "Epigenomics Workbench", "Bioinformatics",
        "ATAC-seq, ChIP-seq, CUT&RUN, methylation and regulatory-region analysis with RNA integration and provenance.",
        "Prioritise differential regulatory regions, transcription-factor activity and peak-to-gene links while preserving genome build and assay context.",
        ("sample", "region", "condition", "signal", "chrom", "start", "end"),
        ("CSV", "TSV", "BED", "narrowPeak", "broadPeak"),
        ("Import regions", "Assay QC", "Consensus regions", "Differential signal", "Motif and TF analysis", "Peak-to-gene links", "Export"),
        ("differential regions", "motif activity", "peak-to-gene links", "methylation summary", "evidence bundle"),
        ("Peak heatmap", "Genome track", "Accessibility volcano", "Motif heatmap", "TF network", "Methylation profile", "Peak-gene links", "RNA concordance"),
        "Screening-level region analysis must be confirmed with replicate-aware specialist pipelines, matched genome builds and orthogonal assays.",
        ("Transcriptomics", "Gene Regulatory Network", "Comparative Regulatory Genomics"),
        "pages/112_Epigenomics_and_Chromatin_Regulation_Studio.py",
    ),
    BioinformaticsPeakModule(
        "pharmacogenomics_peak", "Pharmacogenomics & Clinical Genomics Studio", "Pharmacogenomics Studio", "Bioinformatics",
        "Variant-to-haplotype, phenotype and drug-gene evidence review with explicit confidence and research-use boundaries.",
        "Connect pharmacogene variants, diplotypes and medication evidence without presenting exploratory calls as clinical recommendations.",
        ("sample", "gene", "variant", "drug", "allele", "evidence_level"),
        ("CSV", "TSV", "VCF", "VCF.GZ", "medication list"),
        ("Import variants and medications", "Genome-build QC", "Allele and diplotype review", "Phenotype inference", "Drug-gene evidence", "Conflict review", "Report"),
        ("drug-gene review table", "diplotype evidence", "phenotype summary", "conflict queue", "structured report"),
        ("Pharmacogene coverage", "Diplotype waterfall", "Drug-gene matrix", "Phenotype distribution", "Population comparison", "Evidence ladder", "Conflict matrix", "Review timeline"),
        "Research-use output is not a prescribing recommendation. Clinical decisions require validated genotyping, current guidelines and qualified professional review.",
        ("Variant Workbench", "Clinical Biomarker Studio", "Evidence Review"),
        "pages/117_Pharmacogenomics_and_Precision_Medicine_Board.py",
    ),
    BioinformaticsPeakModule(
        "structural_variant_peak", "Structural Variant, Repeat Expansion & Mosaicism Studio", "SV & Mosaicism Studio", "Bioinformatics",
        "Harmonise deletions, duplications, inversions, translocations, repeat expansions, mobile-element insertions and mosaic candidates.",
        "Combine caller support, size, allele fraction, gene disruption and inheritance evidence into an auditable review queue.",
        ("sample", "event_id", "chrom", "start", "end", "event_type", "support"),
        ("CSV", "TSV", "VCF", "VCF.GZ", "BED", "BEDPE", "CNV segments"),
        ("Import caller outputs", "Coordinate harmonisation", "Evidence QC", "Mosaic and repeat review", "Gene and regulatory impact", "Family segregation", "Export"),
        ("harmonised event table", "caller concordance", "mosaic candidates", "repeat candidates", "review bundle"),
        ("Chromosome SV track", "Breakpoint Circos", "CNV profile", "Repeat-size distribution", "Mosaic allele fraction", "Caller concordance", "Segregation view", "Priority waterfall"),
        "Breakpoints and mosaic fractions require raw-read review and orthogonal confirmation; this module does not manufacture clinical classifications.",
        ("Variant Workbench", "Rare Disease Board", "Cancer Genomics"),
        "pages/135_Structural_Variant_Repeat_Expansion_Lab.py",
    ),
    BioinformaticsPeakModule(
        "rna_splicing_peak", "RNA Splicing & Isoform Pathology Lab", "RNA Splicing Lab", "Bioinformatics",
        "Detect exon usage, intron retention, splice-site shifts, isoform switching and transcript-level pathology signals.",
        "Bridge transcriptomics, long-read evidence and variant interpretation through junction-aware, uncertainty-labelled analysis.",
        ("sample", "gene", "transcript", "event", "group", "psi", "junction_support"),
        ("CSV", "TSV", "GTF", "GFF", "junction table", "long-read transcript table"),
        ("Import transcripts and junctions", "Support QC", "Event classification", "Differential splicing", "Variant linkage", "Disease prioritisation", "Export"),
        ("splicing event table", "isoform switches", "junction QC", "variant-splice links", "evidence bundle"),
        ("Sashimi-style view", "Transcript architecture", "Exon-usage heatmap", "PSI distribution", "Isoform switching", "Junction support", "Variant-splice map", "Gene summary"),
        "Built-in calculations are exploratory and do not replace splice-aware alignment, transcript assembly or validated DEXSeq, DRIMSeq, MAJIQ or long-read workflows.",
        ("Transcriptomics", "Rare Disease Board", "Long-Read Isoforms"),
        "pages/137_RNA_Isoform_Alternative_Splicing_Studio.py",
    ),
    BioinformaticsPeakModule(
        "immune_repertoire", "Immunogenomics & Immune Repertoire Studio", "Immune Repertoire Studio", "Bioinformatics",
        "HLA, TCR and BCR repertoire analytics with clonotype expansion, diversity, V(D)J usage and longitudinal tracking.",
        "Inspect repertoire composition and immune clone dynamics while separating technical sampling effects from biological interpretation.",
        ("sample", "clonotype", "chain", "v_gene", "j_gene", "cdr3", "count"),
        ("CSV", "TSV", "AIRR table", "VDJ summary", "single-cell receptor table"),
        ("Import repertoire", "Sequence and count QC", "Clonotype assignment", "Diversity analysis", "Expansion tracking", "Single-cell integration", "Export"),
        ("clonotype table", "diversity metrics", "V/J usage", "longitudinal clone tracking", "evidence bundle"),
        ("Clonotype network", "V/J chord-style matrix", "CDR3 length", "Diversity curves", "Expansion treemap", "Clone-cell embedding", "Longitudinal tracking", "QC dashboard"),
        "Repertoire frequencies are sensitive to library preparation, sampling depth and clonotype definition; biological conclusions require matched experimental design.",
        ("Single-Cell Heterogeneity", "Vaccine Design", "Clinical Biomarker Studio"),
    ),
    BioinformaticsPeakModule(
        "single_cell_multiome", "Single-Cell Multiome & Regulatory Network Studio", "Single-Cell Multiome Studio", "Bioinformatics",
        "Joint scRNA, scATAC and protein-tag analysis with modality QC, integrated embeddings and regulatory links.",
        "Build a transparent multi-modal cell-state view with marker agreement, batch diagnostics, peak-to-gene links and TF activity.",
        ("cell", "sample", "cluster", "modality", "feature", "value", "batch"),
        ("CSV", "TSV", "H5AD metadata", "MuData export", "feature matrix"),
        ("Import modalities", "Modality QC", "Cell and feature filtering", "Joint embedding", "Peak-to-gene links", "Regulatory inference", "Export"),
        ("cell annotations", "joint embedding", "modality agreement", "regulatory links", "evidence bundle"),
        ("Joint embedding", "Modality agreement", "RNA-ATAC links", "TF activity heatmap", "Cell trajectory", "Feature browser", "Batch mixing", "Cluster composition"),
        "Joint embeddings and transferred labels are exploratory. Validate modality integration, cell labels and regulatory links with independent evidence.",
        ("Single-Cell Heterogeneity", "Cell Atlas Mapping", "Gene Regulatory Network"),
    ),
    BioinformaticsPeakModule(
        "proteogenomics_peak", "Proteogenomics & Neoantigen Discovery Studio", "Proteogenomics Studio", "Bioinformatics",
        "Connect genomic variants, RNA expression, peptide evidence, HLA binding and normal-tissue risk for neoantigen research.",
        "Rank candidate variant peptides using multiple evidence layers and retain every exclusion and uncertainty decision.",
        ("sample", "variant", "gene", "peptide", "hla", "binding_score", "expression", "ms_support"),
        ("CSV", "TSV", "VCF-derived peptide table", "FASTA", "proteomics evidence"),
        ("Import variants and peptides", "Peptide QC", "HLA binding review", "RNA and MS support", "Clonality and safety", "Panel selection", "Export"),
        ("ranked peptides", "HLA coverage", "evidence matrix", "normal-tissue risk", "vaccine panel"),
        ("Variant-peptide Sankey", "HLA heatmap", "Peptide coverage", "RNA-MS evidence", "Candidate waterfall", "Normal-tissue risk", "Clonality map", "Panel diversity"),
        "Predicted binding and immunogenicity do not establish therapeutic efficacy. Candidates require validated HLA typing, assays and safety review.",
        ("Cancer Genomics", "Vaccine Design", "Clinical Biomarker Studio"),
        "pages/124_Proteogenomics_and_Neoantigen_Discovery_Studio.py",
    ),
    BioinformaticsPeakModule(
        "gene_regulatory_network", "Gene Regulatory Network & TF Activity Studio", "Regulatory Network Studio", "Bioinformatics",
        "Infer evidence-weighted TF-target relationships, regulon activity and condition-specific master regulators.",
        "Combine expression, accessibility and motif evidence into reviewable regulatory hypotheses rather than opaque network claims.",
        ("sample", "condition", "tf", "target", "activity", "evidence", "expression"),
        ("CSV", "TSV", "regulon table", "motif activity table", "peak-gene links"),
        ("Import regulatory evidence", "Edge QC", "Regulon scoring", "Condition comparison", "Master-regulator ranking", "Perturbation scenarios", "Export"),
        ("regulatory edge table", "TF activity", "regulon scores", "master regulators", "evidence bundle"),
        ("TF network", "Regulon heatmap", "TF volcano", "Target Sankey", "Centrality plot", "Circuit diagram", "Evidence matrix", "Condition comparison"),
        "Inferred regulatory edges are hypotheses and must be validated with perturbation, binding or orthogonal evidence.",
        ("Epigenomics", "Transcriptomics", "Causal Biology"),
    ),
    BioinformaticsPeakModule(
        "federated_genomic_discovery", "Federated Genomic Discovery & Phenopacket Studio", "Federated Genomic Discovery", "Bioinformatics",
        "Phenopacket, pedigree and Beacon-style cohort discovery with consent-aware source provenance.",
        "Match phenotype and variant evidence across local or federated sources without hiding access restrictions or match uncertainty.",
        ("case_id", "source", "phenotype", "gene", "variant", "phenotype_similarity", "variant_match", "access_status"),
        ("CSV", "TSV", "Phenopacket JSON", "Beacon-style response", "pedigree table"),
        ("Import cases", "Phenotype validation", "Access and consent review", "Federated query", "Case matching", "Human review", "Export"),
        ("case matches", "source coverage", "phenotype matrix", "access review", "query provenance"),
        ("Phenotype-case matrix", "Federated source map", "Variant-match network", "Pedigree view", "Access badges", "Query timeline", "Match waterfall", "Source coverage"),
        "Federated discovery does not grant access to restricted records and must respect consent, governance and source-specific interpretation rules.",
        ("Rare Disease Board", "Variant Workbench", "Evidence Review"),
    ),
    BioinformaticsPeakModule(
        "viral_within_host", "Viral Genomics & Within-Host Evolution Studio", "Viral Evolution Studio", "Bioinformatics",
        "Consensus, minor-variant, lineage, recombination, selection and longitudinal within-host evolution analysis.",
        "Separate low-frequency noise from reproducible viral evolution signals and connect sequence changes to time and lineage context.",
        ("sample", "subject", "time", "chrom", "position", "ref", "alt", "frequency", "lineage"),
        ("CSV", "TSV", "VCF", "VCF.GZ", "FASTA-derived variant table"),
        ("Import variants", "Depth and frequency QC", "Consensus and minor variants", "Longitudinal dynamics", "Lineage and recombination", "Selection review", "Export"),
        ("variant table", "within-host trajectories", "lineage markers", "recombination flags", "surveillance bundle"),
        ("Frequency trajectories", "Minor-variant spectrum", "Lineage map", "Recombination matrix", "Selection profile", "Subject timeline", "Mutation heatmap", "QC dashboard"),
        "Low-frequency variants are highly sensitive to sequencing and contamination artefacts; confirm with validated callers, controls and replicate evidence.",
        ("Pathogen Outbreak", "Comparative Pathogen Genomics", "AMR Surveillance"),
        "pages/146_Virology_Viral_Evolution_Workbench.py",
    ),
    BioinformaticsPeakModule(
        "genome_annotation", "Genome Annotation & Comparative Annotation Studio", "Genome Annotation Studio", "Bioinformatics",
        "Validate GFF/GTF gene models, compare annotation versions and integrate orthology, protein-domain and synteny evidence.",
        "Create an auditable annotation review queue that separates model completeness from functional evidence.",
        ("genome", "feature_id", "chrom", "start", "end", "strand", "feature_type", "evidence"),
        ("CSV", "TSV", "GFF", "GFF3", "GTF", "annotation comparison table"),
        ("Import annotation", "Syntax and coordinate QC", "Gene-model comparison", "Functional evidence", "Orthology and synteny", "Completeness review", "Export"),
        ("validated annotation", "version diff", "completeness metrics", "orthology table", "review bundle"),
        ("Genome feature track", "Annotation diff", "Completeness dashboard", "Orthology matrix", "Synteny blocks", "Evidence distribution", "Feature-length profile", "Review funnel"),
        "Automated annotation transfer can propagate errors. Curated gene models and experimental evidence remain authoritative.",
        ("Long-Read Assembly", "Protein Annotation", "Comparative Genomics"),
    ),
    BioinformaticsPeakModule(
        "circular_dna_instability", "Circular DNA, Mobile Elements & Genome Instability Studio", "Genome Instability Studio", "Bioinformatics",
        "Review ecDNA, circular DNA, mobile-element insertions, amplification structures and complex rearrangement candidates.",
        "Integrate breakpoint, copy-number and read-support evidence into a transparent genome-instability review workflow.",
        ("sample", "event_id", "chrom", "start", "end", "event_type", "copy_number", "support"),
        ("CSV", "TSV", "BED", "BEDPE", "VCF", "amplicon summary"),
        ("Import instability events", "Breakpoint QC", "Circle and insertion classification", "Copy-number review", "Gene impact", "Recurrence analysis", "Export"),
        ("instability events", "circle candidates", "mobile-element insertions", "amplification structures", "review bundle"),
        ("Circular breakpoint map", "Copy-number profile", "Amplification topology", "Mobile-element map", "Recurrence heatmap", "Gene impact", "Event-size distribution", "Priority waterfall"),
        "Complex rearrangement structures require raw-read, assembly and orthogonal validation; inferred circles are research hypotheses.",
        ("Structural Variant Studio", "Cancer Genomics", "Long-Read Assembly"),
    ),
    BioinformaticsPeakModule(
        "environmental_edna", "Environmental Genomics & eDNA Surveillance Studio", "eDNA Surveillance Studio", "Bioinformatics",
        "Species detection, occupancy, biodiversity, contamination-control and spatiotemporal eDNA surveillance.",
        "Distinguish biological detections from background contamination and reference-library uncertainty across sites and sampling events.",
        ("sample", "site", "date", "species", "reads", "control_type", "reference_confidence"),
        ("CSV", "TSV", "metabarcoding abundance table", "taxonomy table", "sample metadata"),
        ("Import detections", "Control and depth QC", "Taxonomy harmonisation", "Occupancy and biodiversity", "Spatial and temporal review", "Alert generation", "Export"),
        ("species detections", "occupancy summary", "biodiversity metrics", "contamination flags", "surveillance report"),
        ("Species-site heatmap", "Occupancy map", "Biodiversity curves", "Control contamination", "Temporal trends", "Reference confidence", "Community ordination", "Alert dashboard"),
        "eDNA detection depends on sampling design, assay specificity, reference coverage and environmental persistence; presence does not prove abundance or viability.",
        ("One Health Center", "Microbiology & Metagenomics", "Pathogen Outbreak"),
    ),
    BioinformaticsPeakModule(
        "comparative_regulatory_genomics", "Comparative Regulatory Genomics Studio", "Comparative Regulatory Genomics", "Bioinformatics",
        "Compare conserved non-coding regions, enhancer activity, motif turnover and regulatory synteny across species.",
        "Connect sequence conservation and functional activity without treating conservation alone as proof of regulatory function.",
        ("species", "region", "ortholog_group", "motif", "conservation", "activity", "chrom", "start", "end"),
        ("CSV", "TSV", "BED", "conserved-element table", "orthologous peak table"),
        ("Import orthologous regions", "Coordinate and orthology QC", "Conservation analysis", "Motif turnover", "Activity comparison", "Regulatory synteny", "Export"),
        ("conserved regions", "motif turnover", "activity comparison", "synteny blocks", "evidence bundle"),
        ("Conservation landscape", "Motif turnover heatmap", "Activity comparison", "Regulatory synteny", "Ortholog network", "Constraint distribution", "Species clustering", "Evidence matrix"),
        "Conservation and motif presence are indirect evidence. Functional claims require species- and tissue-matched experimental validation.",
        ("Epigenomics", "Comparative Genomics", "Gene Regulatory Network"),
    ),
)

_VISUAL_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "population_gwas_peak": ("Sample QC landscape", "Variant QC matrix", "Fine-mapping credible set", "PRS calibration"),
    "epigenomics_peak": ("Sample-level assay QC", "Condition balance", "Regulatory-class composition", "Genome-bin signal"),
    "pharmacogenomics_peak": ("Locus coverage QC", "Diplotype confidence", "Medication impact board", "Reanalysis triggers"),
    "structural_variant_peak": ("Consensus event clusters", "Mosaic candidate review", "Repeat expansion candidates", "Breakpoint hotspot profile"),
    "rna_splicing_peak": ("Group balance and QC", "High-confidence isoform switches", "Aberrant splicing outliers", "NMD-risk proxy"),
    "immune_repertoire": ("Chain and depth QC", "Public/shared clonotypes", "Clonality by sample", "Rarefaction profile"),
    "single_cell_multiome": ("Cell quality landscape", "Modality depth", "Deep modality agreement", "Multimodal marker ranking"),
    "proteogenomics_peak": ("Candidate panel", "Shared neoantigens", "Evidence-tier composition", "Peptide QC"),
    "gene_regulatory_network": ("Master regulator ranking", "Network statistics", "Perturbation simulation", "Edge-confidence distribution"),
    "federated_genomic_discovery": ("Consent and access matrix", "Federated query plan", "Case-level match summary", "Phenopacket QC"),
    "viral_within_host": ("Depth QC", "Primer-dropout profile", "Mixed-infection review", "Transmission summary"),
    "genome_annotation": ("Annotation conflict map", "Orphan feature review", "Version consistency", "Feature QC matrix"),
    "circular_dna_instability": ("Consensus topology clusters", "Sample recurrence", "Amplification topology summary", "Breakpoint hotspots"),
    "environmental_edna": ("Control QC", "Replicate concordance", "Taxonomic ambiguity", "Surveillance alerts"),
    "comparative_regulatory_genomics": ("Species support", "Regulatory gain/loss", "Tissue matching", "Conservation QC"),
}

MODULES = tuple(replace(module, visuals=tuple((*module.visuals, *_VISUAL_EXTENSIONS[module.key]))) for module in MODULES)

MODULE_BY_KEY = {module.key: module for module in MODULES}
NEW_MODULE_KEYS = {
    "immune_repertoire",
    "single_cell_multiome",
    "gene_regulatory_network",
    "federated_genomic_discovery",
    "genome_annotation",
    "circular_dna_instability",
    "environmental_edna",
    "comparative_regulatory_genomics",
}
