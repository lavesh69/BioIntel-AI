from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class CapabilityRequirement:
    area: str
    requirement: str
    status: str
    evidence_boundary: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


WORKFLOW_STAGES: tuple[str, ...] = (
    "Input",
    "Validation",
    "Configuration",
    "Run",
    "Results",
    "Interpretation",
    "Evidence",
    "Export",
)


_DOMAIN_DEFAULTS: dict[str, tuple[CapabilityRequirement, ...]] = {
    "BioIntel Genomics & Bioinformatics": (
        CapabilityRequirement("Input", "Native and tabular biological inputs are schema-validated and checksum-bound.", "implemented"),
        CapabilityRequirement("Execution", "Large files use bounded parsing or staged background execution.", "implemented"),
        CapabilityRequirement("Visuals", "Results include multiple scientific views plus underlying data.", "implemented"),
        CapabilityRequirement("Evidence", "Reference build, annotation release, parameters and limitations are retained.", "implemented"),
    ),
    "BioIntel Discovery": (
        CapabilityRequirement("Chemistry", "Structures are standardised while original representations remain preserved.", "implemented"),
        CapabilityRequirement("Model assurance", "Applicability domain, uncertainty and split strategy are visible for model outputs.", "implemented"),
        CapabilityRequirement("Decision support", "Candidate ranking separates heuristics, model outputs and experimental evidence.", "implemented"),
        CapabilityRequirement("External boundary", "Docking, predictive endpoints and designed candidates require independent validation.", "external", "No software-only workflow can manufacture wet-lab confirmation."),
    ),
    "BioIntel Omics & Next-Generation Biology": (
        CapabilityRequirement("Study design", "Sample identity, group, batch and covariates are reviewable before analysis.", "implemented"),
        CapabilityRequirement("Statistics", "Missingness, normalization, batch effects and stability are surfaced.", "implemented"),
        CapabilityRequirement("Visuals", "Dimension reduction, distributions, feature rankings and sensitivity views are available.", "implemented"),
        CapabilityRequirement("Validation", "External-cohort or orthogonal validation remains explicit where required.", "external"),
    ),
    "BioIntel Lab": (
        CapabilityRequirement("Assay controls", "Units, controls, replicates, plate/run structure and acceptance limits are checked.", "implemented"),
        CapabilityRequirement("Range safety", "Out-of-range measurements are never silently exported as valid numbers.", "implemented"),
        CapabilityRequirement("Run provenance", "Raw-file hash, method, parameters and output artefacts are retained.", "implemented"),
        CapabilityRequirement("Regulated boundary", "Organisation-specific validation, qualification and approval remain external.", "external"),
    ),
    "Therapy & Translational": (
        CapabilityRequirement("Safety", "Safety risks, assumptions, evidence level and unresolved questions are explicit.", "implemented"),
        CapabilityRequirement("Population", "Cohort definition, subgroup stability and missingness are reviewed.", "implemented"),
        CapabilityRequirement("Simulation boundary", "Synthetic or simulated cohorts are clearly separated from real-patient evidence.", "implemented"),
        CapabilityRequirement("Clinical boundary", "Clinical utility and regulatory claims require independent clinical evidence.", "external"),
    ),
}


