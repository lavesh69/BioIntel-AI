from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EvidenceRequirement:
    key: str
    label: str
    category: str
    severity: str
    aliases: tuple[str, ...]
    description: str
    external: bool = False


@dataclass(frozen=True)
class EvidenceReadiness:
    module_key: str
    score: float
    grade: str
    data_quality_score: float
    design_score: float
    provenance_score: float
    validation_score: float
    reproducibility_score: float
    release_ready: bool
    checks: pd.DataFrame
    requirements: pd.DataFrame
    blockers: tuple[str, ...]
    manifest: dict[str, Any]


_STATUS_FACTOR = {"pass": 1.0, "review": 0.5, "fail": 0.0}
_CATEGORY_WEIGHTS = {
    "data_quality": 30.0,
    "study_design": 20.0,
    "provenance": 20.0,
    "validation": 20.0,
    "reproducibility": 10.0,
}


def _req(
    key: str,
    label: str,
    category: str,
    severity: str,
    aliases: Iterable[str],
    description: str,
    *,
    external: bool = False,
) -> EvidenceRequirement:
    return EvidenceRequirement(
        key=key,
        label=label,
        category=category,
        severity=severity,
        aliases=tuple(str(alias).lower() for alias in aliases),
        description=description,
        external=external,
    )


COMMON_REQUIREMENTS: tuple[EvidenceRequirement, ...] = (
    _req(
        "input_identity",
        "Content identity / checksum",
        "reproducibility",
        "major",
        ("sha256", "input_sha256", "checksum", "file_hash", "content_hash"),
        "Record a content hash for every primary input used by the analysis.",
    ),
    _req(
        "method_version",
        "Software, model or pipeline version",
        "provenance",
        "major",
        ("engine_version", "tool_version", "software_version", "model_version", "pipeline_version", "workflow_version"),
        "Pin the exact analytical software/model version and material parameters.",
    ),
    _req(
        "reference_release",
        "Reference/database release",
        "provenance",
        "major",
        ("reference_release", "reference_version", "database_release", "database_version", "annotation_release", "atlas_release"),
        "Pin reference data, annotation, atlas or database releases used for interpretation.",
    ),
    _req(
        "independent_validation",
        "Independent or orthogonal validation",
        "validation",
        "critical",
        ("independent_validation", "external_validation", "orthogonal_validation", "validation_reference", "confirmation_assay", "independent_cohort"),
        "Attach independently generated evidence appropriate to the intended scientific claim.",
        external=True,
    ),
    _req(
        "reviewer_approval",
        "Qualified scientific review",
        "validation",
        "major",
        ("reviewer", "reviewer_id", "review_decision", "scientific_approval", "pathologist_review", "clinical_review"),
        "Record an accountable reviewer and decision for high-impact findings.",
        external=True,
    ),
)


