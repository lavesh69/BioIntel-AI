from __future__ import annotations

"""Domain-aware visual augmentation for BioIntel AI scientific modules.

This layer deliberately excludes AI Lab, Operations and Governance pages. It adds
one bounded, selectable five-view visual suite to every other legacy page while
newer NextGen modules continue to use their native data-linked visual workbench.
"""

from dataclasses import dataclass
import hashlib
import math
from typing import Any, Iterable

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

EXCLUDED_CATEGORIES = frozenset({"AI Lab", "Operations", "Governance"})
MAX_VISUAL_ROWS = 5_000


@dataclass(frozen=True)
class VisualSpec:
    key: str
    title: str
    purpose: str
    method: str
    kind: str


FAMILY_TEMPLATES: dict[str, tuple[VisualSpec, ...]] = {
    "start": (
        VisualSpec("workflow", "Scientific workflow progress", "Shows active and pending workflow stages.", "Stage-state timeline", "timeline"),
        VisualSpec("domain", "Scientific domain coverage", "Compares activity across major BioIntel domains.", "Domain activity radar", "radar"),
        VisualSpec("activity", "Recent research activity", "Shows the volume and status of recent work.", "Time-binned activity", "line"),
        VisualSpec("risk", "Workspace risk matrix", "Locates current blockers by likelihood and impact.", "Likelihood-impact matrix", "risk"),
        VisualSpec("next", "Recommended next actions", "Ranks the next useful user actions.", "Priority and readiness ranking", "ranking"),
    ),
    "sequence": (
        VisualSpec("composition", "Sequence composition profile", "Shows base or residue composition and ambiguity burden.", "Composition frequency", "bar"),
        VisualSpec("track", "Sequence feature track", "Places motifs, ORFs and quality events along sequence coordinates.", "Coordinate feature track", "track"),
        VisualSpec("window", "Sliding sequence quality", "Shows local GC, complexity or conservation changes.", "Rolling-window profile", "line"),
        VisualSpec("length", "Sequence length distribution", "Compares record lengths and highlights outliers.", "Length distribution", "hist"),
        VisualSpec("decision", "Sequence review priorities", "Ranks records needing manual review.", "Quality-weighted ranking", "ranking"),
    ),
    "fastq": (
        VisualSpec("cycle", "Per-cycle quality profile", "Shows quality decay and read-end instability.", "Per-cycle mean and percentile profile", "multiline"),
        VisualSpec("gc", "GC-content distribution", "Detects composition shifts and contamination patterns.", "GC histogram", "hist"),
        VisualSpec("adapter", "Adapter-position profile", "Shows where adapter signal increases along reads.", "Position-wise adapter rate", "line"),
        VisualSpec("length", "Read-length distribution", "Compares read lengths across samples.", "Length distribution", "hist"),
        VisualSpec("sample_qc", "Multi-sample QC heatmap", "Summarises pass, review and fail metrics by sample.", "Sample × QC metric matrix", "heatmap"),
    ),
    "variant": (
        VisualSpec("density", "Genome-wide variant density", "Shows variant burden across chromosomes or regions.", "Binned genomic density", "manhattan"),
        VisualSpec("consequence", "Variant consequence composition", "Shows the balance of predicted consequence classes.", "Consequence frequency", "bar"),
        VisualSpec("frequency", "Allele-frequency spectrum", "Separates rare and common findings.", "Allele-frequency histogram", "hist"),
        VisualSpec("genotype", "Sample genotype matrix", "Shows genotype states across samples and variants.", "Variant × sample matrix", "heatmap"),
        VisualSpec("evidence", "Variant evidence waterfall", "Shows how frequency, impact and phenotype evidence contribute to priority.", "Evidence contribution waterfall", "waterfall"),
    ),
    "transcriptomics": (
        VisualSpec("pca", "Sample expression landscape", "Shows clustering, outliers and batch structure.", "Two-component projection", "scatter"),
        VisualSpec("volcano", "Differential-expression volcano", "Combines effect size and statistical evidence.", "Effect versus −log10 evidence", "volcano"),
        VisualSpec("heatmap", "Top-feature expression heatmap", "Shows expression patterns across samples.", "Feature × sample matrix", "heatmap"),
        VisualSpec("correlation", "Sample correlation matrix", "Reveals replicate consistency and outliers.", "Pairwise correlation", "heatmap"),
        VisualSpec("pathway", "Pathway enrichment overview", "Ranks pathway-level signals.", "Gene-ratio and evidence bubble plot", "bubble"),
    ),
    "protein": (
        VisualSpec("domains", "Protein feature architecture", "Places domains, signal peptides, TM regions and disorder on sequence coordinates.", "Protein coordinate track", "track"),
        VisualSpec("properties", "Protein property profile", "Compares stability, solubility and composition indicators.", "Normalised property radar", "radar"),
        VisualSpec("ptm", "PTM and residue-event map", "Shows modification and mutation positions.", "Residue lollipop plot", "lollipop"),
        VisualSpec("coverage", "Peptide or annotation coverage", "Shows which sequence regions are supported.", "Coverage profile", "line"),
        VisualSpec("ranking", "Protein candidate ranking", "Prioritises records using quality and evidence.", "Composite evidence ranking", "ranking"),
    ),
    "phylogeny": (
        VisualSpec("tree", "Phylogenetic relationship view", "Shows lineage relationships and clade structure.", "Radial relationship network", "network"),
        VisualSpec("distance", "Genomic distance heatmap", "Compares pairwise sequence or isolate distances.", "Pairwise distance matrix", "heatmap"),
        VisualSpec("timeline", "Lineage emergence timeline", "Shows when lineages or mutations appear.", "Temporal lineage profile", "line"),
        VisualSpec("mutation", "Mutation burden by lineage", "Compares lineage-level mutation counts.", "Grouped mutation burden", "bar"),
        VisualSpec("metadata", "Lineage metadata composition", "Shows location, host or phenotype distribution by lineage.", "Metadata composition", "bubble"),
    ),
    "single_cell": (
        VisualSpec("embedding", "Cell-state embedding", "Shows clusters, conditions and candidate transitions.", "Bounded two-dimensional embedding", "scatter"),
        VisualSpec("qc", "Single-cell QC distributions", "Shows library size, genes and mitochondrial burden.", "QC distribution panel", "box"),
        VisualSpec("markers", "Cluster marker heatmap", "Compares marker programmes across clusters.", "Cluster × marker matrix", "heatmap"),
        VisualSpec("composition", "Cell-type composition", "Shows cluster proportions by sample or condition.", "Stacked composition", "stacked"),
        VisualSpec("trajectory", "Cell-state trajectory", "Shows ordered progression through inferred states.", "Pseudotime trajectory", "line"),
    ),
    "cancer": (
        VisualSpec("oncoplot", "Cancer alteration oncoplot", "Shows recurrent alterations across samples.", "Gene × sample alteration matrix", "heatmap"),
        VisualSpec("tmb", "Mutation-burden distribution", "Compares sample-level mutation burden.", "TMB distribution", "hist"),
        VisualSpec("signature", "Mutational-signature profile", "Shows relative signature contributions.", "Signature composition", "stacked"),
        VisualSpec("cnv", "Copy-number landscape", "Shows chromosome-level gains and losses.", "Sample × region CNV matrix", "heatmap"),
        VisualSpec("clonal", "Clonal evolution view", "Shows subclone relationships and fractions.", "Clone relationship network", "network"),
    ),
    "discovery": (
        VisualSpec("space", "Chemical-space landscape", "Shows candidate diversity and clusters.", "Descriptor projection", "scatter"),
        VisualSpec("radar", "Developability profile", "Compares potency, selectivity and physicochemical properties.", "Normalised multi-property radar", "radar"),
        VisualSpec("scaffold", "Scaffold series composition", "Shows scaffold representation and diversity.", "Scaffold frequency", "bar"),
        VisualSpec("liability", "Liability and alert matrix", "Shows candidate-level structural and ADMET concerns.", "Candidate × liability matrix", "heatmap"),
        VisualSpec("pareto", "Candidate trade-off frontier", "Identifies balanced candidates across competing objectives.", "Multi-objective Pareto landscape", "scatter"),
    ),
    "dti": (
        VisualSpec("scores", "Interaction-score distribution", "Shows score separation and review thresholds.", "Prediction distribution", "hist"),
        VisualSpec("calibration", "Prediction calibration", "Compares expected and observed interaction rates.", "Reliability diagram", "calibration"),
        VisualSpec("domain", "Applicability-domain map", "Shows in-domain and out-of-domain candidates.", "Similarity versus uncertainty", "scatter"),
        VisualSpec("family", "Target-family performance", "Compares performance across target families.", "Family × metric heatmap", "heatmap"),
        VisualSpec("explain", "Prediction evidence contributions", "Shows major feature-group contributions.", "Contribution waterfall", "waterfall"),
    ),
    "structure": (
        VisualSpec("structure", "Interactive structure overview", "Shows chains, ligands and residues in three dimensions.", "Bounded 3D coordinate view", "structure3d"),
        VisualSpec("contacts", "Residue contact map", "Shows local contacts and interaction density.", "Residue × residue matrix", "heatmap"),
        VisualSpec("quality", "Structure quality profile", "Shows confidence, clashes and residue-level review needs.", "Per-residue quality profile", "line"),
        VisualSpec("pockets", "Pocket and ligand ranking", "Compares candidate binding sites.", "Pocket score ranking", "ranking"),
        VisualSpec("mutations", "Mutation-to-structure map", "Shows mutation positions and predicted effects.", "Residue effect lollipop", "lollipop"),
    ),
    "pathway": (
        VisualSpec("network", "Gene–pathway network", "Shows connected genes, pathways and evidence.", "Bipartite evidence network", "network"),
        VisualSpec("bubble", "Enrichment bubble plot", "Compares gene ratio, significance and pathway size.", "Enrichment bubble", "bubble"),
        VisualSpec("overlap", "Pathway overlap matrix", "Shows shared genes among pathways.", "Pathway similarity heatmap", "heatmap"),
        VisualSpec("leading", "Leading-edge gene contribution", "Ranks genes driving pathway signals.", "Contribution ranking", "ranking"),
        VisualSpec("evidence", "Pathway evidence status", "Separates reference, screening and validated evidence.", "Evidence-status composition", "stacked"),
    ),
    "lab_assay": (
        VisualSpec("plate", "Plate spatial QC", "Shows control placement, drift and edge effects.", "Well-position heatmap", "plate"),
        VisualSpec("curve", "Assay response curve", "Shows standards, unknowns and valid range.", "Calibration or kinetic curve", "curve"),
        VisualSpec("residual", "Model residual diagnostics", "Shows systematic calibration or kinetic error.", "Residual profile", "scatter"),
        VisualSpec("precision", "Replicate precision", "Compares replicate variability and run acceptance.", "Replicate CV distribution", "box"),
        VisualSpec("acceptance", "Run acceptance summary", "Shows pass, review and fail criteria.", "Acceptance matrix", "heatmap"),
    ),
    "microbiome": (
        VisualSpec("composition", "Taxonomic composition", "Shows relative abundance by sample.", "Stacked abundance chart", "stacked"),
        VisualSpec("alpha", "Alpha-diversity comparison", "Compares within-sample diversity.", "Diversity distribution", "box"),
        VisualSpec("beta", "Beta-diversity ordination", "Shows community separation and outliers.", "Two-dimensional ordination", "scatter"),
        VisualSpec("taxa", "Differential taxa heatmap", "Shows taxa associated with groups or conditions.", "Taxa × group matrix", "heatmap"),
        VisualSpec("function", "Functional pathway coverage", "Shows functional profile differences.", "Pathway composition", "bar"),
    ),
    "bioprocess": (
        VisualSpec("trajectory", "Bioprocess trajectories", "Shows biomass, substrate and product over time.", "Time-series process profile", "multiline"),
        VisualSpec("tunnel", "Golden-batch tolerance tunnel", "Compares current and reference trajectories.", "Tolerance-envelope chart", "tunnel"),
        VisualSpec("control", "Process control chart", "Shows centre line and control-limit excursions.", "SPC-style control chart", "control"),
        VisualSpec("feed", "Feed and volume profile", "Shows process interventions over time.", "Feed/volume time series", "multiline"),
        VisualSpec("deviation", "Batch deviation heatmap", "Shows parameter deviations across batches.", "Batch × parameter matrix", "heatmap"),
    ),
    "data": (
        VisualSpec("missing", "Data completeness profile", "Shows missingness and schema quality.", "Column completeness bar", "bar"),
        VisualSpec("lineage", "Data lineage graph", "Shows source, transformation and output relationships.", "Directed lineage network", "network"),
        VisualSpec("coverage", "Scientific coverage map", "Shows organism, tissue, assay or cohort coverage.", "Coverage heatmap", "heatmap"),
        VisualSpec("freshness", "Source freshness timeline", "Shows release and review recency.", "Freshness timeline", "line"),
        VisualSpec("readiness", "Data readiness decision", "Separates metadata integrity from scientific readiness.", "Readiness matrix", "risk"),
    ),
    "document": (
        VisualSpec("pages", "Page extraction confidence", "Shows OCR and layout confidence by page.", "Page-level confidence profile", "line"),
        VisualSpec("layout", "Document layout map", "Shows text, table, figure and heading regions.", "Layout block canvas", "layout"),
        VisualSpec("entities", "Scientific entity composition", "Shows extracted genes, drugs, diseases and methods.", "Entity frequency", "bar"),
        VisualSpec("evidence", "Claim-to-source evidence graph", "Links claims to supporting document regions.", "Evidence network", "network"),
        VisualSpec("history", "Extraction and correction history", "Shows versions, corrections and review state.", "Processing timeline", "timeline"),
    ),
    "knowledge": (
        VisualSpec("graph", "Biomedical relationship graph", "Shows evidence-linked entities and relationships.", "Bounded relationship network", "network"),
        VisualSpec("sources", "Source diversity", "Shows provider and evidence-source balance.", "Source composition", "bar"),
        VisualSpec("constellation", "Hypothesis–evidence constellation", "Shows supporting, contradictory and unresolved evidence.", "Evidence constellation", "network"),
        VisualSpec("contradiction", "Evidence contradiction matrix", "Shows where sources disagree.", "Source × claim contradiction matrix", "heatmap"),
        VisualSpec("coverage", "Knowledge coverage", "Shows entity and relationship coverage gaps.", "Coverage radar", "radar"),
    ),
    "settings": (
        VisualSpec("theme", "Theme and component preview", "Shows the current design system across common components.", "Component preview matrix", "heatmap"),
        VisualSpec("contrast", "Accessibility contrast audit", "Shows pass and review states for text and surfaces.", "Contrast compliance matrix", "heatmap"),
        VisualSpec("type", "Typography scale preview", "Shows hierarchy and density consistency.", "Typography scale", "ranking"),
        VisualSpec("privacy", "Local data-flow map", "Shows where data is processed and retained.", "Privacy flow network", "network"),
        VisualSpec("preferences", "Preference impact summary", "Shows current accessibility and density choices.", "Preference radar", "radar"),
    ),
    "clinical": (
        VisualSpec("cohort", "Cohort flow", "Shows inclusion, exclusion and analysis populations.", "Cohort attrition funnel", "funnel"),
        VisualSpec("survival", "Outcome or survival trajectory", "Compares outcome trajectories across groups.", "Kaplan–Meier-style curve", "survival"),
        VisualSpec("subgroup", "Subgroup effect forest", "Shows effect estimates and uncertainty across subgroups.", "Forest plot", "forest"),
        VisualSpec("calibration", "Clinical risk calibration", "Compares predicted and observed risk.", "Reliability diagram", "calibration"),
        VisualSpec("decision", "Clinical decision curve", "Shows threshold-dependent net benefit.", "Decision-curve profile", "decision"),
    ),
    "therapy": (
        VisualSpec("construct", "Therapeutic construct profile", "Compares efficacy, safety and manufacturability.", "Construct property radar", "radar"),
        VisualSpec("risk", "Therapy safety-risk matrix", "Shows immunogenicity, off-target and delivery risks.", "Safety risk heatmap", "heatmap"),
        VisualSpec("evidence", "Translational evidence funnel", "Shows evidence maturity from design to validation.", "Evidence attrition funnel", "funnel"),
        VisualSpec("mechanism", "Therapeutic mechanism map", "Shows target, delivery and biological-response links.", "Mechanism network", "network"),
        VisualSpec("plan", "Experiment and validation plan", "Shows the next validation stages and blockers.", "Validation timeline", "timeline"),
    ),
    "research": (
        VisualSpec("design", "Experimental design geometry", "Shows factor-space coverage and replication.", "Design-space scatter", "scatter"),
        VisualSpec("power", "Power and sample-size curve", "Shows sensitivity to effect size and sample size.", "Power curve", "line"),
        VisualSpec("balance", "Randomisation balance", "Shows covariate balance across arms or groups.", "Balance heatmap", "heatmap"),
        VisualSpec("timeline", "Study execution timeline", "Shows milestones and dependencies.", "Study timeline", "timeline"),
        VisualSpec("risk", "Study design risk matrix", "Shows assumptions and design blockers.", "Design risk matrix", "risk"),
    ),
    "spatial": (
        VisualSpec("tissue", "Spatial tissue map", "Shows spots, cells or regions in tissue coordinates.", "Coordinate-linked tissue view", "spatial"),
        VisualSpec("regions", "Regional biomarker heatmap", "Shows molecular signals across tissue regions.", "Region × feature matrix", "heatmap"),
        VisualSpec("cells", "Cell-type composition", "Shows cell-state composition by region or patient.", "Stacked composition", "stacked"),
        VisualSpec("uncertainty", "Spatial uncertainty map", "Shows low-confidence or out-of-domain regions.", "Uncertainty coordinate map", "spatial"),
        VisualSpec("patients", "Patient spatial comparison", "Compares spatial biomarkers across patients.", "Patient-level regional summary", "bubble"),
    ),
    "generic": (
        VisualSpec("distribution", "Primary result distribution", "Shows spread, outliers and central tendency.", "Distribution diagnostic", "hist"),
        VisualSpec("relationship", "Primary relationship", "Shows association between the leading measures.", "Exploratory scatter", "scatter"),
        VisualSpec("groups", "Group comparison", "Compares the leading measure across groups.", "Group-level comparison", "box"),
        VisualSpec("quality", "Data quality heatmap", "Shows record and field-level quality.", "Quality matrix", "heatmap"),
        VisualSpec("decision", "Decision priority", "Ranks records for next action.", "Composite priority ranking", "ranking"),
    ),
}


