from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def neurovascular_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    subjects = result.get("subject_scores")
    factors = result.get("factor_summary")
    if isinstance(subjects, pd.DataFrame) and not subjects.empty:
        figures["subjects"] = px.bar(
            subjects.head(80).sort_values("research_score"),
            x="research_score",
            y="subject_id",
            color="research_band",
            orientation="h",
            title="Transparent neurovascular research-factor score",
            hover_data=["data_completeness", "pulse_pressure"],
        )
    if isinstance(factors, pd.DataFrame) and not factors.empty:
        figures["factors"] = px.bar(
            factors,
            x="factor",
            y="flagged_subjects",
            hover_data=["mean_points"],
            title="Cohort factor coverage",
        )
    return figures


def circadian_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    hourly = result.get("hourly_profile")
    daily = result.get("daily_summary")
    if isinstance(hourly, pd.DataFrame) and not hourly.empty:
        figure = go.Figure()
        figure.add_trace(go.Scatter(x=hourly["hour"], y=hourly["mean_activity"], mode="lines+markers", name="Activity"))
        if "mean_heart_rate" in hourly:
            figure.add_trace(go.Scatter(x=hourly["hour"], y=hourly["mean_heart_rate"], mode="lines+markers", name="Heart rate", yaxis="y2"))
            figure.update_layout(yaxis2={"overlaying": "y", "side": "right", "title": "Mean heart rate"})
        figure.update_layout(title="24-hour circadian profile", xaxis_title="Hour", yaxis_title="Mean activity")
        figures["hourly"] = figure
    if isinstance(daily, pd.DataFrame) and not daily.empty:
        figures["daily"] = px.line(
            daily,
            x="date",
            y=[column for column in ("mean_activity", "low_activity_fraction") if column in daily],
            markers=True,
            title="Daily rhythm stability review",
        )
    return figures


def biomarker_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    ranking = result.get("biomarker_ranking")
    scores = result.get("sample_scores")
    if isinstance(ranking, pd.DataFrame) and not ranking.empty:
        plot = ranking.copy()
        plot["minus_log10_fdr"] = -np.log10(pd.to_numeric(plot["fdr_bh"], errors="coerce").clip(lower=1e-12))
        figures["ranking"] = px.scatter(
            plot,
            x="cohens_d",
            y="minus_log10_fdr",
            size="direction_adjusted_auc",
            hover_name="biomarker",
            hover_data=["bootstrap_auc_ci_low", "bootstrap_auc_ci_high", "missing_fraction"],
            title="Neurological biomarker evidence landscape",
        )
    if isinstance(scores, pd.DataFrame) and not scores.empty:
        figures["scores"] = px.box(
            scores,
            x="group",
            y="panel_score",
            points="all",
            title="Internal composite panel-score distribution",
        )
    return figures


def digital_sensor_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    windows = result.get("window_metrics")
    candidates = result.get("candidate_events")
    if isinstance(windows, pd.DataFrame) and not windows.empty:
        figure = go.Figure()
        figure.add_trace(go.Scatter(x=windows["start_time"], y=windows["mean_magnitude"], mode="lines", name="Mean magnitude"))
        figure.add_trace(go.Scatter(x=windows["start_time"], y=windows["mean_abs_jerk"], mode="lines", name="Mean |jerk|", yaxis="y2"))
        if isinstance(candidates, pd.DataFrame) and not candidates.empty:
            figure.add_trace(go.Scatter(x=candidates["start_time"], y=candidates["mean_magnitude"], mode="markers", marker={"size": 10, "symbol": "x"}, name="Candidate event"))
        figure.update_layout(
            title="Digital-neurology sensor windows",
            xaxis_title="Time",
            yaxis_title="Signal magnitude",
            yaxis2={"overlaying": "y", "side": "right", "title": "Mean absolute jerk"},
        )
        figures["windows"] = figure
    return figures


def neuroimmune_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    differential = result.get("differential_interactions")
    summary = result.get("cell_type_summary")
    if isinstance(differential, pd.DataFrame) and not differential.empty:
        pivot = differential.pivot_table(index="cell_type", columns="pathway", values="cohens_d", aggfunc="mean")
        figures["heatmap"] = px.imshow(
            pivot,
            aspect="auto",
            color_continuous_midpoint=0,
            title="Neuroimmune cell-state/pathway effect map",
        )
    if isinstance(summary, pd.DataFrame) and not summary.empty:
        figures["cell_summary"] = px.bar(
            summary,
            x="cell_type",
            y="mean_absolute_effect",
            hover_data=["pathways", "strongest_priority"],
            title="Cell-type differential interaction burden",
        )
    return figures


