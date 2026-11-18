from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from biointel.universal_platform_v189.catalog import PROFILES as STEP189_PROFILES


@dataclass(frozen=True)
class ExecutionProfile:
    module_key: str
    title: str
    page: str
    category: str
    recommended_engines: tuple[str, ...]
    recommended_references: tuple[str, ...]
    standard_formats: tuple[str, ...]
    native_viewers: tuple[str, ...]
    advanced_capabilities: tuple[str, ...]


CATEGORY_FORMATS: dict[str, tuple[str, ...]] = {
    "genomics": ("FASTA", "FASTQ", "VCF", "GFF3", "BED", "GA4GH-compatible capability JSON"),
    "single_cell_multiomics": ("CSV/TSV matrix", "AnnData-compatible bridge", "H5AD intake contract", "MTX", "cell metadata"),
    "microbiome": ("FASTQ", "BIOM-compatible table", "TSV abundance", "Newick", "sample metadata"),
    "protein_molecular": ("FASTA", "PDB", "mmCIF", "SDF", "SMILES", "design manifest JSON"),
    "imaging_spatial": ("OME-NGFF metadata bridge", "OME-TIFF intake", "WSI intake", "mask CSV", "spatial coordinates"),
    "ai_ml": ("model card JSON", "ONNX intake contract", "predictions CSV", "benchmark JSON", "lineage manifest"),
    "clinical_pharma": ("cohort CSV", "CDISC-style mapping contract", "FHIR-compatible resource map", "endpoint manifest"),
    "lab_bioprocess": ("instrument CSV", "FCS intake contract", "plate map", "protocol JSON", "time-series CSV"),
    "knowledge_documents": ("PDF/DOCX intake", "JSON-LD", "W3C PROV-compatible JSON-LD", "citation manifest"),
    "platform_workflow": ("workflow DAG JSON", "CWL/Nextflow compatibility manifest", "W3C PROV-compatible JSON-LD", "plugin manifest"),
    "general_scientific": ("CSV/TSV", "study manifest JSON", "W3C PROV-compatible JSON-LD", "benchmark JSON"),
}

CATEGORY_VIEWERS: dict[str, tuple[str, ...]] = {
    "genomics": ("genome track", "variant table", "truth-set confusion dashboard"),
    "single_cell_multiomics": ("embedding projection", "feature heatmap", "cohort comparison"),
    "microbiome": ("taxonomic composition", "strain heatmap", "phylogeny/outbreak map contract"),
    "protein_molecular": ("structure projection", "sequence feature map", "pose/design comparison"),
    "imaging_spatial": ("multiscale tile overview", "segmentation overlay", "spatial heatmap"),
    "ai_ml": ("calibration", "subgroup performance", "drift/OOD dashboard"),
    "clinical_pharma": ("endpoint dashboard", "calibration/decision curve", "site/subgroup comparison"),
    "lab_bioprocess": ("control chart", "plate/gate view", "batch trajectory"),
    "knowledge_documents": ("claim-source graph", "evidence conflict map", "document extraction map"),
    "platform_workflow": ("workflow DAG", "job timeline", "dependency/compatibility matrix"),
    "general_scientific": ("effect-size dashboard", "cohort comparison", "quality-control panel"),
}

