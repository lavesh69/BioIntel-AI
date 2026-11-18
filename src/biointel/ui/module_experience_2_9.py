from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import streamlit as st

from biointel.ui.premium_visuals import comparison_state_svg, render_before_after_comparison
from biointel.ui.operational_canvas import render_operational_canvas


@dataclass(frozen=True)
class ModuleExperienceSpec:
    key: str
    title: str
    group: str
    icon: str
    entity_type: str
    primary_canvas: str
    workflow: tuple[str, ...]
    readiness: tuple[tuple[str, str, str], ...]
    handoffs: tuple[str, ...]
    decision_prompts: tuple[str, ...]
    evidence_level: str = "Research workflow"


_GROUP_TEMPLATES: dict[str, dict[str, Any]] = {
    "sequence_genomics": {
        "icon": "🧬",
        "entity_type": "Genomic entity",
        "primary_canvas": "Coordinate-aware sequence and evidence workspace",
        "workflow": ("Input", "Validate", "Map", "Interpret", "Review", "Export"),
        "readiness": (
            ("File integrity", "Pass", "Checksum and structure verified"),
            ("Reference build", "Review", "Confirm genome or transcript build"),
            ("Annotation source", "Review", "Pin database release"),
            ("Statistical context", "Pass", "Method and sample count recorded"),
            ("Evidence status", "Review", "External evidence may be required"),
        ),
    },
    "pathogen_longread": {
        "icon": "🦠",
        "entity_type": "Isolate or assembly",
        "primary_canvas": "Assembly, lineage and outbreak review workspace",
        "workflow": ("Samples", "QC", "Assemble/Profile", "Compare", "Review", "Report"),
        "readiness": (
            ("Sample metadata", "Review", "Host, location and date recommended"),
            ("Reference database", "Review", "Pin taxonomy or assembly database"),
            ("Contamination control", "Pass", "QC state available"),
            ("Lineage confidence", "Review", "Inspect support and recombination"),
            ("Public-health boundary", "Pass", "Research interpretation only"),
        ),
    },
    "omics_spatial": {
        "icon": "🔭",
        "entity_type": "Sample, cell or feature",
        "primary_canvas": "Design, selection and biological-state workspace",
        "workflow": ("Design", "QC", "Normalize", "Model", "Explore", "Export"),
        "readiness": (
            ("Sample design", "Review", "Groups and covariates must be explicit"),
            ("Replicate structure", "Review", "Biological replicates required"),
            ("Batch effects", "Review", "Assess before interpretation"),
            ("Feature identifiers", "Pass", "Mapped to a declared namespace"),
            ("Result provenance", "Pass", "Input and parameter hashes recorded"),
        ),
    },
    "protein_discovery": {
        "icon": "🧩",
        "entity_type": "Protein, residue or compound",
        "primary_canvas": "Structure, sequence and evidence decision workspace",
        "workflow": ("Prepare", "Inspect", "Score", "Compare", "Review", "Handoff"),
        "readiness": (
            ("Identity", "Pass", "Sequence or structure identity recorded"),
            ("Model/structure quality", "Review", "Inspect confidence and missing regions"),
            ("Applicability domain", "Review", "Do not extrapolate silently"),
            ("Experimental evidence", "Review", "In-silico results need confirmation"),
            ("Reproducibility", "Pass", "Parameters and engine version recorded"),
        ),
    },
    "analytical_imaging": {
        "icon": "🔬",
        "entity_type": "Peak, object or image region",
        "primary_canvas": "Raw-evidence and object-review workspace",
        "workflow": ("Import", "Calibrate", "Detect", "Review", "Accept", "Export"),
        "readiness": (
            ("Raw data", "Review", "Native evidence preferred"),
            ("Calibration", "Review", "Units and calibration must be declared"),
            ("Blank/control", "Review", "Controls should be mapped"),
            ("Identification confidence", "Review", "Confidence level visible"),
            ("Manual review", "Pass", "Accept/reject decision recorded"),
        ),
    },
    "wetlab_design": {
        "icon": "🧪",
        "entity_type": "Assay, plate or process run",
        "primary_canvas": "Protocol, allocation and quality-decision workspace",
        "workflow": ("Plan", "Assign", "Run", "QC", "Interpret", "Archive"),
        "readiness": (
            ("Protocol version", "Pass", "Version captured"),
            ("Controls", "Review", "Required controls must be assigned"),
            ("Replicates", "Review", "Biological and technical roles separated"),
            ("Units", "Pass", "Units declared or mapped"),
            ("Acceptance rules", "Review", "Lock before final interpretation"),
        ),
    },
    "ai_models": {
        "icon": "🤖",
        "entity_type": "Model, experiment or prediction",
        "primary_canvas": "Lifecycle, evidence and approval workspace",
        "workflow": ("Register", "Train", "Validate", "Explain", "Approve", "Monitor"),
        "readiness": (
            ("Dataset snapshot", "Pass", "Immutable input reference"),
            ("Leakage audit", "Review", "Entity-aware split required"),
            ("Calibration", "Review", "Probability outputs must be calibrated"),
            ("External validation", "Review", "Independent cohort preferred"),
            ("Approval status", "Pending", "Reviewer action required"),
        ),
    },
    "data_evidence": {
        "icon": "🗂️",
        "entity_type": "Dataset, evidence item or reference asset",
        "primary_canvas": "Lineage, readiness and governance workspace",
        "workflow": ("Register", "Profile", "Curate", "Verify", "Release", "Archive"),
        "readiness": (
            ("Physical asset", "Pass", "Content hash recorded"),
            ("Logical version", "Pass", "Version identifier present"),
            ("Licence/consent", "Review", "Terms must be acknowledged"),
            ("Scientific readiness", "Review", "Separate from metadata completeness"),
            ("Lineage", "Pass", "Parent and downstream links available"),
        ),
    },
}


def _spec(
    key: str,
    title: str,
    group: str,
    *,
    entity_type: str | None = None,
    primary_canvas: str | None = None,
    handoffs: tuple[str, ...] = (),
    decision_prompts: tuple[str, ...] = (),
    evidence_level: str = "Research workflow",
) -> ModuleExperienceSpec:
    template = _GROUP_TEMPLATES[group]
    return ModuleExperienceSpec(
        key=key,
        title=title,
        group=group,
        icon=str(template["icon"]),
        entity_type=entity_type or str(template["entity_type"]),
        primary_canvas=primary_canvas or str(template["primary_canvas"]),
        workflow=tuple(template["workflow"]),
        readiness=tuple(template["readiness"]),
        handoffs=handoffs or ("Project Workspace", "Evidence Review", "Report Studio"),
        decision_prompts=decision_prompts
        or (
            "Is the input scientifically appropriate for this workflow?",
            "Which result needs manual review before release?",
            "What evidence or validation is still missing?",
        ),
        evidence_level=evidence_level,
    )


