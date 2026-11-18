from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreateBody(StrictModel):
    title: str = Field(min_length=1, max_length=240)
    research_question: str = Field(min_length=1, max_length=4000)
    scientific_objective: str = Field(min_length=1, max_length=4000)
    disease_context: str = Field(default="", max_length=1000)
    organism: str = Field(default="", max_length=200)
    assay_types: list[str] = Field(default_factory=list, max_length=100)
    principal_investigator: str = Field(default="", max_length=240)
    owner: str = Field(default="local_user", min_length=1, max_length=240)
    contributors: list[str] = Field(default_factory=list, max_length=500)
    reviewers: list[str] = Field(default_factory=list, max_length=500)
    start_date: str | None = None
    target_date: str | None = None
    data_origin: str = "user_entered_interpretation"
    is_synthetic: bool = False


class ProjectUpdateBody(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    research_question: str | None = Field(default=None, min_length=1, max_length=4000)
    scientific_objective: str | None = Field(default=None, min_length=1, max_length=4000)
    disease_context: str | None = Field(default=None, max_length=1000)
    organism: str | None = Field(default=None, max_length=200)
    assay_types: list[str] | None = Field(default=None, max_length=100)
    principal_investigator: str | None = Field(default=None, max_length=240)
    owner: str | None = Field(default=None, min_length=1, max_length=240)
    contributors: list[str] | None = Field(default=None, max_length=500)
    reviewers: list[str] | None = Field(default=None, max_length=500)
    start_date: str | None = None
    target_date: str | None = None
    milestones: list[dict[str, Any]] | None = None
    risks: list[str] | None = None
    blockers: list[str] | None = None


class StageGateBody(StrictModel):
    stage: str
    artifact_ids: list[str] = Field(default_factory=list, max_length=1000)
    criteria: list[str] | None = Field(default=None, max_length=1000)
    status: Literal["Pending", "Conditional", "Approved", "Rejected"] = "Pending"
    note: str = Field(default="", max_length=4000)


class DatasetCreateBody(StrictModel):
    name: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=4000)
    assay_type: str = Field(default="", max_length=160)
    omics_type: str = Field(default="", max_length=160)
    organism: str = Field(default="", max_length=200)
    tissue: str = Field(default="", max_length=200)
    disease: str = Field(default="", max_length=200)
    cohort: str = Field(default="", max_length=500)
    platform: str = Field(default="", max_length=160)
    instrument: str = Field(default="", max_length=160)
    reference_build: str = Field(default="", max_length=160)
    annotation_release: str = Field(default="", max_length=160)
    sample_count: int = Field(default=0, ge=0)
    feature_count: int = Field(default=0, ge=0)
    file_formats: list[str] = Field(default_factory=list, max_length=100)
    data_origin: str = "imported_external_result"
    consent_restrictions: str = Field(default="", max_length=4000)
    qc_status: str = Field(default="Not assessed", max_length=120)
    processing_status: str = Field(default="Registered", max_length=120)
    parent_dataset_id: str | None = None
    dataset_version: str = Field(default="1.0", min_length=1, max_length=120)
    provenance: dict[str, Any] = Field(default_factory=dict)
    is_synthetic: bool = False


class SampleBatchBody(StrictModel):
    samples: list[dict[str, Any]] = Field(min_length=1, max_length=10_000)


class WorkflowCreateBody(StrictModel):
    name: str = Field(min_length=1, max_length=240)
    nodes: list[dict[str, Any]] = Field(min_length=1, max_length=1000)
    edges: list[dict[str, Any]] = Field(default_factory=list, max_length=5000)
    template_key: str = Field(default="", max_length=120)
    version: str = Field(default="1.0", min_length=1, max_length=120)


class AnalysisRunBody(StrictModel):
    project_id: str
    module_id: str
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=100_000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    dataset_id: str | None = None
    is_synthetic: bool = False
    seed: int | None = None


class CandidateCreateBody(StrictModel):
    candidate_type: str
    identity: str = Field(min_length=1, max_length=500)
    data_source: str = Field(min_length=1, max_length=500)
    synonyms: list[str] = Field(default_factory=list, max_length=500)
    discovery_run_ids: list[str] = Field(default_factory=list, max_length=500)
    scores: dict[str, float] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)
    qc: dict[str, Any] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list, max_length=500)
    limitations: list[str] = Field(default_factory=list, max_length=500)
    owner: str = Field(default="", max_length=240)
    provenance: dict[str, Any] = Field(default_factory=dict)
    origin: str = "real_calculation"


class EvidenceCreateBody(StrictModel):
    source: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=1000)
    evidence_type: str
    identifier: str = Field(default="", max_length=500)
    study_type: str = Field(default="", max_length=200)
    direction: str = Field(default="Neutral", max_length=120)
    strength: str = Field(default="Unrated", max_length=120)
    independence: str = Field(default="Unknown", max_length=120)
    pmid: str = Field(default="", max_length=20)
    doi: str = Field(default="", max_length=500)
    database_name: str = Field(default="", max_length=200)
    database_version: str = Field(default="", max_length=120)
    sample_size: int | None = Field(default=None, ge=0)
    species: str = Field(default="", max_length=200)
    tissue: str = Field(default="", max_length=200)
    verification_state: str = Field(default="Unverified", max_length=120)
    limitations: list[str] = Field(default_factory=list, max_length=500)
    linked_candidates: list[str] = Field(default_factory=list, max_length=500)
    origin: str = "imported_external_result"
    provenance: dict[str, Any] = Field(default_factory=dict)


