from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Mapping, Sequence

DataOrigin = Literal["real", "synthetic", "demo", "mock", "test_fixture"]
EvidenceOrigin = Literal[
    "calculated_real",
    "calculated_synthetic",
    "external_verified",
    "external_unverified",
    "user_entered",
    "demo_fixture",
]

SYNTHETIC_ORIGINS = frozenset({"synthetic", "demo", "mock", "test_fixture"})
SYNTHETIC_BANNER_TITLE = "SYNTHETIC DEMO DATA"
SYNTHETIC_BANNER_TEXT = (
    "This workspace contains simulated data generated for demonstration and testing. "
    "It must not be used for scientific, clinical, diagnostic, regulatory, or publication decisions."
)
SYNTHETIC_WATERMARK = (
    "SYNTHETIC DEMO DATA - NOT FOR SCIENTIFIC, CLINICAL, REGULATORY, OR PUBLICATION USE"
)
ALLOWED_USES = ("demonstration", "testing", "training")
PROHIBITED_USES = (
    "scientific conclusion",
    "clinical decision",
    "diagnosis",
    "treatment",
    "regulatory submission",
    "publication claim",
)
GENERATOR_ID = "biointel.synthetic.workspace"
GENERATOR_VERSION = "Step220.0"

SIZE_PRESETS: dict[str, dict[str, int]] = {
    "small": {"samples": 24, "features": 40},
    "medium": {"samples": 100, "features": 500},
    "large": {"samples": 500, "features": 5000},
}

CONTROL_PRESETS: dict[str, dict[str, float]] = {
    "Clean Dataset": {"noise_level": 0.08, "missing_data_rate": 0.0, "duplicate_rate": 0.0, "outlier_rate": 0.0, "batch_effect_strength": 0.0, "effect_size": 1.6},
    "Typical Research Dataset": {"noise_level": 0.25, "missing_data_rate": 0.03, "duplicate_rate": 0.01, "outlier_rate": 0.02, "batch_effect_strength": 0.2, "effect_size": 1.0},
    "Noisy Dataset": {"noise_level": 0.75, "missing_data_rate": 0.08, "outlier_rate": 0.08, "effect_size": 0.7},
    "Low-Sample Dataset": {"noise_level": 0.35, "effect_size": 0.8, "sample_count": 8},
    "Batch-Confounded Dataset": {"batch_effect_strength": 1.5, "confounding_strength": 0.9, "effect_size": 0.9},
    "Missing-Metadata Dataset": {"missing_data_rate": 0.35, "noise_level": 0.3},
    "Class-Imbalanced Dataset": {"class_imbalance": 0.9, "effect_size": 1.0},
    "High-Outlier Dataset": {"outlier_rate": 0.25, "noise_level": 0.45},
    "Weak-Signal Dataset": {"effect_size": 0.25, "noise_level": 0.55},
    "Strong-Signal Dataset": {"effect_size": 2.5, "noise_level": 0.15},
    "Conflicting-Evidence Dataset": {"contradictory_evidence_level": 0.8, "effect_size": 0.8},
    "Pipeline-Failure Dataset": {"missing_data_rate": 0.45, "outlier_rate": 0.3, "noise_level": 1.0, "validation_success_probability": 0.05},
}

