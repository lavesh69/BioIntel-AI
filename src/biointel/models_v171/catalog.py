from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class ModuleModelSpec:
    module_key: str
    module_title: str
    task_type: str
    package_strategy: str
    task_scope: str
    cohort_key: str | None
    acquisition_source: str
    source_url: str
    licence: str
    limitations: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


MODULE_MODEL_SPECS: tuple[ModuleModelSpec, ...] = (
    ModuleModelSpec(
        "biomedical_foundation_model_hub", "Biomedical Foundation Model Hub", "model-governance benchmark suite",
        "step162_verified_public_suite", "governance-benchmark-only", "step162_public_benchmarks",
        "Verified local Step 162 public benchmark suite", "local://data/step162/public_benchmarks", "mixed public dataset licences",
        "Five authentic public benchmark models validate lifecycle, provenance and evaluation plumbing; they are not biomedical foundation-model weights.",
    ),
    ModuleModelSpec(
        "digital_pathology_foundation", "Digital Pathology Foundation Model", "morphometric pathology classification",
        "wdbc_morphometry", "task-adjacent-baseline", "uci_wdbc_real",
        "UCI Wisconsin Diagnostic Breast Cancer", "https://archive.ics.uci.edu/dataset/17/breast+cancer+wisconsin+diagnostic", "CC BY 4.0",
        "Digitized FNA morphometry baseline only; not a whole-slide image foundation model and not a clinical diagnostic device.",
    ),
    ModuleModelSpec(
        "explainable_ai_assurance", "Explainable AI & Model Assurance", "calibrated model assurance",
        "wdbc_explainability", "task-specific-assurance", "uci_wdbc_real",
        "UCI Wisconsin Diagnostic Breast Cancer", "https://archive.ics.uci.edu/dataset/17/breast+cancer+wisconsin+diagnostic", "CC BY 4.0",
        "Validates deterministic calibration, leakage controls and coefficient-stability reporting; not evidence of clinical utility.",
    ),
    ModuleModelSpec(
        "federated_biomedical_ai", "Federated Biomedical AI", "federated learning benchmark",
        "wdbc_federated_simulation", "task-specific-simulated-sites", "uci_wdbc_real",
        "UCI Wisconsin Diagnostic Breast Cancer", "https://archive.ics.uci.edu/dataset/17/breast+cancer+wisconsin+diagnostic", "CC BY 4.0",
        "Uses deterministic same-source pseudo-sites to validate aggregation and heterogeneity controls; it is not a real multi-institution study.",
    ),
    ModuleModelSpec(
        "model_registry_v2", "Model Registry & Lifecycle", "model lifecycle and rollback",
        "step162_registry_lifecycle", "task-specific-governance", "step162_public_benchmarks",
        "Verified local Step 162 benchmark artifacts", "local://models/authentic_benchmarks", "mixed public dataset licences",
        "Validates immutable model cards, hashes, stage transitions and rollback; does not create domain deployment approval.",
    ),
    ModuleModelSpec(
        "offline_copilot_core", "Offline Copilot Core", "evidence retrieval",
        "verified_evidence_retrieval", "task-specific-retrieval", "verified_scientific_evidence_corpus",
        "BioIntel verified official-reference snapshots", "local://data/real_scientific_pack", "source-specific public licences",
        "Checksum-bound retrieval model only; not a generative LLM and not suitable for autonomous clinical advice.",
    ),
    ModuleModelSpec(
        "offline_scientific_copilot_v2", "Offline Scientific Copilot V2", "scientific evidence retrieval",
        "verified_evidence_retrieval", "task-specific-retrieval", "verified_scientific_evidence_corpus",
        "BioIntel verified official-reference snapshots", "local://data/real_scientific_pack", "source-specific public licences",
        "Citation retrieval benchmark only; generation quality, clinical safety and expert acceptance remain external.",
    ),
    ModuleModelSpec(
        "phenotypic_screening", "Phenotypic Screening", "morphometric phenotype classification",
        "wdbc_morphometry", "task-adjacent-baseline", "uci_wdbc_real",
        "UCI Wisconsin Diagnostic Breast Cancer", "https://archive.ics.uci.edu/dataset/17/breast+cancer+wisconsin+diagnostic", "CC BY 4.0",
        "Real morphometric phenotype baseline, not a high-content screening assay model and not externally validated across instruments.",
    ),
    ModuleModelSpec(
        "protein_language_design", "Protein Language Model Design", "protein sequence property prediction",
        "external_acquisition_required", "blocked-pending-task-cohort", None,
        "TAPE protein benchmark", "https://github.com/songlab-cal/tape", "MIT code; dataset licences are source-specific",
        "No suitable real task cohort or qualified protein-language weights are bundled; synthetic sequence libraries are ineligible.",
    ),
    ModuleModelSpec(
        "protein_ligand_codesign", "Protein–Ligand Co-Design", "protein-ligand affinity and design",
        "external_acquisition_required", "blocked-pending-task-cohort", None,
        "DeepDTA Davis/KIBA benchmark", "https://github.com/hkmztrk/DeepDTA", "source-specific research terms",
        "Requires measured affinity cohorts, chemically disjoint splits and qualified design/docking weights; generic tabular models are ineligible.",
    ),
    ModuleModelSpec(
        "spatial_omics_pathology", "Spatial Omics & Pathology", "spatial molecular pathology",
        "external_acquisition_required", "blocked-pending-task-cohort", None,
        "Public spatial transcriptomics/pathology cohorts", "https://www.10xgenomics.com/datasets", "provider/source-specific",
        "Requires spatial coordinates, expression matrices, histology and independent site validation; WDBC tabular morphology is not substituted.",
    ),
    ModuleModelSpec(
        "strain_microbiome", "Strain-Resolved Microbiome", "strain-level microbiome prediction",
        "external_acquisition_required", "blocked-pending-task-cohort", None,
        "curatedMetagenomicData / MicrobiomeHD", "https://waldronlab.io/curatedMetagenomicData/", "source-specific public study licences",
        "Requires raw or strain-resolved metagenomes, study metadata and leave-study-out validation; demo abundance tables are ineligible.",
    ),
)

SPEC_BY_KEY = {spec.module_key: spec for spec in MODULE_MODEL_SPECS}
APPLICABLE_MODULES = tuple(spec.module_key for spec in MODULE_MODEL_SPECS)

__all__ = ["ModuleModelSpec", "MODULE_MODEL_SPECS", "SPEC_BY_KEY", "APPLICABLE_MODULES"]