class HypothesisCreateBody(StrictModel):
    statement: str = Field(min_length=1, max_length=4000)
    null_hypothesis: str = Field(min_length=1, max_length=4000)
    biological_mechanism: str = Field(default="", max_length=8000)
    supporting_observations: list[str] = Field(min_length=1, max_length=1000)
    contradictory_observations: list[str] = Field(default_factory=list, max_length=1000)
    competing_hypotheses: list[str] = Field(default_factory=list, max_length=1000)
    predictions: list[str] = Field(default_factory=list, max_length=1000)
    falsification_criteria: list[str] = Field(min_length=1, max_length=1000)
    evidence_gaps: list[str] = Field(default_factory=list, max_length=1000)
    candidate_links: list[str] = Field(default_factory=list, max_length=1000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    novelty: str = Field(default="Unassessed", max_length=200)
    status: str = "Draft"
    origin: str = "hypothesis"
    provenance: dict[str, Any] = Field(default_factory=dict)


class RecommendationCreateBody(StrictModel):
    recommendation: dict[str, Any]
    dataset_id: str | None = None
    run_id: str | None = None
    candidate_id: str | None = None
    hypothesis_id: str | None = None
    state: str = "Generated"
    coverage: dict[str, float | None] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    origin: str = "rule_based_guidance"


class ExperimentCreateBody(StrictModel):
    assay: str = Field(min_length=1, max_length=500)
    validation_plan: dict[str, Any]
    acceptance_criteria: list[str] = Field(min_length=1, max_length=1000)
    failure_criteria: list[str] = Field(min_length=1, max_length=1000)
    recommendation_id: str | None = None
    candidate_id: str | None = None
    hypothesis_id: str | None = None
    protocol: str = Field(default="", max_length=12_000)
    sop: str = Field(default="", max_length=12_000)
    samples: list[str] = Field(default_factory=list, max_length=10_000)
    controls: list[str] = Field(default_factory=list, max_length=1000)
    replicates: dict[str, Any] = Field(default_factory=dict)
    randomization: str = Field(default="", max_length=2000)
    blinding: str = Field(default="", max_length=2000)
    expected_result: str = Field(default="", max_length=4000)
    origin: str = "user_entered_interpretation"
    provenance: dict[str, Any] = Field(default_factory=dict)


class ValidationResultBody(StrictModel):
    outcome: Literal["Supported", "Partially Supported", "Failed", "Inconclusive"]
    observed_result: str = Field(min_length=1, max_length=12_000)
    acceptance_met: bool
    qc_status: str = Field(min_length=1, max_length=200)
    interpretation: str = Field(min_length=1, max_length=12_000)
    deviations: list[str] = Field(default_factory=list, max_length=1000)


class ReportCreateBody(StrictModel):
    title: str = Field(min_length=1, max_length=500)
    selected_sections: list[str] | None = Field(default=None, max_length=100)


class ModelCreateBody(StrictModel):
    name: str = Field(min_length=1, max_length=240)
    version: str = Field(min_length=1, max_length=120)
    task: str = Field(min_length=1, max_length=240)
    owner: str = Field(min_length=1, max_length=240)
    artifact_path: str = Field(min_length=1, max_length=4000)
    project_id: str | None = None
    training_dataset_id: str | None = None
    validation_dataset_id: str | None = None
    feature_set: list[str] = Field(default_factory=list, max_length=100_000)
    preprocessing: dict[str, Any] = Field(default_factory=dict)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    random_seed: int | None = None
    performance: dict[str, Any] = Field(default_factory=dict)
    calibration: dict[str, Any] = Field(default_factory=dict)
    subgroup_performance: dict[str, Any] = Field(default_factory=dict)
    bias_analysis: dict[str, Any] = Field(default_factory=dict)
    ood_checks: dict[str, Any] = Field(default_factory=dict)
    drift_status: str = Field(default="Not assessed", max_length=120)
    explainability: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list, max_length=1000)
    approval_status: str = "Experimental"
    deployment_status: str = Field(default="Not deployed", max_length=120)


class SyntheticGenerateBody(StrictModel):
    module_id: str
    scenario: str
    size_preset: Literal["small", "medium", "large"] = "small"
    seed: int = 42
    project_id: str | None = None
    project_title: str = Field(default="Synthetic discovery lab", max_length=240)


class CohortBody(StrictModel):
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=200_000)
    criteria: list[dict[str, Any]] = Field(default_factory=list, max_length=1000)
    group_column: str | None = None


class PropensityBody(StrictModel):
    rows: list[dict[str, Any]] = Field(min_length=20, max_length=200_000)
    treatment_column: str
    covariates: list[str] = Field(min_length=1, max_length=500)
    seed: int = 42


class LongitudinalBody(StrictModel):
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=200_000)
    subject_column: str
    time_column: str
    value_column: str
    group_column: str | None = None


class SpatialBody(StrictModel):
    rows: list[dict[str, Any]] = Field(min_length=2, max_length=500_000)
    x_column: str = "x"
    y_column: str = "y"
    cell_id_column: str = "cell_id"
    cell_type_column: str = "cell_type"
    radius: float = Field(default=50, gt=0)
    maximum_edges: int = Field(default=100_000, ge=1, le=1_000_000)
