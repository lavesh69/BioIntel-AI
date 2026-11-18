from __future__ import annotations

"""Domain-family registry for the native scientific workflow engine.

Kept separate from execution logic so family metadata remains auditable and
the runtime engine stays within the repository maintainability budget.
"""

_FLOW = {"flow_cytometry"}
_METABOLOMICS = {"metabolomics_lipidomics"}
_GLYCOMICS = {"glycomics_glycoproteomics"}
_PROTEOGENOMICS = {"proteogenomics_neoantigen"}
_IMAGING = {"bioimage_microscopy"}
_PATHOLOGY = {"digital_pathology_foundation", "organoid_3d", "phenotypic_screening"}
_SPATIAL = {"spatial_omics_pathology", "spatial_medicine_tme"}
_GENOMIC_VARIANT = {
    "population_gwas",
    "rare_variant_family",
    "structural_variant_repeat",
    "pharmacogenomics",
    "cancer_genomics_core",
}
_SURVIVAL = {"clinical_trial_biomarker", "clinical_biomarker_survival", "clinical_pharma_core"}
_PHARMACOVIGILANCE = {"pharmacovigilance_intelligence"}
_PRIVACY = {"synthetic_data_privacy"}
_BIOPROCESS = {"bioprocess_fermentation"}
_FEDERATED = {"federated_biomedical_ai"}
_STRUCTURAL = {"docking_dynamics", "protein_ligand_codesign"}
_CAUSAL = {"causal_perturbation"}
_NETWORK = {"knowledge_graph_core", "host_pathogen_interaction"}
_CRISPR = {"genome_editing_safety"}
_ANTIBODY = {"antibody_biologics"}
_VACCINE = {"immunoinformatics_vaccine"}
_LONG_READ = {"long_read_core", "long_read_epigenome", "pangenome_core", "pangenome_population_medicine", "single_cell_long_read_isoforms"}
_ISOFORM = {"rna_isoform_splicing"}
_SINGLE_CELL = {"cell_atlas_mapping", "single_cell_core", "single_cell_trajectory"}
_EPIGENOMICS = {"epigenomics_chromatin", "epitranscriptomics"}
_AMR = {"amr_surveillance"}
_GENE_THERAPY = {"gene_therapy_vector"}
_CELL_THERAPY = {"cell_therapy_cart"}
_PROTEIN_DESIGN = {"protein_language_design"}
_ENZYME_DESIGN = {"enzyme_pathway_design"}
_STRUCTURAL_PROTEIN = {"structural_bioinformatics_core"}
_VIROLOGY = {"virology_evolution"}
_SYNTHETIC_BIOLOGY = {"synthetic_biology_core"}
_SEQUENCE = {
}
_MULTIOMICS = {
    "longitudinal_multiomics",
    "multiomics_biomarker_core",
    "multiomics_harmonization",
}
_MODEL_ASSURANCE = {
    "benchmark_validation_v2",
    "biomedical_foundation_model_hub",
    "explainable_ai_assurance",
    "model_registry_v2",
}
_TRIAL = {"autonomous_lab_planner", "synthetic_cohort_trial"}
_SURVEILLANCE = {
    "metagenomics_core",
    "one_health_environmental",
    "pathogen_outbreak_core",
    "strain_microbiome",
}
_JOB_ORCHESTRATION = {"background_job_engine", "background_jobs_core"}
_COLLABORATION_REVIEW = {"collaboration_review_v2"}
_WORKSPACE_LINEAGE = {"cross_module_workspace"}
_DATA_LAKEHOUSE = {"data_lakehouse_v2"}
_EVIDENCE_CITATION = {"evidence_citation_engine"}
_OFFLINE_COPILOT = {"offline_copilot_core", "offline_scientific_copilot_v2"}
_PLUGIN_SECURITY = {"plugin_marketplace_core", "plugin_marketplace_v2"}
_PROVENANCE_LEDGER = {"provenance_ledger_v2"}
_REFERENCE_LIFECYCLE = {"reference_lifecycle_v2"}
_STORE_RELEASE = {"store_readiness_core"}
_REPORT_GOVERNANCE = {"unified_report_builder"}
_FILE_INSPECTION = {"universal_file_inspector"}
_WORKFLOW_ORCHESTRATION = {"workflow_builder_core", "workflow_builder_v2"}
_DOCUMENT_INTELLIGENCE = {"document_intelligence_core"}
_PLATFORM = set()


def _family_for(module_key: str) -> str:
    for family, keys in (
        ("flow-cytometry", _FLOW),
        ("mass-spectrometry", _METABOLOMICS),
        ("glycomics", _GLYCOMICS),
        ("proteogenomics", _PROTEOGENOMICS),
        ("bioimaging", _IMAGING),
        ("pathology-ai", _PATHOLOGY),
        ("spatial", _SPATIAL),
        ("genomic-variant", _GENOMIC_VARIANT),
        ("clinical-survival", _SURVIVAL),
        ("pharmacovigilance", _PHARMACOVIGILANCE),
        ("privacy", _PRIVACY),
        ("bioprocess", _BIOPROCESS),
        ("federated-ai", _FEDERATED),
        ("structural-chemistry", _STRUCTURAL),
        ("causal-inference", _CAUSAL),
        ("knowledge-network", _NETWORK),
        ("crispr-safety", _CRISPR),
        ("antibody-engineering", _ANTIBODY),
        ("vaccine-design", _VACCINE),
        ("long-read", _LONG_READ),
        ("isoform-analysis", _ISOFORM),
        ("single-cell", _SINGLE_CELL),
        ("epigenomics", _EPIGENOMICS),
        ("amr-analysis", _AMR),
        ("gene-therapy", _GENE_THERAPY),
        ("cell-therapy", _CELL_THERAPY),
        ("protein-design", _PROTEIN_DESIGN),
        ("enzyme-design", _ENZYME_DESIGN),
        ("structural-protein", _STRUCTURAL_PROTEIN),
        ("virology-evolution", _VIROLOGY),
        ("synthetic-biology", _SYNTHETIC_BIOLOGY),
        ("sequence-engineering", _SEQUENCE),
        ("multiomics", _MULTIOMICS),
        ("model-assurance", _MODEL_ASSURANCE),
        ("trial-design", _TRIAL),
        ("surveillance", _SURVEILLANCE),
        ("job-orchestration", _JOB_ORCHESTRATION),
        ("collaboration-review", _COLLABORATION_REVIEW),
        ("workspace-lineage", _WORKSPACE_LINEAGE),
        ("data-lakehouse", _DATA_LAKEHOUSE),
        ("evidence-citation", _EVIDENCE_CITATION),
        ("offline-copilot", _OFFLINE_COPILOT),
        ("plugin-security", _PLUGIN_SECURITY),
        ("provenance-ledger", _PROVENANCE_LEDGER),
        ("reference-lifecycle", _REFERENCE_LIFECYCLE),
        ("store-release", _STORE_RELEASE),
        ("report-governance", _REPORT_GOVERNANCE),
        ("file-inspection", _FILE_INSPECTION),
        ("workflow-orchestration", _WORKFLOW_ORCHESTRATION),
        ("document-intelligence", _DOCUMENT_INTELLIGENCE),
        ("platform-governance", _PLATFORM),
    ):
        if module_key in keys:
            return family
    return "general-scientific"


_FAMILY_EXPECTED: dict[str, tuple[str, ...]] = {
    "flow-cytometry": ("event/channel matrix", "optional Time", "optional control labels"),
    "mass-spectrometry": ("feature", "sample", "intensity", "optional sample_type/injection_order"),
    "glycomics": ("PSM score", "target/decoy", "glycan", "site localization"),
    "proteogenomics": ("PSM score", "target/decoy", "variant provenance", "tumour/HLA evidence"),
    "bioimaging": ("image_id", "object_id", "numeric morphology/intensity features"),
    "pathology-ai": ("slide/image ID", "patient ID", "tile/object ID", "truth/prediction"),
    "spatial": ("x", "y", "numeric signal", "optional sample/region"),
    "genomic-variant": ("variant/sample/genotype or domain-specific variant summary columns",),
    "clinical-survival": ("time", "event", "optional group"),
    "pharmacovigilance": ("drug", "event", "optional report_id"),
    "privacy": ("quasi-identifiers", "optional sensitive attribute"),
    "bioprocess": ("time", "batch", "numeric sensor values"),
    "federated-ai": ("site", "round", "metric or loss", "optional sample count"),
    "structural-chemistry": ("SMILES and/or ligand/pose score table",),
    "causal-inference": ("instrument", "beta_exposure", "beta_outcome", "se_outcome"),
    "knowledge-network": ("source", "target", "optional score/evidence"),
    "crispr-safety": ("guide sequence", "PAM", "off-target and population-variant evidence"),
    "antibody-engineering": ("chain-paired amino-acid sequences", "numbering/germline metadata"),
    "vaccine-design": ("peptide", "HLA allele", "binding rank/affinity", "safety annotations"),
    "long-read": ("read/contig length", "quality", "coverage/alignment evidence"),
    "isoform-analysis": ("transcript ID", "gene", "junction/read support", "novelty class"),
    "single-cell": ("cell-by-feature counts", "sample/donor", "batch metadata"),
    "epigenomics": ("chrom", "start", "end", "replicate", "FDR/signal"),
    "amr-analysis": ("isolate", "AMR gene/call", "drug", "phenotype where available"),
    "gene-therapy": ("vector/transgene DNA sequence", "serotype/capsid", "immunity and integration evidence"),
    "cell-therapy": ("construct sequence", "target antigen", "healthy-tissue and functional assay evidence"),
    "protein-design": ("designed protein sequence", "model confidence", "novelty and experimental evidence"),
    "enzyme-design": ("enzyme sequence", "reaction", "thermodynamic/flux/kinetic evidence"),
    "structural-protein": ("structure ID", "confidence/resolution", "clash/Ramachandran/missing-residue metrics"),
    "virology-evolution": ("isolate/sample", "collection date", "lineage", "mutation and geography metadata"),
    "synthetic-biology": ("circuit/construct", "part strengths", "output", "burden and leakiness"),
    "sequence-engineering": ("sequence or guide/peptide/protein sequence",),
    "multiomics": ("sample metadata plus numeric features",),
    "model-assurance": ("y_true", "prediction/y_score", "optional subgroup"),
    "trial-design": ("subject/sample", "arm/group", "outcome"),
    "surveillance": ("sample/isolate", "taxon/pathogen/feature", "abundance or call"),
    "job-orchestration": ("job ID", "status", "heartbeat/retry/checkpoint metadata"),
    "collaboration-review": ("record/version", "reviewer", "decision", "timestamp"),
    "workspace-lineage": ("asset ID", "project/version", "SHA-256", "parent asset"),
    "data-lakehouse": ("asset/path", "SHA-256", "schema/access/retention metadata"),
    "evidence-citation": ("claim ID", "source ID", "exact-support/retraction/conflict fields"),
    "offline-copilot": ("prompt/answer", "citations", "grounding and action-block fields"),
    "plugin-security": ("plugin/publisher", "signature", "permissions", "isolation and scan status"),
    "provenance-ledger": ("sequence", "previous hash", "event hash", "payload"),
    "reference-lifecycle": ("asset/version", "SHA-256", "licence", "compatibility/status"),
    "store-release": ("target", "signing", "package hash", "privacy/version validation"),
    "report-governance": ("section", "source/method traceability", "version/reviewer approval"),
    "file-inspection": ("filename", "extension/magic type", "schema/corruption/sensitivity flags"),
    "workflow-orchestration": ("node", "dependency", "input/output types", "checkpoint/retry state"),
    "document-intelligence": ("document/page", "confidence", "review and citation traceability"),
    "platform-governance": ("records plus provenance/status metadata",),
    "general-scientific": ("tabular scientific records",),
}

