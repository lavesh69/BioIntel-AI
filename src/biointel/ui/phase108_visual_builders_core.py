from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .phase108_visuals import (
    PHASE108_VISUAL_TITLES,
    VisualResult,
    _bar,
    _df,
    _empty,
    _forest,
    _heatmap,
    _json_dict,
    _numeric,
    _radar,
    _read_sql,
    _safe_ratio,
)

def _clinical_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    db = "data/clinical_pharma/clinical_validation.sqlite3"
    if index == 0:
        evidence = _read_sql(root, db, "SELECT category,evidence_type,status,COUNT(*) AS records FROM evidence_items GROUP BY category,evidence_type,status")
        artifacts = _read_sql(root, db, "SELECT domain AS category,source_type AS evidence_type,status,COUNT(*) AS records FROM external_validation_artifacts GROUP BY domain,source_type,status")
        data = pd.concat([evidence, artifacts], ignore_index=True)
        if data.empty:
            return _empty(PHASE108_VISUAL_TITLES["clinical_validation"][index], "No clinical evidence records have been registered yet.")
        levels = {"analytical": 1, "in_vitro": 1, "preclinical": 2, "retrospective": 3, "prospective": 4, "clinical": 4, "regulatory": 5}
        data["level"] = data["category"].astype(str).str.lower().map(levels).fillna(2)
        summary = data.groupby(["level", "category"], as_index=False)["records"].sum().sort_values("level")
        fig = _bar(summary, "records", "category", "Clinical evidence pyramid", color="level", orientation="h")
        return fig, summary, "Shows the current evidence mix by maturity level; higher levels require independent clinical or regulatory evidence.", "Registered evidence and artifact counts", "Records"
    if index == 1:
        programs = _read_sql(root, db, "SELECT COUNT(*) AS programs FROM validation_programs")
        protocols = _read_sql(root, db, "SELECT COUNT(*) AS protocols,COALESCE(SUM(sample_size),0) AS planned_samples FROM protocols")
        predictions = _read_sql(root, db, "SELECT COALESCE(SUM(sample_count),0) AS predicted_samples FROM prediction_batches")
        outcomes = _read_sql(root, db, "SELECT COALESCE(SUM(sample_count),0) AS outcome_samples FROM outcome_batches")
        analyses = _read_sql(root, db, "SELECT COUNT(*) AS analysed_endpoints FROM analysis_results")
        values = [
            ("Programs", int(programs.iloc[0, 0]) if not programs.empty else 0),
            ("Planned samples", int(protocols.get("planned_samples", pd.Series([0])).iloc[0]) if not protocols.empty else 0),
            ("Locked predictions", int(predictions.iloc[0, 0]) if not predictions.empty else 0),
            ("Outcomes received", int(outcomes.iloc[0, 0]) if not outcomes.empty else 0),
            ("Analysed endpoints", int(analyses.iloc[0, 0]) if not analyses.empty else 0),
        ]
        data = pd.DataFrame(values, columns=["stage", "count"])
        fig = go.Figure(go.Funnel(y=data["stage"], x=data["count"], textinfo="value+percent initial"))
        fig.update_layout(title="Validation cohort and evidence flow", height=500)
        return fig, data, "Tracks the operational path from registered validation programmes to analysed outcomes.", "Registry-derived validation funnel", "Records / samples"
    if index == 2:
        data = _read_sql(root, db, "SELECT metric_name,metric_value,lower_ci,upper_ci,result_scope,site_id,subgroup,passed,status FROM analysis_results ORDER BY created_at DESC LIMIT 100")
        if data.empty:
            return _empty(PHASE108_VISUAL_TITLES["clinical_validation"][index], "No analysed clinical endpoints with confidence intervals are available.")
        fig = _forest(data, "Endpoint effect estimates and confidence intervals")
        return fig, data, "Displays endpoint estimates with available confidence intervals and pass status.", "Registered analysis results", "Endpoint-specific units"
    if index == 3:
        data = _read_sql(root, db, "SELECT severity,status,event_type,COUNT(*) AS events FROM quality_events GROUP BY severity,status,event_type")
        if data.empty:
            return _empty(PHASE108_VISUAL_TITLES["clinical_validation"][index], "No quality events have been registered.")
        matrix = data.pivot_table(index="event_type", columns=["severity", "status"], values="events", aggfunc="sum", fill_value=0)
        fig = _heatmap(matrix, "Clinical quality-risk matrix", text_auto=".0f")
        flat = matrix.reset_index()
        return fig, flat, "Highlights concentrations of open or severe quality events requiring review.", "Quality-event count matrix", "Events"
    tables = {
        "Protocols": "protocols",
        "Sites": "validation_sites",
        "Evidence": "evidence_items",
        "External artifacts": "external_validation_artifacts",
        "Prediction batches": "prediction_batches",
        "Outcome batches": "outcome_batches",
        "Analyses": "analysis_results",
        "Training": "training_records",
        "Signatures": "signatures",
    }
    rows: list[dict[str, Any]] = []
    for label, table in tables.items():
        frame = _read_sql(root, db, f'SELECT COUNT(*) AS count FROM "{table}"')
        count = int(frame.iloc[0, 0]) if not frame.empty else 0
        rows.append({"dimension": label, "coverage": 100.0 if count > 0 else 0.0, "records": count})
    data = pd.DataFrame(rows)
    fig = _radar(data, "dimension", "coverage", "Validation record coverage")
    return fig, data, "Shows which validation record classes are populated; it does not claim clinical validity.", "Presence-based registry coverage", "% populated"

