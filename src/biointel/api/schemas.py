from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SequenceAnalysisRequest(BaseModel):
    sequence: str = Field(min_length=1, max_length=200_000)
    sequence_type: Literal["auto", "DNA", "RNA", "Protein"] = "auto"


class AlignmentRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200_000)
    target: str = Field(min_length=1, max_length=200_000)
    sequence_type: Literal["DNA", "RNA", "Protein"]
    mode: Literal["global", "local"] = "global"
    match_score: float = 2.0
    mismatch_score: float = -1.0
    gap_open: float = -2.0
    gap_extend: float = -0.5
    substitution_matrix: Literal["BLOSUM62", "PAM250"] = "BLOSUM62"


class DtiPredictionRequest(BaseModel):
    model_filename: str = Field(min_length=1, max_length=255)
    canonical_smiles: str = Field(min_length=1, max_length=10_000)
    protein_sequence: str = Field(min_length=1, max_length=100_000)


class DtiBatchRow(BaseModel):
    sample_id: str | int | None = None
    canonical_smiles: str = Field(min_length=1, max_length=10_000)
    protein_sequence: str = Field(min_length=1, max_length=100_000)


class DtiBatchRequest(BaseModel):
    model_filename: str = Field(min_length=1, max_length=255)
    rows: list[DtiBatchRow] = Field(min_length=1, max_length=100)


class ExternalValidationRequest(BaseModel):
    model_filename: str = Field(min_length=1, max_length=255)
    rows: list[dict[str, Any]] = Field(min_length=2, max_length=500)


class DataCurationRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=5_000)
    active_threshold: float = Field(default=6.0, ge=0.0, le=15.0)
    aggregate_duplicates: bool = True
    source_database: str = Field(default="api_import", min_length=1, max_length=100)


class ReleaseGateRequest(BaseModel):
    model_filename: str = Field(min_length=1, max_length=255)
    external_validation: dict[str, Any] | None = None
    prospective_validation: dict[str, Any] | None = None
    split_summary: dict[str, Any] | None = None
    evidence_manifest: dict[str, Any] | None = None
    dataset_metadata: dict[str, Any] | None = None
    leakage_audit: dict[str, Any] | None = None
    validation_matrix: dict[str, Any] | None = None
    drift_report: dict[str, Any] | None = None
    strict: bool = True


class EvidenceReviewRequest(BaseModel):
    evidence_key: str = Field(min_length=8, max_length=128)
    decision: Literal["pending", "accepted", "rejected", "edited"]
    reviewer: str = Field(min_length=1, max_length=120)
    comment: str = Field(default="", max_length=5_000)
    original: dict[str, Any] | None = None
    revised: dict[str, Any] | None = None


class JobSubmitRequest(BaseModel):
    job_type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any]
    priority: int = Field(default=100, ge=1, le=10_000)
    max_attempts: int = Field(default=3, ge=1, le=10)
    dependencies: list[str] = Field(default_factory=list, max_length=50)
    stages: list[str] = Field(default_factory=list, max_length=50)
    resources: dict[str, Any] = Field(default_factory=dict)
    estimated_seconds: float | None = Field(default=None, ge=0, le=604800)


class UnifiedReportRequest(BaseModel):
    title: str = Field(default="BioIntel AI Unified Scientific Report", min_length=1, max_length=200)
    notes: str = Field(default="", max_length=20_000)
    reviewer: str = Field(default="", max_length=200)
    sections: list[str] = Field(default_factory=list, max_length=20)


class UiRegressionRequest(BaseModel):
    mode: Literal["static", "apptest", "full"] = "static"
    selected_pages: list[str] = Field(default_factory=list, max_length=500)
    timeout_seconds: int = Field(default=30, ge=5, le=120)


class DocumentOrganizeRequest(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=100)
    project_code: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=10_000)


class DocumentQuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=5_000)
    run_ids: list[str] | None = Field(default=None, max_length=50)
    maximum_documents: int = Field(default=10, ge=1, le=50)
    maximum_citations: int = Field(default=5, ge=1, le=20)


class DocumentCompareRequest(BaseModel):
    left_run_id: str = Field(min_length=8, max_length=128)
    right_run_id: str = Field(min_length=8, max_length=128)


class OcrCorrectionRequest(BaseModel):
    region_id: str = Field(min_length=8, max_length=128)
    original_text: str = Field(default="", max_length=10_000)
    corrected_text: str = Field(min_length=1, max_length=10_000)
    reviewer: str = Field(min_length=1, max_length=120)
    comment: str = Field(default="", max_length=5_000)


class DocumentDatasetBridgeRequest(BaseModel):
    table_index: int = Field(ge=0, le=10_000)
    dataset_name: str = Field(min_length=1, max_length=200)
    dataset_version: str = Field(min_length=1, max_length=100)
    task_type: Literal["classification", "regression", "unlabelled"] = "unlabelled"
    activity_type: str | None = Field(default=None, max_length=100)
    notes: str = Field(default="", max_length=10_000)


