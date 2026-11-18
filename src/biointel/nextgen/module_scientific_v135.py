from __future__ import annotations

import hashlib
import itertools
import math
import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from scipy import optimize, stats
from scipy.spatial import cKDTree

from .biomedical_expansion import NEW_BIOMEDICAL_KEYS

MODULE_ONLY_KEYS = NEW_BIOMEDICAL_KEYS

MAX_DEPTH_ROWS = 200_000
MAX_PLOT_ROWS = 20_000
MAX_STAT_GROUPS = 250
MAX_BOOTSTRAPS = 120
MAX_NETWORK_LINKS = 180


@dataclass(frozen=True)
class ScientificDepthProfile:
    title: str
    resolved_gaps: tuple[str, ...]
    viewers: tuple[str, ...]
    external_boundary: str


PROFILES: dict[str, ScientificDepthProfile] = {
    "digital_pathology_foundation": ScientificDepthProfile(
        "Pathology tile, uncertainty and scanner-domain review",
        ("Tile-grid reconstruction", "Uncertainty/OOD triage", "Scanner-domain drift PCA", "Slide-level composition confidence"),
        ("Tile probability map", "Uncertainty mosaic", "Scanner-domain projection", "Slide review waterfall"),
        "True WSI pyramids, nuclei/tumour segmentation and diagnostic inference still require OpenSlide/DICOM plus qualified pathology models and pathologist review.",
    ),
    "long_read_epigenome": ScientificDepthProfile(
        "Coverage-weighted methylation, haplotype and DMR diagnostics",
        ("Coverage-weighted condition effects", "Bootstrap confidence intervals", "Allele-specific imbalance", "Replicate-aware FDR review"),
        ("CpG-style lollipop", "Haplotype ribbons", "Confidence-aware DMR volcano", "Coverage/effect landscape"),
        "Raw modified-base calling, read-backed phasing and validated DMR inference require BAM/CRAM/bedMethyl tools such as Dorado/Remora/Modkit and prespecified models.",
    ),
    "single_cell_long_read_isoforms": ScientificDepthProfile(
        "Differential isoform usage and transcript-support diagnostics",
        ("Pseudobulk isoform usage", "Chi-square usage screening with FDR", "Cluster entropy", "Novel/low-support review"),
        ("Isoform-flow Sankey", "Transcript support landscape", "Usage heatmap", "Junction-arc proxy"),
        "Barcode correction, transcript assembly, fusion confirmation and novel-isoform classification require raw long-read pipelines and independent evidence.",
    ),
    "biomedical_foundation_model_hub": ScientificDepthProfile(
        "Model asset, quantisation and hardware-fit planning",
        ("FP32/FP16/INT8/INT4 memory profiles", "Training-memory estimate", "Hardware compatibility", "Efficiency/Pareto screening"),
        ("Hardware-fit matrix", "Accuracy-memory frontier", "Licence/task map", "Operational readiness waterfall"),
        "Actual checkpoint download, security scanning, inference benchmarking, quantisation and fine-tuning require verified model assets and execution backends.",
    ),
    "amr_surveillance": ScientificDepthProfile(
        "AMR concordance, uncertainty and temporal emergence review",
        ("Wilson resistance intervals", "Genotype/phenotype confusion audit", "Rolling temporal acceleration", "Lineage/gene emergence ranking"),
        ("Concordance matrix", "Resistance trend with intervals", "Lineage-gene flow", "Emergence alert map"),
        "Species confirmation, MLST/cgMLST, breakpoint interpretation and plasmid context require current validated databases and specialist genomic pipelines.",
    ),
    "spatial_medicine_tme": ScientificDepthProfile(
        "Spatial neighbourhood and tumour-boundary intelligence",
        ("k-nearest-cell neighbourhood enrichment", "Tumour/immune adjacency", "Regional expression contrast", "Patient replication audit"),
        ("Layered spatial map", "Neighbourhood enrichment heatmap", "Tumour-immune adjacency view", "Region/gene profile"),
        "Native platform ingestion, histology registration, segmentation, deconvolution and ligand-receptor inference require platform-specific validated workflows.",
    ),
    "gene_therapy_vector": ScientificDepthProfile(
        "Vector capacity, sequence-liability and construct-map review",
        ("Vector-specific capacity", "Optional sequence GC/homopolymer/motif QC", "Promoter/vector compatibility", "Safety-manufacturability register"),
        ("Linear construct map", "Capacity gauge", "Sequence-liability profile", "Safety/tropism matrix"),
        "ITR/LTR validation, integration-site risk, immunogenicity and manufacturing qualification require sequence-aware specialist tools and experimental evidence.",
    ),
    "cell_therapy_cart": ScientificDepthProfile(
        "CAR architecture, antigen risk and efficacy-safety balance",
        ("Construct architecture manifest", "Affinity/exhaustion balance", "Off-tumour risk prioritisation", "Domain/manufacturability comparison"),
        ("CAR architecture schematic", "Efficacy-safety frontier", "Antigen-domain matrix", "Construct score waterfall"),
        "CDR/germline annotation, healthy-tissue antigen evidence, tonic signalling and product-release qualification require validated external resources and assays.",
    ),
    "federated_biomedical_ai": ScientificDepthProfile(
        "Federated convergence, fairness and privacy accounting",
        ("Round convergence diagnostics", "Site heterogeneity/fairness gap", "Conservative epsilon composition", "Outlier-site persistence"),
        ("Round performance band", "Site-round heatmap", "Privacy-utility frontier", "Federation topology"),
        "Secure aggregation, attack resistance, membership-inference testing and real multi-site execution require an actual federated runtime and governance controls.",
    ),
    "clinical_biomarker_survival": ScientificDepthProfile(
        "Cox survival, proportional-hazards and calibration screening",
        ("Kaplan-Meier risk tables", "Cox partial-likelihood estimates", "Schoenfeld-style PH diagnostic", "Time-horizon discrimination/calibration"),
        ("KM with risk table", "Cox forest plot", "Calibration curve", "Patient risk waterfall"),
        "These are exploratory statistical screens. Clinical claims require prespecified modelling, missing-data handling, external validation and qualified statistical review.",
    ),
    "protein_ligand_codesign": ScientificDepthProfile(
        "Robust Pareto, selectivity and design-diversity review",
        ("True non-dominated set", "Robust score under objective perturbation", "Diverse shortlist", "Variant-ligand consistency"),
        ("3D objective landscape", "Parallel objective coordinates", "Variant-ligand heatmap", "Robust Pareto frontier"),
        "Docking poses, structural contacts, MD/free-energy and binding confirmation require validated structure engines and experimental feedback.",
    ),
    "pangenome_population_medicine": ScientificDepthProfile(
        "Population differentiation, path diversity and reference-bias review",
        ("FST-like screening", "Population path entropy", "Equity-aware prioritisation", "Cross-population frequency contrast"),
        ("Population-path Sankey", "Allele-frequency heatmap", "Differentiation profile", "Reference-bias distribution"),
        "Graph indexing/genotyping, coordinate liftover and clinical interpretation require VG/ODGI/minigraph-class tools and validated population resources.",
    ),
    "pharmacovigilance_intelligence": ScientificDepthProfile(
        "Shrinkage disproportionality, duplicate and case-series review",
        ("Fisher exact significance", "Gamma-Poisson shrinkage signal", "IC025 screening", "Duplicate/fingerprint review"),
        ("Disproportionality volcano", "Drug-event signal matrix", "Outcome hierarchy", "Signal-strength waterfall"),
        "Validated signal management requires current MedDRA/WHODrug coding, exposure context, duplicate adjudication and pharmacovigilance expert review.",
    ),
    "synthetic_cohort_trial": ScientificDepthProfile(
        "Trial operating characteristics and dropout sensitivity",
        ("Monte Carlo risk-difference distribution", "Observed-effect power screening", "Null type-I error screening", "Dropout sensitivity"),
        ("Risk-difference distribution", "Power/dropout curve", "Covariate Love plot", "Recruitment trajectory"),
        "Simulation outputs depend on explicit assumptions and are not evidence of treatment benefit or a replacement for a prespecified statistical analysis plan.",
    ),
    "autonomous_lab_planner": ScientificDepthProfile(
        "DoE coverage, power planning, plate layout and scheduling",
        ("Factorial coverage matrix", "Approximate sample-size planning", "Adjacency-aware plate assignment", "Resource/cost schedule"),
        ("Interactive plate map", "Resource Gantt", "Factor-level heatmap", "Cost waterfall"),
        "Final experimental design, biosafety, randomisation, instrument scheduling and execution require human approval and organisational ELN/LIMS controls.",
    ),
}