def _external_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    result = context.get("result") or context.get("ext_result")
    if result is None:
        return _empty(PHASE108_VISUAL_TITLES["external_validation"][index], "Run external validation to generate this visual.")
    metrics = _json_dict(getattr(result, "metrics", None) if not isinstance(result, dict) else result.get("metrics"))
    drift = _json_dict(getattr(result, "drift", None) if not isinstance(result, dict) else result.get("drift"))
    predictions = _df(getattr(result, "predictions", None) if not isinstance(result, dict) else result.get("predictions"))
    if index == 0:
        data = pd.DataFrame([{"metric": key, "value": value} for key, value in metrics.items() if isinstance(value, (int, float)) and value is not None])
        if data.empty:
            return _empty(PHASE108_VISUAL_TITLES["external_validation"][index], "No numeric validation metrics were generated.")
        fig = _bar(data, "metric", "value", "External validation performance")
        return fig, data, "Summarises the independent-cohort metrics reported by the frozen model evaluation.", "External validation metrics", "Metric-specific"
    if index == 1:
        data = _df(drift.get("top_shifted_features", []))
        if data.empty:
            return _empty(PHASE108_VISUAL_TITLES["external_validation"][index], "No feature-level drift rankings were generated.")
        value_col = next((c for c in ("standardized_mean_shift", "psi", "ks_statistic", "shift") if c in data.columns), None)
        feature_col = next((c for c in ("feature", "feature_name", "name") if c in data.columns), None)
        if not value_col or not feature_col:
            return _empty(PHASE108_VISUAL_TITLES["external_validation"][index], "The drift result does not contain plottable feature and shift columns.")
        data[value_col] = _numeric(data[value_col])
        data = data.dropna(subset=[value_col]).sort_values(value_col, ascending=False).head(30)
        fig = _bar(data, value_col, feature_col, "Top shifted model features", orientation="h")
        return fig, data, "Ranks the features with the largest measured distribution shift.", "Feature drift ranking", "Standardised shift"
    if index == 2:
        if {"actual", "positive_probability"}.issubset(predictions.columns):
            work = predictions[["actual", "positive_probability"]].dropna().copy()
            if work.empty:
                return _empty(PHASE108_VISUAL_TITLES["external_validation"][index], "No prediction probabilities are available.")
            work["bin"] = pd.cut(_numeric(work["positive_probability"]), bins=np.linspace(0, 1, 11), include_lowest=True)
            cal = work.groupby("bin", observed=True).agg(mean_probability=("positive_probability", "mean"), observed_rate=("actual", "mean"), samples=("actual", "size")).reset_index()
            fig = px.scatter(cal, x="mean_probability", y="observed_rate", size="samples", title="External calibration curve")
            fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Ideal"))
            return fig, cal, "Compares predicted probabilities with observed event rates in the external cohort.", "Decile reliability analysis", "Probability"
        if {"actual", "predicted"}.issubset(predictions.columns):
            work = predictions[["actual", "predicted"]].apply(pd.to_numeric, errors="coerce").dropna().head(20000)
            fig = px.scatter(work, x="actual", y="predicted", opacity=0.55, title="Observed versus predicted values")
            if not work.empty:
                low = float(min(work.min()))
                high = float(max(work.max()))
                fig.add_trace(go.Scatter(x=[low, high], y=[low, high], mode="lines", name="Ideal"))
            return fig, work, "Shows agreement between observed and predicted values on independent data.", "Observed-predicted agreement", "Outcome units"
        return _empty(PHASE108_VISUAL_TITLES["external_validation"][index], "Predictions do not contain probability or observed/predicted columns.")
    if index == 3:
        if "residual" in predictions.columns:
            data = predictions[["residual"]].copy()
            data["residual"] = _numeric(data["residual"])
            data = data.dropna()
            fig = px.histogram(data, x="residual", nbins=40, marginal="box", title="External residual distribution")
            return fig, data, "Shows prediction error spread and outliers in the external cohort.", "Residual distribution", "Outcome units"
        if "positive_probability" in predictions.columns:
            data = predictions[[c for c in ("actual", "positive_probability") if c in predictions.columns]].copy()
            data["positive_probability"] = _numeric(data["positive_probability"])
            data = data.dropna(subset=["positive_probability"])
            fig = px.histogram(data, x="positive_probability", color="actual" if "actual" in data.columns else None, nbins=30, marginal="box", title="Prediction confidence distribution")
            return fig, data, "Shows confidence separation and potential overconfidence on independent data.", "Prediction probability distribution", "Probability"
        return _empty(PHASE108_VISUAL_TITLES["external_validation"][index], "No residual or confidence field is available.")
    input_rows = int(getattr(result, "input_rows", 0) if not isinstance(result, dict) else result.get("input_rows", 0))
    valid_rows = int(getattr(result, "valid_rows", 0) if not isinstance(result, dict) else result.get("valid_rows", 0))
    invalid_rows = int(getattr(result, "invalid_rows", 0) if not isinstance(result, dict) else result.get("invalid_rows", 0))
    data = pd.DataFrame({"stage": ["Input rows", "Valid rows", "Invalid rows"], "rows": [input_rows, valid_rows, invalid_rows]})
    fig = go.Figure(go.Funnel(y=data["stage"], x=data["rows"], textinfo="value+percent initial"))
    fig.update_layout(title="External validation data-quality funnel", height=480)
    return fig, data, "Shows how many input rows reached model evaluation and how many were rejected.", "Validation row-flow audit", "Rows"

