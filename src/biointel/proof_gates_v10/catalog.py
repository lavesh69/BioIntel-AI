from __future__ import annotations

"""The P0/P1 priority portfolio and honest four-proof-gate requirements."""

from dataclasses import dataclass

GATE_ORDER = (
    "qualified_runtime_data",
    "real_benchmark",
    "independent_confirmation",
    "governance_release",
)

GATE_LABELS = {
    "qualified_runtime_data": "Qualified runtime / data",
    "real_benchmark": "Real benchmark",
    "independent_confirmation": "Independent confirmation",
    "governance_release": "Governance / release",
}

P0_MODULE_KEYS: tuple[str, ...] = (
    "protein_language_design",
    "protein_ligand_codesign",
    "strain_microbiome",
    "spatial_omics_pathology",
    "phenotypic_screening",
    "amr_surveillance",
    "antibody_biologics",
    "cancer_genomics_core",
    "cell_therapy_cart",
    "docking_dynamics",
    "enzyme_pathway_design",
    "rare_variant_family",
    "population_gwas",
    "genome_editing_safety",
    "immunoinformatics_vaccine",
    "long_read_core",
    "long_read_epigenome",
    "metagenomics_core",
    "one_health_environmental",
    "pharmacogenomics",
    "proteogenomics_neoantigen",
    "structural_variant_repeat",
    "digital_pathology_foundation",
    "offline_copilot_core",
    "offline_scientific_copilot_v2",
)

P1_MODULE_KEYS: tuple[str, ...] = (
    "bioimage_microscopy",
    "organoid_3d",
    "cell_atlas_mapping",
    "epigenomics_chromatin",
    "glycomics_glycoproteomics",
    "metabolomics_lipidomics",
    "multiomics_harmonization",
    "pathogen_outbreak_core",
    "virology_evolution",
    "pangenome_core",
    "pangenome_population_medicine",
    "rna_isoform_splicing",
    "single_cell_core",
    "single_cell_trajectory",
    "single_cell_long_read_isoforms",
    "spatial_medicine_tme",
    "structural_bioinformatics_core",
    "biomedical_foundation_model_hub",
    "federated_biomedical_ai",
    "explainable_ai_assurance",
    "model_registry_ml_lifecycle",
    "multiomics_biomarker_discovery",
    "clinical_biomarker_survival",
    "clinical_trial_biomarker",
    "bioprocess_fermentation",
    "causal_inference_perturbation",
    "clinical_pharma_validation",
    "epitranscriptomics",
    "flow_cytometry",
    "gene_therapy_vector",
    "host_pathogen_interaction",
    "autonomous_laboratory_planner",
    "longitudinal_multiomics",
    "pharmacovigilance",
    "synthetic_cohort_trial",
    "synthetic_biology_circuit",
    "synthetic_data_privacy",
)


# A small group of historical page keys were renamed in the final module
# catalogue.  Keep the priority portfolio keyed by the page the user opens,
# while routing execution, manifests and downstream workspaces to one stable
# canonical key.  This prevents the same module from silently accumulating
# split evidence or execution records under two different names.
EXECUTION_KEY_ALIASES: dict[str, str] = {
    "model_registry_ml_lifecycle": "model_registry_v2",
    "multiomics_biomarker_discovery": "multiomics_biomarker_core",
    "causal_inference_perturbation": "causal_perturbation",
    "clinical_pharma_validation": "clinical_pharma_core",
    "autonomous_laboratory_planner": "autonomous_lab_planner",
    "pharmacovigilance": "pharmacovigilance_intelligence",
    "synthetic_biology_circuit": "synthetic_biology_core",
}


@dataclass(frozen=True)
class PriorityModule:
    module_key: str
    title: str
    priority: str
    runtime_data: str
    benchmark: str
    confirmation: str
    governance: str

    def gate_requirements(self) -> dict[str, str]:
        return {
            "qualified_runtime_data": self.runtime_data,
            "real_benchmark": self.benchmark,
            "independent_confirmation": self.confirmation,
            "governance_release": self.governance,
        }