MODULE_SPECS: dict[str, dict[str, Any]] = {
    "sequencing_quality": {"title": "Sequencing Quality Demo", "scenarios": ("high_quality_run", "adapter_contamination", "severe_3prime_degradation", "high_duplication", "low_sequencing_depth", "gc_bias", "sample_contamination", "mixed_quality_cohort")},
    "alignment_mapping": {"title": "Alignment and Mapping Demo", "scenarios": ("good_mapping", "wrong_reference_build", "poor_quality_alignment", "high_multimapping", "incorrect_strandness", "index_missing", "low_coverage")},
    "differential_expression": {"title": "RNA-seq Differential Expression Demo", "scenarios": ("balanced_clean_design", "low_sample_size", "strong_batch_effect", "group_batch_confounding", "weak_biological_signal", "strong_biological_signal", "outlier_driven_result", "no_true_differential_expression")},
    "biomarker_discovery": {"title": "Biomarker Discovery Demo", "scenarios": ("stable_biomarker", "unstable_biomarker", "data_leakage", "overfitting", "class_imbalance", "poor_calibration", "strong_internal_weak_external", "multi_marker_panel_advantage", "subgroup_performance_failure")},
    "variant_prioritization": {"title": "Variant Prioritization Demo", "scenarios": ("high_priority_research_variant", "common_benign_like_variant", "conflicting_evidence", "missing_phenotype", "transcript_ambiguity", "compound_heterozygous", "de_novo", "low_quality_call")},
    "pathway_enrichment": {"title": "Pathway Enrichment Demo", "scenarios": ("strong_coherent_signal", "redundant_pathway_list", "incorrect_background_universe", "weak_enrichment", "contradictory_directionality", "no_significant_pathway")},
    "multi_omics": {"title": "Multi-Omics Demo", "scenarios": ("concordant_layers", "missing_layers", "mismatched_sample_ids", "discordant_signals", "layer_batch_effect", "known_latent_factor", "integrated_biomarker")},
    "single_cell": {"title": "Single-Cell Demo", "scenarios": ("clean_annotated_dataset", "doublet_heavy", "strong_ambient_rna", "batch_shifted", "over_clustered", "under_clustered", "rare_cell_population", "ambiguous_annotation", "noisy_trajectory")},
    "proteomics": {"title": "Proteomics Demo", "scenarios": ("clean_proteomics", "mar_missingness", "mnar_missingness", "protein_inference_ambiguity", "high_peptide_confidence", "low_peptide_confidence", "batch_drift", "differential_protein_signal", "failed_instrument_run")},
    "metabolomics": {"title": "Metabolomics Demo", "scenarios": ("clean_metabolomics", "batch_drift", "blank_contamination", "poor_peak_quality", "internal_standard_failure", "unknown_features", "strong_biological_signal", "weak_biological_signal")},
    "microbiome": {"title": "Microbiome Demo", "scenarios": ("clean_balanced_cohort", "contamination", "compositional_effects", "differential_abundance", "rare_taxa", "insufficient_depth", "batch_effects", "confounded_phenotype")},
    "structural_biology": {"title": "Structural Biology Demo", "scenarios": ("high_confidence_model", "low_confidence_region", "high_pae_uncertainty", "disordered_domain", "candidate_pocket", "mutation_impact", "low_structural_coverage")},
    "drug_target_discovery": {"title": "Drug and Target Discovery Demo", "scenarios": ("balanced_target_evidence", "strong_genetic_support", "essential_target_warning", "off_target_risk", "weak_druggability", "safety_flag", "validation_not_ready")},
    "experimental_design": {"title": "Experimental Design Demo", "scenarios": ("well_powered_design", "underpowered_design", "confounded_design", "missing_control", "incorrect_replicate_structure", "batch_imbalanced_design")},
    "statistical_analysis": {"title": "Statistical Analysis Demo", "scenarios": ("two_group_clean", "paired_analysis", "multi_group_analysis", "repeated_measures", "linear_regression", "logistic_regression", "survival_analysis", "longitudinal_analysis", "mixed_effects", "non_parametric", "non_normality", "heteroscedasticity", "missingness", "outliers", "multicollinearity", "separation", "non_proportional_hazards")},
    "literature_discovery": {"title": "Literature Discovery Demo", "scenarios": ("balanced_corpus", "supporting_studies", "contradictory_studies", "review_like_records", "low_quality_evidence", "duplicate_reports", "synthetic_retracted_record", "research_gaps")},
    "hypothesis_generation": {"title": "Hypothesis Generation Demo", "scenarios": ("testable_hypothesis", "contradictory_observations", "competing_hypotheses", "null_hypothesis", "weak_falsification", "multiple_mechanisms")},
    "laboratory_validation": {"title": "Laboratory Validation Demo", "scenarios": ("passing_validation", "failed_validation", "inconclusive_validation", "control_failure", "insufficient_replicates", "dynamic_range_failure")},
}

CLEAN_SCENARIOS: dict[str, str] = {
    module_id: str(spec["scenarios"][0]) for module_id, spec in MODULE_SPECS.items()
}