MODULE_EXPERIENCE_CATALOG: dict[str, ModuleExperienceSpec] = {
    # 2. Sequence and genomics
    "sequence_analyzer": _spec("sequence_analyzer", "Sequence Analyzer", "sequence_genomics", entity_type="Sequence or ORF", handoffs=("Sequence Comparison", "Protein Annotation", "Primer & CRISPR", "Report Studio")),
    "sequence_comparison": _spec("sequence_comparison", "Sequence Comparison", "sequence_genomics", entity_type="Sequence pair or alignment block", handoffs=("Alignment & Phylogeny", "Variant Workbench", "Protein Annotation")),
    "batch_sequence": _spec("batch_sequence", "Batch Sequence Analysis", "sequence_genomics", entity_type="Sequence batch", handoffs=("FASTQ QC", "Sequence Analyzer", "Data Registry")),
    "fastq_qc": _spec("fastq_qc", "FASTQ & Genome QC", "sequence_genomics", entity_type="Read set", handoffs=("Long-Read Assembly", "Metagenomics", "Variant Workbench")),
    "variant_workbench": _spec("variant_workbench", "Variant & Annotation Workbench", "sequence_genomics", entity_type="Variant or genomic interval", handoffs=("Rare Disease", "Cancer Genomics", "Pharmacogenomics", "Genome Browser")),
    "gwas": _spec("gwas", "Population Genetics & GWAS", "sequence_genomics", entity_type="Variant, phenotype or cohort", handoffs=("Variant Workbench", "Clinical Biomarkers", "Scientific Data Readiness")),
    "structural_variant": _spec("structural_variant", "Structural Variant & Repeat Expansion", "sequence_genomics", entity_type="Breakpoint or repeat locus", handoffs=("Variant Workbench", "Rare Disease", "Genome Browser")),
    "epigenomics": _spec("epigenomics", "Epigenomics & Chromatin", "sequence_genomics", entity_type="Peak, region or regulatory element", handoffs=("Transcriptomics", "Pathway Analysis", "Genome Browser")),
    "rna_splicing": _spec("rna_splicing", "RNA Isoform & Alternative Splicing", "sequence_genomics", entity_type="Transcript, exon or junction", handoffs=("Transcriptomics", "Protein Annotation", "Genome Browser")),
    "cancer_genomics": _spec("cancer_genomics", "Cancer Genomics", "sequence_genomics", entity_type="Tumour sample, clone or variant", handoffs=("Clinical Biomarkers", "Proteogenomics", "Variant Workbench")),
    "genome_editing": _spec("genome_editing", "Genome Editing Safety", "sequence_genomics", entity_type="Guide or off-target locus", handoffs=("Primer & CRISPR", "Variant Workbench", "Report Studio")),
    "rare_disease": _spec("rare_disease", "Rare Disease Interpretation", "sequence_genomics", entity_type="Patient, gene or candidate variant", handoffs=("Family Genetics", "Variant Workbench", "Evidence Review")),
    "family_genetics": _spec("family_genetics", "Rare Variant & Family Genetics", "sequence_genomics", entity_type="Pedigree member or inherited variant", handoffs=("Rare Disease", "Variant Workbench", "Report Studio")),
    "pharmacogenomics": _spec("pharmacogenomics", "Pharmacogenomics & Precision Medicine", "sequence_genomics", entity_type="Gene, diplotype or medication", handoffs=("Variant Workbench", "Evidence Review", "Clinical Biomarkers"), evidence_level="Research support — clinical review required"),
    # 3. Long-read, pangenome and pathogen
    "pangenome": _spec("pangenome", "Pangenome & Variation Graph", "pathogen_longread", entity_type="Graph node, path or bubble", handoffs=("Long-Read Assembly", "Comparative Genomics", "Genome Browser")),
    "long_read": _spec("long_read", "Long-Read Assembly & T2T", "pathogen_longread", entity_type="Read set, contig or assembly region", handoffs=("Pangenome", "Variant Workbench", "Assembly Report")),
    "comparative_pathogen": _spec("comparative_pathogen", "Comparative Pathogen Genomics", "pathogen_longread", entity_type="Isolate, genome or ortholog", handoffs=("Pathogen Outbreak", "Metagenomics", "Phylogeny")),
    "pathogen_outbreak": _spec("pathogen_outbreak", "Pathogen Outbreak Genomics", "pathogen_longread", entity_type="Case, isolate or transmission link", handoffs=("One Health", "Phylogeny", "Evidence Review")),
    "virology": _spec("virology", "Virology & Viral Evolution", "pathogen_longread", entity_type="Viral genome, lineage or mutation", handoffs=("Pathogen Outbreak", "Phylogeny", "Genome Browser")),
    "one_health": _spec("one_health", "One Health & Environmental Genomics", "pathogen_longread", entity_type="Human, animal or environmental sample", handoffs=("Pathogen Outbreak", "Metagenomics", "Evidence Review")),
    "metagenomics": _spec("metagenomics", "Metagenomics Professional Pipeline", "pathogen_longread", entity_type="Sample, taxon or functional feature", handoffs=("Microbiology Rapid Screen", "One Health", "Report Studio")),
    "microbiology": _spec("microbiology", "Microbiology & Metagenomics Rapid Screen", "pathogen_longread", entity_type="Sample, organism or AMR hit", handoffs=("Metagenomics Pipeline", "One Health", "Evidence Review")),
    "strain_microbiome": _spec("strain_microbiome", "Strain-Resolved Microbiome", "pathogen_longread", entity_type="Strain, pathway or resistance determinant", handoffs=("Metagenomics", "One Health", "Data Registry")),
    # 4. Transcriptomics, single-cell and spatial
    "transcriptomics": _spec("transcriptomics", "Transcriptomics Expression Lab", "omics_spatial", entity_type="Sample, gene or contrast", handoffs=("RNA Splicing", "Pathway Analysis", "Biomarker Discovery")),
    "single_cell": _spec("single_cell", "Single-Cell Heterogeneity", "omics_spatial", entity_type="Cell, cluster or marker", handoffs=("Cell Atlas", "Trajectory & Communication", "Spatial Omics")),
    "single_cell_trajectory": _spec("single_cell_trajectory", "Single-Cell Trajectory & Communication", "omics_spatial", entity_type="Cell state, branch or ligand-receptor pair", handoffs=("Single-Cell Heterogeneity", "Cell Atlas", "Pathway Analysis")),
    "cell_atlas": _spec("cell_atlas", "Cell Atlas Mapping", "omics_spatial", entity_type="Reference cell type or query cell", handoffs=("Single-Cell Heterogeneity", "Trajectory & Communication", "Data Registry")),
    "perturbseq": _spec("perturbseq", "CRISPR Screen & Perturb-seq", "omics_spatial", entity_type="Guide, perturbation or cell state", handoffs=("Single-Cell Heterogeneity", "Genome Editing Safety", "Pathway Analysis")),
    "spatial_omics": _spec("spatial_omics", "Spatial Omics & Digital Pathology", "omics_spatial", entity_type="Tissue region, spot or cell", handoffs=("Single-Cell Heterogeneity", "Clinical Biomarkers", "Pathology Review")),
    "multiomics": _spec("multiomics", "Omics Integration Hub", "omics_spatial", entity_type="Sample or cross-omics feature", handoffs=("Biomarker Discovery", "Pathway Analysis", "Data Registry")),
    "biomarker_discovery": _spec("biomarker_discovery", "Multi-Omics Biomarker Discovery", "omics_spatial", entity_type="Biomarker candidate or cohort", handoffs=("Clinical Biomarkers", "Model Training", "Evidence Review")),
    # 5. Protein, structure and discovery (DTI excluded)
    "protein_annotation": _spec("protein_annotation", "Protein Annotation & Proteomics", "protein_discovery", entity_type="Protein, domain or peptide", handoffs=("Structural Bioinformatics", "Proteogenomics", "Pathway Analysis")),
    "structural_bioinformatics": _spec("structural_bioinformatics", "Structural Bioinformatics", "protein_discovery", entity_type="Structure, chain or residue", handoffs=("Molecular Docking", "Protein Design", "Antibody Engineering")),
    "molecular_docking": _spec("molecular_docking", "Molecular Docking & Dynamics", "protein_discovery", entity_type="Pose, ligand or residue contact", handoffs=("Structural Bioinformatics", "ADMET", "Report Studio")),
    "protein_design": _spec("protein_design", "AI Protein Design", "protein_discovery", entity_type="Design candidate, mutation or residue", handoffs=("Structural Bioinformatics", "Antibody Engineering", "Model Evaluation")),
    "antibody": _spec("antibody", "Antibody & Biologics Engineering", "protein_discovery", entity_type="Antibody chain, CDR or mutation", handoffs=("Structural Bioinformatics", "Immunoinformatics", "Report Studio")),
    "immunoinformatics": _spec("immunoinformatics", "Immunoinformatics & Vaccine Design", "protein_discovery", entity_type="Epitope, HLA allele or construct", handoffs=("Protein Annotation", "Clinical Biomarkers", "Evidence Review")),
    "enzyme_engineering": _spec("enzyme_engineering", "Enzyme Engineering & Pathway Design", "protein_discovery", entity_type="Enzyme, active site or pathway reaction", handoffs=("Structural Bioinformatics", "Synthetic Biology", "Bioprocess")),
    "smiles": _spec("smiles", "Drug SMILES Analyzer", "protein_discovery", entity_type="Molecule, scaffold or substructure", handoffs=("ChEMBL Builder", "ADMET", "Molecular Docking")),
    "chembl": _spec("chembl", "ChEMBL Dataset Builder", "protein_discovery", entity_type="Compound, assay or activity record", handoffs=("Drug SMILES Analyzer", "ADMET", "Data Registry")),
    "admet": _spec("admet", "ADMET Triage & Developability", "protein_discovery", entity_type="Molecule or endpoint", handoffs=("Drug SMILES Analyzer", "Molecular Docking", "Report Studio")),
    "pathway": _spec("pathway", "Pathway & Network Analysis", "protein_discovery", entity_type="Gene, protein or pathway", handoffs=("Transcriptomics", "Omics Integration", "Evidence Review")),
    "host_pathogen": _spec("host_pathogen", "Host–Pathogen Interaction", "protein_discovery", entity_type="Host factor, pathogen factor or interaction", handoffs=("Pathogen Outbreak", "Pathway Analysis", "Drug SMILES Analyzer")),
    # 6. Metabolomics, proteomics and imaging
    "metabolomics": _spec("metabolomics", "Metabolomics & Lipidomics", "analytical_imaging", entity_type="Peak, metabolite or lipid species", handoffs=("Omics Integration", "Pathway Analysis", "Biomarker Discovery")),
    "proteogenomics": _spec("proteogenomics", "Proteogenomics & Neoantigen Discovery", "analytical_imaging", entity_type="Variant peptide, spectrum match or neoantigen", handoffs=("Protein Annotation", "Cancer Genomics", "Immunoinformatics")),
    "glycomics": _spec("glycomics", "Glycomics & Glycoproteomics", "analytical_imaging", entity_type="Glycan, glycopeptide or site", handoffs=("Protein Annotation", "Omics Integration", "Evidence Review")),
    "bioimage": _spec("bioimage", "Bioimage & Microscopy AI", "analytical_imaging", entity_type="Image, object or segmentation mask", handoffs=("High-Content Screening", "Organoid Analytics", "Report Studio")),
    "organoid": _spec("organoid", "Organoid & 3D Cell Analytics", "analytical_imaging", entity_type="Organoid, well or tracked object", handoffs=("Bioimage AI", "High-Content Screening", "Biomarker Discovery")),
    "high_content": _spec("high_content", "Phenotypic & High-Content Screening", "analytical_imaging", entity_type="Well, image object or phenotype", handoffs=("Bioimage AI", "ADMET", "Biomarker Discovery")),
    "flow_cytometry": _spec("flow_cytometry", "Flow-Cytometry Analysis", "analytical_imaging", entity_type="Event, gate or population", handoffs=("Wet-Lab Biotechnology", "Single-Cell Heterogeneity", "Report Studio")),
    # 7. Wet-lab and study design
    "wetlab": _spec("wetlab", "Wet-Lab Biotechnology", "wetlab_design", entity_type="Assay run, plate or sample", handoffs=("Statistical Power", "Data Registry", "Research Report")),
    "bioprocess": _spec("bioprocess", "Bioprocess & Fermentation", "wetlab_design", entity_type="Batch, reactor or process phase", handoffs=("Enzyme Engineering", "Statistical Power", "Report Studio")),
    "study_design": _spec("study_design", "Statistical Power & Study Design", "wetlab_design", entity_type="Study scenario, arm or allocation", handoffs=("Wet-Lab Biotechnology", "Clinical Biomarkers", "Project Workspace")),
    "synthetic_biology": _spec("synthetic_biology", "Synthetic Biology & Genetic Circuit Design", "wetlab_design", entity_type="Circuit, part or construct", handoffs=("Enzyme Engineering", "Primer & Codon Studio", "Bioprocess")),
    "primer_codon": _spec("primer_codon", "Primer, CRISPR & Codon Studio", "wetlab_design", entity_type="Primer, guide or coding sequence", handoffs=("Genome Editing Safety", "Sequence Analyzer", "Wet-Lab Biotechnology")),
    # 8. AI, ML and model lifecycle
    "model_training": _spec("model_training", "Model Training", "ai_models", entity_type="Training run or model candidate", handoffs=("Model Evaluation", "Experiment Registry", "Model Lifecycle")),
    "model_evaluation": _spec("model_evaluation", "Model Evaluation", "ai_models", entity_type="Model, cohort or error case", handoffs=("External Validation", "Explainable AI", "Model Lifecycle")),
    "ml_autolab": _spec("ml_autolab", "ML AutoLab", "ai_models", entity_type="Automated experiment or candidate model", handoffs=("Model Evaluation", "Experiment Registry", "Model Lifecycle")),
    "external_validation": _spec("external_validation", "External Validation & Drift", "ai_models", entity_type="Model, external cohort or drift signal", handoffs=("Model Evaluation", "Model Lifecycle", "Evidence Review")),
    "explainable_ai": _spec("explainable_ai", "Explainable AI & Model Assurance", "ai_models", entity_type="Prediction, feature or explanation", handoffs=("Model Evaluation", "Clinical Biomarkers", "Evidence Review")),
    "causal_biology": _spec("causal_biology", "Causal Biology & Perturbation", "ai_models", entity_type="Variable, instrument or causal edge", handoffs=("Biomarker Discovery", "Pathway Analysis", "Study Design")),
    "model_lifecycle": _spec("model_lifecycle", "Model Lifecycle", "ai_models", entity_type="Model version or approval event", handoffs=("Model Registry", "External Validation", "Release Gate")),
    "model_registry": _spec("model_registry", "Model Registry & ML Lifecycle", "ai_models", entity_type="Registered model or deployment", handoffs=("Model Evaluation", "Model Lifecycle", "Release Gate")),
    "batch_jobs": _spec("batch_jobs", "Resumable Batch Jobs", "ai_models", entity_type="Job, stage or artifact", handoffs=("Model Training", "Performance Center", "Project Workspace")),
    "leakage_lab": _spec("leakage_lab", "Benchmark & Leakage Lab", "ai_models", entity_type="Split, overlapping entity or benchmark result", handoffs=("Model Evaluation", "Model Training", "Release Gate")),
    "ppi_ml": _spec("ppi_ml", "Protein Interaction ML", "ai_models", entity_type="Protein pair or prediction", handoffs=("Protein Annotation", "Pathway Analysis", "Model Evaluation")),
    # 9. Data, evidence and reference
    "dataset_registry": _spec("dataset_registry", "Dataset Registry & Lineage", "data_evidence", entity_type="Dataset version or physical asset", handoffs=("Data Quality", "Scientific Data Readiness", "Project Workspace")),
    "data_readiness": _spec("data_readiness", "Scientific Data Readiness", "data_evidence", entity_type="Dataset or validation issue", handoffs=("Dataset Registry", "Evidence Review", "Release Gate")),
    "data_quality": _spec("data_quality", "Data Quality & Activity", "data_evidence", entity_type="Column, sample or quality issue", handoffs=("Dataset Registry", "Data Curation", "Scientific Data Readiness")),
    "data_coverage": _spec("data_coverage", "Data Coverage Center", "data_evidence", entity_type="Organism, tissue, modality or coverage gap", handoffs=("Data Curation", "Provider Integration", "Project Workspace")),
    "data_model_library": _spec("data_model_library", "Data & Model Library", "data_evidence", entity_type="Dataset, model or compatibility link", handoffs=("Dataset Registry", "Model Registry", "Project Workspace")),
    "data_curation": _spec("data_curation", "Scientific Data Curation", "data_evidence", entity_type="Record, inclusion decision or curation issue", handoffs=("Dataset Registry", "Evidence Registry", "Scientific Data Readiness")),
    "reference_manager": _spec("reference_manager", "Reference Database Manager", "data_evidence", entity_type="Reference asset or version", handoffs=("Reference Lifecycle", "Provider Integration", "System Diagnostics")),
    "reference_lifecycle": _spec("reference_lifecycle", "Reference Database Lifecycle", "data_evidence", entity_type="Reference version, download or activation", handoffs=("Reference Manager", "Provider Integration", "System Diagnostics")),
    "provider_integration": _spec("provider_integration", "Provider Integration Center", "data_evidence", entity_type="Provider, sync job or rejected record", handoffs=("Reference Lifecycle", "Evidence Registry", "Data Curation")),
    "real_evidence": _spec("real_evidence", "Real Evidence Studio", "data_evidence", entity_type="Evidence record, source or review", handoffs=("Evidence Review", "Dataset Registry", "Report Studio")),
    "evidence_citation": _spec("evidence_citation", "Scientific Evidence & Citation Engine", "data_evidence", entity_type="Claim, source or citation link", handoffs=("Real Evidence Studio", "Knowledge Graph", "Report Studio")),
    "data_lakehouse": _spec("data_lakehouse", "Data Lakehouse & Sample Search", "data_evidence", entity_type="Indexed asset, sample or duplicate cluster", handoffs=("Dataset Registry", "Project Workspace", "Data Quality")),
}


