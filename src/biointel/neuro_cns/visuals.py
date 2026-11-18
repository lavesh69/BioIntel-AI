from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def empty_figure(title: str, message: str = "No plottable data available") -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    figure.update_layout(title=title, xaxis_visible=False, yaxis_visible=False)
    return figure


def expression_atlas_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    regional = result.get("regional_summary")
    cells = result.get("cell_type_summary")
    diseases = result.get("disease_summary")
    if isinstance(regional, pd.DataFrame) and not regional.empty:
        figures["regional"] = px.bar(
            regional.head(40), x="region", y="mean_expression", error_y="standard_deviation" if "standard_deviation" in regional else None,
            hover_data=[column for column in ("median_expression", "sample_count") if column in regional],
            title="Brain-region expression summary",
        )
    if isinstance(cells, pd.DataFrame) and not cells.empty:
        figures["cell_type"] = px.bar(
            cells.head(40), x="cell_type", y="mean_expression", error_y="standard_deviation" if "standard_deviation" in cells else None,
            hover_data=[column for column in ("median_expression", "sample_count") if column in cells],
            title="Neural cell-type expression summary",
        )
    if isinstance(diseases, pd.DataFrame) and not diseases.empty:
        figures["disease"] = px.bar(diseases.head(30), x="disease", y="mean_expression", title="Condition-stratified expression")
    return figures


def omics_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    ranking = result.get("feature_ranking")
    if isinstance(ranking, pd.DataFrame) and not ranking.empty:
        plot = ranking.copy()
        plot["minus_log10_fdr"] = -np.log10(pd.to_numeric(plot["fdr_bh"], errors="coerce").clip(lower=1e-300))
        figures["volcano"] = px.scatter(
            plot.head(500), x="cohens_d", y="minus_log10_fdr", size="cross_validated_auc",
            hover_name="feature", hover_data=["univariate_auc", "exploratory_rank_score"],
            title="Exploratory biomarker effect and FDR landscape",
        )
    calibration = result.get("calibration_table")
    if isinstance(calibration, pd.DataFrame) and not calibration.empty:
        figure = go.Figure()
        figure.add_trace(go.Scatter(
            x=calibration["mean_predicted_probability"], y=calibration["observed_positive_fraction"],
            mode="lines+markers", name="Observed",
        ))
        figure.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Ideal"))
        figure.update_layout(title="Internal calibration review", xaxis_title="Mean predicted probability", yaxis_title="Observed positive fraction")
        figures["calibration"] = figure
    permutation = result.get("permutation_distribution")
    if isinstance(permutation, pd.DataFrame) and not permutation.empty:
        figures["permutation"] = px.histogram(permutation, x="direction_adjusted_auc", title="Permutation null distribution")
    coefficients = result.get("selected_feature_coefficients")
    if isinstance(coefficients, pd.DataFrame) and not coefficients.empty:
        figures["coefficients"] = px.bar(
            coefficients.head(30).sort_values("standardized_logistic_coefficient"),
            x="standardized_logistic_coefficient", y="feature", orientation="h",
            title="Leakage-safe selected feature coefficients",
        )
    return figures


def variant_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    variants = result.get("prioritized_variants")
    if isinstance(variants, pd.DataFrame) and not variants.empty:
        top = variants.head(50).copy()
        top["variant"] = top.apply(lambda row: f"{row.get('gene') or '?'} {row.get('chrom') or ''}:{row.get('position') or ''} {row.get('ref') or ''}>{row.get('alt') or ''}", axis=1)
        figures["priority"] = px.bar(
            top.sort_values("priority_score"), x="priority_score", y="variant", orientation="h",
            hover_data=[column for column in ("priority_band", "consequence", "clinvar_uploaded", "allele_frequency", "reasons") if column in top],
            title="Research variant-priority evidence waterfall",
        )
        evidence_rows: list[dict[str, Any]] = []
        for _, row in top.head(20).iterrows():
            components = row.get("evidence_components")
            if isinstance(components, dict):
                for component, score in components.items():
                    evidence_rows.append({"variant": row["variant"], "evidence": component, "score": score})
        if evidence_rows:
            evidence = pd.DataFrame(evidence_rows)
            figures["evidence"] = px.bar(evidence, x="variant", y="score", color="evidence", title="Evidence-component contributions")
    return figures


