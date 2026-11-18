from __future__ import annotations

import csv
import html
import io
import json
import math
import os
import platform
import sqlite3
import uuid
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from biointel.synthetic.core import (
    SYNTHETIC_WATERMARK,
    SyntheticSafetyError,
    derive_output_origin,
    origin_fields,
    payload_contains_synthetic,
)

from .recommendation_modules import (
    analyze_module,
    build_cost_feasibility,
    build_multi_model_consensus,
    build_what_if_analysis,
)
RESEARCH_USE_DISCLAIMER = (
    "Research-use decision support only. Do not use recommendations for clinical, "
    "diagnostic, prescribing, manufacturing-release or regulatory decisions without "
    "validated data, approved procedures and qualified human review."
)
RECOMMENDATION_STATUSES = (
    "Draft", "Generated", "Under Review", "Accepted", "Rejected", "Deferred", "Planned",
    "In Progress", "Implemented", "Validated", "Failed Validation", "Completed", "Superseded", "Archived",
)
DEFAULT_PRIORITY_WEIGHTS = {
    "statistical_significance": 1.1, "effect_size": 1.0, "biological_relevance": 1.0,
    "evidence_consistency": 1.0, "data_quality": 1.2, "validation_availability": 0.9,
    "novelty": 0.5, "translational_potential": 0.7, "reproducibility": 0.9,
    "experimental_feasibility": 0.8, "cost": 0.4, "time": 0.4, "risk": 0.9,
    "user_defined_research_objective": 0.7,
}
_SPEC_ROWS = [
    ("sequencing_quality", "fastq,sequencing,read_qc", "Sequencing Quality Recommendation Module", "Data Quality Recommendation", "FASTQ quality profile|sample metadata", "MultiQC report|platform|negative control", "QC-gate sequencing reads before downstream analysis.", "Review per-sample read quality, adapters, duplication and retained-read expectations.", "Repeat FASTQ QC after trimming and compare retained read quality.", .86, .82, .74),
    ("alignment_mapping", "alignment,mapping,phylogeny", "Alignment and Mapping Recommendation Module", "Analysis Recommendation", "assay type|organism|reference genome|reads or alignments", "annotation GTF/GFF|benchmark run|resource budget", "Choose an assay-aware aligner and verify reference compatibility.", "Validate reference build, annotation version, read groups and post-alignment QC gates.", "Run a benchmark subset across candidate aligners and compare mapping QC.", .78, .62, .66),
    ("differential_expression", "transcriptomics,de,rna_seq", "Differential Expression Recommendation Module", "Gene Recommendation", "expression matrix|sample metadata|experimental groups", "batch covariates|external cohort|qPCR validation data", "Prioritize differential-expression candidates with design-aware validation.", "Validate the design matrix, batch structure, effect sizes and independent replication route.", "Validate top genes by qPCR or an orthogonal expression assay in an independent cohort.", .72, .58, .54),
    ("biomarker_discovery", "biomarker,markers", "Biomarker Discovery Recommendation Module", "Biomarker Recommendation", "feature matrix|phenotype|sample metadata", "external cohort|confounders|assay feasibility", "Rank biomarker candidates with leakage-aware validation.", "Run nested validation, threshold stability and assay feasibility review.", "Validate the candidate or panel in an independent cohort with a prespecified endpoint.", .62, .46, .42),
    ("variant_prioritization", "variant,vcf,variants", "Variant Prioritization Recommendation Module", "Variant Recommendation", "variant file|reference genome|annotation database version", "phenotype HPO terms|family pedigree|ClinVar snapshot|gnomAD snapshot", "Prioritize variants only with transcript, frequency and evidence provenance.", "Review consequence, frequency, phenotype fit, conflicting classifications and validation needs.", "Confirm priority variants with an orthogonal assay and document research-only status.", .68, .52, .48),
    ("pathway_enrichment", "pathway,enrichment,gsea", "Pathway and Enrichment Recommendation Module", "Pathway Recommendation", "ranked genes|background gene set|organism|database version", "Reactome results|GO results|KEGG results|literature evidence", "Interpret pathway findings with background checks and cross-database confirmation.", "Reduce pathway redundancy, identify core driver genes and validate directionality.", "Validate core pathway genes or proteins using an orthogonal assay.", .76, .66, .62),
    ("multi_omics", "multiomics,multi_omics,omics", "Multi-Omics Integration Recommendation Module", "Analysis Recommendation", "omics layers|sample matching table|normalization status", "batch metadata|protein interaction network|external validation", "Integrate omics layers only after sample identity and normalization checks.", "Audit shared samples, missing layers, cross-omics agreement and layer contribution.", "Validate concordant features across an independent multi-omics cohort where available.", .54, .44, .40),
    ("single_cell", "single_cell,scrna,cell", "Single-Cell Recommendation Module", "Analysis Recommendation", "cell-by-feature matrix|sample metadata|cell QC metrics", "reference atlas|batch labels|doublet scores|marker evidence", "Use dataset-adaptive QC and annotation confidence before biological interpretation.", "Review doublets, ambient RNA, clustering stability and marker-supported cell labels.", "Validate rare or priority populations with FACS, spatial or orthogonal marker assays.", .58, .46, .38),
    ("proteomics", "protein,proteomics", "Proteomics Recommendation Module", "Protein Recommendation", "protein abundance|sample metadata|instrument run QC", "peptide evidence|PTM annotations|targeted validation data", "Prioritize proteins with missingness-aware and peptide-supported evidence.", "Audit missingness, protein inference confidence, differential abundance and validation route.", "Confirm targets using PRM, ELISA, western blot or another orthogonal assay.", .64, .50, .44),
    ("metabolomics", "metabolomics,metabolite", "Metabolomics Recommendation Module", "Analysis Recommendation", "feature table|sample metadata|peak quality|batch information", "internal standards|MSI identity level|authentic standards", "Prioritize metabolite findings with peak quality and identity confidence.", "Review peak quality, batch drift, compound identity level and targeted validation needs.", "Confirm priority metabolites with authentic standards or a targeted method.", .60, .48, .36),
    ("microbiome", "metagenomics,microbiome,taxonomy", "Microbiome Recommendation Module", "Analysis Recommendation", "read quality|taxonomic profile|sample metadata|negative controls", "mock community|functional profile|host metadata|database version", "Interpret microbiome findings with contamination and compositional-data controls.", "Review negative controls, compositional method choice, diversity suitability and database version.", "Validate key taxa or functions using qPCR, targeted sequencing or a spike-in strategy.", .68, .56, .50),
    ("structural_biology", "structural,structure,pdb", "Structural Biology Recommendation Module", "Protein Recommendation", "structure model|residue confidence|domain coverage", "PDB reference|ligand definition|mutation list|docking protocol", "Interpret structures with residue-level confidence and protocol boundaries.", "Review pLDDT/PAE or experimental quality, pocket confidence and mutation-impact evidence.", "Validate structural hypotheses with mutagenesis, binding or biophysical assays.", .56, .42, .34),
    ("drug_target_discovery", "drug,target,drug_target,dti", "Drug and Target Discovery Recommendation Module", "Drug/Compound Recommendation", "target evidence|disease context|druggability evidence", "safety data|tissue expression|existing ligands|competitive landscape", "Prioritize targets with decomposed evidence, safety and tractability gates.", "Review genetic support, expression specificity, essentiality, ligandability and go/no-go criteria.", "Run target-validation experiments with prespecified orthogonal and functional endpoints.", .48, .34, .26),
    ("experimental_design", "experimental_design,study_design,experiment", "Experimental Design Recommendation Module", "Experimental Validation Recommendation", "research question|hypothesis|groups|endpoint", "effect size|dropout|batch plan|budget|timeline", "Lock the study design before generating scientific claims.", "Define endpoint, controls, replication, randomization, power and data-management plan.", "Run a pilot or positive/negative control check before full execution.", .74, .58, .52),
    ("statistical_analysis", "statistics,statistical,biostatistics", "Statistical Analysis Recommendation Module", "Statistical Recommendation", "data type|study design|sample metadata", "covariates|missingness plan|power target|model diagnostics", "Choose statistical methods from data type, design and assumptions.", "Run assumption checks, effect sizes, confidence intervals and sensitivity analyses.", "Re-run the analysis with a robust alternative and document sensitivity.", .82, .72, .78),
    ("literature_discovery", "literature,knowledge,pubmed", "Literature and Knowledge Discovery Recommendation Module", "Literature Review Recommendation", "search query|entities|evidence corpus", "date filters|study-quality rules|citation library|retraction check", "Rank literature evidence with provenance, contradiction and quality checks.", "Build a systematic query, remove duplicates, grade study quality and record gaps.", "Refresh the evidence corpus and repeat contradiction/retraction checks.", .80, .66, .82),
    ("hypothesis_generation", "hypothesis,hypothesis_generation", "Research Hypothesis Recommendation Module", "Hypothesis Generation Recommendation", "observations|biological rationale|testable prediction", "competing hypotheses|novelty search|causal diagram", "Promote hypotheses only when they are testable and falsifiable.", "Define supporting observations, competing hypotheses, experiment and failure interpretation.", "Run the smallest decisive experiment with positive and negative controls.", .70, .60, .62),
    ("laboratory_validation", "lab_validation,validation,qpcr,elisa,western", "Laboratory Validation Recommendation Module", "Experimental Validation Recommendation", "validation objective|candidate target|available samples", "assay SOP|reagents|controls|replicates|acceptance criteria", "Convert candidate findings into an auditable validation plan.", "Select assay, controls, replicates, acceptance criteria and capture plan.", "Execute the selected orthogonal assay and compare to the source analysis.", .66, .50, .40),
    ("generic_bioinformatics", "sequence,pangenome,long_read,generic", "Bioinformatics Research Decision Support Workspace", "Analysis Recommendation", "module analysis result|sample metadata|parameters", "external validation|literature evidence|database versions", "Review bioinformatics findings through evidence, uncertainty and validation gates.", "Inspect data quality, evidence support, alternatives, risks and reproducibility metadata.", "Choose the module-specific orthogonal validation path before release claims.", .72, .60, .58),
]
MODULE_PROFILES = {r[0]: {"aliases": tuple(r[1].split(",")), "label": r[2], "type": r[3], "required": tuple(r[4].split("|")), "optional": tuple(r[5].split("|")), "title": r[6], "next": r[7], "validation": r[8], "feasibility": r[9], "time": r[10], "cost": r[11]} for r in _SPEC_ROWS}
_ALIASES = {alias.lower(): key for key, spec in MODULE_PROFILES.items() for alias in (key, *spec["aliases"])}