CATEGORY_ADVANCED: dict[str, tuple[str, ...]] = {
    "genomics": (
        "reference build detection and liftover contract", "VCF normalisation and decomposition", "sample contamination and relatedness",
        "coverage and callability", "truth-set precision recall F1", "population/subgroup stratification", "CNV SV phasing and mosaicism",
        "pedigree and segregation analysis", "genome browser evidence", "database update reanalysis impact",
    ),
    "single_cell_multiomics": (
        "cell and sample QC", "doublet and ambient signal detection", "batch correction comparison", "cell-type annotation confidence",
        "reference atlas mapping", "pseudobulk analysis", "trajectory and communication", "cluster stability", "patient-level split enforcement",
        "multimodal feature provenance",
    ),
    "microbiome": (
        "read QC and host-removal contract", "negative controls and extraction blanks", "contamination modelling", "taxonomy and strain confidence",
        "functional AMR virulence profiles", "alpha beta diversity and CLR", "mock-community truth benchmark", "ambiguous-call abstention",
        "database-version comparison", "cross-site/outbreak linkage",
    ),
    "protein_molecular": (
        "sequence and structure validation", "missing residue and atom preparation", "binding-site selection", "mutation scanning",
        "redocking and pose RMSD", "steric clash and consensus scoring", "selectivity and developability", "novelty/restricted motif checks",
        "multi-objective Pareto ranking", "design history and rollback",
    ),
    "imaging_spatial": (
        "tiled and memory-safe processing", "focus blur and artefact QC", "stain/scanner/site drift", "segmentation and annotation",
        "Dice IoU object-F1", "coordinate registration", "neighbourhood/spatial autocorrelation", "OOD image detection",
        "reviewer agreement", "mask and annotation export",
    ),
    "ai_ml": (
        "model card and intended use", "training data and licence summary", "weight checksum and lineage", "leakage verification",
        "calibration uncertainty and abstention", "OOD/adversarial/prompt-injection tests", "fairness and subgroup metrics",
        "explanation stability", "canary and drift monitoring", "promotion rollback and retirement",
    ),
    "clinical_pharma": (
        "intended use endpoint and cohort lock", "patient-level temporal/site validation", "sensitivity specificity PPV NPV",
        "calibration survival and decision curve", "subgroup safety", "missing-data sensitivity", "protocol deviation tracking",
        "prospective evidence intake", "expert sign-off", "controlled release and post-release monitoring",
    ),
    "lab_bioprocess": (
        "instrument and calibration validation", "compensation/transformation/gating contract", "plate map and replicate concordance",
        "protocol reagent lot and sample custody", "process control charts", "alarm thresholds", "yield and scale-up comparison",
        "experiment state machine", "instrument/process drift", "maintenance and audit history",
    ),
    "knowledge_documents": (
        "layout/table/figure extraction", "citation resolution and source snapshot", "duplicate and retraction detection",
        "claim-to-source mapping", "evidence grading and conflicts", "ontology/entity resolution", "knowledge graph provenance",
        "literature watchlist", "review queue", "unsupported claim blocking",
    ),
    "platform_workflow": (
        "typed ports and DAG validation", "cycle detection and conditional branches", "scatter/gather and scheduling",
        "workflow versioning and subworkflows", "plugin signature permission and sandbox", "dependency isolation",
        "concurrent conflict handling", "backup restore and rollback", "offline plugin installation", "portable workflow marketplace bundle",
    ),
    "general_scientific": (
        "domain-specific input contract", "sample/cohort QC", "native deterministic analysis", "gold-standard demo benchmark",
        "effect size confidence and multiple testing", "subgroup/batch analysis", "interactive results", "evidence-linked interpretation",
        "publication-quality export", "independent validation gate",
    ),
}

