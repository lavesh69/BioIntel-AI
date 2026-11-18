from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus

from biointel.connected.providers import PROVIDERS


@dataclass(frozen=True)
class ModuleResearchProfile:
    module_key: str
    title: str
    research_focus: str
    query_hint: str
    provider_entity_types: tuple[tuple[str, str], ...]
    quick_queries: tuple[str, ...]

    @property
    def providers(self) -> tuple[str, ...]:
        return tuple(provider for provider, _ in self.provider_entity_types)

    def entity_type_for(self, provider: str) -> str:
        for key, entity_type in self.provider_entity_types:
            if key == provider:
                return entity_type
        return "literature"


ALL_MAJOR_MODULE_KEYS: tuple[str, ...] = (
    "knowledge_graph_core", "multiomics_biomarker_discovery", "plugin_marketplace_core",
    "workflow_builder_core", "epigenomics_chromatin", "metabolomics_lipidomics",
    "immunoinformatics_vaccine", "antibody_biologics", "docking_dynamics",
    "pharmacogenomics", "spatial_omics_pathology", "single_cell_trajectory",
    "bioimage_microscopy", "clinical_trial_biomarker", "genome_editing_safety",
    "proteogenomics_neoantigen", "bioprocess_fermentation", "causal_inference_perturbation",
    "explainable_ai_assurance", "multiomics_harmonization", "glycomics_glycoproteomics",
    "one_health_environmental", "synthetic_data_privacy", "population_gwas",
    "structural_variant_repeat", "longitudinal_multiomics", "rna_isoform_splicing",
    "epitranscriptomics", "strain_microbiome", "cell_atlas_mapping",
    "phenotypic_screening", "organoid_3d", "protein_language_design",
    "enzyme_pathway_design", "host_pathogen_interaction", "virology_evolution",
    "rare_variant_family", "universal_file_inspector", "cross_module_workspace",
    "workflow_builder_v2", "background_job_engine", "unified_report_builder",
    "reference_lifecycle_v2", "provenance_ledger_v2", "evidence_citation_engine",
    "model_registry_ml_lifecycle", "collaboration_review_v2", "offline_scientific_copilot_v2",
    "data_lakehouse_v2", "benchmark_validation_v2", "plugin_marketplace_v2",
    "digital_pathology_foundation", "long_read_epigenome", "single_cell_long_read_isoforms",
    "biomedical_foundation_model_hub", "amr_surveillance", "spatial_medicine_tme",
    "gene_therapy_vector", "cell_therapy_cart", "federated_biomedical_ai",
    "clinical_biomarker_survival", "protein_ligand_codesign", "pangenome_population_medicine",
    "pharmacovigilance", "synthetic_cohort_trial", "autonomous_laboratory_planner",
    "background_jobs_core", "document_intelligence_core", "structural_bioinformatics_core",
    "flow_cytometry", "single_cell_core", "cancer_genomics_core", "metagenomics_core",
    "offline_copilot_core", "store_readiness_core", "clinical_pharma_validation",
    "pangenome_core", "long_read_core", "pathogen_outbreak_core", "synthetic_biology_circuit",
)


def _title(module_key: str) -> str:
    special = {
        "gwas": "GWAS", "amr": "AMR", "rna": "RNA", "ai": "AI", "ml": "ML",
        "tme": "TME", "cart": "CAR-T", "3d": "3D", "t2t": "T2T",
        "multiomics": "Multi-Omics", "pangenome": "Pangenome",
        "metagenomics": "Metagenomics", "bioimage": "Bioimage",
        "bioprocess": "Bioprocess", "pharmacogenomics": "Pharmacogenomics",
    }
    words = []
    for token in module_key.replace("_core", "").replace("_v2", " 2").split("_"):
        words.append(special.get(token, token.capitalize()))
    return " ".join(words)