def is_visual_target(category: str | None) -> bool:
    return str(category or "").strip() not in EXCLUDED_CATEGORIES


def _contains(text: str, words: Iterable[str]) -> bool:
    return any(word in text for word in words)


def family_for(page_key: str, title: str, category: str) -> str:
    text = f"{page_key} {title}".lower()
    if category == "Start":
        return "start"
    if category == "Settings":
        return "settings"
    if category == "Research Planning":
        return "research"
    if category == "Clinical Research":
        return "therapy" if _contains(text, ("therapy", "pharmaco", "pangenome population")) else "clinical"
    if category == "Data":
        return "document" if _contains(text, ("document", "ocr", "layout", "evidence bridge")) else "data"
    if category == "Intelligence":
        return "document" if "document" in text else "knowledge"
    if category == "Discovery":
        if _contains(text, ("dti", "interaction")):
            return "dti"
        if _contains(text, ("structural", "docking", "dynamics", "ligand")):
            return "structure"
        if _contains(text, ("pathway", "network", "host–pathogen", "host-pathogen")):
            return "pathway"
        if _contains(text, ("cell therapy", "car-t", "vaccine", "immunoinformatics")):
            return "therapy"
        return "discovery"
    if category == "Lab Analytics":
        if _contains(text, ("metagenom", "microbi", "strain")):
            return "microbiome"
        if _contains(text, ("bioprocess", "fermentation", "pat")):
            return "bioprocess"
        if _contains(text, ("gene therapy", "vector")):
            return "therapy"
        if _contains(text, ("bioimage", "microscopy", "organoid", "phenotypic")):
            return "spatial"
        return "lab_assay"
    if category == "Bioinformatics":
        if _contains(text, ("fastq", "genome qc")):
            return "fastq"
        if _contains(text, ("variant", "rare disease", "gwas", "population genetics", "repeat expansion", "genome editing safety")):
            return "variant"
        if _contains(text, ("transcript", "rna isoform", "splicing", "epitranscript", "multi-omics", "multiomics", "omics integration", "longitudinal")):
            return "transcriptomics"
        if _contains(text, ("protein", "proteom", "glycom")):
            return "protein"
        if _contains(text, ("phylogen", "pathogen", "outbreak", "virology", "amr", "one health")):
            return "phylogeny"
        if _contains(text, ("single-cell", "single cell", "cell atlas", "trajectory")):
            return "single_cell"
        if _contains(text, ("cancer", "tumour", "tumor")):
            return "cancer"
        if _contains(text, ("spatial", "pathology", "epigenome", "chromatin", "methylation")):
            return "spatial"
        if _contains(text, ("metabol", "lipid")):
            return "transcriptomics"
        if _contains(text, ("alignment", "comparison", "pangenome", "assembly")):
            return "phylogeny"
        return "sequence"
    return "generic"


