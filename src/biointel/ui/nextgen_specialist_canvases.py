from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CanvasMetric:
    label: str
    column: str | None = None
    aggregate: str = "mean"
    fallback: str = "—"
    suffix: str = ""


@dataclass(frozen=True)
class CanvasProfile:
    title: str
    subtitle: str
    stages: tuple[str, ...]
    metrics: tuple[CanvasMetric, ...]


_PROFILES: dict[str, CanvasProfile] = {
    "digital_pathology_foundation": CanvasProfile(
        "Whole-slide evidence canvas", "Slide QC, tissue coverage, tumour burden and embedding drift",
        ("Slide intake", "Tissue QC", "Embedding review", "Pathologist handoff"),
        (CanvasMetric("Slides", "slide_id", "nunique"), CanvasMetric("Mean tissue", "tissue_fraction", "mean", suffix="%"), CanvasMetric("Tumour burden", "tumour_burden", "mean", suffix="%"), CanvasMetric("QC flags", "qc_flag", "sum")),
    ),
    "long_read_epigenome": CanvasProfile(
        "Methylation and imprinting canvas", "Coverage-aware regional, haplotype and allelic-imbalance review",
        ("bedMethyl intake", "Coverage gate", "DMR screen", "Imprinting review"),
        (CanvasMetric("Regions", "region", "nunique"), CanvasMetric("Median coverage", "median_coverage", "median"), CanvasMetric("FDR candidates", "q_value", "le_005"), CanvasMetric("Max imbalance", "allelic_imbalance", "max", suffix="%")),
    ),
    "single_cell_long_read_isoforms": CanvasProfile(
        "Isoform-resolution canvas", "Full-length support, splice junctions and cluster-specific transcript usage",
        ("Barcode/UMI QC", "Isoform support", "Cluster comparison", "Transcript review"),
        (CanvasMetric("Genes", "gene", "nunique"), CanvasMetric("Isoforms", "transcript", "nunique"), CanvasMetric("Full-length rate", "full_length_rate", "mean", suffix="%"), CanvasMetric("Median junctions", "median_junctions", "median")),
    ),
    "biomedical_foundation_model_hub": CanvasProfile(
        "Foundation-model operations canvas", "Licence, local assets, hardware fit and benchmark readiness",
        ("Registry", "Asset integrity", "Hardware fit", "Inference gate"),
        (CanvasMetric("Models", "model_id", "nunique"), CanvasMetric("Local ready", "local_ready", "sum"), CanvasMetric("Mean benchmark", "benchmark_score", "mean", suffix="%"), CanvasMetric("Blocked", "release_blocked", "sum")),
    ),
    "amr_surveillance": CanvasProfile(
        "AMR surveillance canvas", "Species, lineage, genotype–phenotype concordance and emerging signals",
        ("Isolate QC", "Typing", "AMR evidence", "Surveillance alert"),
        (CanvasMetric("Isolates", "isolates", "sum"), CanvasMetric("Signals", "review_required", "sum"), CanvasMetric("Resistance", "resistance_rate", "mean", suffix="%"), CanvasMetric("Concordance", "concordance", "mean", suffix="%")),
    ),
    "spatial_medicine_tme": CanvasProfile(
        "Tumour microenvironment canvas", "Spatial compartments, immune exclusion and regional review",
        ("Spatial intake", "Compartment map", "Neighbourhood review", "Biomarker handoff"),
        (CanvasMetric("Patients", "patient", "nunique"), CanvasMetric("Regions", "region", "nunique"), CanvasMetric("Immune fraction", "immune", "mean", suffix="%"), CanvasMetric("Exclusion score", "immune_exclusion_score", "mean", suffix="%")),
    ),
    "gene_therapy_vector": CanvasProfile(
        "Vector engineering canvas", "Cargo capacity, tropism, immunogenicity and integration-risk gates",
        ("Construct map", "Packaging gate", "Safety review", "Manufacturing handoff"),
        (CanvasMetric("Constructs", "construct", "nunique"), CanvasMetric("Packaging pass", "packaging_pass", "sum"), CanvasMetric("Mean safety", "safety_score", "mean", suffix="%"), CanvasMetric("Blocked", "release_blocked", "sum")),
    ),
    "cell_therapy_cart": CanvasProfile(
        "CAR-T engineering canvas", "Antigen, scFv, signalling, exhaustion and manufacturability balance",
        ("Construct parse", "Antigen review", "Safety/developability", "Cell-product handoff"),
        (CanvasMetric("Constructs", "construct", "nunique"), CanvasMetric("Antigens", "antigen", "nunique"), CanvasMetric("Engineering score", "engineering_score", "mean", suffix="%"), CanvasMetric("Safety reviews", "safety_review", "sum")),
    ),
    "federated_biomedical_ai": CanvasProfile(
        "Federated-learning canvas", "Round performance, site drift, privacy budget and governance",
        ("Site enrolment", "Federated rounds", "Privacy audit", "Global release gate"),
        (CanvasMetric("Rounds", "round", "nunique"), CanvasMetric("Sites", "sites", "max"), CanvasMetric("Global metric", "global_metric", "max", suffix="%"), CanvasMetric("Mean drift", "mean_drift", "mean", suffix="%")),
    ),
    "clinical_biomarker_survival": CanvasProfile(
        "Clinical stratification canvas", "Biomarker groups, response, time-to-event and site heterogeneity",
        ("Cohort QC", "Cut-off lock", "Survival model", "External validation"),
        (CanvasMetric("Patients", "patients", "sum"), CanvasMetric("Response rate", "response_rate", "mean", suffix="%"), CanvasMetric("Event rate", "event_rate", "mean", suffix="%"), CanvasMetric("Median time", "median_time", "median")),
    ),
    "protein_ligand_codesign": CanvasProfile(
        "Protein–ligand co-design canvas", "Protein, ligand, interface and selectivity objectives",
        ("Candidate pair", "Interface review", "Pareto selection", "Experimental handoff"),
        (CanvasMetric("Candidates", "candidate", "nunique"), CanvasMetric("Joint score", "joint_score", "mean", suffix="%"), CanvasMetric("Pareto-like", "pareto_like", "sum"), CanvasMetric("Selectivity review", "selectivity_review", "sum")),
    ),
    "pangenome_population_medicine": CanvasProfile(
        "Population pangenome canvas", "Graph paths, population frequency shifts and reference-bias review",
        ("Graph intake", "Population paths", "Bias audit", "Equity review"),
        (CanvasMetric("Populations", "population", "nunique"), CanvasMetric("Variants", "variant", "nunique"), CanvasMetric("Mean bias", "reference_bias", "mean", suffix="%"), CanvasMetric("Bias reviews", "bias_review", "sum")),
    ),
    "pharmacovigilance_intelligence": CanvasProfile(
        "Safety-signal canvas", "Disproportionality, seriousness and signal-review lifecycle",
        ("Case intake", "Deduplication", "Signal detection", "Safety review"),
        (CanvasMetric("Drug–event pairs", None, "rows"), CanvasMetric("Signals", "signal_flag", "sum"), CanvasMetric("Serious rate", "serious_rate", "mean", suffix="%"), CanvasMetric("Max ROR", "reporting_odds_ratio", "max")),
    ),
    "synthetic_cohort_trial": CanvasProfile(
        "Trial simulation canvas", "Cohort balance, site heterogeneity and operating-characteristic review",
        ("Scenario design", "Cohort generation", "Simulation", "Decision review"),
        (CanvasMetric("Arms", "arm", "nunique"), CanvasMetric("Patients", "patients", "sum"), CanvasMetric("Outcome rate", "outcome_rate", "mean", suffix="%"), CanvasMetric("Balance", "balance_score", "mean", suffix="%")),
    ),
    "autonomous_lab_planner": CanvasProfile(
        "Experiment-planning canvas", "Hypotheses, factors, controls, replication and resource readiness",
        ("Hypothesis", "Design of experiments", "Resource plan", "Human approval"),
        (CanvasMetric("Experiments", "experiment_id", "nunique"), CanvasMetric("Mean replicates", "replicates", "mean"), CanvasMetric("Total cost", "total_cost", "sum", suffix=" currency"), CanvasMetric("Review required", "review_required", "sum")),
    ),
}