def _num(series: Any, fill: float | None = None) -> pd.Series:
    if isinstance(series, pd.Series):
        out = pd.to_numeric(series, errors="coerce")
    else:
        out = pd.Series(series)
        out = pd.to_numeric(out, errors="coerce")
    return out.fillna(fill) if fill is not None else out


def _bool(series: Any) -> pd.Series:
    source = series if isinstance(series, pd.Series) else pd.Series(series)
    truthy = {"1", "true", "yes", "y", "positive", "resistant", "serious", "event", "case", "pass"}
    return source.map(lambda value: str(value).strip().lower() in truthy if not isinstance(value, (bool, np.bool_)) else bool(value)).astype(bool)


def _safe_div(a: Any, b: Any, default: float = float("nan")) -> float:
    try:
        aa, bb = float(a), float(b)
        return aa / bb if math.isfinite(aa) and math.isfinite(bb) and bb != 0 else default
    except Exception:
        return default


def _stable_rng(module_key: str, *frames: pd.DataFrame) -> np.random.Generator:
    parts = [module_key]
    for frame in frames:
        if isinstance(frame, pd.DataFrame):
            parts.extend([str(len(frame)), "|".join(map(str, frame.columns))])
    digest = hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()
    return np.random.default_rng(int(digest[:16], 16))


