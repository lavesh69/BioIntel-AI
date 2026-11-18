from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from biointel.scientific_depth.profiles import MODULE_PROFILES


@dataclass(frozen=True)
class ConfirmationProfile:
    module_key: str
    module_title: str
    evidence_class: str
    requires_wet_lab: bool
    requires_prospective: bool
    requires_orthogonal: bool
    requires_independent_site: bool
    requires_instrument_qualification: bool
    requires_gpu_qualification: bool
    requires_expert_signoff: bool
    requires_formal_release_review: bool
    minimum_independent_sites: int
    minimum_qualified_experts: int
    minimum_confirmation_batches: int
    minimum_operating_runs: int
    software_framework_score: float
    scientific_boundary: str


_CLINICAL = {
    "cancer_genomics_core", "cell_therapy_cart", "clinical_biomarker_survival", "clinical_pharma_core",
    "clinical_trial_biomarker", "digital_pathology_foundation", "gene_therapy_vector", "pharmacogenomics",
    "pharmacovigilance_intelligence", "rare_variant_family", "spatial_medicine_tme", "synthetic_cohort_trial",
}
_INSTRUMENT = {
    "bioimage_microscopy", "bioprocess_fermentation", "digital_pathology_foundation", "flow_cytometry",
    "glycomics_glycoproteomics", "metabolomics_lipidomics", "organoid_3d", "spatial_omics_pathology",
}
_MODEL = {
    "biomedical_foundation_model_hub", "digital_pathology_foundation", "explainable_ai_assurance",
    "federated_biomedical_ai", "model_registry_v2", "offline_copilot_core", "offline_scientific_copilot_v2",
    "phenotypic_screening", "protein_language_design", "protein_ligand_codesign", "spatial_omics_pathology",
    "strain_microbiome",
}
_OPERATIONAL = {
    "background_job_engine", "background_jobs_core", "benchmark_validation_v2", "collaboration_review_v2",
    "cross_module_workspace", "data_lakehouse_v2", "document_intelligence_core", "evidence_citation_engine",
    "knowledge_graph_core", "plugin_marketplace_core", "plugin_marketplace_v2", "provenance_ledger_v2",
    "reference_lifecycle_v2", "store_readiness_core", "unified_report_builder", "universal_file_inspector",
    "workflow_builder_core", "workflow_builder_v2",
}
_GPU = {
    "bioimage_microscopy", "biomedical_foundation_model_hub", "digital_pathology_foundation", "docking_dynamics",
    "offline_copilot_core", "offline_scientific_copilot_v2", "organoid_3d", "phenotypic_screening",
    "protein_language_design", "protein_ligand_codesign", "single_cell_core", "single_cell_trajectory",
    "spatial_omics_pathology",
}


def _mentions(profile: Any, *terms: str) -> bool:
    text = " ".join([profile.boundary, *profile.validations]).lower()
    return any(term in text for term in terms)


def confirmation_profile(module_key: str) -> ConfirmationProfile:
    profile = MODULE_PROFILES[module_key]
    if module_key in _CLINICAL:
        evidence_class = "clinical-high-impact"
    elif module_key in _INSTRUMENT:
        evidence_class = "instrument-assisted-biological"
    elif module_key in _MODEL:
        evidence_class = "predictive-model"
    elif module_key in _OPERATIONAL:
        evidence_class = "software-operational"
    else:
        evidence_class = "biological-research"

    orthogonal = evidence_class in {"clinical-high-impact", "instrument-assisted-biological", "biological-research"} or _mentions(
        profile, "orthogonal", "experimental", "assay", "ground truth", "replication"
    )
    wet_lab = evidence_class in {"clinical-high-impact", "instrument-assisted-biological"} or _mentions(
        profile, "wet-lab", "experimental", "assay", "immunogenicity", "affinity", "standards"
    )
    prospective = evidence_class in {"clinical-high-impact", "predictive-model"} or _mentions(
        profile, "prospective", "external validation", "replication", "controlled experiments"
    )
    independent_site = evidence_class in {
        "clinical-high-impact", "instrument-assisted-biological", "predictive-model", "biological-research"
    }
    instrument = module_key in _INSTRUMENT
    expert = True
    formal_release = True
    if evidence_class == "clinical-high-impact":
        sites, experts, batches, runs = 2, 2, 2, 30
    elif evidence_class == "instrument-assisted-biological":
        sites, experts, batches, runs = 1, 1, 3, 20
    elif evidence_class == "predictive-model":
        sites, experts, batches, runs = 1, 1, 1, 20
    elif evidence_class == "biological-research":
        sites, experts, batches, runs = 1, 1, 2, 20
    else:
        sites, experts, batches, runs = 0, 1, 0, 30

    return ConfirmationProfile(
        module_key=module_key,
        module_title=profile.title,
        evidence_class=evidence_class,
        requires_wet_lab=wet_lab,
        requires_prospective=prospective,
        requires_orthogonal=orthogonal,
        requires_independent_site=independent_site,
        requires_instrument_qualification=instrument,
        requires_gpu_qualification=module_key in _GPU,
        requires_expert_signoff=expert,
        requires_formal_release_review=formal_release,
        minimum_independent_sites=sites,
        minimum_qualified_experts=experts,
        minimum_confirmation_batches=batches,
        minimum_operating_runs=runs,
        software_framework_score=10.0,
        scientific_boundary=profile.boundary,
    )


ALL_MODULES = tuple(sorted(MODULE_PROFILES))
PROFILES = {key: confirmation_profile(key) for key in ALL_MODULES}


def profile_matrix() -> pd.DataFrame:
    return pd.DataFrame([asdict(PROFILES[key]) for key in ALL_MODULES])


__all__ = ["ALL_MODULES", "PROFILES", "ConfirmationProfile", "confirmation_profile", "profile_matrix"]