def signal_figures(result: dict[str, Any], *, channel: str | None = None) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    preview = result.get("referenced_signal_preview")
    if isinstance(preview, pd.DataFrame) and not preview.empty:
        channels = [column for column in preview.columns if column != "time_seconds"][:12]
        long = preview.melt(id_vars="time_seconds", value_vars=channels, var_name="channel", value_name="amplitude")
        figures["waveform"] = px.line(long, x="time_seconds", y="amplitude", facet_row="channel", title="Referenced neural-signal preview")
        figures["waveform"].update_yaxes(matches=None)
    spectrogram = result.get("spectrogram")
    if isinstance(spectrogram, pd.DataFrame) and not spectrogram.empty:
        selected = channel if channel in spectrogram["channel"].astype(str).unique() else str(spectrogram.iloc[0]["channel"])
        subset = spectrogram.loc[spectrogram["channel"].astype(str) == selected]
        pivot = subset.pivot_table(index="frequency_hz", columns="time_seconds", values="power", aggfunc="mean")
        figures["spectrogram"] = px.imshow(pivot, aspect="auto", origin="lower", title=f"Time-frequency spectrogram — {selected}")
    evoked = result.get("evoked_response")
    if isinstance(evoked, pd.DataFrame) and not evoked.empty:
        channels = [column for column in evoked.columns if column != "relative_time_seconds"][:12]
        long = evoked.melt(id_vars="relative_time_seconds", value_vars=channels, var_name="channel", value_name="amplitude")
        figures["evoked"] = px.line(long, x="relative_time_seconds", y="amplitude", color="channel", title="Event-related average response")
    psd = result.get("power_spectral_density")
    if isinstance(psd, pd.DataFrame) and not psd.empty:
        figures["psd"] = px.line(psd, x="frequency_hz", y="power_spectral_density", color="channel", title="Power spectral density")
    return figures


def imaging_slice_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    slices = result.get("orthogonal_slices")
    if isinstance(slices, dict):
        for axis, values in slices.items():
            array = np.asarray(values, dtype=float)
            if array.ndim == 2 and array.size:
                figures[axis] = px.imshow(array, aspect="equal", origin="lower", title=f"Orthogonal slice — {axis}")
    atlas = result.get("atlas_summary")
    if isinstance(atlas, pd.DataFrame) and not atlas.empty:
        figures["atlas"] = px.bar(atlas.head(40), x="region", y="volume_mm3", hover_data=["mean_intensity"], title="Atlas-region volume and signal summary")
    motion = result.get("motion_qc")
    if isinstance(motion, pd.DataFrame) and not motion.empty:
        figures["motion"] = px.line(motion, x="frame", y=["global_mean_signal", "mean_absolute_frame_difference"], title="4D frame-level QC")
    return figures


def connectivity_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    matrix = result.get("connectivity_matrix")
    if isinstance(matrix, pd.DataFrame) and not matrix.empty:
        figures["matrix"] = px.imshow(matrix, aspect="auto", zmin=-1, zmax=1, title="ROI correlation matrix")
    nodes = result.get("network_summary", {}).get("nodes") if isinstance(result.get("network_summary"), dict) else None
    edges = result.get("strongest_connections")
    if isinstance(nodes, pd.DataFrame) and not nodes.empty:
        names = nodes["roi"].astype(str).tolist()
        angles = np.linspace(0, 2 * math.pi, len(names), endpoint=False)
        positions = {name: (math.cos(angle), math.sin(angle)) for name, angle in zip(names, angles)}
        figure = go.Figure()
        if isinstance(edges, pd.DataFrame) and not edges.empty:
            for _, row in edges.loc[edges.get("passes_threshold", True) == True].head(100).iterrows():  # noqa: E712
                left, right = str(row["roi_a"]), str(row["roi_b"])
                if left in positions and right in positions:
                    figure.add_trace(go.Scatter(x=[positions[left][0], positions[right][0]], y=[positions[left][1], positions[right][1]], mode="lines", line={"width": max(0.5, abs(float(row["correlation"])) * 4)}, hoverinfo="text", text=f"{left} ↔ {right}: {row['correlation']:.3f}", showlegend=False))
        figure.add_trace(go.Scatter(
            x=[positions[name][0] for name in names], y=[positions[name][1] for name in names], mode="markers+text",
            text=names, textposition="top center", marker={"size": 12 + nodes["degree"].to_numpy(float) * 2},
            customdata=nodes[[column for column in ("degree", "strength", "clustering_coefficient") if column in nodes]].to_numpy(),
            hovertemplate="%{text}<extra></extra>", showlegend=False,
        ))
        figure.update_layout(title="Thresholded connectivity network", xaxis_visible=False, yaxis_visible=False)
        figures["network"] = figure
    return figures


def precision_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    assignments = result.get("assignments")
    if isinstance(assignments, pd.DataFrame) and {"PC1", "PC2", "cluster"}.issubset(assignments.columns):
        plot = assignments.copy()
        plot["cluster_label"] = plot["cluster"].astype(str)
        figures["clusters"] = px.scatter(plot, x="PC1", y="PC2", color="cluster_label", hover_name="sample_id", title="Exploratory consensus stratification")
    consensus = result.get("consensus_matrix")
    if isinstance(consensus, pd.DataFrame) and not consensus.empty:
        figures["consensus"] = px.imshow(consensus, aspect="auto", zmin=0, zmax=1, title="Cross-seed co-assignment consensus")
    seed = result.get("seed_stability")
    if isinstance(seed, pd.DataFrame) and not seed.empty:
        figures["stability"] = px.histogram(seed, x="adjusted_rand_vs_primary", title="Cluster stability across seeds")
    trajectory = result.get("longitudinal_trajectories")
    if isinstance(trajectory, pd.DataFrame) and not trajectory.empty and "PC1" in trajectory:
        figures["trajectory"] = px.line(trajectory, x="time", y="PC1", color="subject", markers=True, title="Longitudinal PC1 trajectories")
    return figures


def chemistry_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    bbb = result.get("bbb_screen", result)
    mpo = bbb.get("cns_mpo_proxy", {}) if isinstance(bbb, dict) else {}
    factors = mpo.get("factor_desirability") if isinstance(mpo, dict) else None
    if isinstance(factors, dict) and factors:
        frame = pd.DataFrame([{"factor": key, "desirability": value} for key, value in factors.items()])
        figures["mpo"] = px.bar(frame, x="factor", y="desirability", range_y=[0, 1], title="Transparent CNS MPO-proxy factors")
    reference = result.get("reference_chemical_space") if isinstance(result, dict) else None
    if isinstance(reference, dict) and reference.get("descriptor_z_scores"):
        frame = pd.DataFrame([{"descriptor": key, "z_score": value} for key, value in reference["descriptor_z_scores"].items()])
        figures["chemical_space"] = px.bar(frame, x="descriptor", y="z_score", title="Reference chemical-space descriptor distance")
    return figures


def pk_figures(population_result: dict[str, Any] | None = None, occupancy_result: dict[str, Any] | None = None) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    if population_result:
        curve = population_result.get("percentile_curve")
        if isinstance(curve, pd.DataFrame) and not curve.empty:
            figure = go.Figure()
            figure.add_trace(go.Scatter(x=curve["time_hours"], y=curve["brain_unbound_p95"], mode="lines", line={"width": 0}, showlegend=False))
            figure.add_trace(go.Scatter(x=curve["time_hours"], y=curve["brain_unbound_p05"], mode="lines", fill="tonexty", name="P05–P95"))
            figure.add_trace(go.Scatter(x=curve["time_hours"], y=curve["brain_unbound_p50"], mode="lines", name="Median brain-unbound"))
            figure.update_layout(title="Brain-exposure uncertainty envelope", xaxis_title="Time (hours)", yaxis_title="Brain-unbound concentration")
            figures["exposure"] = figure
    if occupancy_result:
        curve = occupancy_result.get("occupancy_curve")
        if isinstance(curve, pd.DataFrame) and not curve.empty:
            figures["occupancy"] = px.line(curve, x="time_hours", y="occupancy_percent", color="target", line_dash="method", title="Time-resolved receptor occupancy")
    return figures


