from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from biointel.major_module_standard_v188.catalog import PROFILES as STEP188_PROFILES


@dataclass(frozen=True)
class PlatformProfile:
    module_key: str
    title: str
    page: str
    source_step: int
    module_class: str
    category: str
    recommended_engines: tuple[str, ...]
    recommended_references: tuple[str, ...]
    category_capabilities: tuple[str, ...]
    boundary: str


UNIVERSAL_CAPABILITIES: tuple[str, ...] = (
    "real_engine_adapter_and_version_detection",
    "unified_project_and_sample_registry",
    "smart_input_schema_and_file_type_assistant",
    "preflight_ready_warning_blocked_decision",
    "structured_error_diagnosis_and_support_bundle",
    "durable_background_jobs_with_retry_and_checkpoint",
    "result_and_run_comparison",
    "scientific_confidence_uncertainty_and_abstention",
    "tamper_evident_provenance_hash_chain",
    "reproducible_pdf_docx_html_csv_json_reports",
    "cross_module_asset_and_workflow_handoff",
    "runtime_observability_metrics_and_alerts",
    "role_based_review_approval_and_release_states",
    "interactive_visual_and_drilldown_contracts",
    "guided_beginner_and_expert_modes",
    "reference_database_checksum_licence_and_rollback",
    "security_permissions_secret_redaction_and_audit",
    "accessibility_keyboard_labels_and_help",
    "offline_operation_and_dependency_fallback",
    "backup_restore_archive_and_portable_project_bundle",
)

CATEGORY_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "genomics": (
        "reference_build_detection_and_liftover", "vcf_normalisation_and_decomposition",
        "coverage_callability_contamination_relatedness", "truth_set_precision_recall_f1",
        "population_frequency_and_consequence_ranking", "cnv_sv_phasing_mosaicism_support",
        "pedigree_and_family_analysis", "genome_browser_and_variant_review_board",
        "database_update_reanalysis", "evidence_conflict_resolution",
    ),
    "single_cell_multiomics": (
        "anndata_seurat_compatible_import", "cell_and_sample_qc", "doublet_and_ambient_rna_detection",
        "batch_correction_comparison", "cell_type_annotation_confidence", "atlas_mapping",
        "differential_expression_and_pathways", "trajectory_and_cell_communication",
        "patient_level_split_and_pseudobulk", "cluster_stability_and_marker_validation",
    ),
    "microbiome": (
        "read_qc_and_host_removal", "negative_control_and_blank_modelling", "contamination_detection",
        "taxonomic_and_strain_confidence", "functional_amr_and_virulence_profiles",
        "alpha_beta_diversity_and_clr", "differential_abundance", "mock_community_benchmark",
        "phylogenetic_and_outbreak_mapping", "ambiguous_call_abstention",
    ),
    "protein_molecular": (
        "fasta_pdb_mmcif_sdf_validation", "structure_and_missing_atom_preparation",
        "binding_site_and_chain_selection", "mutation_scanning_and_structure_confidence",
        "docking_redocking_pose_rmsd", "clash_and_consensus_scoring", "selectivity_and_developability",
        "novelty_restricted_motif_and_toxicity_checks", "interactive_3d_viewer", "design_history_and_rollback",
    ),
    "imaging_spatial": (
        "wsi_microscopy_tiled_processing", "focus_blur_and_artefact_qc", "stain_normalisation_and_scanner_drift",
        "segmentation_and_annotation_editor", "dice_iou_object_f1", "spatial_registration_and_overlays",
        "neighbourhood_and_spatial_autocorrelation", "ood_image_detection", "reviewer_agreement",
        "mask_annotation_and_slide_report_export",
    ),
    "ai_ml": (
        "model_card_and_intended_use", "training_data_and_licence_summary", "weight_checksum_and_registry",
        "split_and_leakage_verification", "calibration_uncertainty_and_abstention", "ood_and_adversarial_tests",
        "fairness_and_subgroup_metrics", "explainability", "canary_drift_and_monitoring",
        "deployment_promotion_rollback_and_retirement",
    ),
    "clinical_pharma": (
        "intended_use_endpoint_and_cohort_lock", "patient_level_temporal_external_site_validation",
        "sensitivity_specificity_ppv_npv", "calibration_survival_and_decision_curve",
        "subgroup_safety_and_missing_data_sensitivity", "protocol_deviation_and_adverse_event_tracking",
        "prospective_evidence_intake", "expert_signoff", "research_vs_clinical_use_boundary",
        "controlled_release_and_post_release_monitoring",
    ),
    "lab_bioprocess": (
        "instrument_file_and_calibration_validation", "compensation_transformation_and_gating",
        "plate_map_and_replicate_concordance", "protocol_reagent_lot_and_sample_custody",
        "time_series_process_control", "alarm_thresholds", "yield_and_scaleup_comparison",
        "experiment_approval_execution_completion", "instrument_drift", "maintenance_and_audit_history",
    ),
    "knowledge_documents": (
        "document_structure_table_and_figure_extraction", "citation_resolution_and_source_snapshot",
        "duplicate_and_retraction_detection", "claim_to_source_mapping", "evidence_grading_and_conflicts",
        "ontology_mapping_and_entity_resolution", "knowledge_graph_provenance", "literature_watchlist",
        "review_queue", "unsupported_claim_blocking",
    ),
    "platform_workflow": (
        "typed_ports_and_dag_validation", "cycle_detection_and_conditional_branches",
        "scatter_gather_and_resource_scheduling", "workflow_versioning_and_nested_workflows",
        "plugin_signature_permission_and_sandbox", "dependency_isolation_and_compatibility",
        "concurrent_user_conflict_handling", "backup_restore_and_rollback", "offline_plugin_install",
        "portable_project_and_template_marketplace",
    ),
    "general_scientific": (
        "domain_specific_input_contract", "sample_and_cohort_qc", "native_analysis_adapter",
        "gold_standard_benchmark", "effect_size_confidence_and_multiple_testing",
        "subgroup_and_batch_effect_analysis", "interactive_results", "evidence_linked_interpretation",
        "publication_quality_export", "independent_validation_gate",
    ),
}