GROUPS: dict[str, tuple[str, ...]] = {
    "gene_variant": (
        "pharmacogenomics", "genome_editing_safety", "population_gwas",
        "structural_variant_repeat", "rare_variant_family", "long_read_epigenome",
        "gene_therapy_vector", "pangenome_population_medicine", "cancer_genomics_core",
        "pangenome_core", "long_read_core", "epigenomics_chromatin",
    ),
    "omics_cell": (
        "multiomics_biomarker_discovery", "spatial_omics_pathology", "single_cell_trajectory",
        "proteogenomics_neoantigen", "causal_inference_perturbation", "multiomics_harmonization",
        "glycomics_glycoproteomics", "metabolomics_lipidomics", "longitudinal_multiomics",
        "rna_isoform_splicing", "epitranscriptomics", "cell_atlas_mapping", "organoid_3d",
        "spatial_medicine_tme", "single_cell_long_read_isoforms", "single_cell_core",
    ),
    "protein_drug": (
        "immunoinformatics_vaccine", "antibody_biologics", "docking_dynamics",
        "protein_language_design", "enzyme_pathway_design", "protein_ligand_codesign",
        "structural_bioinformatics_core", "biomedical_foundation_model_hub",
    ),
    "microbe_pathogen": (
        "one_health_environmental", "strain_microbiome", "host_pathogen_interaction",
        "virology_evolution", "amr_surveillance", "metagenomics_core",
        "pathogen_outbreak_core",
    ),
    "clinical": (
        "clinical_trial_biomarker", "clinical_biomarker_survival", "pharmacovigilance",
        "synthetic_cohort_trial", "clinical_pharma_validation", "cell_therapy_cart",
    ),
    "imaging_screening": (
        "bioimage_microscopy", "phenotypic_screening", "digital_pathology_foundation",
        "flow_cytometry",
    ),
    "lab_design": (
        "bioprocess_fermentation", "autonomous_laboratory_planner", "synthetic_biology_circuit",
    ),
    "ai_governance": (
        "explainable_ai_assurance", "synthetic_data_privacy", "federated_biomedical_ai",
        "model_registry_ml_lifecycle", "benchmark_validation_v2",
    ),
    "knowledge_evidence": (
        "knowledge_graph_core", "evidence_citation_engine", "document_intelligence_core",
        "offline_scientific_copilot_v2", "offline_copilot_core", "unified_report_builder",
        "provenance_ledger_v2", "reference_lifecycle_v2",
    ),
    "platform": (
        "plugin_marketplace_core", "workflow_builder_core", "universal_file_inspector",
        "cross_module_workspace", "workflow_builder_v2", "background_job_engine",
        "collaboration_review_v2", "data_lakehouse_v2", "plugin_marketplace_v2",
        "background_jobs_core", "store_readiness_core",
    ),
}



# Direct official-website access is intentionally limited to modules where
# provider records are scientifically actionable. Platform, installer, queue,
# marketplace, privacy and generic workflow modules retain no visible website
# panel even though their historical Step 196 hook remains for release
# compatibility.
TOP_WEBSITE_ELIGIBLE_MODULE_KEYS: frozenset[str] = frozenset(
    {
        # Genes, genomes and variants
        *GROUPS["gene_variant"],
        # Omics and cellular biology
        *GROUPS["omics_cell"],
        # Protein/drug research, excluding the generic model hub
        *(key for key in GROUPS["protein_drug"] if key != "biomedical_foundation_model_hub"),
        # Microbiology, pathogens and One Health
        *GROUPS["microbe_pathogen"],
        # Clinical and translational research
        *GROUPS["clinical"],
        # Imaging, pathology, cytometry and screening
        *GROUPS["imaging_screening"],
        # Wet-lab and experimental design
        *GROUPS["lab_design"],
        # Evidence-centric modules where official sources are core to the task
        "knowledge_graph_core",
        "evidence_citation_engine",
        "document_intelligence_core",
        "offline_scientific_copilot_v2",
        "offline_copilot_core",
        "reference_lifecycle_v2",
    }
)


