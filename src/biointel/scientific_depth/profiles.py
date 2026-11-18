from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ModuleDepthProfile:
    key: str
    title: str
    engines: tuple[str, ...]
    references: tuple[str, ...]
    native_formats: tuple[str, ...]
    validations: tuple[str, ...]
    optimization: tuple[str, ...]
    boundary: str


# These profiles describe executable/readiness requirements. They never mark an
# unavailable third-party engine or reference database as bundled or validated.
_PROFILES: tuple[ModuleDepthProfile, ...] = (
    ModuleDepthProfile("epigenomics_chromatin", "Epigenomics depth", ("bwa", "samtools", "macs2", "deeptools"), ("Reference FASTA", "Gene annotation", "Motif database"), ("FASTQ", "BAM/CRAM", "BED/narrowPeak", "bigWig"), ("Replicate balance", "Peak reproducibility", "Differential-accessibility assumptions", "Genome-build match"), ("Indexed region access", "Chunked peak tables", "Cached signal summaries"), "Peak calls and motif findings require specialist tools, matched controls and orthogonal validation."),
    ModuleDepthProfile("metabolomics_lipidomics", "Metabolomics depth", ("openms",), ("Spectral library", "Retention-time standards", "Adduct table"), ("mzML", "MGF", "CSV/TSV feature table"), ("Blank subtraction", "Pooled-QC CV", "Batch drift", "Identification confidence"), ("Streaming mzML", "Feature-level caching", "Bounded spectrum previews"), "Feature matches are hypotheses until confirmed by retention time, MS/MS evidence and authentic standards."),
    ModuleDepthProfile("immunoinformatics_vaccine", "Immunoinformatics depth", ("netmhcpan", "netmhciipan"), ("HLA allele frequencies", "Pathogen proteome", "Allergen/toxin references"), ("FASTA", "CSV/TSV peptide table"), ("Allele coverage", "Conservancy", "Safety filters", "Experimental immunogenicity plan"), ("Batch peptide generation", "Deduplicated peptide cache", "Allele-parallel execution"), "Predicted epitopes are research candidates and require experimental immunogenicity and safety validation."),
    ModuleDepthProfile("antibody_biologics", "Antibody engineering depth", ("anarci", "igblast"), ("IMGT germlines", "Liability motif catalogue", "Structure templates"), ("FASTA", "CSV/TSV variant table", "PDB/mmCIF"), ("CDR numbering", "Humanness", "Aggregation/liability review", "Affinity assay linkage"), ("Sequence fingerprint cache", "Batch variant scoring", "Lazy structure loading"), "Computational developability does not establish manufacturability, efficacy or clinical safety."),
    ModuleDepthProfile("docking_dynamics", "Docking and dynamics depth", ("vina", "gromacs", "openmm"), ("Prepared receptor", "Ligand protonation states", "Force-field assets"), ("PDB/mmCIF", "SDF/MOL2", "trajectory summaries"), ("Pose replication", "Consensus scoring", "Trajectory equilibration", "Experimental-affinity linkage"), ("Background execution", "Checkpointed trajectories", "Bounded coordinate previews"), "Docking and simulation scores are model-dependent and are not measured affinity."),
    ModuleDepthProfile("pharmacogenomics", "Pharmacogenomics depth", ("bcftools", "whatshap", "vep"), ("Allele-definition release", "Guideline release", "Population frequencies"), ("VCF/BCF", "CSV/TSV medication table"), ("Phasing", "Copy-number awareness", "Allele-version traceability", "Human clinical review"), ("Indexed VCF queries", "Reference-version pinning", "Cached normalized variants"), "This is a research evidence workspace, not autonomous prescribing or clinical decision support."),
    ModuleDepthProfile("spatial_omics_pathology", "Spatial pathology depth", ("openslide", "cellpose"), ("Tissue image", "Spatial assay manifest", "Reference atlas"), ("H5AD", "OME-TIFF", "SVS/NDPI through adapter", "CSV/TSV coordinates"), ("Image registration", "ROI review", "Spatial-neighbourhood statistics", "Pathologist review"), ("Tiled image access", "ROI caches", "Sparse expression matrices"), "Spatial findings require image registration checks, biological replication and pathology review."),
    ModuleDepthProfile("single_cell_trajectory", "Single-cell trajectory depth", ("scanpy", "scvelo", "cellrank"), ("Cell atlas", "Ligand-receptor database", "Genome annotation"), ("H5AD", "MTX", "CSV/TSV cell metadata"), ("Cell QC", "Doublet/ambient-RNA review", "Replicate-aware inference", "Trajectory uncertainty"), ("Backed H5AD mode", "Sparse matrices", "Bounded embeddings"), "Trajectory and communication results are model-dependent and require replicate-aware biological validation."),
    ModuleDepthProfile("bioimage_microscopy", "Bioimage depth", ("cellpose", "stardist"), ("Pixel calibration", "Segmentation model", "Ground-truth annotations"), ("OME-TIFF", "TIFF", "PNG/JPEG", "CSV object table"), ("Segmentation quality", "Manual correction", "Batch/image drift", "Ground-truth comparison"), ("Tiled image processing", "GPU-optional queues", "Mask compression"), "Automated image segmentation must be reviewed against representative ground truth."),
    ModuleDepthProfile("clinical_trial_biomarker", "Clinical biomarker depth", (), ("Protocol", "Data dictionary", "Endpoint definitions"), ("CSV/TSV patient table",), ("Prespecified cut-offs", "Missing-data plan", "Multivariable adjustment", "External validation"), ("Cohort-level caching", "Lazy survival curves", "De-identified exports"), "Exploratory subgroups and cut-offs require prespecification and independent validation."),
    ModuleDepthProfile("genome_editing_safety", "Genome-editing safety depth", ("bowtie", "blastn", "bcftools"), ("Reference genome", "Population VCF", "Annotation GTF/GFF"), ("FASTA", "VCF", "BED", "CSV guide table"), ("Genome-wide off-target search", "Variant overlap", "Bulge/mismatch review", "Orthogonal safety assay"), ("Indexed genome search", "Guide cache", "Parallel candidate evaluation"), "In-silico specificity is not proof of editing safety."),
    ModuleDepthProfile("proteogenomics_neoantigen", "Proteogenomics depth", ("bcftools", "comet", "msgfplus"), ("Reference proteome", "HLA alleles", "Spectral libraries"), ("VCF", "FASTA", "mzML/MGF", "CSV evidence table"), ("Target-decoy FDR", "Variant-protein provenance", "Tumour-normal specificity", "Functional immune validation"), ("Spectrum streaming", "Candidate database cache", "Background PSM search"), "Neoantigen candidates require orthogonal peptide, tumour-specificity and immune-function validation."),
    ModuleDepthProfile("bioprocess_fermentation", "Bioprocess depth", (), ("Process units", "Batch phase definitions", "Golden batch"), ("CSV/TSV sensor time series",), ("Batch-specific time order", "Unit consistency", "Mass-balance assumptions", "Control-limit review"), ("Chunked time-series processing", "Downsampled live plots", "Batch caches"), "Process recommendations require controlled experiments and approved quality systems."),
    ModuleDepthProfile("causal_perturbation", "Causal inference depth", (), ("Covariate register", "Instrument definitions", "DAG assumptions"), ("CSV/TSV estimates",), ("Instrument strength", "Pleiotropy/sensitivity", "Confounding assessment", "Multiplicity correction"), ("Vectorized sensitivity analysis", "Cached bootstrap", "Bounded DAG rendering"), "Causal claims depend on design assumptions and cannot be established by association alone."),
    ModuleDepthProfile("explainable_ai_assurance", "Model assurance depth", (), ("Model card", "External validation cohort", "Subgroup definitions"), ("CSV predictions", "JSON model metadata"), ("Calibration", "Subgroup performance", "OOD detection", "Explanation stability"), ("Cached metrics", "Chunked predictions", "Sampled explanation plots"), "Explanations describe model behaviour and do not establish biological causality."),
    ModuleDepthProfile("multiomics_harmonization", "Multi-omics harmonization depth", (), ("Feature identifier maps", "Batch metadata", "Platform metadata"), ("CSV/TSV", "H5AD", "MTX"), ("Batch diagnostics", "Biological-signal preservation", "Identifier harmonization", "Missing-modality policy"), ("Sparse matrices", "Feature intersection cache", "Chunked normalization"), "Batch correction can remove biological signal and must preserve raw values and design context."),
    ModuleDepthProfile("glycomics_glycoproteomics", "Glycomics depth", ("openms",), ("Glycan database", "Fragment rules", "Protein annotation"), ("mzML/MGF", "CSV glycopeptide table"), ("Target-decoy FDR", "Site localization", "Occupancy uncertainty", "Manual spectrum review"), ("Spectrum streaming", "Library indexing", "Bounded fragment previews"), "Glycan/glycopeptide assignments require spectrum-level review and validated identification control."),
    ModuleDepthProfile("one_health_environmental", "One Health depth", ("kraken2", "bracken", "humann", "minimap2"), ("Taxonomy database", "AMR database", "Geographic metadata"), ("FASTQ/FASTA", "CSV/TSV surveillance table"), ("Source harmonization", "Contamination controls", "Temporal/geographic uncertainty", "AMR evidence"), ("Per-sample jobs", "Database pinning", "Incremental surveillance"), "Surveillance signals require epidemiological context, confirmatory testing and public-health review."),
    ModuleDepthProfile("synthetic_data_privacy", "Synthetic-data privacy depth", (), ("Privacy policy", "Quasi-identifier definitions", "Utility benchmark"), ("CSV/TSV",), ("k-anonymity", "l-diversity", "t-closeness", "Membership-inference testing"), ("Vectorized privacy groups", "Bounded attack simulations", "Seeded generation"), "Synthetic data reduces but does not eliminate disclosure risk."),
    ModuleDepthProfile("population_gwas", "GWAS depth", ("plink2", "regenie", "saige"), ("Reference panel", "Genome build", "Phenotype/covariate dictionary"), ("VCF/BCF", "PLINK BED/BIM/FAM", "summary statistics"), ("Sample/variant QC", "Population structure", "Relatedness", "External replication"), ("Indexed variants", "Chromosome-partitioned jobs", "Memory estimates"), "Association findings require ancestry-aware QC, replication and careful interpretation."),
    ModuleDepthProfile("structural_variant_repeat", "Structural-variant depth", ("samtools", "bcftools", "sniffles", "expansionhunter"), ("Reference genome", "Gene annotation", "Population SV resource"), ("VCF/BCF", "BEDPE", "BAM/CRAM"), ("Split-read/pair evidence", "Breakpoint confidence", "Inheritance", "Orthogonal confirmation"), ("Region-indexed reads", "Breakpoint caches", "Bounded evidence snapshots"), "Structural-variant calls require caller-specific QC and orthogonal confirmation."),
    ModuleDepthProfile("longitudinal_multiomics", "Longitudinal multi-omics depth", (), ("Visit schedule", "Subject metadata", "Feature maps"), ("CSV/TSV", "H5AD"), ("Within-subject modelling", "Unequal visits", "Missingness", "Batch/time confounding"), ("Long-format storage", "Subject caches", "Chunked mixed-model inputs"), "Longitudinal inference must account for repeated measures and informative missingness."),
    ModuleDepthProfile("rna_isoform_splicing", "RNA splicing depth", ("star", "mafft"), ("Transcript annotation", "Reference genome"), ("GTF/GFF", "BED", "junction tables"), ("Junction confidence", "Isoform ambiguity", "Replicate-aware PSI", "Long-read support"), ("Indexed annotations", "Sparse junction matrices", "Region queries"), "Isoform and splicing calls depend on alignment, annotation and replicate-aware statistics."),
    ModuleDepthProfile("epitranscriptomics", "Epitranscriptomics depth", (), ("Transcript annotation", "Modification motifs", "Editing database"), ("BED/GFF/GTF", "CSV site table"), ("Strand awareness", "Coverage support", "Sequencing-error separation", "Replicate validation"), ("Region indexes", "Site-level caches", "Bounded motif scans"), "RNA modification/editing signals require technology-specific controls and orthogonal validation."),
    ModuleDepthProfile("strain_microbiome", "Strain-resolved microbiome depth", ("kraken2", "bracken", "humann"), ("Taxonomy database", "Marker database", "AMR/virulence database"), ("FASTQ/FASTA", "abundance tables"), ("Contamination control", "Compositional statistics", "Strain confidence", "Mock-community benchmark"), ("Per-sample parallelism", "Database pinning", "Sparse abundance matrices"), "Strain-level assignments are database- and coverage-dependent."),
    ModuleDepthProfile("cell_atlas_mapping", "Cell-atlas mapping depth", ("scanpy",), ("Reference atlas", "Gene identifier map"), ("H5AD", "MTX", "CSV metadata"), ("Reference compatibility", "Batch/platform shift", "Unknown-cell detection", "Annotation confidence"), ("Backed reference access", "Embedding cache", "Sparse query matrices"), "Transferred labels require marker review and independent biological validation."),
    ModuleDepthProfile("phenotypic_screening", "Phenotypic screening depth", ("cellpose", "stardist"), ("Plate map", "Control wells", "Image calibration"), ("OME-TIFF/TIFF/PNG", "CSV object table"), ("Z-prime", "Edge effects", "Replicate consistency", "Dose-response QC"), ("Tiled images", "Plate-wise jobs", "Feature caches"), "Screening hits require orthogonal confirmation and assay-specific acceptance criteria."),
    ModuleDepthProfile("organoid_3d", "Organoid analytics depth", ("cellpose", "stardist"), ("Voxel calibration", "Plate map", "Ground-truth masks"), ("TIFF/OME-TIFF", "CSV measurements"), ("3D segmentation", "Tracking", "Batch effects", "Manual correction"), ("Chunked z-stacks", "GPU queues", "Compressed masks"), "Automated organoid phenotypes require manual QC and biological replication."),
    ModuleDepthProfile("protein_language_design", "Protein design depth", ("proteinmpnn", "rfdiffusion"), ("Model weights", "Structure templates", "Conservation constraints"), ("FASTA", "PDB/mmCIF", "CSV candidates"), ("Constraint enforcement", "Sequence diversity", "Structure feedback", "Wet-lab validation"), ("GPU-aware jobs", "Embedding cache", "Candidate deduplication"), "Generated sequences are hypotheses and require structural and experimental validation."),
    ModuleDepthProfile("enzyme_pathway_design", "Enzyme/pathway design depth", ("proteinmpnn",), ("Metabolic model", "EC/reaction database", "Structure templates"), ("FASTA", "SBML-like tables", "CSV flux table"), ("Active-site protection", "Flux feasibility", "Cofactor balance", "Experimental activity"), ("Reaction graph cache", "Sparse stoichiometry", "Candidate batching"), "Predicted pathway or enzyme improvements require organism-specific experimental validation."),
    ModuleDepthProfile("host_pathogen_interaction", "Host-pathogen interaction depth", (), ("Host/pathogen proteomes", "Interaction evidence", "Virulence database"), ("FASTA", "CSV interaction table"), ("Evidence provenance", "False-positive control", "Network bias", "Experimental interaction validation"), ("Sparse networks", "Evidence caches", "Bounded layouts"), "Predicted interactions require independent experimental support."),
    ModuleDepthProfile("virology_evolution", "Virology depth", ("mafft", "iqtree", "bcftools"), ("Reference genome", "Lineage definitions", "Sampling metadata"), ("FASTA", "VCF", "CSV metadata"), ("Mixed infection", "Recombination", "Low-frequency variants", "Temporal/geographic bias"), ("Sample-parallel consensus", "Indexed variants", "Tree caches"), "Evolutionary and outbreak interpretations require sampling context and confirmatory epidemiology."),
    ModuleDepthProfile("rare_variant_family", "Family genetics depth", ("bcftools", "whatshap", "vep"), ("Reference genome", "HPO", "Population frequencies", "Gene-disease evidence"), ("VCF/BCF", "PED/FAM", "CSV phenotype table"), ("Pedigree validation", "Phasing", "Mosaicism", "Segregation and clinical review"), ("Region-indexed variants", "Evidence cache", "Family-aware filtering"), "Variant prioritisation is research support and not a diagnostic conclusion."),
)