GROUP_LABELS = {
    "sequence_genomics": "Sequence & genomics",
    "pathogen_longread": "Long-read, pangenome & pathogen",
    "omics_spatial": "Transcriptomics, single-cell & spatial",
    "protein_discovery": "Protein, structure & discovery",
    "analytical_imaging": "Metabolomics, proteomics & imaging",
    "wetlab_design": "Wet-lab & study design",
    "ai_models": "AI, ML & model lifecycle",
    "data_evidence": "Data, evidence & reference",
}


def _safe(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _inject_css() -> None:
    """Inject workspace CSS for the current Streamlit page render.

    Streamlit keeps ``st.session_state`` while replacing the page DOM during
    multipage navigation.  The previous implementation used a session-level
    flag and therefore skipped the stylesheet on later pages, leaving the
    workspace summary as concatenated unstyled text.  The stylesheet is small
    and intentionally emitted on every renderer call so every page owns the
    styles it needs.
    """
    st.markdown(
        """
<style id="biointel-module-experience-v2">
.mx-shell,.mx-shell *{box-sizing:border-box}
.mx-shell{display:block!important;border:1px solid var(--bio-border,rgba(111,149,198,.28));border-radius:18px;background:linear-gradient(145deg,var(--bio-surface-raised,rgba(11,23,42,.97)),var(--bio-surface-primary,rgba(8,16,31,.98)));padding:18px;margin:10px 0 16px;box-shadow:0 12px 34px rgba(0,0,0,.18);line-height:1.45;overflow:hidden}
.mx-header{display:flex!important;gap:12px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}.mx-title{display:block!important;font-size:1.05rem;font-weight:850;color:var(--bio-text-primary,#f5f8ff)}.mx-sub{display:block!important;font-size:.8rem;color:var(--bio-text-muted,#aebbd3);margin-top:3px;max-width:900px}.mx-badges{display:flex!important;gap:6px;flex-wrap:wrap}
.mx-badge{display:inline-flex!important;align-items:center;padding:4px 9px;border:1px solid rgba(255,255,255,.13);border-radius:999px;font-size:.7rem;font-weight:750;white-space:normal}.mx-pass{background:rgba(31,184,137,.15);color:#79efc8}.mx-review{background:rgba(245,178,58,.15);color:#ffd071}.mx-pending{background:rgba(113,131,163,.16);color:#c0cadc}.mx-fail{background:rgba(235,88,104,.16);color:#ff9da7}
.mx-grid{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-top:12px;width:100%;align-items:stretch}.mx-card{display:block!important;border:1px solid rgba(113,149,198,.25);border-radius:14px;background:var(--bio-surface-card,rgba(23,39,65,.74));padding:12px;min-height:76px;min-width:0;height:100%;overflow:hidden;overflow-wrap:anywhere;word-break:normal;hyphens:auto}.mx-card b{display:block!important;color:var(--bio-text-primary,#f3f7ff);font-size:.82rem;margin-bottom:5px;min-width:0}.mx-card span{display:block!important;color:var(--bio-text-muted,#aebbd3);font-size:.74rem;line-height:1.38;min-width:0;white-space:normal}.mx-card strong{font-size:1.12rem;color:#7fe6d5}
.mx-stepper{display:flex!important;gap:8px;overflow-x:auto;margin:12px 0;padding-bottom:4px}.mx-step{display:block!important;position:relative;min-width:118px;border:1px solid rgba(113,149,198,.25);border-radius:12px;background:rgba(22,39,65,.72);padding:10px}.mx-step:after{content:'›';position:absolute;right:-9px;top:22px;color:#8193af;font-size:1.3rem}.mx-step:last-child:after{display:none}.mx-step small{display:block;color:#7f92af}.mx-step strong{display:block;font-size:.77rem;color:#eff5ff}
.mx-matrix{width:100%;border-collapse:separate;border-spacing:4px}.mx-matrix th,.mx-matrix td{padding:7px 9px;border-radius:8px;font-size:.73rem;text-align:left}.mx-matrix th{color:#9fb0c9}.mx-matrix td{background:rgba(23,41,69,.72);color:#dce6f5}
.mx-canvas{display:block!important;width:100%;height:auto;border-radius:15px;border:1px solid rgba(113,149,198,.27);background:#081321}.mx-callout{display:block!important;border-left:4px solid #49d8ca;border-radius:0 12px 12px 0;background:rgba(21,40,66,.72);padding:11px 13px;color:#dce8f7;font-size:.8rem;margin:10px 0}.mx-timeline{display:block!important;position:relative;padding-left:18px}.mx-event{display:block!important;position:relative;padding:0 0 14px 18px;border-left:2px solid rgba(88,188,190,.35)}.mx-event:before{content:'';position:absolute;left:-6px;top:2px;width:10px;height:10px;border-radius:50%;background:#55d1c7}.mx-event b{display:block!important;color:#eef5ff;font-size:.8rem}.mx-event span{display:block!important;color:#9fb1ca;font-size:.73rem}.mx-handoff{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:9px}.mx-node{display:block!important;border:1px solid rgba(113,149,198,.27);border-radius:13px;background:rgba(24,42,70,.75);padding:11px;color:#e7effc;font-size:.78rem;position:relative}.mx-node:after{content:'→';position:absolute;right:-10px;top:16px;color:#67d7ce;font-size:1.1rem}.mx-node:last-child:after{display:none}.mx-passport{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}.mx-field{display:block!important;border:1px solid rgba(113,149,198,.25);border-radius:12px;padding:10px;background:rgba(18,34,58,.74)}.mx-field small{display:block;color:#8fa1bd}.mx-field b{display:block;color:#eff5ff;font-size:.82rem}.mx-compare{display:grid!important;grid-template-columns:1fr 1fr;gap:10px}.mx-pane{display:block!important;border:1px solid rgba(113,149,198,.25);border-radius:13px;padding:12px;background:rgba(18,34,58,.74)}.mx-pane h5{display:block;margin:0 0 8px;color:#eef5ff}.mx-chip{display:inline-block!important;padding:3px 7px;border-radius:999px;background:rgba(77,118,184,.2);color:#bcd2f5;font-size:.68rem;margin:2px}
@media(max-width:1100px){.mx-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:760px){.mx-shell{padding:13px}.mx-grid{grid-template-columns:1fr 1fr}.mx-compare{grid-template-columns:1fr}.mx-node:after{display:none}}
@media(max-width:480px){.mx-grid{grid-template-columns:1fr}.mx-header{display:block!important}.mx-badges{margin-top:10px}}
@media(forced-colors:active){.mx-shell,.mx-card,.mx-step,.mx-node,.mx-field,.mx-pane{forced-color-adjust:auto;border:1px solid CanvasText}.mx-badge{border:1px solid CanvasText}}
</style>
""",
        unsafe_allow_html=True,
    )


def _badge(label: str, state: str) -> str:
    normalized = state.lower()
    cls = "mx-pass" if normalized in {"pass", "ready", "active", "verified"} else "mx-fail" if normalized in {"fail", "blocked"} else "mx-pending" if normalized in {"pending", "not started"} else "mx-review"
    return f'<span class="mx-badge {cls}">{_safe(label)} · {_safe(state)}</span>'


def _stepper(steps: Iterable[str], active_index: int = 2) -> str:
    parts: list[str] = []
    for index, label in enumerate(steps):
        state = "Pass" if index < active_index else "Active" if index == active_index else "Pending"
        parts.append(f'<div class="mx-step"><small>{index + 1:02d}</small><strong>{_safe(label)}</strong><div style="margin-top:6px">{_badge(state, state)}</div></div>')
    return '<div class="mx-stepper">' + "".join(parts) + "</div>"


def _readiness(rows: Iterable[tuple[str, str, str]]) -> str:
    body = "".join(f'<tr><td>{_safe(check)}</td><td>{_badge(status, status)}</td><td>{_safe(action)}</td></tr>' for check, status, action in rows)
    return '<table class="mx-matrix"><thead><tr><th>Scientific check</th><th>Status</th><th>Required action</th></tr></thead><tbody>' + body + "</tbody></table>"


def _cards(
    cards: Iterable[tuple[str, str]],
    *,
    module_key: str = "shared",
    surface: str = "detail",
) -> str:
    rendered: list[str] = []
    for index, (title, text) in enumerate(cards, 1):
        normalized_title = str(title).strip() or "Workspace detail"
        normalized_text = str(text).strip() or "No module-specific detail is available."
        card_id = f"{module_key}-{surface}-{index:02d}"
        rendered.append(
            f'<div class="mx-card" role="group" aria-label="{_safe(normalized_title)}" '
            f'data-biointel-card-id="{_safe(card_id)}" data-biointel-card-surface="{_safe(surface)}">'
            f'<b>{_safe(normalized_title)}</b><span>{_safe(normalized_text)}</span></div>'
        )
    return '<div class="mx-grid">' + "".join(rendered) + "</div>"


def workspace_summary_cards(spec: ModuleExperienceSpec) -> tuple[tuple[str, str], ...]:
    """Build six complete, module-specific cards for collapsed workspace summaries."""
    status_counts: dict[str, int] = {}
    for _, status, _ in spec.readiness:
        normalized = str(status).strip().title() or "Unknown"
        status_counts[normalized] = status_counts.get(normalized, 0) + 1
    readiness_summary = " · ".join(
        f"{status}: {count}" for status, count in sorted(status_counts.items())
    )
    workflow_summary = " → ".join(step.strip() for step in spec.workflow if step.strip())
    handoff_summary = " · ".join(target.strip() for target in spec.handoffs if target.strip())
    return (
        ("Primary canvas", spec.primary_canvas),
        ("Focus entity", spec.entity_type),
        ("Workflow coverage", workflow_summary),
        ("Readiness checks", f"{len(spec.readiness)} checks · {readiness_summary}"),
        ("Handoff targets", handoff_summary),
        ("Evidence boundary", spec.evidence_level),
    )


def validate_workspace_summary(spec: ModuleExperienceSpec) -> tuple[str, ...]:
    """Return deterministic completeness issues for a module summary."""
    issues: list[str] = []
    cards = workspace_summary_cards(spec)
    if len(cards) != 6:
        issues.append(f"expected 6 cards, found {len(cards)}")
    titles = [title.strip() for title, _ in cards]
    if len(set(titles)) != len(titles):
        issues.append("duplicate card titles")
    for index, (title, value) in enumerate(cards, 1):
        if not title.strip():
            issues.append(f"card {index} title is empty")
        if not value.strip():
            issues.append(f"card {index} value is empty")
        if len(value.strip()) < 3:
            issues.append(f"card {index} value is too short")
    if not spec.handoffs:
        issues.append("no handoff targets")
    if not spec.workflow:
        issues.append("no workflow stages")
    if not spec.readiness:
        issues.append("no readiness checks")
    return tuple(issues)


def _svg_wrap(content: str, label: str, viewbox: str = "0 0 900 390") -> str:
    return f'<svg class="mx-canvas" viewBox="{viewbox}" role="img" aria-label="{_safe(label)}" xmlns="http://www.w3.org/2000/svg"><title>{_safe(label)}</title>{content}</svg>'


def _canvas_for_group(spec: ModuleExperienceSpec, selected: str, mode: str) -> str:
    label = f"{spec.title} · {spec.primary_canvas}"
    if spec.group == "sequence_genomics":
        content = (
            '<text x="26" y="34" fill="#dfeaff" font-size="18">Coordinate and evidence canvas</text>'
            '<rect x="55" y="78" width="790" height="28" rx="12" fill="#173756"/>'
            '<rect x="110" y="84" width="130" height="16" rx="6" fill="#4accc2"/>'
            '<rect x="295" y="84" width="95" height="16" rx="6" fill="#6d83ef"/>'
            '<rect x="455" y="84" width="170" height="16" rx="6" fill="#b56fe2"/>'
            '<rect x="690" y="84" width="90" height="16" rx="6" fill="#f0a34a"/>'
            '<text x="55" y="138" fill="#9fb1cb" font-size="13">Reference / feature tracks</text>'
            '<path d="M75 190 C180 130 245 250 350 185 S530 135 650 190 S760 225 835 165" fill="none" stroke="#56d5c9" stroke-width="4"/>'
            '<circle cx="350" cy="185" r="9" fill="#ffcf68"/><circle cx="650" cy="190" r="9" fill="#ff7e96"/>'
            '<rect x="65" y="250" width="770" height="82" rx="14" fill="#10233c" stroke="#315171"/>'
            '<text x="88" y="280" fill="#f0f5ff" font-size="15">Selected entity</text>'
            f'<text x="88" y="308" fill="#9fded5" font-size="14">{_safe(selected)}</text>'
            f'<text x="570" y="308" fill="#b4c4dc" font-size="13">Mode: {_safe(mode)}</text>'
        )
        return _svg_wrap(content, label)
    if spec.group == "pathogen_longread":
        content = (
            '<text x="26" y="34" fill="#dfeaff" font-size="18">Assembly, lineage and outbreak canvas</text>'
            '<defs><marker id="mxarr" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#62d6cb"/></marker></defs>'
            '<circle cx="130" cy="205" r="55" fill="#183a56" stroke="#5ad6cc" stroke-width="3"/>'
            '<circle cx="365" cy="105" r="48" fill="#27375d" stroke="#7c92f4" stroke-width="3"/>'
            '<circle cx="365" cy="300" r="48" fill="#442b4a" stroke="#d577c8" stroke-width="3"/>'
            '<circle cx="650" cy="205" r="62" fill="#3b3323" stroke="#f0b052" stroke-width="3"/>'
            '<path d="M185 190 L315 125" stroke="#62d6cb" stroke-width="4" marker-end="url(#mxarr)"/>'
            '<path d="M185 220 L315 280" stroke="#62d6cb" stroke-width="4" marker-end="url(#mxarr)"/>'
            '<path d="M413 118 L590 185" stroke="#62d6cb" stroke-width="4" marker-end="url(#mxarr)"/>'
            '<path d="M413 286 L590 225" stroke="#62d6cb" stroke-width="4" marker-end="url(#mxarr)"/>'
            '<text x="130" y="210" text-anchor="middle" fill="#edf6ff">Input</text><text x="365" y="110" text-anchor="middle" fill="#edf6ff">Lineage A</text><text x="365" y="305" text-anchor="middle" fill="#edf6ff">Lineage B</text><text x="650" y="210" text-anchor="middle" fill="#fff2d6">Review</text>'
            f'<text x="720" y="330" fill="#9fded5" font-size="13">{_safe(selected)} · {_safe(mode)}</text>'
        )
        return _svg_wrap(content, label)
    if spec.group == "omics_spatial":
        cells = "".join(f'<circle cx="{120 + (i % 12) * 52}" cy="{85 + (i // 12) * 52}" r="{8 + (i % 4)}" fill="{["#4ecdc4","#7c86f4","#d875c8","#f3b55d"][i % 4]}" opacity=".82"/>' for i in range(48))
        content = (
            '<text x="26" y="34" fill="#dfeaff" font-size="18">Sample, cell and feature selection canvas</text>'
            f'{cells}'
            '<rect x="710" y="70" width="150" height="230" rx="14" fill="#10233c" stroke="#315171"/>'
            '<text x="730" y="100" fill="#eff5ff">Selection</text><text x="730" y="132" fill="#9fb1cb">Cluster: 3</text><text x="730" y="160" fill="#9fb1cb">Condition: treated</text><text x="730" y="188" fill="#9fb1cb">Batch: B2</text><text x="730" y="216" fill="#9fb1cb">Cells: 184</text>'
            f'<text x="730" y="265" fill="#9fded5">{_safe(selected)}</text><text x="730" y="288" fill="#b4c4dc">{_safe(mode)}</text>'
        )
        return _svg_wrap(content, label)
    if spec.group == "protein_discovery":
        content = (
            '<text x="26" y="34" fill="#dfeaff" font-size="18">Structure, sequence and evidence workspace</text>'
            '<path d="M95 200 C170 80 245 310 330 165 S470 95 560 210 S690 300 800 135" fill="none" stroke="#65d4ca" stroke-width="8" opacity=".72"/>'
            '<circle cx="330" cy="165" r="15" fill="#ffd064"/><circle cx="560" cy="210" r="15" fill="#ef7a9a"/>'
            '<polygon points="610,105 650,125 642,170 600,178 575,140" fill="#9b72df" stroke="#e8ddff" stroke-width="2"/>'
            '<rect x="70" y="285" width="760" height="54" rx="12" fill="#10233c" stroke="#315171"/>'
            '<text x="92" y="318" fill="#eaf2ff">Sequence / structure / assay evidence synchronized</text>'
            f'<text x="620" y="318" fill="#9fded5">{_safe(selected)}</text>'
        )
        return _svg_wrap(content, label)
    if spec.group == "analytical_imaging":
        tiles = "".join(f'<rect x="{70 + (i % 6) * 95}" y="{70 + (i // 6) * 76}" width="78" height="58" rx="8" fill="{["#183950","#25436a","#4a3154","#5b4729"][i % 4]}" stroke="#6a88aa"/><circle cx="{108 + (i % 6) * 95}" cy="{99 + (i // 6) * 76}" r="{8 + i % 6}" fill="{["#50d0c6","#8c8ff4","#e77ab3","#f0b45b"][i % 4]}" opacity=".82"/>' for i in range(18))
        content = (
            '<text x="26" y="34" fill="#dfeaff" font-size="18">Raw evidence and object review canvas</text>'
            f'{tiles}'
            '<rect x="665" y="70" width="190" height="210" rx="14" fill="#10233c" stroke="#315171"/>'
            '<text x="688" y="103" fill="#eff5ff">Review queue</text><text x="688" y="137" fill="#9fb1cb">Accepted: 31</text><text x="688" y="165" fill="#9fb1cb">Review: 7</text><text x="688" y="193" fill="#9fb1cb">Rejected: 2</text>'
            f'<text x="688" y="238" fill="#9fded5">{_safe(selected)}</text>'
        )
        return _svg_wrap(content, label)
    if spec.group == "wetlab_design":
        wells = "".join(f'<circle cx="{120 + (i % 12) * 54}" cy="{82 + (i // 12) * 54}" r="17" fill="{["#315b96","#8e5ec7","#2e9b78","#4a566c"][i % 4]}" stroke="#a8b9d2"><title>Well {i + 1}</title></circle>' for i in range(48))
        content = (
            '<text x="26" y="34" fill="#dfeaff" font-size="18">Protocol, allocation and quality workspace</text>'
            f'{wells}'
            '<rect x="735" y="74" width="130" height="228" rx="14" fill="#10233c" stroke="#315171"/>'
            '<text x="756" y="106" fill="#eff5ff">Run state</text><text x="756" y="142" fill="#9fb1cb">Controls: 8</text><text x="756" y="170" fill="#9fb1cb">Samples: 30</text><text x="756" y="198" fill="#9fb1cb">Review: 6</text>'
            f'<text x="756" y="250" fill="#9fded5">{_safe(mode)}</text>'
        )
        return _svg_wrap(content, label)
    if spec.group == "ai_models":
        content = (
            '<text x="26" y="34" fill="#dfeaff" font-size="18">Model lifecycle, evidence and approval workspace</text>'
            '<defs><marker id="mxaiarr" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#62d6cb"/></marker></defs>'
            '<rect x="50" y="145" width="125" height="78" rx="14" fill="#173756"/><rect x="225" y="145" width="125" height="78" rx="14" fill="#173756"/><rect x="400" y="145" width="125" height="78" rx="14" fill="#25385f"/><rect x="575" y="145" width="125" height="78" rx="14" fill="#4b334f"/><rect x="750" y="145" width="100" height="78" rx="14" fill="#3c3424"/>'
            '<text x="112" y="188" text-anchor="middle" fill="#eff5ff">Register</text><text x="287" y="188" text-anchor="middle" fill="#eff5ff">Train</text><text x="462" y="188" text-anchor="middle" fill="#eff5ff">Validate</text><text x="637" y="188" text-anchor="middle" fill="#eff5ff">Review</text><text x="800" y="188" text-anchor="middle" fill="#fff2d6">Approve</text>'
            '<path d="M175 184 L225 184" stroke="#62d6cb" stroke-width="4" marker-end="url(#mxaiarr)"/><path d="M350 184 L400 184" stroke="#62d6cb" stroke-width="4" marker-end="url(#mxaiarr)"/><path d="M525 184 L575 184" stroke="#62d6cb" stroke-width="4" marker-end="url(#mxaiarr)"/><path d="M700 184 L750 184" stroke="#62d6cb" stroke-width="4" marker-end="url(#mxaiarr)"/>'
            f'<text x="50" y="290" fill="#9fded5">Selected: {_safe(selected)}</text><text x="580" y="290" fill="#b4c4dc">Mode: {_safe(mode)}</text>'
        )
        return _svg_wrap(content, label)
    content = (
        '<text x="26" y="34" fill="#dfeaff" font-size="18">Lineage, readiness and governance workspace</text>'
        '<defs><marker id="mxdataarr" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#62d6cb"/></marker></defs>'
        '<rect x="60" y="145" width="160" height="80" rx="14" fill="#173756"/><rect x="310" y="70" width="180" height="80" rx="14" fill="#25385f"/><rect x="310" y="250" width="180" height="80" rx="14" fill="#3f304b"/><rect x="600" y="145" width="220" height="80" rx="14" fill="#1d4d45"/>'
        '<text x="140" y="190" text-anchor="middle" fill="#eff5ff">Physical asset</text><text x="400" y="115" text-anchor="middle" fill="#eff5ff">Curated version</text><text x="400" y="295" text-anchor="middle" fill="#eff5ff">Evidence links</text><text x="710" y="190" text-anchor="middle" fill="#eafff9">Release snapshot</text>'
        '<path d="M220 170 L310 115" stroke="#62d6cb" stroke-width="4" marker-end="url(#mxdataarr)"/><path d="M220 200 L310 285" stroke="#62d6cb" stroke-width="4" marker-end="url(#mxdataarr)"/><path d="M490 115 L600 170" stroke="#62d6cb" stroke-width="4" marker-end="url(#mxdataarr)"/><path d="M490 285 L600 205" stroke="#62d6cb" stroke-width="4" marker-end="url(#mxdataarr)"/>'
        f'<text x="60" y="355" fill="#9fded5">{_safe(selected)}</text><text x="650" y="355" fill="#b4c4dc">{_safe(mode)}</text>'
    )
    return _svg_wrap(content, label)


def _default_selected(spec: ModuleExperienceSpec) -> str:
    examples = {
        "sequence_genomics": "Selected genomic entity",
        "pathogen_longread": "Selected isolate or assembly",
        "omics_spatial": "Selected sample or cell state",
        "protein_discovery": "Selected protein or compound",
        "analytical_imaging": "Selected peak or object",
        "wetlab_design": "Selected run or plate",
        "ai_models": "Selected model version",
        "data_evidence": "Selected dataset or evidence record",
    }
    return examples[spec.group]


def _state_key(prefix: str, suffix: str) -> str:
    return f"{prefix}_{suffix}"


def _notebook_events(prefix: str) -> list[dict[str, str]]:
    key = _state_key(prefix, "notebook_events")
    if key not in st.session_state:
        st.session_state[key] = [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "type": "System",
                "note": "Interactive module workspace opened.",
            }
        ]
    return st.session_state[key]