CUSTOM_REQUIREMENTS: dict[str, tuple[EvidenceRequirement, ...]] = {
    "flow_cytometry": (
        _req("instrument_qc", "Instrument QC record", "provenance", "critical", ("instrument_qc", "cytometer_qc", "bead_qc", "instrument_id"), "Record instrument identity and same-run or policy-compliant QC evidence."),
        _req("unstained_control", "Unstained control", "study_design", "critical", ("unstained", "unstained_control", "control_type"), "Include an acquisition-matched unstained control."),
        _req("single_stain_controls", "Single-stain compensation controls", "study_design", "critical", ("single_stain", "single_stain_control", "compensation_control"), "Provide one suitable single-stain control per fluorescence detector."),
        _req("fmo_controls", "FMO controls for critical gates", "study_design", "major", ("fmo", "fmo_control", "control_type"), "Use FMO controls for gates where spillover/spread affects positivity."),
        _req("gate_review", "Independent gate review", "validation", "critical", ("gate_reviewer", "manual_gate_review", "gating_review"), "Have representative gates independently reviewed and version locked.", external=True),
    ),
    "epigenomics_chromatin": (
        _req("genome_build", "Genome build", "provenance", "critical", ("genome_build", "reference_build", "assembly", "build"), "Use one pinned genome build across intervals, alignments and annotation."),
        _req("biological_replicates", "Biological replicates", "study_design", "critical", ("replicate", "replicate_id", "biological_replicate", "sample"), "Identify independent biological replicates for each condition."),
        _req("peak_caller", "Peak caller and control provenance", "provenance", "major", ("peak_caller", "caller_version", "input_control", "control_sample"), "Record caller/version, controls and peak parameters."),
        _req("orthogonal_assay", "Orthogonal regulatory confirmation", "validation", "critical", ("orthogonal_assay", "qpcr_validation", "chip_validation", "reporter_assay"), "Confirm priority regions using an independent assay.", external=True),
    ),
    "metabolomics_lipidomics": (
        _req("pooled_qc", "Pooled-QC samples", "study_design", "critical", ("pooled_qc", "qc_sample", "sample_type", "control_type"), "Include repeated pooled-QC injections across the analytical sequence."),
        _req("blank_controls", "Blank controls", "study_design", "critical", ("blank", "blank_sample", "blank_intensity", "sample_type"), "Include extraction/process blanks and blank-aware filtering."),
        _req("ms2_evidence", "MS/MS evidence", "validation", "critical", ("ms2_score", "spectral_match", "fragment_score", "library_match", "msms_evidence"), "Retain spectrum-level MS/MS matching and library provenance."),
        _req("identification_level", "Identification confidence level", "provenance", "major", ("identification_level", "msi_level", "annotation_confidence"), "Assign a transparent metabolite-identification confidence level."),
        _req("authentic_standard", "Authentic-standard confirmation", "validation", "critical", ("authentic_standard", "retention_time_match", "standard_confirmed"), "Confirm high-priority identities with authentic standards and retention time.", external=True),
    ),
    "immunoinformatics_vaccine": (
        _req("predictor_version", "MHC predictor and allele version", "provenance", "major", ("predictor_version", "netmhcpan_version", "allele_release"), "Pin predictor, model and HLA nomenclature versions."),
        _req("population_coverage", "Population allele coverage", "study_design", "major", ("population_coverage", "allele_frequency", "population"), "Evaluate allele-frequency coverage in intended populations."),
        _req("host_similarity", "Host similarity/allergen/toxin review", "validation", "major", ("host_similarity", "allergenicity", "toxicity", "autoimmunity_risk"), "Review host similarity and relevant safety signals."),
        _req("immunogenicity_assay", "Experimental immunogenicity", "validation", "critical", ("immunogenicity_assay", "elispot", "tetramer", "functional_assay"), "Confirm shortlisted epitopes experimentally.", external=True),
    ),
    "antibody_biologics": (
        _req("chain_pairing", "Heavy/light chain pairing", "study_design", "critical", ("heavy_chain", "light_chain", "chain_pair", "pairing"), "Preserve correct heavy/light chain pairing for every variant."),
        _req("numbering_scheme", "Antibody numbering scheme", "provenance", "major", ("numbering_scheme", "anarci_version", "imgt_numbering", "cdr_definition"), "Pin numbering/CDR definition and germline reference release."),
        _req("structure_model", "Structure model and quality", "provenance", "major", ("structure_model", "model_confidence", "pdb", "mmcif"), "Record structure source/model confidence where structural reasoning is used."),
        _req("developability_assays", "Experimental developability assays", "validation", "critical", ("sec", "dls", "tm", "viscosity", "aggregation_assay", "developability_assay"), "Confirm aggregation, stability, viscosity and expression experimentally.", external=True),
    ),
    "docking_dynamics": (
        _req("target_preparation", "Target/ligand preparation provenance", "provenance", "critical", ("target_id", "receptor_preparation", "protonation", "ligand_preparation", "force_field"), "Record receptor/ligand preparation, protonation and force-field choices."),
        _req("redocking", "Redocking/pose validation", "validation", "major", ("redocking_rmsd", "redocking_validation", "pose_validation"), "Validate protocol against a known pose when feasible."),
        _req("replicate_simulation", "Replicate simulations", "study_design", "major", ("replicate", "simulation_replica", "trajectory_id"), "Use independent simulation replicas for stability claims."),
        _req("convergence", "Equilibration and convergence evidence", "validation", "major", ("equilibration", "convergence", "rmsd_plateau", "ess"), "Document equilibration and convergence diagnostics."),
        _req("affinity_assay", "Measured binding affinity", "validation", "critical", ("kd", "ki", "ic50", "binding_affinity", "experimental_affinity"), "Link computational ranking to measured affinity.", external=True),
    ),
    "pharmacogenomics": (
        _req("genome_build", "Genome build and transcript release", "provenance", "critical", ("genome_build", "reference_build", "transcript_release"), "Pin genome build and transcript/allele definition releases."),
        _req("phasing_cnv", "Phasing and copy-number evidence", "validation", "critical", ("phase", "phasing", "copy_number", "cnv", "hybrid_allele"), "Resolve phase and copy number for loci where diplotypes depend on them."),
        _req("guideline_version", "Guideline/allele-definition version", "provenance", "critical", ("guideline_version", "cpic_version", "dpwg_version", "allele_definition_version"), "Pin clinical guideline and star-allele definition releases."),
        _req("clinical_review", "Qualified clinical review", "validation", "critical", ("clinical_review", "pharmacist_review", "geneticist_review"), "Require qualified clinical governance before any treatment interpretation.", external=True),
    ),
    "spatial_omics_pathology": (
        _req("registration", "Image-coordinate registration", "validation", "critical", ("registration_transform", "registration_error", "fiducial_qc", "image_id"), "Retain transforms and registration residuals between image and molecular coordinates."),
        _req("section_replicates", "Independent sections/samples", "study_design", "critical", ("section", "section_id", "sample", "donor", "replicate"), "Use independent tissue sections and biological samples."),
        _req("atlas_release", "Reference atlas release", "provenance", "major", ("atlas_release", "reference_atlas", "cell_type_reference"), "Pin the reference atlas and mapping model."),
        _req("pathology_review", "Pathologist review", "validation", "critical", ("pathologist_review", "roi_approval", "histology_review"), "Attach accountable pathology review for relevant regions.", external=True),
    ),
    "single_cell_trajectory": (
        _req("biological_replicates", "Donor/sample replicates", "study_design", "critical", ("donor", "sample", "sample_id", "replicate", "batch"), "Identify biological replicates and use replicate-aware inference."),
        _req("root_justification", "Trajectory root/direction justification", "validation", "major", ("root_cell", "root_cluster", "root_justification", "direction_evidence"), "Document the biological rationale for root and direction."),
        _req("velocity_evidence", "RNA-velocity model evidence", "provenance", "major", ("spliced", "unspliced", "velocity_model", "scvelo_version"), "Record spliced/unspliced processing and velocity-model version."),
        _req("lr_database", "Ligand-receptor database release", "provenance", "major", ("lr_database", "ligand_receptor_release", "database_release"), "Pin the ligand-receptor knowledgebase release."),
        _req("biological_validation", "Biological lineage/communication validation", "validation", "critical", ("lineage_validation", "perturbation_validation", "communication_assay"), "Confirm major lineage or communication claims independently.", external=True),
    ),
    "bioimage_microscopy": (
        _req("pixel_calibration", "Pixel/voxel calibration", "provenance", "critical", ("pixel_size", "voxel_size", "microns_per_pixel", "calibration"), "Record spatial calibration and channel metadata."),
        _req("segmentation_version", "Segmentation model/version", "provenance", "critical", ("segmentation_model", "model_version", "checkpoint", "mask_version"), "Pin the exact segmentation model/checkpoint and parameters."),
        _req("ground_truth", "Ground-truth annotations", "validation", "critical", ("ground_truth", "manual_mask", "expert_annotation", "dice", "iou"), "Compare representative outputs against expert annotations."),
        _req("independent_images", "Independent image replicates", "study_design", "critical", ("image_id", "field_id", "well", "replicate"), "Use image/well/sample—not segmented objects—as the inferential unit."),
    ),
    "genome_editing_safety": (
        _req("genome_build", "Pinned genome build", "provenance", "critical", ("genome_build", "reference_build", "assembly"), "Use a pinned, intended-population-compatible genome reference."),
        _req("nuclease_pam", "Nuclease/PAM model", "provenance", "major", ("nuclease", "pam", "pam_model", "editor"), "Record nuclease/editor, PAM model and scoring version."),
        _req("exhaustive_search", "Mismatch/bulge search parameters", "validation", "critical", ("max_mismatch", "bulge_count", "search_engine", "search_parameters"), "Document the full off-target search space and parameters."),
        _req("population_variants", "Population-variant overlap", "validation", "major", ("population_af", "snp_overlap", "population_vcf", "variant_release"), "Assess variants that create or remove target/off-target sites."),
        _req("off_target_assay", "Orthogonal off-target assay", "validation", "critical", ("guide_seq", "circle_seq", "digenome_seq", "amplicon_validation"), "Confirm major off-target risks experimentally.", external=True),
    ),
    "proteogenomics_neoantigen": (
        _req("psm_fdr", "PSM/peptide target-decoy FDR", "validation", "critical", ("q_value", "fdr", "pep", "decoy", "spectral_score"), "Control spectrum/peptide identifications using target-decoy statistics."),
        _req("variant_provenance", "Variant-to-protein provenance", "provenance", "critical", ("variant_id", "transcript", "protein_change", "reference_build"), "Retain exact variant, transcript and translated peptide provenance."),
        _req("hla_genotype", "HLA genotype and predictor version", "provenance", "major", ("hla", "hla_genotype", "predictor_version"), "Pin HLA genotype and binding-predictor version."),
        _req("tumour_specificity", "Tumour-normal specificity", "validation", "critical", ("normal_expression", "tumour_expression", "tumor_specificity", "clonality"), "Demonstrate tumour specificity and clonal relevance."),
        _req("immune_validation", "Functional immune validation", "validation", "critical", ("t_cell_assay", "elispot", "tetramer", "cytotoxicity"), "Confirm immunogenicity with a functional assay.", external=True),
    ),
    "glycomics_glycoproteomics": (
        _req("target_decoy", "Target-decoy FDR", "validation", "critical", ("q_value", "fdr", "decoy", "pep"), "Control glycopeptide identifications with target-decoy statistics."),
        _req("localization", "Site-localization confidence", "validation", "major", ("localization_probability", "site_probability", "delta_score"), "Quantify glycosite localization confidence."),
        _req("fragmentation", "Diagnostic fragment evidence", "validation", "major", ("oxonium_ions", "fragment_score", "etd_evidence", "hcd_evidence"), "Retain diagnostic fragment and fragmentation-method evidence."),
        _req("standard_review", "Standard/manual spectrum confirmation", "validation", "critical", ("manual_spectrum_review", "standard_confirmed", "expert_review"), "Confirm priority structures with expert review and suitable standards.", external=True),
    ),
    "population_gwas": (
        _req("genome_build", "Genome build", "provenance", "critical", ("genome_build", "reference_build", "assembly"), "Pin genome build and variant normalization procedure."),
        _req("ancestry_structure", "Population structure/ancestry covariates", "study_design", "critical", ("ancestry", "population", "pc1", "principal_component", "covariates"), "Model ancestry/population structure using prespecified covariates."),
        _req("relatedness", "Relatedness/kinship handling", "study_design", "major", ("kinship", "relatedness", "family_id", "grm"), "Detect and account for relatedness."),
        _req("phenotype_dictionary", "Phenotype/covariate dictionary", "provenance", "major", ("phenotype_definition", "data_dictionary", "covariate_dictionary"), "Lock phenotype and covariate definitions before association testing."),
        _req("replication_cohort", "Independent replication cohort", "validation", "critical", ("replication_cohort", "external_cohort", "independent_validation"), "Replicate priority associations in an independent cohort.", external=True),
    ),
    "structural_variant_repeat": (
        _req("genome_build", "Genome build", "provenance", "critical", ("genome_build", "reference_build", "assembly"), "Pin the build used for calling, annotation and review."),
        _req("caller_version", "Caller/version and parameters", "provenance", "critical", ("caller", "caller_version", "parameters", "algorithm"), "Record caller, version and calling parameters."),
        _req("read_support", "Read-level support", "validation", "critical", ("split_reads", "paired_reads", "read_support", "allele_depth"), "Retain split/paired-read or repeat-spanning evidence."),
        _req("inheritance", "Inheritance/family review", "study_design", "major", ("inheritance", "trio", "family_id", "segregation"), "Assess inheritance/segregation where family data exist."),
        _req("orthogonal_assay", "Orthogonal confirmation", "validation", "critical", ("pcr_validation", "long_read_validation", "cytogenetic_validation", "orthogonal_validation"), "Confirm reportable candidates independently.", external=True),
    ),
    "rna_isoform_splicing": (
        _req("annotation_release", "Transcript annotation release", "provenance", "critical", ("annotation_release", "gtf_version", "transcript_release"), "Pin the transcript annotation release."),
        _req("strand_library", "Strand/library protocol", "provenance", "major", ("strandedness", "library_protocol", "read_layout"), "Record strandedness, read layout and library protocol."),
        _req("junction_support", "Junction/read support", "validation", "critical", ("junction_reads", "read_support", "coverage", "psi"), "Retain event-level read/junction support."),
        _req("biological_replicates", "Biological replicates", "study_design", "critical", ("sample", "replicate", "donor", "condition"), "Use replicate-aware event models rather than pooled reads."),
        _req("orthogonal_assay", "Orthogonal isoform confirmation", "validation", "critical", ("rt_pcr", "long_read_confirmation", "orthogonal_validation"), "Confirm priority isoforms/events independently.", external=True),
    ),
    "cell_atlas_mapping": (
        _req("atlas_release", "Reference atlas release", "provenance", "critical", ("atlas_release", "reference_atlas", "model_version"), "Pin atlas and mapping-model releases."),
        _req("ood_policy", "OOD/confidence policy", "validation", "critical", ("ood_score", "mapping_confidence", "confidence_threshold", "unknown_label"), "Define thresholds and fallback behavior for unsupported cell states."),
        _req("batch_review", "Batch/subgroup mapping review", "study_design", "major", ("batch", "sample", "donor", "subgroup"), "Review mapping performance across batches and donors."),
        _req("expert_annotation", "Expert annotation review", "validation", "critical", ("expert_review", "annotation_reviewer", "marker_review"), "Confirm critical labels using marker/context review.", external=True),
    ),
    "digital_pathology_foundation": (
        _req("scanner_site", "Scanner/site qualification", "provenance", "critical", ("scanner", "scanner_model", "site", "stain_batch"), "Qualify scanner/site/stain variability for the intended use."),
        _req("model_card", "Foundation-model card/version", "provenance", "critical", ("model_version", "checkpoint", "model_card", "training_domain"), "Pin model/checkpoint and intended-domain limitations."),
        _req("ground_truth", "Pathology ground truth", "validation", "critical", ("ground_truth", "pathologist_label", "consensus_label"), "Use representative pathologist-derived ground truth."),
        _req("external_site", "External-site validation", "validation", "critical", ("external_site", "independent_cohort", "external_validation"), "Validate at a genuinely independent site/scanner.", external=True),
    ),
    "long_read_epigenome": (
        _req("basecaller_model", "Basecaller/modification model", "provenance", "critical", ("basecaller_version", "modification_model", "dorado_version"), "Pin basecaller and modification model releases."),
        _req("phasing", "Haplotype phasing evidence", "validation", "major", ("haplotype", "phase_set", "whatshap_version"), "Retain read-backed phasing and phase-set provenance."),
        _req("coverage", "Coverage and replicate adequacy", "study_design", "critical", ("coverage", "read_depth", "sample", "replicate"), "Require adequate per-haplotype coverage and biological replication."),
        _req("orthogonal_methylation", "Orthogonal methylation validation", "validation", "critical", ("bisulfite_validation", "pyrosequencing", "orthogonal_validation"), "Confirm priority DMR/imprinting findings independently.", external=True),
    ),
    "amr_surveillance": (
        _req("database_release", "AMR database release", "provenance", "critical", ("database_release", "card_version", "resfinder_version", "amrfinder_version"), "Pin taxonomy/AMR databases and interpretation rules."),
        _req("controls", "Negative/mock controls", "study_design", "critical", ("negative_control", "mock_control", "control_type"), "Include contamination and process controls."),
        _req("phenotype", "Phenotypic susceptibility", "validation", "critical", ("mic", "susceptibility", "phenotype", "breakpoint_version"), "Compare genotype with validated phenotypic susceptibility."),
        _req("lab_confirmation", "Laboratory confirmation", "validation", "critical", ("culture_confirmation", "clinical_lab_review", "orthogonal_validation"), "Confirm high-impact calls in a qualified laboratory.", external=True),
    ),
    "gene_therapy_vector": (
        _req("vector_map", "Versioned vector map", "provenance", "critical", ("vector_version", "construct_id", "genbank", "sequence_hash"), "Lock the complete vector sequence/map and component provenance."),
        _req("integration_risk", "Integration-site risk evidence", "validation", "critical", ("integration_site", "insertional_risk", "integration_assay"), "Assess integration-site and insertional-oncogenesis risk."),
        _req("capsid_immunity", "Capsid/host immunity evidence", "validation", "major", ("neutralizing_antibody", "capsid_immunity", "preexisting_immunity"), "Assess relevant pre-existing and induced immune responses."),
        _req("manufacturing_validation", "Manufacturing/lot validation", "validation", "critical", ("lot", "potency_assay", "purity", "manufacturing_validation"), "Confirm identity, purity, potency and consistency experimentally.", external=True),
    ),
    "cell_therapy_cart": (
        _req("construct_version", "Versioned CAR construct", "provenance", "critical", ("construct_id", "sequence_hash", "vector_version"), "Lock the complete construct and manufacturing version."),
        _req("healthy_tissue", "Healthy-tissue antigen review", "validation", "critical", ("healthy_tissue_expression", "off_tumour_risk", "atlas_release"), "Evaluate target expression in critical healthy tissues."),
        _req("functional_assays", "Function/exhaustion assays", "validation", "critical", ("cytotoxicity", "cytokine", "exhaustion", "tonic_signaling"), "Confirm potency, specificity, exhaustion and tonic-signalling profiles."),
        _req("manufacturing_release", "Manufacturing release evidence", "validation", "critical", ("release_assay", "sterility", "identity", "viability", "potency"), "Attach qualified lot-release evidence.", external=True),
    ),
    "federated_biomedical_ai": (
        _req("site_manifest", "Site/data manifest", "provenance", "critical", ("site_id", "site_manifest", "schema_version", "cohort_definition"), "Pin site-specific cohorts, schemas and eligibility rules."),
        _req("secure_aggregation", "Secure aggregation implementation", "validation", "critical", ("secure_aggregation", "protocol_version", "cryptographic_review"), "Use a reviewed secure-aggregation protocol, not a simulation flag."),
        _req("privacy_budget", "Privacy/accounting policy", "provenance", "major", ("epsilon", "delta", "privacy_budget", "dp_accountant"), "Record privacy budget and accounting assumptions where DP is used."),
        _req("attack_testing", "Privacy/adversarial testing", "validation", "critical", ("membership_inference", "gradient_leakage", "poisoning_test", "red_team"), "Perform privacy and adversarial attack testing.", external=True),
    ),
    "protein_ligand_codesign": (
        _req("model_version", "Generative model/version", "provenance", "critical", ("model_version", "checkpoint", "training_domain"), "Pin generative model/checkpoint and training-domain limits."),
        _req("structure_quality", "Structure/pose quality", "validation", "major", ("structure_confidence", "pose_confidence", "clash_score", "rmsd"), "Review structural confidence, clashes and pose plausibility."),
        _req("synthesis_feasibility", "Synthesis/developability review", "validation", "major", ("synthesis_score", "sa_score", "developability", "liability"), "Assess synthesis and developability constraints."),
        _req("experimental_binding", "Experimental binding/function", "validation", "critical", ("kd", "ki", "ic50", "functional_assay"), "Confirm designed candidates experimentally.", external=True),
    ),
    "pharmacovigilance_intelligence": (
        _req("terminology_release", "MedDRA/terminology release", "provenance", "critical", ("meddra_version", "terminology_release", "coding_version"), "Pin coding terminology and dictionary versions."),
        _req("deduplication", "Case deduplication/provenance", "data_quality", "critical", ("case_id", "duplicate_group", "source_system", "report_version"), "Resolve follow-ups and duplicate reports without double counting."),
        _req("exposure_denominator", "Exposure/denominator context", "study_design", "major", ("exposure", "patient_years", "denominator", "utilization"), "Interpret reporting signals with exposure and reporting context where available."),
        _req("causal_review", "Clinical causal assessment", "validation", "critical", ("causality_assessment", "clinical_review", "adjudication"), "Require expert case review before causal conclusions.", external=True),
    ),
    "autonomous_lab_planner": (
        _req("instrument_driver", "Qualified instrument/robot driver", "provenance", "critical", ("driver_version", "robot_model", "instrument_id"), "Pin and qualify real device drivers and deck/labware definitions."),
        _req("deck_validation", "Deck/labware validation", "validation", "critical", ("deck_layout", "labware_definition", "collision_check"), "Validate positions, volumes, collisions and consumables."),
        _req("safety_interlock", "Physical safety interlocks", "validation", "critical", ("safety_interlock", "emergency_stop", "hazard_review"), "Confirm physical safety and hazard controls."),
        _req("closed_loop_validation", "Closed-loop experiment validation", "validation", "critical", ("closed_loop_run", "execution_log", "human_approval"), "Validate planned-to-executed actions under supervised conditions.", external=True),
    ),
}