FAILURE_SCENARIOS: dict[str, str] = {
    "sequencing_quality": "adapter_contamination",
    "alignment_mapping": "wrong_reference_build",
    "differential_expression": "group_batch_confounding",
    "biomarker_discovery": "data_leakage",
    "variant_prioritization": "low_quality_call",
    "pathway_enrichment": "incorrect_background_universe",
    "multi_omics": "mismatched_sample_ids",
    "single_cell": "doublet_heavy",
    "proteomics": "failed_instrument_run",
    "metabolomics": "internal_standard_failure",
    "microbiome": "insufficient_depth",
    "structural_biology": "low_structural_coverage",
    "drug_target_discovery": "safety_flag",
    "experimental_design": "missing_control",
    "statistical_analysis": "separation",
    "literature_discovery": "duplicate_reports",
    "hypothesis_generation": "contradictory_observations",
    "laboratory_validation": "control_failure",
}

@dataclass(frozen=True)
class OriginMetadata:
    data_origin: DataOrigin = "synthetic"
    is_synthetic: bool = True
    synthetic_generator_id: str | None = GENERATOR_ID
    synthetic_generator_version: str | None = GENERATOR_VERSION
    synthetic_seed: int | None = None
    synthetic_scenario: str | None = None
    synthetic_created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SyntheticScenario:
    module_id: str
    scenario_id: str
    title: str
    is_failure: bool
    expected_behavior: str


@dataclass(frozen=True)
class SyntheticGenerationConfig:
    module_id: str
    scenario: str
    size_preset: Literal["small", "medium", "large"] = "small"
    sample_count: int | None = None
    feature_count: int | None = None
    group_count: int = 2
    effect_size: float = 1.0
    noise_level: float = 0.25
    missing_data_rate: float = 0.02
    duplicate_rate: float = 0.0
    outlier_rate: float = 0.02
    batch_effect_strength: float = 0.2
    class_imbalance: float = 0.5
    confounding_strength: float = 0.0
    signal_sparsity: float = 0.1
    measurement_error: float = 0.1
    seed: int = 42
    positive_control_strength: float = 1.5
    negative_control_strength: float = 0.0
    contradictory_evidence_level: float = 0.0
    validation_success_probability: float = 0.8
    preset_name: str = "Typical Research Dataset"

    def __post_init__(self) -> None:
        if self.module_id not in MODULE_SPECS:
            raise ValueError(f"Unsupported synthetic module: {self.module_id}")
        if self.size_preset not in SIZE_PRESETS:
            raise ValueError(f"Unsupported size preset: {self.size_preset}")
        if self.scenario not in MODULE_SPECS[self.module_id]["scenarios"]:
            raise ValueError(f"Unsupported scenario '{self.scenario}' for {self.module_id}")
        samples, features = self.dimensions
        if not 4 <= samples <= 2000:
            raise ValueError("sample_count must be between 4 and 2000")
        if not 1 <= features <= 10000:
            raise ValueError("feature_count must be between 1 and 10000")
        if samples * features > 10_000_000:
            raise ValueError("Requested dataset exceeds the 10,000,000-cell safety limit")
        for name in ("missing_data_rate", "duplicate_rate", "outlier_rate", "class_imbalance", "signal_sparsity", "contradictory_evidence_level", "validation_success_probability"):
            value = float(getattr(self, name))
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.group_count < 2 or self.group_count > 20:
            raise ValueError("group_count must be between 2 and 20")

    @property
    def dimensions(self) -> tuple[int, int]:
        preset = SIZE_PRESETS[self.size_preset]
        return int(self.sample_count or preset["samples"]), int(self.feature_count or preset["features"])

    @property
    def memory_warning(self) -> str | None:
        if self.size_preset == "large":
            samples, features = self.dimensions
            estimate_mb = samples * features * 8 / (1024 * 1024)
            return f"Large preset: approximately {estimate_mb:.1f} MiB for one dense numeric matrix before overhead. Generation uses bounded chunks where possible."
        return None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["resolved_sample_count"], payload["resolved_feature_count"] = self.dimensions
        return payload

    @classmethod
    def from_preset(cls, module_id: str, scenario: str, size_preset: str, preset_name: str, seed: int = 42, **overrides: Any) -> "SyntheticGenerationConfig":
        values = dict(CONTROL_PRESETS.get(preset_name, CONTROL_PRESETS["Typical Research Dataset"]))
        values.update({key: value for key, value in overrides.items() if value is not None})
        return cls(module_id=module_id, scenario=scenario, size_preset=size_preset, preset_name=preset_name, seed=seed, **values)