_P0_FOCUS: dict[str, tuple[str, str, str]] = {
    "protein_language_design": (
        "Qualify ProteinMPNN and RFdiffusion with approved model weights plus BindingDB and UniProt/Swiss-Prot provenance.",
        "Run a blinded design benchmark with structure-validation controls.",
        "Obtain expression/function evidence and an independent design review.",
    ),
    "protein_ligand_codesign": (
        "Qualify ColabFold, ProteinMPNN, RFdiffusion and Vina with BindingDB/ChEMBL and validated weights.",
        "Use benchmark complexes and locked affinity controls.",
        "Obtain prospective binding/affinity assay evidence and independent chemistry review.",
    ),
    "strain_microbiome": (
        "Qualify Bracken, HUMAnN and Kraken2 with ChocoPhlAn, UniRef90 and Kraken database versions.",
        "Use mock-community truth sets with contamination controls.",
        "Confirm reproducibility using independent cohort or laboratory evidence.",
    ),
    "spatial_omics_pathology": (
        "Qualify Cellpose and OpenSlide with locked annotated slides and scanner/stain provenance.",
        "Measure segmentation QC and scanner/stain robustness on held-out slides.",
        "Obtain pathology-expert review and multi-site validation.",
    ),
    "phenotypic_screening": (
        "Qualify Cellpose, StarDist and ChEMBL inputs with plate-control lineage.",
        "Run dose-response QC and replicate screening benchmarks.",
        "Obtain orthogonal biological confirmation.",
    ),
    "amr_surveillance": (
        "Qualify AMRFinderPlus, BCFtools, Kraken2, Minimap2 and AMRFinder/CARD/ResFinder database versions.",
        "Use phenotype/AST concordance with locked samples.",
        "Confirm across independent sites and review epidemiology interpretation.",
    ),
    "antibody_biologics": (
        "Qualify ANARCI, IgBLAST and validated germline reference assets.",
        "Benchmark binding, expression, developability and immunogenicity inputs.",
        "Attach independent assay evidence for candidate confirmation.",
    ),
    "cancer_genomics_core": (
        "Qualify BCFtools, VEP, GRCh38, ClinVar and VEP cache versions.",
        "Use locked variant truth sets with reproducible interpretation.",
        "Obtain orthogonal molecular confirmation and clinical-governance review.",
    ),
    "cell_therapy_cart": (
        "Qualify ANARCI, IgBLAST and validated germline assets.",
        "Use locked functional, specificity, safety and manufacturability controls.",
        "Obtain relevant functional and safety confirmation.",
    ),
    "docking_dynamics": (
        "Qualify GROMACS, OpenMM and Vina with BindingDB/ChEMBL provenance.",
        "Benchmark against curated complexes and measured-affinity controls.",
        "Obtain prospective assay validation for decision-relevant claims.",
    ),
    "enzyme_pathway_design": (
        "Qualify ProteinMPNN with GO, Reactome and UniProt reference provenance.",
        "Benchmark enzyme kinetics and pathway-flux controls.",
        "Obtain organism-specific validation evidence.",
    ),
    "rare_variant_family": (
        "Qualify BCFtools, VEP, WhatsHap, GRCh38, ClinVar, gnomAD, HPO and VEP cache versions.",
        "Use pedigree-aware truth samples and locked interpretation controls.",
        "Obtain segregation evidence and independent interpretation review.",
    ),
    "population_gwas": (
        "Qualify PLINK2, REGENIE, SAIGE and GRCh38/gnomAD reference provenance.",
        "Use ancestry-aware QC, calibration and pre-specified statistics.",
        "Obtain replication-cohort evidence.",
    ),
    "genome_editing_safety": (
        "Qualify BCFtools, BLASTn, Bowtie and GRCh38 reference provenance.",
        "Use validated on/off-target benchmark panels.",
        "Obtain orthogonal sequencing confirmation.",
    ),
    "immunoinformatics_vaccine": (
        "Document NetMHCpan/NetMHCIIpan availability and licensed-data permissions; provider-controlled tools remain manual.",
        "Use peptide-binding benchmark data within authorised licence scope.",
        "Obtain peptide-binding and T-cell assay validation.",
    ),
    "long_read_core": (
        "Qualify BUSCO, Flye, Hifiasm, Merqury and required BUSCO lineage assets.",
        "Use known truth genomes with reproducible assembly benchmarks.",
        "Obtain replicate-sequencing and assembly confirmation.",
    ),
    "long_read_epigenome": (
        "Qualify Dorado, Modkit, SAMtools and WhatsHap with approved Dorado model provenance.",
        "Use methylation control materials and locked quality metrics.",
        "Obtain orthogonal methylation-assay confirmation.",
    ),
    "metagenomics_core": (
        "Qualify Bracken, HUMAnN and Kraken2 with ChocoPhlAn, UniRef90 and Kraken database versions.",
        "Use mock communities and contamination-control benchmarks.",
        "Obtain independent cohort replication.",
    ),
    "one_health_environmental": (
        "Qualify Bracken, HUMAnN, Kraken2 and Minimap2 with CARD and microbiome references.",
        "Use cross-source proficiency panels and traceable epidemiology inputs.",
        "Obtain independent epidemiology review.",
    ),
    "pharmacogenomics": (
        "Qualify BCFtools, VEP, WhatsHap, ClinVar, gnomAD, GRCh38 and VEP references.",
        "Use locked genotype–phenotype benchmark sets.",
        "Obtain replication and expert pharmacogenomics review.",
    ),
    "proteogenomics_neoantigen": (
        "Qualify BCFtools, Comet, MSGF+ plus UniProt and approved MHC reference assets.",
        "Use FDR-controlled benchmark data and targeted-MS controls.",
        "Obtain immunogenicity confirmation where claimed.",
    ),
    "structural_variant_repeat": (
        "Qualify BCFtools, ExpansionHunter, SAMtools, Sniffles, GRCh38, repeat catalogue and VEP assets.",
        "Use truth samples with locked calling criteria.",
        "Obtain PCR or long-read confirmation.",
    ),
    "digital_pathology_foundation": (
        "Qualify Cellpose, OpenSlide and multi-site annotated image provenance.",
        "Benchmark scanner generalisation against held-out sites.",
        "Obtain pathologist agreement and independent review.",
    ),
    "offline_copilot_core": (
        "Qualify llama.cpp plus licensed local-model weights and data-security controls.",
        "Run a domain benchmark, hallucination tests and red-team evaluation.",
        "Obtain an expert-reviewed answer set and security audit.",
    ),
    "offline_scientific_copilot_v2": (
        "Qualify llama.cpp plus licensed local-model weights and data-security controls.",
        "Run a domain benchmark, hallucination tests and red-team evaluation.",
        "Obtain an expert-reviewed answer set and security audit.",
    ),
}

