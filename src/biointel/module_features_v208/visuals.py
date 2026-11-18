from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _first_numeric(frame: pd.DataFrame, excluded: set[str] | None = None) -> str | None:
    excluded = excluded or set()
    for column in frame.select_dtypes(include="number").columns:
        if str(column) not in excluded:
            return str(column)
    return None


def figures_for_result(feature_key: str, result: dict[str, Any]) -> dict[str, go.Figure]:
    figures: dict[str, go.Figure] = {}
    if feature_key == "advanced_eeg_meg":
        bands = result.get("band_power")
        if isinstance(bands, pd.DataFrame) and not bands.empty:
            figures["relative_band_power"] = px.bar(bands, x="band", y="relative_power", color="channel", barmode="group", title="Relative frequency-band power")
        epochs = result.get("epoch_summary")
        if isinstance(epochs, pd.DataFrame) and not epochs.empty:
            figures["epoch_artifacts"] = px.line(epochs, x="start_seconds", y=[column for column in ("artifact_fraction", "rms", "peak_to_peak") if column in epochs], title="Epoch-level signal and artifact review")
        preview = result.get("processed_preview")
        if isinstance(preview, pd.DataFrame) and not preview.empty and "time" in preview:
            channels = [column for column in preview.select_dtypes(include="number").columns if column != "time"][:8]
            if channels:
                stride = max(1, len(preview) // 1500)
                figures["processed_waveforms"] = px.line(preview.iloc[::stride], x="time", y=channels, title="Processed neural signal preview")
        qc = result.get("channel_qc")
        if isinstance(qc, pd.DataFrame) and not qc.empty:
            figures["channel_quality"] = px.bar(qc, x="channel", y="standard_deviation_before_filter", color="bad_channel_candidate", title="Channel quality review")
        if isinstance(bands, pd.DataFrame) and not bands.empty:
            heat = bands.pivot_table(index="channel", columns="band", values="relative_power", aggfunc="mean")
            figures["band_power_heatmap"] = px.imshow(heat, aspect="auto", labels={"x": "Band", "y": "Channel", "color": "Relative power"}, title="Channel-by-band power map")
    elif feature_key == "advanced_neuroimaging":
        slices = result.get("slice_summary")
        if isinstance(slices, pd.DataFrame) and not slices.empty:
            figures["slice_qc"] = px.line(slices, x="slice_index", y="mean_intensity", color="axis", title="Slice intensity profile")
        components = result.get("components")
        if isinstance(components, pd.DataFrame) and not components.empty:
            figures["component_volume"] = px.bar(components.head(30), x="component", y="volume_mm3", title="Threshold component volumes")
        for plane, label in (("axial_mid_slice", "Axial"), ("coronal_mid_slice", "Coronal"), ("sagittal_mid_slice", "Sagittal")):
            image = result.get(plane)
            if isinstance(image, pd.DataFrame) and not image.empty:
                figures[f"{plane}_heatmap"] = px.imshow(image.to_numpy(), aspect="equal", labels={"x": "Voxel", "y": "Voxel", "color": "Intensity"}, title=f"{label} mid-slice")
        roi = result.get("roi_summary")
        if isinstance(roi, pd.DataFrame) and not roi.empty:
            figures["roi_profile"] = px.bar(roi, x="roi", y=[column for column in ("mean_intensity", "threshold_fraction") if column in roi], barmode="group", title="ROI intensity and threshold profile")
    elif feature_key == "advanced_neurogenetics":
        frame = result.get("variants")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["variant_priority"] = px.bar(frame.head(30), x="variant_key", y="research_priority_score", color="research_tier", title="Research variant priority")
            figures["variant_evidence_space"] = px.scatter(frame, x="population_af_numeric", y="research_priority_score", color="research_tier", symbol="inheritance" if "inheritance" in frame else None, hover_name="variant_key", title="Population frequency versus research priority")
            figures["variant_tiers"] = px.histogram(frame, x="research_tier", color="clinvar" if "clinvar" in frame else None, title="Variant evidence tiers")
    elif feature_key == "advanced_expression_atlas":
        frame = result.get("expression_profile")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["expression_context"] = px.bar(frame.head(60), x="region", y="expression", color="cell_type", facet_col="gene", title="Brain-region and cell-type expression")
            heat = frame.pivot_table(index=["gene", "cell_type"], columns="region", values="expression", aggfunc="mean")
            figures["expression_heatmap"] = px.imshow(heat, aspect="auto", labels={"x": "Brain region", "y": "Gene / cell type", "color": "Expression"}, title="Expression atlas heatmap")
        condition = result.get("condition_comparison")
        if isinstance(condition, pd.DataFrame) and not condition.empty:
            figures["condition_change"] = px.bar(condition, x="gene", y="log2_fold_change_proxy", title="Condition-associated expression change proxy")
    elif feature_key == "advanced_neuro_omics":
        frame = result.get("feature_ranking")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["biomarker_ranking"] = px.scatter(frame, x="cohens_d", y="univariate_auc", size="priority", hover_name="feature", title="Biomarker effect and discrimination")
        calibration = result.get("calibration")
        if isinstance(calibration, pd.DataFrame) and not calibration.empty:
            figure = px.line(calibration, x="mean_probability", y="observed_fraction", markers=True, title="Cross-validated calibration")
            figure.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="ideal"))
            figures["calibration"] = figure
        predictions = result.get("cross_validated_predictions")
        if isinstance(predictions, pd.DataFrame) and not predictions.empty:
            figures["prediction_distribution"] = px.histogram(predictions, x="cross_validated_probability", color="group", marginal="box", title="Cross-validated probability distribution")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["effect_priority"] = px.scatter(frame, x="cohens_d", y="priority", color="missing_fraction", size="univariate_auc", hover_name="feature", title="Effect, missingness and biomarker priority")
    elif feature_key == "advanced_precision_neurology":
        frame = result.get("assignments")
        if isinstance(frame, pd.DataFrame) and {"pc1", "pc2", "cluster"}.issubset(frame.columns):
            figures["consensus_clusters"] = px.scatter(frame, x="pc1", y="pc2", color=frame["cluster"].astype(str), hover_name="subject_id", title="Consensus stratification")
        evaluation = result.get("cluster_evaluation")
        if isinstance(evaluation, pd.DataFrame) and not evaluation.empty:
            figures["cluster_stability"] = px.line(evaluation.sort_values("clusters"), x="clusters", y=["mean_silhouette", "mean_pairwise_ari", "selection_score"], markers=True, title="Cluster stability")
        consensus = result.get("consensus_matrix")
        if isinstance(consensus, pd.DataFrame) and not consensus.empty:
            figures["consensus_heatmap"] = px.imshow(consensus.to_numpy(), aspect="equal", labels={"x": "Subject", "y": "Subject", "color": "Consensus"}, title="Subject consensus matrix")
        loadings = result.get("pca_loadings")
        if isinstance(loadings, pd.DataFrame) and not loadings.empty:
            melted = loadings.melt(id_vars=["feature"], value_vars=[column for column in ("pc1", "pc2", "pc3") if column in loadings], var_name="component", value_name="loading")
            figures["feature_loadings"] = px.bar(melted, x="feature", y="loading", color="component", barmode="group", title="Feature contributions to principal components")
    elif feature_key == "advanced_neuro_pk":
        frame = result.get("curve")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["concentrations"] = px.line(frame, x="time_hours", y=["plasma_concentration_mg_l", "brain_concentration_mg_l"], title="Plasma and brain exposure")
            figures["occupancy"] = px.line(frame, x="time_hours", y=["kinetic_occupancy", "equilibrium_occupancy"], title="Time-dependent target occupancy")
    elif feature_key == "advanced_target_evidence":
        edges = result.get("edges")
        if isinstance(edges, pd.DataFrame) and not edges.empty:
            figures["evidence_edges"] = px.bar(edges, x="source", y="evidence_score", color="target", title="Target–disease evidence")
            nodes = sorted(set(edges["source"].astype(str)) | set(edges["target"].astype(str)))
            angle = np.linspace(0, 2 * np.pi, len(nodes), endpoint=False) if nodes else np.array([])
            positions = {node: (float(np.cos(value)), float(np.sin(value))) for node, value in zip(nodes, angle)}
            edge_x: list[float | None] = []
            edge_y: list[float | None] = []
            for row in edges.itertuples(index=False):
                x0, y0 = positions[str(row.source)]
                x1, y1 = positions[str(row.target)]
                edge_x.extend([x0, x1, None]); edge_y.extend([y0, y1, None])
            network = go.Figure()
            network.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines", hoverinfo="skip", name="Evidence links"))
            network.add_trace(go.Scatter(x=[positions[node][0] for node in nodes], y=[positions[node][1] for node in nodes], mode="markers+text", text=nodes, textposition="top center", name="Targets and diseases"))
            network.update_layout(title="Target–disease evidence network", showlegend=False, xaxis={"visible": False}, yaxis={"visible": False})
            figures["evidence_network"] = network
    elif feature_key == "advanced_trial_intelligence":
        frame = result.get("landscape")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["trial_landscape"] = px.bar(frame, x="phase_normalized", y="trials", color="status_normalized", title="CNS trial landscape")
        trials = result.get("trials")
        if isinstance(trials, pd.DataFrame) and not trials.empty:
            figures["trial_status"] = px.histogram(trials, x="status_normalized", color="phase_normalized", title="Trial status by phase")
            if "last_update_parsed" in trials:
                figures["trial_updates"] = px.scatter(trials, x="last_update_parsed", y="phase_normalized", color="stale_over_one_year", hover_name="trial_id_normalized", title="Trial update recency")
    elif feature_key == "epilepsy_diary":
        frame = result.get("daily_timeline")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["event_timeline"] = px.line(frame, x="date", y=["event_count", "rolling_7d_events"], title="Daily events and 7-day total")
            factors = [column for column in ("sleep_hours", "medication_adherence", "stress_score") if column in frame]
            if factors:
                figures["event_factor_space"] = px.scatter_matrix(frame, dimensions=["event_count", *factors], title="Diary factor relationships")
        correlations = result.get("factor_correlations")
        if isinstance(correlations, pd.DataFrame) and not correlations.empty:
            figures["factor_correlations"] = px.bar(correlations, x="factor", y="spearman_correlation", title="Event-factor correlations")
    elif feature_key == "movement_disorders":
        frame = result.get("candidate_steps")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["candidate_steps"] = px.scatter(frame, x="time_seconds", y="magnitude", title="Candidate movement peaks")
            figures["movement_peak_distribution"] = px.histogram(frame, x="magnitude", marginal="box", title="Candidate movement magnitude distribution")
        summary = result.get("signal_summary")
        if isinstance(summary, pd.DataFrame) and not summary.empty:
            figures["movement_metrics"] = px.bar(summary, x="metric", y="value", title="Movement signal metrics")
    elif feature_key == "autonomic_hrv":
        posture = result.get("posture_summary")
        if isinstance(posture, pd.DataFrame) and not posture.empty:
            figures["posture_hrv"] = px.bar(posture, x="posture", y=[column for column in ("mean_rr_ms", "sdnn_ms") if column in posture], barmode="group", title="HRV by posture")
        metrics = result.get("metrics")
        if isinstance(metrics, dict) and metrics:
            metric_frame = pd.DataFrame({"metric": list(metrics), "value": list(metrics.values())})
            metric_frame["value"] = pd.to_numeric(metric_frame["value"], errors="coerce")
            figures["hrv_metrics"] = px.bar(metric_frame.dropna(subset=["value"]), x="metric", y="value", title="Autonomic time-domain metrics")
    elif feature_key == "speech_language":
        samples = result.get("sample_summary")
        if isinstance(samples, pd.DataFrame) and not samples.empty:
            figures["speech_deviation"] = px.histogram(samples, x="feature_deviation", marginal="box", title="Sample-level multimodal speech deviation")
        qc = result.get("feature_qc")
        if isinstance(qc, pd.DataFrame) and not qc.empty:
            figures["speech_feature_qc"] = px.bar(qc, x="feature", y=[column for column in ("missing_fraction", "standard_deviation") if column in qc], barmode="group", title="Speech and language feature QC")
    elif feature_key == "neuro_oncology":
        samples = result.get("sample_summary")
        if isinstance(samples, pd.DataFrame) and not samples.empty:
            figures["oncology_sample_deviation"] = px.bar(samples.sort_values("multi_marker_deviation", ascending=False), x="sample_id", y="multi_marker_deviation", title="Multi-marker tumour-sample deviation")
        markers = result.get("marker_summary")
        if isinstance(markers, pd.DataFrame) and not markers.empty:
            figures["oncology_marker_summary"] = px.scatter(markers, x="mean_value", y="sd_value", size="samples", hover_name="marker", title="Marker-level mean and variability")
    elif feature_key == "neurodegeneration_progression":
        frame = result.get("subject_progression")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["progression_burden"] = px.bar(frame.head(30), x="subject_id", y="multimodal_change_burden", title="Multimodal change burden")
            slope_columns = [column for column in frame.columns if column.endswith("_annual_slope")]
            if slope_columns:
                heat = frame.set_index("subject_id")[slope_columns]
                figures["multimodal_slope_heatmap"] = px.imshow(heat, aspect="auto", labels={"x": "Modality", "y": "Subject", "color": "Annual slope"}, title="Subject-by-modality progression slopes")
    elif feature_key == "neuropathology":
        objects = result.get("objects")
        if isinstance(objects, pd.DataFrame) and not objects.empty:
            figures["object_area_distribution"] = px.histogram(objects, x="area_pixels", marginal="box", title="Candidate histology object areas")
            figures["object_shape"] = px.scatter(objects.head(3000), x="bbox_width", y="bbox_height", size="area_pixels", title="Candidate object dimensions")
    elif feature_key == "neurocritical_care":
        frame = result.get("timeline")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            numeric = [column for column in frame.select_dtypes(include="number").columns][:6]
            if numeric:
                figures["trend_timeline"] = px.line(frame, x="timestamp", y=numeric, title="Neurocritical research trends")
        summary = result.get("trend_summary")
        if isinstance(summary, pd.DataFrame) and not summary.empty:
            figures["trend_slopes"] = px.bar(summary, x="variable", y="slope_per_hour", color="candidate_change_points", title="Trend slopes and candidate changes")
    elif feature_key == "genomic_cohort_qc":
        frame = result.get("sample_qc")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["sample_flags"] = px.histogram(frame, x="review_flag_count", title="Sample review flags")
    elif feature_key == "single_cell_qc":
        frame = result.get("cell_qc")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["single_cell_qc"] = px.scatter(frame, x="library_size", y="detected_genes", color="low_quality_candidate", size="mitochondrial_fraction", title="Single-cell QC")
    elif feature_key == "spatial_qc":
        frame = result.get("local_spatial_qc")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["spatial_map"] = px.scatter(frame, x="x", y="y", color="value", size=frame["local_difference"].abs(), title="Spatial value and local difference")
    elif feature_key == "multiomics_qc":
        frame = result.get("pca_coordinates")
        if isinstance(frame, pd.DataFrame) and {"PC1", "PC2"}.issubset(frame.columns):
            color = "batch" if "batch" in frame else "group" if "group" in frame else None
            figures["multiomics_pca"] = px.scatter(frame, x="PC1", y="PC2", color=color, title="Multi-omics PCA")
    elif feature_key in {"microbiome_controls", "metagenomics_controls"}:
        frame = result.get("feature_qc")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            x = "control_prevalence" if "control_prevalence" in frame else _first_numeric(frame)
            y = "sample_prevalence" if "sample_prevalence" in frame else _first_numeric(frame, {x} if x else set())
            if x and y:
                figures["control_prevalence"] = px.scatter(frame, x=x, y=y, color="contamination_candidate", hover_name="feature" if "feature" in frame else None, title="Control prevalence review")
    elif feature_key == "compound_standardization":
        frame = result.get("compounds")
        if isinstance(frame, pd.DataFrame) and not frame.empty and {"molecular_weight", "logp"}.issubset(frame.columns):
            figures["chemical_space"] = px.scatter(frame[frame["valid"].fillna(False)], x="molecular_weight", y="logp", size="tpsa", color="lipinski_alert_count", hover_name="compound_id", title="Standardized chemical space")
    elif feature_key == "docking_validation":
        frame = result.get("pose_review")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            x = "rmsd" if "rmsd" in frame else "consensus_pose_score"
            figures["pose_review"] = px.scatter(frame, x=x, y="docking_score" if "docking_score" in frame else "score", color="ligand_id" if "ligand_id" in frame else None, size="interaction_support", title="Docking pose review")
    elif feature_key == "admet_calibration":
        frame = result.get("calibration")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figure = px.scatter(frame, x="predicted", y="measured", title="ADMET measured versus predicted")
            numeric = frame[["predicted", "measured"]].apply(pd.to_numeric, errors="coerce").dropna()
            if len(numeric) >= 2 and numeric["predicted"].nunique() > 1:
                slope, intercept = np.polyfit(numeric["predicted"].to_numpy(), numeric["measured"].to_numpy(), 1)
                x_line = np.linspace(float(numeric["predicted"].min()), float(numeric["predicted"].max()), 100)
                figure.add_trace(go.Scatter(x=x_line, y=slope * x_line + intercept, mode="lines", name="least-squares fit"))
            figures["calibration"] = figure
        domain = result.get("query_applicability_domain")
        if isinstance(domain, pd.DataFrame) and not domain.empty:
            figures["domain"] = px.bar(domain, x="compound_id", y="mahalanobis_distance", color="inside_applicability_domain", title="Applicability-domain distance")
    elif feature_key == "lead_optimization":
        frame = result.get("ranking")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            numeric = [column for column in frame.select_dtypes(include="number").columns if column not in {"internal_rank"}]
            if len(numeric) >= 2:
                figures["pareto"] = px.scatter(frame, x=numeric[0], y=numeric[1], color="pareto_front", size="internal_progression_score", hover_name="compound_id" if "compound_id" in frame else None, title="Multi-objective candidate space")
    elif feature_key == "protein_design":
        frame = result.get("candidate_qc")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["design_qc"] = px.scatter(frame, x="sequence_identity", y="design_review_score", size="mutation_count", color="conserved_position_violations", hover_name="candidate_id", title="Protein design review")
    elif feature_key == "antibody_developability":
        frame = result.get("developability")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["antibody_liabilities"] = px.bar(frame[frame["valid"].fillna(False)], x="antibody_id", y="liability_count", title="Antibody sequence liabilities")
    elif feature_key == "neoantigen":
        frame = result.get("ranking")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["neoantigen_ranking"] = px.scatter(frame, x="binding_affinity_nm", y="research_priority_score", color="normal_tissue_filter_flag", hover_name="peptide", title="Neoantigen research ranking", log_x=True)
    elif feature_key == "microscopy_qc":
        frame = result.get("channel_qc")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["channel_qc"] = px.bar(frame, x="channel", y=["focus_laplacian_variance", "saturation_fraction", "background_median"], barmode="group", title="Microscopy channel QC")
    elif feature_key == "plate_qc":
        frame = result.get("well_qc")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["plate_map"] = px.scatter(frame, x="column", y="row", color="measurement", symbol="control_type", facet_col="plate", title="Plate measurement map")
    elif feature_key == "bioprocess":
        frame = result.get("time_series")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            y = [column for column in ("biomass", "product", "substrate") if column in frame]
            figures["bioprocess_timeline"] = px.line(frame, x="time_hours", y=y, title="Bioprocess trajectory")
    elif feature_key == "organoid":
        frame = result.get("measurements")
        if isinstance(frame, pd.DataFrame) and not frame.empty and "time" in frame:
            figures["organoid_growth"] = px.line(frame, x="time", y="volume", color="organoid_id", title="Organoid volume trajectories")
    elif feature_key == "gene_therapy":
        frame = result.get("vector_qc")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["vector_capacity"] = px.bar(frame, x="vector_type", y=["length", "capacity"], barmode="group", title="Vector cargo capacity")
    elif feature_key == "experiment_planner":
        frame = result.get("run_plan")
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            figures["run_order"] = px.scatter(frame, x="run_order", y="block", color="group", symbol="record_type", title="Randomized experiment run order")
    if not figures:
        for key, value in result.items():
            if not isinstance(value, pd.DataFrame) or value.empty:
                continue
            numeric = [str(column) for column in value.select_dtypes(include="number").columns]
            categorical = [str(column) for column in value.columns if str(column) not in numeric]
            if numeric:
                preview = value.head(50).copy()
                x = categorical[0] if categorical else preview.index
                figures[key] = px.bar(preview, x=x, y=numeric[0], title=key.replace("_", " ").title())
                break
    return figures