@dataclass(frozen=True)
class SyntheticTruthRecord:
    truth_id: str
    truth_type: str
    entity_id: str
    expected_value: Any
    tolerance: float | None = None
    hidden_by_default: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SyntheticValidationResult:
    validation_id: str
    check: str
    passed: bool
    observed: Any
    expected: Any
    detail: str
    data_origin: DataOrigin = "synthetic"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SyntheticDatasetManifest:
    generator_id: str
    generator_version: str
    module_id: str
    seed: int
    scenario: str
    sample_count: int
    feature_count: int
    injected_signals: list[dict[str, Any]]
    injected_qc_issues: list[dict[str, Any]]
    expected_findings: list[str]
    expected_warnings: list[str]
    created_at: str
    data_origin: DataOrigin = "synthetic"
    is_synthetic: bool = True
    synthetic_generator_id: str = GENERATOR_ID
    synthetic_generator_version: str = GENERATOR_VERSION
    allowed_use: tuple[str, ...] = ALLOWED_USES
    prohibited_use: tuple[str, ...] = PROHIBITED_USES
    file_hashes: dict[str, str] = field(default_factory=dict)
    expected_behavior: str = "Demo workflow should preserve synthetic provenance."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SyntheticGeneratedDataset:
    config: SyntheticGenerationConfig
    manifest: SyntheticDatasetManifest
    tables: dict[str, Any]
    ground_truth: list[SyntheticTruthRecord]
    expected_qc_findings: list[dict[str, Any]]
    expected_recommendations: list[dict[str, Any]]
    tutorial_notes: list[str]
    validation_results: list[SyntheticValidationResult] = field(default_factory=list)

    @property
    def data_origin(self) -> str:
        return "synthetic"

    @property
    def is_synthetic(self) -> bool:
        return True

    def recommendation_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tables": self.tables,
            "data_origin": "synthetic",
            "is_synthetic": True,
            "synthetic_generator_id": self.manifest.generator_id,
            "synthetic_generator_version": self.manifest.generator_version,
            "synthetic_seed": self.config.seed,
            "synthetic_scenario": self.config.scenario,
            "synthetic_created_at": self.manifest.created_at,
            "expected_qc_findings": self.expected_qc_findings,
            "synthetic_truth_count": len(self.ground_truth),
            "analysis_status": "complete",
            "qc_status": "warning" if self.expected_qc_findings else "pass",
        }
        for name, table in self.tables.items():
            payload[name] = table
        return payload


class SyntheticSafetyError(ValueError):
    pass


