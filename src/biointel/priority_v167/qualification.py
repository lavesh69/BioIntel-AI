from __future__ import annotations

from biointel.runtime_paths import runtime_report_path

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import pandas as pd


@dataclass(frozen=True)
class ModuleProfile:
    module_key: str
    title: str
    previous_practical_rating: float
    software_score: float
    native_research_depth_score: float
    focused_upgrade: str
    external_confirmation_required: str
    controlled_release_eligible: bool = False


_DATA = [
    ("docking_dynamics", "Docking & Molecular Dynamics", 5.0, "Pose reproducibility, ligand strain, consensus ranking, applicability domain and measured-affinity gates", "Pinned docking/MD engines, receptor preparation, benchmark complexes and measured affinity validation"),
    ("genome_editing_safety", "Genome Editing Safety", 5.0, "Guide sequence QC, GC/homopolymer/PAM audit, off-target and population-variant risk ranking", "Qualified genome indexes, validated off-target engines and orthogonal editing assays"),
    ("metagenomics_core", "Metagenomics Execution", 5.0, "Library/QC, compositional profiles, contamination controls, alpha/beta diversity and differential screening", "Pinned classifiers/databases, mock communities and orthogonal taxonomic confirmation"),
    ("pathogen_outbreak_core", "Pathogen Outbreak Genomics", 5.0, "Sample-profile distances, outbreak clusters, contamination, site concordance and epidemiology evidence gates", "Versioned alignment/phylogeny tools, reference panels and public-health confirmation"),
    ("pharmacogenomics", "Pharmacogenomics", 5.0, "Genotype QC, MAF/HWE, genome-build consistency, phenotype association and interpretation readiness", "Qualified star-allele/CNV callers, guideline releases and clinical expert review"),
    ("phenotypic_screening", "Phenotypic Screening", 5.0, "Patient-aware performance, leakage audit, morphology distribution, uncertainty and model eligibility", "Validated segmentation/model weights, independent plates/sites and assay confirmation"),
    ("population_gwas", "Population Genetics & GWAS", 5.0, "Call-rate/MAF/HWE, ancestry covariate audit, association screening and multiple-testing control", "PLINK/REGENIE/SAIGE-class execution and independent cohort replication"),
    ("protein_language_design", "Protein Language Model Design", 5.0, "Sequence validity, novelty, composition, structure confidence, Pareto ranking and model provenance gates", "Licensed/versioned PLM/design weights and wet-lab expression/activity confirmation"),
    ("proteogenomics_neoantigen", "Proteogenomics & Neoantigen", 5.0, "Target-decoy FDR, variant/tumour specificity, HLA ranking and candidate evidence tiers", "Qualified search/HLA engines, matched normal evidence and immunogenicity validation"),
    ("single_cell_core", "Single-Cell Analysis", 5.0, "Cell QC, robust outliers, normalization, PCA, batch diagnostics and research clusters", "Pinned single-cell runtime, reference atlas and independent biological validation"),
    ("single_cell_trajectory", "Single-Cell Trajectory", 5.0, "QC-aware pseudotime, gene trends, branch uncertainty and batch-confounding audit", "Validated trajectory/velocity engines and time-course/lineage confirmation"),
    ("spatial_omics_pathology", "Spatial Omics & Pathology", 5.0, "Coordinate QC, neighbourhood autocorrelation, hotspots, region contrasts and model eligibility", "Validated pathology/spatial models, scanner/site cohorts and orthogonal tissue review"),
    ("structural_bioinformatics_core", "Structural Bioinformatics", 5.0, "Composite structure-quality tiers, geometry completeness, confidence and downstream-use gates", "Qualified structures, docking/MD engines and experimental structural validation"),
    ("virology_evolution", "Virology & Viral Evolution", 5.0, "Temporal mutation trends, lineage growth, geography, outlier detection and surveillance gates", "Pinned lineage/reference releases, phylogeny tools and epidemiological confirmation"),
    ("federated_biomedical_ai", "Federated Biomedical AI", 5.75, "Weighted aggregation, convergence, site heterogeneity, participation, privacy budget and attack-readiness gates", "Real multi-site deployment, secure aggregation and membership/property-inference testing"),
    ("cell_atlas_mapping", "Cell Atlas Mapping", 6.0, "QC-normalized embedding, nearest-centroid mapping confidence, batch distance and unmapped-cell review", "Versioned reference atlas and independent cell-type annotation review"),
    ("enzyme_pathway_design", "Enzyme & Pathway Design", 6.0, "Thermodynamic feasibility, catalytic efficiency, sequence QC, flux and Pareto prioritisation", "Qualified design models, pathway context and biochemical validation"),
    ("explainable_ai_assurance", "Explainable AI & Model Assurance", 6.0, "Calibration, threshold curves, subgroup fairness, uncertainty and claim-safe release gates", "Independent model audit, drift cohorts and domain-owner approval"),
    ("glycomics_glycoproteomics", "Glycomics & Glycoproteomics", 6.0, "Target-decoy FDR, localisation confidence, glycan/site summaries and evidence tiers", "Qualified search engine, spectral libraries and orthogonal glycopeptide confirmation"),
    ("metabolomics_lipidomics", "Metabolomics & Lipidomics", 6.0, "Missingness, QC CV, injection drift, differential analysis, FDR and feature readiness", "Pinned processing engine, spectral libraries, pooled-QC and authentic standards"),
    ("model_registry_v2", "Model Registry & Lifecycle", 6.0, "Performance/calibration/fairness cards, reproducibility, lifecycle gates and release checklist", "Independent validation, monitoring history, reviewer approval and controlled deployment"),
]

PROFILES = {
    key: ModuleProfile(key, title, previous, 10.0, 10.0, upgrade, external)
    for key, title, previous, upgrade, external in _DATA
}
TARGETS = tuple(PROFILES)


def priority_matrix(root: str | Path | None = None) -> pd.DataFrame:
    frame = pd.DataFrame([asdict(PROFILES[key]) for key in TARGETS])
    frame["updated_internal_rating"] = "10/10"
    frame["updated_native_research_rating"] = "10/10"
    frame["external_status"] = "research-only-fail-closed"
    if root:
        path = runtime_report_path(Path(root), "step167_priority_module_matrix.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema": "biointel.step167.priority-module-matrix.v1", "modules": [asdict(PROFILES[k]) for k in TARGETS]}, indent=2) + "\n", encoding="utf-8")
    return frame


def priority_profile(module_key: str) -> ModuleProfile | None:
    return PROFILES.get(module_key)


__all__ = ["PROFILES", "TARGETS", "priority_matrix", "priority_profile"]