class DocumentEvidenceBridgeRequest(BaseModel):
    table_index: int = Field(ge=0, le=10_000)
    column_mapping: dict[str, str]
    provider: str = Field(default="document_extraction", min_length=1, max_length=100)
    source_release: str = Field(default="document_import", min_length=1, max_length=100)
    active_threshold: float = Field(default=6.0, ge=0.0, le=15.0)


class FastqQcRequest(BaseModel):
    fastq_text: str = Field(min_length=8, max_length=10_000_000)
    adapter: str | None = Field(default=None, max_length=200)
    minimum_quality: int = Field(default=20, ge=0, le=50)
    minimum_length: int = Field(default=30, ge=1, le=10_000)


class VariantSummaryRequest(BaseModel):
    vcf_text: str = Field(min_length=8, max_length=10_000_000)
    minimum_quality: float = Field(default=20.0, ge=0, le=10_000)
    require_pass: bool = True


class PrimerDesignRequest(BaseModel):
    sequence: str = Field(min_length=40, max_length=200_000)
    minimum_product: int = Field(default=100, ge=30, le=100_000)
    maximum_product: int = Field(default=600, ge=50, le=200_000)
    maximum_pairs: int = Field(default=25, ge=1, le=200)


class CrisprDesignRequest(BaseModel):
    sequence: str = Field(min_length=25, max_length=200_000)
    guide_length: int = Field(default=20, ge=15, le=30)


class ProteinAnnotationRequest(BaseModel):
    sequence: str = Field(min_length=1, max_length=200_000)


class StructureAnalysisRequest(BaseModel):
    pdb_text: str = Field(min_length=20, max_length=20_000_000)
    contact_cutoff: float = Field(default=4.0, ge=1.0, le=10.0)


class AdmetProfileRequest(BaseModel):
    smiles: str = Field(min_length=1, max_length=10_000)


class PathwayEnrichmentRequest(BaseModel):
    genes: list[str] = Field(min_length=1, max_length=10_000)


class QpcrAnalysisRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=100_000)
    calibrator_sample: str = Field(min_length=1, max_length=200)


class ElisaAnalysisRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(min_length=4, max_length=100_000)
    candidate_models: list[Literal["4PL", "5PL", "log-linear", "linear"]] = Field(default_factory=lambda: ["4PL", "5PL", "log-linear"], min_length=1, max_length=4)
    maximum_replicate_cv_percent: float = Field(default=20.0, gt=0, le=200)


class EnzymeKineticsRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(min_length=4, max_length=100_000)
    model: Literal["auto", "michaelis_menten", "hill", "substrate_inhibition"] = "auto"


class BioprocessAnalysisRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(min_length=3, max_length=200_000)
    process_mode: Literal["Batch", "Fed-batch", "Continuous", "Perfusion"] = "Batch"
    batch_column: str | None = Field(default=None, max_length=200)


class ExperimentalDesignRequest(BaseModel):
    design_type: Literal["two_group", "paired", "anova", "noninferiority", "equivalence"] = "two_group"
    effect_size: float = Field(default=0.8, gt=0)
    alpha: float = Field(default=0.05, gt=0, lt=1)
    power: float = Field(default=0.8, gt=0, lt=1)
    groups: int = Field(default=3, ge=2, le=100)
    margin: float = Field(default=0.5, gt=0)
    assumed_standard_deviation: float = Field(default=1.0, gt=0)
    dropout_fraction: float = Field(default=0.0, ge=0, lt=0.8)


class PlateQcRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=100_000)
    value_column: str = Field(min_length=1, max_length=200)
    well_column: str = Field(default="well", min_length=1, max_length=200)
    plate_column: str | None = Field(default=None, max_length=200)
    plate_format: Literal[96, 384] = 96


class PhylogenyRequest(BaseModel):
    sequences: dict[str, str] = Field(min_length=2, max_length=5000)


class ConnectedSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    entity_type: Literal[
        "gene", "protein", "compound", "structure", "variant", "literature",
        "clinical trial", "pathway", "protein interaction", "expression study", "sequence"
    ] = "gene"
    providers: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=10, ge=1, le=25)


class ConnectedHealthRequest(BaseModel):
    providers: list[str] = Field(default_factory=list, max_length=20)



class CopilotQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    providers: list[str] = Field(default_factory=list, max_length=20)
    context: str = Field(default="", max_length=20_000)
    model: str | None = Field(default=None, max_length=100)


class DiscoveryProjectCreateRequest(BaseModel):
    project_name: str = Field(min_length=1, max_length=200)
    indication: str = Field(default="", max_length=300)
    objective: str = Field(default="", max_length=10_000)
    owner: str = Field(default="local_user", min_length=1, max_length=120)
    settings: dict[str, Any] = Field(default_factory=dict)


class DiscoveryTargetProfileRequest(BaseModel):
    target_id: str = Field(min_length=1, max_length=200)
    indication: str = Field(default="", max_length=300)
    template: Literal["balanced", "genetics_first", "oncology", "cns", "infectious_disease"] = "balanced"
    evidence_rows: list[dict[str, Any]] = Field(min_length=1, max_length=10_000)
    custom_weights: dict[str, float] | None = None
    hard_gates: dict[str, float] = Field(default_factory=dict)