def _leakage_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    result = context.get("result") or context.get("step25_leakage")
    if not isinstance(result, dict):
        return _empty(PHASE108_VISUAL_TITLES["benchmark_leakage"][index], "Run the strict leakage audit to generate this visual.")
    keys = ["exact_compound_overlap", "scaffold_overlap", "exact_target_overlap", "target_cluster_overlap", "pair_overlap"]
    labels = ["Exact compounds", "Scaffolds", "Exact targets", "Target clusters", "Drug-target pairs"]
    overlaps = [int(result.get(key, 0) or 0) for key in keys]
    if index == 0:
        data = pd.DataFrame({"leakage_type": labels, "overlap": overlaps})
        fig = _bar(data, "leakage_type", "overlap", "Train-test leakage overlap profile")
        return fig, data, "Shows exact and structural overlap types that can inflate benchmark performance.", "Strict train-test overlap audit", "Overlapping entities"
    if index == 1:
        data = pd.DataFrame([overlaps], columns=labels, index=["Overlap count"])
        fig = _heatmap(data, "Leakage-risk matrix", text_auto=".0f")
        return fig, data.reset_index(names="measure"), "Concentrates leakage signals into a single release-blocking matrix.", "Overlap count heatmap", "Count"
    train = _df(context.get("train"))
    test = _df(context.get("test"))
    if index == 2:
        denominators = [
            max(1, int(test.get("canonical_smiles", pd.Series(dtype=str)).nunique())),
            max(1, int(test.get("canonical_smiles", pd.Series(dtype=str)).nunique())),
            max(1, int(test.get("protein_sequence", pd.Series(dtype=str)).nunique())),
            max(1, int(test.get("protein_sequence", pd.Series(dtype=str)).nunique())),
            max(1, len(test)),
        ]
        retention = [100.0 * (1.0 - min(1.0, _safe_ratio(o, d))) for o, d in zip(overlaps, denominators)]
        data = pd.DataFrame({"entity_type": labels, "unique_retention_percent": retention, "overlap": overlaps, "test_denominator": denominators})
        fig = _bar(data, "entity_type", "unique_retention_percent", "Unique entity retention after leakage audit")
        fig.update_yaxes(range=[0, 100])
        return fig, data, "Estimates how much of the independent test entity space remains non-overlapping.", "Overlap-adjusted entity retention", "% unique"
    if index == 3:
        passed = bool(result.get("passed", False))
        value = 100 if passed else max(0, 100 - 20 * sum(v > 0 for v in overlaps))
        fig = go.Figure(go.Indicator(mode="gauge+number+delta", value=value, delta={"reference": 100}, title={"text": "Leakage-safe release score"}, gauge={"axis": {"range": [0, 100]}, "threshold": {"line": {"width": 4}, "thickness": 0.8, "value": 100}}))
        fig.update_layout(height=430)
        data = pd.DataFrame([{"passed": passed, "score": value, "overlap_types": sum(v > 0 for v in overlaps)}])
        return fig, data, "A release-facing summary; any non-zero audited overlap should remain reviewable or blocking.", "Rule-based leakage gate", "Score"
    data = pd.DataFrame({"partition": ["Train", "Test"], "rows": [int(result.get("train_rows", len(train))), int(result.get("test_rows", len(test)))]})
    fig = _bar(data, "partition", "rows", "Benchmark partition composition")
    return fig, data, "Compares the sample support used for training and independent evaluation.", "Partition row counts", "Rows"