def _render_workspace(spec: ModuleExperienceSpec, prefix: str) -> dict[str, Any]:
    c1, c2, c3 = st.columns([1.2, 1, 1])
    selected = c1.text_input("Selected entity", value=_default_selected(spec), key=_state_key(prefix, "selected_entity"))
    mode = c2.selectbox("Workspace mode", ["Review", "Compare", "Validate", "Prepare handoff"], key=_state_key(prefix, "mode"))
    compact = c3.toggle("Compact canvas", value=False, key=_state_key(prefix, "compact"))

    st.markdown(
        f'<div class="mx-shell"><div class="mx-header"><div><div class="mx-title">{_safe(spec.icon)} {_safe(spec.primary_canvas)}</div><div class="mx-sub">The canvas is deterministic, offline and synchronized with the current module context. It does not replace specialist external engines or independent validation.</div></div><div class="mx-badges">{_badge("Evidence", spec.evidence_level)}{_badge("Selected", "Active")}{_badge("State", "Saved locally")}</div></div>{_stepper(spec.workflow, 2)}{_canvas_for_group(spec, selected, mode)}</div>',
        unsafe_allow_html=True,
    )

    if not compact:
        st.markdown(_readiness(spec.readiness), unsafe_allow_html=True)

    st.markdown("##### Interactive before / after inspector")
    before_svg = comparison_state_svg(
        title=spec.primary_canvas,
        label="Raw · unreviewed · default parameters",
        after=False,
        motif=GROUP_LABELS[spec.group],
    )
    after_svg = comparison_state_svg(
        title=spec.primary_canvas,
        label="Validated · reviewed · provenance saved",
        after=True,
        motif=GROUP_LABELS[spec.group],
    )
    render_before_after_comparison(
        before_svg=before_svg,
        after_svg=after_svg,
        key=f"{prefix}_before_after",
        before_label="Input state",
        after_label="Current state",
        height=420,
        caption="Drag the handle or use the keyboard slider to inspect state changes. Underlying scientific data and parameters remain exportable separately.",
    )

    st.markdown("##### Decision cards")
    st.markdown(_cards((("What was found", f"{selected} is active in {mode.lower()} mode."), ("Why it matters", "The selected entity drives synchronized evidence, readiness and handoff panels."), ("Recommended action", "Resolve all Review or Pending checks before scientific release."), ("Limitations", "Specialist databases, external tools and independent validation may still be required."))), unsafe_allow_html=True)
    return {"selected_entity": selected, "mode": mode, "compact": compact}


