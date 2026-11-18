from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy import stats


MODULE_ONLY_KEYS: frozenset[str] = frozenset({
    "digital_pathology_foundation",
    "long_read_epigenome",
    "single_cell_long_read_isoforms",
    "biomedical_foundation_model_hub",
    "amr_surveillance",
    "spatial_medicine_tme",
    "gene_therapy_vector",
    "cell_therapy_cart",
    "federated_biomedical_ai",
    "clinical_biomarker_survival",
    "protein_ligand_codesign",
    "pangenome_population_medicine",
    "pharmacovigilance_intelligence",
    "synthetic_cohort_trial",
    "autonomous_lab_planner",
})

MAX_MODULE_ROWS = 250_000
MAX_VISUAL_ROWS = 10_000


@dataclass(frozen=True)
class ModuleUpgradeProfile:
    title: str
    feature_groups: tuple[str, ...]
    visual_groups: tuple[str, ...]
    quality_gates: tuple[str, ...]
    external_engine: str


PROFILES: dict[str, ModuleUpgradeProfile] = {
    "digital_pathology_foundation": ModuleUpgradeProfile(
        "Pathology cohort and scanner-quality upgrade",
        ("Slide-level tissue/tumour composition", "Scanner/site drift", "Tile uncertainty", "Pathologist review queue"),
        ("Slide QC matrix", "Tumour-versus-tissue scatter", "Scanner drift map", "Tile uncertainty distribution"),
        ("Minimum tissue coverage", "Embedding/OOD review", "Scanner/site balance", "Slide-level sample size"),
        "OpenSlide + validated pathology foundation model/MIL pipeline",
    ),
    "long_read_epigenome": ModuleUpgradeProfile(
        "Coverage-weighted methylation and imprinting upgrade",
        ("Coverage-weighted methylation", "Allelic imbalance", "Condition effect", "FDR-controlled DMR review"),
        ("DMR volcano", "Haplotype ribbon table", "Coverage-effect map", "Region-condition heatmap"),
        ("Minimum coverage", "Replicate count", "Effect-size threshold", "FDR threshold"),
        "Dorado/Remora/Modkit plus validated DMR and phasing workflow",
    ),
    "single_cell_long_read_isoforms": ModuleUpgradeProfile(
        "Isoform usage and transcript-support upgrade",
        ("Isoform entropy", "Cluster-specific usage", "Full-length support", "Switch-candidate ranking"),
        ("Isoform usage heatmap", "Transcript support scatter", "Cluster entropy", "Switch-candidate table"),
        ("Cell support", "UMI depth", "Full-length fraction", "Junction support"),
        "Long-read alignment/assembly plus SQANTI-like transcript classification",
    ),
    "biomedical_foundation_model_hub": ModuleUpgradeProfile(
        "Model operations and hardware-fit upgrade",
        ("Hardware fit", "Licence risk", "Efficiency frontier", "Operational readiness"),
        ("Accuracy-resource frontier", "Task-modality coverage", "Licence matrix", "Local readiness chart"),
        ("Asset checksum", "Licence compatibility", "RAM/VRAM fit", "Benchmark provenance"),
        "Local model registry, secure downloader, quantisation and benchmark runner",
    ),
    "amr_surveillance": ModuleUpgradeProfile(
        "AMR concordance and surveillance upgrade",
        ("Phenotype-genotype concordance", "Lineage/location trends", "Emerging signal detection", "Conflict review"),
        ("Gene-isolate matrix", "Concordance heatmap", "Temporal resistance trend", "Location-lineage summary"),
        ("Species confirmation", "Breakpoint version", "Database release", "Minimum isolate count"),
        "AMRFinderPlus/ResFinder/CARD with MLST/cgMLST and breakpoint standards",
    ),
    "spatial_medicine_tme": ModuleUpgradeProfile(
        "Tumour microenvironment neighbourhood upgrade",
        ("Compartment composition", "Immune exclusion", "Region contrast", "Spatial neighbourhood enrichment"),
        ("Spatial point map", "Region-cell heatmap", "Immune exclusion profile", "Patient-region comparison"),
        ("Coordinate completeness", "Cell-type coverage", "Patient replication", "Region size"),
        "Native spatial platform loader, segmentation, deconvolution and neighbourhood modelling",
    ),
    "gene_therapy_vector": ModuleUpgradeProfile(
        "Vector construct safety and manufacturability upgrade",
        ("Packaging margin", "Sequence composition", "Safety liabilities", "Construct comparison"),
        ("Capacity gauge", "Construct risk matrix", "Sequence composition", "Vector comparison"),
        ("Vector-specific cargo limit", "ITR/LTR integrity", "GC/extreme motif review", "Evidence completeness"),
        "Validated vector-design, immunogenicity and integration-risk workflows",
    ),
    "cell_therapy_cart": ModuleUpgradeProfile(
        "CAR construct efficacy-safety upgrade",
        ("Antigen risk", "Exhaustion/persistence", "Domain comparison", "Manufacturability"),
        ("Efficacy-safety frontier", "Antigen risk matrix", "Domain comparison", "Construct ranking"),
        ("Healthy-tissue expression", "scFv evidence", "Safety switch", "Manufacturing evidence"),
        "IgBLAST/ANARCI plus antigen atlas and experimental CAR validation",
    ),
    "federated_biomedical_ai": ModuleUpgradeProfile(
        "Federated robustness and privacy upgrade",
        ("Site heterogeneity", "Round stability", "Privacy-utility", "Outlier site review"),
        ("Round trajectory", "Site drift heatmap", "Privacy-utility frontier", "Global-local gap"),
        ("Minimum sites", "Client participation", "Privacy budget", "Subgroup fairness"),
        "Federated runtime with secure aggregation, DP accountant and attack testing",
    ),
    "clinical_biomarker_survival": ModuleUpgradeProfile(
        "Survival and biomarker validation upgrade",
        ("Kaplan-Meier", "Log-rank screening", "Hazard-rate ratio", "Cut-off stability"),
        ("KM curve", "Risk table", "Site heterogeneity", "Biomarker response profile"),
        ("Event count", "Proportional-hazards review", "External cohort", "Missing-data strategy"),
        "Validated Cox/competing-risk modelling with nested and external validation",
    ),
    "protein_ligand_codesign": ModuleUpgradeProfile(
        "Multi-objective co-design upgrade",
        ("Pareto dominance", "Selectivity penalty", "Variant-ligand consistency", "Candidate diversity"),
        ("Pareto frontier", "Variant-ligand heatmap", "Score-component radar", "Selectivity-risk plot"),
        ("Structure quality", "Pose validity", "Selectivity panel", "Experimental binding evidence"),
        "Docking/rescoring, structure validation, MD/free-energy and wet-lab feedback",
    ),
    "pangenome_population_medicine": ModuleUpgradeProfile(
        "Population specificity and reference-bias upgrade",
        ("Population differentiation", "Reference-bias audit", "Path diversity", "Clinical-weight review"),
        ("Population-variant heatmap", "Differentiation profile", "Bias distribution", "Path coverage"),
        ("Population sample size", "Graph release", "Coordinate system", "Ancestry context"),
        "VG/ODGI/minigraph graph services with validated population frequency resources",
    ),
    "pharmacovigilance_intelligence": ModuleUpgradeProfile(
        "Signal detection and case-series upgrade",
        ("ROR/PRR/IC", "Empirical-Bayes shrinkage", "Time-to-onset", "Seriousness review"),
        ("Signal volcano", "Drug-event matrix", "Time-to-onset profile", "Outcome severity chart"),
        ("Duplicate cases", "Drug/event coding", "Exposure denominator", "Temporal stability"),
        "MedDRA/WHODrug normalisation with validated signal-management workflow",
    ),
    "synthetic_cohort_trial": ModuleUpgradeProfile(
        "Trial operating-characteristics upgrade",
        ("Monte Carlo risk difference", "Covariate balance", "Event-time simulation", "Site heterogeneity"),
        ("Simulation distribution", "Love plot", "KM comparison", "Site forest-style view"),
        ("Scenario seed", "Treatment estimand", "Dropout model", "Type-I error/power"),
        "Prespecified simulation protocol and validated statistical trial engine",
    ),
    "autonomous_lab_planner": ModuleUpgradeProfile(
        "Design-of-experiments and resource upgrade",
        ("Factor-level coverage", "Control coverage", "Replication adequacy", "Resource schedule"),
        ("Design matrix", "Cost waterfall", "Schedule timeline", "Risk register"),
        ("Power/sample size", "Randomisation", "Blinding", "Human approval"),
        "Validated DoE/statistical design engine with inventory, scheduling and ELN/LIMS integration",
    ),
}