def _dti_validation_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    report = context.get("report")
    if not isinstance(report, dict):
        return _empty(PHASE108_VISUAL_TITLES["dti_validation"][index], "Validation readiness report is unavailable.")
    frame = _df(report.get("capabilities"))
    summary = _json_dict(report.get("summary"))
    if index == 0:
        if frame.empty:
            return _empty(PHASE108_VISUAL_TITLES["dti_validation"][index], "No capability scores are available.")
        data = frame.melt(id_vars=["label"], value_vars=["implementation_score", "evidence_score"], var_name="score_type", value_name="score")
        fig = _bar(data.sort_values("score"), "score", "label", "DTI implementation versus actual evidence", color="score_type", orientation="h")
        fig.update_xaxes(range=[0, 10])
        return fig, data, "Separates implemented controls from independently completed evidence.", "Capability readiness comparison", "Score / 10"
    if index == 1:
        if frame.empty:
            return _empty(PHASE108_VISUAL_TITLES["dti_validation"][index], "No capability scores are available.")
        matrix = frame.set_index("label")[["implementation_score", "evidence_score"]].copy()
        matrix["evidence_gap"] = matrix["implementation_score"] - matrix["evidence_score"]
        fig = _heatmap(matrix, "DTI validation evidence-gap heatmap", zmin=0, zmax=10)
        return fig, matrix.reset_index(), "Highlights areas where software controls are stronger than completed independent evidence.", "Implementation-evidence gap", "Score / 10"
    if index == 2:
        if frame.empty or "status" not in frame.columns:
            return _empty(PHASE108_VISUAL_TITLES["dti_validation"][index], "No qualification status data are available.")
        data = frame.groupby("status", as_index=False).size().rename(columns={"size": "capabilities"})
        fig = px.pie(data, names="status", values="capabilities", hole=0.55, title="Qualification status composition")
        return fig, data, "Shows how many validation capability areas are complete, partial or blocked.", "Capability status counts", "Capabilities"
    if index == 3:
        if frame.empty:
            return _empty(PHASE108_VISUAL_TITLES["dti_validation"][index], "No capability scores are available.")
        data = frame[["label", "implementation_score", "evidence_score"]].copy()
        data["gap"] = _numeric(data["implementation_score"]) - _numeric(data["evidence_score"])
        data = data.sort_values("gap", ascending=False).head(20)
        fig = _bar(data, "gap", "label", "Largest DTI validation evidence gaps", orientation="h")
        return fig, data, "Ranks the evidence gaps that should receive independent validation effort first.", "Readiness gap ranking", "Score points"
    names = ["Studies", "External DTI", "Blinded prospective", "Wet-lab", "Independent sites", "Multi-site", "Release eligible"]
    values = [summary.get("studies", 0), summary.get("completed_external_dti", 0), summary.get("completed_blinded_prospective", 0), summary.get("completed_wetlab", 0), summary.get("independent_sites", 0), summary.get("completed_multisite", 0), summary.get("release_eligible_studies", 0)]
    data = pd.DataFrame({"stage": names, "count": values})
    fig = go.Figure(go.Funnel(y=data["stage"], x=data["count"], textinfo="value"))
    fig.update_layout(title="Validation milestone funnel", height=530)
    return fig, data, "Shows the currently completed progression from registered studies to release-eligible evidence.", "Validation evidence milestones", "Count"