# High-value module-specific depth. Category capabilities still apply to every module.
MODULE_EXTRAS: dict[str, tuple[str, ...]] = {
    "amr_surveillance": ("phenotype-genotype concordance", "plasmid and mobile-element context", "resistance ontology mapping", "outbreak clustering"),
    "cancer_genomics_core": ("tumour purity/ploidy", "clonality", "mutational signatures", "longitudinal tumour evolution"),
    "rare_variant_family": ("pedigree builder", "de-novo/recessive/X-linked filters", "phenotype matching", "variant review board"),
    "population_gwas": ("ancestry QC", "LD pruning", "fine mapping", "PRS portability testing"),
    "genome_editing_safety": ("mismatch and bulge modelling", "base/prime editing", "PAM compatibility", "multiplex guide interactions"),
    "long_read_core": ("HiFi and ONT presets", "polishing comparison", "misassembly detection", "telomere/centromere completeness"),
    "long_read_epigenome": ("modified-base calling contract", "haplotype-specific methylation", "DMR detection", "coverage confidence"),
    "structural_variant_repeat": ("multi-caller consensus", "breakpoint confidence", "repeat sizing", "mosaic expansion"),
    "pharmacogenomics": ("star-allele calling", "copy-number-aware diplotypes", "phenotype translation", "guideline evidence"),
    "proteogenomics_neoantigen": ("personalised proteome", "peptide-spectrum evidence", "HLA ensemble", "clonality/expression support"),
    "pangenome_core": ("GFA graph import", "graph alignment contract", "sample haplotype paths", "graph-linear coordinate bridge"),
    "pathogen_outbreak_core": ("time-resolved phylogeny", "sample-location map", "transmission probability", "recombination checks"),
    "virology_evolution": ("quasispecies", "minority variants", "recombination", "selection pressure"),
    "single_cell_core": ("H5AD import/export", "doublet detection", "ambient correction", "pseudobulk differential expression"),
    "single_cell_trajectory": ("trajectory method comparison", "root sensitivity", "branch confidence", "ligand-receptor consensus"),
    "cell_atlas_mapping": ("multiple atlases", "ontology-normalised labels", "unknown-cell abstention", "atlas version comparison"),
    "multiomics_harmonization": ("sample identity reconciliation", "modality missingness", "latent-factor stability", "feature provenance"),
    "multiomics_biomarker_discovery": ("nested cross-validation", "feature stability", "panel-cost optimisation", "assay transferability"),
    "longitudinal_multiomics": ("irregular time modelling", "subject trajectories", "event alignment", "missing-visit handling"),
    "metabolomics_lipidomics": ("internal-standard QC", "batch drift correction", "adduct/isotope grouping", "identification confidence"),
    "glycomics_glycoproteomics": ("glycan composition validation", "site occupancy", "glycoform comparison", "fragmentation evidence"),
    "docking_dynamics": ("receptor ensembles", "consensus docking", "MD stability metrics", "free-energy estimation contract"),
    "protein_language_design": ("multiple model backends", "constrained generation", "novelty search", "design diversity"),
    "protein_ligand_codesign": ("joint optimisation", "selectivity prediction", "synthesis feasibility", "active-learning loop"),
    "antibody_biologics": ("CDR annotation", "humanisation", "aggregation/immunogenicity", "epitope-paratope mapping"),
    "enzyme_pathway_design": ("active-site mutation ranking", "kinetic estimates", "flux simulation", "cofactor balancing"),
    "immunoinformatics_vaccine": ("population HLA coverage", "epitope conservancy", "processing prediction", "escape-risk analysis"),
    "gene_therapy_vector": ("cargo-size validation", "tropism", "promoter selection", "integration risk"),
    "cell_therapy_cart": ("CAR architecture comparison", "off-tumour risk", "exhaustion markers", "cytokine-risk modelling"),
    "synthetic_biology_circuit": ("circuit simulation", "promoter/RBS libraries", "burden estimation", "stochastic failure modes"),
    "bioimage_microscopy": ("OME-NGFF bridge", "segmentation ensemble", "active learning", "uncertainty overlays"),
    "organoid_3d": ("3D segmentation", "lineage tracking", "morphology embeddings", "treatment response"),
    "digital_pathology_foundation": ("WSI embeddings", "tile retrieval", "weak supervision", "domain adaptation"),
    "phenotypic_screening": ("plate-map editor", "Z-prime and edge effects", "dose response", "hit confirmation"),
    "spatial_omics_pathology": ("image-expression registration", "tissue region annotation", "spatial neighbourhoods", "clinical endpoint linkage"),
    "clinical_biomarker_survival": ("competing risks", "time-dependent ROC", "calibration over time", "decision curves"),
    "clinical_trial_biomarker": ("protocol endpoint lock", "arm stratification", "interim analysis", "cut-point validation"),
    "synthetic_cohort_trial": ("covariate balancing", "event simulation", "dropout/adherence", "scenario sensitivity"),
    "pharmacovigilance": ("MedDRA mapping contract", "disproportionality", "duplicate-case detection", "temporal signals"),
    "causal_inference_perturbation": ("DAG editor contract", "positivity checks", "doubly robust estimation", "unmeasured-confounding sensitivity"),
    "flow_cytometry": ("compensation QC", "gating templates", "automated/manual comparison", "instrument drift"),
    "bioprocess_fermentation": ("soft sensors", "batch trajectories", "yield prediction", "scale-up modelling"),
    "autonomous_laboratory_planner": ("resource scheduling", "reagent constraints", "safety blocking", "result-driven replanning"),
    "biomedical_foundation_model_hub": ("compatibility matrix", "quantisation profiles", "benchmark arena", "licence restrictions"),
    "federated_biomedical_ai": ("secure aggregation", "site dropout recovery", "poisoning detection", "privacy accounting"),
    "explainable_ai_assurance": ("explanation stability", "counterfactuals", "subgroup explanations", "reviewer usability"),
    "model_registry_ml_lifecycle": ("staging promotion", "canary/shadow evaluation", "deprecation", "retirement"),
    "offline_copilot_core": ("grounded retrieval", "citation verification", "unsupported-claim refusal", "local index management"),
    "offline_scientific_copilot_v2": ("agent permissions", "tool-call audit", "memory isolation", "prompt-injection defence"),
    "synthetic_data_privacy": ("membership-inference risk", "attribute disclosure", "utility/privacy frontier", "privacy budget"),
    "evidence_citation_engine": ("identifier resolution", "retraction checks", "contradictory evidence", "citation-location verification"),
    "knowledge_graph_core": ("ontology versioning", "entity confidence", "temporal facts", "reasoning explanations"),
    "provenance_ledger_v2": ("W3C PROV export", "lineage visualisation", "cryptographic signatures", "provenance queries"),
    "reference_lifecycle_v2": ("delta updates", "mirrors/resume", "dependency graph", "retirement warnings"),
    "background_job_engine": ("worker pools", "resource quotas", "dead-letter queue", "chaos tests"),
    "background_jobs_core": ("job dependencies", "resumable artefacts", "stale-worker recovery", "priority fairness"),
    "benchmark_validation_v2": ("immutable benchmark registry", "dataset licence records", "uncertainty-aware leaderboard", "cross-machine reproducibility"),
    "cross_module_workspace": ("project branches", "merge/conflict handling", "dependency graph", "workspace snapshots"),
    "data_lakehouse_v2": ("columnar partitioning", "semantic metadata search", "lineage-aware query", "retention tiers"),
    "plugin_marketplace_core": ("signed packages", "static scan", "isolated environments", "permission prompts"),
    "plugin_marketplace_v2": ("compatibility certification", "publisher trust", "rollback", "offline install"),
    "workflow_builder_core": ("scatter/gather", "conditional branches", "subworkflows", "visual debugging"),
    "workflow_builder_v2": ("loops", "typed schemas", "resource scheduling", "portable workflow export"),
    "store_readiness_core": ("signed installer contract", "repair mode", "clean uninstall", "update rollback"),
    "document_intelligence_core": ("layout-aware extraction", "table/figure localisation", "handwriting confidence", "source localisation"),
    "unified_report_builder": ("dynamic sections", "figure provenance", "review comments", "regulatory-style templates"),
    "collaboration_review_v2": ("inline comments", "issue resolution", "blinded review", "electronic signatures"),
    "universal_file_inspector": ("magic-byte detection", "nested archive scan", "PHI/secret detection", "repair suggestions"),
}