_P1_FOCUS: dict[str, tuple[str, str, str]] = {
    "bioimage_microscopy": ("Qualify Cellpose/StarDist and annotated multi-site imaging provenance.", "Use inter-rater and imaging-panel benchmarks.", "Obtain biological replicate validation."),
    "organoid_3d": ("Qualify Cellpose/StarDist and annotated multi-site imaging provenance.", "Use inter-rater and imaging-panel benchmarks.", "Obtain biological replicate validation."),
    "cell_atlas_mapping": ("Qualify trusted atlas reference and label-transfer configuration.", "Benchmark batch effects and label transfer on held-out cells.", "Obtain independent annotation evaluation."),
    "epigenomics_chromatin": ("Qualify BWA, deepTools, MACS2, SAMtools and reference provenance.", "Use replicate and spike-in QC controls.", "Obtain orthogonal chromatin-assay confirmation."),
    "glycomics_glycoproteomics": ("Qualify OpenMS and authentic spectral-library provenance.", "Use pooled-QC and spike-in benchmark controls.", "Obtain targeted confirmation."),
    "metabolomics_lipidomics": ("Qualify OpenMS and authentic spectral-library provenance.", "Use pooled-QC and spike-in benchmark controls.", "Obtain targeted confirmation."),
    "multiomics_harmonization": ("Qualify GO/Reactome references and versioned integration inputs.", "Benchmark cross-site batch correction.", "Obtain independent reproducibility evidence."),
    "pathogen_outbreak_core": ("Qualify BCFtools, IQ-TREE and MAFFT with lineage truth provenance.", "Use proficiency-panel and lineage-truth benchmarks.", "Obtain epidemiology review."),
    "virology_evolution": ("Qualify BCFtools, IQ-TREE and MAFFT with lineage truth provenance.", "Use proficiency-panel and lineage-truth benchmarks.", "Obtain epidemiology review."),
    "pangenome_core": ("Qualify GraphAligner, Minigraph, ODGI and VG with reference provenance.", "Use known-genome truth sets and bias testing.", "Obtain independent replication."),
    "pangenome_population_medicine": ("Qualify GraphAligner, Minigraph, ODGI and VG with reference provenance.", "Use known-genome truth sets and bias testing.", "Obtain independent replication."),
    "rna_isoform_splicing": ("Qualify STAR and MAFFT with controlled isoform reference inputs.", "Use synthetic isoform controls and locked metrics.", "Obtain orthogonal transcript validation."),
    "single_cell_core": ("Qualify Scanpy and trusted cell-type reference assets.", "Use label truth, batch robustness and donor-aware controls.", "Obtain independent biological replication."),
    "single_cell_trajectory": ("Qualify Scanpy, CellRank and scVelo with trusted reference assets.", "Use label truth, batch robustness and trajectory controls.", "Obtain independent biological replication."),
    "single_cell_long_read_isoforms": ("Qualify Minimap2 and SAMtools with spike-in and isoform truth assets.", "Use locked isoform truth-set benchmarks.", "Obtain orthogonal validation."),
    "spatial_medicine_tme": ("Qualify Cellpose, OpenSlide and Scanpy with spatial cohort provenance.", "Use spatially annotated cohort benchmarks.", "Obtain pathology review."),
    "structural_bioinformatics_core": ("Qualify GROMACS, OpenMM and Vina with reference provenance.", "Use experimental structure/binding benchmarks.", "Obtain independent assay evidence."),
    "biomedical_foundation_model_hub": ("Qualify model-card, licence and provenance controls.", "Run a domain benchmark and safety/hallucination suite.", "Obtain independent review."),
    "federated_biomedical_ai": ("Qualify actual multi-site federation and security controls.", "Run site-specific calibration and privacy testing.", "Obtain independent operational audit."),
    "explainable_ai_assurance": ("Qualify explainability configuration and data provenance.", "Use stability, counterfactual and failure-case benchmarks.", "Obtain clinician/scientist usability evidence."),
    "model_registry_ml_lifecycle": ("Qualify immutable model/data lineage and reproducible rerun controls.", "Run independent rerun and lineage-integrity benchmarks.", "Obtain registry audit and release sign-off."),
    "multiomics_biomarker_discovery": ("Qualify frozen cohort lineage and calibration controls.", "Use blinded hold-out benchmark data.", "Obtain independent-site and prospective validation where intended."),
    "clinical_biomarker_survival": ("Qualify frozen cohort lineage and calibration controls.", "Use blinded hold-out benchmark data.", "Obtain independent-site and prospective validation where intended."),
    "clinical_trial_biomarker": ("Qualify frozen cohort lineage and calibration controls.", "Use blinded hold-out benchmark data.", "Obtain independent-site and prospective validation where intended."),
    "bioprocess_fermentation": ("Qualify calibrated sensor and process configuration records.", "Use scale-down/scale-up replicate benchmarks and acceptance criteria.", "Obtain independent process review."),
    "causal_inference_perturbation": ("Document pre-specified causal assumptions and data provenance.", "Use negative controls and sensitivity analyses.", "Obtain external replication."),
    "clinical_pharma_validation": ("Qualify verified evidence sources and intended-use boundaries.", "Use human-safety review and calibrated validation controls.", "Obtain independent-site confirmation; do not make autonomous clinical claims."),
    "epitranscriptomics": ("Qualify assay-control and cohort provenance.", "Use replicate-cohort benchmark controls.", "Obtain orthogonal mark validation."),
    "flow_cytometry": ("Qualify instrument calibration, compensation and FMO controls.", "Use gating-reproducibility benchmarks.", "Obtain independent laboratory comparison."),
    "gene_therapy_vector": ("Qualify vector QC, potency and safety evidence provenance.", "Use off-target and biodistribution control benchmarks.", "Obtain expert review."),
    "host_pathogen_interaction": ("Qualify controlled datasets and biological replicate provenance.", "Use locked host/pathogen benchmark controls.", "Obtain orthogonal host/pathogen assay evidence."),
    "autonomous_laboratory_planner": ("Qualify simulation, constraint and human-approval audit controls.", "Use safety and constraint-test benchmarks.", "Obtain safety review; never authorise an experiment automatically."),
    "longitudinal_multiomics": ("Qualify repeated-measures data provenance and missingness controls.", "Use temporal validation and longitudinal benchmarks.", "Obtain independent cohort evidence."),
    "pharmacovigilance": ("Qualify curated case-data provenance and safety-review workflow.", "Use signal-detection benchmarks and causality-review controls.", "Obtain independent safety review."),
    "synthetic_cohort_trial": ("Qualify synthetic-data labelling, privacy and utility controls.", "Use privacy, bias and utility testing.", "Keep visibly synthetic; it is never real clinical evidence."),
    "synthetic_biology_circuit": ("Qualify containment/biosafety constraints and organism context.", "Use defined circuit benchmark controls.", "Obtain organism-specific bench validation and independent review."),
    "synthetic_data_privacy": ("Qualify privacy-attack and disclosure-risk audit controls.", "Use privacy, bias and utility test suites.", "Obtain external privacy review."),
}