def cognitive_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    trajectories = result.get("subject_trajectories")
    summary = result.get("subject_summary")
    if isinstance(trajectories, pd.DataFrame) and not trajectories.empty:
        subset_subjects = (
            summary.sort_values("annualized_slope").head(20)["subject_id"].astype(str).tolist()
            if isinstance(summary, pd.DataFrame) and not summary.empty
            else trajectories["subject_id"].astype(str).unique()[:20].tolist()
        )
        plot = trajectories.loc[trajectories["subject_id"].astype(str).isin(subset_subjects)]
        figures["trajectories"] = px.line(
            plot,
            x="time_months",
            y="score",
            color="subject_id",
            line_dash="domain",
            markers=True,
            title="Longitudinal cognitive trajectories",
        )
    if isinstance(summary, pd.DataFrame) and not summary.empty:
        figures["slopes"] = px.bar(
            summary.sort_values("annualized_slope"),
            x="annualized_slope",
            y="subject_id",
            color="rapid_decline_flag",
            orientation="h",
            title="Annualized trajectory slopes",
        )
    return figures


def rehabilitation_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    response = result.get("participant_response")
    if not isinstance(response, pd.DataFrame) or response.empty:
        return {}
    return {
        "waterfall": px.bar(
            response.sort_values("oriented_improvement"),
            x="subject_id",
            y="oriented_improvement",
            color="response_class",
            title="Neurorehabilitation response waterfall",
        )
    }


def polypharmacy_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    subjects = result.get("subject_burden")
    medications = result.get("medication_summary")
    figures: dict[str, go.Figure] = {}
    if isinstance(subjects, pd.DataFrame) and not subjects.empty:
        figures["burden"] = px.bar(
            subjects.sort_values("composite_burden"),
            x="composite_burden",
            y="subject_id",
            color="burden_band",
            orientation="h",
            title="User-annotated CNS medication burden",
        )
    if isinstance(medications, pd.DataFrame) and not medications.empty:
        figures["medications"] = px.bar(
            medications.head(30),
            x="medication",
            y="subjects",
            title="Medication frequency in the uploaded cohort",
        )
    return figures


def network_vulnerability_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    nodes = result.get("node_metrics")
    curve = result.get("resilience_curve")
    if isinstance(nodes, pd.DataFrame) and not nodes.empty:
        figures["nodes"] = px.scatter(
            nodes,
            x="strength",
            y="efficiency_loss_if_removed",
            size="degree",
            color="clustering_coefficient",
            hover_name="node",
            title="Brain-network hub vulnerability",
        )
    if isinstance(curve, pd.DataFrame) and not curve.empty:
        figures["resilience"] = px.line(
            curve,
            x="removed_nodes",
            y="global_efficiency",
            markers=True,
            title="Targeted hub-removal resilience curve",
        )
    return figures


def developmental_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    observations = result.get("observations")
    summary = result.get("subject_domain_summary")
    if isinstance(observations, pd.DataFrame) and not observations.empty:
        flagged_subjects = (
            summary.sort_values("annual_z_velocity").head(18)["subject_id"].astype(str).tolist()
            if isinstance(summary, pd.DataFrame) and not summary.empty
            else observations["subject_id"].astype(str).unique()[:18].tolist()
        )
        plot = observations.loc[observations["subject_id"].astype(str).isin(flagged_subjects)]
        figures["trajectories"] = px.line(
            plot,
            x="age_months",
            y="z_score",
            color="subject_id",
            line_dash="domain",
            markers=True,
            title="Age-referenced neurodevelopmental z-trajectories",
        )
    if isinstance(summary, pd.DataFrame) and not summary.empty:
        figures["velocity"] = px.scatter(
            summary,
            x="last_z",
            y="annual_z_velocity",
            color="domain",
            symbol="below_minus_1_5_sd",
            hover_name="subject_id",
            title="Developmental status and velocity review",
        )
    return figures


FIGURE_BUILDERS = {
    "neurovascular_research": neurovascular_figures,
    "sleep_circadian": circadian_figures,
    "fluid_biomarkers": biomarker_figures,
    "digital_neurology": digital_sensor_figures,
    "neuroimmune_interactions": neuroimmune_figures,
    "cognitive_trajectory": cognitive_figures,
    "neurorehabilitation": rehabilitation_figures,
    "polypharmacy_cns": polypharmacy_figures,
    "brain_network_vulnerability": network_vulnerability_figures,
    "neurodevelopmental_trajectory": developmental_figures,
}


def figures_for(feature_key: str, result: dict[str, Any]) -> dict[str, go.Figure]:
    builder = FIGURE_BUILDERS.get(feature_key)
    return builder(result) if builder else {}


__all__ = ["FIGURE_BUILDERS", "figures_for"]