def _num(series: pd.Series, fill: float | None = None) -> pd.Series:
    out = pd.to_numeric(series, errors="coerce")
    return out.fillna(fill) if fill is not None else out


def _safe_div(a: Any, b: Any, default: float = 0.0) -> float:
    try:
        denominator = float(b)
        return float(a) / denominator if denominator not in {0.0, -0.0} and math.isfinite(denominator) else default
    except Exception:
        return default


def _bh(p_values: pd.Series) -> pd.Series:
    values = _num(p_values).to_numpy(float)
    output = np.full(len(values), np.nan)
    valid = np.isfinite(values)
    if not valid.any():
        return pd.Series(output, index=p_values.index)
    p = values[valid]
    order = np.argsort(p)
    ranked = p[order]
    adjusted = np.minimum.accumulate((ranked * len(ranked) / np.arange(1, len(ranked) + 1))[::-1])[::-1]
    restored = np.empty_like(adjusted)
    restored[order] = np.clip(adjusted, 0, 1)
    output[np.where(valid)[0]] = restored
    return pd.Series(output, index=p_values.index)


def _entropy(values: pd.Series) -> float:
    x = _num(values, 0).clip(lower=0).to_numpy(float)
    total = x.sum()
    if total <= 0:
        return 0.0
    p = x / total
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def _logrank(frame: pd.DataFrame, group_col: str = "biomarker_group") -> dict[str, float]:
    required = {"time", "event", group_col}
    if not required.issubset(frame.columns):
        return {"chi_square": float("nan"), "p_value": float("nan"), "hazard_rate_ratio": float("nan")}
    work = frame[["time", "event", group_col]].copy()
    work["time"] = _num(work["time"])
    work["event"] = _num(work["event"], 0).clip(0, 1)
    work = work.dropna(subset=["time", group_col])
    groups = list(work[group_col].astype(str).dropna().unique())
    if len(groups) != 2:
        return {"chi_square": float("nan"), "p_value": float("nan"), "hazard_rate_ratio": float("nan")}
    g0, g1 = groups
    observed = {g0: 0.0, g1: 0.0}
    expected = {g0: 0.0, g1: 0.0}
    variance = 0.0
    for t in sorted(work.loc[work["event"] > 0, "time"].unique()):
        at0 = int(((work[group_col].astype(str) == g0) & (work["time"] >= t)).sum())
        at1 = int(((work[group_col].astype(str) == g1) & (work["time"] >= t)).sum())
        d0 = int(((work[group_col].astype(str) == g0) & (work["time"] == t) & (work["event"] > 0)).sum())
        d1 = int(((work[group_col].astype(str) == g1) & (work["time"] == t) & (work["event"] > 0)).sum())
        n, d = at0 + at1, d0 + d1
        if n <= 1 or d <= 0:
            continue
        e0 = d * at0 / n
        observed[g0] += d0
        observed[g1] += d1
        expected[g0] += e0
        expected[g1] += d - e0
        variance += at0 * at1 * d * (n - d) / (n * n * (n - 1))
    chi = ((observed[g0] - expected[g0]) ** 2 / variance) if variance > 0 else float("nan")
    p = float(stats.chi2.sf(chi, 1)) if math.isfinite(chi) else float("nan")
    rate0 = _safe_div(observed[g0], work.loc[work[group_col].astype(str) == g0, "time"].sum())
    rate1 = _safe_div(observed[g1], work.loc[work[group_col].astype(str) == g1, "time"].sum())
    return {"chi_square": chi, "p_value": p, "hazard_rate_ratio": _safe_div(rate1, rate0, float("nan"))}


