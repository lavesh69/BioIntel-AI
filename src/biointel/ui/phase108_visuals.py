from __future__ import annotations

import json
import math
import sqlite3
from biointel.database.core import managed_connect
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from biointel.ui.components import scientific_chart_card

VisualResult = tuple[go.Figure, pd.DataFrame, str, str, str]

PHASE108_VISUAL_TITLES: dict[str, tuple[str, ...]] = {
    "clinical_validation": (
        "Clinical evidence pyramid",
        "Validation cohort flow",
        "Endpoint forest plot",
        "Quality-risk matrix",
        "Validation record coverage",
    ),
    "external_validation": (
        "External performance summary",
        "Feature-drift ranking",
        "Calibration or agreement",
        "Error and confidence distribution",
        "Validation data-quality funnel",
    ),
    "benchmark_leakage": (
        "Leakage overlap profile",
        "Leakage-risk matrix",
        "Unique-entity retention",
        "Release decision gauge",
        "Train and test composition",
    ),
    "dti_validation": (
        "Implementation versus evidence",
        "Evidence-gap heatmap",
        "Qualification status composition",
        "Capability gap ranking",
        "Validation milestone funnel",
    ),
    "data_readiness": (
        "Metadata versus scientific readiness",
        "Dataset readiness matrix",
        "Readiness blocker profile",
        "Dataset lineage coverage",
        "Provider data coverage",
    ),
    "model_evaluation": (
        "Model metric comparison",
        "Validation-to-test agreement",
        "Generalisation delta heatmap",
        "Data support versus performance",
        "Model provenance composition",
    ),
    "experiment_registry": (
        "Experiment performance leaderboard",
        "Cross-validation stability",
        "Hyperparameter search landscape",
        "Runtime versus performance",
        "Validation requirement status",
    ),
    "dataset_registry": (
        "Logical versus physical datasets",
        "Dataset lineage network",
        "Schema and QC coverage",
        "Storage and format composition",
        "Readiness issue matrix",
    ),
    "knowledge_graph": (
        "Evidence-confidence distribution",
        "Relationship type composition",
        "Citation coverage by relation",
        "Conflict and research-gap profile",
        "Entity-type connectivity",
    ),
    "evidence_package": (
        "Package readiness profile",
        "Evidence file composition",
        "Claim-to-artifact coverage",
        "Integrity and completeness matrix",
        "Package blocker ranking",
    ),
    "governance": (
        "Governance control matrix",
        "Project risk heatmap",
        "Open findings trend",
        "Approval and review timeline",
        "Compliance coverage profile",
    ),
    "release_gate": (
        "Release gate waterfall",
        "Blocker severity profile",
        "Validation evidence matrix",
        "Readiness scorecard",
        "Required versus available evidence",
    ),
    "provider_integration": (
        "Provider connection health",
        "Provider latency and availability",
        "Query and record activity",
        "Failure-type distribution",
        "Provider coverage matrix",
    ),
    "reference_manager": (
        "Reference storage profile",
        "Release and version timeline",
        "Reference integrity matrix",
        "Asset lifecycle events",
        "Compatibility and activation status",
    ),
}


def _empty(title: str, reason: str) -> VisualResult:
    fig = go.Figure()
    fig.add_annotation(
        text=reason,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"size": 16},
        align="center",
    )
    fig.update_layout(title=title, height=430, xaxis={"visible": False}, yaxis={"visible": False})
    return fig, pd.DataFrame([{"status": "No data", "reason": reason}]), reason, "No-data safe state", ""