def _data_readiness_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    datasets = _df(context.get("datasets"))
    providers = _df(context.get("providers"))
    if datasets.empty:
        try:
            from biointel.data.readiness import dataset_readiness_rows, provider_readiness_rows
            datasets = pd.DataFrame(dataset_readiness_rows(root))
            providers = pd.DataFrame(provider_readiness_rows(root))
        except Exception:
            pass
    if index == 0:
        if datasets.empty:
            return _empty(PHASE108_VISUAL_TITLES["data_readiness"][index], "No dataset readiness records are available.")
        data = datasets.copy()
        data["metadata_completeness"] = _numeric(data.get("metadata_completeness", 0))
        data["readiness_score"] = _numeric(data.get("readiness_score", 0))
        fig = px.scatter(data, x="metadata_completeness", y="readiness_score", color="scientific_status" if "scientific_status" in data.columns else None, size="row_count" if "row_count" in data.columns else None, hover_name="dataset_name" if "dataset_name" in data.columns else None, title="Metadata completeness versus scientific readiness")
        fig.update_xaxes(range=[0, 105]); fig.update_yaxes(range=[0, 105])
        return fig, data, "Separates registry completeness from scientific readiness and release status.", "Dataset readiness registry", "%"
    if index == 1:
        if datasets.empty:
            return _empty(PHASE108_VISUAL_TITLES["data_readiness"][index], "No dataset readiness records are available.")
        cols = [c for c in ("file_count", "column_count", "sample_count", "qc_count", "lineage_count", "provenance_count") if c in datasets.columns]
        matrix = datasets.set_index("dataset_name")[cols].copy().head(50)
        matrix = matrix.apply(pd.to_numeric, errors="coerce").fillna(0)
        matrix = (matrix > 0).astype(int) * 100
        fig = _heatmap(matrix, "Dataset readiness component matrix", zmin=0, zmax=100, text_auto=".0f")
        return fig, matrix.reset_index(), "Shows which datasets have files, schemas, samples, QC, lineage and provenance coverage.", "Presence-based readiness matrix", "% present"
    if index == 2:
        if datasets.empty:
            return _empty(PHASE108_VISUAL_TITLES["data_readiness"][index], "No dataset readiness records are available.")
        rows: list[dict[str, Any]] = []
        for _, row in datasets.iterrows():
            blockers = row.get("blockers_json", "[]")
            warnings = row.get("warnings_json", "[]")
            for kind, raw in (("Blocker", blockers), ("Warning", warnings)):
                try:
                    items = json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    items = []
                for item in items or []:
                    rows.append({"type": kind, "message": str(item)})
        data = pd.DataFrame(rows)
        if data.empty:
            return _empty(PHASE108_VISUAL_TITLES["data_readiness"][index], "No readiness blockers or warnings are currently registered.")
        data = data.groupby(["type", "message"], as_index=False).size().rename(columns={"size": "datasets"}).sort_values("datasets", ascending=False).head(25)
        fig = _bar(data, "datasets", "message", "Dataset readiness blockers and warnings", color="type", orientation="h")
        return fig, data, "Ranks recurring readiness issues across registered datasets.", "Readiness issue aggregation", "Datasets"
    if index == 3:
        if datasets.empty:
            return _empty(PHASE108_VISUAL_TITLES["data_readiness"][index], "No dataset readiness records are available.")
        data = datasets[[c for c in ("dataset_name", "lineage_count", "provenance_count", "file_count") if c in datasets.columns]].copy()
        for c in ("lineage_count", "provenance_count", "file_count"):
            if c in data.columns:
                data[c] = _numeric(data[c]).fillna(0)
        fig = px.scatter(data, x="lineage_count", y="provenance_count", size="file_count" if "file_count" in data.columns else None, hover_name="dataset_name" if "dataset_name" in data.columns else None, title="Dataset lineage and provenance coverage")
        return fig, data, "Shows whether datasets are connected to lineage and provenance records, not only files.", "Lineage-provenance coverage", "Record counts"
    if providers.empty:
        return _empty(PHASE108_VISUAL_TITLES["data_readiness"][index], "No provider readiness records are available.")
    data = providers.copy()
    for c in ("records_available", "reference_record_count", "download_records", "sync_events"):
        if c in data.columns:
            data[c] = _numeric(data[c]).fillna(0)
    value_cols = [c for c in ("records_available", "reference_record_count", "download_records", "sync_events") if c in data.columns]
    data_long = data.melt(id_vars=["provider"], value_vars=value_cols, var_name="coverage_type", value_name="count")
    fig = _bar(data_long, "provider", "count", "Provider data and sync coverage", color="coverage_type")
    return fig, data_long, "Distinguishes registered connectors from locally imported records and completed sync activity.", "Provider readiness catalogue", "Records / events"