def _number(frame: pd.DataFrame, metric: CanvasMetric, secondary: pd.DataFrame | None = None) -> str:
    if metric.aggregate == "rows":
        return f"{len(frame):,}"
    source = frame
    if metric.column is not None and (metric.column not in source.columns or source.empty) and isinstance(secondary, pd.DataFrame) and metric.column in secondary.columns and not secondary.empty:
        source = secondary
    if metric.column is None or metric.column not in source.columns or source.empty:
        return metric.fallback
    series = source[metric.column]
    try:
        if metric.aggregate == "nunique":
            value: Any = int(series.nunique(dropna=True))
        elif metric.aggregate == "sum":
            value = float(pd.to_numeric(series, errors="coerce").fillna(0).sum())
        elif metric.aggregate == "median":
            value = float(pd.to_numeric(series, errors="coerce").median())
        elif metric.aggregate == "max":
            value = float(pd.to_numeric(series, errors="coerce").max())
        elif metric.aggregate == "le_005":
            value = int((pd.to_numeric(series, errors="coerce") <= 0.05).sum())
        else:
            value = float(pd.to_numeric(series, errors="coerce").mean())
    except Exception:
        return metric.fallback
    if isinstance(value, float) and not np.isfinite(value):
        return metric.fallback
    if metric.suffix == "%":
        return f"{100.0 * float(value):.1f}%"
    if metric.suffix == " currency":
        return f"{float(value):,.0f}"
    if isinstance(value, float):
        return f"{value:,.3g}"
    return f"{value:,}"