def _render_passport(spec: ModuleExperienceSpec, prefix: str) -> dict[str, Any]:
    identifier = st.text_input("Entity identifier", value=f"{spec.key.upper()}-001", key=_state_key(prefix, "passport_id"))
    status = st.selectbox("Review status", ["Draft", "Reviewed", "Approved for research", "Blocked"], key=_state_key(prefix, "passport_status"))
    owner = st.text_input("Owner / reviewer", value="Local researcher", key=_state_key(prefix, "passport_owner"))
    warnings = st.multiselect("Warnings", ["Reference version required", "External validation pending", "Small sample size", "Missing metadata", "Out-of-domain result"], default=["External validation pending"], key=_state_key(prefix, "passport_warnings"))
    related = [spec.title, *spec.handoffs[:3]]
    fields = (
        ("Identity", identifier),
        ("Entity type", spec.entity_type),
        ("Status", status),
        ("Owner", owner),
        ("Evidence boundary", spec.evidence_level),
        ("Related workspaces", " · ".join(related)),
    )
    html_fields = "".join(f'<div class="mx-field"><small>{_safe(label)}</small><b>{_safe(value)}</b></div>' for label, value in fields)
    st.markdown(f'<div class="mx-shell"><div class="mx-title">Entity Passport</div><div class="mx-sub">Reusable identity, evidence, warning and action record for the selected scientific entity.</div><div class="mx-passport">{html_fields}</div><div style="margin-top:10px">{"".join(_badge(w, "Review") for w in warnings) if warnings else _badge("Warnings", "None")}</div></div>', unsafe_allow_html=True)
    return {"identifier": identifier, "status": status, "owner": owner, "warnings": warnings}