_SPECIFIC: dict[str, tuple[CapabilityRequirement, ...]] = {
    "fastq_genomics_qc": (
        CapabilityRequirement("FASTQ QC", "Per-cycle quality, GC, length, duplication and adapter profiles are available.", "implemented"),
        CapabilityRequirement("Paired-end", "Pair synchronisation and coordinated trimming are validated.", "implemented"),
        CapabilityRequirement("Scale", "Large FASTQ inputs are streamed or staged instead of loaded repeatedly.", "implemented"),
    ),
    "variant_annotation": (
        CapabilityRequirement("Variant views", "Chromosome, genotype, call-rate and interval views are available.", "implemented"),
        CapabilityRequirement("Annotation", "Consequence and clinical interpretation require a versioned annotation source.", "external", "Reference/demo annotations are not clinical classifications."),
        CapabilityRequirement("Review", "Sample, quality, allele-frequency and inheritance filters preserve an auditable review path.", "implemented"),
    ),
    "transcriptomics_expression": (
        CapabilityRequirement("Design", "Groups, reference level, batch and covariates are editable.", "implemented"),
        CapabilityRequirement("Statistics", "Normalization, PCA, differential expression, FDR and contrasts are available.", "implemented"),
        CapabilityRequirement("Interpretation", "Volcano, heatmap and pathway handoff preserve analysis assumptions.", "implemented"),
    ),
    "single_cell_heterogeneity": (
        CapabilityRequirement("Cell QC", "Cell quality, ambient-RNA and doublet screens are available.", "implemented"),
        CapabilityRequirement("Inference", "Clustering, markers, pseudobulk, trajectory and batch diagnostics are separated.", "implemented"),
        CapabilityRequirement("Annotation", "Cell labels remain provisional until study-specific confirmation.", "external"),
    ),
    "rare_disease_board": (
        CapabilityRequirement("Phenotype", "HPO, inheritance, segregation and population rarity are reviewable.", "implemented"),
        CapabilityRequirement("ACMG", "Criteria are transparent assistance prompts, not automated diagnosis.", "implemented"),
        CapabilityRequirement("Clinical boundary", "Clinical classification requires accredited laboratory and specialist review.", "external"),
    ),
    "dti_predictor": (
        CapabilityRequirement("Splits", "Cold-drug, cold-target, cold-both, scaffold or family-aware evaluation is required.", "implemented"),
        CapabilityRequirement("Calibration", "Calibration, uncertainty and applicability are shown with predictions.", "implemented"),
        CapabilityRequirement("Validation", "Independent or prospective assay validation is a hard release gate.", "external"),
    ),
    "structural_bioinformatics": (
        CapabilityRequirement("3D inspection", "Chains, ligands, residues, contacts and structure exports are interactive.", "implemented"),
        CapabilityRequirement("Quality", "Experimental quality, missing residues, clashes and assembly assumptions are reviewed.", "implemented"),
        CapabilityRequirement("Mechanistic boundary", "Visual contacts do not prove binding or mechanism.", "external"),
    ),
    "admet_discovery": (
        CapabilityRequirement("Batch", "Batch structure validation, duplicate handling, ranking and failed-row export are available.", "implemented"),
        CapabilityRequirement("Endpoint clarity", "Rule-based, heuristic, qualified-model and not-assessed endpoints are separated.", "implemented"),
        CapabilityRequirement("Validation", "Biological endpoints require endpoint-specific validation and assays.", "external"),
    ),
    "protein_design_lab": (
        CapabilityRequirement("Design", "Mutation compatibility, epistasis, stability and developability are considered.", "implemented"),
        CapabilityRequirement("Execution", "External model/tool readiness, weights, hardware and licence status are checked.", "implemented"),
        CapabilityRequirement("Validation", "Designed proteins require experimental confirmation.", "external"),
    ),
    "multiomics_biomarker": (
        CapabilityRequirement("Integration", "Identifier mapping, missingness, harmonisation and batch effects are reviewed.", "implemented"),
        CapabilityRequirement("Validation", "Nested evaluation, feature stability and decision curves are available.", "implemented"),
        CapabilityRequirement("External cohort", "A locked biomarker signature requires independent cohort validation.", "external"),
    ),
    "digital_pathology_foundation": (
        CapabilityRequirement("Image QC", "Tissue, stain, scanner/site and region quality are reviewed.", "implemented"),
        CapabilityRequirement("Uncertainty", "Region-level predictions and uncertainty maps remain reviewable.", "implemented"),
        CapabilityRequirement("Pathologist review", "Clinical interpretation requires qualified pathology review.", "external"),
    ),
    "spatial_medicine_tme": (
        CapabilityRequirement("Spatial QC", "Registration, coordinate integrity and neighbourhood context are checked.", "implemented"),
        CapabilityRequirement("TME", "Core/margin, immune neighbourhood and patient-level comparisons are available.", "implemented"),
        CapabilityRequirement("Validation", "Spatial biomarkers require orthogonal and cohort validation.", "external"),
    ),
    "long_read_epigenome": (
        CapabilityRequirement("Long-read QC", "Read/platform metadata, haplotype and methylation confidence are retained.", "implemented"),
        CapabilityRequirement("Epigenome", "DMR, allele-specific and imprinting screens are separated from claims.", "implemented"),
        CapabilityRequirement("Orthogonal validation", "Methylation findings require independent validation.", "external"),
    ),
    "wetlab_biotechnology": (
        CapabilityRequirement("qPCR", "Role-aware controls, MIQE metadata, reference stability and uncertainty are supported.", "implemented"),
        CapabilityRequirement("ELISA", "4PL/5PL complexity guards, LLOQ/ULOQ and safe inverse calibration are enforced.", "implemented"),
        CapabilityRequirement("Bioprocess", "Multi-batch and mode-aware process analytics preserve units and batch identity.", "implemented"),
        CapabilityRequirement("PAT", "Live historian/OPC-UA use requires validated external integration.", "external"),
    ),
    "lab_instrument_import": (
        CapabilityRequirement("Native import", "Instrument metadata, units, lot, operator and raw hash remain preserved.", "implemented"),
        CapabilityRequirement("Adapters", "RDML, qPCR, plate-reader and historian profiles are versioned.", "implemented"),
    ),
    "gene_therapy_vector": (
        CapabilityRequirement("Vector", "Capacity, promoter, tropism, integration and manufacturability are reviewed.", "implemented"),
        CapabilityRequirement("Safety", "Immunogenicity, off-target and biodistribution planning are explicit.", "implemented"),
        CapabilityRequirement("Preclinical boundary", "Preclinical evidence cannot be replaced by simulation.", "external"),
    ),
    "cell_therapy_cart": (
        CapabilityRequirement("Target", "Antigen evidence and off-tumour expression are reviewed.", "implemented"),
        CapabilityRequirement("Engineering", "scFv, signalling, exhaustion and manufacturing trade-offs are visible.", "implemented"),
        CapabilityRequirement("Clinical boundary", "Cell-therapy safety and efficacy require external preclinical/clinical evidence.", "external"),
    ),
    "clinical_biomarker_survival": (
        CapabilityRequirement("Cohort", "Eligibility, missingness, site effects and subgroup stability are explicit.", "implemented"),
        CapabilityRequirement("Statistics", "Survival, calibration, cut-off stability and decision curves are available.", "implemented"),
        CapabilityRequirement("Validation", "Clinical utility requires independent cohort validation.", "external"),
    ),
    "synthetic_cohort_trial": (
        CapabilityRequirement("Simulation", "Seeds, distributions, site heterogeneity, dropout and missingness are reproducible.", "implemented"),
        CapabilityRequirement("Boundary", "Simulation is never represented as real-patient evidence.", "implemented"),
    ),
}