def specs_for(page_key: str, title: str, category: str) -> tuple[VisualSpec, ...]:
    return FAMILY_TEMPLATES[family_for(page_key, title, category)]


def _seed(page_key: str) -> int:
    return int(hashlib.sha256(page_key.encode("utf-8")).hexdigest()[:8], 16)


def _bounded_frame(value: Any) -> pd.DataFrame:
    try:
        frame = value.copy(deep=False) if isinstance(value, pd.DataFrame) else pd.DataFrame(value)
    except Exception:
        return pd.DataFrame()
    if frame.empty:
        return frame
    frame = frame.loc[:, ~frame.columns.astype(str).duplicated()].copy()
    frame.columns = [str(column) for column in frame.columns]
    for column in frame.columns:
        if pd.api.types.is_numeric_dtype(frame[column].dtype):
            frame[column] = frame[column].replace([np.inf, -np.inf], np.nan)
    if len(frame) > MAX_VISUAL_ROWS:
        positions = np.linspace(0, len(frame) - 1, MAX_VISUAL_ROWS, dtype=int)
        frame = frame.iloc[positions]
    return frame.reset_index(drop=True)


def _session_frame(st: Any, page_key: str) -> pd.DataFrame:
    candidates: list[tuple[int, int, pd.DataFrame]] = []
    tokens = {token for token in page_key.lower().split("_") if len(token) > 2}
    for key, value in list(st.session_state.items()):
        key_text = str(key).lower()
        score = 0
        if page_key.lower() in key_text:
            score += 10
        score += sum(2 for token in tokens if token in key_text)
        if any(token in key_text for token in ("result", "data", "frame", "table", "preview")):
            score += 2
        values = [value]
        if hasattr(value, "result"):
            values.insert(0, getattr(value, "result"))
        if isinstance(value, dict):
            values.extend(value.get(name) for name in ("result", "data", "frame", "table", "preview") if name in value)
        for item in values:
            frame = _bounded_frame(item)
            if not frame.empty and len(frame.columns) >= 1:
                candidates.append((score, min(len(frame), MAX_VISUAL_ROWS), frame))
    if not candidates:
        return pd.DataFrame()
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def _demo_frame(page_key: str, family: str, rows: int = 180) -> pd.DataFrame:
    rng = np.random.default_rng(_seed(page_key))
    n = max(48, min(int(rows), 360))
    groups = np.array(["Control", "Treatment", "Reference"])
    frame = pd.DataFrame({
        "record_id": [f"{page_key[:10]}-{index + 1:04d}" for index in range(n)],
        "sample": [f"S{index % 24 + 1:02d}" for index in range(n)],
        "group": groups[np.arange(n) % len(groups)],
        "score": np.clip(rng.beta(2.5, 2.2, n), 0, 1),
        "confidence": np.clip(rng.normal(0.78, 0.14, n), 0, 1),
        "value": rng.normal(0, 1, n),
        "value_2": rng.normal(0.2, 1.1, n),
        "time": np.arange(n) % 30,
        "status": np.where(np.arange(n) % 11 == 0, "Review", np.where(np.arange(n) % 7 == 0, "Warning", "Pass")),
    })
    if family in {"variant", "phylogeny", "cancer"}:
        frame["chromosome"] = [str(index % 22 + 1) for index in range(n)]
        frame["position"] = np.arange(n) * 10_000 + rng.integers(1, 9_000, n)
        frame["allele_frequency"] = np.clip(rng.lognormal(-4, 1.4, n), 1e-6, 0.5)
        frame["consequence"] = np.array(["missense", "synonymous", "splice", "frameshift"])[np.arange(n) % 4]
    if family in {"transcriptomics", "single_cell", "spatial", "cancer"}:
        frame["log2_fold_change"] = rng.normal(0, 1.4, n)
        frame["p_value"] = np.clip(rng.beta(0.7, 8, n), 1e-8, 1)
        frame["cluster"] = [f"C{index % 7 + 1}" for index in range(n)]
        frame["x"] = rng.normal(0, 2.0, n)
        frame["y"] = rng.normal(0, 2.0, n)
    if family in {"discovery", "dti", "structure"}:
        frame["potency"] = np.clip(rng.normal(0.68, 0.18, n), 0, 1)
        frame["selectivity"] = np.clip(rng.normal(0.62, 0.2, n), 0, 1)
        frame["developability"] = np.clip(rng.normal(0.7, 0.16, n), 0, 1)
        frame["uncertainty"] = np.clip(1 - frame["confidence"] + rng.normal(0, 0.05, n), 0, 1)
        frame["family"] = [f"Family {index % 6 + 1}" for index in range(n)]
    if family in {"lab_assay", "bioprocess"}:
        frame["batch"] = [f"B{index % 8 + 1}" for index in range(n)]
        frame["replicate"] = [index % 3 + 1 for index in range(n)]
        frame["response"] = np.clip(0.15 + 0.82 / (1 + np.exp(-(frame["time"] - 12) / 3)) + rng.normal(0, 0.04, n), 0, 1.2)
        frame["cv_percent"] = np.clip(rng.normal(8, 4, n), 0, 35)
    if family == "microbiome":
        frame["taxon"] = [f"Taxon {index % 12 + 1}" for index in range(n)]
        frame["abundance"] = rng.dirichlet(np.ones(12), size=max(1, math.ceil(n / 12))).reshape(-1)[:n]
        frame["diversity"] = np.clip(rng.normal(3.2, 0.7, n), 0, None)
    if family in {"data", "document", "knowledge"}:
        frame["source"] = np.array(["Local", "Curated", "Provider", "Review"])[np.arange(n) % 4]
        frame["completeness"] = np.clip(rng.normal(0.86, 0.12, n), 0, 1)
        frame["freshness_days"] = rng.integers(0, 365, n)
        frame.loc[frame.index % 13 == 0, "value_2"] = np.nan
    if family in {"clinical", "therapy", "research"}:
        frame["arm"] = np.array(["Control", "Intervention"])[np.arange(n) % 2]
        frame["event"] = (rng.random(n) < 0.35).astype(int)
        frame["survival"] = np.clip(np.exp(-frame["time"] / 45) + rng.normal(0, 0.03, n), 0, 1)
        frame["effect"] = rng.normal(0.2, 0.25, n)
        frame["lower"] = frame["effect"] - rng.uniform(0.08, 0.28, n)
        frame["upper"] = frame["effect"] + rng.uniform(0.08, 0.28, n)
    return frame