def _render_replay(spec: ModuleExperienceSpec, prefix: str) -> dict[str, Any]:
    st.markdown(f'<div class="mx-shell"><div class="mx-title">Decision Replay</div><div class="mx-sub">Reconstruct how the current interpretation was produced without relying on hidden state.</div>{_stepper(spec.workflow, 3)}</div>', unsafe_allow_html=True)
    prompts: list[dict[str, str]] = []
    for index, prompt in enumerate(spec.decision_prompts, 1):
        response = st.selectbox(prompt, ["Pass", "Review", "Blocked", "Not assessed"], index=1 if index > 1 else 0, key=_state_key(prefix, f"decision_{index}"))
        rationale = st.text_input(f"Rationale {index}", value="Recorded in the analysis manifest.", key=_state_key(prefix, f"rationale_{index}"))
        prompts.append({"question": prompt, "response": response, "rationale": rationale})
    timeline = "".join(f'<div class="mx-event"><b>{_safe(item["response"])} · {_safe(item["question"])}</b><span>{_safe(item["rationale"])}</span></div>' for item in prompts)
    st.markdown(f'<div class="mx-shell"><div class="mx-timeline">{timeline}</div></div>', unsafe_allow_html=True)
    return {"decisions": prompts}


def _render_handoff(spec: ModuleExperienceSpec, prefix: str) -> dict[str, Any]:
    destination = st.selectbox("Handoff destination", list(spec.handoffs), key=_state_key(prefix, "handoff_destination"))
    include = st.multiselect("Include in handoff", ["Selected entity", "Filtered table", "Viewer state", "Parameters", "Evidence links", "Reviewer notes", "Input hashes"], default=["Selected entity", "Parameters", "Evidence links", "Input hashes"], key=_state_key(prefix, "handoff_include"))
    st.markdown(f'<div class="mx-shell"><div class="mx-title">Cross-Module Handoff Board</div><div class="mx-sub">Only explicit, versioned state is transferred. The destination module must revalidate compatibility.</div><div class="mx-handoff"><div class="mx-node">{_safe(spec.title)}</div><div class="mx-node">Compatibility validation</div><div class="mx-node">{_safe(destination)}</div><div class="mx-node">Provenance confirmation</div></div>{_cards((("Transfer type", "Versioned local manifest"), ("Selected content", str(len(include)) + " items"), ("Compatibility", "Must be rechecked"), ("Data movement", "No hidden network transfer")))}</div>', unsafe_allow_html=True)
    return {"destination": destination, "include": include}


