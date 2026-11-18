from __future__ import annotations

PROJECT_STAGES = (
    "Research Question",
    "Hypothesis",
    "Study Design",
    "Data Collection",
    "Data Ingestion",
    "Quality Control",
    "Analysis",
    "Discovery",
    "Candidate Prioritization",
    "Recommendation",
    "Validation Planning",
    "Experiment Execution",
    "Validation Review",
    "Interpretation",
    "Reporting",
    "Publication Preparation",
    "Reproducibility Archive",
    "Completed",
    "Archived",
)

STAGE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "Research Question": ("research_question", "scientific_objective"),
    "Hypothesis": ("hypothesis",),
    "Study Design": ("study_design",),
    "Data Collection": ("milestone",),
    "Data Ingestion": ("dataset",),
    "Quality Control": ("qc_complete",),
    "Analysis": ("completed_run",),
    "Discovery": ("candidate",),
    "Candidate Prioritization": ("ranked_candidate",),
    "Recommendation": ("recommendation",),
    "Validation Planning": ("validation_plan",),
    "Experiment Execution": ("experiment",),
    "Validation Review": ("validation_result",),
    "Interpretation": ("notebook_entry",),
    "Reporting": ("report",),
    "Publication Preparation": ("review_approval",),
    "Reproducibility Archive": ("frozen_run",),
    "Completed": ("completion_gate",),
    "Archived": ("archive_reason",),
}

ROLES = (
    "Administrator",
    "Lab Manager",
    "Principal Investigator",
    "Researcher",
    "Bioinformatician",
    "Data Analyst",
    "Reviewer",
    "Read-only Viewer",
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "Administrator": frozenset({"*"}),
    "Lab Manager": frozenset({"read", "write", "run", "review", "assign", "export"}),
    "Principal Investigator": frozenset({"read", "write", "run", "review", "approve", "export"}),
    "Researcher": frozenset({"read", "write", "run", "comment", "export"}),
    "Bioinformatician": frozenset({"read", "write", "run", "comment", "export"}),
    "Data Analyst": frozenset({"read", "write", "run", "comment", "export"}),
    "Reviewer": frozenset({"read", "review", "comment", "export"}),
    "Read-only Viewer": frozenset({"read"}),
}

DATA_ORIGINS = (
    "real_calculation",
    "imported_external_result",
    "rule_based_guidance",
    "model_prediction",
    "database_derived_evidence",
    "literature_derived_evidence",
    "user_entered_interpretation",
    "synthetic_demo_output",
    "hypothesis",
    "validation_result",
)

CANDIDATE_TYPES = (
    "Gene",
    "Transcript",
    "Variant",
    "Protein",
    "Peptide",
    "Metabolite",
    "Pathway",
    "Cell type",
    "Microbial taxon",
    "Molecular signature",
    "Biomarker",
    "Therapeutic target",
    "Drug",
    "Structural site",
    "Research hypothesis",
)

CANDIDATE_STATES = (
    "Detected",
    "Prioritized",
    "Under Review",
    "Shortlisted",
    "Validation Planned",
    "Validation Running",
    "Validated",
    "Rejected",
    "Deferred",
    "Archived",
)

RECOMMENDATION_STATES = (
    "Draft",
    "Generated",
    "Under Review",
    "Accepted",
    "Rejected",
    "Deferred",
    "Planned",
    "In Progress",
    "Implemented",
    "Validation Pending",
    "Validated",
    "Failed Validation",
    "Completed",
    "Superseded",
    "Archived",
)

HYPOTHESIS_STATES = (
    "Generated",
    "Draft",
    "Under Review",
    "Approved for Testing",
    "Experiment Planned",
    "Testing",
    "Supported",
    "Partially Supported",
    "Rejected",
    "Inconclusive",
    "Archived",
)

MODEL_STATES = (
    "Experimental",
    "Development",
    "Testing",
    "Internally Validated",
    "Externally Validated",
    "Approved for Research",
    "Deprecated",
    "Failed Validation",
    "Archived",
)