def _numeric(frame: pd.DataFrame) -> list[str]:
    return [str(column) for column in frame.columns if pd.to_numeric(frame[column], errors="coerce").notna().sum() >= 3]


def _categorical(frame: pd.DataFrame) -> list[str]:
    out: list[str] = []
    for column in frame.columns:
        count = frame[column].dropna().astype(str).nunique()
        if 1 < count <= 40:
            out.append(str(column))
    return out


def _normalise(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    if not values.notna().any():
        return pd.Series(np.zeros(len(series)), index=series.index)
    low, high = float(values.min()), float(values.max())
    if math.isclose(low, high):
        return pd.Series(np.full(len(series), 0.5), index=series.index)
    return ((values - low) / (high - low)).fillna(0.0)


def _matrix(frame: pd.DataFrame, rows: int = 12, cols: int = 12, value: str | None = None) -> pd.DataFrame:
    numeric = _numeric(frame)
    source = pd.to_numeric(frame[value], errors="coerce") if value and value in frame else pd.to_numeric(frame[numeric[0]], errors="coerce") if numeric else pd.Series(np.arange(len(frame)))
    data = np.resize(source.fillna(source.median() if source.notna().any() else 0).to_numpy(), rows * cols).reshape(rows, cols)
    return pd.DataFrame(data, index=[f"R{i+1}" for i in range(rows)], columns=[f"C{i+1}" for i in range(cols)])


def _network_figure(frame: pd.DataFrame, title: str) -> go.Figure:
    count = min(24, max(6, len(frame) // 5))
    nodes = [f"N{index + 1}" for index in range(count)]
    angle = np.linspace(0, 2 * np.pi, count, endpoint=False)
    positions = {node: (float(np.cos(a)), float(np.sin(a))) for node, a in zip(nodes, angle)}
    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for index in range(count):
        a, b = nodes[index], nodes[(index * 3 + 5) % count]
        edge_x.extend([positions[a][0], positions[b][0], None])
        edge_y.extend([positions[a][1], positions[b][1], None])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines", hoverinfo="skip", name="links"))
    fig.add_trace(go.Scatter(x=[positions[n][0] for n in nodes], y=[positions[n][1] for n in nodes], text=nodes, mode="markers+text", textposition="top center", marker={"size": 14}, name="entities"))
    fig.update_layout(title=title, showlegend=False, xaxis={"visible": False}, yaxis={"visible": False})
    return fig


def _figure(spec: VisualSpec, frame: pd.DataFrame, page_key: str, family: str) -> tuple[go.Figure, pd.DataFrame]:
    numeric = _numeric(frame)
    categorical = _categorical(frame)
    xnum = numeric[0] if numeric else None
    ynum = numeric[1] if len(numeric) > 1 else xnum
    cat = categorical[0] if categorical else None
    data = frame.head(MAX_VISUAL_ROWS).copy()
    kind = spec.kind

    if kind in {"heatmap", "plate", "layout"}:
        matrix = _matrix(data, 8 if kind == "plate" else 12, 12, ynum)
        fig = px.imshow(matrix, aspect="auto", title=spec.title, labels={"x": "Column", "y": "Row", "color": "Value"})
        return fig, matrix.reset_index(names="row")
    if kind == "radar":
        metrics = numeric[:5] or ["score"]
        values = [float(_normalise(data[m]).mean()) for m in metrics]
        fig = go.Figure(go.Scatterpolar(r=values + values[:1], theta=metrics + metrics[:1], fill="toself", name="Profile"))
        fig.update_layout(title=spec.title, polar={"radialaxis": {"visible": True, "range": [0, 1]}}, showlegend=False)
        return fig, pd.DataFrame({"metric": metrics, "normalised_value": values})
    if kind in {"line", "multiline", "timeline", "control", "tunnel", "survival", "decision", "calibration", "curve"}:
        timeline = pd.DataFrame({"x": np.arange(min(60, max(20, len(data)))), "observed": np.linspace(0.1, 0.9, min(60, max(20, len(data))))})
        rng = np.random.default_rng(_seed(page_key + spec.key))
        timeline["observed"] = np.clip(timeline["observed"] + rng.normal(0, 0.06, len(timeline)), 0, 1)
        fig = go.Figure()
        if kind == "calibration":
            timeline["expected"] = timeline["x"] / max(timeline["x"].max(), 1)
            timeline["observed"] = np.clip(timeline["expected"] + rng.normal(0, 0.05, len(timeline)), 0, 1)
            fig.add_trace(go.Scatter(x=timeline["expected"], y=timeline["observed"], mode="lines+markers", name="Observed"))
            fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Ideal", line={"dash": "dash"}))
        elif kind == "tunnel":
            timeline["reference"] = np.clip(np.linspace(0.2, 0.85, len(timeline)), 0, 1)
            timeline["lower"] = np.clip(timeline["reference"] - 0.12, 0, 1)
            timeline["upper"] = np.clip(timeline["reference"] + 0.12, 0, 1)
            fig.add_trace(go.Scatter(x=timeline["x"], y=timeline["upper"], mode="lines", line={"width": 0}, showlegend=False))
            fig.add_trace(go.Scatter(x=timeline["x"], y=timeline["lower"], mode="lines", fill="tonexty", name="Tolerance"))
            fig.add_trace(go.Scatter(x=timeline["x"], y=timeline["observed"], mode="lines+markers", name="Current"))
        elif kind == "survival":
            timeline["group"] = np.where(timeline["x"] % 2 == 0, "Control", "Intervention")
            timeline["survival"] = np.clip(np.exp(-timeline["x"] / 42) + np.where(timeline["group"] == "Intervention", 0.08, 0), 0, 1)
            fig = px.line(timeline, x="x", y="survival", color="group", line_shape="hv", title=spec.title)
        elif kind == "control":
            mean = float(timeline["observed"].mean()); std = float(timeline["observed"].std())
            fig.add_trace(go.Scatter(x=timeline["x"], y=timeline["observed"], mode="lines+markers", name="Observed"))
            for label, value in (("Centre", mean), ("UCL", mean + 3 * std), ("LCL", max(0.0, mean - 3 * std))):
                fig.add_hline(y=value, annotation_text=label, line_dash="dash")
        elif kind == "multiline":
            timeline["secondary"] = np.clip(1 - timeline["observed"] + rng.normal(0, 0.05, len(timeline)), 0, 1)
            fig = px.line(timeline, x="x", y=["observed", "secondary"], title=spec.title)
        else:
            fig.add_trace(go.Scatter(x=timeline["x"], y=timeline["observed"], mode="lines+markers", name="Observed"))
        fig.update_layout(title=spec.title, xaxis_title="Stage / time", yaxis_title="Normalised value")
        return fig, timeline
    if kind in {"scatter", "volcano", "spatial", "bubble"}:
        plot = data.copy()
        if kind == "volcano":
            plot["effect"] = pd.to_numeric(plot.get("log2_fold_change", plot.get(xnum, 0)), errors="coerce").fillna(0)
            p = pd.to_numeric(plot.get("p_value", np.linspace(0.001, 0.8, len(plot))), errors="coerce").clip(1e-12, 1)
            plot["evidence"] = -np.log10(p)
            fig = px.scatter(plot, x="effect", y="evidence", color=cat, hover_name="record_id" if "record_id" in plot else None, title=spec.title)
        elif kind == "spatial":
            if "x" not in plot:
                plot["x"] = np.cos(np.linspace(0, 8 * np.pi, len(plot))) * np.linspace(0.2, 2, len(plot))
                plot["y"] = np.sin(np.linspace(0, 8 * np.pi, len(plot))) * np.linspace(0.2, 2, len(plot))
            fig = px.scatter(plot, x="x", y="y", color=cat or xnum, size="confidence" if "confidence" in plot else None, title=spec.title)
            fig.update_yaxes(autorange="reversed", scaleanchor="x")
        else:
            if xnum is None:
                plot["x_value"] = np.arange(len(plot)); xnum = "x_value"
            if ynum is None:
                plot["y_value"] = np.linspace(0, 1, len(plot)); ynum = "y_value"
            fig = px.scatter(plot, x=xnum, y=ynum, color=cat, size="confidence" if kind == "bubble" and "confidence" in plot else None, title=spec.title, render_mode="webgl")
        return fig, plot
    if kind in {"bar", "ranking"}:
        if cat:
            summary = data.groupby(cat, dropna=False)[xnum].mean().reset_index() if xnum else data[cat].value_counts().rename_axis(cat).reset_index(name="records")
            y = xnum if xnum else "records"
            summary = summary.sort_values(y, ascending=False).head(25)
            fig = px.bar(summary, x=cat, y=y, title=spec.title)
        else:
            summary = pd.DataFrame({"item": [f"Item {i+1}" for i in range(20)], "score": np.sort(np.random.default_rng(_seed(page_key + spec.key)).random(20))[::-1]})
            fig = px.bar(summary, x="item", y="score", title=spec.title)
        return fig, summary
    if kind in {"hist", "box"}:
        if xnum is None:
            data["numeric_value"] = np.arange(len(data)); xnum = "numeric_value"
        if kind == "box":
            fig = px.box(data, x=cat, y=xnum, points="outliers", title=spec.title) if cat else px.box(data, y=xnum, points="outliers", title=spec.title)
        else:
            fig = px.histogram(data, x=xnum, color=cat, nbins=30, marginal="box", title=spec.title)
        return fig, data
    if kind in {"network"}:
        return _network_figure(data, spec.title), data.head(100)
    if kind == "waterfall":
        summary = pd.DataFrame({"component": ["Frequency", "Function", "Phenotype", "Evidence", "Uncertainty"], "contribution": [0.18, 0.27, 0.22, 0.25, -0.09]})
        fig = go.Figure(go.Waterfall(x=summary["component"], y=summary["contribution"], measure=["relative"] * len(summary)))
        fig.update_layout(title=spec.title)
        return fig, summary
    if kind in {"track", "lollipop"}:
        track = pd.DataFrame({"position": np.arange(1, 201, 5), "value": np.abs(np.sin(np.arange(1, 201, 5) / 18)), "feature": np.array(["Domain", "Motif", "Variant", "Low complexity"])[np.arange(40) % 4]})
        if kind == "lollipop":
            fig = go.Figure()
            for _, row in track.iterrows():
                fig.add_shape(type="line", x0=row["position"], x1=row["position"], y0=0, y1=row["value"], line={"width": 1})
            fig.add_trace(go.Scatter(x=track["position"], y=track["value"], mode="markers", text=track["feature"], name="Events"))
        else:
            fig = px.scatter(track, x="position", y="feature", size="value", title=spec.title)
        fig.update_layout(title=spec.title)
        return fig, track
    if kind == "manhattan":
        plot = data.copy()
        plot["chrom"] = plot.get("chromosome", np.array([str(i % 22 + 1) for i in range(len(plot))]))
        plot["position"] = pd.to_numeric(plot.get("position", np.arange(len(plot)) * 10000), errors="coerce")
        p = pd.to_numeric(plot.get("p_value", np.linspace(0.8, 1e-5, len(plot))), errors="coerce").clip(1e-12, 1)
        plot["minus_log10_p"] = -np.log10(p)
        plot["genome_order"] = np.arange(len(plot))
        fig = px.scatter(plot, x="genome_order", y="minus_log10_p", color=plot["chrom"].astype(str), title=spec.title)
        return fig, plot
    if kind == "stacked":
        if not cat:
            data["category"] = np.array(["A", "B", "C", "D"])[np.arange(len(data)) % 4]; cat = "category"
        secondary_cat = next((column for column in categorical if column != cat), "group" if "group" in data else cat)
        value = xnum or "score"
        summary = data.groupby([secondary_cat, cat], dropna=False)[value].mean().reset_index()
        fig = px.bar(summary, x=secondary_cat, y=value, color=cat, barmode="stack", title=spec.title)
        return fig, summary
    if kind == "funnel":
        summary = pd.DataFrame({"stage": ["Input", "QC passed", "Analysed", "Reviewed", "Validated"], "records": [100, 84, 70, 46, 18]})
        fig = px.funnel(summary, x="records", y="stage", title=spec.title)
        return fig, summary
    if kind == "risk":
        summary = pd.DataFrame({"risk": ["Data", "Method", "Evidence", "Reproducibility", "External validation"], "likelihood": [2, 2, 3, 1, 4], "impact": [3, 4, 4, 3, 5], "status": ["Review", "Review", "High", "Low", "High"]})
        fig = px.scatter(summary, x="likelihood", y="impact", color="status", size=[12, 14, 18, 10, 22], text="risk", title=spec.title)
        fig.update_xaxes(range=[0.5, 5.5]); fig.update_yaxes(range=[0.5, 5.5])
        return fig, summary
    if kind == "forest":
        summary = pd.DataFrame({"subgroup": ["Overall", "Site A", "Site B", "Low risk", "High risk"], "effect": [0.22, 0.18, 0.31, 0.12, 0.38], "lower": [0.08, -0.02, 0.10, -0.08, 0.14], "upper": [0.36, 0.38, 0.52, 0.32, 0.62]})
        fig = go.Figure(go.Scatter(x=summary["effect"], y=summary["subgroup"], mode="markers", error_x={"type": "data", "symmetric": False, "array": summary["upper"] - summary["effect"], "arrayminus": summary["effect"] - summary["lower"]}))
        fig.add_vline(x=0, line_dash="dash"); fig.update_layout(title=spec.title)
        return fig, summary
    if kind == "structure3d":
        rng = np.random.default_rng(_seed(page_key + spec.key))
        count = 180
        coords = np.cumsum(rng.normal(0, 0.45, (count, 3)), axis=0)
        structure = pd.DataFrame({"x": coords[:, 0], "y": coords[:, 1], "z": coords[:, 2], "residue": np.arange(1, count + 1), "chain": np.where(np.arange(count) < count / 2, "A", "B")})
        fig = px.line_3d(structure, x="x", y="y", z="z", color="chain", hover_name="residue", title=spec.title)
        return fig, structure
    # Safe final fallback.
    if xnum is None:
        data["x_value"] = np.arange(len(data)); xnum = "x_value"
    fig = px.histogram(data, x=xnum, title=spec.title)
    return fig, data


def render_peak_visual_suite(*, page_key: str, title: str, category: str, expanded: bool = False) -> None:
    """Render one responsive module-specific visual at a time.

    The function is intentionally self-contained and catches all visual failures so
    a chart cannot crash the scientific page. When no current-session table can be
    found, a clearly labelled deterministic preview is used.
    """
    if not is_visual_target(category):
        return
    import streamlit as st

    family = family_for(page_key, title, category)
    specs = specs_for(page_key, title, category)
    frame = _session_frame(st, page_key)
    source_label = "Current session data"
    if frame.empty:
        frame = _demo_frame(page_key, family)
        source_label = "Deterministic module preview"

    marker = f"_bio_visual_peak_rendered_{page_key}"
    if st.session_state.get(marker):
        return
    st.session_state[marker] = True

    with st.expander("Peak scientific visuals", expanded=expanded):
        st.caption(
            f"{source_label} · 5 domain-specific visual layers · one chart rendered at a time for responsive performance. "
            "Preview visuals do not represent experimental or clinical validation."
        )
        labels = [spec.title for spec in specs]
        selected_title = st.selectbox("Visual", labels, key=f"visual_peak_choice_{page_key}")
        spec = specs[labels.index(selected_title)]
        try:
            figure, source = _figure(spec, frame, page_key, family)
            from biointel.ui.components import scientific_chart_card

            scientific_chart_card(
                figure,
                title=spec.title,
                interpretation=spec.purpose,
                data=source,
                method=spec.method,
                key=f"visual_peak_{page_key}_{spec.key}",
                module_key=page_key,
                source_record_count=len(frame),
                aggregation_note="Deterministic bounded preview" if source_label.startswith("Deterministic") else "Bounded current-session view",
                configuration={"visual_family": family, "visual_key": spec.key, "source": source_label},
            )
        except Exception as exc:  # visual failures must never crash the module
            error_id = hashlib.sha256(f"{page_key}:{spec.key}:{type(exc).__name__}".encode()).hexdigest()[:10].upper()
            st.error(f"Visual stopped safely · VIS-{error_id}")
            st.caption("Switch to another visual or run the module again. Scientific tables and exports remain available.")
        with st.popover("Visual catalogue"):
            st.dataframe(
                pd.DataFrame([{"Visual": item.title, "Scientific purpose": item.purpose, "Method": item.method} for item in specs]),
                hide_index=True,
                width="stretch",
            )


__all__ = [
    "EXCLUDED_CATEGORIES",
    "FAMILY_TEMPLATES",
    "VisualSpec",
    "family_for",
    "is_visual_target",
    "render_peak_visual_suite",
    "specs_for",
]