def render_nextgen_specialist_canvas(
    module_key: str,
    *,
    result: pd.DataFrame | None,
    secondary: pd.DataFrame | None = None,
) -> None:
    import streamlit as st

    profile = _PROFILES.get(module_key)
    frame = result if isinstance(result, pd.DataFrame) else pd.DataFrame()
    if profile is None or frame.empty:
        return
    metric_html = "".join(
        f'<div class="ng129-metric"><span>{html.escape(metric.label)}</span><strong>{html.escape(_number(frame, metric, secondary))}</strong></div>'
        for metric in profile.metrics
    )
    stage_html = "".join(
        f'<div class="ng129-stage"><b>{idx}</b><span>{html.escape(stage)}</span></div>'
        for idx, stage in enumerate(profile.stages, start=1)
    )
    st.markdown(
        f"""
        <style>
        .ng129-canvas{{border:1px solid rgba(145,165,255,.28);border-radius:20px;padding:18px 20px;margin:4px 0 18px;background:linear-gradient(135deg,rgba(23,29,54,.88),rgba(10,16,34,.76));box-shadow:0 18px 55px rgba(0,0,0,.18);overflow:hidden}}
        .ng129-title{{font-size:1.05rem;font-weight:750;letter-spacing:.01em;margin-bottom:3px}}
        .ng129-subtitle{{opacity:.72;font-size:.86rem;margin-bottom:14px}}
        .ng129-metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px}}
        .ng129-metric{{padding:11px 12px;border-radius:14px;background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.075);min-width:0}}
        .ng129-metric span{{display:block;opacity:.66;font-size:.72rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
        .ng129-metric strong{{display:block;font-size:1.12rem;margin-top:4px}}
        .ng129-stages{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}}
        .ng129-stage{{display:flex;align-items:center;gap:8px;padding:9px 10px;border-radius:12px;background:rgba(119,135,255,.08)}}
        .ng129-stage b{{display:grid;place-items:center;width:24px;height:24px;border-radius:50%;background:rgba(119,135,255,.23);font-size:.72rem}}
        .ng129-stage span{{font-size:.76rem;line-height:1.15}}
        @media(max-width:900px){{.ng129-metrics,.ng129-stages{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
        </style>
        <section class="ng129-canvas" aria-label="{html.escape(profile.title)}">
          <div class="ng129-title">{html.escape(profile.title)}</div>
          <div class="ng129-subtitle">{html.escape(profile.subtitle)}</div>
          <div class="ng129-metrics">{metric_html}</div>
          <div class="ng129-stages">{stage_html}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )
