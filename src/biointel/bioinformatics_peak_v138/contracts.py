from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParameterSpec:
    key: str
    label: str
    kind: str
    default: Any
    help: str
    options: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    advanced: bool = False


@dataclass(frozen=True)
class ModuleContract:
    key: str
    organisms: tuple[str, ...]
    genome_builds: tuple[str, ...]
    analysis_profiles: tuple[str, ...]
    parameters: tuple[ParameterSpec, ...]
    qc_checks: tuple[str, ...]
    capabilities: tuple[str, ...]
    specialist_engines: tuple[str, ...]
    reference_assets: tuple[str, ...]
    review_roles: tuple[str, ...]


def _p(key: str, label: str, kind: str, default: Any, help: str, *, options: tuple[str, ...] = (), minimum: float | None = None, maximum: float | None = None, step: float | None = None, advanced: bool = False) -> ParameterSpec:
    return ParameterSpec(key, label, kind, default, help, options, minimum, maximum, step, advanced)


COMMON = (
    _p("genome_build", "Genome/reference build", "select", "GRCh38", "Coordinate system used by variants, intervals and annotations.", options=("GRCh38", "GRCh37", "T2T-CHM13v2.0", "Custom/other")),
    _p("organism", "Organism", "select", "Homo sapiens", "Organism context used for annotations and scientific boundaries.", options=("Homo sapiens", "Mus musculus", "Rattus norvegicus", "Pathogen/viral", "Environmental/mixed", "Custom/other")),
    _p("missing_policy", "Missing-value policy", "select", "Retain and flag", "Controls whether incomplete records remain visible for review.", options=("Retain and flag", "Exclude incomplete records", "Median/mode imputation for screening")),
    _p("priority_threshold", "Priority review threshold", "float", 0.70, "Records at or above this score are highlighted for review.", minimum=0.0, maximum=1.0, step=0.05),
    _p("random_seed", "Reproducibility seed", "int", 42, "Seed used for deterministic sampling and preview calculations.", minimum=0, maximum=2_147_483_647, step=1, advanced=True),
)