def _model_evaluation_visual(index: int, root: Path, context: Mapping[str, Any]) -> VisualResult:
    comparison = _df(context.get("comparison"))
    if comparison.empty:
        return _empty(PHASE108_VISUAL_TITLES["model_evaluation"][index], "Select compatible saved models to build the comparison visuals.")
    metric_cols = [c for c in comparison.columns if (c.startswith("Validation ") or c.startswith("Test ")) and _numeric(comparison[c]).notna().any()]
    if index == 0:
        data = comparison.melt(id_vars=["File"], value_vars=metric_cols, var_name="metric", value_name="value").dropna()
        if data.empty:
            return _empty(PHASE108_VISUAL_TITLES["model_evaluation"][index], "No numeric model metrics are available.")
        fig = _bar(data, "metric", "value", "Model performance comparison", color="File")
        return fig, data, "Compares saved-model metrics while preserving model identity.", "Stored validation and held-out test metrics", "Metric-specific"
    pairs: list[dict[str, Any]] = []
    for test_col in [c for c in metric_cols if c.startswith("Test ")]:
        suffix = test_col.removeprefix("Test ")
        val_col = f"Validation {suffix}"
        if val_col in comparison.columns:
            for _, row in comparison.iterrows():
                pairs.append({"File": row.get("File"), "Metric": suffix, "Validation": row.get(val_col), "Test": row.get(test_col)})
    paired = pd.DataFrame(pairs)
    if index == 1:
        if paired.empty:
            return _empty(PHASE108_VISUAL_TITLES["model_evaluation"][index], "No matched validation and test metrics are available.")
        paired[["Validation", "Test"]] = paired[["Validation", "Test"]].apply(pd.to_numeric, errors="coerce")
        paired = paired.dropna()
        fig = px.scatter(paired, x="Validation", y="Test", color="File", symbol="Metric", hover_data=["Metric"], title="Validation-to-test agreement")
        if not paired.empty:
            low = float(min(paired[["Validation", "Test"]].min()))
            high = float(max(paired[["Validation", "Test"]].max()))
            fig.add_trace(go.Scatter(x=[low, high], y=[low, high], mode="lines", name="No drop"))
        return fig, paired, "Shows whether held-out test performance is consistent with validation performance.", "Matched metric agreement", "Metric value"
    if index == 2:
        if paired.empty:
            return _empty(PHASE108_VISUAL_TITLES["model_evaluation"][index], "No matched validation and test metrics are available.")
        paired[["Validation", "Test"]] = paired[["Validation", "Test"]].apply(pd.to_numeric, errors="coerce")
        paired["Delta"] = paired["Test"] - paired["Validation"]
        matrix = paired.pivot_table(index="File", columns="Metric", values="Delta", aggfunc="mean")
        fig = _heatmap(matrix, "Generalisation delta: test minus validation", zmin=-1, zmax=1)
        return fig, matrix.reset_index(), "Negative values flag performance loss from validation to held-out test data.", "Test-validation metric delta", "Metric points"
    if index == 3:
        preferred = next((c for c in comparison.columns if c.startswith("Test ") and any(token in c.lower() for token in ("roc", "accuracy", "f1", "r2", "balanced"))), metric_cols[-1] if metric_cols else None)
        if preferred is None:
            return _empty(PHASE108_VISUAL_TITLES["model_evaluation"][index], "No suitable test metric is available.")
        data = comparison[[c for c in ("File", "Train rows", "Test rows", preferred, "Task", "Synthetic demo") if c in comparison.columns]].copy()
        for c in ("Train rows", "Test rows", preferred):
            if c in data.columns:
                data[c] = _numeric(data[c])
        data = data.dropna(subset=["Train rows", preferred])
        fig = px.scatter(data, x="Train rows", y=preferred, size="Test rows" if "Test rows" in data.columns else None, color="Task" if "Task" in data.columns else None, symbol="Synthetic demo" if "Synthetic demo" in data.columns else None, hover_name="File", title="Data support versus held-out performance")
        return fig, data, "Shows whether stronger metrics are supported by sufficient train and held-out test sample sizes.", "Model support-performance scatter", "Rows / metric"
    cols = [c for c in ("Task", "Split", "Calibration", "Synthetic demo") if c in comparison.columns]
    rows: list[dict[str, Any]] = []
    for col in cols:
        counts = comparison[col].astype(str).value_counts(dropna=False)
        rows.extend({"dimension": col, "category": str(k), "models": int(v)} for k, v in counts.items())
    data = pd.DataFrame(rows)
    if data.empty:
        return _empty(PHASE108_VISUAL_TITLES["model_evaluation"][index], "No provenance dimensions are available.")
    fig = _bar(data, "category", "models", "Model provenance and evaluation design", color="dimension")
    return fig, data, "Summarises task, split, calibration and synthetic/demo composition across selected models.", "Stored model metadata", "Models"