MODULE_PROFILES = {profile.key: profile for profile in _PROFILES}
# Core-module aliases and non-expansion workspaces. These keep legacy pages on
# the same depth/readiness contract without changing their established analysis.
MODULE_PROFILES.update({
    "flow_cytometry": ModuleDepthProfile(
        "flow_cytometry",
        "Flow-cytometry depth",
        (),
        ("Single-stained controls", "FMO/unstained controls", "Panel and instrument metadata", "Ground-truth/manual gating review"),
        ("FCS", "CSV/TSV event table", "Compensation matrix"),
        ("Compensation stability", "Transformation lock", "Doublet/time-drift review", "Control-aware gating", "Population reproducibility"),
        ("Bounded FCS decoding", "Sampled scatter previews", "Vectorized compensation", "Gate-audit export"),
        "Flow-cytometry populations require instrument QC, validated compensation, control-aware gates and representative manual review.",
    ),
    "clinical_pharma_core": ModuleDepthProfile("clinical_pharma_core", "Clinical validation depth", (), ("Protocol and endpoint definitions", "Independent validation cohort", "Bias/eligibility register"), ("CSV/TSV de-identified cohort",), ("Cohort flow", "Prespecified endpoints", "Calibration/subgroups", "Independent review"), ("De-identified bounded datasets", "Cached cohort summaries", "Background report generation"), "Clinical conclusions require independent prospective evidence and qualified human review."),
    "structural_bioinformatics_core": ModuleDepthProfile("structural_bioinformatics_core", "Structural bioinformatics depth", ("vina", "gromacs", "openmm"), ("Reference structure", "Ligand definitions", "Density/PAE assets"), ("PDB/mmCIF", "SDF/MOL2", "trajectory files"), ("Structure quality", "Biological assembly", "Pocket/contact validation", "Experimental support"), ("Lazy 3D rendering", "Coordinate downsampling", "Trajectory background jobs"), "Structural scores and visual contacts are hypotheses until experimentally validated."),
    "cancer_genomics_core": ModuleDepthProfile("cancer_genomics_core", "Cancer genomics depth", ("bcftools", "vep"), ("Reference genome", "Cancer gene census", "Population frequencies", "Clinical annotation release"), ("VCF/MAF", "CNV tables", "RNA expression"), ("Tumour-normal provenance", "Purity/ploidy", "Multiple-testing control", "Independent cohort validation"), ("Chromosome-partitioned processing", "Sparse alteration matrices", "Cached annotations"), "Cancer-genomics findings are research evidence and not autonomous clinical interpretation."),
    "synthetic_biology_core": ModuleDepthProfile("synthetic_biology_core", "Synthetic-biology depth", (), ("Host codon table", "Part registry", "Biosafety constraints"), ("FASTA/GenBank-like sequence", "SBOL-lite JSON", "CSV parts"), ("Sequence integrity", "Host burden", "Failure-mode review", "Experimental construct validation"), ("Part caches", "Bounded sequence simulation", "Versioned construct manifests"), "Circuit behaviour and biosafety require organism-specific experimental validation."),
    "knowledge_graph_core": ModuleDepthProfile("knowledge_graph_core", "Knowledge-graph depth", (), ("Ontology releases", "Provider snapshots", "Retraction metadata"), ("CSV/JSON/RDF-like edge tables",), ("Entity resolution", "Claim-source traceability", "Contradictory evidence", "Temporal provenance"), ("Indexed graph search", "Evidence caches", "Bounded layouts"), "Graph paths do not establish causality and must preserve exact supporting evidence."),
    "multiomics_biomarker_core": ModuleDepthProfile("multiomics_biomarker_core", "Biomarker-discovery depth", (), ("Feature maps", "External validation cohort", "Analysis protocol"), ("CSV/TSV", "H5AD", "MTX"), ("Nested validation", "Leakage audit", "Calibration", "Panel stability"), ("Sparse matrices", "Cached folds", "Background resampling"), "Exploratory biomarker panels require independent validation and locked analysis plans."),
    "offline_copilot_core": ModuleDepthProfile("offline_copilot_core", "Offline copilot depth", ("llama_cpp",), ("Approved local corpus", "Biomedical ontology", "Citation index"), ("PDF/HTML/TXT/JSON documents",), ("Citation grounding", "Hallucination tests", "Conflict detection", "Clinical-action blocking"), ("Quantized local models", "Embedding cache", "Bounded context"), "The copilot must not replace expert scientific or clinical judgment."),
    "plugin_marketplace_core": ModuleDepthProfile("plugin_marketplace_core", "Plugin security depth", (), ("Trusted publisher list", "Permission policy", "Compatibility matrix"), ("ZIP plugin package", "JSON manifest"), ("Signature verification", "Static security scan", "Permission isolation", "Rollback"), ("Isolated environments", "Disabled-by-default install", "Dependency locks"), "Untrusted plugin code must never execute merely because an archive was uploaded."),
    "store_readiness_core": ModuleDepthProfile("store_readiness_core", "Windows product readiness", (), ("Publisher certificate", "Legal URLs", "Store metadata"), ("EXE/MSI/MSIX artifacts",), ("Signed binaries", "Upgrade/rollback", "Uninstall", "Physical Windows matrix"), ("Deterministic build", "Delta-update planning", "Crash-log rotation"), "Store acceptance, certificate trust and SmartScreen reputation are external outcomes."),
    "background_jobs_core": ModuleDepthProfile("background_jobs_core", "Background execution depth", (), ("Resource policy", "Worker state database", "Artifact registry"), ("JSON job manifests",), ("Heartbeat", "Process-tree cancellation", "Checkpoint recovery", "Resource limits"), ("Separate workers", "Priority queues", "Persistent retries"), "Heavy jobs should not execute inside a Streamlit rerun process."),
    "workflow_builder_core": ModuleDepthProfile("workflow_builder_core", "Workflow execution depth", (), ("Typed node schema", "Container/tool versions", "Resource policy"), ("Workflow JSON/YAML",), ("DAG validation", "Input/output compatibility", "Checkpoint resume", "Provenance"), ("Node caching", "Critical-path scheduling", "Scatter/gather limits"), "A visually valid workflow is not scientifically valid until inputs, tools and parameters are qualified."),
    "pangenome_core": ModuleDepthProfile("pangenome_core", "Pangenome execution depth", ("minigraph", "vg", "odgi", "graphaligner"), ("Assembly set", "GFF/GTF annotations", "Reference path"), ("GFA", "FASTA", "GFF/GTF"), ("Assembly quality", "Path recovery", "Bubble/variant validation", "Graph benchmark"), ("Graph indexing", "Region/path queries", "Background graph builds"), "Pangenome paths and bubbles require assembly, annotation and graph-quality validation."),
    "long_read_core": ModuleDepthProfile("long_read_core", "Long-read assembly depth", ("flye", "hifiasm", "busco", "merqury"), ("Reference/related genome", "BUSCO lineage", "k-mer database"), ("FASTQ/FASTA", "GFA", "assembly FASTA"), ("Read QC", "Polishing", "Haplotig review", "Completeness/contamination"), ("Checkpointed assembly", "Disk/RAM estimation", "Chunked read QC"), "Assemblies require platform-aware polishing and independent completeness/contamination assessment."),
    "pathogen_outbreak_core": ModuleDepthProfile("pathogen_outbreak_core", "Outbreak genomics depth", ("mafft", "iqtree", "bcftools"), ("Reference genome", "Lineage definitions", "AMR database"), ("FASTA", "VCF", "CSV epidemiology"), ("Recombination", "Sampling bias", "Transmission uncertainty", "AMR confirmation"), ("Sample-parallel consensus", "Tree cache", "Incremental surveillance"), "Genomic clusters do not by themselves prove direct transmission."),
    "single_cell_core": ModuleDepthProfile("single_cell_core", "Single-cell analysis depth", ("scanpy", "scvelo", "cellrank"), ("Reference atlas", "Gene annotation", "Ligand-receptor database"), ("H5AD", "MTX", "10x matrices"), ("Cell QC", "Doublets/ambient RNA", "Replicate-aware differential analysis", "Annotation confidence"), ("Sparse matrices", "Backed mode", "Embedding cache"), "Cells are not biological replicates; confirm findings using replicate-aware analyses."),
    "metagenomics_core": ModuleDepthProfile("metagenomics_core", "Metagenomics execution depth", ("kraken2", "bracken", "humann"), ("Pinned taxonomy database", "Functional database", "AMR/virulence database"), ("FASTQ/FASTA", "abundance tables"), ("Negative/mock controls", "Host depletion", "Compositional statistics", "Database/version traceability"), ("Per-sample jobs", "Database pinning", "Checkpoint resume"), "Taxonomic and functional profiles depend on controls, database version and sufficient coverage."),
    "universal_file_inspector": ModuleDepthProfile("universal_file_inspector", "Universal file-inspection depth", (), ("Format signatures", "Schema rules", "Privacy policy"), ("Scientific file families",), ("Magic-byte detection", "Corruption/schema checks", "Resource estimate", "Sensitive-data warning"), ("Streaming inspection", "Bounded previews", "Content-hash cache"), "Format detection and previews do not establish biological validity."),
    "cross_module_workspace": ModuleDepthProfile("cross_module_workspace", "Cross-module project depth", (), ("Project schema", "Dataset/run identifiers", "Storage policy"), ("Content-addressed project assets",), ("Immutable lineage", "Version locking", "Permission review", "Exact rerun"), ("Deduplicated assets", "Snapshot manifests", "Bounded project indexes"), "A project snapshot is reproducible only when external tools and databases are pinned."),
    "workflow_builder_v2": ModuleDepthProfile("workflow_builder_v2", "Workflow execution depth", (), ("Typed node schema", "Container/tool versions", "Resource policy"), ("Workflow JSON/YAML",), ("DAG validation", "Input/output compatibility", "Checkpoint resume", "Provenance"), ("Node caching", "Critical-path scheduling", "Scatter/gather limits"), "A visually valid workflow is not scientifically valid until inputs, tools and parameters are qualified."),
    "background_job_engine": ModuleDepthProfile("background_job_engine", "Background execution depth", (), ("Resource policy", "Worker state database", "Artifact registry"), ("JSON job manifests",), ("Heartbeat", "Process-tree cancellation", "Checkpoint recovery", "Resource limits"), ("Separate workers", "Priority queues", "Persistent retries"), "Heavy jobs should not execute inside a Streamlit rerun process."),
    "unified_report_builder": ModuleDepthProfile("unified_report_builder", "Scientific reporting depth", (), ("Report templates", "Citation policy", "Approval roles"), ("PDF/DOCX/HTML/JSON",), ("Claim-source traceability", "Method/parameter completeness", "Version locking", "Reviewer approval"), ("Background rendering", "Asset reuse", "Deterministic bundles"), "Reports are only as reliable as their underlying data, methods and review."),
    "reference_lifecycle_v2": ModuleDepthProfile("reference_lifecycle_v2", "Reference lifecycle depth", (), ("Provider release metadata", "Licence terms", "Checksums"), ("Local archives/directories",), ("Checksum verification", "Version activation", "Rollback", "Compatibility"), ("Resumable downloads", "Managed storage", "Index-build jobs"), "Reference data must be licensed, versioned and scientifically suitable for the analysis."),
    "provenance_ledger_v2": ModuleDepthProfile("provenance_ledger_v2", "Provenance depth", (), ("Identity policy", "Clock policy", "Retention policy"), ("JSONL/SQLite ledger",), ("Hash chaining", "Environment capture", "External tool provenance", "Tamper evidence"), ("Append-only writes", "Batch commits", "Ledger compaction without mutation"), "Local provenance is not equivalent to an independently timestamped or regulated audit trail."),
    "evidence_citation_engine": ModuleDepthProfile("evidence_citation_engine", "Evidence and citation depth", (), ("Provider snapshots", "Retraction metadata", "Entity normalization"), ("DOI/PMID/URL metadata",), ("Claim-source mapping", "Evidence strength", "Conflict/retraction review", "Versioned citations"), ("Indexed retrieval", "Deduplicated citations", "Cached entity maps"), "Citations must support the exact claim and may still represent weak or conflicting evidence."),
    "model_registry_v2": ModuleDepthProfile("model_registry_v2", "Model lifecycle depth", (), ("Dataset snapshots", "Evaluation protocol", "Approval policy"), ("Model package/manifest",), ("Lineage", "Calibration/external validation", "Approval gates", "Rollback"), ("Artifact deduplication", "Lazy model loading", "Metric caches"), "A registered model is not validated or approved merely because an artifact exists."),
    "collaboration_review_v2": ModuleDepthProfile("collaboration_review_v2", "Scientific review depth", (), ("Reviewer roles", "Decision policy", "Retention policy"), ("Version-linked review records",), ("Identity", "Version-linked comments", "Conflict resolution", "Locked decisions"), ("Indexed review status", "Notification batching", "Immutable decision records"), "Formal electronic signatures and regulated review require organization-specific validation."),
    "offline_scientific_copilot_v2": ModuleDepthProfile("offline_scientific_copilot_v2", "Offline copilot depth", ("llama_cpp",), ("Approved local corpus", "Biomedical ontology", "Citation index"), ("PDF/HTML/TXT/JSON documents",), ("Citation grounding", "Hallucination tests", "Conflict detection", "Clinical-action blocking"), ("Quantized local models", "Embedding cache", "Bounded context"), "The copilot must not replace expert scientific or clinical judgment."),
    "data_lakehouse_v2": ModuleDepthProfile("data_lakehouse_v2", "Data lakehouse depth", (), ("Metadata schema", "Access policy", "Retention rules"), ("Local scientific assets",), ("Content identity", "Schema/index freshness", "Access filtering", "Archive/restore"), ("Incremental indexing", "Hash cache", "Tiered storage"), "Indexed assets still require scientific QC and appropriate access controls."),
    "benchmark_validation_v2": ModuleDepthProfile("benchmark_validation_v2", "Benchmarking depth", (), ("Locked benchmark datasets", "Expected outputs", "Hardware metadata"), ("Benchmark manifests/results",), ("Gold-standard provenance", "Tolerance ranges", "Version regression", "Scientific metrics"), ("Cached fixtures", "Isolated workers", "Hardware-normalized reports"), "Passing software benchmarks does not by itself establish clinical or biological validity."),
    "plugin_marketplace_v2": ModuleDepthProfile("plugin_marketplace_v2", "Plugin security depth", (), ("Trusted publisher list", "Permission policy", "Compatibility matrix"), ("ZIP plugin package", "JSON manifest"), ("Signature verification", "Static security scan", "Permission isolation", "Rollback"), ("Isolated environments", "Disabled-by-default install", "Dependency locks"), "Untrusted plugin code must never execute merely because an archive was uploaded."),
    "document_intelligence_core": ModuleDepthProfile("document_intelligence_core", "Document intelligence depth", (), ("OCR language assets", "Citation policy", "Approved extraction schema"), ("PDF/DOCX/XLSX/HTML/images",), ("Page-level provenance", "Table/figure review", "OCR confidence", "Citation traceability"), ("Page streaming", "OCR caches", "Background batch extraction"), "Extracted text and tables require source-page review before scientific use."),
})