CONTRACTS: dict[str, ModuleContract] = {
    "population_gwas_peak": ModuleContract(
        "population_gwas_peak", ("Homo sapiens", "Custom/other"), ("GRCh38", "GRCh37", "Custom/other"),
        ("Case-control", "Quantitative trait", "PRS exploration", "QC only"),
        COMMON + (
            _p("analysis_profile", "Analysis profile", "select", "Case-control", "Selects association and interpretation defaults.", options=("Case-control", "Quantitative trait", "PRS exploration", "QC only")),
            _p("min_call_rate", "Minimum call rate", "float", 0.95, "Minimum non-missing genotype fraction.", minimum=0.5, maximum=1.0, step=0.01),
            _p("min_maf", "Minimum minor-allele frequency", "float", 0.01, "Variants below this frequency are marked for exclusion.", minimum=0.0, maximum=0.5, step=0.005),
            _p("hwe_threshold", "HWE review threshold", "float", 1e-6, "Hardy-Weinberg p-values below this are flagged.", minimum=1e-12, maximum=0.1, step=1e-6, advanced=True),
            _p("prs_top_n", "PRS variants", "int", 25, "Number of highest-ranked variants used for exploratory PRS.", minimum=1, maximum=500, step=1, advanced=True),
        ),
        ("Sample missingness", "Variant missingness", "Heterozygosity", "Relatedness proxy", "MAF", "Hardy-Weinberg", "Population structure", "Phenotype balance"),
        ("Sample/variant QC", "Ancestry PCA", "Association screening", "LD proxy", "Regional review", "Fine-mapping proxy", "PRS", "Subgroup performance"),
        ("PLINK 2", "REGENIE", "SAIGE", "BCFtools"), ("Reference genome", "Population allele frequencies", "Gene annotation", "LD reference panel"), ("Analyst", "Statistical geneticist", "Clinical reviewer"),
    ),
    "epigenomics_peak": ModuleContract(
        "epigenomics_peak", ("Homo sapiens", "Mus musculus", "Custom/other"), ("GRCh38", "GRCh37", "GRCm39", "Custom/other"),
        ("ATAC-seq", "ChIP-seq", "CUT&RUN/CUT&Tag", "DNA methylation"),
        COMMON + (
            _p("analysis_profile", "Assay profile", "select", "ATAC-seq", "Controls assay-specific guidance.", options=("ATAC-seq", "ChIP-seq", "CUT&RUN/CUT&Tag", "DNA methylation")),
            _p("min_signal", "Minimum region signal", "float", 1.0, "Regions below this signal are flagged.", minimum=0.0, maximum=1_000_000.0, step=0.5),
            _p("min_replicates", "Minimum replicates per condition", "int", 2, "Conditions below this count receive a blocker.", minimum=1, maximum=20, step=1),
            _p("promoter_window", "Promoter window (bp)", "int", 2000, "Distance used for promoter-proximal annotation.", minimum=100, maximum=100_000, step=100, advanced=True),
        ),
        ("Replicate balance", "Coordinate validity", "Peak width", "Signal distribution", "TSS/fragment profile availability", "Genome-build consistency", "Batch structure"),
        ("Consensus regions", "Differential accessibility", "Motif enrichment", "TF activity", "Peak-to-gene links", "Methylation", "RNA concordance", "Genome tracks"),
        ("MACS3", "deepTools", "BEDTools", "HOMER"), ("Reference genome", "Gene annotation", "Motif library", "Enhancer catalogue"), ("Analyst", "Epigenomics specialist", "Biological reviewer"),
    ),
    "pharmacogenomics_peak": ModuleContract(
        "pharmacogenomics_peak", ("Homo sapiens",), ("GRCh38", "GRCh37"), ("Variant review", "Diplotype review", "Medication review"),
        COMMON + (
            _p("analysis_profile", "Workflow profile", "select", "Diplotype review", "Selects review emphasis.", options=("Variant review", "Diplotype review", "Medication review")),
            _p("min_coverage", "Minimum locus coverage", "float", 20.0, "Coverage below this value is flagged.", minimum=0.0, maximum=1000.0, step=1.0),
            _p("guideline_snapshot", "Guideline snapshot", "text", "Local versioned snapshot", "Records the evidence/guideline release used.", advanced=True),
        ),
        ("Genome build", "Gene coverage", "Allele completeness", "Copy-number availability", "Guideline version", "Medication mapping", "Evidence conflicts"),
        ("Allele review", "Diplotype assembly", "Phenotype inference", "Drug-gene evidence", "Conflict review", "Population context", "Reanalysis alerts"),
        ("Aldy", "Stargazer", "VEP"), ("Pharmacogene definitions", "Guideline snapshot", "Population allele frequencies", "Transcript annotation"), ("Analyst", "Pharmacogenomics specialist", "Qualified clinical reviewer"),
    ),
    "structural_variant_peak": ModuleContract(
        "structural_variant_peak", ("Homo sapiens", "Mus musculus", "Custom/other"), ("GRCh38", "GRCh37", "T2T-CHM13v2.0", "Custom/other"),
        ("Structural variants", "Repeat expansions", "Mosaicism", "Multi-caller consensus"),
        COMMON + (
            _p("analysis_profile", "Workflow profile", "select", "Multi-caller consensus", "Controls event-specific checks.", options=("Structural variants", "Repeat expansions", "Mosaicism", "Multi-caller consensus")),
            _p("min_support", "Minimum supporting reads", "int", 3, "Events below this support are low-confidence.", minimum=0, maximum=10000, step=1),
            _p("mosaic_vaf_max", "Mosaic VAF upper bound", "float", 0.35, "Allele fractions below this are reviewed as possible mosaic events.", minimum=0.01, maximum=0.5, step=0.01),
            _p("merge_distance", "Breakpoint merge distance (bp)", "int", 1000, "Events within this distance may form a consensus cluster.", minimum=0, maximum=1_000_000, step=100, advanced=True),
        ),
        ("Coordinate validity", "Event size", "Read support", "Caller concordance", "Allele fraction", "Copy-number consistency", "Family/sample completeness"),
        ("SV normalization", "Breakpoint clustering", "Multi-caller consensus", "Repeat review", "Mosaic review", "Gene/regulatory impact", "Segregation"),
        ("SURVIVOR", "ExpansionHunter", "CNVkit", "MELT"), ("Reference genome", "Repeat catalogue", "Gene annotation", "Population SV frequencies"), ("Analyst", "Cytogenomics reviewer", "Clinical reviewer"),
    ),
    "rna_splicing_peak": ModuleContract(
        "rna_splicing_peak", ("Homo sapiens", "Mus musculus", "Custom/other"), ("GRCh38", "GRCh37", "GRCm39", "Custom/other"),
        ("Differential splicing", "Isoform switching", "Aberrant splicing", "Variant-linked review"),
        COMMON + (
            _p("analysis_profile", "Workflow profile", "select", "Differential splicing", "Selects event and output emphasis.", options=("Differential splicing", "Isoform switching", "Aberrant splicing", "Variant-linked review")),
            _p("min_junction_support", "Minimum junction support", "int", 10, "Events below this support are flagged.", minimum=0, maximum=1_000_000, step=1),
            _p("min_delta_psi", "Minimum |ΔPSI|", "float", 0.10, "Effect-size threshold for review.", minimum=0.0, maximum=1.0, step=0.01),
            _p("min_group_samples", "Minimum samples per group", "int", 3, "Groups below this count receive a blocker.", minimum=1, maximum=1000, step=1),
        ),
        ("Junction support", "Group balance", "PSI bounds", "Transcript consistency", "Reference annotation", "Replicate structure"),
        ("Event classification", "Differential splicing", "Isoform switching", "Outlier detection", "Variant linkage", "Fusion review", "NMD proxy"),
        ("STAR", "RegTools", "MAJIQ", "DEXSeq"), ("Transcript annotation", "Splice-site reference", "Tissue expression reference", "Disease gene list"), ("Analyst", "RNA specialist", "Rare-disease reviewer"),
    ),
    "immune_repertoire": ModuleContract(
        "immune_repertoire", ("Homo sapiens", "Mus musculus", "Custom/other"), ("Reference-independent",), ("TCR", "BCR", "Single-cell VDJ", "Longitudinal repertoire"),
        COMMON + (
            _p("analysis_profile", "Repertoire profile", "select", "TCR", "Selects receptor-specific guidance.", options=("TCR", "BCR", "Single-cell VDJ", "Longitudinal repertoire")),
            _p("min_clone_count", "Minimum clonotype count", "int", 2, "Clonotypes below this count are flagged as low support.", minimum=1, maximum=100000, step=1),
            _p("public_clone_min_samples", "Shared-clone sample count", "int", 2, "Minimum samples required for a public/shared clone.", minimum=2, maximum=1000, step=1),
        ),
        ("Read/count depth", "Chain validity", "CDR3 completeness", "Sample depth balance", "Clonotype uniqueness", "Longitudinal consistency"),
        ("Clonotype assignment", "Diversity", "V/J usage", "Expansion", "Public clonotypes", "Longitudinal tracking", "Single-cell integration", "Isotype switching"),
        ("MiXCR", "IgBLAST", "Scirpy"), ("V(D)J germline reference", "HLA reference", "AIRR schema"), ("Analyst", "Immunologist", "Clinical reviewer"),
    ),
    "single_cell_multiome": ModuleContract(
        "single_cell_multiome", ("Homo sapiens", "Mus musculus", "Custom/other"), ("GRCh38", "GRCm39", "Custom/other"), ("scRNA+scATAC", "CITE-seq", "Multiome QC", "Regulatory inference"),
        COMMON + (
            _p("analysis_profile", "Multiome profile", "select", "scRNA+scATAC", "Selects modality-specific defaults.", options=("scRNA+scATAC", "CITE-seq", "Multiome QC", "Regulatory inference")),
            _p("min_features", "Minimum detected features per cell", "int", 200, "Cells below this threshold are flagged.", minimum=0, maximum=100000, step=50),
            _p("max_mito_pct", "Maximum mitochondrial %", "float", 20.0, "Cells above this value are flagged.", minimum=0.0, maximum=100.0, step=1.0),
            _p("min_modality_agreement", "Minimum modality agreement", "float", 0.30, "Cells/links below this score receive review status.", minimum=0.0, maximum=1.0, step=0.05),
        ),
        ("Cell barcode matching", "Modality depth", "Feature counts", "Mitochondrial fraction", "Doublet proxy", "Batch mixing", "Cluster representation"),
        ("Joint embedding", "Modality agreement", "Peak-to-gene links", "TF activity", "Regulons", "Pseudotime", "Differential abundance", "Multimodal markers"),
        ("Scanpy", "MuData", "MuON", "ArchR/Signac bridge"), ("Reference genome", "Gene annotation", "Motif library", "Cell atlas reference"), ("Analyst", "Single-cell specialist", "Biological reviewer"),
    ),
    "proteogenomics_peak": ModuleContract(
        "proteogenomics_peak", ("Homo sapiens", "Mus musculus", "Custom/other"), ("GRCh38", "GRCh37", "Custom/other"), ("Proteogenomics", "Neoantigen prioritization", "Vaccine panel"),
        COMMON + (
            _p("analysis_profile", "Workflow profile", "select", "Neoantigen prioritization", "Selects evidence requirements.", options=("Proteogenomics", "Neoantigen prioritization", "Vaccine panel")),
            _p("max_normal_tissue_risk", "Maximum normal-tissue risk", "float", 0.25, "Candidates above this score are blocked from the default panel.", minimum=0.0, maximum=1.0, step=0.05),
            _p("min_expression", "Minimum expression support", "float", 1.0, "Expression below this value is considered weak support.", minimum=0.0, maximum=1_000_000.0, step=0.5),
            _p("panel_size", "Candidate panel size", "int", 20, "Maximum candidates in the generated panel.", minimum=1, maximum=500, step=1),
        ),
        ("HLA completeness", "Peptide length", "Expression support", "MS support", "Clonality", "Normal-tissue risk", "Variant uniqueness"),
        ("Variant peptide generation", "HLA ranking", "RNA/MS evidence", "Clonality", "Normal-tissue review", "Shared candidates", "Panel diversity"),
        ("VEP", "NetMHCpan", "MSFragger"), ("Reference proteome", "HLA allele definitions", "Normal-tissue expression", "Variant annotation"), ("Analyst", "Immunogenomics specialist", "Translational reviewer"),
    ),
    "gene_regulatory_network": ModuleContract(
        "gene_regulatory_network", ("Homo sapiens", "Mus musculus", "Custom/other"), ("GRCh38", "GRCm39", "Custom/other"), ("Bulk RNA", "Single-cell RNA", "RNA+ATAC", "Perturbation"),
        COMMON + (
            _p("analysis_profile", "Regulatory profile", "select", "RNA+ATAC", "Selects network evidence requirements.", options=("Bulk RNA", "Single-cell RNA", "RNA+ATAC", "Perturbation")),
            _p("min_edge_evidence", "Minimum edge evidence", "float", 0.50, "Edges below this score remain visible but are not high confidence.", minimum=0.0, maximum=1.0, step=0.05),
            _p("max_edges", "Maximum displayed network edges", "int", 100, "Limits network complexity for interactive rendering.", minimum=10, maximum=1000, step=10),
        ),
        ("TF/target completeness", "Replicate balance", "Activity variance", "Motif support", "Edge evidence", "Network density"),
        ("Regulon scoring", "Differential TF activity", "Master regulators", "Network centrality", "Perturbation simulation", "Enhancer-promoter links", "Time-series comparison"),
        ("pySCENIC", "HOMER", "BEDTools"), ("Motif library", "TF-target reference", "Enhancer catalogue", "Gene annotation"), ("Analyst", "Regulatory genomics specialist", "Biological reviewer"),
    ),
    "federated_genomic_discovery": ModuleContract(
        "federated_genomic_discovery", ("Homo sapiens", "Custom/other"), ("GA4GH/VRS", "GRCh38", "GRCh37"), ("Phenopacket review", "Federated discovery", "Case matching"),
        COMMON + (
            _p("analysis_profile", "Discovery profile", "select", "Case matching", "Controls query and review emphasis.", options=("Phenopacket review", "Federated discovery", "Case matching")),
            _p("min_phenotype_similarity", "Minimum phenotype similarity", "float", 0.40, "Matches below this score are low priority.", minimum=0.0, maximum=1.0, step=0.05),
            _p("privacy_mode", "Privacy mode", "select", "Metadata-only", "Controls whether only local metadata or federated requests are planned.", options=("Metadata-only", "Local/private", "Federated request plan")),
        ),
        ("Phenopacket validity", "HPO identifiers", "Variant representation", "Consent scope", "Access status", "Source availability", "De-identification"),
        ("Phenotype similarity", "Genotype-phenotype matching", "Federated source discovery", "Consent review", "Case matching", "Query provenance", "De-identification review"),
        ("Phenopackets", "GA4GH VRS", "Beacon v2 client"), ("HPO", "Disease ontology", "GA4GH schemas", "Federated source registry"), ("Analyst", "Data-access reviewer", "Clinical reviewer"),
    ),
    "viral_within_host": ModuleContract(
        "viral_within_host", ("Pathogen/viral", "Custom/other"), ("Virus-specific reference", "Custom/other"), ("Consensus/lineage", "Within-host variants", "Outbreak linkage", "Resistance/antigenic review"),
        COMMON + (
            _p("analysis_profile", "Viral analysis profile", "select", "Within-host variants", "Selects frequency and timeline defaults.", options=("Consensus/lineage", "Within-host variants", "Outbreak linkage", "Resistance/antigenic review")),
            _p("min_depth", "Minimum depth", "int", 100, "Sites below this depth are flagged.", minimum=0, maximum=1_000_000, step=10),
            _p("minor_variant_min", "Minor-variant frequency", "float", 0.02, "Lower frequency threshold for within-host candidates.", minimum=0.001, maximum=0.5, step=0.005),
            _p("primer_dropout_threshold", "Primer-dropout depth fraction", "float", 0.20, "Regions below this fraction of median depth are flagged.", minimum=0.0, maximum=1.0, step=0.05, advanced=True),
        ),
        ("Depth", "Reference consistency", "Mixed infection", "Primer dropout", "Timepoint order", "Contamination", "Lineage database version"),
        ("Consensus QC", "Minor variants", "Quasispecies proxy", "Lineage assignment", "Recombination", "Selection proxy", "Transmission distance", "Resistance/antigenic review"),
        ("iVar", "Nextclade", "LoFreq", "MAFFT/IQ-TREE"), ("Virus reference", "Lineage database", "Resistance catalogue", "Primer scheme"), ("Analyst", "Virologist", "Outbreak reviewer"),
    ),
    "genome_annotation": ModuleContract(
        "genome_annotation", ("Homo sapiens", "Mus musculus", "Pathogen/viral", "Environmental/mixed", "Custom/other"), ("Assembly-specific", "Custom/other"), ("Eukaryotic annotation", "Prokaryotic annotation", "Annotation comparison", "Transfer/curation"),
        COMMON + (
            _p("analysis_profile", "Annotation profile", "select", "Annotation comparison", "Selects gene-model and completeness guidance.", options=("Eukaryotic annotation", "Prokaryotic annotation", "Annotation comparison", "Transfer/curation")),
            _p("min_feature_length", "Minimum feature length (bp)", "int", 50, "Shorter features are flagged for review.", minimum=1, maximum=1_000_000, step=10),
            _p("min_completeness", "Minimum completeness", "float", 0.70, "Features/annotations below this score are reviewed.", minimum=0.0, maximum=1.0, step=0.05),
        ),
        ("FASTA/GFF compatibility", "Coordinate validity", "Feature overlap", "Evidence support", "ORF length", "Completeness", "Version consistency"),
        ("GFF/GTF validation", "Gene-model comparison", "Orthology", "Synteny", "Functional annotation", "Pseudogene review", "Completeness", "Manual curation"),
        ("BRAKER", "Bakta", "BUSCO", "InterProScan"), ("Assembly FASTA", "Protein/domain reference", "Orthology database", "Functional ontology"), ("Analyst", "Genome annotator", "Biological curator"),
    ),
    "circular_dna_instability": ModuleContract(
        "circular_dna_instability", ("Homo sapiens", "Custom/other"), ("GRCh38", "GRCh37", "T2T-CHM13v2.0", "Custom/other"), ("ecDNA", "Mobile elements", "Viral integration", "Genome instability"),
        COMMON + (
            _p("analysis_profile", "Instability profile", "select", "ecDNA", "Selects event-specific checks.", options=("ecDNA", "Mobile elements", "Viral integration", "Genome instability")),
            _p("min_copy_number", "Amplification copy-number threshold", "float", 4.0, "Events above this threshold receive amplification support.", minimum=0.0, maximum=1000.0, step=0.5),
            _p("min_support", "Minimum breakpoint support", "int", 3, "Events below this count are flagged.", minimum=0, maximum=10000, step=1),
        ),
        ("Breakpoint support", "Copy-number context", "Circular topology", "Gene impact", "Sample recurrence", "Long-read support", "Integration-site validity"),
        ("Circular topology", "Breakpoint clusters", "Focal amplification", "Mobile elements", "Integration sites", "Sample recurrence", "Instability score"),
        ("AmpliconArchitect", "Circle-Map", "MELT"), ("Reference genome", "RepeatMasker annotation", "Oncogene list", "Viral references"), ("Analyst", "Cancer genomics reviewer", "Molecular reviewer"),
    ),
    "environmental_edna": ModuleContract(
        "environmental_edna", ("Environmental/mixed", "Custom/other"), ("Reference-independent", "Marker-specific"), ("Metabarcoding", "Species surveillance", "Occupancy", "Biodiversity"),
        COMMON + (
            _p("analysis_profile", "eDNA profile", "select", "Species surveillance", "Selects control and detection guidance.", options=("Metabarcoding", "Species surveillance", "Occupancy", "Biodiversity")),
            _p("min_reads", "Minimum adjusted reads", "int", 3, "Detections below this count are not considered positive.", minimum=0, maximum=1_000_000, step=1),
            _p("min_reference_confidence", "Minimum reference confidence", "float", 0.70, "Taxa below this confidence require review.", minimum=0.0, maximum=1.0, step=0.05),
            _p("negative_control_multiplier", "Negative-control multiplier", "float", 1.0, "Background subtraction multiplier.", minimum=0.0, maximum=10.0, step=0.1, advanced=True),
        ),
        ("Negative controls", "Positive controls", "Sequencing depth", "Reference confidence", "Taxonomic ambiguity", "Site/date completeness", "Replicate consistency"),
        ("Contamination filtering", "Species detection", "Occupancy", "Biodiversity", "Rare/invasive alerts", "Temporal/spatial surveillance", "Reference confidence"),
        ("QIIME 2", "DADA2", "OBITools"), ("Marker reference library", "Taxonomy database", "Site metadata", "Species watch list"), ("Analyst", "Ecologist", "Surveillance reviewer"),
    ),
    "comparative_regulatory_genomics": ModuleContract(
        "comparative_regulatory_genomics", ("Homo sapiens", "Mus musculus", "Custom/other"), ("Species-specific builds", "HAL/VG alignment", "Custom/other"), ("Conservation", "Motif turnover", "Regulatory synteny", "Cross-species activity"),
        COMMON + (
            _p("analysis_profile", "Comparative profile", "select", "Cross-species activity", "Selects conservation and activity defaults.", options=("Conservation", "Motif turnover", "Regulatory synteny", "Cross-species activity")),
            _p("min_conservation", "Minimum conservation", "float", 0.50, "Regions below this score are treated as lineage-specific/low conservation.", minimum=0.0, maximum=1.0, step=0.05),
            _p("min_species", "Minimum species support", "int", 2, "Ortholog groups below this count receive review status.", minimum=2, maximum=100, step=1),
        ),
        ("Species/build consistency", "Lift-over quality", "Ortholog completeness", "Motif mapping", "Activity normalization", "Tissue matching"),
        ("Conserved elements", "Enhancer conservation", "Motif turnover", "Regulatory synteny", "TF activity comparison", "Gain/loss", "Comparative networks"),
        ("HAL tools", "BEDTools", "phastCons"), ("Multi-species alignment", "Orthology database", "Motif library", "Species annotations"), ("Analyst", "Evolutionary genomics specialist", "Biological reviewer"),
    ),
}


def contract_for(module_key: str) -> ModuleContract:
    return CONTRACTS[module_key]


def parameters_for(module_key: str, *, expert: bool = False) -> tuple[ParameterSpec, ...]:
    specs = CONTRACTS[module_key].parameters
    return specs if expert else tuple(spec for spec in specs if not spec.advanced)