CATEGORY_ENGINES: dict[str, tuple[str, ...]] = {
    "genomics": ("bcftools", "samtools", "plink2", "vep", "gatk"),
    "single_cell_multiomics": ("scanpy", "cellranger", "star", "salmon"),
    "microbiome": ("kraken2", "bracken", "humann", "metaphlan"),
    "protein_molecular": ("vina", "colabfold", "foldseek", "openbabel"),
    "imaging_spatial": ("openslide", "cellpose", "stardist", "qupath"),
    "ai_ml": ("onnxruntime", "pytorch", "transformers"),
    "clinical_pharma": ("r", "python", "lifelines"),
    "lab_bioprocess": ("python", "r", "opencv"),
    "knowledge_documents": ("pypdf", "tesseract", "pandoc"),
    "platform_workflow": ("python", "docker", "git"),
    "general_scientific": ("python", "r"),
}

CATEGORY_REFERENCES: dict[str, tuple[str, ...]] = {
    "genomics": ("reference_genome", "gene_annotation", "population_frequency", "clinical_variant_evidence"),
    "single_cell_multiomics": ("cell_atlas", "gene_annotation", "pathway_ontology"),
    "microbiome": ("taxonomy_database", "microbial_genomes", "functional_pathways", "amr_catalogue"),
    "protein_molecular": ("protein_sequences", "protein_structures", "compound_library", "binding_benchmarks"),
    "imaging_spatial": ("annotation_ontology", "scanner_profile", "stain_reference", "external_image_cohort"),
    "ai_ml": ("model_registry", "benchmark_dataset", "ood_dataset"),
    "clinical_pharma": ("clinical_terminology", "drug_dictionary", "external_validation_cohort"),
    "lab_bioprocess": ("instrument_profile", "protocol_library", "control_limits"),
    "knowledge_documents": ("ontology_release", "citation_index", "retraction_feed"),
    "platform_workflow": ("plugin_registry", "compatibility_matrix", "security_advisory_feed"),
    "general_scientific": ("domain_reference_pack", "benchmark_dataset"),
}


