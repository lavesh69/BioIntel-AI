from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class TargetModuleProfile:
    module_key: str
    title: str
    page: str
    evidence_class: str
    workflow: tuple[str, ...]
    quality_gates: tuple[str, ...]
    required_outputs: tuple[str, ...]
    boundary: str


TARGET_PROFILES: dict[str, TargetModuleProfile] = {
    "amr_surveillance": TargetModuleProfile(
        "amr_surveillance", "AMR Genomic Surveillance & Resistance Intelligence",
        "pages/177_AMR_Genomic_Surveillance_Resistance_Intelligence.py", "public-health-high-impact",
        ("Read/isolate QC and species confirmation", "AMR determinant calling", "Drug-level evidence reconciliation", "Cluster and transmission screening", "Phenotype discordance review"),
        ("Negative and positive controls", "Pinned breakpoint standard", "Phenotypic AST attached", "Database release and checksum locked", "Public-health expert review"),
        ("Isolate QC table", "Drug-level concordance table", "Resistance evidence ledger", "Cluster review", "Release gate"),
        "Genomic AMR predictions are research support and do not replace phenotypic susceptibility testing or public-health interpretation.",
    ),
    "antibody_biologics": TargetModuleProfile(
        "antibody_biologics", "Antibody & Biologics Engineering",
        "pages/115_Antibody_and_Biologics_Engineering_Studio.py", "translational-biologics",
        ("Sequence and numbering validation", "Germline/humanness assessment", "Developability liability scan", "Structure/epitope evidence", "Candidate ranking and review"),
        ("Sequence identity and chain pairing", "Germline database pinned", "Assay-backed affinity", "Aggregation/stability evidence", "Biologics expert sign-off"),
        ("Numbered sequence", "Liability matrix", "Developability scorecard", "Evidence trace", "Candidate release gate"),
        "In-silico antibody prioritisation requires experimental binding, specificity, stability and developability confirmation.",
    ),
    "cancer_genomics_core": TargetModuleProfile(
        "cancer_genomics_core", "Cancer Genomics",
        "pages/81_Cancer_Genomics.py", "clinical-high-impact",
        ("Variant normalisation and assay QC", "Matched-normal/population filtering", "CNV/SV/fusion integration", "Clonality and signature screening", "Molecular review board package"),
        ("Genome build locked", "Assay validation and callable territory", "Matched normal or validated substitute", "Curated evidence release pinned", "Molecular pathology sign-off"),
        ("Variant QC report", "Prioritisation table", "TMB/signature audit", "Oncoprint and clonality views", "Clinical boundary gate"),
        "This module is not diagnostic software; clinical use requires accredited pipelines and qualified molecular-pathology review.",
    ),
    "cell_therapy_cart": TargetModuleProfile(
        "cell_therapy_cart", "Cell Therapy & CAR-T Engineering",
        "pages/180_Cell_Therapy_CART_Immune_Engineering_Studio.py", "translational-cell-therapy",
        ("Construct sequence and domain validation", "Specificity and cross-reactivity review", "Manufacturability assessment", "Potency/safety evidence integration", "Candidate governance"),
        ("Construct identity confirmed", "Off-target panel tested", "Potency assay qualified", "Manufacturing comparability attached", "Cell-therapy expert sign-off"),
        ("Construct map", "Liability and specificity matrix", "Potency evidence table", "Manufacturing risk register", "Release gate"),
        "CAR-T and cell-therapy designs require validated wet-lab potency, specificity, safety and manufacturing evidence.",
    ),
    "docking_dynamics": TargetModuleProfile(
        "docking_dynamics", "Molecular Docking & Dynamics",
        "pages/116_Molecular_Docking_and_Dynamics_Lab.py", "discovery-chemistry",
        ("Structure and ligand preparation", "Docking pose generation", "Pose QC and interaction review", "Dynamics/stability analysis", "Measured-affinity reconciliation"),
        ("Receptor preparation qualified", "Protocol and search space locked", "Positive/decoy controls", "Pose reproducibility", "Measured affinity attached"),
        ("Preparation audit", "Pose ensemble", "Interaction fingerprint", "Dynamics QC", "Research release gate"),
        "Docking and dynamics scores are hypotheses and require measured binding and experimental structural confirmation.",
    ),
    "enzyme_pathway_design": TargetModuleProfile(
        "enzyme_pathway_design", "Enzyme & Metabolic Pathway Design",
        "pages/144_Enzyme_Engineering_Metabolic_Pathway_Design_Studio.py", "synthetic-biology",
        ("Sequence/function validation", "Active-site and mutation design", "Pathway stoichiometry assessment", "Burden/toxicity review", "Experimental design package"),
        ("Reference sequence locked", "Activity assay defined", "Host context declared", "Flux assumptions sensitivity-tested", "Synthetic-biology expert review"),
        ("Mutation candidate table", "Pathway balance report", "Host-risk register", "Assay plan", "Release gate"),
        "Predicted enzyme and pathway designs require biochemical activity, host-fitness and product-quality confirmation.",
    ),
    "rare_variant_family": TargetModuleProfile(
        "rare_variant_family", "Rare Variant & Family Genetics",
        "pages/147_Rare_Variant_Burden_Family_Genetics_Lab.py", "clinical-high-impact",
        ("Pedigree/sample identity QC", "Variant normalisation and annotation", "Inheritance/segregation analysis", "Phenotype-driven prioritisation", "Family review package"),
        ("Pedigree relationships confirmed", "Genome build and references pinned", "Population frequencies qualified", "Segregation/orthogonal confirmation", "Clinical genetics sign-off"),
        ("Sample/pedigree QC", "Inheritance table", "Phenotype match evidence", "Candidate variant ledger", "Clinical boundary gate"),
        "Rare-variant findings require accredited confirmation, segregation review and qualified clinical-genetics interpretation.",
    ),
    "population_gwas": TargetModuleProfile(
        "population_gwas", "Population Genetics, GWAS & PRS",
        "pages/134_Population_Genetics_GWAS_Studio.py", "population-research",
        ("Sample/variant QC", "Relatedness and ancestry assessment", "Association modelling", "Calibration and sensitivity analysis", "Independent replication"),
        ("Phenotype definition locked", "Population structure controlled", "Relatedness handled", "Multiple-testing correction", "Independent cohort replication"),
        ("QC exclusions", "Ancestry/relatedness report", "Association results", "Calibration diagnostics", "Replication gate"),
        "GWAS and PRS outputs are population-dependent research results and must not be used for individual clinical decisions without validation.",
    ),
    "genome_editing_safety": TargetModuleProfile(
        "genome_editing_safety", "Genome Editing & Off-Target Safety",
        "pages/123_Genome_Editing_Safety_and_Off_Target_Validation_Lab.py", "translational-gene-editing",
        ("Guide/target validation", "Genome-wide candidate search", "Specificity ranking", "On-target consequence review", "Orthogonal assay package"),
        ("Genome build locked", "Whole-genome search engine qualified", "Relevant cell context declared", "Orthogonal off-target assay attached", "Genome-editing expert sign-off"),
        ("Guide QC", "Off-target candidate table", "Specificity scorecard", "Consequence review", "Release gate"),
        "Off-target predictions require cell-context-specific, orthogonal experimental confirmation before translational use.",
    ),
    "immunoinformatics_vaccine": TargetModuleProfile(
        "immunoinformatics_vaccine", "Immunoinformatics & Vaccine Design",
        "pages/114_Immunoinformatics_and_Vaccine_Design_Lab.py", "translational-immunology",
        ("Antigen sequence QC", "Epitope and HLA-binding prediction", "Conservancy/population coverage", "Safety and cross-reactivity review", "Experimental validation plan"),
        ("Predictor licence and release qualified", "HLA panel justified", "Pathogen diversity represented", "Safety screens complete", "Immunology expert sign-off"),
        ("Epitope table", "Population coverage", "Conservancy report", "Safety ledger", "Release gate"),
        "Predicted epitopes require immunological assay confirmation and do not establish vaccine efficacy or safety.",
    ),
    "long_read_core": TargetModuleProfile(
        "long_read_core", "Long-Read Assembly & T2T",
        "pages/95_Long_Read_Assembly_T2T_Studio.py", "genome-assembly",
        ("Read QC and contamination review", "Assembly graph generation", "Polishing and phasing", "Completeness/consensus validation", "T2T evidence package"),
        ("Platform/basecaller release locked", "Coverage and read-length thresholds", "Contamination controls", "BUSCO/Merqury qualified", "Assembly expert review"),
        ("Read QC", "Assembly statistics", "Graph/contig review", "Completeness/QV report", "Release gate"),
        "Assembly completeness and T2T claims require orthogonal evidence, contamination review and expert curation.",
    ),
    "long_read_epigenome": TargetModuleProfile(
        "long_read_epigenome", "Long-Read Epigenome",
        "pages/174_Long_Read_Epigenome_Methylation_Imprinting_Studio.py", "epigenomics-high-impact",
        ("Read/basecall/modification QC", "Alignment and modification calling", "Haplotype phasing", "DMR/imprinting analysis", "Orthogonal methylation review"),
        ("Basecaller/model release locked", "Coverage-aware thresholds", "Biological replicates", "Phasing evidence", "Orthogonal methylation assay"),
        ("Read/modification QC", "Methylation intervals", "Haplotype imbalance", "DMR/imprinting table", "Release gate"),
        "Modification and imprinting findings require model, coverage, replication, phasing and orthogonal assay confirmation.",
    ),
    "metagenomics_core": TargetModuleProfile(
        "metagenomics_core", "Metagenomics Pipeline",
        "pages/82_Metagenomics_Pipeline.py", "microbiome-research",
        ("Read/sample QC and controls", "Taxonomic profiling", "Functional profiling", "Compositional and diversity analysis", "Contamination-aware interpretation"),
        ("Negative controls", "Mock community", "Database releases pinned", "Batch/extraction effects reviewed", "Microbiome expert sign-off"),
        ("QC and contamination report", "Taxonomy table", "Functional table", "Diversity/differential analysis", "Release gate"),
        "Metagenomic associations are research findings and require contamination controls, qualified databases and independent confirmation.",
    ),
    "one_health_environmental": TargetModuleProfile(
        "one_health_environmental", "One Health & Environmental Genomics",
        "pages/131_One_Health_and_Environmental_Genomics_Center.py", "public-health-high-impact",
        ("Host/site/sample harmonisation", "Taxonomy and AMR profiling", "Temporal/geospatial cluster screening", "Source linkage assessment", "Epidemiology review"),
        ("Sampling design documented", "Environmental controls", "Databases pinned", "Confirmatory testing", "Epidemiology/public-health sign-off"),
        ("Sampling QC", "Taxonomy/AMR matrix", "Cluster timeline/map", "Source linkage evidence", "Release gate"),
        "One Health genomic signals require confirmatory testing and epidemiological interpretation before public-health action.",
    ),
    "pharmacogenomics": TargetModuleProfile(
        "pharmacogenomics", "Pharmacogenomics",
        "pages/117_Pharmacogenomics_and_Precision_Medicine_Board.py", "clinical-high-impact",
        ("Variant and sample QC", "Phasing/CNV-aware allele calling", "Diplotype inference", "Guideline evidence mapping", "Clinical review package"),
        ("Genome build/reference locked", "Phasing and CNV evidence", "Allele definitions pinned", "Guideline release qualified", "Pharmacogenomics expert sign-off"),
        ("Variant QC", "Allele/diplotype evidence", "Guideline trace", "Uncertainty and exceptions", "Clinical boundary gate"),
        "Pharmacogenomic output is research support and requires validated genotyping plus qualified clinical interpretation.",
    ),
    "proteogenomics_neoantigen": TargetModuleProfile(
        "proteogenomics_neoantigen", "Proteogenomics & Neoantigen Discovery",
        "pages/124_Proteogenomics_and_Neoantigen_Discovery_Studio.py", "translational-oncology",
        ("Variant/transcript/protein harmonisation", "Custom proteome construction", "Spectrum search and FDR control", "HLA presentation prediction", "Orthogonal validation plan"),
        ("Sample identity maintained", "Search database version locked", "Target-decoy/FDR qualified", "HLA typing confirmed", "Immunopeptidomics/assay confirmation"),
        ("Custom proteome manifest", "PSM/peptide FDR table", "Neoantigen ranking", "Evidence trace", "Release gate"),
        "Neoantigen candidates require orthogonal peptide/presentation and immunological validation before translational use.",
    ),
    "structural_variant_repeat": TargetModuleProfile(
        "structural_variant_repeat", "Structural Variant & Repeat Expansion",
        "pages/135_Structural_Variant_Repeat_Expansion_Lab.py", "clinical-high-impact",
        ("Read/sample QC", "SV/repeat calling", "Breakpoint and read-support review", "Annotation/segregation analysis", "Orthogonal confirmation package"),
        ("Genome build locked", "Caller versions and parameters pinned", "Read-level evidence", "Repeat catalogue qualified", "Orthogonal confirmation and expert sign-off"),
        ("QC report", "SV/repeat candidate table", "Breakpoint/read evidence", "Segregation/annotation ledger", "Clinical boundary gate"),
        "SV and repeat-expansion candidates require read-level review, orthogonal confirmation and qualified clinical interpretation.",
    ),
}

TARGET_MODULES: tuple[str, ...] = tuple(TARGET_PROFILES)


def profile_frame(keys: Iterable[str] | None = None) -> pd.DataFrame:
    selected = list(keys or TARGET_MODULES)
    return pd.DataFrame([asdict(TARGET_PROFILES[key]) for key in selected])


__all__ = ["TARGET_MODULES", "TARGET_PROFILES", "TargetModuleProfile", "profile_frame"]