def _stable_rng(module_key: str, frame: pd.DataFrame) -> np.random.Generator:
    digest = hashlib.sha256(f"{module_key}|{len(frame)}|{'|'.join(map(str, frame.columns))}".encode()).hexdigest()
    return np.random.default_rng(int(digest[:8], 16))


def build_module_upgrade_artifacts(
    module_key: str,
    data: pd.DataFrame,
    result: pd.DataFrame,
    secondary: pd.DataFrame | None = None,
    extras: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    if module_key not in MODULE_ONLY_KEYS:
        return {"summary": {}, "tables": {}, "figures": {}}
    source = data.head(MAX_MODULE_ROWS).copy() if isinstance(data, pd.DataFrame) else pd.DataFrame()
    output = result.head(MAX_MODULE_ROWS).copy() if isinstance(result, pd.DataFrame) else pd.DataFrame()
    extra_tables = dict(extras or {})
    tables: dict[str, pd.DataFrame] = {}
    figures: dict[str, go.Figure] = {}
    summary: dict[str, Any] = {"module": module_key, "input_rows": len(source), "result_rows": len(output)}

    try:
        if module_key == "digital_pathology_foundation":
            slide = output.copy()
            if not slide.empty:
                slide["review_score"] = (
                    _num(slide.get("tumour_burden", 0), 0).clip(0, 1)
                    * (1 - _num(slide.get("ood_risk", 0), 0).clip(0, 1))
                    * _num(slide.get("tissue_fraction", 0), 0).clip(0, 1)
                )
                slide["review_reason"] = np.select(
                    [slide.get("qc_flag", False).astype(bool), _num(slide.get("ood_risk", 0), 0) > 0.45],
                    ["QC failure", "Embedding/OOD review"],
                    default="Routine review",
                )
                tables["slide_review_queue"] = slide.sort_values(["review_score"], ascending=False)
                group_cols = [c for c in ["site", "scanner"] if c in slide.columns]
                if group_cols:
                    tables["scanner_site_quality"] = slide.groupby(group_cols, as_index=False).agg(
                        slides=("slide_id", "nunique") if "slide_id" in slide.columns else (slide.columns[0], "size"),
                        mean_tissue=("tissue_fraction", "mean"),
                        mean_tumour=("tumour_burden", "mean"),
                        mean_ood=("ood_risk", "mean"),
                        qc_flags=("qc_flag", "sum"),
                    )
                plot = slide.head(MAX_VISUAL_ROWS)
                figures["tumour_tissue_qc"] = px.scatter(plot, x="tissue_fraction", y="tumour_burden", color="qc_flag", hover_name="slide_id" if "slide_id" in plot else None, size="tiles" if "tiles" in plot else None, title="Tumour burden versus tissue coverage")
                if "site" in plot and "scanner" in plot:
                    figures["scanner_drift"] = px.box(plot, x="site", y="ood_risk", color="scanner", points="all", title="Scanner and site OOD distribution")
                summary.update({"review_queue": int(len(slide)), "qc_flags": int(slide.get("qc_flag", pd.Series(dtype=bool)).sum())})

        elif module_key == "long_read_epigenome":
            dmr = output.copy()
            if not dmr.empty:
                dmr["effect_abs"] = _num(dmr.get("delta_methylation", 0), 0).abs()
                dmr["evidence_score"] = dmr["effect_abs"] * (1 - _num(dmr.get("q_value", 1), 1).clip(0, 1)) * _num(dmr.get("qc_pass", 0), 0)
                dmr["direction"] = np.where(_num(dmr.get("delta_methylation", 0), 0) >= 0, "Hypermethylated", "Hypomethylated")
                tables["coverage_weighted_dmr_review"] = dmr.sort_values("evidence_score", ascending=False)
                if {"region", "haplotype", "mean_methylation"}.issubset(dmr.columns):
                    tables["haplotype_ribbon"] = dmr[["region", "haplotype", "mean_methylation", "median_coverage", "effect_abs", "q_value"]].copy()
                plot = dmr.head(MAX_VISUAL_ROWS).copy()
                plot["minus_log10_q"] = -np.log10(_num(plot.get("q_value", 1), 1).clip(lower=1e-300))
                figures["dmr_volcano"] = px.scatter(plot, x="delta_methylation", y="minus_log10_q", color="direction", size="median_coverage", hover_name="region", title="Coverage-aware DMR volcano")
                figures["coverage_effect"] = px.scatter(plot, x="median_coverage", y="effect_abs", color="qc_pass", hover_name="region", title="Coverage versus methylation effect")
                summary.update({"fdr_candidates": int((_num(dmr.get("q_value", 1), 1) <= 0.05).sum()), "max_effect": float(dmr["effect_abs"].max())})

        elif module_key == "single_cell_long_read_isoforms":
            iso = output.copy()
            if not iso.empty:
                entropy = iso.groupby([c for c in ["gene", "cluster"] if c in iso.columns]).apply(lambda g: _entropy(g.get("mean_fraction", pd.Series(dtype=float))), include_groups=False).reset_index(name="isoform_entropy")
                tables["cluster_gene_entropy"] = entropy
                iso["support_grade"] = pd.cut(_num(iso.get("support_score", 0), 0), [-np.inf, 0.25, 0.5, 0.75, np.inf], labels=["Low", "Moderate", "Strong", "High"])
                tables["isoform_support_review"] = iso.sort_values("priority_score", ascending=False)
                plot = iso.head(MAX_VISUAL_ROWS)
                figures["isoform_support"] = px.scatter(plot, x="mean_fraction", y="full_length_rate", size="cells", color="support_grade", hover_name="transcript", facet_col="cluster" if plot.get("cluster", pd.Series()).nunique() <= 6 else None, title="Isoform abundance and full-length support")
                if {"gene", "cluster", "mean_fraction"}.issubset(plot.columns):
                    matrix = plot.groupby(["gene", "cluster"], as_index=False)["mean_fraction"].max()
                    figures["cluster_usage"] = px.density_heatmap(matrix, x="cluster", y="gene", z="mean_fraction", histfunc="avg", title="Cluster-specific dominant isoform usage")
                summary.update({"genes": int(iso.get("gene", pd.Series()).nunique()), "high_support": int((iso.get("support_grade", pd.Series()).astype(str) == "High").sum())})

        elif module_key == "biomedical_foundation_model_hub":
            models = output.copy()
            if not models.empty:
                params = _num(models.get("parameter_count", 0), 0)
                models["estimated_fp16_gb"] = params * 2 / 1e9
                models["estimated_int8_gb"] = params / 1e9
                models["efficiency_score"] = _num(models.get("benchmark_score", 0), 0) / np.log10(params.clip(lower=10))
                licence = models.get("license", pd.Series("Unknown", index=models.index)).astype(str).str.lower()
                models["licence_risk"] = np.select([licence.str.contains("research|custom"), licence.str.contains("apache|mit")], ["Review", "Permissive"], default="Unknown")
                models["hardware_fit_8gb"] = models["estimated_int8_gb"] <= 8
                models["hardware_fit_16gb"] = models["estimated_fp16_gb"] <= 16
                tables["model_operations_matrix"] = models.sort_values(["local_ready", "benchmark_score"], ascending=[False, False])
                figures["accuracy_resource_frontier"] = px.scatter(models, x="estimated_fp16_gb", y="benchmark_score", color="local_ready", symbol="licence_risk", size="embedding_dim" if "embedding_dim" in models else None, hover_name="model_id", title="Benchmark versus estimated model memory")
                if {"modality", "task"}.issubset(models.columns):
                    coverage = models.groupby(["modality", "task"], as_index=False).size()
                    figures["task_modality_coverage"] = px.density_heatmap(coverage, x="task", y="modality", z="size", histfunc="sum", title="Task and modality coverage")
                summary.update({"models": len(models), "local_ready": int(models.get("local_ready", pd.Series(dtype=bool)).astype(bool).sum()), "licence_reviews": int((models["licence_risk"] == "Review").sum())})

        elif module_key == "amr_surveillance":
            amr = output.copy()
            if not amr.empty:
                if "concordance" in amr:
                    amr["concordance_state"] = np.where(_num(amr["concordance"], 0) >= 0.8, "Concordant", "Conflict")
                tables["amr_conflict_review"] = amr.sort_values([c for c in ["review_required", "resistance_rate"] if c in amr], ascending=False)
                if {"species", "amr_gene"}.issubset(source.columns):
                    gene_matrix = source.groupby(["species", "amr_gene"], as_index=False).size().rename(columns={"size": "isolates"})
                    tables["species_gene_matrix"] = gene_matrix
                    figures["gene_species_heatmap"] = px.density_heatmap(gene_matrix, x="amr_gene", y="species", z="isolates", histfunc="sum", title="AMR gene distribution by species")
                if "date" in source.columns:
                    time = source.copy()
                    time["date"] = pd.to_datetime(time["date"], errors="coerce")
                    time = time.dropna(subset=["date"])
                    if not time.empty:
                        time["month"] = time["date"].dt.to_period("M").astype(str)
                        trend = time.groupby(["month", "species"], as_index=False).agg(isolates=("sample", "nunique"), resistance=("resistant_probability", "mean"))
                        tables["temporal_resistance"] = trend
                        figures["resistance_trend"] = px.line(trend, x="month", y="resistance", color="species", markers=True, title="Temporal resistance trend")
                summary.update({"alerts": int(amr.get("review_required", pd.Series(dtype=bool)).astype(bool).sum()), "species": int(source.get("species", pd.Series()).nunique())})

        elif module_key == "spatial_medicine_tme":
            spatial = source.copy()
            if not spatial.empty:
                if {"patient", "region", "cell_type"}.issubset(spatial.columns):
                    comp = spatial.groupby(["patient", "region", "cell_type"], as_index=False).size().rename(columns={"size": "cells"})
                    total = comp.groupby(["patient", "region"])["cells"].transform("sum").replace(0, np.nan)
                    comp["fraction"] = comp["cells"] / total
                    tables["region_cell_composition"] = comp
                    figures["region_cell_heatmap"] = px.density_heatmap(comp, x="cell_type", y="region", z="fraction", facet_col="patient" if comp["patient"].nunique() <= 4 else None, histfunc="avg", title="Cell-type composition by region")
                if {"x", "y"}.issubset(spatial.columns):
                    plot = spatial.head(MAX_VISUAL_ROWS)
                    figures["spatial_point_map"] = px.scatter(plot, x="x", y="y", color="cell_type" if "cell_type" in plot else None, size="expression" if "expression" in plot else None, hover_data=[c for c in ["patient", "region", "gene"] if c in plot], title="Spatial tissue point map")
                summary.update({"patients": int(spatial.get("patient", pd.Series()).nunique()), "regions": int(spatial.get("region", pd.Series()).nunique())})

        elif module_key == "gene_therapy_vector":
            vector = output.copy()
            if not vector.empty:
                cargo_source = vector["cargo_size"] if "cargo_size" in vector else vector["cargo_length"] if "cargo_length" in vector else vector["cargo_bp"] if "cargo_bp" in vector else pd.Series(0, index=vector.index)
                cargo = _num(cargo_source, 0)
                if "capacity_limit" in vector:
                    limit = _num(vector["capacity_limit"], 4700)
                else:
                    limits = {"AAV": 4700.0, "Lentiviral": 8000.0, "Adenoviral": 36000.0}
                    limit = vector.get("vector_type", pd.Series("AAV", index=vector.index)).astype(str).map(limits).fillna(4700.0)
                vector["packaging_margin"] = limit - cargo
                vector["capacity_utilisation"] = cargo / limit.replace(0, np.nan)
                if "sequence" in source.columns:
                    seq_map = source.assign(sequence=source["sequence"].astype(str)).set_index(source.columns[0])["sequence"] if not source.empty else pd.Series(dtype=str)
                    # Sequence metrics are intentionally best-effort and do not imply construct validation.
                vector["risk_count"] = sum((_num(vector.get(c, 0), 0) > 0.5).astype(int) for c in ["immunogenicity_risk", "integration_risk"] if c in vector)
                tables["construct_safety_matrix"] = vector.sort_values([c for c in ["release_blocked", "safety_score"] if c in vector], ascending=[True, False][:len([c for c in ["release_blocked", "safety_score"] if c in vector])])
                figures["capacity_utilisation"] = px.bar(vector.head(100), x="construct", y="capacity_utilisation", color="packaging_pass" if "packaging_pass" in vector else None, title="Vector cargo capacity utilisation")
                if {"safety_score", "tropism_score"}.issubset(vector.columns):
                    figures["safety_tropism"] = px.scatter(vector, x="tropism_score", y="safety_score", size="capacity_utilisation", color="vector_type" if "vector_type" in vector else None, hover_name="construct", title="Tropism and safety profile")
                summary.update({"constructs": len(vector), "packaging_failures": int((~vector.get("packaging_pass", pd.Series(True, index=vector.index)).astype(bool)).sum())})

        elif module_key == "cell_therapy_cart":
            cart = output.copy()
            if not cart.empty:
                cart["efficacy_proxy"] = _num(cart.get("scfv_affinity", 0), 0) * (1 - _num(cart.get("exhaustion_score", 0), 0).clip(0, 1))
                cart["safety_proxy"] = 1 - _num(cart.get("off_tumour_risk", 0), 0).clip(0, 1)
                cart["balanced_score"] = np.sqrt((cart["efficacy_proxy"].clip(lower=0) * cart["safety_proxy"].clip(lower=0))) * _num(cart.get("manufacturability", 0), 0)
                tables["cart_construct_review"] = cart.sort_values("balanced_score", ascending=False)
                figures["efficacy_safety_frontier"] = px.scatter(cart, x="safety_proxy", y="efficacy_proxy", size="manufacturability", color="costim_domain" if "costim_domain" in cart else None, hover_name="construct", title="CAR efficacy-safety frontier")
                if {"antigen", "costim_domain"}.issubset(cart.columns):
                    domain = cart.groupby(["antigen", "costim_domain"], as_index=False).agg(score=("balanced_score", "mean"), constructs=("construct", "nunique"))
                    tables["antigen_domain_matrix"] = domain
                    figures["domain_matrix"] = px.density_heatmap(domain, x="costim_domain", y="antigen", z="score", histfunc="avg", title="Antigen and costimulatory-domain profile")
                summary.update({"constructs": len(cart), "safety_reviews": int(cart.get("safety_review", pd.Series(dtype=bool)).astype(bool).sum())})

        elif module_key == "federated_biomedical_ai":
            fed = source.copy()
            if not fed.empty:
                metric_col = "metric" if "metric" in fed else ("local_metric" if "local_metric" in fed else None)
                if metric_col and {"site", "round"}.issubset(fed.columns):
                    fed[metric_col] = _num(fed[metric_col])
                    round_summary = fed.groupby("round", as_index=False).agg(global_metric=(metric_col, "mean"), site_sd=(metric_col, "std"), sites=("site", "nunique"))
                    tables["round_stability"] = round_summary
                    figures["round_trajectory"] = px.line(round_summary, x="round", y="global_metric", error_y="site_sd", markers=True, title="Federated round performance")
                    site = fed.groupby("site", as_index=False).agg(mean_metric=(metric_col, "mean"), metric_sd=(metric_col, "std"), rounds=("round", "nunique"))
                    site["drift_from_global"] = (site["mean_metric"] - fed[metric_col].mean()).abs()
                    tables["site_heterogeneity"] = site.sort_values("drift_from_global", ascending=False)
                if {"epsilon", metric_col or ""}.issubset(fed.columns):
                    figures["privacy_utility"] = px.scatter(fed, x="epsilon", y=metric_col, color="site" if "site" in fed else None, hover_data=["round"] if "round" in fed else None, title="Privacy-utility frontier")
                summary.update({"sites": int(fed.get("site", pd.Series()).nunique()), "rounds": int(fed.get("round", pd.Series()).nunique())})

        elif module_key == "clinical_biomarker_survival":
            clinical = source.copy()
            if not clinical.empty:
                if "biomarker_group" not in clinical.columns and "biomarker" in clinical.columns:
                    biomarker_values = _num(clinical["biomarker"])
                    cutoff = float(biomarker_values.median()) if biomarker_values.notna().any() else float("nan")
                    clinical["biomarker_group"] = np.where(biomarker_values >= cutoff, "High", "Low")
                    clinical["biomarker_cutoff"] = cutoff
                group_col = "biomarker_group" if "biomarker_group" in clinical else ("group" if "group" in clinical else None)
                if group_col and {"time", "event"}.issubset(clinical.columns):
                    lr = _logrank(clinical, group_col)
                    tables["survival_screening_statistics"] = pd.DataFrame([{**lr, "group_column": group_col, "groups": clinical[group_col].nunique(), "events": int(_num(clinical["event"], 0).sum())}])
                    km_rows: list[dict[str, Any]] = []
                    for group, part in clinical.groupby(group_col):
                        work = part[["time", "event"]].copy()
                        work["time"] = _num(work["time"])
                        work["event"] = _num(work["event"], 0).clip(0, 1)
                        work = work.dropna().sort_values("time")
                        survival = 1.0
                        km_rows.append({group_col: group, "time": 0.0, "survival": 1.0, "at_risk": len(work)})
                        for t in sorted(work["time"].unique()):
                            at_risk = int((work["time"] >= t).sum())
                            events = int(((work["time"] == t) & (work["event"] > 0)).sum())
                            if at_risk and events:
                                survival *= 1 - events / at_risk
                            km_rows.append({group_col: group, "time": float(t), "survival": float(survival), "at_risk": at_risk})
                    km = pd.DataFrame(km_rows)
                    tables["kaplan_meier"] = km
                    figures["km_curve"] = px.line(km, x="time", y="survival", color=group_col, line_shape="hv", title="Kaplan–Meier screening curve")
                    summary.update({"logrank_p": lr["p_value"], "hazard_rate_ratio": lr["hazard_rate_ratio"]})
                if "site" in clinical.columns:
                    site = clinical.groupby("site", as_index=False).agg(patients=(clinical.columns[0], "size"), event_rate=("event", "mean") if "event" in clinical else (clinical.columns[0], "size"), median_time=("time", "median") if "time" in clinical else (clinical.columns[0], "size"))
                    tables["site_heterogeneity"] = site
                summary.update({"patients": int(clinical.get("patient", pd.Series()).nunique()), "events": int(_num(clinical.get("event", pd.Series(dtype=float)), 0).sum())})

        elif module_key == "protein_ligand_codesign":
            co = output.copy()
            if not co.empty:
                objectives = [c for c in ["protein_score", "ligand_score", "interface_score"] if c in co]
                risk = _num(co.get("selectivity_risk", 0), 0)
                dominated = np.zeros(len(co), dtype=bool)
                values = co[objectives].apply(pd.to_numeric, errors="coerce").fillna(0).to_numpy(float) if objectives else np.zeros((len(co), 0))
                risk_values = risk.to_numpy(float)
                for i in range(len(co)):
                    if dominated[i]:
                        continue
                    better_or_equal = (values >= values[i]).all(axis=1) if values.shape[1] else np.ones(len(co), dtype=bool)
                    lower_risk = risk_values <= risk_values[i]
                    strictly_better = ((values > values[i]).any(axis=1) if values.shape[1] else np.zeros(len(co), dtype=bool)) | (risk_values < risk_values[i])
                    dominated[i] = bool((better_or_equal & lower_risk & strictly_better).any())
                co["pareto_optimal"] = ~dominated
                co["robust_score"] = _num(co.get("joint_score", 0), 0) * (1 - risk.clip(0, 1))
                tables["pareto_review"] = co.sort_values(["pareto_optimal", "robust_score"], ascending=[False, False])
                figures["pareto_frontier"] = px.scatter_3d(co.head(MAX_VISUAL_ROWS), x=objectives[0] if objectives else co.columns[0], y=objectives[1] if len(objectives) > 1 else "robust_score", z=objectives[2] if len(objectives) > 2 else "selectivity_risk", color="pareto_optimal", size="robust_score", hover_name="candidate", title="Protein–ligand multi-objective frontier")
                if {"protein_variant", "ligand"}.issubset(co.columns):
                    matrix = co.groupby(["protein_variant", "ligand"], as_index=False)["robust_score"].max()
                    tables["variant_ligand_matrix"] = matrix
                summary.update({"candidates": len(co), "pareto_optimal": int(co["pareto_optimal"].sum())})

        elif module_key == "pangenome_population_medicine":
            pg = output.copy()
            if not pg.empty:
                pg["af"] = _num(pg.get("allele_frequency", 0), 0).clip(0, 1)
                global_af = pg.groupby("variant")["af"].transform("mean")
                denom = (global_af * (1 - global_af)).replace(0, np.nan)
                pg["fst_like"] = ((pg["af"] - global_af) ** 2 / denom).clip(lower=0)
                pg["equity_priority"] = pg["fst_like"].fillna(0) * _num(pg.get("clinical_weight", 0), 0) * (1 - _num(pg.get("reference_bias", 0), 0).clip(0, 1))
                tables["population_differentiation"] = pg.sort_values("equity_priority", ascending=False)
                figures["population_variant_heatmap"] = px.density_heatmap(pg.head(MAX_VISUAL_ROWS), x="variant", y="population", z="af", histfunc="avg", title="Population allele-frequency profile")
                figures["bias_distribution"] = px.box(pg, x="population", y="reference_bias", points="outliers", title="Reference-bias distribution")
                summary.update({"populations": int(pg.get("population", pd.Series()).nunique()), "high_differentiation": int((pg["fst_like"] > 0.15).sum())})

        elif module_key == "pharmacovigilance_intelligence":
            pv = output.copy()
            if not pv.empty:
                reports = _num(pv.get("reports", 0), 0)
                ic = _num(pv.get("information_component", 0), 0)
                # Conservative empirical-Bayes-like shrinkage for ranking only; not a validated EBGM implementation.
                shrink = reports / (reports + 5.0)
                pv["shrunk_information_score"] = ic * shrink
                pv["signal_strength"] = np.log1p(_num(pv.get("reporting_odds_ratio", 0), 0).clip(lower=0)) * shrink * (0.5 + 0.5 * _num(pv.get("serious_rate", 0), 0))
                tables["signal_adjudication_queue"] = pv.sort_values("signal_strength", ascending=False)
                plot = pv.head(MAX_VISUAL_ROWS).copy()
                plot["minus_log10_inverse_ror_lb"] = -np.log10((1 / _num(plot.get("ror_lower_95", 1), 1).clip(lower=1e-6)).clip(lower=1e-6))
                figures["signal_volcano"] = px.scatter(plot, x="reporting_odds_ratio", y="information_component", size="reports", color="signal_flag", hover_name="event", hover_data=["drug"], title="Disproportionality signal map")
                if {"drug", "event", "reports"}.issubset(pv.columns):
                    figures["drug_event_matrix"] = px.density_heatmap(pv, x="event", y="drug", z="reports", histfunc="sum", title="Drug–event report matrix")
                if {"date", "drug"}.issubset(source.columns):
                    t = source.copy(); t["date"] = pd.to_datetime(t["date"], errors="coerce"); t = t.dropna(subset=["date"])
                    if not t.empty:
                        t["month"] = t["date"].dt.to_period("M").astype(str)
                        timeline = t.groupby(["month", "drug"], as_index=False).size().rename(columns={"size": "reports"})
                        tables["signal_timeline"] = timeline
                summary.update({"signals": int(pv.get("signal_flag", pd.Series(dtype=bool)).astype(bool).sum()), "strong_signals": int((pv["signal_strength"] >= pv["signal_strength"].quantile(0.9)).sum())})

        elif module_key == "synthetic_cohort_trial":
            trial = source.copy()
            if not trial.empty and {"arm", "outcome"}.issubset(trial.columns):
                arms = list(trial["arm"].astype(str).unique())
                rng = _stable_rng(module_key, trial)
                simulations: list[dict[str, float]] = []
                if len(arms) >= 2:
                    a0 = _num(trial.loc[trial["arm"].astype(str) == arms[0], "outcome"], 0).to_numpy(float)
                    a1 = _num(trial.loc[trial["arm"].astype(str) == arms[-1], "outcome"], 0).to_numpy(float)
                    if len(a0) and len(a1):
                        for i in range(500):
                            rd = float(rng.choice(a1, len(a1), replace=True).mean() - rng.choice(a0, len(a0), replace=True).mean())
                            simulations.append({"simulation": i + 1, "risk_difference": rd})
                sim = pd.DataFrame(simulations)
                if not sim.empty:
                    tables["monte_carlo_risk_difference"] = sim
                    figures["simulation_distribution"] = px.histogram(sim, x="risk_difference", nbins=40, title="Bootstrap/Monte Carlo risk-difference distribution")
                    summary.update({"simulations": len(sim), "risk_difference_mean": float(sim["risk_difference"].mean()), "risk_difference_ci_low": float(sim["risk_difference"].quantile(0.025)), "risk_difference_ci_high": float(sim["risk_difference"].quantile(0.975))})
                if {"age", "baseline_risk"}.intersection(trial.columns):
                    balance_rows = []
                    for col in [c for c in ["age", "baseline_risk"] if c in trial]:
                        x = _num(trial.loc[trial["arm"].astype(str) == arms[0], col]).dropna()
                        y = _num(trial.loc[trial["arm"].astype(str) == arms[-1], col]).dropna()
                        if len(x) >= 2 and len(y) >= 2:
                            pooled = math.sqrt(max(((len(x)-1)*x.var(ddof=1)+(len(y)-1)*y.var(ddof=1))/max(len(x)+len(y)-2,1),0))
                            smd = _safe_div(y.mean()-x.mean(), pooled)
                            balance_rows.append({"covariate": col, "smd": smd, "absolute_smd": abs(smd), "balanced": abs(smd) <= 0.1})
                    balance = pd.DataFrame(balance_rows)
                    if not balance.empty:
                        tables["covariate_balance_v133"] = balance
                        figures["love_plot"] = px.scatter(balance, x="smd", y="covariate", color="balanced", title="Covariate balance (standardised mean difference)")
                summary.update({"patients": int(trial.get("patient", pd.Series()).nunique()), "sites": int(trial.get("site", pd.Series()).nunique())})

        elif module_key == "autonomous_lab_planner":
            plan = output.copy()
            if not plan.empty:
                coverage = plan.groupby(["factor", "level"], as_index=False).agg(experiments=("experiment_id", "nunique"), replicates=("replicates", "sum"), controls=("control", "sum"), cost=("total_cost", "sum"))
                factor_levels = coverage.groupby("factor")["level"].nunique().reset_index(name="levels")
                factor_levels["coverage_grade"] = pd.cut(factor_levels["levels"], [0, 1, 2, 3, np.inf], labels=["Single", "Limited", "Adequate", "Rich"])
                tables["factor_level_coverage"] = coverage
                tables["factor_coverage_grade"] = factor_levels
                figures["design_matrix"] = px.density_heatmap(coverage, x="level", y="factor", z="experiments", histfunc="sum", title="Experimental factor-level design matrix")
                if "schedule_order" in plan:
                    figures["resource_schedule"] = px.bar(plan.head(200), x="estimated_hours", y="experiment_id", color="review_required", orientation="h", hover_data=[c for c in ["hypothesis", "factor", "level", "total_cost"] if c in plan], title="Experiment schedule and review blockers")
                figures["cost_waterfall"] = px.bar(plan.head(100), x="experiment_id", y="total_cost", color="factor" if "factor" in plan else None, title="Experiment cost profile")
                summary.update({"experiments": len(plan), "review_required": int(plan.get("review_required", pd.Series(dtype=bool)).astype(bool).sum()), "factors": int(plan.get("factor", pd.Series()).nunique())})

    except Exception as exc:
        summary["safe_error"] = f"{type(exc).__name__}: {exc}"

    summary.update({
        "advanced_tables": len(tables),
        "advanced_visuals": len(figures),
        "bounded_input": len(source) < len(data) if isinstance(data, pd.DataFrame) else False,
        "external_engine_required": PROFILES[module_key].external_engine,
    })
    return {"summary": summary, "tables": tables, "figures": figures}


def render_module_upgrade_panel(
    module_key: str,
    data: pd.DataFrame,
    run_state: Any | None,
    *,
    key_prefix: str,
) -> None:
    import streamlit as st

    from biointel.ui.components import metric_cards, smart_dataframe

    if module_key not in MODULE_ONLY_KEYS:
        return
    profile = PROFILES[module_key]
    st.markdown(f"### {profile.title}")
    st.caption("Step 133 module-only upgrade: this panel improves the scientific module itself; no new central hub or platform workflow is created.")
    if run_state is None:
        st.info("Run the module analysis first to activate module-specific advanced features and visuals.")
        return
    artifacts = build_module_upgrade_artifacts(
        module_key,
        data,
        run_state.result,
        run_state.secondary,
        run_state.extras,
    )
    summary = artifacts["summary"]
    metric_cards([
        ("Advanced tables", summary.get("advanced_tables", 0), "Module-specific"),
        ("Advanced visuals", summary.get("advanced_visuals", 0), "Module-specific"),
        ("Input rows", summary.get("input_rows", 0), "Bounded safely"),
        ("Result rows", summary.get("result_rows", 0), "Current run"),
    ])
    if summary.get("safe_error"):
        st.warning(f"Advanced module analysis failed safely: {summary['safe_error']}")

    tab_features, tab_visuals, tab_quality, tab_engine = st.tabs([
        "Advanced features", "Specialist visuals", "Quality gates", "External execution boundary"
    ])
    with tab_features:
        for item in profile.feature_groups:
            st.markdown(f"- {item}")
        for name, frame in artifacts["tables"].items():
            st.markdown(f"#### {name.replace('_', ' ').title()}")
            smart_dataframe(frame.head(10_000), height=340, key=f"{key_prefix}_{name}")
    with tab_visuals:
        if not artifacts["figures"]:
            st.info("The current result does not contain enough compatible fields for specialist visuals.")
        for name, figure in artifacts["figures"].items():
            st.plotly_chart(figure, width="stretch", key=f"{key_prefix}_{name}_plot")
        with st.expander("Visuals expected for this module", expanded=False):
            for item in profile.visual_groups:
                st.markdown(f"- {item}")
    with tab_quality:
        st.markdown("**Module-specific release gates**")
        for item in profile.quality_gates:
            st.markdown(f"- {item}")
        if summary.get("bounded_input"):
            st.warning(f"Advanced module analysis was safely limited to the first {MAX_MODULE_ROWS:,} rows. Use the background engine for the complete dataset.")
    with tab_engine:
        st.info(profile.external_engine)
        st.caption("Built-in results remain research-screening outputs until the required specialist engine, reference release and external validation are available.")