EXECUTION_DIMENSIONS: tuple[str, ...] = (
    "external_engine_detection", "native_offline_execution", "safe_command_plan", "engine_version_and_licence_matrix",
    "standard_input_format_bridge", "standard_output_format_bridge", "GA4GH_or_domain_capability_descriptor",
    "W3C_PROV_compatible_export", "truth_set_benchmark", "negative_control_benchmark", "positive_control_benchmark",
    "precision_recall_or_domain_metric", "calibration_or_confidence_metric", "uncertainty_and_abstention",
    "subgroup_or_batch_robustness", "OOD_or_corrupt_input_handling", "large_file_chunk_streaming",
    "memory_and_runtime_profile", "cache_key_and_repeatability", "native_interactive_viewer", "viewer_export",
    "reference_intake_manifest", "reference_checksum_and_licence_gate", "reference_update_impact_analysis",
    "model_or_engine_update_impact_analysis", "cross_tool_comparison", "parameter_preset_comparison",
    "beginner_and_expert_execution_modes", "result_handoff_contract", "full_provenance_manifest",
    "multi_format_report_linkage", "error_catalogue_and_recovery", "security_and_path_safety", "accessibility_contract",
    "module_specific_advanced_capabilities", "category_specific_advanced_capabilities", "production_readiness_matrix",
    "external_evidence_intake", "controlled_release_fail_closed", "automated_regression_qualification",
)

PROFILES: dict[str, ExecutionProfile] = {}
for key, p in STEP189_PROFILES.items():
    extras = MODULE_EXTRAS.get(key, ())
    PROFILES[key] = ExecutionProfile(
        module_key=key,
        title=p.title,
        page=p.page,
        category=p.category,
        recommended_engines=p.recommended_engines,
        recommended_references=p.recommended_references,
        standard_formats=CATEGORY_FORMATS[p.category],
        native_viewers=CATEGORY_VIEWERS[p.category],
        advanced_capabilities=tuple(dict.fromkeys((*CATEGORY_ADVANCED[p.category], *extras))),
    )

TARGET_MODULES: tuple[str, ...] = tuple(PROFILES)
PAGE_TO_MODULES: dict[str, tuple[str, ...]] = {}
for key, profile in PROFILES.items():
    PAGE_TO_MODULES.setdefault(profile.page.split("/")[-1], tuple())
    PAGE_TO_MODULES[profile.page.split("/")[-1]] = (*PAGE_TO_MODULES[profile.page.split("/")[-1]], key)

__all__ = [
    "ExecutionProfile", "CATEGORY_FORMATS", "CATEGORY_VIEWERS", "CATEGORY_ADVANCED", "MODULE_EXTRAS",
    "EXECUTION_DIMENSIONS", "PROFILES", "TARGET_MODULES", "PAGE_TO_MODULES",
]