_GOVERNANCE = (
    "Attach SOP, risk register, provenance record, named reviewer/sign-off metadata and a formal release-review decision. "
    "Local staging never grants controlled release."
)


def _priority_title(module_key: str) -> str:
    """Return the stable user-facing title without importing connected services.

    The priority registry must remain usable during a fresh offline install,
    before optional network-client dependencies are installed.  Keep the title
    convention aligned with the contextual-research catalogue, but do not
    import that package here because it initialises connected providers.
    """
    special = {
        "gwas": "GWAS", "amr": "AMR", "rna": "RNA", "ai": "AI", "ml": "ML",
        "tme": "TME", "cart": "CAR-T", "3d": "3D", "t2t": "T2T",
        "multiomics": "Multi-Omics", "pangenome": "Pangenome",
        "metagenomics": "Metagenomics", "bioimage": "Bioimage",
        "bioprocess": "Bioprocess", "pharmacogenomics": "Pharmacogenomics",
    }
    return " ".join(
        special.get(token, token.capitalize())
        for token in module_key.replace("_core", "").replace("_v2", " 2").split("_")
    )


def _make_priority_module(module_key: str, priority: str, focus: tuple[str, str, str]) -> PriorityModule:
    return PriorityModule(
        module_key=module_key,
        title=_priority_title(module_key),
        priority=priority,
        runtime_data=focus[0],
        benchmark=focus[1],
        confirmation=focus[2],
        governance=_GOVERNANCE,
    )