def _df(value: Any) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, list):
        try:
            return pd.DataFrame(value)
        except Exception:
            return pd.DataFrame()
    if isinstance(value, tuple):
        try:
            return pd.DataFrame(list(value))
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _safe_ratio(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return float(numerator) / float(denominator)


@st.cache_data(ttl=60, show_spinner=False)
def _read_sql_cached(path_text: str, mtime_ns: int, query: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    del mtime_ns
    path = Path(path_text)
    if not path.is_file():
        return pd.DataFrame()
    try:
        with managed_connect(path) as connection:
            return pd.read_sql_query(query, connection, params=params)
    except (sqlite3.Error, pd.errors.DatabaseError):
        return pd.DataFrame()


def _read_sql(root: Path, relative: str, query: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    path = root / relative
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        stamp = 0
    return _read_sql_cached(str(path), stamp, query, params)


def _bar(frame: pd.DataFrame, x: str, y: str, title: str, *, color: str | None = None, orientation: str = "v", barmode: str = "group") -> go.Figure:
    kwargs: dict[str, Any] = {"data_frame": frame, "x": x, "y": y, "title": title, "orientation": orientation, "barmode": barmode}
    if color and color in frame.columns:
        kwargs["color"] = color
    fig = px.bar(**kwargs)
    fig.update_layout(legend_title_text="")
    return fig


def _heatmap(matrix: pd.DataFrame, title: str, *, zmin: float | None = None, zmax: float | None = None, text_auto: str | bool = ".1f") -> go.Figure:
    fig = px.imshow(matrix, aspect="auto", title=title, zmin=zmin, zmax=zmax, text_auto=text_auto)
    fig.update_layout(coloraxis_colorbar_title="Value")
    return fig


def _radar(frame: pd.DataFrame, label_col: str, value_col: str, title: str, max_value: float = 100.0) -> go.Figure:
    data = frame[[label_col, value_col]].copy()
    data[value_col] = _numeric(data[value_col]).fillna(0).clip(lower=0, upper=max_value)
    theta = data[label_col].astype(str).tolist()
    values = data[value_col].tolist()
    if theta:
        theta.append(theta[0])
        values.append(values[0])
    fig = go.Figure(go.Scatterpolar(r=values, theta=theta, fill="toself", name="Coverage"))
    fig.update_layout(title=title, polar={"radialaxis": {"visible": True, "range": [0, max_value]}}, showlegend=False, height=520)
    return fig


def _forest(frame: pd.DataFrame, title: str) -> go.Figure:
    data = frame.copy()
    data["metric_value"] = _numeric(data.get("metric_value", pd.Series(dtype=float)))
    data["lower_ci"] = _numeric(data.get("lower_ci", data["metric_value"]))
    data["upper_ci"] = _numeric(data.get("upper_ci", data["metric_value"]))
    data = data.dropna(subset=["metric_value"]).head(60)
    labels = data.get("metric_name", pd.Series(range(len(data)))).astype(str)
    error_plus = (data["upper_ci"].fillna(data["metric_value"]) - data["metric_value"]).clip(lower=0)
    error_minus = (data["metric_value"] - data["lower_ci"].fillna(data["metric_value"])).clip(lower=0)
    fig = go.Figure(
        go.Scatter(
            x=data["metric_value"],
            y=labels,
            mode="markers",
            error_x={"type": "data", "array": error_plus, "arrayminus": error_minus},
            marker={"size": 10},
            text=data.get("result_scope", ""),
            hovertemplate="%{y}: %{x:.3f}<extra></extra>",
        )
    )
    fig.update_layout(title=title, height=max(430, 50 + len(data) * 28), xaxis_title="Metric value", yaxis_title="Endpoint")
    return fig


def _clinical_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    from .phase108_visual_builders_core import _clinical_visual as implementation
    return implementation(index, root, context)


def _external_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    from .phase108_visual_builders_core import _external_visual as implementation
    return implementation(index, root, context)


def _leakage_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    from .phase108_visual_builders_core import _leakage_visual as implementation
    return implementation(index, root, context)


def _dti_validation_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    from .phase108_visual_builders_core import _dti_validation_visual as implementation
    return implementation(index, root, context)


def _data_readiness_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    from .phase108_visual_builders_core import _data_readiness_visual as implementation
    return implementation(index, root, context)


def _model_evaluation_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    from .phase108_visual_builders_core import _model_evaluation_visual as implementation
    return implementation(index, root, context)


def _experiment_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    db = "reports/experiments.sqlite3"
    experiments = _df(context.get("display"))
    if experiments.empty:
        experiments = _read_sql(root, db, "SELECT * FROM experiments ORDER BY trained_at_utc")
    if index == 0:
        rows: list[dict[str, Any]] = []
        for _, row in experiments.iterrows():
            metrics = _json_dict(row.get("metrics_json"))
            for key, value in metrics.items():
                if isinstance(value, (int, float)) and value is not None:
                    rows.append({"experiment_id": row.get("experiment_id"), "model_name": row.get("model_name"), "metric": key, "value": value, "synthetic_demo": row.get("synthetic_demo")})
        data = pd.DataFrame(rows)
        if data.empty:
            return _empty(PHASE108_VISUAL_TITLES["experiment_registry"][index], "No numeric final-test metrics are registered.")
        fig = _bar(data, "metric", "value", "Experiment performance leaderboard", color="model_name")
        return fig, data, "Compares final-test metrics stored for registered experiments.", "Experiment registry metrics", "Metric-specific"
    if index == 1:
        folds = _read_sql(root, db, "SELECT experiment_id,fold_index,metrics_json FROM experiment_folds ORDER BY experiment_id,fold_index")
        rows = []
        for _, row in folds.iterrows():
            for key, value in _json_dict(row.get("metrics_json")).items():
                if isinstance(value, (int, float)) and value is not None:
                    rows.append({"experiment_id": row["experiment_id"], "fold": row["fold_index"], "metric": key, "value": value})
        data = pd.DataFrame(rows)
        if data.empty:
            return _empty(PHASE108_VISUAL_TITLES["experiment_registry"][index], "No fold-level numeric metrics are available.")
        fig = px.box(data, x="metric", y="value", color="experiment_id", points="all", title="Cross-validation stability")
        return fig, data, "Shows fold-to-fold performance spread and unstable experiments.", "Cross-validation fold distribution", "Metric-specific"
    if index == 2:
        data = _read_sql(root, db, "SELECT experiment_id,trial_number,objective_name,objective_value,state,duration_seconds FROM hyperparameter_trials ORDER BY experiment_id,trial_number")
        if data.empty:
            return _empty(PHASE108_VISUAL_TITLES["experiment_registry"][index], "No hyperparameter trials are registered.")
        data["objective_value"] = _numeric(data["objective_value"])
        data["duration_seconds"] = _numeric(data["duration_seconds"])
        fig = px.scatter(data, x="trial_number", y="objective_value", color="experiment_id", size="duration_seconds", symbol="state", hover_data=["objective_name"], title="Hyperparameter search landscape")
        return fig, data, "Shows optimisation progress, failed trials and time cost across experiments.", "Hyperparameter trial registry", "Objective value"
    if index == 3:
        runtime = _read_sql(root, db, "SELECT experiment_id,metric_name,metric_value,unit FROM experiment_runtime_metrics")
        perf_rows = []
        for _, row in experiments.iterrows():
            metrics = _json_dict(row.get("metrics_json"))
            preferred = next((metrics[k] for k in metrics if isinstance(metrics[k], (int, float)) and any(t in k.lower() for t in ("roc", "accuracy", "f1", "r2", "balanced"))), None)
            if preferred is not None:
                perf_rows.append({"experiment_id": row.get("experiment_id"), "performance": preferred})
        perf = pd.DataFrame(perf_rows)
        if runtime.empty or perf.empty:
            return _empty(PHASE108_VISUAL_TITLES["experiment_registry"][index], "Runtime metrics or comparable model performance are unavailable.")
        time_metric = runtime[runtime["metric_name"].astype(str).str.contains("time|duration", case=False, regex=True)].copy()
        if time_metric.empty:
            time_metric = runtime.groupby("experiment_id", as_index=False)["metric_value"].sum()
        else:
            time_metric = time_metric.groupby("experiment_id", as_index=False)["metric_value"].sum()
        data = perf.merge(time_metric, on="experiment_id", how="inner").rename(columns={"metric_value": "runtime"})
        fig = px.scatter(data, x="runtime", y="performance", hover_name="experiment_id", title="Runtime versus final performance")
        return fig, data, "Highlights experiments with favourable performance-to-runtime trade-offs.", "Registered runtime and final metrics", "Runtime / metric"
    data = _read_sql(root, db, "SELECT status,requirement_label,COUNT(*) AS requirements FROM experiment_validation_requirements GROUP BY status,requirement_label")
    if data.empty:
        return _empty(PHASE108_VISUAL_TITLES["experiment_registry"][index], "No validation requirements are registered.")
    matrix = data.pivot_table(index="requirement_label", columns="status", values="requirements", aggfunc="sum", fill_value=0)
    fig = _heatmap(matrix, "Experiment validation requirement status", text_auto=".0f")
    return fig, matrix.reset_index(), "Shows which scientific requirements are passed, pending or blocked across experiments.", "Validation requirement counts", "Requirements"


def _dataset_registry_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    db = "reports/datasets.sqlite3"
    if index == 0:
        logical = _read_sql(root, db, "SELECT COUNT(*) AS logical_datasets,COUNT(DISTINCT dataset_sha256) AS unique_logical FROM datasets")
        physical = _read_sql(root, db, "SELECT COUNT(*) AS physical_assets,COUNT(DISTINCT asset_sha256) AS unique_physical FROM physical_data_assets")
        aliases = _read_sql(root, db, "SELECT COUNT(*) AS aliases FROM dataset_aliases")
        data = pd.DataFrame({"asset_type": ["Logical dataset versions", "Physical data assets", "Aliases"], "count": [int(logical.get("logical_datasets", pd.Series([0])).iloc[0]) if not logical.empty else 0, int(physical.get("physical_assets", pd.Series([0])).iloc[0]) if not physical.empty else 0, int(aliases.get("aliases", pd.Series([0])).iloc[0]) if not aliases.empty else 0]})
        fig = _bar(data, "asset_type", "count", "Logical versus physical dataset inventory")
        return fig, data, "Separates logical registry versions from unique physical data assets and aliases.", "Dataset registry inventory", "Records"
    if index == 1:
        data = _read_sql(root, db, "SELECT source_dataset_sha256,target_dataset_sha256,relation_type FROM dataset_links LIMIT 1000")
        if data.empty:
            return _empty(PHASE108_VISUAL_TITLES["dataset_registry"][index], "No dataset lineage relationships are registered.")
        nodes = sorted(set(data["source_dataset_sha256"]).union(data["target_dataset_sha256"]))
        node_index = {node: i for i, node in enumerate(nodes)}
        relation_counts = data.groupby(["source_dataset_sha256", "target_dataset_sha256", "relation_type"], as_index=False).size().rename(columns={"size": "weight"})
        fig = go.Figure(go.Sankey(node={"label": [n[:10] + "…" for n in nodes]}, link={"source": [node_index[s] for s in relation_counts["source_dataset_sha256"]], "target": [node_index[t] for t in relation_counts["target_dataset_sha256"]], "value": relation_counts["weight"], "label": relation_counts["relation_type"]}))
        fig.update_layout(title="Dataset lineage and relationship flow", height=540)
        return fig, relation_counts, "Shows registered parent, derived and scientific relationships between dataset versions.", "Dataset link registry", "Relationships"
    if index == 2:
        readiness = _read_sql(root, db, "SELECT d.dataset_name,r.file_count,r.column_count,r.sample_count,r.qc_count,r.provenance_count,r.readiness_score FROM datasets d JOIN dataset_readiness r USING(dataset_sha256)")
        if readiness.empty:
            return _empty(PHASE108_VISUAL_TITLES["dataset_registry"][index], "No dataset readiness records are available.")
        cols = ["file_count", "column_count", "sample_count", "qc_count", "provenance_count"]
        matrix = readiness.set_index("dataset_name")[cols].apply(pd.to_numeric, errors="coerce").fillna(0)
        matrix = (matrix > 0).astype(int) * 100
        fig = _heatmap(matrix.head(55), "Schema, sample, QC and provenance coverage", zmin=0, zmax=100, text_auto=".0f")
        return fig, matrix.reset_index(), "Shows whether each logical dataset has essential registry components.", "Dataset component presence", "% present"
    if index == 3:
        data = _read_sql(root, db, "SELECT file_format,COUNT(*) AS files,SUM(size_bytes) AS size_bytes FROM physical_data_assets GROUP BY file_format ORDER BY size_bytes DESC")
        if data.empty:
            return _empty(PHASE108_VISUAL_TITLES["dataset_registry"][index], "No physical data assets are registered.")
        fig = px.treemap(data, path=["file_format"], values="size_bytes", color="files", title="Physical dataset storage by format")
        return fig, data, "Shows which scientific file formats dominate local storage and asset counts.", "Physical data asset registry", "Bytes"
    data = _read_sql(root, db, "SELECT severity,category,resolution_status,COUNT(*) AS issues FROM dataset_validation_issues GROUP BY severity,category,resolution_status")
    if data.empty:
        return _empty(PHASE108_VISUAL_TITLES["dataset_registry"][index], "No dataset readiness issues are registered.")
    matrix = data.pivot_table(index="category", columns=["severity", "resolution_status"], values="issues", aggfunc="sum", fill_value=0)
    fig = _heatmap(matrix, "Dataset readiness issue matrix", text_auto=".0f")
    return fig, matrix.reset_index(), "Highlights unresolved or severe dataset registry and scientific-readiness issues.", "Validation issue counts", "Issues"


def _knowledge_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    nodes = _df(context.get("nodes"))
    edges = _df(context.get("filtered_edges"))
    conflicts = _df(context.get("conflicts"))
    gaps = _df(context.get("gaps"))
    if edges.empty:
        return _empty(PHASE108_VISUAL_TITLES["knowledge_graph"][index], "No evidence relationships are available after filtering.")
    if index == 0:
        if "evidence_score" not in edges.columns:
            return _empty(PHASE108_VISUAL_TITLES["knowledge_graph"][index], "Evidence scores are unavailable.")
        data = edges.copy(); data["evidence_score"] = _numeric(data["evidence_score"])
        fig = px.histogram(data.dropna(subset=["evidence_score"]), x="evidence_score", color="evidence_type" if "evidence_type" in data.columns else None, nbins=20, marginal="box", title="Evidence-confidence distribution")
        return fig, data, "Shows the confidence distribution and source-type mix of loaded relationships.", "Loaded graph evidence scores", "Score"
    if index == 1:
        relation_col = "relation" if "relation" in edges.columns else None
        if not relation_col:
            return _empty(PHASE108_VISUAL_TITLES["knowledge_graph"][index], "Relationship labels are unavailable.")
        data = edges.groupby(relation_col, as_index=False).size().rename(columns={"size": "relationships"}).sort_values("relationships", ascending=False).head(30)
        fig = _bar(data, relation_col, "relationships", "Biomedical relationship type composition")
        return fig, data, "Shows which relation types dominate the current knowledge graph.", "Graph relation counts", "Relationships"
    if index == 2:
        if "relation" not in edges.columns or "citation" not in edges.columns:
            return _empty(PHASE108_VISUAL_TITLES["knowledge_graph"][index], "Citation or relationship fields are unavailable.")
        data = edges.copy(); data["has_citation"] = data["citation"].astype(str).str.strip().ne("")
        coverage = data.groupby("relation", as_index=False).agg(relationships=("relation", "size"), citation_coverage=("has_citation", "mean"))
        coverage["citation_coverage"] *= 100
        fig = px.scatter(coverage, x="relationships", y="citation_coverage", size="relationships", hover_name="relation", title="Citation coverage by relationship type")
        fig.update_yaxes(range=[0, 105])
        return fig, coverage, "Prioritises relation types with many edges but weak citation support.", "Citation presence by relation", "% cited"
    if index == 3:
        data = pd.DataFrame({"category": ["Conflicts", "Research gaps", "Unconnected entities"], "records": [len(conflicts), len(gaps[gaps.get("gap_score", pd.Series(dtype=float)).fillna(0) > 0]) if not gaps.empty else 0, int((gaps.get("degree", pd.Series(dtype=float)).fillna(0) == 0).sum()) if not gaps.empty else 0]})
        fig = _bar(data, "category", "records", "Graph conflicts and research-gap profile")
        return fig, data, "Shows curation pressure from conflicts, weak evidence and disconnected entities.", "Conflict and gap counts", "Records"
    if nodes.empty or not {"node", "type"}.issubset(nodes.columns):
        return _empty(PHASE108_VISUAL_TITLES["knowledge_graph"][index], "Node type data are unavailable.")
    degree = pd.concat([edges["source"], edges["target"]]).value_counts().rename_axis("node").reset_index(name="degree")
    data = nodes.merge(degree, on="node", how="left"); data["degree"] = data["degree"].fillna(0)
    summary = data.groupby("type", as_index=False).agg(entities=("node", "size"), mean_degree=("degree", "mean"), isolated=("degree", lambda s: int((s == 0).sum())))
    fig = px.scatter(summary, x="entities", y="mean_degree", size="isolated", hover_name="type", title="Entity-type connectivity")
    return fig, summary, "Shows entity classes with weak graph connectivity or many isolated records.", "Node degree by entity type", "Entities / degree"


def _evidence_package_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    prepared = context.get("prepared") or st.session_state.get("prepared_evidence_package")
    manifest = context.get("manifest") if isinstance(context.get("manifest"), dict) else {}
    readiness = context.get("readiness") if isinstance(context.get("readiness"), dict) else {}
    summary_obj = None
    if isinstance(prepared, dict):
        summary_obj = prepared.get("summary") or prepared.get("package_summary")
        manifest = prepared.get("manifest") or manifest
        readiness = prepared.get("readiness") or readiness
    if index == 0:
        criteria = _df(readiness.get("criteria"))
        if criteria.empty and summary_obj is not None:
            values = []
            for attr in ("readiness_score", "manifest_coverage", "integrity_score", "lineage_score", "governance_score"):
                if hasattr(summary_obj, attr):
                    values.append({"dimension": attr.replace("_", " ").title(), "score": float(getattr(summary_obj, attr))})
            criteria = pd.DataFrame(values)
        if criteria.empty:
            return _empty(PHASE108_VISUAL_TITLES["evidence_package"][index], "Prepare an evidence package to calculate readiness visuals.")
        label = next((c for c in ("label", "criterion", "name", "dimension") if c in criteria.columns), criteria.columns[0])
        score = next((c for c in ("score", "readiness_score", "value", "passed") if c in criteria.columns), None)
        if score is None:
            criteria["score"] = 0
            score = "score"
        criteria[score] = criteria[score].map(lambda v: 100 if v is True else 0 if v is False else v)
        fig = _radar(criteria.rename(columns={label: "dimension", score: "score"}), "dimension", "score", "Evidence package readiness profile")
        return fig, criteria, "Shows package readiness dimensions derived from the current manifest and control checks.", "Evidence package readiness criteria", "% / score"
    files = []
    if isinstance(manifest, dict):
        files = manifest.get("files") or manifest.get("artifacts") or []
    file_frame = _df(files)
    if index == 1:
        if file_frame.empty:
            return _empty(PHASE108_VISUAL_TITLES["evidence_package"][index], "No manifest files are available in the prepared package.")
        path_col = next((c for c in ("path", "relative_path", "file", "name") if c in file_frame.columns), None)
        if not path_col:
            return _empty(PHASE108_VISUAL_TITLES["evidence_package"][index], "Manifest file paths are unavailable.")
        data = file_frame.copy(); data["extension"] = data[path_col].astype(str).map(lambda v: Path(v).suffix.lower() or "[none]")
        data = data.groupby("extension", as_index=False).size().rename(columns={"size": "files"}).sort_values("files", ascending=False)
        fig = px.pie(data, names="extension", values="files", hole=0.5, title="Evidence package file composition")
        return fig, data, "Shows the evidence package mix by file type.", "Manifest file extension counts", "Files"
    if index == 2:
        criteria = _df(readiness.get("criteria"))
        if criteria.empty:
            return _empty(PHASE108_VISUAL_TITLES["evidence_package"][index], "No claim or criterion coverage data are available.")
        label = next((c for c in ("label", "criterion", "name") if c in criteria.columns), criteria.columns[0])
        status = next((c for c in ("status", "passed", "available") if c in criteria.columns), None)
        if not status:
            return _empty(PHASE108_VISUAL_TITLES["evidence_package"][index], "Criteria do not contain a coverage status field.")
        data = criteria[[label, status]].copy(); data["coverage"] = data[status].map(lambda v: 100 if str(v).lower() in {"true", "pass", "passed", "available", "complete"} or v is True else 0)
        fig = _bar(data, label, "coverage", "Claim-to-artifact coverage")
        fig.update_yaxes(range=[0, 105])
        return fig, data, "Shows whether each package claim or criterion has supporting evidence artifacts.", "Criterion coverage", "% covered"
    if index == 3:
        criteria = _df(readiness.get("criteria"))
        if criteria.empty:
            return _empty(PHASE108_VISUAL_TITLES["evidence_package"][index], "No integrity or completeness checks are available.")
        label = next((c for c in ("label", "criterion", "name") if c in criteria.columns), criteria.columns[0])
        status = next((c for c in ("status", "passed", "available") if c in criteria.columns), None)
        score = next((c for c in ("score", "value", "readiness_score") if c in criteria.columns), None)
        data = criteria.copy()
        if status:
            data["status_numeric"] = data[status].map(lambda v: 100 if str(v).lower() in {"true", "pass", "passed", "available", "complete"} or v is True else 0)
        elif score:
            data["status_numeric"] = _numeric(data[score]).fillna(0)
        else:
            data["status_numeric"] = 0
        matrix = data.set_index(label)[["status_numeric"]]
        fig = _heatmap(matrix, "Evidence package integrity and completeness", zmin=0, zmax=100, text_auto=".0f")
        return fig, data, "Shows the current status of package integrity, lineage and completeness controls.", "Package criterion status", "%"
    blockers = readiness.get("blockers") if isinstance(readiness, dict) else []
    if not blockers:
        criteria = _df(readiness.get("criteria"))
        if not criteria.empty:
            status_col = next((c for c in ("status", "passed", "available") if c in criteria.columns), None)
            label_col = next((c for c in ("label", "criterion", "name") if c in criteria.columns), criteria.columns[0])
            if status_col:
                mask = ~criteria[status_col].astype(str).str.lower().isin(["true", "pass", "passed", "available", "complete"])
                blockers = criteria.loc[mask, label_col].astype(str).tolist()
    data = pd.DataFrame({"blocker": [str(item) for item in blockers]})
    if data.empty:
        return _empty(PHASE108_VISUAL_TITLES["evidence_package"][index], "No package blockers are currently listed.")
    data = data.groupby("blocker", as_index=False).size().rename(columns={"size": "count"}).sort_values("count", ascending=False).head(25)
    fig = _bar(data, "count", "blocker", "Evidence package blockers", orientation="h")
    return fig, data, "Ranks missing or failed package criteria requiring action before handoff.", "Package blocker counts", "Blockers"


def _governance_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    db = "reports/projects.sqlite3"
    milestones = _df(context.get("milestone_table"))
    if milestones.empty:
        milestones = _read_sql(root, db, "SELECT * FROM project_milestones")
    decisions = _read_sql(root, db, "SELECT * FROM project_decisions")
    gates = _read_sql(root, db, "SELECT * FROM project_gates")
    projects = _read_sql(root, db, "SELECT * FROM projects")
    if index == 0:
        rows = []
        for name, frame, status_col in (("Milestones", milestones, "status"), ("Decisions", decisions, "status"), ("Release gates", gates, "status")):
            if not frame.empty and status_col in frame.columns:
                counts = frame[status_col].astype(str).value_counts()
                rows.extend({"control": name, "status": str(k), "records": int(v)} for k, v in counts.items())
        data = pd.DataFrame(rows)
        if data.empty:
            return _empty(PHASE108_VISUAL_TITLES["governance"][index], "No governance controls are registered.")
        matrix = data.pivot_table(index="control", columns="status", values="records", aggfunc="sum", fill_value=0)
        fig = _heatmap(matrix, "Governance control status matrix", text_auto=".0f")
        return fig, matrix.reset_index(), "Shows milestone, decision and gate status across the governance registry.", "Governance control counts", "Records"
    if index == 1:
        if projects.empty:
            return _empty(PHASE108_VISUAL_TITLES["governance"][index], "No projects are registered.")
        data = projects.copy()
        priority_map = {"critical": 5, "high": 4, "medium": 3, "normal": 3, "low": 2}
        status_risk = {"blocked": 5, "at risk": 4, "active": 3, "planned": 2, "completed": 1, "archived": 1}
        data["priority_score"] = data.get("priority", "normal").astype(str).str.lower().map(priority_map).fillna(3)
        data["status_risk"] = data.get("status", "active").astype(str).str.lower().map(status_risk).fillna(3)
        matrix = data.pivot_table(index="priority", columns="status", values="project_id", aggfunc="count", fill_value=0)
        fig = _heatmap(matrix, "Project governance risk heatmap", text_auto=".0f")
        return fig, matrix.reset_index(), "Shows how project priority and lifecycle status combine into governance workload.", "Project priority-status matrix", "Projects"
    if index == 2:
        events = _read_sql(root, db, "SELECT created_at_utc,event_type FROM project_events")
        if events.empty:
            return _empty(PHASE108_VISUAL_TITLES["governance"][index], "No project governance events are registered.")
        events["date"] = pd.to_datetime(events["created_at_utc"], errors="coerce", utc=True).dt.date
        data = events.dropna(subset=["date"]).groupby(["date", "event_type"], as_index=False).size().rename(columns={"size": "events"})
        fig = px.line(data, x="date", y="events", color="event_type", markers=True, title="Governance findings and events over time")
        return fig, data, "Shows the timing and type of governance activity, including potential open findings.", "Project event timeline", "Events"
    if index == 3:
        rows = []
        for source, frame, date_col in (("Decision", decisions, "decision_date"), ("Gate", gates, "decision_date"), ("Milestone", milestones, "due_date")):
            if frame.empty or date_col not in frame.columns:
                continue
            temp = frame.copy(); temp["date"] = pd.to_datetime(temp[date_col], errors="coerce")
            temp = temp.dropna(subset=["date"])
            temp["type"] = source
            temp["label"] = temp.get("title", temp.get("gate_name", temp.get("milestone_id", ""))).astype(str)
            rows.append(temp[["date", "type", "status", "label"]])
        data = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
        if data.empty:
            return _empty(PHASE108_VISUAL_TITLES["governance"][index], "No governance decision or review dates are available.")
        fig = px.scatter(data, x="date", y="type", color="status", hover_name="label", title="Approval and review timeline")
        return fig, data, "Shows when decisions, gates and milestones are due or completed.", "Governance timeline", "Date"
    rows = []
    for label, frame, status_col in (("Milestones", milestones, "status"), ("Decisions", decisions, "status"), ("Gates", gates, "status"), ("Projects", projects, "status")):
        total = len(frame)
        complete = int(frame[status_col].astype(str).str.lower().isin(["approved", "completed", "closed", "accepted", "done"]).sum()) if total and status_col in frame.columns else 0
        rows.append({"dimension": label, "coverage": 100 * _safe_ratio(complete, total), "records": total})
    data = pd.DataFrame(rows)
    fig = _radar(data, "dimension", "coverage", "Governance completion coverage")
    return fig, data, "Shows completion coverage across core governance record classes.", "Status-derived completion coverage", "% complete"


def _release_gate_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    result = context.get("result") or st.session_state.get("release_gate_result")
    if result is None:
        return _empty(PHASE108_VISUAL_TITLES["release_gate"][index], "Run the scientific release gate to generate this visual.")
    checks = _df(getattr(result, "checks", None) if not isinstance(result, dict) else result.get("checks"))
    blockers = getattr(result, "blockers", []) if not isinstance(result, dict) else result.get("blockers", [])
    score = float(getattr(result, "score", 0) if not isinstance(result, dict) else result.get("score", 0) or 0)
    passed = bool(getattr(result, "passed", False) if not isinstance(result, dict) else result.get("passed", False))
    if index == 0:
        if checks.empty:
            return _empty(PHASE108_VISUAL_TITLES["release_gate"][index], "Release gate checks are unavailable.")
        status_col = next((c for c in ("status", "passed", "result") if c in checks.columns), None)
        label_col = next((c for c in ("check", "label", "requirement", "name") if c in checks.columns), checks.columns[0])
        if not status_col:
            return _empty(PHASE108_VISUAL_TITLES["release_gate"][index], "Release checks do not expose status values.")
        data = checks[[label_col, status_col]].copy(); data["value"] = data[status_col].map(lambda v: 1 if str(v).lower() in {"true", "pass", "passed", "ok"} or v is True else -1)
        fig = go.Figure(go.Waterfall(x=data[label_col], y=data["value"], measure=["relative"] * len(data), connector={"line": {"width": 1}}))
        fig.update_layout(title="Scientific release gate waterfall", yaxis_title="Pass (+1) / block (-1)", height=520)
        return fig, data, "Shows how each check contributes to the final release decision.", "Release gate check outcomes", "Pass/block"
    if index == 1:
        rows = []
        for item in blockers or []:
            if isinstance(item, dict):
                rows.append({"severity": item.get("severity", "blocker"), "blocker": item.get("message") or item.get("label") or str(item)})
            else:
                text = str(item)
                severity = "critical" if any(t in text.lower() for t in ("missing", "failed", "leakage", "invalid")) else "blocker"
                rows.append({"severity": severity, "blocker": text})
        data = pd.DataFrame(rows)
        if data.empty:
            return _empty(PHASE108_VISUAL_TITLES["release_gate"][index], "No release blockers are currently reported.")
        data = data.groupby(["severity", "blocker"], as_index=False).size().rename(columns={"size": "count"}).head(30)
        fig = _bar(data, "count", "blocker", "Release blocker severity", color="severity", orientation="h")
        return fig, data, "Ranks release-blocking findings and their severity.", "Release gate blockers", "Blockers"
    if index == 2:
        if checks.empty:
            return _empty(PHASE108_VISUAL_TITLES["release_gate"][index], "Release gate checks are unavailable.")
        status_col = next((c for c in ("status", "passed", "result") if c in checks.columns), None)
        group_col = next((c for c in ("category", "section", "area", "check_type") if c in checks.columns), None)
        label_col = next((c for c in ("check", "label", "requirement", "name") if c in checks.columns), checks.columns[0])
        work = checks.copy()
        work["status_numeric"] = work[status_col].map(lambda v: 100 if str(v).lower() in {"true", "pass", "passed", "ok"} or v is True else 0) if status_col else 0
        if group_col:
            matrix = work.pivot_table(index=group_col, columns=label_col, values="status_numeric", aggfunc="max", fill_value=0)
        else:
            matrix = work.set_index(label_col)[["status_numeric"]]
        fig = _heatmap(matrix, "Release validation evidence matrix", zmin=0, zmax=100, text_auto=".0f")
        return fig, work, "Shows pass or block status for release evidence checks.", "Release check status matrix", "% pass"
    if index == 3:
        data = pd.DataFrame({"dimension": ["Gate score", "Decision"], "value": [score, 100 if passed else 0]})
        fig = go.Figure(go.Indicator(mode="gauge+number", value=score, title={"text": "Scientific release readiness score"}, gauge={"axis": {"range": [0, 100]}, "threshold": {"line": {"width": 4}, "value": 100}}))
        fig.update_layout(height=430)
        return fig, data, "Summarises the release score while preserving the binary pass/block decision.", "Scientific release gate score", "%"
    if checks.empty:
        return _empty(PHASE108_VISUAL_TITLES["release_gate"][index], "Release gate checks are unavailable.")
    label_col = next((c for c in ("check", "label", "requirement", "name") if c in checks.columns), checks.columns[0])
    status_col = next((c for c in ("status", "passed", "result") if c in checks.columns), None)
    data = checks[[label_col] + ([status_col] if status_col else [])].copy()
    data["Required"] = 1
    data["Available"] = data[status_col].map(lambda v: 1 if str(v).lower() in {"true", "pass", "passed", "ok"} or v is True else 0) if status_col else 0
    long = data.melt(id_vars=[label_col], value_vars=["Required", "Available"], var_name="evidence_state", value_name="count")
    fig = _bar(long, label_col, "count", "Required versus available release evidence", color="evidence_state")
    return fig, long, "Shows which required release evidence items are currently available.", "Release evidence availability", "Present / absent"


def _provider_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    health = _df(context.get("health"))
    if health.empty:
        health = _df(context.get("rows"))
    if health.empty:
        health = _read_sql(root, "reports/connected_sources.sqlite3", "SELECT * FROM provider_health_checks ORDER BY checked_at_utc DESC LIMIT 1000")
    provider_catalog = pd.DataFrame()
    try:
        func = context.get("provider_rows")
        if callable(func):
            provider_catalog = pd.DataFrame(func())
    except Exception:
        provider_catalog = pd.DataFrame()
    query_rows = _df(context.get("query_rows"))
    if query_rows.empty:
        query_rows = _read_sql(root, "reports/connected_sources.sqlite3", "SELECT * FROM connected_queries ORDER BY retrieved_at_utc DESC LIMIT 1000")
    if index == 0:
        if health.empty:
            data = provider_catalog.copy()
            if data.empty:
                return _empty(PHASE108_VISUAL_TITLES["provider_integration"][index], "No provider health checks have been run.")
            data["status"] = "Not checked"
            data["providers"] = 1
            name_col = next((c for c in ("provider", "name", "key") if c in data.columns), data.columns[0])
            fig = _bar(data, name_col, "providers", "Provider catalogue awaiting health checks", color="status")
            return fig, data, "Shows registered providers that still require live or cached health checks.", "Provider catalogue", "Providers"
        data = health.copy(); data["availability"] = data.get("available", 0).map(lambda v: "Available" if bool(v) else "Unavailable")
        provider_col = next((c for c in ("provider", "name") if c in data.columns), data.columns[0])
        latest = data.drop_duplicates(provider_col)
        fig = _bar(latest, provider_col, "available", "Latest provider connection health", color="availability")
        return fig, latest, "Shows the latest recorded connection state for each provider.", "Provider health checks", "Available = 1"
    if index == 1:
        if health.empty or "latency_ms" not in health.columns:
            return _empty(PHASE108_VISUAL_TITLES["provider_integration"][index], "No provider latency measurements are available.")
        data = health.copy(); data["latency_ms"] = _numeric(data["latency_ms"]); data["available"] = _numeric(data.get("available", 0)).fillna(0)
        provider_col = next((c for c in ("provider", "name") if c in data.columns), data.columns[0])
        fig = px.scatter(data.dropna(subset=["latency_ms"]), x="latency_ms", y="available", color=provider_col, size="records" if "records" in data.columns else None, title="Provider latency and availability")
        return fig, data, "Separates slow providers from unavailable providers and high-record responses.", "Provider health latency", "Milliseconds"
    if index == 2:
        if query_rows.empty:
            return _empty(PHASE108_VISUAL_TITLES["provider_integration"][index], "No connected provider queries have been recorded.")
        data = query_rows.copy(); data["retrieved_at_utc"] = pd.to_datetime(data.get("retrieved_at_utc"), errors="coerce", utc=True); data["date"] = data["retrieved_at_utc"].dt.date
        data = data.groupby(["date", "provider"], as_index=False).agg(queries=("query_id", "size"), records=("record_count", "sum"))
        fig = px.line(data, x="date", y="records", color="provider", markers=True, title="Provider query and record activity")
        return fig, data, "Shows actual connected retrieval activity rather than registered connector count.", "Connected query history", "Records"
    if index == 3:
        if health.empty or "error_type" not in health.columns:
            return _empty(PHASE108_VISUAL_TITLES["provider_integration"][index], "No provider failure types have been recorded.")
        failures = health[health.get("available", 0).astype(int) == 0].copy()
        if failures.empty:
            return _empty(PHASE108_VISUAL_TITLES["provider_integration"][index], "Latest provider checks contain no failures.")
        data = failures.groupby("error_type", as_index=False).size().rename(columns={"size": "failures"})
        fig = _bar(data, "error_type", "failures", "Provider failure-type distribution")
        return fig, data, "Ranks DNS, authentication, rate-limit and provider API failures.", "Provider health failures", "Checks"
    if provider_catalog.empty:
        return _empty(PHASE108_VISUAL_TITLES["provider_integration"][index], "Provider catalogue metadata are unavailable.")
    provider_col = next((c for c in ("provider", "name", "key") if c in provider_catalog.columns), provider_catalog.columns[0])
    dimensions = [c for c in ("requires_key", "supports_batch", "supports_search", "supports_lookup", "configured") if c in provider_catalog.columns]
    if not dimensions:
        string_dims = [c for c in ("base_url", "documentation_url", "resource_type") if c in provider_catalog.columns]
        data = provider_catalog[[provider_col] + string_dims].copy()
        for c in string_dims:
            data[c] = data[c].astype(str).str.strip().ne("").astype(int) * 100
        dimensions = string_dims
    else:
        data = provider_catalog[[provider_col] + dimensions].copy()
        for c in dimensions:
            data[c] = data[c].map(lambda v: 100 if bool(v) else 0)
    matrix = data.set_index(provider_col)[dimensions]
    fig = _heatmap(matrix, "Provider capability and configuration coverage", zmin=0, zmax=100, text_auto=".0f")
    return fig, data, "Shows provider catalogue capability and configuration coverage.", "Provider capability matrix", "% available"


def _reference_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    assets = _read_sql(root, "data/reference_assets/reference_assets.sqlite3", "SELECT * FROM assets")
    events = _read_sql(root, "data/reference_assets/reference_assets.sqlite3", "SELECT * FROM asset_events")
    releases = _df(context.get("releases"))
    if releases.empty:
        releases = _read_sql(root, "workspace/step104/platform.sqlite3", "SELECT * FROM references_v2")
    if index == 0:
        if assets.empty:
            return _empty(PHASE108_VISUAL_TITLES["reference_manager"][index], "No reference assets are registered.")
        data = assets.copy(); data["size_bytes"] = _numeric(data["size_bytes"]).fillna(0)
        fig = px.treemap(data, path=["provider", "version"], values="size_bytes", color="status", title="Reference database storage profile")
        return fig, data, "Shows local storage consumption by provider, version and lifecycle status.", "Reference asset registry", "Bytes"
    if index == 1:
        if releases.empty:
            return _empty(PHASE108_VISUAL_TITLES["reference_manager"][index], "No reference releases or versions are registered.")
        date_col = next((c for c in ("created_at_utc", "installed_at_utc", "retrieved_at") if c in releases.columns), None)
        name_col = next((c for c in ("database_name", "provider", "name") if c in releases.columns), releases.columns[0])
        version_col = next((c for c in ("version", "release", "release_id") if c in releases.columns), None)
        data = releases.copy()
        if date_col:
            data["date"] = pd.to_datetime(data[date_col], errors="coerce")
        else:
            data["date"] = pd.RangeIndex(len(data))
        fig = px.scatter(data, x="date", y=name_col, color="status" if "status" in data.columns else None, hover_data=[version_col] if version_col else None, title="Reference database release and version timeline")
        return fig, data, "Shows when database versions were registered, installed or activated.", "Reference release registry", "Date"
    if index == 2:
        if assets.empty:
            return _empty(PHASE108_VISUAL_TITLES["reference_manager"][index], "No reference assets are registered.")
        data = assets.copy(); data["checksum_match"] = (data["expected_sha256"].astype(str).str.len() == 64) & (data["expected_sha256"].astype(str) == data["observed_sha256"].astype(str)); data["licensed"] = _numeric(data["license_accepted"]).fillna(0) > 0; data["installed"] = data["local_path"].astype(str).str.strip().ne("")
        matrix = data.set_index("asset_id")[["checksum_match", "licensed", "installed"]].astype(int) * 100
        fig = _heatmap(matrix, "Reference integrity, licence and installation matrix", zmin=0, zmax=100, text_auto=".0f")
        return fig, data, "Shows checksum, licence acceptance and local installation status for each reference asset.", "Reference asset integrity controls", "% pass"
    if index == 3:
        if events.empty:
            return _empty(PHASE108_VISUAL_TITLES["reference_manager"][index], "No reference lifecycle events are registered.")
        data = events.copy(); data["created_at_utc"] = pd.to_datetime(data["created_at_utc"], errors="coerce", utc=True); data["date"] = data["created_at_utc"].dt.date
        data = data.groupby(["date", "event_type"], as_index=False).size().rename(columns={"size": "events"})
        fig = px.line(data, x="date", y="events", color="event_type", markers=True, title="Reference asset lifecycle events")
        return fig, data, "Shows installation, verification, update and rollback activity over time.", "Reference asset event log", "Events"
    if releases.empty:
        return _empty(PHASE108_VISUAL_TITLES["reference_manager"][index], "No reference compatibility records are available.")
    data = releases.copy()
    status_col = "status" if "status" in data.columns else None
    active_col = "active" if "active" in data.columns else None
    name_col = next((c for c in ("database_name", "provider", "name") if c in data.columns), data.columns[0])
    data["active_numeric"] = _numeric(data[active_col]).fillna(0) if active_col else 0
    data["registered"] = 1
    if status_col:
        data["status_group"] = data[status_col].astype(str)
    else:
        data["status_group"] = "registered"
    summary = data.groupby([name_col, "status_group"], as_index=False).agg(versions=("registered", "sum"), active_versions=("active_numeric", "sum"))
    fig = px.scatter(summary, x="versions", y="active_versions", color="status_group", hover_name=name_col, size="versions", title="Reference compatibility and activation status")
    return fig, summary, "Shows version depth, lifecycle status and active-reference coverage.", "Reference version registry", "Versions"


_BUILDERS: dict[str, Callable[[int, Path, Mapping[str, Any]], VisualResult]] = {
    "clinical_validation": _clinical_visual,
    "external_validation": _external_visual,
    "benchmark_leakage": _leakage_visual,
    "dti_validation": _dti_validation_visual,
    "data_readiness": _data_readiness_visual,
    "model_evaluation": _model_evaluation_visual,
    "experiment_registry": _experiment_visual,
    "dataset_registry": _dataset_registry_visual,
    "knowledge_graph": _knowledge_visual,
    "evidence_package": _evidence_package_visual,
    "governance": _governance_visual,
    "release_gate": _release_gate_visual,
    "provider_integration": _provider_visual,
    "reference_manager": _reference_visual,
}


def render_phase108_visual_suite(
    module_key: str,
    root: str | Path,
    *,
    context: Mapping[str, Any] | None = None,
    expanded: bool = True,
) -> None:
    """Render one lazily selected decision visual from a five-visual module suite.

    The selector lists all five module-specific visual choices, but only the selected
    chart is constructed. This keeps Streamlit reruns bounded on large registries.
    """
    titles = PHASE108_VISUAL_TITLES.get(module_key)
    builder = _BUILDERS.get(module_key)
    if not titles or builder is None:
        return
    with st.expander("Decision visual workspace", expanded=expanded):
        st.caption(
            "Five module-specific decision views are available. Single mode renders one chart; "
            "comparison mode is capped at two charts to keep database-backed pages responsive."
        )
        title_list = list(titles)
        mode = st.radio(
            "Visual layout",
            ["Single visual", "Compare two visuals"],
            horizontal=True,
            key=f"phase108_visual_layout_{module_key}",
        )

        def render_selected(selected_title: str, *, side: str = "single") -> None:
            index = title_list.index(selected_title)
            try:
                figure, data, interpretation, method, units = builder(index, Path(root), context or {})
            except Exception as exc:  # Optional visualisation must not break the parent module.
                from biointel.ui.visual_workspace import record_visual_error
                error_id = record_visual_error(module_key=module_key, chart_key=f"phase108_{index}", error=exc)
                figure, data, interpretation, method, units = _empty(
                    selected_title,
                    f"This visual could not be generated safely. Diagnostic ID: {error_id}",
                )
            scientific_chart_card(
                figure,
                title=selected_title,
                interpretation=interpretation,
                data=data,
                method=method,
                units=units or None,
                key=f"phase108_{module_key}_{side}_{index}",
                module_key=module_key,
                source_record_count=len(data),
                configuration={"visual_index": index, "comparison_side": side, **dict(context or {})},
            )

        if mode == "Single visual":
            selected = st.selectbox(
                "Visual view",
                title_list,
                key=f"phase108_visual_selector_{module_key}",
            )
            render_selected(selected)
        else:
            left, right = st.columns(2, gap="large")
            with left:
                left_title = st.selectbox("Left view", title_list, key=f"phase108_left_{module_key}")
            with right:
                right_options = [title for title in title_list if title != left_title] or title_list
                right_title = st.selectbox("Right view", right_options, key=f"phase108_right_{module_key}")
            with left:
                render_selected(left_title, side="left")
            with right:
                render_selected(right_title, side="right")
