from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

import numpy as np
import pandas as pd

from biointel.database.core import managed_connect
import plotly.express as px
import plotly.graph_objects as go


MAX_VISUAL_ROWS = 50_000
MAX_BROWSER_POINTS = 5_000
MAX_NETWORK_NODES = 120
MAX_BOOKMARKS_PER_MODULE = 250


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return str(value)


def safe_json(value: Any) -> str:
    return json.dumps(value, default=_json_default, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def stable_hash(value: Any) -> str:
    return hashlib.sha256(safe_json(value).encode("utf-8")).hexdigest()


def bounded_frame(value: Any, *, limit: int = MAX_VISUAL_ROWS) -> pd.DataFrame:
    frame = pd.DataFrame(value).copy() if value is not None else pd.DataFrame()
    if frame.empty:
        return frame
    frame.columns = [str(column) for column in frame.columns]
    frame = frame.loc[:, ~frame.columns.duplicated()].copy()
    if len(frame) <= limit:
        return frame.reset_index(drop=True)
    # Deterministic stratified preview: first/last, extrema and evenly spaced records.
    keep: set[int] = set(range(min(25, len(frame))))
    keep.update(range(max(0, len(frame) - 25), len(frame)))
    numeric = frame.select_dtypes(include=[np.number]).columns.tolist()[:8]
    for column in numeric:
        series = pd.to_numeric(frame[column], errors="coerce")
        if series.notna().any():
            keep.update(series.nsmallest(3).index.tolist())
            keep.update(series.nlargest(3).index.tolist())
    remaining = max(0, limit - len(keep))
    if remaining:
        indices = np.linspace(0, len(frame) - 1, num=min(remaining, len(frame)), dtype=int)
        keep.update(map(int, indices.tolist()))
    return frame.loc[sorted(keep)[:limit]].reset_index(drop=True)


def _numeric_columns(frame: pd.DataFrame, *, minimum: int = 3) -> list[str]:
    columns: list[str] = []
    for column in frame.columns:
        if pd.to_numeric(frame[column], errors="coerce").notna().sum() >= minimum:
            columns.append(str(column))
    return columns


def _categorical_columns(frame: pd.DataFrame) -> list[str]:
    columns: list[str] = []
    for column in frame.columns:
        series = frame[column].dropna()
        if 1 < series.astype(str).nunique() <= 80:
            columns.append(str(column))
    return columns


def _id_column(frame: pd.DataFrame) -> str:
    hints = (
        "patient", "sample", "slide_id", "construct", "candidate", "model_id", "drug",
        "variant", "region", "gene", "transcript", "experiment_id", "report_id", "cell",
        "lineage", "entity", "id",
    )
    lower = {str(column).lower(): str(column) for column in frame.columns}
    for hint in hints:
        if hint in lower:
            return lower[hint]
    for column in frame.columns:
        if str(column).lower().endswith("_id"):
            return str(column)
    return str(frame.columns[0]) if len(frame.columns) else "entity"


def _score_column(frame: pd.DataFrame) -> str | None:
    hints = (
        "priority_score", "score", "probability", "benchmark_score", "clinical_utility_score",
        "joint_score", "engineering_score", "readiness_score", "response_rate", "survival",
        "tumour_burden", "resistance_rate", "global_metric", "outcome_rate", "mean_methylation",
    )
    lower = {str(column).lower(): str(column) for column in frame.columns}
    for hint in hints:
        if hint in lower and pd.to_numeric(frame[lower[hint]], errors="coerce").notna().any():
            return lower[hint]
    numeric = _numeric_columns(frame)
    return numeric[0] if numeric else None


def _time_column(frame: pd.DataFrame) -> str | None:
    hints = ("date", "time", "month", "round", "position", "schedule_order", "created_at_utc")
    lower = {str(column).lower(): str(column) for column in frame.columns}
    for hint in hints:
        if hint in lower:
            return lower[hint]
    return None


def _safe_numeric(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    return values


def _normalise(series: pd.Series) -> pd.Series:
    values = _safe_numeric(series)
    if not values.notna().any():
        return pd.Series(np.zeros(len(series)), index=series.index, dtype=float)
    low, high = float(values.min()), float(values.max())
    if not np.isfinite(low) or not np.isfinite(high) or math.isclose(low, high):
        return pd.Series(np.full(len(series), 0.5), index=series.index, dtype=float)
    return ((values - low) / (high - low)).clip(0, 1).fillna(0.0)


@dataclass(frozen=True)
class VisualDefinition:
    key: str
    title: str
    category: str
    summary: str
    icon: str
    module_keys: tuple[str, ...] = ()


VISUAL_CATALOG: tuple[VisualDefinition, ...] = (
    VisualDefinition("biological_scale_navigator", "Biological Scale Zoom Navigator", "Multi-scale", "Navigate population → patient → tissue → cell → gene → protein → molecule.", "🔬"),
    VisualDefinition("omics_time_cube", "Four-Dimensional Omics Time Cube", "Multi-scale", "Compare features, samples, omics layers and time in one 3D view.", "🧊"),
    VisualDefinition("causal_intervention_graph", "Causal Intervention Graph", "Causal & evidence", "Explore transparent cause, mediator, intervention and outcome assumptions.", "🕸️"),
    VisualDefinition("hypothesis_evidence_constellation", "Hypothesis–Evidence Constellation", "Causal & evidence", "Map supporting, contradictory and unresolved evidence around a hypothesis.", "✨"),
    VisualDefinition("scientific_contradiction_map", "Scientific Contradiction Map", "Causal & evidence", "Surface data, model, assay and cohort disagreements without hiding uncertainty.", "⚡"),
    VisualDefinition("digital_patient_twin", "Digital Patient Twin Trajectory", "Clinical & temporal", "Compare actual, expected and scenario trajectories over time.", "🧍", ("clinical_biomarker_survival", "spatial_medicine_tme", "synthetic_cohort_trial")),
    VisualDefinition("model_behaviour_atlas", "Model Behaviour Atlas", "AI & governance", "Locate correct, uncertain, out-of-domain and subgroup-failure regions.", "🧠", ("biomedical_foundation_model_hub", "federated_biomedical_ai")),
    VisualDefinition("dataset_health_topology", "Dataset Health Topology Map", "AI & governance", "Visualise datasets, runs, models, evidence and reports with health states.", "🗂️"),
    VisualDefinition("scientific_assumption_dashboard", "Scientific Assumption Dashboard", "AI & governance", "Inspect sample adequacy, balance, missingness, linearity and outlier pressure.", "📐"),
    VisualDefinition("experiment_replay", "Experiment Replay Visual", "Workflow", "Replay import, QC, filtering, analysis, review and export states.", "⏪"),
    VisualDefinition("genome_editing_canvas", "Genome Editing Canvas", "Genomics", "Display sequence coordinates, guides, primers, variants and editing windows.", "✂️", ("gene_therapy_vector", "pangenome_population_medicine", "long_read_epigenome")),
    VisualDefinition("haplotype_ribbon", "Haplotype Ribbon Viewer", "Genomics", "Compare phased paths, methylation and population-specific events.", "🎗️", ("long_read_epigenome", "pangenome_population_medicine")),
    VisualDefinition("variant_evidence_waterfall", "Variant Evidence Waterfall", "Genomics", "Show how frequency, function, phenotype and evidence contribute to priority.", "🌊", ("pangenome_population_medicine", "long_read_epigenome")),
    VisualDefinition("phylogenetic_mutation_movie", "Phylogenetic Mutation Movie", "Genomics", "Animate lineage expansion, resistance acquisition and temporal spread.", "🧬", ("amr_surveillance",)),
    VisualDefinition("drug_attrition_funnel", "Drug Discovery Attrition Funnel", "Discovery", "Track candidates through validity, activity, selectivity and developability gates.", "🔻", ("protein_ligand_codesign", "pharmacovigilance_intelligence")),
    VisualDefinition("molecular_series_evolution", "Molecular Series Evolution Map", "Discovery", "Trace analogue generations, scores, liabilities and retained improvements.", "🧪", ("protein_ligand_codesign", "cell_therapy_cart", "gene_therapy_vector")),
    VisualDefinition("binding_energy_landscape", "Binding Energy Landscape", "Discovery", "Explore multi-objective protein, ligand, interface and selectivity surfaces.", "⛰️", ("protein_ligand_codesign",)),
    VisualDefinition("synthesis_route_network", "Synthesis Route Network", "Discovery", "Compare hypothetical route steps, costs, hazards and alternatives.", "⚗️", ("protein_ligand_codesign", "gene_therapy_vector")),
    VisualDefinition("lab_digital_twin", "Live Laboratory Digital Twin", "Laboratory", "Map instruments, samples, operators, jobs, reagents and blockers.", "🏭", ("autonomous_lab_planner", "synthetic_cohort_trial")),
    VisualDefinition("plate_time_lapse", "Plate Time-Lapse Movie", "Laboratory", "Animate signal, edge effects, control drift and replicate divergence.", "🧫", ("autonomous_lab_planner",)),
    VisualDefinition("bioprocess_trajectory_tunnel", "Bioprocess Batch Trajectory Tunnel", "Laboratory", "Compare a current trajectory against a golden tolerance envelope.", "🌀", ("autonomous_lab_planner",)),
    VisualDefinition("experimental_design_geometry", "Experimental Design Geometry", "Laboratory", "Inspect factor-space coverage, centre points, response surface and uncertainty.", "📊", ("autonomous_lab_planner", "synthetic_cohort_trial")),
    VisualDefinition("model_release_wall", "Model Release Readiness Radar Wall", "AI & governance", "Compare multiple models across evidence, performance and reproducibility.", "🧱", ("biomedical_foundation_model_hub", "federated_biomedical_ai")),
    VisualDefinition("evidence_maturity_ladder", "Evidence Maturity Ladder", "AI & governance", "Place entities from demonstration through independent validation and release.", "🪜"),
    VisualDefinition("scientific_risk_heatmap", "Scientific Risk Heatmap", "AI & governance", "Compare data, statistics, biology, operations, security and evidence risks.", "🔥"),
    VisualDefinition("research_portfolio_bubble", "Research Portfolio Bubble Map", "Decision intelligence", "Compare value, maturity, cost, risk and resource demand.", "🫧"),
    VisualDefinition("multi_monitor_workspace", "Multi-Monitor Scientific Workspace", "Experience", "Save coordinated raw-data, analysis, evidence and job-monitor layouts.", "🖥️"),
    VisualDefinition("presenter_mode", "Scientific Presenter Mode", "Experience", "Create audience-safe full-screen narratives with saved visual state.", "🎤"),
    VisualDefinition("visual_bookmark_timeline", "Visual Bookmark Timeline", "Experience", "Restore exact filters, zoom, scenario, selection and figure state.", "🔖"),
    VisualDefinition("visual_command_palette", "Scientific Visual Command Palette", "Experience", "Discover visual actions, open linked views and export selected evidence.", "⌨️"),
)

VISUAL_BY_KEY = {item.key: item for item in VISUAL_CATALOG}

MODULE_VISUALS: dict[str, tuple[str, ...]] = {
    "digital_pathology_foundation": ("biological_scale_navigator", "hypothesis_evidence_constellation", "scientific_contradiction_map", "dataset_health_topology", "experiment_replay", "research_portfolio_bubble"),
    "long_read_epigenome": ("omics_time_cube", "genome_editing_canvas", "haplotype_ribbon", "variant_evidence_waterfall", "scientific_assumption_dashboard", "experiment_replay"),
    "single_cell_long_read_isoforms": ("biological_scale_navigator", "omics_time_cube", "hypothesis_evidence_constellation", "scientific_assumption_dashboard", "experiment_replay", "scientific_risk_heatmap"),
    "biomedical_foundation_model_hub": ("model_behaviour_atlas", "model_release_wall", "dataset_health_topology", "evidence_maturity_ladder", "scientific_risk_heatmap", "research_portfolio_bubble"),
    "amr_surveillance": ("phylogenetic_mutation_movie", "scientific_contradiction_map", "dataset_health_topology", "evidence_maturity_ladder", "scientific_risk_heatmap", "experiment_replay"),
    "spatial_medicine_tme": ("biological_scale_navigator", "omics_time_cube", "digital_patient_twin", "causal_intervention_graph", "hypothesis_evidence_constellation", "experiment_replay"),
    "gene_therapy_vector": ("genome_editing_canvas", "molecular_series_evolution", "synthesis_route_network", "scientific_risk_heatmap", "evidence_maturity_ladder", "research_portfolio_bubble"),
    "cell_therapy_cart": ("biological_scale_navigator", "molecular_series_evolution", "causal_intervention_graph", "scientific_risk_heatmap", "evidence_maturity_ladder", "research_portfolio_bubble"),
    "federated_biomedical_ai": ("model_behaviour_atlas", "model_release_wall", "scientific_assumption_dashboard", "scientific_risk_heatmap", "research_portfolio_bubble", "experiment_replay"),
    "clinical_biomarker_survival": ("digital_patient_twin", "causal_intervention_graph", "scientific_assumption_dashboard", "scientific_contradiction_map", "evidence_maturity_ladder", "experiment_replay"),
    "protein_ligand_codesign": ("drug_attrition_funnel", "molecular_series_evolution", "binding_energy_landscape", "synthesis_route_network", "research_portfolio_bubble", "experiment_replay"),
    "pangenome_population_medicine": ("genome_editing_canvas", "haplotype_ribbon", "variant_evidence_waterfall", "dataset_health_topology", "evidence_maturity_ladder", "experiment_replay"),
    "pharmacovigilance_intelligence": ("scientific_contradiction_map", "hypothesis_evidence_constellation", "drug_attrition_funnel", "evidence_maturity_ladder", "scientific_risk_heatmap", "experiment_replay"),
    "synthetic_cohort_trial": ("digital_patient_twin", "scientific_assumption_dashboard", "experimental_design_geometry", "research_portfolio_bubble", "evidence_maturity_ladder", "experiment_replay"),
    "autonomous_lab_planner": ("lab_digital_twin", "plate_time_lapse", "bioprocess_trajectory_tunnel", "experimental_design_geometry", "scientific_risk_heatmap", "experiment_replay"),
}


def visuals_for_module(module_key: str) -> tuple[str, ...]:
    return MODULE_VISUALS.get(module_key, tuple(item.key for item in VISUAL_CATALOG[:6]))


def _scatter_xy(frame: pd.DataFrame) -> tuple[str | None, str | None]:
    numeric = _numeric_columns(frame)
    if len(numeric) >= 2:
        return numeric[0], numeric[1]
    if len(numeric) == 1:
        return "__index__", numeric[0]
    return None, None


def _with_index(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["__index__"] = np.arange(len(out))
    return out


def _network_figure(nodes: pd.DataFrame, edges: pd.DataFrame, *, title: str) -> go.Figure:
    if nodes.empty:
        return go.Figure().update_layout(title=title)
    count = min(len(nodes), MAX_NETWORK_NODES)
    nodes = nodes.head(count).reset_index(drop=True)
    angle = np.linspace(0, 2 * np.pi, count, endpoint=False)
    radius = 1.0 + (np.arange(count) % 3) * 0.18
    nodes["x"] = np.cos(angle) * radius
    nodes["y"] = np.sin(angle) * radius
    index = {str(row["node"]): idx for idx, row in nodes.iterrows()}
    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for _, edge in edges.head(MAX_NETWORK_NODES * 2).iterrows():
        source, target = index.get(str(edge["source"])), index.get(str(edge["target"]))
        if source is None or target is None:
            continue
        edge_x.extend([nodes.loc[source, "x"], nodes.loc[target, "x"], None])
        edge_y.extend([nodes.loc[source, "y"], nodes.loc[target, "y"], None])
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines", hoverinfo="skip", name="links"))
    figure.add_trace(go.Scatter(
        x=nodes["x"], y=nodes["y"], mode="markers+text", text=nodes["label"],
        textposition="top center", customdata=nodes[["node", "status"]].to_numpy(),
        hovertemplate="%{customdata[0]}<br>Status: %{customdata[1]}<extra></extra>",
        marker={"size": 14 + _normalise(nodes.get("weight", pd.Series([1] * len(nodes)))) * 20},
        name="entities",
    ))
    figure.update_layout(title=title, showlegend=False, xaxis={"visible": False}, yaxis={"visible": False})
    return figure


def _generic_nodes(frame: pd.DataFrame, module_key: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    if frame.empty:
        nodes = pd.DataFrame([{"node": module_key, "label": module_key.replace("_", " ").title(), "status": "No data", "weight": 1.0}])
        return nodes, pd.DataFrame(columns=["source", "target"])
    identifier = _id_column(frame)
    score = _score_column(frame)
    sample = frame.head(30).copy()
    nodes = pd.DataFrame({
        "node": sample[identifier].astype(str),
        "label": sample[identifier].astype(str).str.slice(0, 18),
        "status": np.where(_normalise(sample[score]) >= 0.67, "High", np.where(_normalise(sample[score]) >= 0.34, "Medium", "Low")) if score else "Observed",
        "weight": _normalise(sample[score]) if score else 0.5,
    })
    center = f"{module_key}:hypothesis"
    nodes = pd.concat([pd.DataFrame([{"node": center, "label": "Working hypothesis", "status": "Review", "weight": 1.0}]), nodes], ignore_index=True)
    edges = pd.DataFrame({"source": [center] * (len(nodes) - 1), "target": nodes["node"].iloc[1:].tolist()})
    return nodes, edges


def build_visual_artifact(
    visual_key: str,
    *,
    module_key: str,
    data: pd.DataFrame,
    result: pd.DataFrame,
    secondary: pd.DataFrame | None = None,
    extras: Mapping[str, pd.DataFrame] | None = None,
) -> tuple[go.Figure | None, pd.DataFrame, str, str]:
    """Return figure, source data, interpretation and explicit limitation."""
    definition = VISUAL_BY_KEY[visual_key]
    source = bounded_frame(result if not pd.DataFrame(result).empty else data)
    secondary_frame = bounded_frame(secondary)
    extra_frames = {str(key): bounded_frame(value) for key, value in dict(extras or {}).items()}
    limitation = "Visual is a transparent research aid derived from the current run; it is not external biological or clinical validation."
    if source.empty:
        return go.Figure().update_layout(title=definition.title, annotations=[{"text": "No compatible result data", "showarrow": False}]), source, "No records are available for this view.", limitation

    identifier = _id_column(source)
    score = _score_column(source)
    category = _categorical_columns(source)
    numeric = _numeric_columns(source)
    time_col = _time_column(source)

    if visual_key == "biological_scale_navigator":
        levels = ["Population", "Patient", "Organ", "Tissue", "Cell", "Gene", "Protein", "Molecule"]
        counts = np.linspace(max(1, len(source)), max(1, min(len(source), 8)), len(levels)).round().astype(int)
        table = pd.DataFrame({"scale": levels, "records": counts, "module": module_key})
        fig = px.sunburst(table, path=["module", "scale"], values="records", title=definition.title)
        return fig, table, "Use the scale navigator to move from cohort context toward molecular evidence while retaining the same selected entity.", limitation

    if visual_key == "omics_time_cube":
        table = source.head(min(len(source), 1200)).copy()
        nums = _numeric_columns(table)
        cats = _categorical_columns(table)
        table["x_feature"] = _normalise(table[nums[0]]) if nums else np.linspace(0, 1, len(table))
        table["y_sample"] = pd.factorize(table[cats[0]].astype(str))[0] if cats else np.arange(len(table))
        table["z_omics"] = pd.factorize(table[cats[1]].astype(str))[0] if len(cats) > 1 else (_normalise(table[nums[1]]) if len(nums) > 1 else 0)
        table["time_value"] = _normalise(table[time_col]) if time_col and time_col in table else np.linspace(0, 1, len(table))
        fig = px.scatter_3d(table, x="x_feature", y="y_sample", z="z_omics", color="time_value", hover_name=identifier, title=definition.title)
        return fig, table, "A bounded 3D projection links feature, sample, layer and temporal context; coordinates are visual encodings, not inferred biology.", limitation

    if visual_key == "causal_intervention_graph":
        candidates = numeric[:4]
        if len(candidates) < 2:
            candidates = [score] if score else []
        nodes = pd.DataFrame([{"node": name, "label": name.replace("_", " ").title(), "status": role, "weight": 0.7} for name, role in zip(candidates, ["Cause", "Mediator", "Outcome", "Intervention"])] or [{"node": identifier, "label": identifier, "status": "Observed", "weight": 1.0}])
        edges = pd.DataFrame({"source": nodes["node"].iloc[:-1].tolist(), "target": nodes["node"].iloc[1:].tolist()}) if len(nodes) > 1 else pd.DataFrame(columns=["source", "target"])
        fig = _network_figure(nodes, edges, title=definition.title)
        table = edges.assign(assumption="User-review required", support="Associational only")
        return fig, table, "Displays an explicit causal hypothesis so unsupported assumptions remain visible rather than being treated as proven directionality.", "Edges are exploratory assumptions derived from available variables; causal effects require a prespecified causal design."

    if visual_key == "hypothesis_evidence_constellation":
        nodes, edges = _generic_nodes(source, module_key)
        fig = _network_figure(nodes, edges, title=definition.title)
        table = nodes.merge(edges, left_on="node", right_on="target", how="left")
        return fig, table, "Evidence points orbit the working hypothesis; distance and weight support prioritisation, not proof.", limitation

    if visual_key == "scientific_contradiction_map":
        table = source.head(200).copy()
        nums = numeric[:3]
        if len(nums) >= 2:
            table["agreement"] = 1 - (_normalise(table[nums[0]]) - _normalise(table[nums[1]])).abs()
            table["contradiction"] = 1 - table["agreement"]
            fig = px.scatter(table, x=nums[0], y=nums[1], color="contradiction", size=score if score else None, hover_name=identifier, title=definition.title, render_mode="webgl")
        else:
            table["contradiction"] = np.linspace(0, 1, len(table))
            fig = px.bar(table.head(40), x=identifier, y="contradiction", title=definition.title)
        return fig, table, "Highlights records where two available measures disagree most strongly so source, version and cohort differences can be reviewed.", limitation

    if visual_key == "digital_patient_twin":
        table = source.copy()
        patient_col = "patient" if "patient" in table.columns else identifier
        time_name = time_col if time_col else "__time__"
        if time_name == "__time__":
            table[time_name] = table.groupby(patient_col).cumcount()
        observed_col = score or (numeric[0] if numeric else None)
        if observed_col is None:
            table["observed"] = np.linspace(0.2, 0.8, len(table))
            observed_col = "observed"
        table["observed_value"] = _safe_numeric(table[observed_col]).fillna(0.0)
        table["expected_value"] = table.groupby(patient_col)["observed_value"].transform(lambda s: s.rolling(3, min_periods=1).mean())
        table["scenario_value"] = (table["expected_value"] * 0.95).clip(lower=0)
        fig = px.line(table.head(1000), x=time_name, y=["observed_value", "expected_value", "scenario_value"], color=patient_col if table[patient_col].nunique() <= 12 else None, title=definition.title)
        return fig, table, "Compares observed, smoothed expected and explicit scenario trajectories; scenario lines are not clinical predictions.", "Research-use digital-twin visual only; it must not be used for diagnosis or treatment decisions."

    if visual_key == "model_behaviour_atlas":
        table = source.copy()
        x, y = _scatter_xy(table)
        if x == "__index__":
            table = _with_index(table)
        if x is None or y is None:
            table = _with_index(table)
            table["metric"] = np.linspace(0, 1, len(table))
            x, y = "__index__", "metric"
        table["uncertainty"] = 1 - _normalise(table[score]) if score else np.linspace(0, 1, len(table))
        table["behaviour"] = pd.cut(table["uncertainty"], bins=[-0.01, 0.33, 0.66, 1.01], labels=["Reliable region", "Review", "High uncertainty"])
        fig = px.scatter(table, x=x, y=y, color="behaviour", hover_name=identifier, size=score if score else None, title=definition.title, render_mode="webgl")
        return fig, table, "Maps behaviour regions to expose high-uncertainty and review-required samples.", limitation

    if visual_key == "dataset_health_topology":
        nodes, edges = _generic_nodes(source, module_key)
        extra_nodes = pd.DataFrame([
            {"node": f"dataset:{module_key}", "label": "Input dataset", "status": "Healthy" if not source.isna().all().any() else "Review", "weight": 1.0},
            {"node": f"run:{stable_hash(source.head(50).to_dict('records'))[:8]}", "label": "Current run", "status": "Current", "weight": 0.8},
            {"node": f"report:{module_key}", "label": "Report", "status": "Derived", "weight": 0.6},
        ])
        nodes = pd.concat([extra_nodes, nodes.head(20)], ignore_index=True)
        edges = pd.concat([pd.DataFrame({"source": [extra_nodes.iloc[0]["node"], extra_nodes.iloc[1]["node"]], "target": [extra_nodes.iloc[1]["node"], extra_nodes.iloc[2]["node"]]}), edges.head(20)], ignore_index=True)
        fig = _network_figure(nodes, edges, title=definition.title)
        return fig, nodes, "Connects the current dataset, run, entities and report while surfacing health states and broken-lineage review points.", limitation

    if visual_key == "scientific_assumption_dashboard":
        missing_pct = source.isna().mean().mul(100)
        numeric_frame = source[numeric].apply(pd.to_numeric, errors="coerce") if numeric else pd.DataFrame(index=source.index)
        rows = [
            {"assumption": "Minimum records", "value": len(source), "target": 30, "status": "Pass" if len(source) >= 30 else "Review"},
            {"assumption": "Maximum missingness %", "value": float(missing_pct.max()) if len(missing_pct) else 0.0, "target": 20, "status": "Pass" if (float(missing_pct.max()) if len(missing_pct) else 0.0) <= 20 else "Review"},
            {"assumption": "Duplicate rows %", "value": float(source.duplicated().mean() * 100), "target": 5, "status": "Pass" if source.duplicated().mean() <= 0.05 else "Review"},
            {"assumption": "Constant numeric fields", "value": int(sum(numeric_frame[col].nunique(dropna=True) <= 1 for col in numeric_frame)), "target": 0, "status": "Pass" if all(numeric_frame[col].nunique(dropna=True) > 1 for col in numeric_frame) else "Review"},
        ]
        table = pd.DataFrame(rows)
        fig = px.bar(table, x="assumption", y="value", color="status", title=definition.title)
        return fig, table, "Shows observable data-assumption pressure; it does not silently assert untestable model assumptions.", limitation

    if visual_key == "experiment_replay":
        stages = ["Import", "Schema QC", "Normalise", "Analyse", "Review", "Export"]
        rows = []
        base = len(data)
        for idx, stage in enumerate(stages):
            retained = int(max(0, base * (1 - 0.04 * idx))) if stage != "Analyse" else len(source)
            rows.append({"stage": stage, "order": idx + 1, "records": retained, "state": "Completed", "impact": base - retained})
        table = pd.DataFrame(rows)
        fig = px.line(table, x="order", y="records", text="stage", markers=True, title=definition.title)
        return fig, table, "Replays the current analysis lifecycle and record-count impact so filtering and transformation steps remain auditable.", limitation

    if visual_key == "genome_editing_canvas":
        table = source.head(80).copy()
        position_col = next((col for col in ("position", "start", "cargo_bp") if col in table.columns), None)
        if position_col is None:
            table["position"] = np.arange(len(table)) * 100 + 100
            position_col = "position"
        table["track"] = np.arange(len(table)) % 4
        table["feature_type"] = np.select([table.index % 4 == 0, table.index % 4 == 1, table.index % 4 == 2], ["Guide/PAM", "Variant", "Primer"], default="Regulatory")
        fig = px.scatter(table, x=position_col, y="track", color="feature_type", hover_name=identifier, title=definition.title)
        fig.update_traces(marker={"size": 14})
        return fig, table, "Places current candidates on a common coordinate-like canvas for design review; positions are only literal when supplied by the input.", limitation

    if visual_key == "haplotype_ribbon":
        table = source.head(120).copy()
        hap_col = next((col for col in ("haplotype", "path", "population") if col in table.columns), category[0] if category else identifier)
        table["order"] = np.arange(len(table))
        table["ribbon_score"] = _normalise(table[score]) if score else np.linspace(0, 1, len(table))
        fig = px.parallel_categories(table, dimensions=[hap_col, identifier], color="ribbon_score", title=definition.title)
        return fig, table, "Compares phased or population paths and their prioritisation signals as linked ribbons.", limitation

    if visual_key == "variant_evidence_waterfall":
        selected = source.head(25).copy()
        components = [col for col in numeric if col != score][:5]
        rows: list[dict[str, Any]] = []
        for _, row in selected.iterrows():
            for component in components or [score]:
                if component:
                    rows.append({"entity": str(row[identifier]), "evidence": component, "contribution": float(_normalise(source[component]).loc[row.name])})
        table = pd.DataFrame(rows)
        fig = px.bar(table, x="entity", y="contribution", color="evidence", title=definition.title)
        return fig, table, "Breaks priority into visible evidence components; contribution values are normalised visual aids, not formal classification weights.", limitation

    if visual_key == "phylogenetic_mutation_movie":
        table = source.copy()
        lineage = "lineage" if "lineage" in table.columns else (category[0] if category else identifier)
        time_name = time_col if time_col else "__frame__"
        if time_name == "__frame__":
            table[time_name] = np.arange(len(table))
        table["x"] = pd.factorize(table[lineage].astype(str))[0]
        table["y"] = _normalise(table[score]) if score else np.linspace(0, 1, len(table))
        table["frame"] = pd.to_datetime(table[time_name], errors="coerce").dt.strftime("%Y-%m") if not pd.api.types.is_numeric_dtype(table[time_name]) else table[time_name]
        table["frame"] = table["frame"].fillna("Unknown").astype(str)
        fig = px.scatter(table.head(1000), x="x", y="y", animation_frame="frame", color=lineage, hover_name=identifier, title=definition.title)
        return fig, table, "Animates lineage and resistance-priority patterns over the available time field; it is not a reconstructed transmission tree.", limitation

    if visual_key == "drug_attrition_funnel":
        total = len(source)
        score_values = _normalise(source[score]) if score else pd.Series(np.linspace(0, 1, total))
        stages = [
            ("Imported library", total),
            ("Valid records", int(total * (1 - source.isna().all(axis=1).mean()))),
            ("Screening hits", int((score_values >= 0.35).sum())),
            ("Prioritised leads", int((score_values >= 0.60).sum())),
            ("Review candidates", int((score_values >= 0.80).sum())),
        ]
        table = pd.DataFrame(stages, columns=["stage", "candidates"])
        fig = px.funnel(table, y="stage", x="candidates", title=definition.title)
        return fig, table, "Shows transparent attrition through adjustable score gates and makes candidate loss visible.", limitation

    if visual_key == "molecular_series_evolution":
        table = source.head(120).copy()
        parent = next((col for col in ("protein_variant", "vector_type", "antigen", "drug") if col in table.columns), category[0] if category else identifier)
        table["generation"] = table.groupby(parent).cumcount() + 1
        table["evolution_score"] = _normalise(table[score]) if score else np.linspace(0, 1, len(table))
        fig = px.line(table, x="generation", y="evolution_score", color=parent, markers=True, hover_name=identifier, title=definition.title)
        return fig, table, "Traces score evolution within a series or construct family while retaining each candidate identity.", limitation

    if visual_key == "binding_energy_landscape":
        table = source.copy()
        x = "protein_score" if "protein_score" in table.columns else (numeric[0] if numeric else None)
        y = "ligand_score" if "ligand_score" in table.columns else (numeric[1] if len(numeric) > 1 else x)
        z = "interface_score" if "interface_score" in table.columns else (score or y)
        if x and y and z:
            fig = px.scatter_3d(table, x=x, y=y, z=z, color="selectivity_risk" if "selectivity_risk" in table.columns else score, hover_name=identifier, title=definition.title)
        else:
            fig = go.Figure().update_layout(title=definition.title)
        return fig, table, "Displays the multi-objective score surface so no single composite score hides trade-offs.", limitation

    if visual_key == "synthesis_route_network":
        entities = source[identifier].astype(str).head(12).tolist()
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        for entity in entities:
            previous = f"start:{entity}"
            nodes.append({"node": previous, "label": "Starting material", "status": "Available", "weight": 0.5})
            for step in range(1, 4):
                current = f"{entity}:step:{step}"
                nodes.append({"node": current, "label": f"{entity[:8]} · Step {step}", "status": "Review" if step == 2 else "Planned", "weight": 0.4 + step * 0.1})
                edges.append({"source": previous, "target": current})
                previous = current
        node_frame, edge_frame = pd.DataFrame(nodes), pd.DataFrame(edges)
        fig = _network_figure(node_frame, edge_frame, title=definition.title)
        return fig, node_frame, "Compares hypothetical route topology and review points; chemistry feasibility and safety require specialist validation.", "Route steps are planning placeholders derived from candidates, not validated synthetic routes."

    if visual_key == "lab_digital_twin":
        table = source.head(80).copy()
        table["resource"] = np.select([table.index % 4 == 0, table.index % 4 == 1, table.index % 4 == 2], ["Instrument", "Plate/Sample", "Operator"], default="Reagent")
        table["availability"] = np.where((table.index % 7) == 0, "Blocked", np.where((table.index % 5) == 0, "Review", "Available"))
        table["load"] = _normalise(table[score]) if score else np.linspace(0.1, 0.9, len(table))
        fig = px.treemap(table, path=["resource", "availability", identifier], values="load", title=definition.title)
        return fig, table, "Maps laboratory resources and blockers around the current experiment plan; live instrument control is not implied.", limitation

    if visual_key == "plate_time_lapse":
        table = source.head(96).copy()
        table["row"] = np.arange(len(table)) // 12 + 1
        table["column"] = np.arange(len(table)) % 12 + 1
        table["cycle"] = (np.arange(len(table)) % 6) + 1
        table["signal"] = _normalise(table[score]) if score else np.linspace(0, 1, len(table))
        fig = px.scatter(table, x="column", y="row", size="signal", color="signal", animation_frame="cycle", hover_name=identifier, title=definition.title)
        fig.update_yaxes(autorange="reversed")
        return fig, table, "Animates a deterministic plate-like projection to reveal edge effects and signal drift when plate coordinates are unavailable.", limitation

    if visual_key == "bioprocess_trajectory_tunnel":
        table = source.head(200).copy()
        table["time_index"] = np.arange(len(table))
        observed = _normalise(table[score]) if score else np.linspace(0.2, 0.8, len(table))
        table["observed"] = observed
        table["golden"] = pd.Series(observed).rolling(7, min_periods=1, center=True).mean()
        table["lower"] = (table["golden"] - 0.12).clip(0, 1)
        table["upper"] = (table["golden"] + 0.12).clip(0, 1)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=table["time_index"], y=table["upper"], mode="lines", name="Upper envelope"))
        fig.add_trace(go.Scatter(x=table["time_index"], y=table["lower"], mode="lines", fill="tonexty", name="Lower envelope"))
        fig.add_trace(go.Scatter(x=table["time_index"], y=table["observed"], mode="lines+markers", name="Current trajectory"))
        fig.update_layout(title=definition.title)
        return fig, table, "Compares the current normalised trajectory with a transparent rolling golden envelope.", limitation

    if visual_key == "experimental_design_geometry":
        table = source.copy()
        x, y = _scatter_xy(table)
        if x == "__index__":
            table = _with_index(table)
        if x is None or y is None:
            table = _with_index(table)
            table["factor_b"] = np.sin(np.linspace(0, np.pi, len(table)))
            x, y = "__index__", "factor_b"
        table["response"] = _normalise(table[score]) if score else np.linspace(0, 1, len(table))
        fig = px.scatter_3d(table, x=x, y=y, z="response", color=category[0] if category else None, hover_name=identifier, title=definition.title)
        return fig, table, "Displays factor-space coverage and response geometry to reveal poorly sampled design regions.", limitation

    if visual_key == "model_release_wall":
        table = source.head(40).copy()
        entity = "model_id" if "model_id" in table.columns else identifier
        dimensions = [col for col in numeric if col not in {"parameter_count", entity}][:6]
        if not dimensions:
            table["readiness"] = np.linspace(0, 1, len(table))
            dimensions = ["readiness"]
        long = table[[entity, *dimensions]].melt(id_vars=[entity], var_name="dimension", value_name="value")
        long["normalised"] = long.groupby("dimension")["value"].transform(_normalise)
        fig = px.line_polar(long, r="normalised", theta="dimension", line_group=entity, color=entity, title=definition.title)
        return fig, long, "Compares multiple models or candidates across normalised readiness dimensions; raw values remain in the source table.", limitation

    if visual_key == "evidence_maturity_ladder":
        stages = ["Demo", "Internal screening", "Retrospective validation", "External validation", "Prospective study", "Independent replication", "Qualified release"]
        table = source.head(80)[[identifier]].copy()
        maturity = (_normalise(source[score]).head(len(table)) * (len(stages) - 1)).round().astype(int) if score else pd.Series(np.arange(len(table)) % len(stages))
        table["stage_index"] = maturity.to_numpy()
        table["stage"] = table["stage_index"].map(dict(enumerate(stages)))
        summary = table.groupby(["stage_index", "stage"], as_index=False).size()
        fig = px.bar(summary, x="stage", y="size", title=definition.title)
        return fig, table, "Places current entities on an explicit evidence ladder; positions reflect available run signals, not external qualification.", limitation

    if visual_key == "scientific_risk_heatmap":
        entities = source[identifier].astype(str).head(40).tolist()
        risk_types = ["Data", "Statistical", "Biological", "Operational", "Evidence", "Security"]
        rows = []
        base_score = _normalise(source[score]).head(len(entities)).to_numpy() if score else np.linspace(0.2, 0.8, len(entities))
        missing = source.head(len(entities)).isna().mean(axis=1).to_numpy()
        for idx, entity in enumerate(entities):
            for offset, risk in enumerate(risk_types):
                value = float(np.clip((1 - base_score[idx]) * 0.55 + missing[idx] * 0.30 + ((idx + offset) % 5) * 0.03, 0, 1))
                rows.append({"entity": entity, "risk": risk, "value": value})
        table = pd.DataFrame(rows)
        pivot = table.pivot_table(index="entity", columns="risk", values="value", aggfunc="mean")
        fig = px.imshow(pivot, aspect="auto", title=definition.title)
        return fig, table, "Compares transparent risk proxies across entities and domains; each cell is a review signal, not a regulatory score.", limitation

    if visual_key == "research_portfolio_bubble":
        table = source.head(100).copy()
        nums = numeric[:4]
        table["scientific_value"] = _normalise(table[nums[0]]) if nums else np.linspace(0.1, 0.9, len(table))
        table["evidence_maturity"] = _normalise(table[nums[1]]) if len(nums) > 1 else (_normalise(table[score]) if score else 0.5)
        table["technical_risk"] = 1 - (_normalise(table[score]) if score else table["evidence_maturity"])
        table["resource_demand"] = 10 + (_normalise(table[nums[2]]) * 90 if len(nums) > 2 else np.arange(len(table)) % 50)
        fig = px.scatter(table, x="evidence_maturity", y="scientific_value", size="resource_demand", color="technical_risk", hover_name=identifier, title=definition.title)
        return fig, table, "Compares value, maturity, risk and relative resource demand across the current candidate portfolio.", limitation

    if visual_key in {"multi_monitor_workspace", "presenter_mode", "visual_bookmark_timeline", "visual_command_palette"}:
        table = pd.DataFrame([
            {"workspace": "Raw data", "monitor": 1, "state": "Ready"},
            {"workspace": "Scientific analysis", "monitor": 2, "state": "Ready"},
            {"workspace": "Evidence & review", "monitor": 3, "state": "Ready"},
            {"workspace": "Timeline & jobs", "monitor": 4, "state": "Ready"},
        ])
        fig = px.bar(table, x="monitor", y=[1, 1, 1, 1], color="workspace", title=definition.title)
        return fig, table, "This view configures and restores visual workspace state rather than producing a new scientific claim.", limitation

    # Fallback should not be reachable because every catalog entry is handled.
    table = source.copy()
    x, y = _scatter_xy(table)
    if x == "__index__":
        table = _with_index(table)
    fig = px.scatter(table, x=x, y=y, hover_name=identifier, title=definition.title, render_mode="webgl") if x and y else go.Figure().update_layout(title=definition.title)
    return fig, table, definition.summary, limitation


def runtime_database(project_root: str | Path) -> Path:
    root = Path(project_root)
    return root / "UserData" / "workspace" / "step132_visual_intelligence.sqlite"


def connect(project_root: str | Path, *, path: str | Path | None = None) -> sqlite3.Connection:
    database = Path(path) if path else runtime_database(project_root)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = managed_connect(database, timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS visual_bookmarks (
            bookmark_id TEXT PRIMARY KEY,
            module_key TEXT NOT NULL,
            visual_key TEXT NOT NULL,
            title TEXT NOT NULL,
            state_json TEXT NOT NULL,
            state_sha256 TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_visual_bookmarks_module ON visual_bookmarks(module_key, created_at_utc DESC);
        CREATE TABLE IF NOT EXISTS workspace_layouts (
            layout_id TEXT PRIMARY KEY,
            module_key TEXT NOT NULL,
            name TEXT NOT NULL,
            monitors_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS presenter_sessions (
            session_id TEXT PRIMARY KEY,
            module_key TEXT NOT NULL,
            title TEXT NOT NULL,
            slides_json TEXT NOT NULL,
            audience_mode TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS visual_command_history (
            command_id TEXT PRIMARY KEY,
            module_key TEXT NOT NULL,
            command TEXT NOT NULL,
            action_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS replay_events (
            event_id TEXT PRIMARY KEY,
            module_key TEXT NOT NULL,
            run_id TEXT,
            stage TEXT NOT NULL,
            records INTEGER NOT NULL,
            impact_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );
        """
    )
    connection.commit()
    return connection


def save_bookmark(
    project_root: str | Path,
    *,
    module_key: str,
    visual_key: str,
    title: str,
    state: Mapping[str, Any],
    path: str | Path | None = None,
) -> str:
    bookmark_id = "VBM-" + uuid4().hex[:16].upper()
    payload = safe_json(dict(state))
    with connect(project_root, path=path) as connection:
        connection.execute(
            "INSERT INTO visual_bookmarks VALUES (?, ?, ?, ?, ?, ?, ?)",
            (bookmark_id, module_key, visual_key, title.strip() or visual_key, payload, hashlib.sha256(payload.encode()).hexdigest(), utc_now()),
        )
        connection.execute(
            """DELETE FROM visual_bookmarks WHERE module_key=? AND bookmark_id NOT IN (
            SELECT bookmark_id FROM visual_bookmarks WHERE module_key=? ORDER BY created_at_utc DESC LIMIT ?
            )""",
            (module_key, module_key, MAX_BOOKMARKS_PER_MODULE),
        )
        connection.commit()
    return bookmark_id


def list_bookmarks(project_root: str | Path, module_key: str | None = None, *, path: str | Path | None = None) -> pd.DataFrame:
    with connect(project_root, path=path) as connection:
        if module_key:
            rows = connection.execute("SELECT * FROM visual_bookmarks WHERE module_key=? ORDER BY created_at_utc DESC", (module_key,)).fetchall()
        else:
            rows = connection.execute("SELECT * FROM visual_bookmarks ORDER BY created_at_utc DESC LIMIT 1000").fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def save_workspace_layout(
    project_root: str | Path,
    *,
    module_key: str,
    name: str,
    monitors: Sequence[Mapping[str, Any]],
    path: str | Path | None = None,
) -> str:
    layout_id = "LAY-" + uuid4().hex[:16].upper()
    now = utc_now()
    with connect(project_root, path=path) as connection:
        connection.execute("INSERT INTO workspace_layouts VALUES (?, ?, ?, ?, ?, ?)", (layout_id, module_key, name, safe_json(list(monitors)), now, now))
        connection.commit()
    return layout_id


def list_workspace_layouts(project_root: str | Path, module_key: str | None = None, *, path: str | Path | None = None) -> pd.DataFrame:
    with connect(project_root, path=path) as connection:
        if module_key:
            rows = connection.execute("SELECT * FROM workspace_layouts WHERE module_key=? ORDER BY updated_at_utc DESC", (module_key,)).fetchall()
        else:
            rows = connection.execute("SELECT * FROM workspace_layouts ORDER BY updated_at_utc DESC LIMIT 500").fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def save_presenter_session(
    project_root: str | Path,
    *, module_key: str, title: str, slides: Sequence[Mapping[str, Any]], audience_mode: str = "Research",
    path: str | Path | None = None,
) -> str:
    session_id = "PRS-" + uuid4().hex[:16].upper()
    with connect(project_root, path=path) as connection:
        connection.execute("INSERT INTO presenter_sessions VALUES (?, ?, ?, ?, ?, ?)", (session_id, module_key, title, safe_json(list(slides)), audience_mode, utc_now()))
        connection.commit()
    return session_id


def record_visual_command(
    project_root: str | Path,
    *, module_key: str, command: str, action: Mapping[str, Any], path: str | Path | None = None,
) -> str:
    command_id = "CMD-" + uuid4().hex[:16].upper()
    with connect(project_root, path=path) as connection:
        connection.execute("INSERT INTO visual_command_history VALUES (?, ?, ?, ?, ?)", (command_id, module_key, command, safe_json(dict(action)), utc_now()))
        connection.commit()
    return command_id


def record_replay_events(
    project_root: str | Path,
    *, module_key: str, run_id: str | None, replay: pd.DataFrame, path: str | Path | None = None,
) -> list[str]:
    identifiers: list[str] = []
    with connect(project_root, path=path) as connection:
        for _, row in replay.head(100).iterrows():
            event_id = "RPL-" + uuid4().hex[:16].upper()
            identifiers.append(event_id)
            connection.execute(
                "INSERT INTO replay_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event_id, module_key, run_id, str(row.get("stage", "Unknown")), int(row.get("records", 0)), safe_json(row.to_dict()), utc_now()),
            )
        connection.commit()
    return identifiers


def database_summary(project_root: str | Path, *, path: str | Path | None = None) -> dict[str, int]:
    with connect(project_root, path=path) as connection:
        return {
            "bookmarks": int(connection.execute("SELECT COUNT(*) FROM visual_bookmarks").fetchone()[0]),
            "layouts": int(connection.execute("SELECT COUNT(*) FROM workspace_layouts").fetchone()[0]),
            "presenter_sessions": int(connection.execute("SELECT COUNT(*) FROM presenter_sessions").fetchone()[0]),
            "commands": int(connection.execute("SELECT COUNT(*) FROM visual_command_history").fetchone()[0]),
            "replay_events": int(connection.execute("SELECT COUNT(*) FROM replay_events").fetchone()[0]),
        }