def requirements_for(page_key: str, domain: str) -> tuple[CapabilityRequirement, ...]:
    specific = _SPECIFIC.get(str(page_key or "").strip(), ())
    default = _DOMAIN_DEFAULTS.get(str(domain or "").strip(), ())
    seen: set[tuple[str, str]] = set()
    output: list[CapabilityRequirement] = []
    for requirement in (*specific, *default):
        identity = (requirement.area, requirement.requirement)
        if identity not in seen:
            seen.add(identity)
            output.append(requirement)
    return tuple(output)


def _has_nonempty_mapping(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value)


def workflow_stage_rows(
    *,
    upload_profile: Mapping[str, Any] | None,
    run_manifest: Mapping[str, Any] | None,
    frame_audits: Mapping[str, Mapping[str, Any]] | None,
    visual_audits: Mapping[str, Mapping[str, Any]] | None,
    export_prepared: bool = False,
) -> list[dict[str, str]]:
    upload = dict(upload_profile or {})
    run = dict(run_manifest or {})
    frames = dict(frame_audits or {})
    visuals = dict(visual_audits or {})
    blockers = [
        str(message)
        for audit in frames.values()
        for message in (audit.get("blockers", []) or [])
    ]
    run_status = str(run.get("status", "")).lower()
    has_input = bool(upload) or bool(frames)
    validation_ok = has_input and not blockers
    configured = has_input
    run_done = run_status in {"completed", "success", "succeeded", "complete"} or bool(run.get("completed_at_utc"))
    results_ready = run_done or bool(frames.get("results")) or bool(visuals)
    interpretation_ready = results_ready and not blockers
    evidence_ready = results_ready

    state = {
        "Input": ("Complete" if has_input else "Awaiting", "Upload or select a dataset."),
        "Validation": ("Complete" if validation_ok else ("Blocked" if blockers else "Awaiting"), "Schema, missingness, duplicates and non-finite values."),
        "Configuration": ("Complete" if configured else "Awaiting", "Parameters and scientific assumptions."),
        "Run": ("Complete" if run_done else (run_status.title() if run_status else "Awaiting"), "Bounded execution with progress and recovery."),
        "Results": ("Complete" if results_ready else "Awaiting", "Tables and scientific visuals."),
        "Interpretation": ("Complete" if interpretation_ready else ("Blocked" if blockers else "Awaiting"), "Finding, confidence, limitations and next action."),
        "Evidence": ("Complete" if evidence_ready else "Awaiting", "Provenance, evidence status and boundary."),
        "Export": ("Complete" if export_prepared else "On demand", "Bounded reproducibility bundle."),
    }
    return [
        {"Stage": stage, "Status": state[stage][0], "Purpose": state[stage][1]}
        for stage in WORKFLOW_STAGES
    ]


