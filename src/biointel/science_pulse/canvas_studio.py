from __future__ import annotations

import html
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd
import streamlit as st


CANVAS_SCHEMA_VERSION = "science_plus_canvas_v1"
CARD_STATUSES = ("Prompt", "Planned", "In progress", "Needs evidence", "In review", "Complete", "Blocked")
WORKSPACE_STATUSES = ("Draft", "Active", "In review", "Complete", "Archived")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_segment(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip(".-")
    return (cleaned[:80] or fallback).lower()


def _card(column: str, title: str, guidance: str, *, tags: Sequence[str] = ()) -> dict[str, Any]:
    return {
        "column": column,
        "title": title,
        "guidance": guidance,
        "notes": "",
        "status": "Prompt",
        "owner": "",
        "due_date": "",
        "tags": list(tags),
        "evidence_ids": [],
    }


@dataclass(frozen=True, slots=True)
class CanvasTemplate:
    key: str
    title: str
    category: str
    icon: str
    description: str
    canvas_type: str
    columns: tuple[str, ...]
    starter_cards: tuple[dict[str, Any], ...]
    workflow: tuple[str, ...]
    tags: tuple[str, ...] = ()


def _template(
    key: str,
    title: str,
    category: str,
    icon: str,
    description: str,
    canvas_type: str,
    columns: Sequence[str],
    prompts: Sequence[tuple[str, str, str]],
    workflow: Sequence[str],
    tags: Sequence[str] = (),
) -> CanvasTemplate:
    return CanvasTemplate(
        key=key,
        title=title,
        category=category,
        icon=icon,
        description=description,
        canvas_type=canvas_type,
        columns=tuple(columns),
        starter_cards=tuple(_card(column, title_, guidance) for column, title_, guidance in prompts),
        workflow=tuple(workflow),
        tags=tuple(tags),
    )


TEMPLATES: tuple[CanvasTemplate, ...] = (
    _template(
        "research-question", "Research Question Builder", "Core Research", "❓",
        "Turn a broad topic into a bounded, answerable and evidence-ready scientific question.", "board",
        ("Context", "Question", "Variables", "Boundaries", "Decision"),
        (
            ("Context", "Problem landscape", "Describe the scientific problem, population and why it matters."),
            ("Question", "Primary question", "Write one precise question that can be answered with available evidence or data."),
            ("Variables", "Inputs and outcomes", "Define exposures, interventions, comparators, outcomes and covariates."),
            ("Boundaries", "Scope and exclusions", "Record organisms, tissues, dates, geographies, modalities and exclusion rules."),
            ("Decision", "Success criterion", "State what result would change the next scientific or operational decision."),
        ),
        ("Frame", "Bound", "Validate", "Search", "Decide"), ("question", "scope", "PICOT"),
    ),
    _template(
        "hypothesis-experiment", "Hypothesis & Experiment Canvas", "Core Research", "🧪",
        "Design a falsifiable hypothesis, controls, measurements and analysis path before execution.", "board",
        ("Observation", "Hypothesis", "Design", "Controls", "Analysis", "Decision"),
        (
            ("Observation", "Starting observation", "Record the source-linked observation or gap motivating the experiment."),
            ("Hypothesis", "Falsifiable statement", "Write the predicted relationship and an explicit null alternative."),
            ("Design", "Experimental units", "Define samples, replicates, perturbations, time points and measurement platform."),
            ("Controls", "Control strategy", "List positive, negative, vehicle, batch and process controls."),
            ("Analysis", "Analysis plan", "Specify quality gates, statistical model, multiple-testing policy and sensitivity checks."),
            ("Decision", "Go / no-go rule", "Define thresholds and the next action for positive, negative or ambiguous results."),
        ),
        ("Observe", "Hypothesise", "Design", "Execute", "Analyse", "Decide"), ("experiment", "controls", "analysis"),
    ),
    _template(
        "study-design", "Study Design Blueprint", "Core Research", "📐",
        "Plan cohorts, sampling, endpoints, bias controls and a reproducible analysis contract.", "board",
        ("Objective", "Population", "Design", "Measurements", "Statistics", "Governance"),
        (
            ("Objective", "Primary objective", "State the primary estimand or scientific objective."),
            ("Population", "Eligibility and sampling", "Define inclusion, exclusion, recruitment and sampling frame."),
            ("Design", "Arms and allocation", "Describe observational or interventional design, allocation and blinding."),
            ("Measurements", "Endpoints and schedule", "Define primary/secondary outcomes, instruments and measurement timing."),
            ("Statistics", "Power and analysis", "Record assumptions, sample-size logic, analysis sets and missing-data policy."),
            ("Governance", "Ethics and data plan", "Capture consent, privacy, monitoring, lineage and retention requirements."),
        ),
        ("Objective", "Protocol", "Power", "Approve", "Run", "Report"), ("study", "cohort", "statistics"),
    ),
    _template(
        "systematic-review", "Systematic Review / PRISMA Canvas", "Evidence & Literature", "📚",
        "Manage protocol, search, screening, extraction, bias assessment and synthesis without inventing evidence.", "board",
        ("Protocol", "Search", "Screening", "Extraction", "Bias", "Synthesis"),
        (
            ("Protocol", "Review question and registration", "Record protocol identifier, eligibility rules and planned synthesis."),
            ("Search", "Search strategy", "Capture databases, exact queries, dates and deduplication approach."),
            ("Screening", "Screening decisions", "Track title/abstract and full-text decisions with exclusion reasons."),
            ("Extraction", "Extraction schema", "Define study characteristics, outcomes and units to extract."),
            ("Bias", "Risk-of-bias method", "Select the appropriate instrument and decision rules."),
            ("Synthesis", "Synthesis plan", "Specify qualitative or quantitative synthesis and heterogeneity checks."),
        ),
        ("Register", "Search", "Screen", "Extract", "Assess", "Synthesize"), ("PRISMA", "review", "evidence"),
    ),
    _template(
        "literature-review", "Literature Review Matrix", "Evidence & Literature", "🔎",
        "Compare papers by question, method, population, result, limitation and relevance.", "matrix",
        ("Candidate", "Included", "Compared", "Critical appraisal", "Synthesis"),
        (
            ("Candidate", "Search candidates", "Attach persisted Science Plus records or add source identifiers."),
            ("Included", "Eligibility decision", "Document why each source is included and which question it informs."),
            ("Compared", "Method and findings", "Extract design, sample, assay, effect and uncertainty consistently."),
            ("Critical appraisal", "Limitations and bias", "Record confounding, selection, measurement and reporting limitations."),
            ("Synthesis", "Cross-paper conclusion", "Separate convergent evidence, disagreement and unresolved gaps."),
        ),
        ("Find", "Select", "Extract", "Appraise", "Synthesize"), ("literature", "matrix", "appraisal"),
    ),
    _template(
        "evidence-synthesis", "Evidence Synthesis Board", "Evidence & Literature", "⚖️",
        "Map claims to supporting, conflicting and missing evidence with confidence and provenance.", "board",
        ("Claim", "Supporting", "Conflicting", "Quality", "Gap", "Conclusion"),
        (
            ("Claim", "Decision-relevant claim", "Write a bounded claim without exceeding the available evidence."),
            ("Supporting", "Supporting evidence", "Attach records and note directness, effect and uncertainty."),
            ("Conflicting", "Contradictory evidence", "Capture credible disagreement and possible reasons."),
            ("Quality", "Evidence quality", "Assess source quality, bias, consistency and applicability."),
            ("Gap", "Missing evidence", "List the observation, cohort or experiment needed to reduce uncertainty."),
            ("Conclusion", "Calibrated conclusion", "State what is supported, uncertain and not supported."),
        ),
        ("Claim", "Collect", "Challenge", "Grade", "Conclude"), ("claims", "confidence", "provenance"),
    ),
    _template(
        "citation-map", "Citation & Influence Map", "Evidence & Literature", "🕸️",
        "Trace foundational work, method lineages, replication, correction and downstream influence.", "graph",
        ("Seed papers", "Foundations", "Methods", "Replications", "Challenges", "Current frontier"),
        (
            ("Seed papers", "Anchor publications", "Attach the central publication records and identifiers."),
            ("Foundations", "Foundational evidence", "Map earlier concepts, datasets and methods used by the anchors."),
            ("Methods", "Method lineage", "Trace assay, algorithm, model or protocol inheritance."),
            ("Replications", "Independent replication", "Record independent confirmations and their context."),
            ("Challenges", "Corrections and disputes", "Track retractions, corrections, failed replications and critiques."),
            ("Current frontier", "Latest extensions", "Attach recent work that changes the scientific boundary."),
        ),
        ("Anchor", "Trace", "Verify", "Compare", "Update"), ("citation", "lineage", "influence"),
    ),
    _template(
        "paper-reading", "Scientific Paper Reading Canvas", "Evidence & Literature", "📄",
        "Read one paper systematically from question through methods, results, limitations and reuse.", "board",
        ("Identity", "Question", "Methods", "Results", "Limitations", "Reuse"),
        (
            ("Identity", "Paper identity", "Record DOI/PMID, version, journal or preprint server and trust state."),
            ("Question", "Question and contribution", "State the question and claimed contribution in your own words."),
            ("Methods", "Methods audit", "Capture design, data, sample, model, controls and reproducibility assets."),
            ("Results", "Key results", "Record effect sizes, uncertainty, negative results and figure references."),
            ("Limitations", "Limitations", "Separate author-stated limitations from reviewer-observed risks."),
            ("Reuse", "Reuse decision", "State whether the evidence, method or data can be reused and under which constraints."),
        ),
        ("Identify", "Read", "Audit", "Interpret", "Reuse"), ("paper", "reading", "critical appraisal"),
    ),
    _template(
        "genomics-variant", "Genomics & Variant Interpretation Canvas", "Omics & Genomics", "🧬",
        "Organize variant evidence, phenotype fit, inheritance, population frequency and classification rationale.", "board",
        ("Case", "Variant", "Evidence", "Phenotype", "Classification", "Action"),
        (
            ("Case", "Case context", "Record consent boundary, phenotype terms, pedigree and assay scope."),
            ("Variant", "Candidate variants", "Capture assembly, locus, allele, transcript and quality metrics."),
            ("Evidence", "Variant evidence", "Attach population, computational, functional and literature evidence."),
            ("Phenotype", "Phenotype and inheritance fit", "Assess gene-disease validity, segregation and phenotypic concordance."),
            ("Classification", "Classification rationale", "Document criterion-level evidence and uncertainty; do not automate clinical sign-out."),
            ("Action", "Review action", "Define validation, reanalysis or expert-review next steps."),
        ),
        ("Ingest", "Filter", "Annotate", "Review", "Classify", "Handoff"), ("variant", "genomics", "phenotype"),
    ),
    _template(
        "multi-omics", "Multi-Omics Integration Canvas", "Omics & Genomics", "🧩",
        "Align cohorts, modalities, preprocessing, integration and cross-omics validation.", "board",
        ("Question", "Cohort", "Modalities", "Harmonisation", "Integration", "Validation"),
        (
            ("Question", "Biological question", "Define the cross-omics question and expected mechanistic resolution."),
            ("Cohort", "Sample map", "Map participants, biospecimens, time points and missing modality patterns."),
            ("Modalities", "Assays and feature spaces", "Record modality, platform, reference and measurement units."),
            ("Harmonisation", "QC and batch strategy", "Specify within-modality QC, normalization and batch diagnostics."),
            ("Integration", "Integration model", "Choose early, intermediate or late integration and define latent factors."),
            ("Validation", "Biological validation", "Plan pathway, held-out cohort, orthogonal assay and sensitivity validation."),
        ),
        ("Map", "QC", "Harmonise", "Integrate", "Validate", "Interpret"), ("multi-omics", "integration", "batch"),
    ),
    _template(
        "single-cell", "Single-Cell Analysis Canvas", "Omics & Genomics", "🔬",
        "Plan cell-level QC, integration, annotation, differential testing and trajectory interpretation.", "board",
        ("Samples", "QC", "Integration", "Annotation", "Comparisons", "Validation"),
        (
            ("Samples", "Sample and chemistry map", "Record tissue, condition, donor, chemistry, lanes and expected cell yield."),
            ("QC", "Cell and gene QC", "Define thresholds, doublet handling, ambient RNA checks and mitochondrial review."),
            ("Integration", "Batch integration", "Select integration strategy and checks that biological structure is preserved."),
            ("Annotation", "Cell identity", "Combine marker evidence, references and uncertainty labels."),
            ("Comparisons", "Differential and trajectory tests", "Define contrasts, pseudobulk strategy and trajectory assumptions."),
            ("Validation", "Validation", "Plan orthogonal markers, spatial context or external atlas mapping."),
        ),
        ("Ingest", "QC", "Integrate", "Annotate", "Test", "Validate"), ("single-cell", "atlas", "trajectory"),
    ),
    _template(
        "spatial-omics", "Spatial Omics Canvas", "Omics & Genomics", "🗺️",
        "Connect tissue regions, segmentation, spatial features, cell states and pathology context.", "map",
        ("Tissue map", "Image QC", "Regions", "Cell states", "Spatial tests", "Interpretation"),
        (
            ("Tissue map", "Tissue and section map", "Record specimen orientation, section order and matched assays."),
            ("Image QC", "Image and registration QC", "Document focus, artefacts, segmentation and cross-modality registration."),
            ("Regions", "Regions of interest", "Define pathology-informed and data-driven regions."),
            ("Cell states", "Cell-type and state mapping", "Record reference mapping, marker evidence and uncertainty."),
            ("Spatial tests", "Spatial hypotheses", "Specify neighbourhood, co-localisation and spatial differential tests."),
            ("Interpretation", "Mechanistic interpretation", "Connect spatial patterns to source-linked biological evidence."),
        ),
        ("Register", "Segment", "Annotate", "Test", "Interpret"), ("spatial", "pathology", "imaging"),
    ),
    _template(
        "transcriptomics", "Transcriptomics Expression Canvas", "Omics & Genomics", "📈",
        "Plan RNA-seq contrasts, QC, differential expression, pathways and validation.", "board",
        ("Design", "QC", "Model", "Genes", "Pathways", "Validation"),
        (
            ("Design", "Contrast design", "Define samples, covariates, paired structure and primary contrasts."),
            ("QC", "Read and sample QC", "Record library quality, mapping, duplication and sample outlier checks."),
            ("Model", "Statistical model", "Specify normalization, dispersion, design formula and multiple-testing control."),
            ("Genes", "Gene-level findings", "Track effect size, uncertainty, direction and annotation version."),
            ("Pathways", "Pathway interpretation", "Separate over-representation, rank-based and network evidence."),
            ("Validation", "Validation plan", "Plan qPCR, independent cohort or orthogonal assay validation."),
        ),
        ("Design", "QC", "Model", "Test", "Interpret", "Validate"), ("RNA-seq", "expression", "pathway"),
    ),
    _template(
        "proteomics-metabolomics", "Proteomics & Metabolomics Canvas", "Omics & Genomics", "🧫",
        "Coordinate feature identification, normalization, missingness, differential analysis and pathway interpretation.", "board",
        ("Assay", "Identification", "QC", "Quantification", "Statistics", "Biology"),
        (
            ("Assay", "Assay design", "Record sample preparation, acquisition method, batches and standards."),
            ("Identification", "Identification confidence", "Capture search space, FDR, library and ambiguous feature policy."),
            ("QC", "Analytical QC", "Track blanks, pooled QC, drift, carryover and batch behaviour."),
            ("Quantification", "Normalization and missingness", "Define normalization, imputation boundaries and censoring assumptions."),
            ("Statistics", "Differential analysis", "Specify contrasts, covariates, multiple testing and sensitivity checks."),
            ("Biology", "Pathway and biomarker context", "Link features to pathways and orthogonal evidence."),
        ),
        ("Acquire", "Identify", "QC", "Quantify", "Test", "Interpret"), ("proteomics", "metabolomics", "mass spectrometry"),
    ),
    _template(
        "pathway-mechanism", "Pathway & Mechanism Canvas", "Molecular & Drug Discovery", "🧠",
        "Build a source-linked mechanism from entities, interactions, perturbations and causal uncertainty.", "graph",
        ("Trigger", "Molecules", "Interactions", "Cellular effects", "Phenotype", "Evidence gaps"),
        (
            ("Trigger", "Perturbation or trigger", "Define disease context, exposure, mutation or treatment initiating the mechanism."),
            ("Molecules", "Key entities", "Add genes, proteins, metabolites, complexes and compartments."),
            ("Interactions", "Supported interactions", "Record direction, sign, context and source for each interaction."),
            ("Cellular effects", "Cell-state consequences", "Map signalling, transcriptional, metabolic and structural effects."),
            ("Phenotype", "Observed phenotype", "Connect molecular effects to measured cellular or organismal outcomes."),
            ("Evidence gaps", "Uncertain edges", "Flag inferred, conflicting or untested links."),
        ),
        ("Define", "Map", "Source", "Challenge", "Validate"), ("pathway", "mechanism", "network"),
    ),
    _template(
        "protein-structure", "Protein Structure Analysis Canvas", "Molecular & Drug Discovery", "🧱",
        "Organize sequence, structure quality, domains, sites, variants and functional hypotheses.", "board",
        ("Identity", "Structure", "Domains", "Sites", "Variants", "Hypotheses"),
        (
            ("Identity", "Protein identity", "Record accession, isoform, organism and sequence version."),
            ("Structure", "Structure evidence", "Attach experimental or predicted structures and quality metrics."),
            ("Domains", "Domain architecture", "Map domains, disorder, transmembrane regions and conserved motifs."),
            ("Sites", "Functional sites", "Record active, binding, modification and interaction sites with evidence."),
            ("Variants", "Variant mapping", "Map variants to structural context and avoid overclaiming functional impact."),
            ("Hypotheses", "Testable hypotheses", "Define experiments or simulations needed to test structural interpretations."),
        ),
        ("Identify", "Assess", "Annotate", "Map", "Hypothesise"), ("protein", "structure", "variant"),
    ),
    _template(
        "drug-discovery", "Drug Discovery Decision Canvas", "Molecular & Drug Discovery", "💊",
        "Move from target rationale through hit evidence, developability, validation and go/no-go decisions.", "board",
        ("Disease", "Target", "Hit", "Mechanism", "Developability", "Decision"),
        (
            ("Disease", "Disease and patient context", "Define unmet need, biology, population and current standard of care."),
            ("Target", "Target rationale", "Capture human genetics, expression, pathway and tractability evidence."),
            ("Hit", "Hit evidence", "Record assay format, potency, selectivity, reproducibility and chemical identity."),
            ("Mechanism", "Mechanism validation", "Link target engagement to downstream biology and phenotype."),
            ("Developability", "ADME / safety / manufacturability", "Track liabilities, exposure, formulation and synthesis constraints."),
            ("Decision", "Portfolio decision", "State evidence threshold, risks, next experiment and stop conditions."),
        ),
        ("Rationale", "Discover", "Validate", "Optimise", "Select"), ("drug", "target", "developability"),
    ),
    _template(
        "biomarker", "Biomarker Discovery Canvas", "Molecular & Drug Discovery", "🎯",
        "Define biomarker context of use, discovery, verification, validation and deployment constraints.", "board",
        ("Context of use", "Candidates", "Assay", "Verification", "Validation", "Deployment"),
        (
            ("Context of use", "Clinical or research use", "Define population, decision, timing and intended consequence."),
            ("Candidates", "Candidate evidence", "Attach discovery data, mechanism and prior evidence for each candidate."),
            ("Assay", "Assay readiness", "Record specimen, platform, analytical performance and pre-analytics."),
            ("Verification", "Technical verification", "Plan precision, accuracy, range, interference and stability checks."),
            ("Validation", "Clinical validation", "Define cohort, endpoint, comparator and performance estimates."),
            ("Deployment", "Implementation constraints", "Capture workflow, cost, turnaround, regulation and monitoring."),
        ),
        ("Define", "Discover", "Verify", "Validate", "Deploy"), ("biomarker", "assay", "validation"),
    ),
    _template(
        "clinical-trial", "Clinical Trial Landscape Canvas", "Clinical & Regulatory", "🏥",
        "Compare trial populations, interventions, endpoints, status and evidence gaps.", "matrix",
        ("Landscape", "Population", "Intervention", "Endpoints", "Status", "Implications"),
        (
            ("Landscape", "Trial set", "Attach registered trial records and define landscape boundaries."),
            ("Population", "Eligibility comparison", "Compare disease stage, biomarkers, prior therapy and geography."),
            ("Intervention", "Intervention map", "Group mechanism, regimen, comparator and combination strategy."),
            ("Endpoints", "Endpoint strategy", "Compare primary endpoints, assessment timing and surrogate assumptions."),
            ("Status", "Recruitment and results", "Track verified status, amendments, posted results and discontinuation."),
            ("Implications", "Portfolio implications", "Identify whitespace, crowding, differentiation and evidence gaps."),
        ),
        ("Collect", "Normalize", "Compare", "Verify", "Decide"), ("trial", "landscape", "clinical"),
    ),
    _template(
        "regulatory", "Regulatory Intelligence Canvas", "Clinical & Regulatory", "⚕️",
        "Track products, jurisdictions, pathways, evidence requirements, decisions and open obligations.", "board",
        ("Product", "Jurisdiction", "Pathway", "Evidence", "Decision", "Obligations"),
        (
            ("Product", "Product profile", "Define modality, indication, population, route and development stage."),
            ("Jurisdiction", "Authority and scope", "Record authority, region, applicable guidance and version dates."),
            ("Pathway", "Regulatory pathway", "Map designation, submission route, meetings and critical milestones."),
            ("Evidence", "Evidence expectations", "Capture quality, nonclinical, clinical and real-world evidence needs."),
            ("Decision", "Verified decisions", "Attach source-linked approvals, refusals, holds or safety communications."),
            ("Obligations", "Open commitments", "Track post-market studies, pharmacovigilance and reporting duties."),
        ),
        ("Profile", "Map", "Evidence", "Submit", "Monitor"), ("regulatory", "approval", "guidance"),
    ),
    _template(
        "grant-funding", "Grant & Funding Strategy Canvas", "Clinical & Regulatory", "💰",
        "Match a scientific programme to funder priorities, eligibility, milestones, budget and review criteria.", "board",
        ("Opportunity", "Fit", "Aims", "Workplan", "Budget", "Submission"),
        (
            ("Opportunity", "Funding opportunity", "Attach the official call and record deadlines, mechanism and jurisdiction."),
            ("Fit", "Strategic fit", "Map programme goals to funder priorities and explicit review criteria."),
            ("Aims", "Specific aims", "Write measurable aims with dependencies and alternative paths."),
            ("Workplan", "Milestones and risks", "Define work packages, deliverables, risks and decision gates."),
            ("Budget", "Budget rationale", "Link personnel, equipment, services and indirect costs to the workplan."),
            ("Submission", "Submission readiness", "Track documents, approvals, collaborators and final quality review."),
        ),
        ("Find", "Fit", "Design", "Budget", "Review", "Submit"), ("grant", "funding", "proposal"),
    ),
    _template(
        "patent-translation", "Patent & Translation Canvas", "Clinical & Regulatory", "💡",
        "Map novelty, prior art, enablement, freedom-to-operate risks and translation milestones.", "board",
        ("Invention", "Prior art", "Claims", "Evidence", "FTO risks", "Translation"),
        (
            ("Invention", "Invention disclosure", "Describe the technical concept, inventors, dates and enabling data."),
            ("Prior art", "Prior-art landscape", "Attach patents and publications relevant to novelty and inventive step."),
            ("Claims", "Claim concepts", "Map broad and narrow claim concepts without presenting legal conclusions."),
            ("Evidence", "Enablement evidence", "Track examples, reproducibility, scope support and missing experiments."),
            ("FTO risks", "Potential blocking rights", "Flag overlapping claims for qualified legal review."),
            ("Translation", "Translation path", "Define licensing, partnership, development and regulatory milestones."),
        ),
        ("Disclose", "Search", "Differentiate", "Strengthen", "Review", "Translate"), ("patent", "innovation", "translation"),
    ),
    _template(
        "outbreak", "Outbreak Intelligence Canvas", "Public Health & Ecology", "🦠",
        "Coordinate verified signals, cases, pathogen evidence, transmission hypotheses and response decisions.", "map",
        ("Signals", "Cases", "Pathogen", "Transmission", "Response", "Uncertainty"),
        (
            ("Signals", "Verified signals", "Attach source-linked alerts and record date, place and source reliability."),
            ("Cases", "Case definition and line list", "Define suspected, probable and confirmed classifications."),
            ("Pathogen", "Laboratory and genomic evidence", "Record assays, sequencing, lineage and quality limits."),
            ("Transmission", "Transmission hypotheses", "Map clusters, exposures, mobility and alternative explanations."),
            ("Response", "Response actions", "Track interventions, owners, timing and measured impact."),
            ("Uncertainty", "Critical uncertainty", "State what is unknown and which data would change the response."),
        ),
        ("Detect", "Verify", "Characterize", "Respond", "Review"), ("outbreak", "pathogen", "surveillance"),
    ),
    _template(
        "one-health", "One Health Evidence Canvas", "Public Health & Ecology", "🌍",
        "Connect human, animal, environmental and food-system evidence across a shared problem.", "graph",
        ("Human", "Animal", "Environment", "Food system", "Connections", "Interventions"),
        (
            ("Human", "Human health evidence", "Attach disease, exposure and population evidence."),
            ("Animal", "Animal health evidence", "Record host species, veterinary surveillance and husbandry context."),
            ("Environment", "Environmental evidence", "Capture water, soil, air, vector and climate measurements."),
            ("Food system", "Food-chain evidence", "Map production, processing, distribution and consumption links."),
            ("Connections", "Cross-domain pathways", "Document supported transmission or exposure links and uncertainty."),
            ("Interventions", "Joint interventions", "Define cross-sector actions, metrics and ownership."),
        ),
        ("Frame", "Connect", "Verify", "Prioritize", "Act"), ("one health", "environment", "zoonosis"),
    ),
    _template(
        "microbiome", "Microbiome Study Canvas", "Public Health & Ecology", "🧫",
        "Plan sampling, contamination control, sequencing, compositional analysis and validation.", "board",
        ("Question", "Sampling", "Wet lab", "Bioinformatics", "Statistics", "Validation"),
        (
            ("Question", "Ecological or clinical question", "Define habitat, host, exposure, outcome and causal boundaries."),
            ("Sampling", "Sampling design", "Record site, time, storage, biomass and negative-control strategy."),
            ("Wet lab", "Extraction and sequencing", "Capture extraction kit, primers or shotgun workflow, batches and controls."),
            ("Bioinformatics", "Processing pipeline", "Specify trimming, host removal, taxonomic/functional references and versions."),
            ("Statistics", "Compositional analysis", "Define diversity, differential abundance, covariates and multiplicity control."),
            ("Validation", "Validation and interpretation", "Plan qPCR, culture, metabolite or independent-cohort confirmation."),
        ),
        ("Design", "Sample", "Sequence", "Process", "Test", "Validate"), ("microbiome", "metagenomics", "ecology"),
    ),
    _template(
        "science-news-digest", "Science News Digest Canvas", "Publishing & Communication", "📰",
        "Build a source-linked digest that separates verified facts, context, uncertainty and action relevance.", "board",
        ("Stories", "Verification", "Context", "Impact", "Draft", "Publish"),
        (
            ("Stories", "Candidate stories", "Attach persisted Science Plus news or publication records."),
            ("Verification", "Source verification", "Confirm original source, date, trust state and whether claims match the source."),
            ("Context", "Scientific context", "Add prior evidence, field consensus and unresolved disagreement."),
            ("Impact", "Why it matters", "State who may be affected and avoid unsupported forecasts."),
            ("Draft", "Digest draft", "Write concise, source-linked summaries with calibrated language."),
            ("Publish", "Release checklist", "Review citations, rights, accessibility and correction path."),
        ),
        ("Collect", "Verify", "Contextualize", "Write", "Review", "Publish"), ("news", "digest", "communication"),
    ),
    _template(
        "publication-planner", "Publication Planning Canvas", "Publishing & Communication", "✍️",
        "Coordinate story, figures, analyses, authorship, reporting guidelines and submission readiness.", "board",
        ("Message", "Evidence", "Figures", "Methods", "Authorship", "Submission"),
        (
            ("Message", "Central scientific message", "Write the primary conclusion and its evidence boundary."),
            ("Evidence", "Analysis and evidence inventory", "Map every claim to analysis, figure, table and source."),
            ("Figures", "Figure plan", "Define figure question, panel logic, uncertainty and accessibility."),
            ("Methods", "Reproducibility package", "Track protocol, code, data availability and environment details."),
            ("Authorship", "Contribution map", "Record contribution roles, conflicts, approvals and acknowledgements."),
            ("Submission", "Journal and checklist", "Track scope fit, reporting guideline, cover letter and final checks."),
        ),
        ("Frame", "Assemble", "Visualize", "Write", "Review", "Submit"), ("publication", "manuscript", "figures"),
    ),
    _template(
        "conference", "Conference & Event Canvas", "Publishing & Communication", "🎤",
        "Plan abstract, poster or talk around audience, evidence, visuals, logistics and follow-up.", "board",
        ("Audience", "Message", "Evidence", "Visuals", "Logistics", "Follow-up"),
        (
            ("Audience", "Audience and venue", "Record event, track, audience expertise, format and constraints."),
            ("Message", "Take-home message", "Write one message the audience should remember."),
            ("Evidence", "Supporting evidence", "Select source-linked analyses and results appropriate to the claim."),
            ("Visuals", "Poster / slide plan", "Map narrative, figures, accessibility and disclosure requirements."),
            ("Logistics", "Submission and travel", "Track deadlines, approvals, registration and presentation assets."),
            ("Follow-up", "Engagement plan", "Capture questions, contacts, feedback and post-event actions."),
        ),
        ("Choose", "Abstract", "Design", "Rehearse", "Present", "Follow up"), ("conference", "poster", "talk"),
    ),
    _template(
        "collaboration", "Scientific Collaboration Canvas", "Publishing & Communication", "🤝",
        "Clarify shared objective, expertise, assets, governance, decisions and handoffs.", "board",
        ("Objective", "People", "Assets", "Workstreams", "Governance", "Decisions"),
        (
            ("Objective", "Shared objective", "Define the joint scientific outcome and explicit non-goals."),
            ("People", "Roles and expertise", "Map contributors, decision owners, reviewers and dependencies."),
            ("Assets", "Data, samples and tools", "Record ownership, access, rights, versions and transfer constraints."),
            ("Workstreams", "Work packages", "Define deliverables, interfaces, milestones and acceptance criteria."),
            ("Governance", "Governance agreement", "Capture communication, authorship, IP, privacy and escalation rules."),
            ("Decisions", "Decision log", "Record decisions, rationale, evidence and follow-up owner."),
        ),
        ("Align", "Resource", "Execute", "Review", "Decide"), ("collaboration", "governance", "handoff"),
    ),
    _template(
        "trend-radar", "Scientific Trend Radar", "Intelligence & Operations", "📡",
        "Track emerging topics by evidence maturity, momentum, relevance and uncertainty.", "radar",
        ("Signals", "Emerging", "Growing", "Established", "Declining", "Watchlist"),
        (
            ("Signals", "New signals", "Attach source-linked records and note why they may represent a new signal."),
            ("Emerging", "Emerging themes", "Group repeated signals that remain early or uncertain."),
            ("Growing", "Growing themes", "Track increasing independent evidence, adoption or investment."),
            ("Established", "Established areas", "Record mature consensus, standards and stable capabilities."),
            ("Declining", "Declining or challenged", "Capture falling support, failed replication or superseded methods."),
            ("Watchlist", "Decision watchlist", "Define trigger conditions that would change priority."),
        ),
        ("Scan", "Cluster", "Verify", "Score", "Watch"), ("trend", "radar", "signals"),
    ),
    _template(
        "technology-watch", "Database & Tool Release Watch", "Intelligence & Operations", "🛠️",
        "Evaluate database, software, model and protocol releases for compatibility and scientific impact.", "board",
        ("Release", "Change", "Compatibility", "Validation", "Adoption", "Monitor"),
        (
            ("Release", "Verified release", "Attach official release notes, version, date and provenance."),
            ("Change", "Material changes", "Summarize schema, reference, algorithm, license or behaviour changes."),
            ("Compatibility", "Compatibility impact", "Identify pipelines, formats, models and reports affected."),
            ("Validation", "Validation plan", "Define regression, benchmark and scientific equivalence checks."),
            ("Adoption", "Adoption decision", "Record rollout, rollback, migration and owner."),
            ("Monitor", "Post-adoption monitoring", "Track performance, drift, incidents and upstream corrections."),
        ),
        ("Detect", "Assess", "Test", "Approve", "Adopt", "Monitor"), ("database", "tool", "release"),
    ),
    _template(
        "research-portfolio", "Research Portfolio Canvas", "Intelligence & Operations", "🗂️",
        "Balance projects by strategic value, evidence maturity, risk, dependency and next decision.", "portfolio",
        ("Ideas", "Discovery", "Validation", "Translation", "Paused", "Completed"),
        (
            ("Ideas", "New opportunity", "Describe the opportunity, source signal and strategic relevance."),
            ("Discovery", "Discovery programme", "Record hypothesis, assets, milestones and key uncertainty."),
            ("Validation", "Validation programme", "Track independent evidence, reproducibility and release gates."),
            ("Translation", "Translation programme", "Capture deployment, clinical, regulatory or partnership milestones."),
            ("Paused", "Paused programme", "Record stop reason, preserved assets and restart trigger."),
            ("Completed", "Completed programme", "Summarize outcome, evidence package and lessons learned."),
        ),
        ("Capture", "Prioritize", "Execute", "Gate", "Learn"), ("portfolio", "programme", "decision"),
    ),
    _template(
        "reproducibility", "Reproducibility & Audit Canvas", "Intelligence & Operations", "✅",
        "Track data, code, environment, provenance, checks and independent reproduction status.", "board",
        ("Claim", "Data", "Code", "Environment", "Checks", "Reproduction"),
        (
            ("Claim", "Target claim or output", "Identify the exact result, figure, table or model to reproduce."),
            ("Data", "Data provenance", "Record source, version, checksum, licence, exclusions and transformations."),
            ("Code", "Code provenance", "Capture repository, commit, parameters, workflow and generated artefacts."),
            ("Environment", "Execution environment", "Record OS, runtime, packages, hardware and external services."),
            ("Checks", "Quality and integrity checks", "Define unit, integration, statistical and visual checks."),
            ("Reproduction", "Independent reproduction", "Record actor, date, outcome, differences and unresolved blockers."),
        ),
        ("Freeze", "Re-run", "Compare", "Investigate", "Qualify"), ("reproducibility", "audit", "provenance"),
    ),
    _template(
        "data-readiness", "Scientific Data Readiness Canvas", "Intelligence & Operations", "🗃️",
        "Assess whether a dataset is fit for a specific scientific question and downstream analysis.", "board",
        ("Purpose", "Provenance", "Schema", "Quality", "Bias", "Readiness"),
        (
            ("Purpose", "Intended use", "Define the question, analysis and decision the data must support."),
            ("Provenance", "Source and lineage", "Record collection context, ownership, licence, versions and transformations."),
            ("Schema", "Structure and semantics", "Map entities, variables, units, coding systems and missing definitions."),
            ("Quality", "Quality profile", "Track completeness, validity, uniqueness, consistency and outliers."),
            ("Bias", "Coverage and bias", "Assess population, site, temporal, platform and label bias."),
            ("Readiness", "Readiness decision", "State usable scope, blockers, remediation and release boundary."),
        ),
        ("Define", "Profile", "Audit", "Remediate", "Qualify"), ("data", "readiness", "quality"),
    ),
    _template(
        "scientific-decision", "Scientific Decision Canvas", "Intelligence & Operations", "🧭",
        "Make an explicit decision from alternatives, evidence, uncertainty, constraints and reversibility.", "board",
        ("Decision", "Options", "Evidence", "Uncertainty", "Constraints", "Commitment"),
        (
            ("Decision", "Decision statement", "Define who decides, by when, and what changes after the decision."),
            ("Options", "Alternatives", "List viable alternatives, including defer, stop or gather more evidence."),
            ("Evidence", "Decision evidence", "Attach source-linked evidence and distinguish observation from inference."),
            ("Uncertainty", "Uncertainty and assumptions", "Record critical assumptions, sensitivity and unknowns."),
            ("Constraints", "Constraints and trade-offs", "Capture time, cost, safety, ethics, regulation and dependencies."),
            ("Commitment", "Decision and review trigger", "Record choice, rationale, owner, actions and conditions for review."),
        ),
        ("Frame", "Compare", "Challenge", "Decide", "Review"), ("decision", "evidence", "risk"),
    ),
)

TEMPLATE_INDEX: dict[str, CanvasTemplate] = {template.key: template for template in TEMPLATES}
TEMPLATE_CATEGORIES: tuple[str, ...] = tuple(dict.fromkeys(template.category for template in TEMPLATES))


class SciencePlusCanvasStore:
    """Local-first, tenant/user-scoped storage for Science Plus canvases."""

    def __init__(self, root: str | Path, *, tenant_id: str, user_id: str) -> None:
        project_root = Path(root).resolve()
        user_root = Path(os.environ.get("BIOINTEL_USER_DATA_DIR", project_root / "UserData")).resolve()
        self.base = user_root / "science_plus_canvases" / _safe_segment(tenant_id, "local") / _safe_segment(user_id, "user")
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, canvas_id: str) -> Path:
        safe_id = _safe_segment(canvas_id, "invalid")
        if safe_id != canvas_id:
            raise ValueError("Invalid canvas identifier.")
        return self.base / f"{safe_id}.json"

    def list(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in self.base.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and payload.get("canvas_id"):
                rows.append(payload)
        return sorted(rows, key=lambda row: str(row.get("updated_at") or ""), reverse=True)

    def load(self, canvas_id: str) -> dict[str, Any] | None:
        path = self._path(canvas_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def create(self, template_key: str, *, title: str | None = None) -> dict[str, Any]:
        template = TEMPLATE_INDEX.get(template_key)
        if template is None:
            raise KeyError(f"Unknown Science Plus canvas template: {template_key}")
        now = _utc_now()
        canvas_id = f"spc-{uuid.uuid4().hex[:16]}"
        cards: list[dict[str, Any]] = []
        for index, prompt in enumerate(template.starter_cards, start=1):
            item = dict(prompt)
            item["card_id"] = f"card-{uuid.uuid4().hex[:12]}"
            item["order"] = index
            item["created_at"] = now
            item["updated_at"] = now
            cards.append(item)
        payload = {
            "schema_version": CANVAS_SCHEMA_VERSION,
            "canvas_id": canvas_id,
            "template_key": template.key,
            "title": str(title or template.title).strip()[:240] or template.title,
            "description": template.description,
            "objective": "",
            "status": "Draft",
            "canvas_type": template.canvas_type,
            "columns": list(template.columns),
            "workflow": list(template.workflow),
            "tags": list(template.tags),
            "cards": cards,
            "created_at": now,
            "updated_at": now,
        }
        return self.save(payload)

    def save(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        normalized = _normalize_workspace(payload)
        path = self._path(str(normalized["canvas_id"]))
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
        return normalized

    def delete(self, canvas_id: str) -> None:
        path = self._path(canvas_id)
        if path.exists():
            path.unlink()

    def duplicate(self, canvas_id: str) -> dict[str, Any]:
        source = self.load(canvas_id)
        if source is None:
            raise KeyError("Canvas not found.")
        now = _utc_now()
        duplicate = dict(source)
        duplicate["canvas_id"] = f"spc-{uuid.uuid4().hex[:16]}"
        duplicate["title"] = f"{source.get('title') or 'Science canvas'} — Copy"[:240]
        duplicate["status"] = "Draft"
        duplicate["created_at"] = now
        duplicate["updated_at"] = now
        duplicate["cards"] = [
            {
                **dict(card),
                "card_id": f"card-{uuid.uuid4().hex[:12]}",
                "created_at": now,
                "updated_at": now,
            }
            for card in list(source.get("cards") or [])
            if isinstance(card, Mapping)
        ]
        return self.save(duplicate)


def _normalize_workspace(payload: Mapping[str, Any]) -> dict[str, Any]:
    canvas_id = _safe_segment(str(payload.get("canvas_id") or ""), "")
    if not canvas_id or not canvas_id.startswith("spc-"):
        raise ValueError("Canvas identifier is missing or invalid.")
    template_key = str(payload.get("template_key") or "custom")[:120]
    columns = [str(value).strip()[:120] for value in list(payload.get("columns") or []) if str(value).strip()]
    columns = list(dict.fromkeys(columns))[:12]
    if not columns:
        columns = ["Ideas", "In progress", "Review", "Complete"]
    now = _utc_now()
    cards: list[dict[str, Any]] = []
    for index, raw in enumerate(list(payload.get("cards") or [])[:500], start=1):
        if not isinstance(raw, Mapping):
            continue
        column = str(raw.get("column") or columns[0]).strip()[:120]
        if column not in columns:
            column = columns[0]
        status = str(raw.get("status") or "Planned")
        if status not in CARD_STATUSES:
            status = "Planned"
        evidence_ids = [str(value).strip()[:180] for value in list(raw.get("evidence_ids") or []) if str(value).strip()]
        tags = [str(value).strip()[:80] for value in list(raw.get("tags") or []) if str(value).strip()]
        cards.append(
            {
                "card_id": _safe_segment(str(raw.get("card_id") or f"card-{uuid.uuid4().hex[:12]}"), f"card-{index}"),
                "column": column,
                "title": str(raw.get("title") or "Untitled card").strip()[:240] or "Untitled card",
                "guidance": str(raw.get("guidance") or "").strip()[:2000],
                "notes": str(raw.get("notes") or "").strip()[:12000],
                "status": status,
                "owner": str(raw.get("owner") or "").strip()[:160],
                "due_date": str(raw.get("due_date") or "").strip()[:32],
                "tags": list(dict.fromkeys(tags))[:20],
                "evidence_ids": list(dict.fromkeys(evidence_ids))[:100],
                "order": int(raw.get("order") or index),
                "created_at": str(raw.get("created_at") or now),
                "updated_at": now,
            }
        )
    workspace_status = str(payload.get("status") or "Draft")
    if workspace_status not in WORKSPACE_STATUSES:
        workspace_status = "Draft"
    return {
        "schema_version": CANVAS_SCHEMA_VERSION,
        "canvas_id": canvas_id,
        "template_key": template_key,
        "title": str(payload.get("title") or "Science canvas").strip()[:240] or "Science canvas",
        "description": str(payload.get("description") or "").strip()[:2000],
        "objective": str(payload.get("objective") or "").strip()[:4000],
        "status": workspace_status,
        "canvas_type": str(payload.get("canvas_type") or "board")[:80],
        "columns": columns,
        "workflow": [str(value).strip()[:120] for value in list(payload.get("workflow") or []) if str(value).strip()][:12],
        "tags": [str(value).strip()[:80] for value in list(payload.get("tags") or []) if str(value).strip()][:30],
        "cards": sorted(cards, key=lambda card: (columns.index(card["column"]), int(card.get("order") or 0))),
        "created_at": str(payload.get("created_at") or now),
        "updated_at": now,
    }


def workspace_markdown(workspace: Mapping[str, Any]) -> str:
    lines = [
        f"# {workspace.get('title') or 'Science canvas'}",
        "",
        f"- Status: {workspace.get('status') or 'Draft'}",
        f"- Template: {workspace.get('template_key') or 'custom'}",
        f"- Updated: {workspace.get('updated_at') or ''}",
        "",
    ]
    if workspace.get("objective"):
        lines.extend(("## Objective", "", str(workspace["objective"]), ""))
    cards = list(workspace.get("cards") or [])
    for column in list(workspace.get("columns") or []):
        lines.extend((f"## {column}", ""))
        selected = [card for card in cards if str(card.get("column")) == str(column)]
        if not selected:
            lines.extend(("_No cards._", ""))
            continue
        for card in selected:
            lines.append(f"### {card.get('title') or 'Untitled card'}")
            lines.append(f"Status: {card.get('status') or 'Planned'}")
            if card.get("owner"):
                lines.append(f"Owner: {card['owner']}")
            if card.get("due_date"):
                lines.append(f"Due: {card['due_date']}")
            if card.get("guidance"):
                lines.extend(("", f"> {card['guidance']}"))
            if card.get("notes"):
                lines.extend(("", str(card["notes"])))
            if card.get("tags"):
                lines.extend(("", "Tags: " + ", ".join(str(value) for value in card["tags"])))
            if card.get("evidence_ids"):
                lines.extend(("", "Evidence IDs: " + ", ".join(str(value) for value in card["evidence_ids"])))
            lines.append("")
    lines.extend(("---", "Generated from the local-first BioIntel Science Plus Canvas Studio. Scientific interpretation requires domain review."))
    return "\n".join(lines).strip() + "\n"


def workspace_validation(workspace: Mapping[str, Any]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    cards = list(workspace.get("cards") or [])
    checks.append({"Check": "Objective", "State": "Ready" if workspace.get("objective") else "Needs attention", "Detail": "Objective is defined." if workspace.get("objective") else "Add a bounded scientific objective."})
    checks.append({"Check": "Canvas content", "State": "Ready" if cards else "Blocked", "Detail": f"{len(cards)} card(s) are present."})
    linked = sum(1 for card in cards if card.get("evidence_ids"))
    checks.append({"Check": "Evidence linkage", "State": "Ready" if linked else "Needs attention", "Detail": f"{linked} card(s) link to persisted Science Plus evidence."})
    blocked = sum(1 for card in cards if card.get("status") == "Blocked")
    checks.append({"Check": "Open blockers", "State": "Ready" if blocked == 0 else "Needs attention", "Detail": f"{blocked} blocked card(s)."})
    incomplete = sum(1 for card in cards if card.get("status") not in {"Complete", "Prompt"})
    checks.append({"Check": "Completion", "State": "Ready" if incomplete == 0 and cards else "In progress", "Detail": f"{incomplete} active card(s) remain."})
    return checks


def _workspace_stats(workspace: Mapping[str, Any]) -> dict[str, int]:
    cards = [card for card in list(workspace.get("cards") or []) if isinstance(card, Mapping)]
    return {
        "cards": len(cards),
        "evidence": sum(1 for card in cards if card.get("evidence_ids")),
        "complete": sum(1 for card in cards if card.get("status") == "Complete"),
        "blocked": sum(1 for card in cards if card.get("status") == "Blocked"),
        "owners": len({str(card.get("owner") or "").strip() for card in cards if str(card.get("owner") or "").strip()}),
    }


def _featured_templates(limit: int = 4) -> tuple[CanvasTemplate, ...]:
    preferred = (
        "research-question",
        "systematic-review",
        "multi-omics",
        "drug-discovery",
    )
    picks = [TEMPLATE_INDEX[key] for key in preferred if key in TEMPLATE_INDEX]
    return tuple(picks[:limit])



def _render_canvas_navigation_overview(active: str = "") -> None:
    metadata = {
        "Template library": ("Start from a scientific framework", "Browse professional templates with prompts, zones and evidence-ready starter cards.", ("Searchable templates", "Domain categories", "Structured prompts")),
        "My canvases": ("Manage local scientific workspaces", "Open, duplicate, export or remove user-scoped canvases without mixing project ownership.", ("Local-first", "User-scoped", "Exportable")),
        "Canvas workspace": ("Build the scientific plan", "Edit cards, move work across zones, capture caveats and track completion or blockers.", ("Board", "Table", "Graph", "Timeline")),
        "Evidence linker": ("Connect planning to evidence", "Search persisted Science Plus records and attach source-linked evidence to specific cards.", ("Provenance-aware", "Record search", "Card linkage")),
        "Exports & governance": ("Review readiness before sharing", "Inspect evidence linkage, blockers and completion before downloading structured outputs.", ("Readiness checks", "JSON", "Markdown", "CSV")),
    }
    title, detail, chips = metadata.get(active, metadata["Template library"])
    chip_html = ''.join(f'<span class="science-plus-chip">{html.escape(chip)}</span>' for chip in chips)
    st.markdown(
        f"""
        <div class="science-plus-callout">
            <div class="science-plus-kicker">Current Canvas Studio view</div>
            <b>{html.escape(title)}</b><br/>
            <span class="science-plus-subtle">{html.escape(detail)}</span>
            <div class="science-plus-chip-row">{chip_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def _render_template_category_overview() -> None:
    counts = {category: sum(1 for template in TEMPLATES if template.category == category) for category in TEMPLATE_CATEGORIES}
    html_cards = "".join(
        f'<div class="science-plus-stat"><strong>{count}</strong><span>{html.escape(category)}</span></div>'
        for category, count in counts.items()
    )
    st.markdown(
        f"""
        <div class="science-plus-callout">
            <b>Template catalogue overview</b><br/>
            Structured scientific canvases grouped by research domain. Use a template to start with prompts, workflow stages and evidence-ready cards.
            <div class="science-plus-stat-grid" style="margin-top:.8rem;">{html_cards}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_canvas_empty_state(message: str, detail: str, *, chips: Sequence[str] = ()) -> None:
    chip_html = ""
    if chips:
        chip_html = '<div class="science-plus-chip-row">' + ''.join(
            f'<span class="science-plus-chip">{html.escape(chip)}</span>' for chip in chips if chip
        ) + '</div>'
    st.markdown(
        f"""
        <div class="science-plus-empty">
            <b>{html.escape(message)}</b>
            <span>{html.escape(detail)}</span>
            {chip_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _template_matches(template: CanvasTemplate, query: str, category: str) -> bool:
    if category != "All" and template.category != category:
        return False
    material = " ".join((template.title, template.description, template.category, *template.tags)).casefold()
    return not query.strip() or query.strip().casefold() in material


def _set_active(canvas_id: str) -> None:
    st.session_state["science_plus_active_canvas"] = canvas_id
    st.session_state["science_plus_studio_view"] = "Canvas workspace"


def _create_canvas(store: SciencePlusCanvasStore, template_key: str, title: str | None = None) -> None:
    created = store.create(template_key, title=title)
    _set_active(str(created["canvas_id"]))
    st.toast("Canvas created from template.")
    st.rerun()


def _render_template_library(store: SciencePlusCanvasStore) -> None:
    _render_template_category_overview()
    spotlight = _featured_templates()
    if spotlight:
        st.subheader("Quick start templates", anchor=False)
        hero_cols = st.columns(len(spotlight))
        for column, template in zip(hero_cols, spotlight):
            with column.container(border=True):
                st.markdown(f"### {template.icon} {template.title}")
                st.caption(template.category)
                st.write(template.description)
                st.caption("Workflow: " + " → ".join(template.workflow[:4]) + (" …" if len(template.workflow) > 4 else ""))
                if template.tags:
                    st.caption(" · ".join(template.tags[:4]))
                if st.button("Start now", key=f"science_plus_quickstart_{template.key}", type="primary"):
                    _create_canvas(store, template.key)
    st.subheader("Template library", anchor=False)
    search_col, category_col, type_col = st.columns([2, 1, 1])
    query = search_col.text_input("Search templates", placeholder="Literature, omics, trial, pathway, publication…", key="science_plus_template_search")
    category = category_col.selectbox("Category", ("All", *TEMPLATE_CATEGORIES), key="science_plus_template_category")
    canvas_type = type_col.selectbox("Canvas type", ("All", *tuple(dict.fromkeys(template.canvas_type for template in TEMPLATES))), key="science_plus_template_type")
    selected = [
        template for template in TEMPLATES
        if _template_matches(template, query, category) and (canvas_type == "All" or template.canvas_type == canvas_type)
    ]
    st.caption(f"{len(selected)} of {len(TEMPLATES)} professional templates · templates contain prompts, not fabricated scientific results.")
    for start in range(0, len(selected), 3):
        columns = st.columns(3)
        for column, template in zip(columns, selected[start:start + 3]):
            with column.container(border=True):
                header = st.container(horizontal=True)
                with header:
                    st.markdown(f"## {template.icon}")
                    st.badge(template.category, color="blue")
                    st.badge(template.canvas_type.upper(), color="gray")
                st.markdown(f"### {template.title}")
                st.caption(template.description)
                st.caption(f"{len(template.columns)} zones · {len(template.starter_cards)} starter prompts")
                if template.tags:
                    st.caption("Tags: " + " · ".join(template.tags[:5]))
                with st.expander("Preview structure"):
                    st.write(" → ".join(template.workflow))
                    for zone in template.columns:
                        st.markdown(f"- **{zone}**")
                action_row = st.container(horizontal=True)
                with action_row:
                    if st.button("Use template", key=f"science_plus_use_{template.key}", type="primary", icon=":material/add:"):
                        _create_canvas(store, template.key)
                    st.download_button(
                        "Template JSON",
                        data=json.dumps(asdict(template), ensure_ascii=False, indent=2),
                        file_name=f"{template.key}-template.json",
                        mime="application/json",
                        key=f"science_plus_template_download_{template.key}",
                    )


def _render_canvas_library(store: SciencePlusCanvasStore) -> None:
    workspaces = store.list()
    if not workspaces:
        _render_canvas_empty_state(
            "No saved canvas yet.",
            "Open Template library and create the first Science Plus canvas.",
            chips=["35 templates", "Board · Table · Graph · Timeline", "Evidence linker"],
        )
        return
    metric_row = st.container(horizontal=True)
    total_cards = sum(len(list(workspace.get("cards") or [])) for workspace in workspaces)
    evidence_linked = sum(
        1 for workspace in workspaces for card in list(workspace.get("cards") or []) if isinstance(card, Mapping) and card.get("evidence_ids")
    )
    completed = sum(1 for workspace in workspaces if workspace.get("status") == "Complete")
    active = sum(1 for workspace in workspaces if workspace.get("status") in {"Active", "In review"})
    with metric_row:
        st.metric("Saved canvases", len(workspaces), border=True)
        st.metric("Active / review", active, border=True)
        st.metric("Completed canvases", completed, border=True)
        st.metric("Evidence-linked cards", evidence_linked, border=True)
    st.caption(f"Canvas library currently contains {total_cards} card(s) across all saved workspaces.")
    for start in range(0, len(workspaces), 3):
        columns = st.columns(3)
        for column, workspace in zip(columns, workspaces[start:start + 3]):
            canvas_id = str(workspace["canvas_id"])
            template = TEMPLATE_INDEX.get(str(workspace.get("template_key") or ""))
            with column.container(border=True):
                st.badge(str(workspace.get("status") or "Draft"), color="green" if workspace.get("status") == "Complete" else "blue")
                st.markdown(f"### {workspace.get('title') or 'Science canvas'}")
                st.caption(template.category if template else "Custom canvas")
                st.caption(f"{len(workspace.get('cards') or [])} cards · updated {str(workspace.get('updated_at') or '').replace('T', ' ')}")
                actions = st.container(horizontal=True)
                with actions:
                    if st.button("Open", key=f"science_plus_open_{canvas_id}", type="primary"):
                        _set_active(canvas_id)
                        st.rerun()
                    if st.button("Duplicate", key=f"science_plus_duplicate_{canvas_id}", icon=":material/content_copy:"):
                        duplicate = store.duplicate(canvas_id)
                        _set_active(str(duplicate["canvas_id"]))
                        st.toast("Canvas duplicated.")
                        st.rerun()
                    with st.popover("More"):
                        st.download_button(
                            "Download JSON", json.dumps(workspace, ensure_ascii=False, indent=2),
                            file_name=f"{_safe_segment(str(workspace.get('title')), 'science-canvas')}.json", mime="application/json",
                            key=f"science_plus_json_{canvas_id}",
                        )
                        st.download_button(
                            "Download Markdown", workspace_markdown(workspace),
                            file_name=f"{_safe_segment(str(workspace.get('title')), 'science-canvas')}.md", mime="text/markdown",
                            key=f"science_plus_md_{canvas_id}",
                        )
                        confirm = st.checkbox("Confirm deletion", key=f"science_plus_confirm_delete_{canvas_id}")
                        if st.button("Delete canvas", key=f"science_plus_delete_{canvas_id}", disabled=not confirm):
                            store.delete(canvas_id)
                            if st.session_state.get("science_plus_active_canvas") == canvas_id:
                                st.session_state.pop("science_plus_active_canvas", None)
                            st.toast("Canvas deleted.")
                            st.rerun()


def _update_card(workspace: dict[str, Any], card_id: str, **changes: Any) -> dict[str, Any]:
    updated = dict(workspace)
    cards = []
    for card in list(workspace.get("cards") or []):
        item = dict(card)
        if str(item.get("card_id")) == card_id:
            item.update(changes)
        cards.append(item)
    updated["cards"] = cards
    return updated


def _move_card(workspace: dict[str, Any], card_id: str, delta: int) -> dict[str, Any]:
    columns = list(workspace.get("columns") or [])
    card = next((item for item in list(workspace.get("cards") or []) if str(item.get("card_id")) == card_id), None)
    if card is None or str(card.get("column")) not in columns:
        return workspace
    index = columns.index(str(card["column"]))
    target = max(0, min(len(columns) - 1, index + delta))
    return _update_card(workspace, card_id, column=columns[target])


def _delete_card(workspace: dict[str, Any], card_id: str) -> dict[str, Any]:
    updated = dict(workspace)
    updated["cards"] = [card for card in list(workspace.get("cards") or []) if str(card.get("card_id")) != card_id]
    return updated


def _render_card_editor(store: SciencePlusCanvasStore, workspace: dict[str, Any], card_id: str) -> None:
    card = next((item for item in list(workspace.get("cards") or []) if str(item.get("card_id")) == card_id), None)
    if card is None:
        return
    with st.expander(f"Edit · {card.get('title') or 'Untitled card'}", expanded=True):
        with st.form(f"science_plus_card_editor_{card_id}", border=False):
            title = st.text_input("Card title", value=str(card.get("title") or ""))
            guidance = st.text_area("Template guidance", value=str(card.get("guidance") or ""), height=90)
            notes = st.text_area("Scientific notes", value=str(card.get("notes") or ""), height=180, placeholder="Add observations, decisions, caveats and next steps. Link evidence below.")
            col_a, col_b, col_c = st.columns(3)
            column = col_a.selectbox("Zone", list(workspace.get("columns") or []), index=list(workspace.get("columns") or []).index(str(card.get("column"))))
            status = col_b.selectbox("Status", CARD_STATUSES, index=CARD_STATUSES.index(str(card.get("status"))) if str(card.get("status")) in CARD_STATUSES else 1)
            due_date = col_c.text_input("Due date", value=str(card.get("due_date") or ""), placeholder="YYYY-MM-DD")
            owner = st.text_input("Owner", value=str(card.get("owner") or ""))
            tags = st.text_input("Tags", value=", ".join(str(value) for value in list(card.get("tags") or [])))
            evidence = st.text_area("Evidence IDs", value="\n".join(str(value) for value in list(card.get("evidence_ids") or [])), help="One persisted Science Plus item ID per line.")
            if st.form_submit_button("Save card", type="primary"):
                updated = _update_card(
                    workspace,
                    card_id,
                    title=title,
                    guidance=guidance,
                    notes=notes,
                    column=column,
                    status=status,
                    due_date=due_date,
                    owner=owner,
                    tags=[value.strip() for value in tags.split(",") if value.strip()],
                    evidence_ids=[value.strip() for value in evidence.splitlines() if value.strip()],
                )
                store.save(updated)
                st.session_state.pop("science_plus_edit_card", None)
                st.toast("Card saved.")
                st.rerun()


def _render_board(store: SciencePlusCanvasStore, workspace: dict[str, Any]) -> None:
    columns = list(workspace.get("columns") or [])
    cards = list(workspace.get("cards") or [])
    for start in range(0, len(columns), 3):
        layout = st.columns(3)
        for column_box, zone in zip(layout, columns[start:start + 3]):
            zone_cards = [card for card in cards if str(card.get("column")) == zone]
            with column_box.container(border=True):
                title_row = st.container(horizontal=True)
                with title_row:
                    st.markdown(f"### {zone}")
                    st.badge(str(len(zone_cards)), color="gray")
                if not zone_cards:
                    st.caption("No cards in this zone.")
                for card in zone_cards:
                    card_id = str(card.get("card_id"))
                    with st.container(border=True):
                        st.markdown(f"**{card.get('title') or 'Untitled card'}**")
                        status = str(card.get("status") or "Planned")
                        st.badge(status, color="green" if status == "Complete" else ("red" if status == "Blocked" else "blue"))
                        if card.get("guidance"):
                            st.caption(str(card["guidance"]))
                        if card.get("notes"):
                            excerpt = str(card["notes"])
                            st.write(excerpt[:320] + ("…" if len(excerpt) > 320 else ""))
                        details = []
                        if card.get("owner"):
                            details.append(f"Owner: {card['owner']}")
                        if card.get("due_date"):
                            details.append(f"Due: {card['due_date']}")
                        if card.get("evidence_ids"):
                            details.append(f"Evidence: {len(card['evidence_ids'])}")
                        if details:
                            st.caption(" · ".join(details))
                        actions = st.container(horizontal=True)
                        with actions:
                            if st.button("←", key=f"science_plus_left_{card_id}", disabled=zone == columns[0], help="Move left"):
                                store.save(_move_card(workspace, card_id, -1)); st.rerun()
                            if st.button("Edit", key=f"science_plus_edit_{card_id}"):
                                st.session_state["science_plus_edit_card"] = card_id; st.rerun()
                            if st.button("→", key=f"science_plus_right_{card_id}", disabled=zone == columns[-1], help="Move right"):
                                store.save(_move_card(workspace, card_id, 1)); st.rerun()
                            with st.popover("⋯"):
                                if st.button("Delete card", key=f"science_plus_remove_{card_id}"):
                                    store.save(_delete_card(workspace, card_id)); st.rerun()
    editing = str(st.session_state.get("science_plus_edit_card") or "")
    if editing:
        _render_card_editor(store, workspace, editing)


def _render_table(store: SciencePlusCanvasStore, workspace: dict[str, Any]) -> None:
    rows = []
    for card in list(workspace.get("cards") or []):
        rows.append({
            "card_id": card.get("card_id"), "Zone": card.get("column"), "Title": card.get("title"),
            "Status": card.get("status"), "Owner": card.get("owner"), "Due": card.get("due_date"),
            "Notes": card.get("notes"), "Evidence": "\n".join(str(value) for value in list(card.get("evidence_ids") or [])),
        })
    edited = st.data_editor(
        pd.DataFrame(rows), width="stretch", hide_index=True, num_rows="dynamic", key=f"science_plus_table_{workspace['canvas_id']}",
        column_config={
            "card_id": None,
            "Zone": st.column_config.SelectboxColumn(options=list(workspace.get("columns") or []), required=True),
            "Status": st.column_config.SelectboxColumn(options=list(CARD_STATUSES), required=True),
            "Notes": st.column_config.TextColumn(width="large"),
            "Evidence": st.column_config.TextColumn(help="One evidence ID per line", width="medium"),
        },
    )
    if st.button("Save table edits", type="primary", key=f"science_plus_table_save_{workspace['canvas_id']}"):
        existing = {str(card.get("card_id")): dict(card) for card in list(workspace.get("cards") or [])}
        cards: list[dict[str, Any]] = []
        for index, row in enumerate(edited.fillna("").to_dict(orient="records"), start=1):
            card_id = _safe_segment(str(row.get("card_id") or f"card-{uuid.uuid4().hex[:12]}"), f"card-{index}")
            item = existing.get(card_id, {})
            item.update(
                {
                    "card_id": card_id,
                    "column": str(row.get("Zone") or list(workspace.get("columns") or ["Ideas"])[0]),
                    "title": str(row.get("Title") or "Untitled card"),
                    "status": str(row.get("Status") or "Planned"),
                    "owner": str(row.get("Owner") or ""),
                    "due_date": str(row.get("Due") or ""),
                    "notes": str(row.get("Notes") or ""),
                    "evidence_ids": [value.strip() for value in str(row.get("Evidence") or "").splitlines() if value.strip()],
                    "order": index,
                }
            )
            cards.append(item)
        updated = dict(workspace)
        updated["cards"] = cards
        store.save(updated)
        st.toast("Table changes saved.")
        st.rerun()


def _dot_escape(value: Any) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _render_graph(workspace: Mapping[str, Any]) -> None:
    columns = list(workspace.get("columns") or [])
    cards = list(workspace.get("cards") or [])
    lines = [
        "digraph science_plus_canvas {",
        "rankdir=LR;",
        'graph [bgcolor="transparent", pad="0.2", nodesep="0.35", ranksep="0.65"];',
        'node [shape=box, style="rounded,filled", fillcolor="#F7F9FC", color="#9AA8BD", fontname="Arial", fontsize=10];',
        'edge [color="#8492A6", arrowsize=0.7];',
    ]
    previous_zone = ""
    for zone_index, zone in enumerate(columns):
        zone_id = f"zone_{zone_index}"
        lines.append(f'{zone_id} [label="{_dot_escape(zone)}", shape=folder, fillcolor="#E9F2FF"];')
        if previous_zone:
            lines.append(f"{previous_zone} -> {zone_id} [penwidth=1.6];")
        previous_zone = zone_id
        for card_index, card in enumerate(card for card in cards if str(card.get("column")) == zone):
            card_id = f"card_{zone_index}_{card_index}"
            label = f"{card.get('title') or 'Untitled'}\\n[{card.get('status') or 'Planned'}]"
            fill = "#EAF7EE" if card.get("status") == "Complete" else ("#FDECEC" if card.get("status") == "Blocked" else "#F7F9FC")
            lines.append(f'{card_id} [label="{_dot_escape(label)}", fillcolor="{fill}"];')
            lines.append(f"{zone_id} -> {card_id} [style=dashed, arrowhead=none];")
    lines.append("}")
    st.graphviz_chart("\n".join(lines), width="stretch")
    st.caption("Graph view represents canvas zones and cards. Relationships are structural, not inferred scientific causality.")


def _render_timeline(workspace: Mapping[str, Any]) -> None:
    cards = [dict(card) for card in list(workspace.get("cards") or [])]
    dated = [card for card in cards if str(card.get("due_date") or "").strip()]
    if not dated:
        st.info("No card has a due date. Add dates in Board or Table view to build the timeline.")
        return
    frame = pd.DataFrame(
        {
            "Due": [card.get("due_date") for card in dated],
            "Zone": [card.get("column") for card in dated],
            "Card": [card.get("title") for card in dated],
            "Status": [card.get("status") for card in dated],
            "Owner": [card.get("owner") for card in dated],
        }
    ).sort_values("Due")
    st.dataframe(frame, width="stretch", hide_index=True)
    st.caption("Timeline order uses the user-entered due-date text. Use ISO dates (YYYY-MM-DD) for reliable sorting.")


def _render_add_card(store: SciencePlusCanvasStore, workspace: dict[str, Any]) -> None:
    with st.popover("Add card", icon=":material/add:"):
        with st.form(f"science_plus_add_card_{workspace['canvas_id']}", border=False):
            title = st.text_input("Card title")
            zone = st.selectbox("Zone", list(workspace.get("columns") or []))
            notes = st.text_area("Notes", height=110)
            status = st.selectbox("Status", CARD_STATUSES, index=1)
            if st.form_submit_button("Create card", type="primary"):
                if not title.strip():
                    st.error("Card title is required.")
                else:
                    now = _utc_now()
                    updated = dict(workspace)
                    updated["cards"] = [
                        *list(workspace.get("cards") or []),
                        {
                            "card_id": f"card-{uuid.uuid4().hex[:12]}",
                            "column": zone,
                            "title": title,
                            "guidance": "",
                            "notes": notes,
                            "status": status,
                            "owner": "",
                            "due_date": "",
                            "tags": [],
                            "evidence_ids": [],
                            "order": len(list(workspace.get("cards") or [])) + 1,
                            "created_at": now,
                            "updated_at": now,
                        },
                    ]
                    store.save(updated)
                    st.toast("Card created.")
                    st.rerun()


def _render_workspace_header(store: SciencePlusCanvasStore, workspace: dict[str, Any]) -> dict[str, Any]:
    template = TEMPLATE_INDEX.get(str(workspace.get("template_key") or ""))
    badge_row = st.container(horizontal=True)
    with badge_row:
        st.badge(str(workspace.get("status") or "Draft"), color="green" if workspace.get("status") == "Complete" else "blue")
        if template:
            st.badge(template.category, color="violet")
            st.badge(template.canvas_type.upper(), color="gray")
        st.caption(f"Updated {str(workspace.get('updated_at') or '').replace('T', ' ')}")
    stats = _workspace_stats(workspace)
    summary_row = st.container(horizontal=True)
    with summary_row:
        st.metric("Cards", stats["cards"], border=True)
        st.metric("Evidence-linked", stats["evidence"], border=True)
        st.metric("Completed", stats["complete"], border=True)
        st.metric("Blocked", stats["blocked"], border=True)
        st.metric("Owners", stats["owners"], border=True)
    with st.expander("Canvas details", expanded=not bool(workspace.get("objective"))):
        with st.form(f"science_plus_details_{workspace['canvas_id']}", border=False):
            title = st.text_input("Canvas title", value=str(workspace.get("title") or ""))
            objective = st.text_area("Scientific objective", value=str(workspace.get("objective") or ""), height=100, placeholder="Define the bounded question, decision or deliverable this canvas supports.")
            description = st.text_area("Description", value=str(workspace.get("description") or ""), height=90)
            status = st.selectbox("Workspace status", WORKSPACE_STATUSES, index=WORKSPACE_STATUSES.index(str(workspace.get("status"))) if str(workspace.get("status")) in WORKSPACE_STATUSES else 0)
            if st.form_submit_button("Save canvas details", type="primary"):
                updated = dict(workspace)
                updated.update({"title": title, "objective": objective, "description": description, "status": status})
                store.save(updated)
                st.toast("Canvas details saved.")
                st.rerun()
    st.title(str(workspace.get("title") or "Science canvas"), anchor=False)
    if workspace.get("description"):
        st.caption(str(workspace["description"]))
    if workspace.get("workflow"):
        st.write(" → ".join(str(value) for value in list(workspace["workflow"])))
    return workspace


def _render_workspace(store: SciencePlusCanvasStore) -> None:
    canvas_id = str(st.session_state.get("science_plus_active_canvas") or "")
    workspace = store.load(canvas_id) if canvas_id else None
    if workspace is None:
        available = store.list()
        if not available:
            _render_canvas_empty_state(
                "No active canvas workspace.",
                "Create a canvas from Template library to start planning with templates, workflow stages and evidence-linked cards.",
                chips=["Professional templates", "Scientific notes", "Local-first export"],
            )
            return
        workspace = available[0]
        canvas_id = str(workspace["canvas_id"])
        st.session_state["science_plus_active_canvas"] = canvas_id
    _render_workspace_header(store, workspace)
    toolbar = st.container(horizontal=True)
    with toolbar:
        _render_add_card(store, workspace)
        if st.button("Duplicate canvas", key=f"science_plus_workspace_duplicate_{canvas_id}", icon=":material/content_copy:"):
            duplicate = store.duplicate(canvas_id)
            _set_active(str(duplicate["canvas_id"]))
            st.toast("Canvas duplicated.")
            st.rerun()
        st.download_button(
            "Export JSON", json.dumps(workspace, ensure_ascii=False, indent=2),
            file_name=f"{_safe_segment(str(workspace.get('title')), 'science-canvas')}.json", mime="application/json",
            key=f"science_plus_workspace_json_{canvas_id}", icon=":material/download:",
        )
        st.download_button(
            "Export Markdown", workspace_markdown(workspace),
            file_name=f"{_safe_segment(str(workspace.get('title')), 'science-canvas')}.md", mime="text/markdown",
            key=f"science_plus_workspace_md_{canvas_id}", icon=":material/article:",
        )
    canvas_view_key = f"science_plus_canvas_view_{canvas_id}"
    canvas_view_default = "Board" if canvas_view_key not in st.session_state else None
    view = st.segmented_control(
        "Canvas view", ("Board", "Table", "Graph", "Timeline"), default=canvas_view_default,
        key=canvas_view_key, label_visibility="collapsed", width="stretch",
    ) or "Board"
    if view == "Table":
        _render_table(store, workspace)
    elif view == "Graph":
        _render_graph(workspace)
    elif view == "Timeline":
        _render_timeline(workspace)
    else:
        _render_board(store, workspace)


def _record_label(record: Mapping[str, Any]) -> str:
    title = str(record.get("title") or "Untitled scientific record")
    source = str(record.get("source_name") or record.get("provider_key") or "source")
    return f"{title[:110]} · {source}"


def _render_evidence_linker(service: Any, store: SciencePlusCanvasStore, *, user_id: str, tenant_id: str) -> None:
    canvas_id = str(st.session_state.get("science_plus_active_canvas") or "")
    workspace = store.load(canvas_id) if canvas_id else None
    if workspace is None:
        st.info("Open a saved canvas before linking Science Plus evidence.")
        return
    query = st.text_input("Search persisted Science Plus evidence", placeholder="Title, gene, disease, method, DOI or PMID")
    records = service.store.search_items(query, tenant_id=tenant_id, limit=50)
    records = [record for record in records if str(record.get("live_state")) != "DEMO"]
    if not records:
        st.info("No persisted non-demo scientific record matches this search.")
        return
    labels = {_record_label(record): record for record in records}
    with st.form(f"science_plus_evidence_linker_{canvas_id}", border=True):
        selected_labels = st.multiselect("Scientific records", list(labels), max_selections=20)
        destination = st.selectbox("Canvas zone", list(workspace.get("columns") or []))
        mode = st.radio("Attach as", ("One evidence card per record", "Link to an existing card"), horizontal=True)
        existing_card = ""
        if mode == "Link to an existing card":
            card_options = {str(card.get("title") or card.get("card_id")): str(card.get("card_id")) for card in list(workspace.get("cards") or [])}
            existing_title = st.selectbox("Existing card", list(card_options)) if card_options else ""
            existing_card = card_options.get(existing_title, "")
        if st.form_submit_button("Attach evidence", type="primary"):
            selected_records = [labels[label] for label in selected_labels]
            if not selected_records:
                st.error("Select at least one persisted record.")
            else:
                updated = dict(workspace)
                cards = [dict(card) for card in list(workspace.get("cards") or [])]
                if existing_card:
                    for card in cards:
                        if str(card.get("card_id")) == existing_card:
                            card["evidence_ids"] = list(dict.fromkeys([*list(card.get("evidence_ids") or []), *(str(record["item_id"]) for record in selected_records)]))
                else:
                    now = _utc_now()
                    for record in selected_records:
                        source = str(record.get("source_name") or record.get("provider_key") or "Unknown source")
                        identifiers = [
                            f"DOI {record['doi']}" if record.get("doi") else "",
                            f"PMID {record['pmid']}" if record.get("pmid") else "",
                        ]
                        cards.append(
                            {
                                "card_id": f"card-{uuid.uuid4().hex[:12]}",
                                "column": destination,
                                "title": str(record.get("title") or "Untitled scientific record")[:240],
                                "guidance": "Persisted Science Plus evidence card. Review the original source before using the record in a scientific conclusion.",
                                "notes": f"Source: {source}. " + " · ".join(value for value in identifiers if value),
                                "status": "Needs evidence",
                                "owner": "",
                                "due_date": "",
                                "tags": [str(record.get("content_type") or "record")],
                                "evidence_ids": [str(record["item_id"])],
                                "order": len(cards) + 1,
                                "created_at": now,
                                "updated_at": now,
                            }
                        )
                updated["cards"] = cards
                store.save(updated)
                st.toast("Persisted evidence attached to the canvas.")
                st.rerun()
    for record in records[:12]:
        with st.container(border=True):
            st.markdown(f"**{record.get('title') or 'Untitled scientific record'}**")
            st.caption(f"{record.get('source_name') or record.get('provider_key') or 'Unknown source'} · {record.get('published_at') or 'date unavailable'} · {record.get('live_state') or 'CACHED'}")
            if record.get("abstract"):
                excerpt = str(record["abstract"])
                st.write(excerpt[:420] + ("…" if len(excerpt) > 420 else ""))
            if record.get("canonical_url"):
                st.link_button("Open original record", str(record["canonical_url"]), icon=":material/open_in_new:")


def _render_exports(store: SciencePlusCanvasStore) -> None:
    canvas_id = str(st.session_state.get("science_plus_active_canvas") or "")
    workspace = store.load(canvas_id) if canvas_id else None
    if workspace is None:
        st.info("Open a saved canvas to review export readiness and governance checks.")
        return
    checks = workspace_validation(workspace)
    ready = sum(1 for row in checks if row["State"] == "Ready")
    metrics = st.container(horizontal=True)
    with metrics:
        st.metric("Readiness checks", f"{ready}/{len(checks)}", border=True)
        st.metric("Cards", len(list(workspace.get("cards") or [])), border=True)
        st.metric("Evidence-linked", sum(1 for card in list(workspace.get("cards") or []) if card.get("evidence_ids")), border=True)
        st.metric("Blocked", sum(1 for card in list(workspace.get("cards") or []) if card.get("status") == "Blocked"), border=True)
    st.dataframe(pd.DataFrame(checks), width="stretch", hide_index=True)
    st.warning("Canvas exports are planning and evidence-organization artefacts. They are not automatic clinical, regulatory or scientific sign-off.")
    export_row = st.container(horizontal=True)
    with export_row:
        st.download_button(
            "Download JSON package", json.dumps(workspace, ensure_ascii=False, indent=2),
            file_name=f"{_safe_segment(str(workspace.get('title')), 'science-canvas')}.json", mime="application/json",
            key=f"science_plus_export_json_{canvas_id}", icon=":material/data_object:",
        )
        st.download_button(
            "Download Markdown report", workspace_markdown(workspace),
            file_name=f"{_safe_segment(str(workspace.get('title')), 'science-canvas')}.md", mime="text/markdown",
            key=f"science_plus_export_md_{canvas_id}", icon=":material/description:",
        )
        cards = pd.DataFrame(list(workspace.get("cards") or []))
        st.download_button(
            "Download card table", cards.to_csv(index=False) if not cards.empty else "",
            file_name=f"{_safe_segment(str(workspace.get('title')), 'science-canvas')}-cards.csv", mime="text/csv",
            key=f"science_plus_export_csv_{canvas_id}", icon=":material/table_view:",
        )



def render_canvas_studio(
    root: str | Path,
    service: Any,
    *,
    user_id: str,
    tenant_id: str,
    can_administer: bool = False,
) -> None:
    del can_administer  # Canvas ownership is user-scoped; administration is not required for personal workspaces.
    store = SciencePlusCanvasStore(root, tenant_id=tenant_id, user_id=user_id)
    workspaces = store.list()
    active_id = str(st.session_state.get("science_plus_active_canvas") or "")
    active = store.load(active_id) if active_id else None
    health = service.health(tenant_id)
    active_cards = len(list(active.get("cards") or [])) if active else 0
    st.markdown(
        f"""
        <section class="science-plus-hero">
            <div class="science-plus-eyebrow">Canvas Studio</div>
            <h2>Science Plus Canvas Studio</h2>
            <p>Professional scientific planning, evidence mapping and decision canvases. Local-first, user-scoped and source-aware.</p>
            <div class="science-plus-stat-grid">
                <div class="science-plus-stat"><strong>{len(TEMPLATES)}</strong><span>Professional templates</span></div>
                <div class="science-plus-stat"><strong>{len(workspaces)}</strong><span>Saved canvases</span></div>
                <div class="science-plus-stat"><strong>{int(health.get('items') or 0)}</strong><span>Scientific records</span></div>
                <div class="science-plus-stat"><strong>{active_cards}</strong><span>Active canvas cards</span></div>
            </div>
            <div class="science-plus-chip-row">
                <span class="science-plus-chip">Board</span>
                <span class="science-plus-chip">Table</span>
                <span class="science-plus-chip">Graph</span>
                <span class="science-plus-chip">Timeline</span>
                <span class="science-plus-chip">Evidence linker</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if active:
        stats = _workspace_stats(active)
        checks = workspace_validation(active)
        ready_checks = sum(1 for row in checks if row["State"] == "Ready")
        readiness = int(round((ready_checks / max(1, len(checks))) * 100))
        st.markdown(
            f"""
            <div class="science-plus-canvas-context">
                <div>
                    <div class="science-plus-kicker">Active scientific canvas</div>
                    <strong>{html.escape(str(active.get('title') or 'Science canvas'))}</strong>
                    <span>{html.escape(str(active.get('status') or 'Draft'))} · updated {html.escape(str(active.get('updated_at') or 'time unavailable').replace('T', ' '))}</span>
                </div>
                <div><strong>{stats['cards']}</strong><span>Total cards</span></div>
                <div><strong>{stats['evidence']}</strong><span>Evidence-linked cards</span></div>
                <div><strong>{readiness}%</strong><span>Governance readiness</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.progress(readiness, text=f"Canvas readiness · {ready_checks}/{len(checks)} checks ready")
        quick = st.container(horizontal=True)
        with quick:
            if st.button("Open workspace", icon=":material/edit_note:", key=f"science_plus_jump_workspace_{active_id}"):
                st.session_state["science_plus_studio_view"] = "Canvas workspace"
                st.rerun()
            if st.button("Link evidence", icon=":material/link:", key=f"science_plus_jump_evidence_{active_id}"):
                st.session_state["science_plus_studio_view"] = "Evidence linker"
                st.rerun()
            if st.button("Review exports", icon=":material/fact_check:", key=f"science_plus_jump_exports_{active_id}"):
                st.session_state["science_plus_studio_view"] = "Exports & governance"
                st.rerun()
    else:
        st.markdown(
            f"""
            <div class="science-plus-canvas-context">
                <div>
                    <div class="science-plus-kicker">Canvas workspace</div>
                    <strong>No active canvas selected</strong>
                    <span>Start from a professional template or open a saved canvas to begin evidence-linked planning.</span>
                </div>
                <div><strong>{len(TEMPLATES)}</strong><span>Templates ready</span></div>
                <div><strong>{len(workspaces)}</strong><span>Saved canvases</span></div>
                <div><strong>{int(health.get('items') or 0)}</strong><span>Evidence records available</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    studio_fallback = "Canvas workspace" if active else "Template library"
    studio_default = studio_fallback if "science_plus_studio_view" not in st.session_state else None
    view = st.segmented_control(
        "Canvas Studio navigation",
        ("Template library", "My canvases", "Canvas workspace", "Evidence linker", "Exports & governance"),
        default=studio_default,
        key="science_plus_studio_view",
        width="stretch",
    ) or studio_fallback
    _render_canvas_navigation_overview(str(view))
    if view == "My canvases":
        _render_canvas_library(store)
    elif view == "Canvas workspace":
        _render_workspace(store)
    elif view == "Evidence linker":
        _render_evidence_linker(service, store, user_id=user_id, tenant_id=tenant_id)
    elif view == "Exports & governance":
        _render_exports(store)
    else:
        _render_template_library(store)


__all__ = [
    "CANVAS_SCHEMA_VERSION",
    "CARD_STATUSES",
    "SciencePlusCanvasStore",
    "TEMPLATES",
    "TEMPLATE_CATEGORIES",
    "TEMPLATE_INDEX",
    "WORKSPACE_STATUSES",
    "render_canvas_studio",
    "workspace_markdown",
    "workspace_validation",
]