EVIDENCE_TYPES = (
    "Internal result",
    "Independent dataset",
    "Literature study",
    "Meta-analysis",
    "Database evidence",
    "Functional evidence",
    "Genetic evidence",
    "Pathway evidence",
    "Protein interaction",
    "Experimental validation",
    "Negative evidence",
    "Contradictory evidence",
    "User-entered interpretation",
    "Synthetic fixture",
)

WORKFLOW_TEMPLATES: dict[str, tuple[str, ...]] = {
    "rna_seq": ("ingest", "fastq_qc", "align", "quantify", "qc", "report"),
    "differential_expression": ("ingest", "design", "normalize", "fit", "fdr", "report"),
    "whole_genome_sequencing": ("ingest", "fastq_qc", "align", "variant_call", "annotate", "report"),
    "whole_exome_sequencing": ("ingest", "fastq_qc", "align", "coverage", "variant_call", "annotate"),
    "variant_prioritization": ("ingest", "normalize", "annotate", "inheritance", "rank", "review"),
    "single_cell_rna_seq": ("ingest", "cell_qc", "normalize", "integrate", "cluster", "annotate", "pseudobulk"),
    "proteomics": ("ingest", "identification_qc", "normalize", "differential", "pathway", "report"),
    "metabolomics": ("ingest", "peak_qc", "blank_correct", "drift_correct", "annotate", "differential"),
    "microbiome": ("ingest", "negative_control_qc", "profile", "compositional", "differential", "report"),
    "multi_omics": ("ingest", "harmonize", "layer_qc", "integrate", "ablation", "rank", "report"),
    "biomarker_discovery": ("ingest", "split", "nested_cv", "calibrate", "stability", "external_validation"),
    "pathway_enrichment": ("ingest", "background_validate", "ora_gsea", "redundancy", "network", "report"),
    "structural_biology": ("ingest", "structure_qc", "confidence", "pocket", "mutation", "report"),
    "drug_target_discovery": ("ingest", "target_evidence", "druggability", "safety", "off_target", "rank"),
    "literature_discovery": ("search", "identifier_validate", "deduplicate", "retraction_check", "grade", "gaps"),
    "laboratory_validation": ("plan", "controls", "execute", "qc", "interpret", "feedback"),
}

MODULE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "sequencing_quality": ("fastqc", "multiqc"),
    "alignment_mapping": ("star", "hisat2", "bwa-mem2", "minimap2", "samtools", "picard"),
    "differential_expression": ("Rscript",),
    "biomarker_discovery": (),
    "variant_prioritization": ("bcftools", "vep", "snpEff"),
    "pathway_enrichment": (),
    "multi_omics": ("Rscript",),
    "single_cell": (),
    "proteomics": ("msconvert", "diann"),
    "metabolomics": ("msconvert", "Rscript"),
    "microbiome": ("qiime", "kraken2", "bracken", "metaphlan", "humann"),
    "structural_biology": (),
    "drug_target_discovery": (),
    "experimental_design": (),
    "statistical_analysis": (),
    "literature_discovery": (),
    "hypothesis_generation": (),
    "laboratory_validation": (),
}

MODULE_LABELS = {
    "sequencing_quality": "Sequencing quality",
    "alignment_mapping": "Alignment and mapping",
    "differential_expression": "Differential expression",
    "biomarker_discovery": "Biomarker discovery",
    "variant_prioritization": "Variant prioritization",
    "pathway_enrichment": "Pathway enrichment",
    "multi_omics": "Multi-omics",
    "single_cell": "Single-cell",
    "proteomics": "Proteomics",
    "metabolomics": "Metabolomics",
    "microbiome": "Microbiome",
    "structural_biology": "Structural biology",
    "drug_target_discovery": "Drug and target discovery",
    "experimental_design": "Experimental design",
    "statistical_analysis": "Statistical analysis",
    "literature_discovery": "Literature discovery",
    "hypothesis_generation": "Hypothesis generation",
    "laboratory_validation": "Laboratory validation",
}

SYNTHETIC_NOTICE = (
    "SYNTHETIC DEMO DATA - NOT FOR SCIENTIFIC, CLINICAL, REGULATORY, OR PUBLICATION USE"
)