class DiscoveryCompoundRequest(BaseModel):
    compound_id: str = Field(min_length=1, max_length=200)
    smiles: str = Field(min_length=1, max_length=10_000)
    preparation_mode: Literal[
        "submitted_form",
        "neutral_parent",
        "tautomer_ensemble",
        "stereoisomer_ensemble",
        "assay_context",
        "physiological_context",
    ] = "neutral_parent"
    ph: float | None = Field(default=None, ge=0, le=14)
    duplicate_policy: Literal[
        "merge_exact", "keep_separate", "reject_exact", "merge_connectivity"
    ] = "merge_exact"
    source: dict[str, Any] = Field(default_factory=dict)


class DiscoveryRankingRequest(BaseModel):
    benefit_columns: dict[str, float] = Field(default_factory=dict)
    cost_columns: dict[str, float] = Field(default_factory=dict)
    method: Literal["robust_percentile", "winsorized_minmax", "minmax", "zscore"] = "robust_percentile"
    missing_penalty: float = Field(default=0.25, ge=0, le=1)
    minimum_completeness: float = Field(default=0.6, ge=0, le=1)


class DiscoveryBatchStandardizeRow(BaseModel):
    compound_id: str | int | None = None
    smiles: str = Field(min_length=1, max_length=10_000)


class DiscoveryBatchStandardizeRequest(BaseModel):
    rows: list[DiscoveryBatchStandardizeRow] = Field(min_length=1, max_length=10_000)
    preparation_mode: Literal[
        "submitted_form",
        "neutral_parent",
        "tautomer_ensemble",
        "stereoisomer_ensemble",
        "assay_context",
        "physiological_context",
    ] = "neutral_parent"
    ph: float | None = Field(default=None, ge=0, le=14)
    deduplicate: bool = True


class DiscoverySimilarityRequest(BaseModel):
    query_smiles: str = Field(min_length=1, max_length=10_000)
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=10_000)
    smiles_column: str = Field(default="smiles", min_length=1, max_length=200)
    name_column: str = Field(default="name", min_length=1, max_length=200)
    top_n: int = Field(default=20, ge=1, le=1000)


class DiscoveryEndpointModelCardRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=200)
    endpoint: str = Field(min_length=1, max_length=300)
    version: str = Field(min_length=1, max_length=100)
    artifact_sha256: str = Field(min_length=1, max_length=64)
    training_dataset_sha256: str = Field(min_length=1, max_length=64)
    licence: str = Field(default="", max_length=500)
    endpoint_definition: str = Field(default="", max_length=5000)
    units: str = Field(default="", max_length=100)
    split_strategies: list[str] = Field(default_factory=list, max_length=50)
    metrics: dict[str, float] = Field(default_factory=dict)
    calibration: dict[str, Any] = Field(default_factory=dict)
    applicability_domain: dict[str, Any] = Field(default_factory=dict)
    independent_validation: dict[str, Any] = Field(default_factory=dict)
    intended_use: str = Field(default="", max_length=5000)
    limitations: list[str] = Field(default_factory=list, max_length=100)


class DiscoveryDockingQualificationRequest(BaseModel):
    receptor_prepared: bool = False
    ligand_prepared: bool = False
    grid_defined: bool = False
    reference_ligand_available: bool = False
    redocking_rmsd_angstrom: float | None = Field(default=None, ge=0, le=50)
    enrichment_factor_1_percent: float | None = Field(default=None, ge=0, le=1000)
    pose_review_completed: bool = False
    protocol: dict[str, Any] = Field(default_factory=dict)


class SyntheticDatasetRequest(BaseModel):
    demo_mode: Literal[True]
    module_id: Literal[
        "sequencing_quality", "alignment_mapping", "differential_expression",
        "biomarker_discovery", "variant_prioritization", "pathway_enrichment",
        "multi_omics", "single_cell", "proteomics", "metabolomics", "microbiome",
        "structural_biology", "drug_target_discovery", "experimental_design",
        "statistical_analysis", "literature_discovery", "hypothesis_generation",
        "laboratory_validation",
    ]
    scenario: str = Field(min_length=1, max_length=120)
    size_preset: Literal["small", "medium", "large"] = "small"
    preset_name: str = Field(default="Typical Research Dataset", min_length=1, max_length=120)
    sample_count: int | None = Field(default=None, ge=4, le=2000)
    feature_count: int | None = Field(default=None, ge=1, le=10000)
    group_count: int = Field(default=2, ge=2, le=20)
    effect_size: float = Field(default=1.0, ge=0.0, le=20.0)
    noise_level: float = Field(default=0.25, ge=0.0, le=10.0)
    missing_data_rate: float = Field(default=0.02, ge=0.0, le=1.0)
    batch_effect_strength: float = Field(default=0.2, ge=0.0, le=10.0)
    seed: int = Field(default=42, ge=0, le=2147483647)
    project_id: str | None = Field(default=None, max_length=120)