class SyntheticGenerationCancelled(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def is_synthetic_origin(origin: Any) -> bool:
    return str(origin or "").strip().lower() in SYNTHETIC_ORIGINS


def payload_contains_synthetic(value: Any, *, _depth: int = 0) -> bool:
    if _depth > 12:
        return False
    if isinstance(value, Mapping):
        if bool(value.get("is_synthetic")) or is_synthetic_origin(value.get("data_origin")):
            return True
        return any(payload_contains_synthetic(item, _depth=_depth + 1) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(payload_contains_synthetic(item, _depth=_depth + 1) for item in list(value)[:1000])
    return False


def derive_output_origin(*inputs: Any) -> tuple[DataOrigin, str]:
    has_synthetic = any(payload_contains_synthetic(item) for item in inputs)
    has_real = any(isinstance(item, Mapping) and str(item.get("data_origin", "")).lower() == "real" for item in inputs)
    if has_synthetic and has_real:
        return "synthetic", "Mixed-Origin Evaluation"
    if has_synthetic:
        return "synthetic", "Synthetic Demo Data"
    return "real", "Real Input Evaluation"


def origin_fields(config: SyntheticGenerationConfig | None = None) -> dict[str, Any]:
    return {
        "data_origin": "synthetic",
        "is_synthetic": True,
        "synthetic_generator_id": GENERATOR_ID,
        "synthetic_generator_version": GENERATOR_VERSION,
        "synthetic_seed": config.seed if config else None,
        "synthetic_scenario": config.scenario if config else None,
        "synthetic_created_at": utc_now(),
        "allowed_use": list(ALLOWED_USES),
        "prohibited_use": list(PROHIBITED_USES),
    }


def enforce_origin_transition(existing: Mapping[str, Any], requested_origin: str, *, synthetic_inputs_replaced: bool = False) -> None:
    if payload_contains_synthetic(existing) and requested_origin == "real" and not synthetic_inputs_replaced:
        raise SyntheticSafetyError("Synthetic status cannot be removed until every synthetic input is replaced with verified real input.")


def enforce_project_merge(source: Mapping[str, Any], destination: Mapping[str, Any], *, explicitly_confirmed_mixed_evaluation: bool = False) -> str:
    source_synthetic = payload_contains_synthetic(source)
    destination_real = str(destination.get("data_origin", "real")).lower() == "real" and not payload_contains_synthetic(destination)
    if source_synthetic and destination_real and not explicitly_confirmed_mixed_evaluation:
        raise SyntheticSafetyError("Synthetic datasets cannot be merged into real projects by default.")
    return "Mixed-Origin Evaluation" if source_synthetic and destination_real else "Synthetic Demo Data" if source_synthetic else "Real Input Evaluation"


def enforce_evidence_assignment(evidence: Mapping[str, Any], recommendation: Mapping[str, Any]) -> None:
    evidence_origin = str(evidence.get("evidence_origin", "")).lower()
    synthetic_evidence = evidence_origin in {"calculated_synthetic", "demo_fixture"} or payload_contains_synthetic(evidence)
    if synthetic_evidence and not payload_contains_synthetic(recommendation):
        raise SyntheticSafetyError("Synthetic evidence cannot be attached to or raise the grade of a real recommendation.")
    if synthetic_evidence and evidence_origin in {"external_verified", "calculated_real"}:
        raise SyntheticSafetyError("Synthetic evidence cannot be reclassified as verified external or calculated real evidence.")


def enforce_validation_assignment(validation: Mapping[str, Any], recommendation: Mapping[str, Any]) -> None:
    synthetic_validation = payload_contains_synthetic(validation) or str(validation.get("evidence_origin", "")).lower() in {"calculated_synthetic", "demo_fixture"}
    if synthetic_validation and not payload_contains_synthetic(recommendation):
        raise SyntheticSafetyError("Synthetic validation results cannot validate a real recommendation.")


def contains_forbidden_identifier(value: str) -> bool:
    text = str(value)
    patterns = (
        r"\bPMID\s*[:#]?\s*\d{5,}\b",
        r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b",
        r"\bNCT\d{8}\b",
    )
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


__all__ = [
    "ALLOWED_USES",
    "CONTROL_PRESETS",
    "DataOrigin",
    "EvidenceOrigin",
    "CLEAN_SCENARIOS",
    "FAILURE_SCENARIOS",
    "GENERATOR_ID",
    "GENERATOR_VERSION",
    "MODULE_SPECS",
    "OriginMetadata",
    "PROHIBITED_USES",
    "SIZE_PRESETS",
    "SYNTHETIC_BANNER_TEXT",
    "SYNTHETIC_BANNER_TITLE",
    "SYNTHETIC_WATERMARK",
    "SyntheticDatasetManifest",
    "SyntheticGeneratedDataset",
    "SyntheticGenerationCancelled",
    "SyntheticGenerationConfig",
    "SyntheticSafetyError",
    "SyntheticScenario",
    "SyntheticTruthRecord",
    "SyntheticValidationResult",
    "contains_forbidden_identifier",
    "derive_output_origin",
    "enforce_evidence_assignment",
    "enforce_origin_transition",
    "enforce_project_merge",
    "enforce_validation_assignment",
    "is_synthetic_origin",
    "origin_fields",
    "payload_contains_synthetic",
    "utc_now",
]