def has_relevant_top_websites(module_key: str) -> bool:
    return module_key in TOP_WEBSITE_ELIGIBLE_MODULE_KEYS


GROUP_CONFIG: dict[str, dict[str, object]] = {
    "gene_variant": {
        "focus": "genes, variants, genomes, cohorts and genomic evidence",
        "hint": "Enter a gene, variant, genomic region, phenotype or study question",
        "providers": (("ncbi", "variant"), ("ensembl", "variant"), ("europepmc", "literature")),
        "quick": ("Find recent validation studies", "Check variant and gene annotations", "Review population evidence"),
    },
    "omics_cell": {
        "focus": "omics datasets, cell states, pathways and biomarker evidence",
        "hint": "Enter a gene set, cell type, biomarker, pathway or omics question",
        "providers": (("ncbi", "expression study"), ("reactome", "pathway"), ("string", "protein interaction"), ("europepmc", "literature")),
        "quick": ("Find related omics studies", "Check pathway support", "Review external biomarker evidence"),
    },
    "protein_drug": {
        "focus": "proteins, structures, compounds, targets and molecular evidence",
        "hint": "Enter a protein, accession, structure, compound, target or design question",
        "providers": (("uniprot", "protein"), ("rcsb", "structure"), ("interpro", "protein"), ("string", "protein interaction"), ("pubchem", "compound"), ("chembl", "compound"), ("europepmc", "literature")),
        "quick": ("Find structures and domains", "Review target and ligand evidence", "Find recent design studies"),
    },
    "microbe_pathogen": {
        "focus": "microbial genomes, taxa, resistance, outbreaks and host-pathogen evidence",
        "hint": "Enter an organism, strain, accession, resistance gene or outbreak question",
        "providers": (("ncbi", "sequence"), ("uniprot", "protein"), ("interpro", "protein"), ("europepmc", "literature")),
        "quick": ("Find genomic records", "Review resistance or virulence evidence", "Find outbreak literature"),
    },
    "clinical": {
        "focus": "clinical studies, biomarkers, cohorts, safety and translational evidence",
        "hint": "Enter a disease, biomarker, intervention, trial identifier or clinical question",
        "providers": (("clinicaltrials", "clinical trial"), ("ncbi", "literature"), ("europepmc", "literature"), ("ensembl", "gene")),
        "quick": ("Find active and completed trials", "Review clinical biomarker evidence", "Check safety literature"),
    },
    "imaging_screening": {
        "focus": "bioimaging, pathology, cytometry, screening and phenotype evidence",
        "hint": "Enter an imaging marker, phenotype, assay, tissue or model question",
        "providers": (("ncbi", "literature"), ("europepmc", "literature"), ("clinicaltrials", "clinical trial"), ("uniprot", "protein")),
        "quick": ("Find imaging validation studies", "Review marker evidence", "Find benchmark datasets"),
    },
    "lab_design": {
        "focus": "experimental design, bioprocess, synthetic biology and laboratory evidence",
        "hint": "Enter an organism, construct, process variable, assay or experiment question",
        "providers": (("ncbi", "literature"), ("europepmc", "literature"), ("reactome", "pathway"), ("uniprot", "protein")),
        "quick": ("Find protocol and method evidence", "Review biological pathway support", "Find process optimization studies"),
    },
    "ai_governance": {
        "focus": "biomedical AI validation, model assurance, privacy and benchmark evidence",
        "hint": "Enter a biomedical AI task, model, benchmark, validation or governance question",
        "providers": (("europepmc", "literature"), ("ncbi", "literature"), ("clinicaltrials", "clinical trial")),
        "quick": ("Find external model benchmarks", "Review calibration and bias studies", "Find privacy-preserving AI evidence"),
    },
    "knowledge_evidence": {
        "focus": "scientific publications, evidence provenance, citations and connected knowledge",
        "hint": "Enter a scientific topic, accession, paper, claim or evidence question",
        "providers": (("europepmc", "literature"), ("ncbi", "literature"), ("reactome", "pathway"), ("uniprot", "protein")),
        "quick": ("Find primary publications", "Check evidence provenance", "Build a citation-backed summary"),
    },
    "platform": {
        "focus": "scientific workflow methods, reproducibility, data operations and platform evidence",
        "hint": "Enter a workflow, data format, reproducibility, software or research-method question",
        "providers": (("europepmc", "literature"), ("ncbi", "literature")),
        "quick": ("Find workflow best practices", "Review reproducibility guidance", "Find scientific software methods"),
    },
}