PRIORITY_MODULES: dict[str, PriorityModule] = {
    key: _make_priority_module(key, "P0", _P0_FOCUS[key]) for key in P0_MODULE_KEYS
}
PRIORITY_MODULES.update(
    {key: _make_priority_module(key, "P1", _P1_FOCUS[key]) for key in P1_MODULE_KEYS}
)

if len(P0_MODULE_KEYS) != 25 or len(P1_MODULE_KEYS) != 37 or len(PRIORITY_MODULES) != 62:
    raise RuntimeError("P0/P1 priority portfolio must contain exactly 25 P0 and 37 P1 modules.")


def get_priority_module(module_key: str) -> PriorityModule | None:
    return PRIORITY_MODULES.get(module_key)


def canonical_execution_key(module_key: str) -> str:
    """Return the durable execution identity for a fixed P0/P1 module.

    ``module_key`` deliberately remains the local evidence key.  The canonical
    execution key is used only when joining an existing runtime/workbench that
    already uses a newer catalogue name.
    """
    key = str(module_key).strip()
    if key not in PRIORITY_MODULES:
        raise KeyError(f"{key!r} is not a P0/P1 priority module.")
    return EXECUTION_KEY_ALIASES.get(key, key)


def priority_requirement_rows(module_key: str) -> list[dict[str, str]]:
    profile = PRIORITY_MODULES[module_key]
    requirements = profile.gate_requirements()
    return [
        {"Gate": GATE_LABELS[gate], "Requirement": requirements[gate]}
        for gate in GATE_ORDER
    ]


__all__ = [
    "GATE_LABELS",
    "GATE_ORDER",
    "EXECUTION_KEY_ALIASES",
    "P0_MODULE_KEYS",
    "P1_MODULE_KEYS",
    "PRIORITY_MODULES",
    "PriorityModule",
    "canonical_execution_key",
    "get_priority_module",
    "priority_requirement_rows",
]