def normalize_recommendation_module(module: str) -> str:
    key = str(module or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _ALIASES.get(key, "generic_bioinformatics")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, pd.DataFrame):
        return {"table": value}
    return {"result": value}


def _is_available(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (bytes, bytearray)):
        return bool(value)
    if isinstance(value, pd.DataFrame):
        return not value.empty
    if isinstance(value, Mapping):
        return any(_is_available(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return bool(value)
    return True


def _sanitize(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.head(1000).where(pd.notna(value), None).to_dict(orient="records")
    if isinstance(value, pd.Series):
        return value.where(pd.notna(value), None).to_list()
    if isinstance(value, Mapping):
        return {str(k): _sanitize(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_sanitize(v) for v in value]
    if isinstance(value, set):
        return sorted(_sanitize(v) for v in value)
    if isinstance(value, (Path, datetime)):
        return str(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def recommendation_to_dict(record: Mapping[str, Any]) -> dict[str, Any]:
    return _sanitize(dict(record))


def _stable_hash(payload: Any) -> str:
    return sha256(json.dumps(_sanitize(payload), sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _dataframes(payload: Any) -> list[pd.DataFrame]:
    if isinstance(payload, pd.DataFrame):
        return [payload]
    out: list[pd.DataFrame] = []
    if isinstance(payload, Mapping):
        for item in payload.values():
            out.extend(_dataframes(item))
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for item in list(payload)[:20]:
            out.extend(_dataframes(item))
    return out


def _numbers(payload: Any) -> dict[str, float]:
    values: dict[str, float] = {}
    def visit(prefix: str, value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                visit(f"{prefix}.{key}" if prefix else str(key), item)
            return
        if isinstance(value, pd.DataFrame):
            values[f"{prefix}.row_count"] = float(len(value))
            if len(value.index) and len(value.columns):
                values[f"{prefix}.missing_fraction"] = float(value.isna().mean().mean())
                if any(token in prefix.lower() for token in ("metadata", "sample", "design", "analysis_table", "table")):
                    values[f"{prefix}.duplicate_row_fraction"] = float(value.duplicated().mean())
            for column in value.columns:
                if pd.api.types.is_numeric_dtype(value[column]) and not pd.api.types.is_bool_dtype(value[column]):
                    series = pd.to_numeric(value[column], errors="coerce").dropna()
                    if not series.empty:
                        base = f"{prefix}.{column}"
                        values[f"{base}.min"] = float(series.min())
                        values[f"{base}.abs_p90"] = float(series.abs().quantile(0.90))
            return
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not (isinstance(value, float) and math.isnan(value)):
                values[prefix] = float(value)
    visit("", payload)
    return values


def _first_number(numbers: Mapping[str, float], needles: Sequence[str]) -> float | None:
    lowered = {k.lower(): v for k, v in numbers.items()}
    for needle in needles:
        for key, value in lowered.items():
            if needle.lower() in key:
                return value
    return None


def _warnings(payload: Any) -> tuple[str, ...]:
    out: list[str] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if str(key).lower() in {"warning", "warnings", "blockers", "errors", "limitations"}:
                if isinstance(value, str) and value.strip():
                    out.append(value.strip())
                elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                    out.extend(str(v) for v in value if str(v).strip())
            out.extend(_warnings(value))
    return tuple(dict.fromkeys(out))


def assess_data_quality(module: str, analysis_results: Mapping[str, Any]) -> tuple[list[dict[str, str]], tuple[str, ...], tuple[str, ...]]:
    profile = MODULE_PROFILES[normalize_recommendation_module(module)]
    available = tuple(str(k).replace("_", " ").title() for k, v in analysis_results.items() if _is_available(v))
    missing = tuple(item for item in profile["required"] if not any(item.lower().split()[0] in seen.lower() for seen in available))
    checks = [
        {"check": "Input requirement checker", "status": "Pass" if available else "Fail", "value": ", ".join(available) if available else "No analysis payload detected", "detail": "Available inputs are derived from the supplied result object.", "recommendation": "Attach the module analysis output before accepting a scientific recommendation." if not available else "Document missing optional inputs before release review."},
        {"check": "Required input completeness", "status": "Warning" if missing and available else "Fail" if missing else "Pass", "value": ", ".join(missing) if missing else "Required inputs represented", "detail": "Expected module inputs are checked before recommendation scoring.", "recommendation": "Add missing inputs or keep the recommendation in review." if missing else "Proceed with evidence grading."},
    ]
    nums = _numbers(analysis_results)
    count = _first_number(nums, ("reads_profiled", "variants_loaded", "samples", "row_count", "records", "cells", "features"))
    if count is None:
        checks.append({"check": "Sample or record count", "status": "Not checked", "value": "Not available", "detail": "No count-like metric was found.", "recommendation": "Include sample/read/variant/cell counts in the result payload."})
    else:
        status = "Fail" if count <= 0 else "Warning" if count < 3 else "Pass"
        checks.append({"check": "Sample or record count", "status": status, "value": str(int(count)), "detail": "Count is calculated from supplied metrics or tables.", "recommendation": "Do not assign high confidence until replication or additional samples are available." if status != "Pass" else "Preserve this count in the manifest."})
    for label, needle, warn, fail, formatter in [
        ("Missing values", "missing_fraction", .05, .35, lambda v: f"{v:.1%}"),
        ("Duplicate samples or rows", "duplicate_row_fraction", 0, .25, lambda v: f"{v:.1%}"),
        ("Read or call quality", "mean_quality", 30, 20, lambda v: f"{v:.2f}"),
        ("PASS or valid-call fraction", "pass_fraction", .8, .5, lambda v: f"{v:.1%}"),
        ("Adapter contamination", "adapter_read_fraction", .05, .15, lambda v: f"{v:.1%}"),
        ("Duplicate read fraction", "duplicate_read_fraction", .2, .6, lambda v: f"{v:.1%}"),
    ]:
        value = max((v for k, v in nums.items() if needle in k.lower()), default=None)
        if value is None:
            continue
        if label == "Read or call quality":
            status = "Pass" if value >= warn else "Warning" if value >= fail else "Fail"
        elif label in {"Adapter contamination", "Duplicate read fraction", "Missing values", "Duplicate samples or rows"}:
            status = "Fail" if value > fail else "Warning" if value > warn else "Pass"
        else:
            status = "Pass" if value >= warn else "Warning" if value >= fail else "Fail"
        checks.append({"check": label, "status": status, "value": formatter(value), "detail": "Calculated from supplied analysis result metrics.", "recommendation": "Resolve or document this quality signal before accepting the recommendation." if status != "Pass" else "Record this metric in exports."})
    for warning in _warnings(analysis_results)[:8]:
        checks.append({"check": "Upstream warning", "status": "Warning", "value": warning, "detail": "Propagated from source analysis.", "recommendation": "Resolve or document before acceptance."})
    return checks, available, missing

def _quality_score(checks: Sequence[Mapping[str, Any]]) -> float:
    scores = {"Pass": 1.0, "Warning": 0.65, "Fail": 0.15, "Not checked": 0.45}
    return sum(scores.get(str(c.get("status")), 0.45) for c in checks) / max(len(checks), 1)


def _has(checks: Sequence[Mapping[str, Any]], status: str) -> bool:
    return any(c.get("status") == status for c in checks)


def build_evidence_panel(module: str, analysis_results: Mapping[str, Any], checks: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    nums = _numbers(analysis_results)
    evidence: list[dict[str, Any]] = []
    contradiction: list[dict[str, Any]] = []
    limitations: list[str] = []
    explicit = analysis_results.get("evidence")
    rows = explicit.to_dict(orient="records") if isinstance(explicit, pd.DataFrame) else list(explicit) if isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes, bytearray)) else []
    for row in rows[:100]:
        if isinstance(row, Mapping):
            item = {"evidence_type": str(row.get("evidence_type", row.get("type", "Evidence"))), "source": str(row.get("source", "Supplied evidence")), "finding": str(row.get("finding", row.get("detail", "Evidence supplied by analysis"))), "strength": str(row.get("strength", row.get("evidence_strength", "Moderate"))), "status": str(row.get("status", "Available")), "provenance": str(row.get("provenance", "User-entered or imported evidence")), "contradictory": bool(row.get("contradictory", False)), "limitation": str(row.get("limitation", ""))}
            (contradiction if item["contradictory"] else evidence).append(item)
    count = _first_number(nums, ("reads_profiled", "variants_loaded", "samples", "row_count", "records"))
    if count is not None:
        evidence.append({"evidence_type": "Current analysis", "source": "Current dataset", "finding": f"{int(count):,} records or samples were available for screening review.", "strength": "Moderate" if count >= 3 else "Limited", "status": "Available", "provenance": "Computed result", "contradictory": False, "limitation": "Small count limits confidence." if count < 3 else ""})
    mean_quality = _first_number(nums, ("mean_quality",))
    if mean_quality is not None:
        item = {"evidence_type": "Data quality", "source": "Current dataset", "finding": f"Mean quality metric is {mean_quality:.2f}.", "strength": "Strong" if mean_quality >= 30 else "Limited", "status": "Available", "provenance": "Computed result", "contradictory": mean_quality < 20, "limitation": "Quality below Q20 blocks high-confidence downstream recommendations." if mean_quality < 20 else ""}
        (contradiction if item["contradictory"] else evidence).append(item)
    pass_fraction = _first_number(nums, ("pass_fraction",))
    if pass_fraction is not None:
        item = {"evidence_type": "Filter support", "source": "Current dataset", "finding": f"PASS or valid-call fraction is {pass_fraction:.1%}.", "strength": "Strong" if pass_fraction >= .8 else "Limited", "status": "Available", "provenance": "Computed result", "contradictory": pass_fraction < .5, "limitation": "Low PASS fraction can indicate caller or reference problems." if pass_fraction < .8 else ""}
        (contradiction if item["contradictory"] else evidence).append(item)
    for frame in _dataframes(analysis_results)[:4]:
        lower = {str(c).lower(): c for c in frame.columns}
        fdr_col = next((lower[n] for n in ("fdr_bh", "fdr", "q_value", "padj") if n in lower), None)
        eff_col = next((lower[n] for n in ("log2_fold_change", "log2fc", "effect_size", "auc", "odds_ratio") if n in lower), None)
        if fdr_col is not None:
            fdr = pd.to_numeric(frame[fdr_col], errors="coerce")
            sig = int((fdr <= .05).sum())
            evidence.append({"evidence_type": "Statistical support", "source": "Current analysis", "finding": f"{sig:,} rows pass FDR <= 0.05.", "strength": "Strong" if sig else "Limited", "status": "Available", "provenance": "Computed result", "contradictory": False, "limitation": "Interpret with effect sizes and QC gates."})
        if eff_col is not None:
            eff = pd.to_numeric(frame[eff_col], errors="coerce").abs().dropna()
            if not eff.empty:
                evidence.append({"evidence_type": "Effect size", "source": "Current analysis", "finding": f"Median absolute effect is {eff.median():.3f}.", "strength": "Moderate" if eff.median() >= .5 else "Limited", "status": "Available", "provenance": "Computed result", "contradictory": False, "limitation": "Effect thresholds must match assay and study design."})
    for check in checks:
        if check["status"] == "Fail":
            contradiction.append({"evidence_type": "Data quality blocker", "source": "QC gate", "finding": check["detail"], "strength": "Strong", "status": "Available", "provenance": "Computed result", "contradictory": True, "limitation": check["recommendation"]})
        elif check["status"] == "Warning":
            limitations.append(f"{check['check']}: {check['detail']}")
    if not evidence:
        limitations.append("No computed evidence rows were available; recommendation remains a scaffold.")
    limitations.extend(i["limitation"] for i in [*evidence, *contradiction] if i.get("limitation"))
    return evidence, contradiction, list(dict.fromkeys(limitations))


def _pvalue_score(payload: Mapping[str, Any]) -> tuple[float | None, str]:
    best = None
    for frame in _dataframes(payload):
        lower = {str(c).lower(): c for c in frame.columns}
        col = next((lower[n] for n in ("fdr_bh", "fdr", "q_value", "padj", "p_value") if n in lower), None)
        if col is not None:
            vals = pd.to_numeric(frame[col], errors="coerce").dropna()
            if not vals.empty:
                score = 1 - min(max(float(vals.min()), 0), 1)
                best = score if best is None else max(best, score)
    return best, "Calculated from 1 - smallest available p-value/FDR." if best is not None else "No p-value or FDR field was found."


def _effect_score(payload: Mapping[str, Any]) -> tuple[float | None, str]:
    best = None
    for frame in _dataframes(payload):
        lower = {str(c).lower(): c for c in frame.columns}
        col = next((lower[n] for n in ("log2_fold_change", "log2fc", "effect_size", "cohens_d", "auc", "odds_ratio") if n in lower), None)
        if col is not None:
            vals = pd.to_numeric(frame[col], errors="coerce").abs().dropna()
            if not vals.empty:
                score = min(float(vals.quantile(.9)) / 2, 1)
                best = score if best is None else max(best, score)
    return best, "Calculated from 90th percentile absolute effect scaled to 0-1." if best is not None else "No effect-size field was found."


def _evidence_score(evidence: Sequence[Mapping[str, Any]], contradiction: Sequence[Mapping[str, Any]]) -> float:
    if not evidence:
        return .15
    weights = {"Strong": 1.0, "Moderate": .75, "Limited": .45, "Weak": .3}
    support = sum(weights.get(str(i.get("strength")), .55) for i in evidence) / len(evidence)
    return max(0.0, min(1.0, support - min(.5, .15 * len(contradiction))))


def calculate_confidence(payload: Mapping[str, Any], checks: Sequence[Mapping[str, Any]], evidence: Sequence[Mapping[str, Any]], contradiction: Sequence[Mapping[str, Any]]) -> tuple[float | None, str, list[dict[str, Any]]]:
    stat, stat_method = _pvalue_score(payload)
    effect, effect_method = _effect_score(payload)
    source_text = " ".join(f"{i.get('source')} {i.get('evidence_type')} {i.get('provenance')}".lower() for i in evidence)
    literature = .80 if any(x in source_text for x in ("pubmed", "europe pmc", "literature")) else None
    external = .75 if any(x in source_text for x in ("external", "geo", "tcga", "gtex", "clinvar")) else None
    validation = .85 if any("validation" in str(i.get("evidence_type", "")).lower() for i in evidence) else None
    components = [
        {"name": "Data Quality Confidence", "score": round(_quality_score(checks), 3), "weight": 1.4, "method": "Average QC gates: Pass=1.0, Warning=0.65, Fail=0.15, Not checked=0.45.", "status": "Calculated"},
        {"name": "Statistical Confidence", "score": round(stat, 3) if stat is not None else None, "weight": 1.0, "method": stat_method, "status": "Not calculated" if stat is None else "Calculated"},
        {"name": "Model or Effect Confidence", "score": round(effect, 3) if effect is not None else None, "weight": .8, "method": effect_method, "status": "Not calculated" if effect is None else "Calculated"},
        {"name": "Biological Evidence Confidence", "score": round(_evidence_score(evidence, contradiction), 3), "weight": 1.0, "method": "Derived from evidence strength and contradiction penalty.", "status": "Calculated"},
        {"name": "Literature Confidence", "score": literature, "weight": .7, "method": "Calculated only from explicit literature evidence rows; references are never invented.", "status": "Not available" if literature is None else "Calculated"},
        {"name": "External Dataset Confidence", "score": external, "weight": .8, "method": "Calculated only when external dataset evidence is explicitly supplied.", "status": "Not available" if external is None else "Calculated"},
        {"name": "Replication or Validation Confidence", "score": validation, "weight": .9, "method": "Calculated only from explicit validation or replication evidence.", "status": "Not available" if validation is None else "Calculated"},
    ]
    usable = [c for c in components if c["score"] is not None]
    if not usable:
        return None, "Confidence not calculated: required validation or analysis data unavailable.", components
    confidence = sum(float(c["score"]) * c["weight"] for c in usable) / sum(c["weight"] for c in usable)
    if _has(checks, "Fail"):
        confidence = min(confidence, .49)
    elif _has(checks, "Warning"):
        confidence = min(confidence, .84)
    return round(confidence * 100, 1), "Overall confidence is calculated from available components and capped by QC gates.", components


def calculate_priority(module: str, payload: Mapping[str, Any], checks: Sequence[Mapping[str, Any]], evidence: Sequence[Mapping[str, Any]], contradiction: Sequence[Mapping[str, Any]], parameters: Mapping[str, Any], weights: Mapping[str, float] | None = None) -> tuple[str, float, str, list[dict[str, Any]]]:
    profile = MODULE_PROFILES[normalize_recommendation_module(module)]
    merged = {**DEFAULT_PRIORITY_WEIGHTS, **dict(weights or {})}
    stat, stat_method = _pvalue_score(payload)
    effect, effect_method = _effect_score(payload)
    objective = .80 if str(parameters.get("research_objective", "")).strip() else .45
    risk = 1 - min(.85, .20 * len(contradiction) + (.30 if _has(checks, "Fail") else 0))
    data = {
        "statistical_significance": (stat if stat is not None else .45, stat_method),
        "effect_size": (effect if effect is not None else .45, effect_method),
        "biological_relevance": (_evidence_score(evidence, contradiction), "Calculated from evidence strength."),
        "evidence_consistency": (max(.1, 1 - .2 * len(contradiction)), "Contradictory evidence lowers consistency."),
        "data_quality": (_quality_score(checks), "Derived from QC gates."),
        "validation_availability": (.85 if any("validation" in str(i.get("evidence_type", "")).lower() for i in evidence) else .35, "Explicit validation evidence raises this score."),
        "novelty": (float(parameters.get("novelty_score", .45)), "User/configured novelty score; neutral if not configured."),
        "translational_potential": (float(parameters.get("translational_potential", profile["feasibility"])), "Module default or user-configured value."),
        "reproducibility": (.78 if payload else .25, "Analysis payload and manifest availability support reproducibility."),
        "experimental_feasibility": (float(parameters.get("feasibility_score", profile["feasibility"])), "Module default or user-configured value."),
        "cost": (float(parameters.get("cost_score", profile["cost"])), "Higher score means lower expected cost or easier resource access."),
        "time": (float(parameters.get("time_score", profile["time"])), "Higher score means shorter expected turnaround."),
        "risk": (risk, "False-positive, QC and contradiction risks lower this score."),
        "user_defined_research_objective": (objective, "Research objective supplied by user." if objective == .80 else "No user objective supplied; neutral screening weight used."),
    }
    components = [{"name": k, "score": v[0], "weight": merged[k], "method": v[1], "status": "Calculated"} for k, v in data.items()]
    score = sum(c["score"] * c["weight"] for c in components) / sum(c["weight"] for c in components)
    if _has(checks, "Fail"):
        score = min(score, .54)
    elif _has(checks, "Warning"):
        score = min(score, .78)
    priority = "Critical" if score >= .90 else "High" if score >= .75 else "Medium" if score >= .55 else "Low" if score >= .35 else "Optional"
    formula = "weighted_average(component_score * user_weight) with QC caps; weights=" + json.dumps(merged, sort_keys=True)
    return priority, round(score * 100, 1), formula, components


def grade_evidence(checks: Sequence[Mapping[str, Any]], evidence: Sequence[Mapping[str, Any]], contradiction: Sequence[Mapping[str, Any]], confidence: float | None, missing_inputs: Sequence[str]) -> tuple[str, str]:
    if _has(checks, "Fail") or (missing_inputs and not evidence):
        return "Grade U - Insufficient Evidence", "Inputs, QC or evidence are insufficient."
    text = " ".join(f"{i.get('source')} {i.get('evidence_type')} {i.get('provenance')}".lower() for i in evidence)
    lit = any(x in text for x in ("pubmed", "europe pmc", "literature"))
    ext = any(x in text for x in ("external", "geo", "tcga", "gtex", "clinvar"))
    val = any("validation" in str(i.get("evidence_type", "")).lower() for i in evidence)
    if ext and val and lit and confidence is not None and confidence >= 80 and not contradiction:
        return "Grade A - Strong Evidence", "Independent, literature and validation evidence are aligned."
    if len(evidence) >= 2 and (lit or ext or val) and len(contradiction) <= 1:
        return "Grade B - Moderate Evidence", "Multiple evidence streams support the recommendation, but validation is incomplete."
    if evidence:
        return "Grade C - Preliminary Evidence", "Current analysis supports a screening-level recommendation only."
    return "Grade D - Hypothesis-Generating", "Recommendation is based on computational or incomplete evidence only."


def _urgency(priority: str, grade: str, checks: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    if _has(checks, "Fail"):
        return "Immediate review", "Prevents unreliable downstream interpretation."
    if priority in {"Critical", "High"} and grade.startswith(("Grade A", "Grade B")):
        return "High", "May materially change project prioritization after validation."
    if priority == "Medium":
        return "Medium", "Useful for planning and hypothesis prioritization."
    return "Routine", "Supports documentation, review and reproducibility."

def _alternatives(profile: Mapping[str, Any], missing: Sequence[str], grade: str) -> list[dict[str, Any]]:
    required = tuple(missing or profile["required"][:1])
    return [
        {"option": "Primary recommendation", "expected_value": profile["next"], "scientific_strength": grade, "cost": "Configured by lab", "time": "Standard", "risk": "Moderate", "required_inputs": tuple(profile["required"]), "validation_requirements": profile["validation"], "limitations": "Depends on supplied analysis quality and validation data."},
        {"option": "Conservative alternative", "expected_value": "Repeat QC, design and evidence review before promotion.", "scientific_strength": "Higher integrity, lower speed", "cost": "Lower", "time": "Longer", "risk": "Lower", "required_inputs": required, "validation_requirements": "Resolve QC warnings before acting.", "limitations": "May delay promising exploratory signals."},
        {"option": "Exploratory alternative", "expected_value": "Use findings only for hypothesis generation and literature triage.", "scientific_strength": "Preliminary", "cost": "Lower", "time": "Faster", "risk": "Higher", "required_inputs": ("Current analysis result",), "validation_requirements": "Clearly label as unvalidated.", "limitations": "Cannot support release, clinical or experimental commitment decisions."},
        {"option": "Lower-cost alternative", "expected_value": "Prioritize in-silico sensitivity analysis and a smaller validation panel.", "scientific_strength": "Moderate", "cost": "Lower", "time": "Standard", "risk": "Moderate", "required_inputs": ("Existing dataset", "selected candidates"), "validation_requirements": "Validate only highest-priority candidates first.", "limitations": "Can miss lower-ranked but relevant signals."},
        {"option": "Faster alternative", "expected_value": "Run threshold what-if review and defer external validation.", "scientific_strength": "Limited", "cost": "Lower", "time": "Faster", "risk": "Higher", "required_inputs": ("Current run",), "validation_requirements": "Use only for planning until validation is complete.", "limitations": "Recommendation stability may be overstated."},
        {"option": "Higher-confidence alternative", "expected_value": "Acquire or import an independent cohort before acceptance.", "scientific_strength": "Higher", "cost": "Higher", "time": "Longer", "risk": "Lower", "required_inputs": ("External validation set",), "validation_requirements": "Require concordant direction and effect-size support.", "limitations": "May be unavailable for rare assays, organisms or cohorts."},
        {"option": "No-action option", "expected_value": "Archive with rationale and revisit after new data or database refresh.", "scientific_strength": "Lowest", "cost": "Lowest", "time": "Fastest", "risk": "Lowest operational risk", "required_inputs": ("Decision reason",), "validation_requirements": "Add reanalysis reminder if context may change.", "limitations": "Opportunity cost if the signal is real."},
    ]


def _risks(module: str, checks: Sequence[Mapping[str, Any]], evidence: Sequence[Mapping[str, Any]], contradiction: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    risks = [
        {"category": "False-positive risk", "level": "High" if _has(checks, "Fail") else "Moderate", "rationale": "Exploratory results can overstate biological signal when QC or replication is weak.", "mitigation": "Require independent validation, effect-size review and negative controls."},
        {"category": "False-negative risk", "level": "Moderate", "rationale": "Filtering, low power or assay noise can hide relevant signals.", "mitigation": "Run sensitivity analysis and document thresholds."},
        {"category": "Batch-effect risk", "level": "High" if any("batch" in c.get("detail", "").lower() and c.get("status") != "Pass" for c in checks) else "Moderate", "rationale": "Unmodeled batch effects can mimic biology.", "mitigation": "Use batch metadata, balanced design and batch-aware models."},
        {"category": "Small-sample risk", "level": "High" if any(c.get("check") == "Sample or record count" and c.get("status") != "Pass" for c in checks) else "Moderate", "rationale": "Small cohorts limit generalizability.", "mitigation": "Increase replication or keep as hypothesis-generating."},
        {"category": "Database-bias risk", "level": "Moderate", "rationale": "Reference databases and annotations can be incomplete, outdated or population-biased.", "mitigation": "Record database versions and compare relevant external resources."},
        {"category": "Reproducibility risk", "level": "High" if not evidence else "Moderate", "rationale": "Missing parameters, versions or input hashes weaken reproducibility.", "mitigation": "Export the reproducibility manifest with every recommendation."},
    ]
    if contradiction:
        risks.append({"category": "Contradictory-evidence risk", "level": "High", "rationale": f"{len(contradiction)} contradictory evidence row(s) were detected.", "mitigation": "Keep under review until conflicts are resolved or explained."})
    if normalize_recommendation_module(module) in {"variant_prioritization", "drug_target_discovery", "biomarker_discovery"}:
        risks.append({"category": "Research-use safety boundary", "level": "High", "rationale": "This module can be mistaken for clinical or translational guidance.", "mitigation": "Keep research-only labels visible and require qualified review."})
    return risks


def _action_plan(profile: Mapping[str, Any], priority: str, checks: Sequence[Mapping[str, Any]], missing: Sequence[str]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    if missing:
        steps.append({"action_title": "Resolve missing recommendation inputs", "owner": "Research analyst", "priority": "High", "status": "Planned", "due_date": "Not scheduled", "dependencies": tuple(), "required_data": tuple(missing), "expected_result": "Input checker passes or missing data are documented as limitations.", "estimated_duration": "1-2 hours", "estimated_cost": "Configured by lab", "completion_notes": ""})
    blockers = [c for c in checks if c.get("status") in {"Fail", "Warning"}]
    if blockers:
        steps.append({"action_title": "Review QC warnings and blockers", "owner": "Bioinformatics lead", "priority": "High" if any(c.get("status") == "Fail" for c in blockers) else "Medium", "status": "Planned", "due_date": "Not scheduled", "dependencies": tuple(c.get("check", "") for c in blockers[:5]), "required_data": ("QC report", "sample metadata"), "expected_result": "QC gates are resolved, accepted with reason or downgraded to hypothesis-only use.", "estimated_duration": "2-4 hours", "estimated_cost": "Configured by lab", "completion_notes": ""})
    steps.extend([
        {"action_title": profile["next"], "owner": "Module owner", "priority": priority, "status": "Planned", "due_date": "Not scheduled", "dependencies": ("QC review",), "required_data": tuple(profile["required"]), "expected_result": "Primary recommendation has traceable evidence and rationale.", "estimated_duration": "Half day", "estimated_cost": "Configured by lab", "completion_notes": ""},
        {"action_title": "Create validation plan and assign owner", "owner": "Lab lead", "priority": "High" if priority in {"Critical", "High"} else "Medium", "status": "Planned", "due_date": "Not scheduled", "dependencies": ("Recommendation review",), "required_data": ("candidate list", "samples", "controls"), "expected_result": "Validation assay, controls and acceptance criteria are approved.", "estimated_duration": "1 day", "estimated_cost": "Configured by lab", "completion_notes": ""},
        {"action_title": "Export reproducibility package", "owner": "Research analyst", "priority": "Medium", "status": "Planned", "due_date": "Not scheduled", "dependencies": ("Final parameters",), "required_data": ("input hashes", "software versions", "database versions", "warnings"), "expected_result": "JSON, CSV, HTML, PDF and manifest outputs are archived with the project.", "estimated_duration": "30 minutes", "estimated_cost": "Low", "completion_notes": ""},
    ])
    return steps


def _validation_plan(profile: Mapping[str, Any], grade: str) -> list[dict[str, Any]]:
    cohort_status = "Not planned" if grade.startswith(("Grade C", "Grade D", "Grade U")) else "Planned"
    return [
        {"validation_type": "Technical validation", "status": "Planned", "required_data": ("input files", "parameters", "software versions"), "acceptance_criteria": "Same inputs and parameters reproduce the recommendation hash.", "failure_criteria": "Output hash or rank materially changes without documented cause.", "notes": "Covers reproducibility and parameter integrity."},
        {"validation_type": "Statistical validation", "status": "Planned", "required_data": ("analysis result table", "metadata"), "acceptance_criteria": "Effect sizes, uncertainty intervals and multiple-testing control remain stable.", "failure_criteria": "Signal disappears under reasonable sensitivity checks.", "notes": "Use robust alternatives where assumptions are weak."},
        {"validation_type": "Independent cohort validation", "status": cohort_status, "required_data": ("external validation set",), "acceptance_criteria": "Direction, rank or performance is concordant in independent data.", "failure_criteria": "Independent data contradict the primary finding.", "notes": "Required before high-confidence scientific claims."},
        {"validation_type": "Orthogonal assay validation", "status": "Planned", "required_data": ("samples", "controls", "candidate targets"), "acceptance_criteria": profile["validation"], "failure_criteria": "Controls or replicate criteria fail.", "notes": "Choose assay based on analyte, sample type and SOP."},
    ]


def _comparison(previous: Mapping[str, Any] | None, current: Mapping[str, Any]) -> list[dict[str, Any]]:
    if previous is None:
        return [{"comparison_type": "Current versus previous run", "status": "Not available", "detail": "No previous recommendation was supplied."}]
    prior = recommendation_to_dict(previous)
    return [{"comparison_type": f, "previous": prior.get(f), "current": current.get(f), "changed": prior.get(f) != current.get(f)} for f in ("priority", "priority_score", "confidence_score", "evidence_grade", "status")]


def build_reproducibility_manifest(module: str, payload: Mapping[str, Any], parameters: Mapping[str, Any], input_payloads: Mapping[str, bytes | str] | None = None, software_version: str = "unknown", model_version: str = "Not used", database_versions: Mapping[str, str] | None = None, reference_genome: str = "", annotation_version: str = "", random_seed: int | None = None, user: str = "") -> dict[str, Any]:
    hashes = {}
    for name, item in dict(input_payloads or {}).items():
        raw = item if isinstance(item, bytes) else str(item).encode("utf-8")
        hashes[str(name)] = sha256(raw).hexdigest()
    if not hashes and payload:
        hashes["analysis_results"] = _stable_hash(payload)
    return {"module": normalize_recommendation_module(module), "input_file_hashes": hashes, "parameters": dict(parameters), "filters": dict(parameters.get("filters", {})) if isinstance(parameters.get("filters"), Mapping) else {}, "software_version": software_version, "package_versions": {"python": platform.python_version(), "pandas": pd.__version__}, "model_version": model_version, "database_versions": dict(database_versions or {}), "reference_genome": reference_genome or "Not specified", "annotation_version": annotation_version or "Not specified", "random_seed": random_seed, "execution_timestamp": _now(), "user": user or os.environ.get("USERNAME") or os.environ.get("USER") or "unknown", "hardware_environment": {"platform": platform.platform(), "processor": platform.processor(), "python_implementation": platform.python_implementation()}, "generated_outputs": ("recommendation_json", "recommendation_csv", "html_report", "pdf_report", "docx_report", "xlsx_workbook", "evidence_package", "parameter_configuration", "audit_report", "reproducibility_manifest"), "warnings": list(_warnings(payload)), "errors": [], "analysis_payload_sha256": _stable_hash(payload)}


def build_recommendation_workspace(module: str, analysis_results: Any, *, project_id: str = "default-project", run_id: str | None = None, parameters: Mapping[str, Any] | None = None, weights: Mapping[str, float] | None = None, input_payloads: Mapping[str, bytes | str] | None = None, previous: Mapping[str, Any] | None = None, software_version: str = "unknown", model_version: str = "Not used", database_versions: Mapping[str, str] | None = None, reference_genome: str = "", annotation_version: str = "", random_seed: int | None = None, user: str = "") -> dict[str, Any]:
    canonical = normalize_recommendation_module(module)
    profile = MODULE_PROFILES[canonical]
    payload = _as_mapping(analysis_results)
    params = dict(parameters or {})
    is_synthetic = payload_contains_synthetic(payload) or payload_contains_synthetic(params)
    output_origin, origin_label = derive_output_origin(payload, params)
    module_analysis = analyze_module(canonical, payload, params)
    multi_model_consensus = build_multi_model_consensus(payload)
    what_if_analysis = build_what_if_analysis(module_analysis, params)
    cost_feasibility = build_cost_feasibility(canonical, params)
    checks, available, missing = assess_data_quality(canonical, payload)
    evidence, contradiction, limitations = build_evidence_panel(canonical, payload, checks)
    if is_synthetic:
        for row in (*evidence, *contradiction):
            row.update({"evidence_origin": "calculated_synthetic", "data_origin": "synthetic", "is_synthetic": True})
    confidence, confidence_message, confidence_components = calculate_confidence(payload, checks, evidence, contradiction)
    priority, priority_score, priority_formula, priority_components = calculate_priority(canonical, payload, checks, evidence, contradiction, params, weights)
    grade, strength = grade_evidence(checks, evidence, contradiction, confidence, missing)
    urgency, impact = _urgency(priority, grade, checks)
    validation_status = "Synthetic demo only - not scientifically validated" if is_synthetic else ("Not planned" if grade.startswith(("Grade C", "Grade D", "Grade U")) else "Planned")
    rationale = ([SYNTHETIC_WATERMARK] if is_synthetic else []) + [profile["title"], f"Priority is {priority} from a transparent weighted score of {priority_score:.1f}/100.", confidence_message, f"Evidence grade is {grade}."]
    if missing:
        rationale.append("Missing required inputs: " + ", ".join(missing) + ".")
    if contradiction:
        rationale.append(f"{len(contradiction)} contradictory or blocking evidence item(s) require review.")
    now = _now()
    current = {"priority": priority, "priority_score": priority_score, "confidence_score": confidence, "evidence_grade": grade, "status": "Generated"}
    explain = sorted(priority_components, key=lambda c: c["weight"] * float(c.get("score") or 0), reverse=True)[:8] + [c for c in confidence_components if c.get("score") is not None] + [{"name": "Data-Quality Contribution", "score": round(_quality_score(checks), 3), "weight": 1.0, "method": "Poor data quality caps both confidence and priority.", "status": "Calculated"}]
    result = {"recommendation_id": f"rec-{uuid.uuid4().hex[:16]}", "project_id": project_id, "run_id": run_id or f"run-{uuid.uuid4().hex[:12]}", "module": canonical, "module_label": profile["label"], "title": profile["title"], "scientific_summary": " ".join(rationale), "recommendation_type": profile["type"], "priority": priority, "priority_score": priority_score, "priority_formula": priority_formula, "priority_components": priority_components, "confidence_score": confidence, "confidence_message": confidence_message, "confidence_components": confidence_components, "evidence_grade": grade, "evidence_strength": strength, "urgency": urgency, "research_impact": impact, "recommended_next_action": profile["next"], "validation_status": validation_status, "research_use_disclaimer": RESEARCH_USE_DISCLAIMER, "available_inputs": available, "missing_inputs": missing, "optional_inputs": tuple(profile["optional"]), "quality_checks": checks, "evidence": evidence, "contradictory_evidence": contradiction, "evidence_limitations": limitations, "explainability": explain, "human_readable_rationale": " ".join(rationale), "alternatives": _alternatives(profile, missing, grade), "risks": _risks(canonical, checks, evidence, contradiction), "action_plan": _action_plan(profile, priority, checks, missing), "validation_plan": _validation_plan(profile, grade), "comparison": _comparison(previous, current), "reproducibility": build_reproducibility_manifest(canonical, payload, params, input_payloads, software_version, model_version, database_versions, reference_genome, annotation_version, random_seed, user), "status": "Generated", "created_at_utc": now, "updated_at_utc": now, "user_notes": "", "reviewer_comments": "", "decision_reason": "", "module_analysis": module_analysis, "multi_model_consensus": multi_model_consensus, "what_if_analysis": what_if_analysis, "cost_feasibility": cost_feasibility}
    result.update({"data_origin": output_origin, "is_synthetic": is_synthetic, "origin_label": origin_label})
    if is_synthetic:
        synthetic_origin = origin_fields()
        synthetic_origin.update({
            "synthetic_generator_id": payload.get("synthetic_generator_id", synthetic_origin["synthetic_generator_id"]),
            "synthetic_generator_version": payload.get("synthetic_generator_version", synthetic_origin["synthetic_generator_version"]),
            "synthetic_seed": payload.get("synthetic_seed", random_seed),
            "synthetic_scenario": payload.get("synthetic_scenario") or params.get("synthetic_scenario"),
            "synthetic_created_at": payload.get("synthetic_created_at", synthetic_origin["synthetic_created_at"]),
        })
        result.update(synthetic_origin)
        result.update({"scientific_use": "Not permitted", "clinical_use": "Not permitted", "publication_use": "Not permitted", "publication_ready": False, "export_watermark": SYNTHETIC_WATERMARK})
        result["research_use_disclaimer"] = SYNTHETIC_WATERMARK
        result["reproducibility"].update(synthetic_origin)
        result["reproducibility"]["export_watermark"] = SYNTHETIC_WATERMARK
    return result


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class RecommendationStore:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS recommendations (
                recommendation_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, run_id TEXT NOT NULL,
                module TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL, priority TEXT NOT NULL,
                priority_score REAL NOT NULL, confidence_score REAL, evidence_grade TEXT NOT NULL,
                created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_recommendations_project_module ON recommendations(project_id, module, updated_at_utc);
            CREATE TABLE IF NOT EXISTS recommendation_events (
                event_id TEXT PRIMARY KEY, recommendation_id TEXT NOT NULL, event_type TEXT NOT NULL,
                actor TEXT NOT NULL, note TEXT NOT NULL, created_at_utc TEXT NOT NULL,
                FOREIGN KEY(recommendation_id) REFERENCES recommendations(recommendation_id)
            );
        """)
        connection.commit()
        return connection

    def save(self, record: Mapping[str, Any]) -> str:
        payload = recommendation_to_dict(record)
        payload["updated_at_utc"] = _now()
        with self._connect() as connection:
            connection.execute("""
                INSERT INTO recommendations(recommendation_id, project_id, run_id, module, title, status, priority, priority_score, confidence_score, evidence_grade, created_at_utc, updated_at_utc, payload_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(recommendation_id) DO UPDATE SET project_id=excluded.project_id, run_id=excluded.run_id, module=excluded.module, title=excluded.title, status=excluded.status, priority=excluded.priority, priority_score=excluded.priority_score, confidence_score=excluded.confidence_score, evidence_grade=excluded.evidence_grade, updated_at_utc=excluded.updated_at_utc, payload_json=excluded.payload_json
            """, (payload["recommendation_id"], payload["project_id"], payload["run_id"], payload["module"], payload["title"], payload["status"], payload["priority"], float(payload["priority_score"]), payload.get("confidence_score"), payload["evidence_grade"], payload["created_at_utc"], payload["updated_at_utc"], json.dumps(payload, sort_keys=True, default=str)))
            connection.execute("INSERT INTO recommendation_events(event_id, recommendation_id, event_type, actor, note, created_at_utc) VALUES(?,?,?,?,?,?)", (f"evt-{uuid.uuid4().hex[:16]}", payload["recommendation_id"], "saved", str(payload.get("reproducibility", {}).get("user", "system")), "Recommendation saved or refreshed.", _now()))
            connection.commit()
        return str(payload["recommendation_id"])

    def get(self, recommendation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload_json FROM recommendations WHERE recommendation_id=?", (recommendation_id,)).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list(self, *, project_id: str | None = None, module: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if project_id:
            clauses.append("project_id=?")
            values.append(project_id)
        if module:
            clauses.append("module=?")
            values.append(normalize_recommendation_module(module))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(f"SELECT payload_json FROM recommendations{where} ORDER BY updated_at_utc DESC LIMIT ?", (*values, int(limit))).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def update_status(self, recommendation_id: str, status: str, *, actor: str = "system", note: str = "", decision_reason: str = "", reviewer_comments: str = "") -> dict[str, Any]:
        if status not in RECOMMENDATION_STATUSES:
            raise ValueError(f"Unsupported recommendation status: {status}")
        payload = self.get(recommendation_id)
        if payload is None:
            raise KeyError(recommendation_id)
        if payload_contains_synthetic(payload) and status == "Validated":
            raise SyntheticSafetyError("Synthetic recommendations cannot be marked scientifically validated.")
        payload["status"] = status
        payload["updated_at_utc"] = _now()
        if decision_reason:
            payload["decision_reason"] = decision_reason
        if reviewer_comments:
            payload["reviewer_comments"] = reviewer_comments
        with self._connect() as connection:
            connection.execute("UPDATE recommendations SET status=?, updated_at_utc=?, payload_json=? WHERE recommendation_id=?", (status, payload["updated_at_utc"], json.dumps(payload, sort_keys=True, default=str), recommendation_id))
            connection.execute("INSERT INTO recommendation_events(event_id, recommendation_id, event_type, actor, note, created_at_utc) VALUES(?,?,?,?,?,?)", (f"evt-{uuid.uuid4().hex[:16]}", recommendation_id, "status_change", actor, note or f"Status changed to {status}.", _now()))
            connection.commit()
        return payload

    def history_frame(self, *, project_id: str | None = None, module: str | None = None) -> pd.DataFrame:
        return pd.DataFrame([{"recommendation_id": x["recommendation_id"], "project_id": x["project_id"], "module": x["module"], "status": x["status"], "priority": x["priority"], "priority_score": x["priority_score"], "confidence_score": x.get("confidence_score"), "evidence_grade": x["evidence_grade"], "updated_at_utc": x["updated_at_utc"], "title": x["title"]} for x in self.list(project_id=project_id, module=module, limit=200)])


def _export_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = recommendation_to_dict(record)
    if payload_contains_synthetic(payload):
        payload.update({"data_origin": "synthetic", "is_synthetic": True, "export_watermark": SYNTHETIC_WATERMARK, "publication_ready": False})
    return payload


def export_recommendation_json(record: Mapping[str, Any]) -> bytes:
    return json.dumps(_export_payload(record), indent=2, sort_keys=True, default=str).encode("utf-8")


def export_recommendation_csv(records: Sequence[Mapping[str, Any]]) -> bytes:
    payloads = [_export_payload(record) for record in records]
    synthetic = any(payload_contains_synthetic(payload) for payload in payloads)
    fields = ["recommendation_id", "project_id", "run_id", "module", "title", "recommendation_type", "priority", "priority_score", "confidence_score", "evidence_grade", "status", "recommended_next_action", "updated_at_utc", "data_origin", "is_synthetic", "synthetic_notice"]
    out = io.StringIO()
    if synthetic:
        out.write(f"# {SYNTHETIC_WATERMARK}\n")
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for payload in payloads:
        row = {field: payload.get(field, "") for field in fields}
        row["synthetic_notice"] = SYNTHETIC_WATERMARK if payload_contains_synthetic(payload) else ""
        writer.writerow(row)
    return out.getvalue().encode("utf-8")


def export_evidence_csv(record: Mapping[str, Any]) -> bytes:
    payload = _export_payload(record)
    rows = list(payload.get("evidence", [])) + list(payload.get("contradictory_evidence", []))
    fields = ["evidence_type", "source", "finding", "strength", "status", "provenance", "contradictory", "limitation", "evidence_origin", "data_origin", "is_synthetic"]
    out = io.StringIO()
    if payload_contains_synthetic(payload):
        out.write(f"# {SYNTHETIC_WATERMARK}\n")
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fields})
    return out.getvalue().encode("utf-8")


def export_reproducibility_manifest(record: Mapping[str, Any]) -> bytes:
    payload = _export_payload(record)
    manifest = dict(payload.get("reproducibility", {}))
    if payload_contains_synthetic(payload):
        manifest.update({"data_origin": "synthetic", "is_synthetic": True, "export_watermark": SYNTHETIC_WATERMARK, "publication_ready": False})
    return json.dumps(manifest, indent=2, sort_keys=True, default=str).encode("utf-8")

def _html_table(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    if not rows:
        return "<p>No records.</p>"
    header = "".join(f"<th>{html.escape(c.replace('_', ' ').title())}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(row.get(c, '')))}</td>" for c in columns) + "</tr>" for row in rows)
    return f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"


def export_recommendation_html(record: Mapping[str, Any]) -> bytes:
    payload = _export_payload(record)
    evidence_rows = list(payload.get("evidence", [])) + list(payload.get("contradictory_evidence", []))
    synthetic = payload_contains_synthetic(payload)
    banner = f'<div class="synthetic"><strong>{html.escape(SYNTHETIC_WATERMARK)}</strong></div>' if synthetic else ""
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(str(payload.get('title', 'Recommendation Report')))}</title><style>body{{font-family:Arial,sans-serif;margin:32px;color:#1f2937}}h1,h2{{color:#0f172a}}.synthetic{{border:3px solid #b42318;background:#fff1f0;color:#8a1c13;padding:14px;margin-bottom:18px;font-size:18px}}.meta{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}}.box{{border:1px solid #cbd5e1;padding:10px;border-radius:6px}}table{{border-collapse:collapse;width:100%;margin:12px 0}}th,td{{border:1px solid #d7dee8;padding:7px;vertical-align:top}}th{{background:#eef2f7;text-align:left}}footer{{margin-top:28px;font-size:12px;color:#475569}}</style></head><body>{banner}<h1>{html.escape(str(payload.get('title', '')))}</h1><p>{html.escape(str(payload.get('scientific_summary', '')))}</p><div class="meta"><div class="box"><strong>Priority</strong><br>{html.escape(str(payload.get('priority', '')))} ({html.escape(str(payload.get('priority_score', '')))} / 100)</div><div class="box"><strong>Confidence</strong><br>{html.escape(str(payload.get('confidence_score', 'Not calculated')))}</div><div class="box"><strong>Evidence</strong><br>{html.escape(str(payload.get('evidence_grade', '')))}</div><div class="box"><strong>Status</strong><br>{html.escape(str(payload.get('status', '')))}</div></div><h2>Next Action</h2><p>{html.escape(str(payload.get('recommended_next_action', '')))}</p><h2>Quality Checks</h2>{_html_table(payload.get('quality_checks', []), ('check', 'status', 'value', 'detail', 'recommendation'))}<h2>Evidence</h2>{_html_table(evidence_rows, ('evidence_type', 'source', 'finding', 'strength', 'status', 'evidence_origin', 'contradictory'))}<h2>Validation Plan</h2>{_html_table(payload.get('validation_plan', []), ('validation_type', 'status', 'acceptance_criteria', 'failure_criteria', 'notes'))}<h2>Action Plan</h2>{_html_table(payload.get('action_plan', []), ('action_title', 'owner', 'priority', 'status', 'expected_result'))}<footer>{html.escape(str(payload.get('research_use_disclaimer', RESEARCH_USE_DISCLAIMER)))}</footer></body></html>"""
    return document.encode("utf-8")

def export_recommendation_pdf(record: Mapping[str, Any]) -> bytes:
    from .recommendation_exports import export_recommendation_pdf_full

    return export_recommendation_pdf_full(record)


def export_recommendation_bundle(record: Mapping[str, Any]) -> dict[str, bytes]:
    from .recommendation_exports import (
        export_audit_report,
        export_parameter_configuration,
        export_recommendation_docx,
        export_recommendation_xlsx,
    )

    p = recommendation_to_dict(record)
    stem = str(p.get("recommendation_id", "recommendation"))
    return {
        f"{stem}.json": export_recommendation_json(p),
        f"{stem}.csv": export_recommendation_csv([p]),
        f"{stem}_evidence.csv": export_evidence_csv(p),
        f"{stem}.html": export_recommendation_html(p),
        f"{stem}.pdf": export_recommendation_pdf(p),
        f"{stem}.docx": export_recommendation_docx(p),
        f"{stem}.xlsx": export_recommendation_xlsx(p),
        f"{stem}_parameters.json": export_parameter_configuration(p),
        f"{stem}_audit.json": export_audit_report(p),
        f"{stem}_reproducibility_manifest.json": export_reproducibility_manifest(p),
    }