def infer_category(title: str, module_key: str, module_class: str) -> str:
    text = f"{title} {module_key}".lower()
    if module_class == "platform-core":
        if any(x in text for x in ("document", "evidence", "knowledge graph", "citation")):
            return "knowledge_documents"
        return "platform_workflow"
    if any(x in text for x in ("single-cell", "single cell", "multi-omics", "multiomics", "cell atlas", "trajectory")):
        return "single_cell_multiomics"
    if any(x in text for x in ("microbiome", "metagenom", "pathogen", "amr", "virolog", "one health")):
        return "microbiome"
    if any(x in text for x in ("protein", "antibody", "docking", "ligand", "enzyme", "structural bio", "vaccine")):
        return "protein_molecular"
    if any(x in text for x in ("image", "imaging", "pathology", "spatial", "microscopy", "organoid", "phenotypic")):
        return "imaging_spatial"
    if any(x in text for x in ("clinical", "pharma", "trial", "survival", "pharmacovigilance", "cohort")):
        return "clinical_pharma"
    if any(x in text for x in ("flow cytometry", "bioprocess", "fermentation", "laboratory", "synthetic biology", "gene therapy", "cell therapy")):
        return "lab_bioprocess"
    if any(x in text for x in ("model", "federated", "explainable", "copilot", "foundation", "synthetic data", "privacy")):
        return "ai_ml"
    if any(x in text for x in ("genom", "variant", "gwas", "prs", "epigen", "long-read", "pangenome", "rna isoform", "pharmacogen")):
        return "genomics"
    if any(x in text for x in ("document", "evidence", "knowledge", "citation")):
        return "knowledge_documents"
    return "general_scientific"


PROFILES: dict[str, PlatformProfile] = {}
for key, profile in STEP188_PROFILES.items():
    category = infer_category(profile.title, key, profile.module_class)
    PROFILES[key] = PlatformProfile(
        module_key=key,
        title=profile.title,
        page=profile.page,
        source_step=profile.source_step,
        module_class=profile.module_class,
        category=category,
        recommended_engines=CATEGORY_ENGINES[category],
        recommended_references=CATEGORY_REFERENCES[category],
        category_capabilities=CATEGORY_CAPABILITIES[category],
        boundary=profile.boundary,
    )

TARGET_MODULES: tuple[str, ...] = tuple(PROFILES)
PAGE_TO_MODULES: dict[str, tuple[str, ...]] = {}
for key, profile in PROFILES.items():
    name = Path(profile.page).name
    PAGE_TO_MODULES[name] = PAGE_TO_MODULES.get(name, tuple()) + (key,)

PLATFORM_DIMENSIONS: tuple[str, ...] = UNIVERSAL_CAPABILITIES + (
    "category_specific_capability_contracts",
    "engine_and_reference_readiness_matrix",
    "preflight_resource_and_permission_checks",
    "project_sample_asset_lineage",
    "job_state_machine_and_recovery_drill",
    "review_state_machine_and_role_controls",
    "monitoring_slo_alert_and_owner_contract",
    "structured_diagnostics_and_redacted_support_export",
    "report_format_generation_and_regeneration_hash",
    "controlled_release_fail_closed_without_external_evidence",
)

assert len(PROFILES) == 80
assert len(PAGE_TO_MODULES) == 79
assert len(UNIVERSAL_CAPABILITIES) == 20
assert len(PLATFORM_DIMENSIONS) == 30

__all__ = [
    "PlatformProfile", "PROFILES", "TARGET_MODULES", "PAGE_TO_MODULES",
    "UNIVERSAL_CAPABILITIES", "CATEGORY_CAPABILITIES", "PLATFORM_DIMENSIONS",
]