def interpretation_summary(
    *,
    title: str,
    domain: str,
    run_manifest: Mapping[str, Any] | None,
    frame_audits: Mapping[str, Mapping[str, Any]] | None,
    visual_audits: Mapping[str, Mapping[str, Any]] | None,
    requirements: Iterable[CapabilityRequirement] = (),
) -> dict[str, Any]:
    run = dict(run_manifest or {})
    frames = dict(frame_audits or {})
    visuals = dict(visual_audits or {})
    blockers = list(dict.fromkeys(
        str(message)
        for audit in frames.values()
        for message in (audit.get("blockers", []) or [])
    ))
    warnings = list(dict.fromkeys(
        str(message)
        for audit in frames.values()
        for message in (audit.get("warnings", []) or [])
    ))
    blank = [name for name, audit in visuals.items() if not bool(audit.get("has_data"))]
    if blank:
        blockers.append(f"{len(blank)} blank visual(s) were suppressed.")

    status = str(run.get("status", "awaiting_run")).replace("_", " ").title()
    if blockers:
        confidence = "Low — automated blockers remain"
        finding = f"{title} produced a reviewable state, but the result is blocked from scientific release."
    elif run:
        confidence = "Moderate — automated checks passed; domain review remains"
        finding = f"{title} completed its bounded research workflow without an automated rendering or data-integrity blocker."
    else:
        confidence = "Not assessed — run the workflow"
        finding = f"{title} is ready for input and configuration; no completed result is available yet."

    external = [item.requirement for item in requirements if item.status == "external"]
    limitations = [*blockers[:5], *warnings[:4], *external[:3]]
    if not limitations:
        limitations = ["Automated checks cannot replace domain-expert review or external validation."]

    next_actions: list[str] = []
    if blockers:
        next_actions.append("Resolve all data and visual blockers, then rerun the analysis.")
    elif not run:
        next_actions.append("Complete input validation and run the configured analysis.")
    else:
        next_actions.append("Review the leading result records and sensitivity views with a domain expert.")
        next_actions.append("Prepare the bounded evidence bundle after final filters and parameters are locked.")
    if external:
        next_actions.append("Plan the independent laboratory, cohort or clinical validation required by the module boundary.")

    payload = {
        "finding": finding,
        "run_status": status,
        "confidence": confidence,
        "limitations": limitations,
        "recommended_next_actions": list(dict.fromkeys(next_actions)),
        "domain": domain,
    }
    payload["interpretation_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return payload


def performance_profile(page_key: str, domain: str) -> dict[str, Any]:
    heavy_tokens = (
        "fastq", "variant", "single_cell", "spatial", "pathology", "long_read",
        "metagen", "multiomics", "protein_design", "cohort", "pangenome",
    )
    heavy = any(token in str(page_key or "").lower() for token in heavy_tokens)
    return {
        "profile": "heavy_scientific" if heavy else "interactive_scientific",
        "interactive_row_limit": 250_000 if heavy else 500_000,
        "display_row_limit": 50_000,
        "visual_point_limit": 200_000,
        "large_file_mode": "staged background job" if heavy else "bounded interactive or staged background job",
        "cache_invalidation": "input checksum + schema + parameters + software version",
        "domain": domain,
    }