def _bh(values: pd.Series) -> pd.Series:
    p = _num(values).to_numpy(float)
    out = np.full(len(p), np.nan)
    valid = np.isfinite(p)
    if not valid.any():
        return pd.Series(out, index=values.index)
    pv = np.clip(p[valid], 0, 1)
    order = np.argsort(pv)
    ranked = pv[order]
    adjusted = np.minimum.accumulate((ranked * len(ranked) / np.arange(1, len(ranked) + 1))[::-1])[::-1]
    restored = np.empty_like(adjusted)
    restored[order] = np.clip(adjusted, 0, 1)
    out[np.where(valid)[0]] = restored
    return pd.Series(out, index=values.index)


def _wilson(successes: float, total: float, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return float("nan"), float("nan")
    p = min(max(successes / total, 0.0), 1.0)
    den = 1 + z * z / total
    center = (p + z * z / (2 * total)) / den
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / den
    return max(0.0, center - half), min(1.0, center + half)


def _input_quality(frame: pd.DataFrame, required: tuple[str, ...] = ()) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    total_cells = max(frame.shape[0] * max(frame.shape[1], 1), 1)
    missing = int(frame.isna().sum().sum()) if not frame.empty else 0
    duplicate_rows = int(frame.duplicated().sum()) if not frame.empty else 0
    duplicate_columns = int(pd.Index(frame.columns).duplicated().sum())
    nonfinite = 0
    for column in frame.select_dtypes(include=[np.number]).columns:
        values = _num(frame[column]).to_numpy(float)
        nonfinite += int((~np.isfinite(values) & ~np.isnan(values)).sum())
    missing_required = [column for column in required if column not in frame.columns]
    rows.extend([
        {"check": "Records", "value": int(len(frame)), "status": "Pass" if len(frame) else "Blocked", "detail": "Rows available for analysis"},
        {"check": "Missing cells", "value": missing, "status": "Review" if missing / total_cells > 0.05 else "Pass", "detail": f"{100 * missing / total_cells:.2f}% of all cells"},
        {"check": "Duplicate rows", "value": duplicate_rows, "status": "Review" if duplicate_rows else "Pass", "detail": "Exact duplicate records"},
        {"check": "Duplicate columns", "value": duplicate_columns, "status": "Blocked" if duplicate_columns else "Pass", "detail": "Column names must be unique"},
        {"check": "Non-finite numeric values", "value": nonfinite, "status": "Review" if nonfinite else "Pass", "detail": "Positive/negative infinity; NaN is counted as missing"},
        {"check": "Missing required columns", "value": len(missing_required), "status": "Blocked" if missing_required else "Pass", "detail": ", ".join(missing_required) if missing_required else "None"},
    ])
    for column in frame.columns:
        cardinality = int(frame[column].nunique(dropna=True))
        if cardinality > 5000 and not pd.api.types.is_numeric_dtype(frame[column]):
            rows.append({"check": f"High-cardinality field: {column}", "value": cardinality, "status": "Review", "detail": "May require indexing or aggregation before visualisation"})
    return pd.DataFrame(rows)


def _clean_for_plot(frame: pd.DataFrame, limit: int = MAX_PLOT_ROWS) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    frame = frame.reset_index(drop=True)
    if len(frame) <= limit:
        return frame.copy()
    numeric = frame.select_dtypes(include=[np.number]).columns.tolist()
    keep: set[int] = set()
    if numeric:
        for column in numeric[:6]:
            series = _num(frame[column])
            for quantile in np.linspace(0, 1, 21):
                target = series.quantile(quantile)
                if math.isfinite(float(target)):
                    keep.add(int((series - target).abs().idxmin()))
    remaining = max(limit - len(keep), 0)
    if remaining:
        digest = pd.util.hash_pandas_object(frame.astype(str), index=True).to_numpy(np.uint64)
        sampled = np.argsort(digest)[:remaining]
        keep.update(int(frame.index[i]) for i in sampled)
    return frame.loc[sorted(keep)[:limit]].copy()


def _pareto_mask(values: np.ndarray, maximise: tuple[bool, ...]) -> np.ndarray:
    if values.size == 0:
        return np.zeros(0, dtype=bool)
    data = values.astype(float).copy()
    for index, flag in enumerate(maximise):
        if not flag:
            data[:, index] *= -1
    mask = np.ones(len(data), dtype=bool)
    for i in range(len(data)):
        if not mask[i]:
            continue
        dominated_by_any = np.any(np.all(data >= data[i], axis=1) & np.any(data > data[i], axis=1))
        if dominated_by_any:
            mask[i] = False
    return mask


def _auc_binary(y: np.ndarray, score: np.ndarray) -> float:
    valid = np.isfinite(y) & np.isfinite(score)
    y, score = y[valid].astype(int), score[valid].astype(float)
    if len(np.unique(y)) < 2:
        return float("nan")
    ranks = stats.rankdata(score)
    n1 = int((y == 1).sum())
    n0 = int((y == 0).sum())
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else float("nan")


def _cox_fit(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    work = frame.copy()
    required = {"time", "event", "biomarker"}
    if not required.issubset(work.columns):
        return pd.DataFrame(), pd.DataFrame(), {"status": "Unavailable", "reason": "time, event and biomarker are required"}
    work["time"] = _num(work["time"])
    work["event"] = _num(work["event"], 0).clip(0, 1)
    work["biomarker"] = _num(work["biomarker"])
    work = work.dropna(subset=["time", "event", "biomarker"])
    work = work.loc[work["time"] >= 0].copy()
    if len(work) < 20 or int(work["event"].sum()) < 8:
        return pd.DataFrame(), pd.DataFrame(), {"status": "Blocked", "reason": "At least 20 patients and 8 events are required for exploratory Cox screening"}

    covariates: list[tuple[str, np.ndarray]] = []
    biomarker = work["biomarker"].to_numpy(float)
    biomarker_sd = float(np.std(biomarker, ddof=1)) or 1.0
    covariates.append(("Biomarker (per SD)", (biomarker - np.mean(biomarker)) / biomarker_sd))
    if "arm" in work.columns:
        arms = work["arm"].astype(str)
        levels = sorted(arms.unique().tolist())
        for level in levels[1:4]:
            covariates.append((f"Arm: {level} vs {levels[0]}", (arms == level).astype(float).to_numpy()))
    if "site" in work.columns:
        sites = work["site"].astype(str)
        top_sites = sites.value_counts().index.tolist()[:4]
        for level in top_sites[1:]:
            covariates.append((f"Site: {level} vs {top_sites[0]}", (sites == level).astype(float).to_numpy()))
    names = [name for name, _ in covariates]
    x = np.column_stack([values for _, values in covariates]).astype(float)
    time = work["time"].to_numpy(float)
    event = work["event"].to_numpy(int)

    # Remove zero-variance columns.
    variance = np.var(x, axis=0)
    keep = variance > 1e-12
    x = x[:, keep]
    names = [name for name, flag in zip(names, keep, strict=False) if flag]
    if x.shape[1] == 0:
        return pd.DataFrame(), pd.DataFrame(), {"status": "Blocked", "reason": "No variable covariates"}

    unique_event_times = np.unique(time[event == 1])

    def nll(beta: np.ndarray) -> float:
        eta = np.clip(x @ beta, -30, 30)
        exp_eta = np.exp(eta)
        value = 0.0
        for t in unique_event_times:
            deaths = (time == t) & (event == 1)
            d = int(deaths.sum())
            if d == 0:
                continue
            risk = time >= t
            risk_sum = float(exp_eta[risk].sum())
            if risk_sum <= 0:
                continue
            value -= float(eta[deaths].sum() - d * math.log(risk_sum))
        return value

    fit = optimize.minimize(nll, np.zeros(x.shape[1]), method="BFGS", options={"maxiter": 500, "gtol": 1e-7})
    beta = fit.x
    try:
        covariance = np.asarray(fit.hess_inv, dtype=float)
        se = np.sqrt(np.clip(np.diag(covariance), 0, np.inf))
    except Exception:
        se = np.full(len(beta), np.nan)
    z = np.divide(beta, se, out=np.full_like(beta, np.nan), where=np.isfinite(se) & (se > 0))
    p = 2 * stats.norm.sf(np.abs(z))
    forest = pd.DataFrame({
        "covariate": names,
        "coefficient": beta,
        "hazard_ratio": np.exp(beta),
        "lower_95": np.exp(beta - 1.96 * se),
        "upper_95": np.exp(beta + 1.96 * se),
        "p_value": p,
    })

    # Schoenfeld-style residual/time correlation screen.
    eta = np.clip(x @ beta, -30, 30)
    exp_eta = np.exp(eta)
    residual_rows: list[dict[str, Any]] = []
    for row_index in np.where(event == 1)[0]:
        t = time[row_index]
        risk = time >= t
        denom = float(exp_eta[risk].sum())
        if denom <= 0:
            continue
        expected = (x[risk] * exp_eta[risk, None]).sum(axis=0) / denom
        residual = x[row_index] - expected
        for j, name in enumerate(names):
            residual_rows.append({"time": t, "covariate": name, "residual": residual[j]})
    residual_frame = pd.DataFrame(residual_rows)
    ph_rows: list[dict[str, Any]] = []
    if not residual_frame.empty:
        for name, group in residual_frame.groupby("covariate"):
            if len(group) >= 5 and group["time"].nunique() > 2:
                rho, p_value = stats.spearmanr(np.log1p(group["time"]), group["residual"], nan_policy="omit")
            else:
                rho, p_value = float("nan"), float("nan")
            ph_rows.append({"covariate": name, "rho_time": rho, "p_value": p_value, "ph_review": bool(math.isfinite(p_value) and p_value < 0.05)})
    ph = pd.DataFrame(ph_rows)

    # Median-horizon discrimination and calibration.
    horizon = float(np.nanmedian(time))
    event_times = sorted(t for t in unique_event_times if t <= horizon)
    baseline_hazard = 0.0
    for t in event_times:
        deaths = int(((time == t) & (event == 1)).sum())
        risk = time >= t
        denom = float(exp_eta[risk].sum())
        if denom > 0:
            baseline_hazard += deaths / denom
    predicted = 1 - np.exp(-baseline_hazard * exp_eta)
    eligible = ((event == 1) & (time <= horizon)) | (time > horizon)
    y_horizon = ((event == 1) & (time <= horizon)).astype(int)
    auc = _auc_binary(y_horizon[eligible], predicted[eligible])
    calibration = pd.DataFrame({"predicted": predicted, "observed_by_horizon": y_horizon, "eligible": eligible})
    calibration = calibration.loc[calibration["eligible"]].copy()
    if len(calibration) >= 8:
        bins = min(5, max(2, len(calibration) // 8))
        calibration["risk_group"] = pd.qcut(calibration["predicted"], bins, duplicates="drop")
        calibration_table = calibration.groupby("risk_group", observed=True, as_index=False).agg(
            patients=("observed_by_horizon", "size"), predicted_risk=("predicted", "mean"), observed_risk=("observed_by_horizon", "mean")
        )
    else:
        calibration_table = pd.DataFrame()
    diagnostics = {"status": "Pass" if fit.success else "Review", "converged": bool(fit.success), "patients": len(work), "events": int(event.sum()), "horizon": horizon, "time_auc": auc, "message": str(fit.message)}
    return forest, ph, {**diagnostics, "calibration": calibration_table, "patient_risk": pd.DataFrame({"patient": work.get("patient", pd.Series(np.arange(len(work)), index=work.index)).astype(str), "time": time, "event": event, "predicted_risk": predicted})}


def _weighted_bootstrap_effect(group: pd.DataFrame, rng: np.random.Generator) -> tuple[float, float, float]:
    conditions = [str(value) for value in group["condition"].dropna().astype(str).unique().tolist()]
    if len(conditions) < 2:
        return float("nan"), float("nan"), float("nan")
    first, second = conditions[0], conditions[-1]

    def weighted_mean(part: pd.DataFrame) -> float:
        value = _num(part["methylation_fraction"])
        weight = _num(part["coverage"], 0).clip(lower=0)
        valid = value.notna() & weight.gt(0)
        return float(np.average(value[valid], weights=weight[valid])) if valid.any() else float(value.mean())

    a = group.loc[group["condition"].astype(str) == first]
    b = group.loc[group["condition"].astype(str) == second]
    if a.empty or b.empty:
        return float("nan"), float("nan"), float("nan")
    effect = weighted_mean(b) - weighted_mean(a)
    values: list[float] = []
    for _ in range(MAX_BOOTSTRAPS):
        aa = a.iloc[rng.integers(0, len(a), len(a))]
        bb = b.iloc[rng.integers(0, len(b), len(b))]
        values.append(weighted_mean(bb) - weighted_mean(aa))
    return effect, float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))


def _factorial_design(frame: pd.DataFrame) -> pd.DataFrame:
    if not {"factor", "level"}.issubset(frame.columns):
        return pd.DataFrame()
    levels = {
        str(factor): sorted(group["level"].dropna().astype(str).unique().tolist())
        for factor, group in frame.groupby("factor")
        if group["level"].notna().any()
    }
    if not levels:
        return pd.DataFrame()
    factors = list(levels)[:8]
    combinations = 1
    for factor in factors:
        combinations *= max(len(levels[factor]), 1)
    if combinations > 256:
        # Preserve bounded operation by selecting the most frequent two levels.
        levels = {factor: levels[factor][:2] for factor in factors}
    rows = [dict(zip(factors, values, strict=False)) for values in itertools.product(*(levels[factor] for factor in factors))]
    result = pd.DataFrame(rows)
    result.insert(0, "design_run", np.arange(1, len(result) + 1))
    return result


def _plate_layout(frame: pd.DataFrame, wells: int = 96) -> pd.DataFrame:
    rows_labels = list("ABCDEFGH") if wells == 96 else list("ABCDEFGHIJKLMNOP")
    columns = 12 if wells == 96 else 24
    available = [(row, column) for row in rows_labels for column in range(1, columns + 1)]
    assignments = frame.copy().reset_index(drop=True)
    if assignments.empty:
        return pd.DataFrame()
    # Put controls across corners/edges first, then interleave hypotheses to reduce adjacency.
    controls = assignments.loc[_bool(assignments.get("control", pd.Series(False, index=assignments.index)))].copy()
    others = assignments.drop(index=controls.index).copy()
    ordered_parts: list[pd.DataFrame] = []
    if not controls.empty:
        ordered_parts.append(controls)
    if not others.empty and "hypothesis" in others.columns:
        buckets = [group for _, group in others.groupby("hypothesis", sort=True)]
        interleaved: list[pd.Series] = []
        while any(len(group) for group in buckets):
            for index, group in enumerate(buckets):
                if len(group):
                    interleaved.append(group.iloc[0])
                    buckets[index] = group.iloc[1:]
        ordered_parts.append(pd.DataFrame(interleaved))
    elif not others.empty:
        ordered_parts.append(others)
    ordered = pd.concat(ordered_parts, ignore_index=True)
    if len(ordered) > len(available):
        ordered = ordered.head(len(available))
    # Corner/edge-first mapping for controls, checkerboard-ish for remaining records.
    priority = [("A", 1), ("A", columns), (rows_labels[-1], 1), (rows_labels[-1], columns)]
    checker = [(r, c) for parity in (0, 1) for r_i, r in enumerate(rows_labels) for c in range(1, columns + 1) if (r_i + c) % 2 == parity and (r, c) not in priority]
    positions = priority + checker
    ordered["plate_row"] = [positions[i][0] for i in range(len(ordered))]
    ordered["plate_column"] = [positions[i][1] for i in range(len(ordered))]
    ordered["well"] = ordered["plate_row"] + ordered["plate_column"].astype(str)
    return ordered


from .module_scientific_builders_v135 import build_module_scientific_artifacts


def render_module_scientific_v135_panel(
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
    st.divider()
    st.markdown(f"### Step 135 · {profile.title}")
    st.caption("Module-only scientific and visual depth: advanced calculations are bounded, transparent and isolated from the primary result so a viewer failure cannot crash the module.")
    if run_state is None:
        st.info("Run the primary module analysis to activate the Step 135 scientific depth and specialist viewers.")
        return

    artifacts = build_module_scientific_artifacts(module_key, data, run_state.result, run_state.secondary, run_state.extras)
    summary = artifacts["summary"]
    metric_cards([
        ("Scientific tables", summary.get("scientific_tables", 0), "New module depth"),
        ("Specialist viewers", summary.get("specialist_viewers", 0), "Domain-specific"),
        ("Input records", summary.get("input_rows", 0), "Current run"),
        ("Safe boundary", "Active", "External proof not fabricated"),
    ])
    if summary.get("safe_error"):
        st.warning(f"Step 135 analysis failed safely without affecting the primary module result: {summary['safe_error']}")

    tab_science, tab_viewers, tab_quality, tab_boundary = st.tabs([
        "Scientific depth", "Specialist viewers", "Dirty-input qualification", "Validation boundary"
    ])
    with tab_science:
        for item in profile.resolved_gaps:
            st.markdown(f"- {item}")
        names = list(artifacts["tables"])
        if not names:
            st.info("The current input does not contain the optional fields required for deeper module calculations.")
        else:
            selected = st.selectbox("Scientific result table", names, format_func=lambda value: value.replace("_", " ").title(), key=f"{key_prefix}_table")
            smart_dataframe(artifacts["tables"][selected].head(20_000), height=430, key=f"{key_prefix}_{selected}")
            st.download_button(
                "Download complete table",
                artifacts["tables"][selected].to_csv(index=False).encode("utf-8"),
                file_name=f"{module_key}_{selected}.csv",
                mime="text/csv",
                key=f"{key_prefix}_{selected}_download",
            )
    with tab_viewers:
        for item in profile.viewers:
            st.markdown(f"- {item}")
        names = list(artifacts["figures"])
        if not names:
            st.info("No compatible specialist viewer could be built from the current result fields.")
        else:
            selected = st.selectbox("Specialist viewer", names, format_func=lambda value: value.replace("_", " ").title(), key=f"{key_prefix}_viewer")
            try:
                st.plotly_chart(artifacts["figures"][selected], width="stretch", key=f"{key_prefix}_{selected}_figure")
            except Exception as exc:
                st.warning(f"Viewer failed safely: {type(exc).__name__}: {exc}")
    with tab_quality:
        smart_dataframe(artifacts["quality"], height=360, key=f"{key_prefix}_quality")
        if summary.get("bounded_input"):
            st.warning(f"Deep analysis was bounded to {MAX_DEPTH_ROWS:,} records. Complete-scale execution should use a background or specialist engine.")
        st.caption("Unknown units, genome builds, reference releases and unsupported categorical values remain review items rather than being silently guessed.")
    with tab_boundary:
        st.warning(profile.external_boundary)
        st.markdown("**Result status:** Built-in research screening and visual review. External-engine results and experimental/clinical validation must be imported with provenance before release claims are made.")