def target_evidence_graph_figure(result: dict[str, Any]) -> go.Figure:
    nodes = result.get("nodes")
    edges = result.get("edges")
    if not isinstance(nodes, pd.DataFrame) or nodes.empty:
        return empty_figure("Target evidence graph")
    names = nodes["node_id"].astype(str).tolist()
    angles = np.linspace(0, 2 * math.pi, len(names), endpoint=False)
    positions = {name: (math.cos(angle), math.sin(angle)) for name, angle in zip(names, angles)}
    figure = go.Figure()
    if isinstance(edges, pd.DataFrame) and not edges.empty:
        for _, row in edges.head(250).iterrows():
            left, right = str(row["source"]), str(row["target"])
            if left in positions and right in positions:
                figure.add_trace(go.Scatter(x=[positions[left][0], positions[right][0]], y=[positions[left][1], positions[right][1]], mode="lines", hoverinfo="text", text=str(row.get("relationship", "related_to")), showlegend=False))
    figure.add_trace(go.Scatter(
        x=[positions[name][0] for name in names], y=[positions[name][1] for name in names], mode="markers+text",
        text=nodes["label"].astype(str), textposition="top center", marker={"size": 16},
        customdata=nodes[[column for column in ("node_type", "source") if column in nodes]].to_numpy(),
        hovertemplate="%{text}<extra></extra>", showlegend=False,
    ))
    figure.update_layout(title="Target–pathway–disease evidence graph", xaxis_visible=False, yaxis_visible=False)
    return figure


def safety_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    occupancy = result.get("occupancy")
    if isinstance(occupancy, pd.DataFrame) and not occupancy.empty:
        figures["occupancy"] = px.bar(occupancy, x="target", y="occupancy_percent", color="role", title="Exposure-aware target occupancy")
    coverage = result.get("target_family_coverage")
    if isinstance(coverage, pd.DataFrame) and not coverage.empty:
        figures["coverage"] = px.bar(coverage, x="target_family", y="coverage_fraction", range_y=[0, 1], title="Supplied selectivity-panel coverage")
    estimates = result.get("side_effect_estimates", {}).get("side_effect_estimates") if isinstance(result.get("side_effect_estimates"), dict) else None
    if isinstance(estimates, list) and estimates:
        frame = pd.DataFrame(estimates)
        figures["side_effects"] = px.bar(frame, x="side_effect_category", y="likelihood_proxy", title="Exploratory side-effect association proxies")
    return figures


def trial_figures(result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    phase = result.get("phase_summary")
    if isinstance(phase, pd.DataFrame) and not phase.empty:
        figures["phase"] = px.bar(phase, x="phase", y="count", title="CNS trial phase landscape")
    status = result.get("status_summary")
    if isinstance(status, pd.DataFrame) and not status.empty:
        figures["status"] = px.bar(status, x="status", y="count", title="Trial-status landscape")
    compound_target = result.get("compound_target_summary")
    if isinstance(compound_target, pd.DataFrame) and not compound_target.empty:
        matrix = compound_target.pivot_table(index="compound", columns="target", values="trial_count", aggfunc="sum", fill_value=0)
        figures["compound_target"] = px.imshow(matrix, aspect="auto", title="Compound–target trial landscape")
    endpoint = result.get("endpoint_summary")
    if isinstance(endpoint, pd.DataFrame) and not endpoint.empty:
        figures["endpoint"] = px.bar(endpoint, x="endpoint_category", y="count", title="Endpoint-category coverage")
    return figures


def sequence_topology_figure(result: dict[str, Any]) -> go.Figure:
    track = result.get("residue_track")
    segments = result.get("transmembrane_like_segments")
    motifs = result.get("motifs")
    if not isinstance(track, pd.DataFrame) or track.empty:
        return empty_figure("Protein topology review")
    figure = go.Figure()
    hydrophobic = track["hydrophobic"].astype(int).rolling(19, center=True, min_periods=1).mean()
    figure.add_trace(go.Scatter(x=track["position"], y=hydrophobic, mode="lines", name="19-aa hydrophobic fraction"))
    if isinstance(segments, list):
        for segment in segments:
            figure.add_vrect(x0=segment.get("start", 0), x1=segment.get("end", 0), opacity=0.18, line_width=0)
    if isinstance(motifs, pd.DataFrame) and not motifs.empty:
        for _, row in motifs.iterrows():
            figure.add_annotation(x=(float(row["start_position"]) + float(row["end_position"])) / 2, y=1.02, text=str(row["motif"]), showarrow=True, arrowhead=1)
    figure.update_layout(title="Sequence topology and motif track", xaxis_title="Residue position", yaxis_title="Local hydrophobic fraction", yaxis_range=[0, 1.15])
    return figure