# Step 128 next-generation biomedical modules.
MODULE_PROFILES.update({
    "digital_pathology_foundation": ModuleDepthProfile(
        "digital_pathology_foundation", "Digital pathology foundation-model depth",
        ("openslide", "cellpose"),
        ("Scanner/site qualification", "Pathology model card", "Ground-truth annotations", "Tissue ontology"),
        ("SVS/NDPI/MRXS through adapter", "OME-TIFF/TIFF", "CSV/TSV tile table"),
        ("Tissue coverage", "Scanner/site drift", "OOD/uncertainty", "Pathologist review"),
        ("Tile streaming", "Embedding cache", "GPU queues", "ROI-level loading"),
        "Foundation-model pathology outputs require validated models, scanner/site qualification and pathologist review.",
    ),
    "long_read_epigenome": ModuleDepthProfile(
        "long_read_epigenome", "Long-read epigenome depth",
        ("dorado", "modkit", "samtools", "whatshap"),
        ("Reference genome", "Modification model release", "Imprinting/DMR catalogue", "Genome build"),
        ("bedMethyl/bedGraph", "BAM/CRAM through adapter", "CSV/TSV"),
        ("Coverage", "Phasing", "Condition replication", "Orthogonal methylation validation"),
        ("Indexed region queries", "Chunked methylation tables", "Haplotype caches"),
        "Long-read methylation and imprinting findings depend on model, coverage, phasing and orthogonal confirmation.",
    ),
    "single_cell_long_read_isoforms": ModuleDepthProfile(
        "single_cell_long_read_isoforms", "Single-cell long-read isoform depth",
        ("minimap2", "samtools"),
        ("Transcript annotation", "Cell barcode whitelist", "Reference genome", "Replicate metadata"),
        ("BAM/CRAM through adapter", "GTF/GFF", "CSV/TSV isoform table"),
        ("Barcode/UMI QC", "Full-length support", "Junction validation", "Replicate-aware inference"),
        ("Sparse cell-transcript matrices", "Backed storage", "Transcript cache"),
        "Cells are not biological replicates; cluster-specific isoform shifts require replicate-aware validation.",
    ),
    "biomedical_foundation_model_hub": ModuleDepthProfile(
        "biomedical_foundation_model_hub", "Foundation-model hub depth",
        (),
        ("Model cards", "Weight checksums", "Licences", "Benchmark protocols", "Hardware manifest"),
        ("JSON/YAML model metadata", "CSV benchmark tables", "Local model directories"),
        ("Licence review", "Asset integrity", "Task compatibility", "External validation", "OOD testing"),
        ("Content-addressed model cache", "Lazy model loading", "Hardware preflight"),
        "Model availability and benchmark scores do not establish fitness for a specific biomedical intended use.",
    ),
    "amr_surveillance": ModuleDepthProfile(
        "amr_surveillance", "AMR surveillance depth",
        ("kraken2", "bcftools", "minimap2", "amrfinderplus", "resfinder"),
        ("Pinned AMR database", "Taxonomy release", "Typing scheme", "Phenotype standards"),
        ("FASTQ/FASTA through pipeline", "VCF", "CSV/TSV isolate table"),
        ("Species confirmation", "Genotype-phenotype concordance", "Contamination", "Epidemiological review"),
        ("Per-isolate jobs", "Database pinning", "Incremental surveillance"),
        "Genomic resistance predictions do not replace susceptibility testing or public-health interpretation.",
    ),
    "spatial_medicine_tme": ModuleDepthProfile(
        "spatial_medicine_tme", "Spatial medicine and TME depth",
        ("openslide", "cellpose", "scanpy"),
        ("Tissue image", "Spatial assay manifest", "Cell-type reference", "Pathology annotations"),
        ("H5AD", "OME-TIFF", "CSV/TSV spots/cells"),
        ("Registration", "Segmentation", "Patient replication", "Neighborhood uncertainty", "Pathologist review"),
        ("Tiled images", "Sparse matrices", "ROI caches"),
        "Tumour-microenvironment patterns are exploratory until registration, pathology and cohort validation are complete.",
    ),
    "gene_therapy_vector": ModuleDepthProfile(
        "gene_therapy_vector", "Gene-therapy vector depth",
        (),
        ("Vector-specific packaging limits", "Promoter/tropism evidence", "Immunogenicity evidence", "Biosafety policy"),
        ("FASTA/GenBank through adapter", "CSV/TSV construct table"),
        ("Cargo integrity", "Packaging capacity", "Integration risk", "Immunogenicity", "Manufacturing review"),
        ("Sequence validation cache", "Construct deduplication", "Background off-target review"),
        "Vector engineering scores do not establish biodistribution, genotoxicity, manufacturability or clinical safety.",
    ),
    "cell_therapy_cart": ModuleDepthProfile(
        "cell_therapy_cart", "Cell-therapy and CAR-T depth",
        ("anarci", "igblast"),
        ("Antigen expression atlas", "Germline references", "Cell-product QC", "Safety evidence"),
        ("FASTA", "CSV/TSV construct and assay tables"),
        ("Antigen specificity", "Off-tumour expression", "Exhaustion", "Manufacturability", "Functional validation"),
        ("Sequence cache", "Batch construct scoring", "Evidence-linked review"),
        "Computational CAR-T prioritisation requires functional, safety and manufacturing validation.",
    ),
    "federated_biomedical_ai": ModuleDepthProfile(
        "federated_biomedical_ai", "Federated biomedical AI depth",
        (),
        ("Site governance agreements", "Privacy policy", "Locked evaluation protocol", "Threat model"),
        ("CSV/JSON round metrics", "Signed update manifests"),
        ("Site drift", "Secure aggregation", "Privacy budget", "Subgroup fairness", "External validation"),
        ("Round-metric cache", "Bounded audit logs", "Checkpointed aggregation"),
        "Federation does not automatically guarantee privacy, fairness, security or scientific validity.",
    ),
    "clinical_biomarker_survival": ModuleDepthProfile(
        "clinical_biomarker_survival", "Clinical biomarker and survival depth",
        (),
        ("Protocol", "Endpoint definitions", "Prespecified cut-off", "External validation cohort"),
        ("CSV/TSV de-identified cohort",),
        ("Missing-data plan", "Proportional-hazards checks", "Calibration", "Site heterogeneity", "Independent validation"),
        ("Cohort caches", "Background resampling", "De-identified exports"),
        "Exploratory biomarker strata require prespecification and independent clinical validation.",
    ),
    "protein_ligand_codesign": ModuleDepthProfile(
        "protein_ligand_codesign", "Protein-ligand co-design depth",
        ("proteinmpnn", "rfdiffusion", "vina", "colabfold"),
        ("Prepared structures", "Ligand states", "Model weights", "Selectivity panel"),
        ("PDB/mmCIF", "SDF/MOL2", "FASTA", "CSV/TSV candidate table"),
        ("Constraint enforcement", "Pose/structure validation", "Selectivity", "Experimental binding"),
        ("GPU-aware queues", "Structure cache", "Candidate deduplication"),
        "Joint design scores are hypotheses and do not establish affinity, selectivity or biological activity.",
    ),
    "pangenome_population_medicine": ModuleDepthProfile(
        "pangenome_population_medicine", "Pangenome population-medicine depth",
        ("minigraph", "vg", "odgi"),
        ("Population assemblies", "Reference paths", "Clinical evidence release", "Ancestry metadata"),
        ("GFA", "VCF/BCF", "CSV/TSV population table"),
        ("Population representation", "Reference bias", "Graph coordinate traceability", "Clinical evidence review"),
        ("Graph indexing", "Population-frequency cache", "Region queries"),
        "Population-specific graph findings do not establish individual clinical risk without validated evidence.",
    ),
    "pharmacovigilance_intelligence": ModuleDepthProfile(
        "pharmacovigilance_intelligence", "Pharmacovigilance depth",
        (),
        ("Drug/event dictionaries", "Deduplication rules", "Exposure context", "Review policy"),
        ("CSV/TSV adverse-event reports",),
        ("Duplicate reports", "Disproportionality stability", "Confounding/reporting bias", "Clinical review"),
        ("Incremental aggregation", "Coded-term cache", "Bounded report previews"),
        "Spontaneous-report signals do not prove causality, incidence or comparative risk.",
    ),
    "synthetic_cohort_trial": ModuleDepthProfile(
        "synthetic_cohort_trial", "Synthetic cohort and trial-simulation depth",
        (),
        ("Scenario assumptions", "Outcome model", "Site/arm definitions", "Random seeds"),
        ("CSV/TSV synthetic cohort", "JSON scenario manifest"),
        ("Covariate balance", "Scenario sensitivity", "Missingness/dropout", "Reproducibility"),
        ("Seeded simulation", "Vectorized scenarios", "Background Monte Carlo"),
        "Synthetic cohorts are design tools and must never be represented as real clinical evidence.",
    ),
    "autonomous_lab_planner": ModuleDepthProfile(
        "autonomous_lab_planner", "Laboratory experiment-planning depth",
        (),
        ("Biosafety policy", "Approved protocols", "Cost catalogue", "Instrument availability"),
        ("CSV/TSV plan", "JSON protocol draft"),
        ("Controls", "Replication", "Randomization", "Resource feasibility", "Human approval"),
        ("Template reuse", "Cost cache", "Schedule-aware planning"),
        "The planner cannot authorise or autonomously execute experiments; human scientific and safety approval is mandatory.",
    ),
})


# Step 153 guarantees a transparent, deterministic local workflow for every
# scientific profile while retaining any specialist external engines.  The
# domain-specialized built-in workflow is deliberately labelled as exploratory and bounded; it is
# never reported as a substitute for confirmatory third-party pipelines.
for _module_key, _profile in list(MODULE_PROFILES.items()):
    _native_engine = f"biointel_native::{_module_key}"
    if _native_engine not in _profile.engines:
        MODULE_PROFILES[_module_key] = replace(
            _profile,
            engines=(_native_engine, *_profile.engines),
        )


def profile_for(module_key: str) -> ModuleDepthProfile | None:
    return MODULE_PROFILES.get(module_key)
