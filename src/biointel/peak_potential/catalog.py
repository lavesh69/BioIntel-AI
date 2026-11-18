from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

# The user explicitly requested these scientific product families only.
CORE_CATEGORIES = frozenset({"Bioinformatics", "Discovery", "Lab Analytics"})

# Omics / next-generation biology and therapy/translational pages that live in
# neighbouring catalogue categories are explicitly included. Operational,
# governance, generic AI and unrelated clinical pages are intentionally excluded.
OMICS_TARGET_KEYS = frozenset(
    {
        "multiomics_biomarker",
        "transcriptomics_expression",
        "protein_annotation",
        "omics_integration",
        "single_cell_heterogeneity",
        "epigenomics_chromatin",
        "metabolomics_lipidomics",
        "spatial_omics_pathology",
        "single_cell_trajectory",
        "multiomics_harmonization",
        "glycomics_glycoproteomics",
        "longitudinal_multiomics",
        "epitranscriptomics",
        "cell_atlas_mapping",
        "digital_pathology_foundation",
        "long_read_epigenome",
        "single_cell_long_read_isoforms",
        "spatial_medicine_tme",
    }
)

THERAPY_TARGET_KEYS = frozenset(
    {
        "pharmacogenomics",
        "clinical_trial_biomarker",
        "rare_variant_family",
        "clinical_biomarker_survival",
        "pangenome_population_medicine",
        "pharmacovigilance_intelligence",
        "gene_therapy_vector",
        "cell_therapy_cart",
    }
)

EXPLICIT_TARGET_KEYS = frozenset(
    {
        *OMICS_TARGET_KEYS,
        *THERAPY_TARGET_KEYS,
        "protein_ligand_codesign",
        "autonomous_lab_planner",
        "amr_surveillance",
    }
)


# High-stakes discovery modules are included for transparent validation and
# robustness, but their output remains research-use only unless external proof
# is supplied.
DISCOVERY_HIGH_STAKES = frozenset(
    {
        "dti_predictor",
        "protein_design_lab",
        "protein_language_design",
        "protein_ligand_codesign",
        "cell_therapy_cart",
    }
)

DOMAIN_BY_CATEGORY = {
    "Bioinformatics": "BioIntel Genomics & Bioinformatics",
    "Discovery": "BioIntel Discovery",
    "Lab Analytics": "BioIntel Lab",
    "Clinical Research": "Therapy & Translational",
    "AI Lab": "BioIntel Omics & Next-Generation Biology",
}




@dataclass(frozen=True)
class PeakModuleContract:
    page_key: str
    title: str
    category: str
    domain: str
    visual_minimum: int
    quality_gates: tuple[str, ...]
    required_outputs: tuple[str, ...]
    handoffs: tuple[str, ...]
    evidence_boundary: str


def is_peak_target(*, page_key: str | None, category: str | None, title: str = "") -> bool:
    del title  # Selection is explicit and stable; display wording must not broaden scope.
    key = str(page_key or "").strip()
    cat = str(category or "").strip()
    if cat in CORE_CATEGORIES:
        return True
    return key in EXPLICIT_TARGET_KEYS


def domain_for(*, page_key: str, category: str, title: str) -> str:
    del title
    key = str(page_key or "").strip()
    cat = str(category or "").strip()
    if key in THERAPY_TARGET_KEYS:
        return "Therapy & Translational"
    # Discovery and Lab are product families in their own right, even when a
    # module title contains words such as proteomics, biomarker or therapy.
    if cat == "Discovery":
        return "BioIntel Discovery"
    if cat == "Lab Analytics":
        return "BioIntel Lab"
    if key in OMICS_TARGET_KEYS:
        return "BioIntel Omics & Next-Generation Biology"
    if cat == "Bioinformatics":
        return "BioIntel Genomics & Bioinformatics"
    return DOMAIN_BY_CATEGORY.get(cat, cat or "Scientific Module")


def contract_for(*, page_key: str, title: str, category: str) -> PeakModuleContract:
    domain = domain_for(page_key=page_key, category=category, title=title)
    lowered = f"{page_key} {title}".lower()
    visual_minimum = 5 if any(token in lowered for token in ("omics", "genom", "pathology", "spatial", "network")) else 4

    common_gates = [
        "Input identity, schema and size validated",
        "No silent empty result or blank visual",
        "Missingness, duplicates and non-finite values audited",
        "Method, parameters and software version captured",
        "Limitations and evidence status shown with every result",
    ]
    if any(token in lowered for token in ("clinical", "therapy", "patient", "rare", "pharmaco")):
        common_gates.extend(
            [
                "High-stakes output explicitly marked research-use only",
                "Independent clinical/laboratory confirmation required",
            ]
        )
    if page_key in DISCOVERY_HIGH_STAKES:
        common_gates.extend(
            [
                "Applicability domain and uncertainty reported",
                "Independent or prospective validation remains a hard release gate",
            ]
        )
    if category == "Lab Analytics" or "lab" in lowered:
        common_gates.extend(
            [
                "Controls, units, replicates and run acceptance rules reviewed",
                "Out-of-range measurements never exported as valid numeric results",
            ]
        )

    outputs = (
        "Interactive scientific results",
        "Underlying result table",
        "Quality and evidence audit",
        "Reproducibility manifest",
        "Portable ZIP evidence bundle",
    )
    if domain == "BioIntel Genomics & Bioinformatics":
        handoffs = ("Omics", "Evidence Review", "Research Report")
    elif domain == "BioIntel Discovery":
        handoffs = ("ADMET / Structure", "Lab validation", "Evidence Review")
    elif domain == "BioIntel Lab":
        handoffs = ("Run Registry", "Evidence Review", "Research Report")
    elif domain == "Therapy & Translational":
        handoffs = ("Clinical validation", "Governance", "Evidence Package")
    else:
        handoffs = ("Biomarker Discovery", "Model Validation", "Evidence Review")

    boundary = (
        "Peak mode improves execution safety, transparency and reproducibility. "
        "It does not manufacture external validation, clinical approval, wet-lab confirmation or regulatory acceptance."
    )
    return PeakModuleContract(
        page_key=page_key,
        title=title,
        category=category,
        domain=domain,
        visual_minimum=visual_minimum,
        quality_gates=tuple(dict.fromkeys(common_gates)),
        required_outputs=outputs,
        handoffs=handoffs,
        evidence_boundary=boundary,
    )


def target_keys_from_pages(pages: Iterable[object]) -> tuple[str, ...]:
    keys: list[str] = []
    for page in pages:
        key = str(getattr(page, "key", ""))
        category = str(getattr(page, "category", ""))
        title = str(getattr(page, "title", ""))
        if is_peak_target(page_key=key, category=category, title=title):
            keys.append(key)
    return tuple(dict.fromkeys(keys))