_FAMILY_OUTPUTS: dict[str, tuple[str, ...]] = {
    "flow-cytometry": ("channel QC", "time-drift audit", "transformation summary"),
    "mass-spectrometry": ("blank/QC filters", "drift audit", "feature statistics"),
    "glycomics": ("target-decoy FDR", "site-localization audit", "glycan evidence table"),
    "proteogenomics": ("target-decoy FDR", "variant provenance", "tumour/HLA evidence audit"),
    "bioimaging": ("image-level summaries", "replication audit", "ground-truth metrics"),
    "pathology-ai": ("patient-safe image summaries", "confusion matrix", "leakage audit"),
    "spatial": ("coordinate QC", "neighborhood summaries", "Moran-style autocorrelation"),
    "genomic-variant": ("variant QC", "call rate/MAF", "domain-specific evidence gates"),
    "clinical-survival": ("Kaplan-Meier table", "log-rank test", "event-rate summary"),
    "pharmacovigilance": ("PRR", "ROR with confidence interval", "signal table"),
    "privacy": ("k-anonymity", "l-diversity", "uniqueness risk"),
    "bioprocess": ("control limits", "drift flags", "batch reconciliation"),
    "federated-ai": ("weighted round metrics", "site drift", "participation audit"),
    "structural-chemistry": ("molecular descriptors", "pose/score QC", "candidate ranking"),
    "causal-inference": ("Wald estimates", "IVW estimate", "heterogeneity audit"),
    "knowledge-network": ("degree table", "components", "evidence coverage"),
    "crispr-safety": ("guide QC", "off-target evidence audit", "variant-overlap review"),
    "antibody-engineering": ("sequence validity", "liability motifs", "developability screen"),
    "vaccine-design": ("binding evidence", "safety screen", "candidate epitope table"),
    "long-read": ("N50/length summary", "quality audit", "coverage evidence"),
    "isoform-analysis": ("isoform support", "full-length evidence", "novelty audit"),
    "single-cell": ("cell QC", "robust embedding", "replicate/batch metadata audit"),
    "epigenomics": ("peak-coordinate QC", "FDR audit", "replicate reproducibility"),
    "amr-analysis": ("AMR prevalence", "genotype-phenotype concordance", "database provenance"),
    "gene-therapy": ("payload/sequence QC", "immunity/integration evidence gates", "vector candidate table"),
    "cell-therapy": ("off-tumour review", "functional/exhaustion evidence", "construct candidate table"),
    "protein-design": ("sequence liability QC", "confidence/novelty review", "experimental evidence audit"),
    "enzyme-design": ("reaction feasibility", "flux/kinetic audit", "enzyme candidate table"),
    "structural-protein": ("structure validation", "geometry/confidence audit", "missing-residue review"),
    "virology-evolution": ("lineage summary", "temporal/geographic evidence audit", "viral evidence table"),
    "synthetic-biology": ("circuit evidence", "part-output relationships", "burden/leakiness audit"),
    "sequence-engineering": ("sequence validity", "composition/liability screen", "deduplication"),
    "multiomics": ("missingness", "robust PCA", "batch/group signal diagnostics"),
    "model-assurance": ("performance", "calibration", "subgroup/OOD checks"),
    "trial-design": ("arm balance", "effect estimate", "power/readiness indicators"),
    "surveillance": ("sample/taxon QC", "prevalence", "contamination/outlier audit"),
    "job-orchestration": ("job reliability audit", "stale worker detection", "retry/checkpoint metrics"),
    "collaboration-review": ("review governance", "version/identity coverage", "conflict-resolution audit"),
    "workspace-lineage": ("content identity", "lineage edge validation", "snapshot locking"),
    "data-lakehouse": ("metadata governance", "access/retention coverage", "index readiness"),
    "evidence-citation": ("claim-source audit", "retraction/conflict screen", "exact-support coverage"),
    "offline-copilot": ("grounding audit", "citation coverage", "clinical-action blocking"),
    "plugin-security": ("signature/publisher audit", "permission review", "environment isolation"),
    "provenance-ledger": ("hash-chain verification", "sequence integrity", "tamper-evidence summary"),
    "reference-lifecycle": ("checksum/licence audit", "compatibility validation", "activation/rollback readiness"),
    "store-release": ("target readiness", "signing/privacy/version gates", "external action list"),
    "report-governance": ("claim/method completeness", "version locking", "review approval"),
    "file-inspection": ("file safety audit", "extension/magic consistency", "schema/sensitivity review"),
    "workflow-orchestration": ("DAG integrity", "type/checkpoint audit", "execution readiness"),
    "document-intelligence": ("extraction confidence", "page/source traceability", "human-review coverage"),
    "platform-governance": ("schema completeness", "provenance coverage", "status consistency"),
    "general-scientific": ("schema QC", "robust summaries", "outlier audit"),
}