def _build_profiles() -> dict[str, ModuleResearchProfile]:
    group_for: dict[str, str] = {}
    for group, keys in GROUPS.items():
        for key in keys:
            if key in group_for:
                raise ValueError(f"Duplicate contextual research profile assignment: {key}")
            group_for[key] = group
    missing = sorted(set(ALL_MAJOR_MODULE_KEYS) - set(group_for))
    extra = sorted(set(group_for) - set(ALL_MAJOR_MODULE_KEYS))
    if missing or extra:
        raise ValueError(f"Invalid contextual profile coverage; missing={missing}, extra={extra}")

    profiles: dict[str, ModuleResearchProfile] = {}
    for key in ALL_MAJOR_MODULE_KEYS:
        config = GROUP_CONFIG[group_for[key]]
        providers = tuple(config["providers"])  # type: ignore[arg-type]
        unknown = [provider for provider, _ in providers if provider not in PROVIDERS]
        if unknown:
            raise ValueError(f"Unknown providers for {key}: {unknown}")
        profiles[key] = ModuleResearchProfile(
            module_key=key,
            title=_title(key),
            research_focus=str(config["focus"]),
            query_hint=str(config["hint"]),
            provider_entity_types=providers,
            quick_queries=tuple(config["quick"]),  # type: ignore[arg-type]
        )
    return profiles


MODULE_RESEARCH_PROFILES = _build_profiles()


def get_module_research_profile(module_key: str) -> ModuleResearchProfile:
    try:
        return MODULE_RESEARCH_PROFILES[module_key]
    except KeyError as exc:
        raise KeyError(f"No contextual online-research profile is registered for {module_key!r}") from exc


def provider_query_url(provider: str, query: str, entity_type: str | None = None) -> str:
    q = quote_plus(query.strip())
    ncbi_urls = {
        "literature": f"https://pubmed.ncbi.nlm.nih.gov/?term={q}",
        "variant": f"https://www.ncbi.nlm.nih.gov/clinvar/?term={q}",
        "expression study": f"https://www.ncbi.nlm.nih.gov/gds/?term={q}",
        "sequence": f"https://www.ncbi.nlm.nih.gov/nuccore/?term={q}",
        "gene": f"https://www.ncbi.nlm.nih.gov/gene/?term={q}",
        "protein": f"https://www.ncbi.nlm.nih.gov/protein/?term={q}",
    }
    urls = {
        "ncbi": ncbi_urls.get(str(entity_type or "").strip().lower(), f"https://www.ncbi.nlm.nih.gov/search/all/?term={q}"),
        "pubchem": f"https://pubchem.ncbi.nlm.nih.gov/#query={q}",
        "uniprot": f"https://www.uniprot.org/uniprotkb?query={q}",
        "rcsb": "https://www.rcsb.org/search",
        "chembl": f"https://www.ebi.ac.uk/chembl/explore/compound/?q={q}",
        "ensembl": f"https://www.ensembl.org/Multi/Search/Results?q={q}",
        "clinicaltrials": f"https://clinicaltrials.gov/search?term={q}",
        "reactome": f"https://reactome.org/content/query?q={q}",
        "string": "https://string-db.org/",
        "interpro": f"https://www.ebi.ac.uk/interpro/search/text/{q}/",
        "europepmc": f"https://europepmc.org/search?query={q}",
    }
    return urls.get(provider, PROVIDERS[provider].base_url)