def _render_notebook(spec: ModuleExperienceSpec, prefix: str) -> dict[str, Any]:
    events = _notebook_events(prefix)
    note_type = st.selectbox("Notebook entry type", ["Observation", "Decision", "Limitation", "Follow-up", "Approval note"], key=_state_key(prefix, "note_type"))
    note = st.text_area("Notebook entry", key=_state_key(prefix, "note_text"), placeholder="Record a scientific observation, decision or follow-up.")
    if st.button("Add notebook entry", key=_state_key(prefix, "add_note"), type="primary"):
        if note.strip():
            events.append({"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "type": note_type, "note": note.strip()})
            st.rerun()
        else:
            st.warning("Enter a note before adding it to the scientific notebook.")
    rendered = "".join(f'<div class="mx-event"><b>{_safe(event["type"])} · {_safe(event["timestamp"])}</b><span>{_safe(event["note"])}</span></div>' for event in reversed(events[-20:]))
    st.markdown(f'<div class="mx-shell"><div class="mx-title">Scientific Notebook Timeline</div><div class="mx-sub">The timeline is stored in the current local Streamlit session and included in the exported workspace state.</div><div class="mx-timeline">{rendered}</div></div>', unsafe_allow_html=True)
    return {"events": list(events)}


def render_module_experience(module_key: str, *, key_prefix: str | None = None, expanded: bool = False) -> None:
    if module_key not in MODULE_EXPERIENCE_CATALOG:
        st.error(f"Unknown Step 116 module experience: {module_key}")
        return
    _inject_css()
    spec = MODULE_EXPERIENCE_CATALOG[module_key]
    prefix = key_prefix or f"step116_{module_key}"
    st.divider()
    st.markdown(f"#### {spec.icon} Interactive Scientific Workspace")
    st.caption(f"{spec.title}: non-chart inspection, entity passport, decision replay, cross-module handoff and scientific notebook.")
    if not st.toggle("Open interactive module workspace", value=expanded, key=_state_key(prefix, "open")):
        st.markdown(
            f'<div class="mx-shell mx-summary" data-biointel-module-workspace="summary" data-biointel-summary-schema="v2" data-biointel-module-key="{_safe(spec.key)}"><div class="mx-header"><div><div class="mx-title">{_safe(spec.title)}</div><div class="mx-sub">{_safe(spec.primary_canvas)}</div></div><div class="mx-badges">{_badge("Group", GROUP_LABELS[spec.group])}{_badge("Evidence", spec.evidence_level)}</div></div>{_cards(workspace_summary_cards(spec), module_key=spec.key, surface="summary")}</div>',
            unsafe_allow_html=True,
        )
        return

    try:
        section = st.radio(
            "Workspace section",
            ["Workspace", "Entity Passport", "Decision Replay", "Handoff", "Notebook & Export"],
            horizontal=True,
            key=_state_key(prefix, "active_section"),
        )
        state: dict[str, Any] = {
            "schema": "biointel.module-experience.v1",
            "version": "15.6.0",
            "module_key": module_key,
            "module_title": spec.title,
            "group": spec.group,
            "evidence_level": spec.evidence_level,
            "active_section": section,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if section == "Workspace":
            state["workspace"] = _render_workspace(spec, prefix)
        elif section == "Entity Passport":
            state["passport"] = _render_passport(spec, prefix)
        elif section == "Decision Replay":
            state["decision_replay"] = _render_replay(spec, prefix)
        elif section == "Handoff":
            state["handoff"] = _render_handoff(spec, prefix)
        else:
            state["notebook"] = _render_notebook(spec, prefix)
            state["saved_widget_state"] = {
                key: value
                for key, value in st.session_state.items()
                if key.startswith(prefix) and not key.endswith("download_state")
            }
            export_name = f"biointel_{module_key}_interactive_workspace.json"
            st.download_button(
                "Download complete workspace state",
                data=json.dumps(state, indent=2, ensure_ascii=False, default=str),
                file_name=export_name,
                mime="application/json",
                key=_state_key(prefix, "download_state"),
            )
            st.info("The export contains local UI state and reviewer notes. It does not certify scientific validity or replace source-data archives.")
    except Exception as exc:  # pragma: no cover - exercised by runtime guards
        error_id = hashlib.sha256(f"{module_key}:{type(exc).__name__}:{exc}".encode("utf-8")).hexdigest()[:12].upper()
        st.error(f"The interactive module workspace could not render safely. Error ID: MX-{error_id}")
        diagnostic = {
            "error_id": f"MX-{error_id}",
            "module_key": module_key,
            "module_title": spec.title,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        with st.expander("Diagnostic details"):
            render_operational_canvas(
                "Workspace diagnostic",
                diagnostic,
                workflow=("Workspace request", "Safe recovery", "Support detail", "Retry"),
            )
            st.download_button(
                "Download diagnostic",
                data=json.dumps(diagnostic, indent=2),
                file_name=f"biointel_{module_key}_workspace_error.json",
                mime="application/json",
                key=_state_key(prefix, "diagnostic_download"),
            )


def render_module_experience_hub() -> None:
    _inject_css()
    st.markdown("### Interactive Module Experience Hub · Sections 2–9")
    st.caption("Explore non-chart canvases, entity passports, decision replay, handoff manifests and notebook timelines across eight scientific module groups.")
    group = st.selectbox("Module group", list(GROUP_LABELS), format_func=lambda key: GROUP_LABELS[key], key="mx_hub_group")
    query = st.text_input("Search modules", placeholder="variant, single-cell, protein, dataset…", key="mx_hub_query")
    candidates = [spec for spec in MODULE_EXPERIENCE_CATALOG.values() if spec.group == group]
    if query.strip():
        token = query.lower().strip()
        candidates = [spec for spec in candidates if token in (spec.title + " " + spec.primary_canvas + " " + " ".join(spec.handoffs)).lower()]
    if not candidates:
        st.info("No modules match the current search.")
        return
    selected = st.selectbox("Open module workspace", [spec.key for spec in candidates], format_func=lambda key: MODULE_EXPERIENCE_CATALOG[key].title, key="mx_hub_module")
    spec = MODULE_EXPERIENCE_CATALOG[selected]
    st.markdown(_cards((("Module", spec.title), ("Group", GROUP_LABELS[spec.group]), ("Entity type", spec.entity_type), ("Primary canvas", spec.primary_canvas), ("Handoff destinations", " · ".join(spec.handoffs)), ("Evidence state", spec.evidence_level))), unsafe_allow_html=True)
    render_module_experience(selected, key_prefix=f"mx_hub_{selected}", expanded=True)


__all__ = [
    "GROUP_LABELS",
    "MODULE_EXPERIENCE_CATALOG",
    "ModuleExperienceSpec",
    "render_module_experience",
    "render_module_experience_hub",
    "validate_workspace_summary",
    "workspace_summary_cards",
]