def _normalise_key(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("-", "_")


def _flatten_metadata(value: Any, prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten_metadata(item, child))
            flattened[_normalise_key(str(key))] = item
    elif isinstance(value, (list, tuple, set)):
        flattened[prefix] = list(value)
    elif prefix:
        flattened[prefix] = value
    return flattened


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        return bool(np.isfinite(value))
    if isinstance(value, dict):
        # Container presence alone is not evidence; scalar fields inside it are
        # flattened and assessed independently.
        return False
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    text = str(value).strip().lower()
    return text not in {"", "none", "null", "nan", "na", "n/a", "unknown", "not available"}


def _column_has_evidence(data: pd.DataFrame | None, alias: str) -> tuple[bool, str]:
    if data is None or data.empty:
        return False, ""
    lookup = {_normalise_key(column): str(column) for column in data.columns}
    key = _normalise_key(alias)
    column = lookup.get(key)
    if column is None:
        return False, ""
    values = data[column]
    if pd.api.types.is_bool_dtype(values):
        present = bool(values.fillna(False).any())
    else:
        present = bool(values.map(_nonempty).any())
    return present, column


def _metadata_has_evidence(flat_metadata: Mapping[str, Any], alias: str) -> tuple[bool, str]:
    key = _normalise_key(alias)
    for meta_key, value in flat_metadata.items():
        normalised = _normalise_key(meta_key.split(".")[-1])
        if normalised == key and _nonempty(value):
            return True, str(meta_key)
    return False, ""


def _requirement_status(
    requirement: EvidenceRequirement,
    data: pd.DataFrame | None,
    flat_metadata: Mapping[str, Any],
    verified_requirements: set[str],
) -> tuple[str, str, str]:
    evidence_source = ""
    evidence_location = ""
    for alias in requirement.aliases:
        present, location = _column_has_evidence(data, alias)
        if present:
            evidence_source, evidence_location = "data column", location
            break
        present, location = _metadata_has_evidence(flat_metadata, alias)
        if present:
            evidence_source, evidence_location = "manifest", location
            break
    if not evidence_source:
        return "fail", "Not detected", ""
    if requirement.external and requirement.key not in verified_requirements:
        return "review", f"Declared in {evidence_source}; independent verification not recorded", evidence_location
    return "pass", f"Detected in {evidence_source}", evidence_location


def _check_row(
    key: str,
    label: str,
    category: str,
    severity: str,
    status: str,
    detail: str,
    *,
    weight: float = 1.0,
) -> dict[str, Any]:
    return {
        "key": key,
        "check": label,
        "category": category,
        "severity": severity,
        "status": status,
        "detail": detail,
        "weight": float(weight),
    }


def _required_column_checks(data: pd.DataFrame | None, required_columns: Sequence[str]) -> list[dict[str, Any]]:
    if not required_columns:
        return []
    if data is None or data.empty:
        return [_check_row("required_schema", "Required input schema", "data_quality", "critical", "fail", "No dataset loaded", weight=3)]
    lookup = {_normalise_key(column) for column in data.columns}
    missing = [column for column in required_columns if _normalise_key(column) not in lookup]
    status = "pass" if not missing else "fail"
    detail = "All required columns detected" if not missing else "Missing: " + ", ".join(missing)
    return [_check_row("required_schema", "Required input schema", "data_quality", "critical", status, detail, weight=3)]


def _generic_data_checks(data: pd.DataFrame | None, source_mode: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if data is None or data.empty:
        rows.append(_check_row("dataset_loaded", "Dataset loaded", "data_quality", "critical", "fail", "No analyzable records", weight=3))
        return rows

    n_rows, n_cols = data.shape
    rows.append(_check_row("dataset_loaded", "Dataset loaded", "data_quality", "critical", "pass", f"{n_rows:,} rows × {n_cols:,} columns", weight=3))
    if n_rows >= 30:
        sample_status = "pass"
    elif n_rows >= 10:
        sample_status = "review"
    else:
        sample_status = "fail"
    rows.append(_check_row("sample_size", "Minimum analyzable records", "study_design", "major", sample_status, f"{n_rows:,} records", weight=2))

    cells = max(n_rows * max(n_cols, 1), 1)
    missing_rate = float(data.isna().sum().sum() / cells)
    missing_status = "pass" if missing_rate <= 0.05 else "review" if missing_rate <= 0.20 else "fail"
    rows.append(_check_row("missingness", "Overall missingness", "data_quality", "major", missing_status, f"{missing_rate:.1%} missing cells", weight=2))

    duplicate_rate = float(data.astype(str).duplicated().mean()) if n_rows else 0.0
    duplicate_status = "pass" if duplicate_rate <= 0.01 else "review" if duplicate_rate <= 0.05 else "fail"
    rows.append(_check_row("duplicates", "Duplicate records", "data_quality", "major", duplicate_status, f"{duplicate_rate:.1%} duplicate rows", weight=2))

    numeric = data.select_dtypes(include=[np.number])
    if numeric.empty:
        rows.append(_check_row("numeric_signal", "Numeric analytical signal", "data_quality", "minor", "review", "No numeric columns detected", weight=1))
    else:
        values = numeric.to_numpy(dtype=float, copy=False)
        finite_rate = float(np.isfinite(values).mean()) if values.size else 1.0
        finite_status = "pass" if finite_rate >= 0.995 else "review" if finite_rate >= 0.95 else "fail"
        rows.append(_check_row("finite_numeric", "Finite numeric values", "data_quality", "major", finite_status, f"{finite_rate:.1%} finite", weight=2))
        constant = int(sum(pd.to_numeric(numeric[column], errors="coerce").nunique(dropna=True) <= 1 for column in numeric.columns))
        constant_rate = constant / max(len(numeric.columns), 1)
        constant_status = "pass" if constant_rate == 0 else "review" if constant_rate <= 0.25 else "fail"
        rows.append(_check_row("constant_features", "Non-constant numeric features", "data_quality", "minor", constant_status, f"{constant}/{len(numeric.columns)} constant", weight=1))

    source = str(source_mode or "").strip().lower()
    if source in {"demo", "demonstration", "synthetic", "deterministic demonstration data"}:
        rows.append(_check_row("real_data", "Real-data evidence", "validation", "critical", "fail", "Demonstration/synthetic data cannot support scientific release", weight=3))
    elif source:
        rows.append(_check_row("real_data", "Real-data evidence", "validation", "critical", "review", f"Source declared as {source}; provenance must be verified", weight=3))
    else:
        rows.append(_check_row("real_data", "Real-data evidence", "validation", "critical", "review", "Source mode not recorded", weight=3))

    return rows


def _design_checks(data: pd.DataFrame | None) -> list[dict[str, Any]]:
    if data is None or data.empty:
        return []
    rows: list[dict[str, Any]] = []
    lookup = {_normalise_key(column): str(column) for column in data.columns}
    group_column = next((lookup[key] for key in ("condition", "group", "arm", "cohort", "phenotype", "treatment") if key in lookup), None)
    sample_column = next((lookup[key] for key in ("sample", "sample_id", "subject", "subject_id", "patient", "donor", "batch", "image_id", "section_id") if key in lookup), None)

    if group_column:
        groups = data[group_column].dropna().astype(str)
        group_count = int(groups.nunique())
        status = "pass" if group_count >= 2 else "fail"
        rows.append(_check_row("group_structure", "Comparison groups", "study_design", "major", status, f"{group_count} distinct groups in {group_column}", weight=2))
        if sample_column and group_count >= 2:
            counts = data[[group_column, sample_column]].dropna().astype(str).drop_duplicates().groupby(group_column)[sample_column].nunique()
            minimum = int(counts.min()) if not counts.empty else 0
            replicate_status = "pass" if minimum >= 3 else "review" if minimum >= 2 else "fail"
            rows.append(_check_row("replicate_balance", "Independent units per group", "study_design", "critical", replicate_status, f"Minimum {minimum} unique {sample_column} values per group", weight=3))
        else:
            rows.append(_check_row("replicate_identity", "Independent experimental-unit identifier", "study_design", "critical", "review", "No independent sample/donor/image/section identifier detected", weight=3))
    else:
        rows.append(_check_row("group_structure", "Study-design grouping", "study_design", "minor", "review", "No standard group/condition/arm column detected", weight=1))

    id_candidates = [lookup[key] for key in ("sample_id", "patient", "subject_id", "cell", "spot", "object_id", "variant_id", "record_id") if key in lookup]
    if id_candidates:
        id_column = id_candidates[0]
        missing_id = float(data[id_column].isna().mean())
        status = "pass" if missing_id == 0 else "review" if missing_id <= 0.05 else "fail"
        rows.append(_check_row("identifier_completeness", "Identifier completeness", "data_quality", "major", status, f"{missing_id:.1%} missing in {id_column}", weight=2))
    return rows


def _requirements_for(
    module_key: str,
    *,
    profile_references: Sequence[str] = (),
    profile_validations: Sequence[str] = (),
) -> tuple[EvidenceRequirement, ...]:
    requirements = list(COMMON_REQUIREMENTS)
    requirements.extend(CUSTOM_REQUIREMENTS.get(module_key, ()))
    existing = {requirement.key for requirement in requirements}

    for index, reference in enumerate(profile_references[:3], start=1):
        key = f"profile_reference_{index}"
        if key in existing:
            continue
        slug = _normalise_key(reference)
        requirements.append(_req(key, str(reference), "provenance", "major", (slug, f"{slug}_version", f"{slug}_release"), f"Record the exact source and release for {reference}."))

    for index, validation in enumerate(profile_validations[:4], start=1):
        key = f"profile_validation_{index}"
        if key in existing:
            continue
        slug = _normalise_key(validation)
        requirements.append(_req(key, str(validation), "validation", "major", (slug, f"{slug}_status", f"{slug}_review"), f"Document the result and reviewer decision for: {validation}."))
    return tuple(requirements)


def _category_score(checks: pd.DataFrame, category: str) -> float:
    subset = checks.loc[checks["category"] == category]
    if subset.empty:
        return 0.0
    weights = pd.to_numeric(subset["weight"], errors="coerce").fillna(1.0)
    factors = subset["status"].map(_STATUS_FACTOR).fillna(0.0)
    return float((weights * factors).sum() / max(weights.sum(), 1e-12) * _CATEGORY_WEIGHTS[category])


def _grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    return "D"


def _stable_frame_hash(data: pd.DataFrame | None) -> str | None:
    if data is None or data.empty:
        return None
    payload = data.to_csv(index=False, lineterminator="\n", na_rep="<NA>").encode("utf-8")
    return sha256(payload).hexdigest()


def evidence_manifest_template(module_key: str, requirements: Sequence[EvidenceRequirement]) -> dict[str, Any]:
    return {
        "schema": "biointel.step151.evidence-declaration.v1",
        "module_key": module_key,
        "source_mode": "upload",
        "input_sha256": "",
        "software_version": "",
        "reference_release": "",
        "reviewer": "",
        "verified_requirements": [],
        "evidence": {
            requirement.key: {
                "status": "not_provided",
                "reference": "",
                "notes": requirement.description,
            }
            for requirement in requirements
        },
    }



def build_evidence_manifest_template(
    module_key: str,
    *,
    profile_references: Sequence[str] = (),
    profile_validations: Sequence[str] = (),
) -> dict[str, Any]:
    return evidence_manifest_template(
        module_key,
        _requirements_for(
            module_key,
            profile_references=profile_references,
            profile_validations=profile_validations,
        ),
    )

def assess_evidence_readiness(
    module_key: str,
    data: pd.DataFrame | None,
    *,
    required_columns: Sequence[str] = (),
    profile_references: Sequence[str] = (),
    profile_validations: Sequence[str] = (),
    metadata: Mapping[str, Any] | None = None,
    source_mode: str | None = None,
    run_summary: Mapping[str, Any] | None = None,
) -> EvidenceReadiness:
    metadata_dict: dict[str, Any] = dict(metadata or {})
    if run_summary:
        metadata_dict.setdefault("run_summary", dict(run_summary))
    if source_mode:
        metadata_dict.setdefault("source_mode", source_mode)
    flat_metadata = _flatten_metadata(metadata_dict)
    verified_raw = metadata_dict.get("verified_requirements", [])
    if isinstance(verified_raw, str):
        verified_requirements = {_normalise_key(value) for value in verified_raw.split(",") if value.strip()}
    elif isinstance(verified_raw, Iterable):
        verified_requirements = {_normalise_key(value) for value in verified_raw}
    else:
        verified_requirements = set()

    requirements = _requirements_for(
        module_key,
        profile_references=profile_references,
        profile_validations=profile_validations,
    )

    check_rows: list[dict[str, Any]] = []
    check_rows.extend(_required_column_checks(data, required_columns))
    check_rows.extend(_generic_data_checks(data, source_mode or str(metadata_dict.get("source_mode", ""))))
    check_rows.extend(_design_checks(data))

    requirement_rows: list[dict[str, Any]] = []
    for requirement in requirements:
        status, detail, location = _requirement_status(requirement, data, flat_metadata, verified_requirements)
        requirement_rows.append({
            **asdict(requirement),
            "aliases": ", ".join(requirement.aliases),
            "status": status,
            "detail": detail,
            "evidence_location": location,
        })
        check_rows.append(_check_row(
            f"evidence:{requirement.key}",
            requirement.label,
            requirement.category,
            requirement.severity,
            status,
            detail,
            weight=3.0 if requirement.severity == "critical" else 2.0 if requirement.severity == "major" else 1.0,
        ))

    checks = pd.DataFrame(check_rows)
    requirements_frame = pd.DataFrame(requirement_rows)
    scores = {category: _category_score(checks, category) for category in _CATEGORY_WEIGHTS}
    total_score = round(float(sum(scores.values())), 1)

    blockers: list[str] = []
    for row in check_rows:
        if row["status"] == "fail" and row["severity"] in {"critical", "major"}:
            blockers.append(f"{row['check']}: {row['detail']}")
    external_unverified = requirements_frame.loc[
        requirements_frame["external"].astype(bool) & (requirements_frame["status"] != "pass")
    ] if not requirements_frame.empty else pd.DataFrame()
    for _, row in external_unverified.iterrows():
        blocker = f"{row['label']}: independent verification is not complete"
        if blocker not in blockers:
            blockers.append(blocker)

    release_ready = bool(total_score >= 90 and not blockers and external_unverified.empty)
    grade = _grade(total_score)
    data_hash = _stable_frame_hash(data)
    manifest = {
        "schema": "biointel.step151.scientific-readiness.v1",
        "module_key": module_key,
        "score": total_score,
        "grade": grade,
        "release_ready": release_ready,
        "category_scores": {key: round(value, 1) for key, value in scores.items()},
        "input_profile": {
            "rows": int(len(data)) if isinstance(data, pd.DataFrame) else 0,
            "columns": list(data.columns) if isinstance(data, pd.DataFrame) else [],
            "stable_table_sha256": data_hash,
            "source_mode": source_mode or metadata_dict.get("source_mode"),
        },
        "checks": check_rows,
        "requirements": requirement_rows,
        "blockers": blockers,
        "evidence_declaration": metadata_dict,
        "policy": {
            "external_evidence_is_never_auto_verified": True,
            "checking_or_declaring_evidence_does_not_certify_it": True,
            "clinical_or_regulatory_release_requires_separate_qualification": True,
        },
    }
    # Confirm deterministic JSON serialisability now, rather than failing during export.
    json.dumps(manifest, default=str, sort_keys=True)
    return EvidenceReadiness(
        module_key=module_key,
        score=total_score,
        grade=grade,
        data_quality_score=round(scores["data_quality"], 1),
        design_score=round(scores["study_design"], 1),
        provenance_score=round(scores["provenance"], 1),
        validation_score=round(scores["validation"], 1),
        reproducibility_score=round(scores["reproducibility"], 1),
        release_ready=release_ready,
        checks=checks,
        requirements=requirements_frame,
        blockers=tuple(blockers),
        manifest=manifest,
    )
