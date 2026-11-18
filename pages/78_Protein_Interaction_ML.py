from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.projects.ppi import (  # noqa: E402
    bootstrap_classification_metrics,
    build_feature_matrix,
    calibration_table,
    candidate_network_tables,
    candidate_ood_report,
    cold_start_validation,
    compare_algorithms,
    decision_curve_analysis,
    demo_ppi_pairs,
    load_ppi_model,
    network_topology_summary,
    pair_dataset_qc,
    precision_recall_points,
    score_candidate_pairs,
    serialize_ppi_model,
    split_leakage_audit,
    threshold_analysis,
    train_and_score_ppi_classifier,
)
from biointel.projects.professional import (  # noqa: E402
    QualityGate,
    model_card_payload,
    overall_quality_score,
    quality_gate_table,
)
from biointel.projects.reporting import build_project_bundle, build_run_manifest  # noqa: E402
from biointel.projects.run_registry import register_run  # noqa: E402
from biointel.ui.components import (  # noqa: E402
    metric_cards,
    scientific_boundary_banner,
    smart_dataframe,
    smart_json,
)
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title  # noqa: E402
from biointel.ui.workflow import (  # noqa: E402
    analysis_run,
    read_uploaded_table,
    render_methodology,
    render_upload_preflight,
)

PROJECT_CODE = "BIO-PPI-ML"
RUN_REGISTRY = ROOT / "reports" / "biotechnology_project_runs.sqlite3"
PROJECT_NAME = "Machine-Learning Algorithms for Protein–Protein Interaction Prediction"
BOUNDARY = (
    "PPI probabilities are computational screening outputs, not experimental interaction evidence. "
    "Protein-disjoint external validation and orthogonal wet-lab confirmation are required before biological claims."
)


def _network_figure(edges: pd.DataFrame, nodes: pd.DataFrame) -> go.Figure:
    if edges.empty or nodes.empty:
        return go.Figure().update_layout(
            title="No interactions meet the selected network threshold"
        )
    proteins = nodes["protein"].astype(str).tolist()
    positions = {
        protein: (
            math.cos(2 * math.pi * index / len(proteins)),
            math.sin(2 * math.pi * index / len(proteins)),
        )
        for index, protein in enumerate(proteins)
    }
    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for row in edges.itertuples(index=False):
        if row.protein_a not in positions or row.protein_b not in positions:
            continue
        x0, y0 = positions[row.protein_a]
        x1, y1 = positions[row.protein_b]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(x=edge_x, y=edge_y, mode="lines", hoverinfo="skip", line={"width": 1})
    )
    figure.add_trace(
        go.Scatter(
            x=[positions[name][0] for name in proteins],
            y=[positions[name][1] for name in proteins],
            mode="markers+text",
            text=proteins,
            textposition="top center",
            customdata=nodes[["degree", "mean_probability", "max_probability"]],
            hovertemplate="Protein=%{text}<br>Degree=%{customdata[0]}<br>Mean probability=%{customdata[1]:.3f}<br>Max probability=%{customdata[2]:.3f}<extra></extra>",
            marker={
                "size": 10 + nodes["degree"].clip(upper=20) * 2,
                "showscale": True,
                "color": nodes["mean_probability"],
            },
        )
    )
    figure.update_layout(
        title="Candidate interaction network",
        showlegend=False,
        xaxis={"visible": False},
        yaxis={"visible": False},
        height=560,
    )
    return figure


st.set_page_config(page_title="Protein Interaction ML · BioIntel AI", page_icon="🔗", layout="wide")
apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/78_Protein_Interaction_ML.py", key_prefix="78_protein_interaction_ml", expanded=False)

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("ppi_ml", key_prefix="step116_78_Protein_Interaction_ML_ppi_ml_1", expanded=False)
hero(
    PROJECT_NAME,
    "A complete PPI research workbench for dataset quality control, sequence-pair feature engineering, algorithm benchmarking, held-out evaluation, calibration, threshold selection, candidate ranking and network exploration.",
    eyebrow="Biotechnology Project 01 · Professional workbench",
    chips=[
        "Dataset QC",
        "Model benchmarking",
        "Calibration",
        "Candidate network",
        "Reproducible bundle",
    ],
)
scientific_boundary_banner(source_kind="demo_reference", release_eligible=False, message=BOUNDARY)

render_methodology(
    method='Sequence-derived pair features, calibrated classifiers, threshold analysis, cold-start checks and reusable inference artifacts.',
    assumptions=[
        'Labels are reliable and protein identifiers map consistently to sequences.',
    ],
    limitations=[
        'Sequence-only features omit structure, localization and biological context.',
        'Random-pair performance can overestimate protein-disjoint generalization.',
    ],
    validation=[
        'Prioritize protein-disjoint and independent external evaluation.',
        'Confirm high-priority interactions with orthogonal experiments.',
    ],
)

with st.expander("Required data contract and workflow", expanded=False):
    smart_dataframe(
        pd.DataFrame(
            [
                ("protein_a / protein_b", "Unique protein identifiers", "Required"),
                (
                    "sequence_a / sequence_b",
                    "Amino-acid sequences using the standard alphabet",
                    "Required",
                ),
                ("label", "0 = non-interaction, 1 = interaction", "Training only"),
                ("source", "Dataset or experiment source identifier", "Recommended"),
            ],
            columns=["Field", "Meaning", "Requirement"],
        ),
        height=250,
    )

input_tab, candidates_tab, settings_tab = st.tabs(
    ["1 · Training data", "2 · Candidate pairs", "3 · Model settings"]
)
with input_tab:
    source = st.radio(
        "Training source",
        ["Deterministic demo", "Upload labelled CSV"],
        horizontal=True,
        key="ppi_source",
    )
    uploaded = st.file_uploader(
        "Labelled protein-pair table",
        type=["csv", "tsv", "xlsx", "xlsm", "zip"],
        help="Required columns: protein_a, protein_b, sequence_a, sequence_b, label.",
        disabled=source == "Deterministic demo",
        key="ppi_training_upload",
    )
    training_upload_profile = render_upload_preflight(
        uploaded, key="ppi_training", allowed_extensions=["csv", "tsv", "xlsx", "xlsm", "zip"], soft_limit_mb=20, hard_limit_mb=150
    )
    demo_size = st.slider(
        "Demo pair count", 80, 500, 160, 20, disabled=source != "Deterministic demo"
    )
    training = (
        demo_ppi_pairs(demo_size)
        if source == "Deterministic demo"
        else (read_uploaded_table(uploaded) if uploaded else None)
    )
    if training is not None:
        qc_table, qc_summary = pair_dataset_qc(training)
        metric_cards(
            [
                ("Pairs", f"{qc_summary['pairs']:,}", None),
                ("Unique proteins", f"{qc_summary['unique_proteins']:,}", None),
                ("Duplicate pairs", f"{qc_summary['duplicate_pairs']:,}", None),
                ("ID conflicts", f"{qc_summary['identifier_sequence_conflicts']:,}", None),
            ]
        )
        left, right = st.columns([1, 1.4])
        with left:
            smart_dataframe(qc_table, height=300, key="ppi_qc_table")
        with right:
            label_counts = (
                training["label"].value_counts().rename_axis("label").reset_index(name="pairs")
                if "label" in training
                else pd.DataFrame()
            )
            if not label_counts.empty:
                st.plotly_chart(
                    px.bar(label_counts, x="label", y="pairs", title="Class balance"),
                    width="stretch",
                )

with candidates_tab:
    candidate_mode = st.radio(
        "Candidate source",
        ["Demo candidates", "Upload candidate CSV", "Use editable table"],
        horizontal=True,
    )
    if training is not None:
        default_candidates = (
            training.drop(columns=["label"], errors="ignore")
            .sample(min(20, len(training)), random_state=5)
            .reset_index(drop=True)
        )
    else:
        default_candidates = demo_ppi_pairs(20).drop(columns=["label"], errors="ignore")
    candidate_upload = st.file_uploader(
        "Candidate-pair table",
        type=["csv", "tsv", "xlsx", "xlsm", "zip"],
        key="ppi_candidate_upload",
        disabled=candidate_mode != "Upload candidate CSV",
        help="Required columns: protein_a, protein_b, sequence_a, sequence_b.",
    )
    candidate_upload_profile = render_upload_preflight(
        candidate_upload, key="ppi_candidates", allowed_extensions=["csv", "tsv", "xlsx", "xlsm", "zip"], soft_limit_mb=20, hard_limit_mb=150
    )
    if candidate_mode == "Upload candidate CSV" and candidate_upload:
        candidates = read_uploaded_table(candidate_upload)
    elif candidate_mode == "Use editable table":
        candidates = st.data_editor(
            default_candidates.head(12),
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            key="ppi_candidate_editor",
        )
    else:
        candidates = default_candidates
    smart_dataframe(candidates.head(100), height=320, key="ppi_candidate_preview")

with settings_tab:
    with st.form("ppi_equal_depth_form"):
        row1 = st.columns(4)
        algorithm = row1[0].selectbox(
            "Final algorithm", ["Random forest", "Logistic regression", "Calibrated random forest"]
        )
        test_size = row1[1].slider("Held-out fraction", 0.15, 0.40, 0.25, 0.05)
        decision_threshold = row1[2].slider("Primary decision threshold", 0.10, 0.90, 0.50, 0.05)
        network_threshold = row1[3].slider("Candidate network threshold", 0.30, 0.95, 0.65, 0.05)
        row2 = st.columns(3)
        random_state = row2[0].number_input("Random seed", 1, 9999, 42)
        calibration_bins = row2[1].slider("Calibration bins", 4, 15, 8)
        show_full_features = row2[2].toggle("Retain full feature matrix", value=True)
        run = st.form_submit_button("Run complete PPI workbench", type="primary", width="stretch")

section_title("Saved-model inference", "📦")
with st.expander("Load a previously exported PPI model and score candidate pairs", expanded=False):
    allow_legacy_model = st.checkbox(
        "Allow migration of a trusted legacy .joblib export",
        value=False,
        help="Legacy pickle/joblib files can execute code while loading. Keep this disabled for files from other people or unknown sources.",
    )
    saved_model_upload = st.file_uploader(
        "PPI model bundle (.bioippimodel)" + (" or trusted legacy .joblib" if allow_legacy_model else ""),
        type=["bioippimodel", "joblib"] if allow_legacy_model else ["bioippimodel"],
        key="ppi_saved_model_upload",
    )
    inference_candidates = st.file_uploader(
        "Candidate pairs for inference",
        type=["csv", "tsv", "xlsx", "xlsm", "zip"],
        key="ppi_inference_candidates",
    )
    model_upload_profile = render_upload_preflight(
        saved_model_upload, key="ppi_saved_model", allowed_extensions=["bioippimodel", "joblib"] if allow_legacy_model else ["bioippimodel"], soft_limit_mb=50, hard_limit_mb=250
    )
    inference_upload_profile = render_upload_preflight(
        inference_candidates, key="ppi_inference_table", allowed_extensions=["csv", "tsv", "xlsx", "xlsm", "zip"], soft_limit_mb=20, hard_limit_mb=150
    )
    inference_run = st.button(
        "Run inference-only scoring",
        disabled=saved_model_upload is None or inference_candidates is None,
        width="stretch",
    )
    if inference_run and saved_model_upload and inference_candidates:
        try:
            with analysis_run("Validating the model contract and scoring candidate pairs"):
                loaded_model = load_ppi_model(saved_model_upload.getvalue(), allow_legacy=allow_legacy_model)
                inference_frame = read_uploaded_table(inference_candidates)
                inference_scores = score_candidate_pairs(loaded_model, inference_frame)
            metric_cards(
                [
                    ("Candidates", f"{len(inference_scores):,}", None),
                    ("Threshold", f"{loaded_model.decision_threshold:.2f}", None),
                    (
                        "Predicted interactions",
                        f"{int(inference_scores['predicted_label'].sum()):,}",
                        None,
                    ),
                    (
                        "Model fingerprint",
                        loaded_model.model_fingerprint[:12] or "Unavailable",
                        None,
                    ),
                ]
            )
            smart_dataframe(inference_scores, height=420, key="ppi_inference_scores")
            st.download_button(
                "Download inference scores",
                inference_scores.to_csv(index=False),
                "ppi_inference_scores.csv",
                "text/csv",
                width="stretch",
            )
        except Exception as exc:
            st.error(f"Saved-model inference could not run: {exc}")

if training is None:
    st.info(
        "Upload a labelled protein-pair table to enable training, or switch to the deterministic demo."
    )
    st.stop()

if run:
    try:
        with analysis_run(
            "Validating data, engineering pair features and benchmarking algorithms"
        ):
            qc_table, qc_summary = pair_dataset_qc(training)
            comparison = compare_algorithms(training, random_state=int(random_state))
            result, scored = train_and_score_ppi_classifier(
                training,
                pd.DataFrame(candidates),
                algorithm=algorithm,
                random_state=int(random_state),
                test_size=float(test_size),
                decision_threshold=float(decision_threshold),
            )
            model_artifact = serialize_ppi_model(result)
            features = build_feature_matrix(training)
            pr_points = precision_recall_points(result.predictions)
            thresholds = threshold_analysis(result.predictions)
            calibration = calibration_table(result.predictions, bins=int(calibration_bins))
            leakage = split_leakage_audit(training, result.predictions)
            network_edges, network_nodes = candidate_network_tables(
                scored, threshold=float(network_threshold)
            )
            parameters = {
                "algorithm": algorithm,
                "held_out_fraction": test_size,
                "decision_threshold": decision_threshold,
                "network_threshold": network_threshold,
                "random_seed": int(random_state),
                "calibration_bins": int(calibration_bins),
            }
            outputs = {
                "algorithm_comparison": comparison,
                "held_out_predictions": result.predictions,
                "roc_curve": result.roc_points,
                "precision_recall_curve": pr_points,
                "threshold_analysis": thresholds,
                "calibration": calibration,
                "feature_importance": result.feature_importance,
                "candidate_scores": scored,
                "candidate_network_edges": network_edges,
                "candidate_network_nodes": network_nodes,
                "split_leakage_audit": leakage,
                "dataset_qc": qc_table,
            }
            if show_full_features:
                outputs["feature_matrix"] = features
            bundle = build_project_bundle(
                project_code=PROJECT_CODE,
                project_name=PROJECT_NAME,
                parameters=parameters,
                inputs={"training_pairs": training, "candidate_pairs": pd.DataFrame(candidates)},
                outputs=outputs,
                scientific_boundary=BOUNDARY,
                notes="Pair-split metrics are exploratory. Use protein-disjoint and independent external validation for evidence-grade evaluation.",
            )
            try:
                cold_metrics, cold_predictions = cold_start_validation(
                    training,
                    algorithm=algorithm,
                    random_state=int(random_state),
                    decision_threshold=float(decision_threshold),
                )
            except ValueError as exc:
                cold_metrics = pd.DataFrame(
                    [
                        {
                            "validation_scheme": "protein_disjoint",
                            "status": "not_available",
                            "reason": str(exc),
                        }
                    ]
                )
                cold_predictions = pd.DataFrame()
            bootstrap_metrics = bootstrap_classification_metrics(
                result.predictions,
                random_state=int(random_state),
                decision_threshold=float(decision_threshold),
            )
            ood = candidate_ood_report(training, pd.DataFrame(candidates))
            decision_curve = decision_curve_analysis(result.predictions)
            topology = network_topology_summary(network_edges, network_nodes)
            outputs.update(
                {
                    "protein_disjoint_metrics": cold_metrics,
                    "protein_disjoint_predictions": cold_predictions,
                    "bootstrap_metric_intervals": bootstrap_metrics,
                    "candidate_ood_audit": ood,
                    "decision_curve": decision_curve,
                    "network_topology": topology,
                }
            )
            cold_auc = (
                float(cold_metrics.iloc[0].get("roc_auc", 0.0)) if not cold_metrics.empty else 0.0
            )
            calibration_error = float(
                calibration["absolute_calibration_error"].mul(calibration["pairs"]).sum()
                / max(calibration["pairs"].sum(), 1)
            )
            gates = quality_gate_table(
                [
                    QualityGate(
                        "PPI-DATA",
                        "Dataset integrity",
                        "pass"
                        if qc_summary.get("identifier_sequence_conflicts", 0) == 0
                        and qc_summary.get("conflicting_label_pairs", 0) == 0
                        else "block",
                        100.0,
                        f"{len(training)} labelled rows; {qc_summary.get('unique_proteins', 0)} proteins; {qc_summary.get('conflicting_label_pairs', 0)} conflicting pairs",
                        "Resolve identifier/sequence conflicts and contradictory pair labels before interpretation.",
                    ),
                    QualityGate(
                        "PPI-PAIR",
                        "Held-out pair performance",
                        "pass" if result.metrics["roc_auc"] >= 0.75 else "review",
                        100.0 * result.metrics["roc_auc"],
                        f"ROC AUC {result.metrics['roc_auc']:.3f}",
                        "Increase independent labelled data when performance is unstable.",
                    ),
                    QualityGate(
                        "PPI-COLD",
                        "Protein-disjoint validation",
                        "pass" if cold_auc >= 0.70 else "review",
                        100.0 * cold_auc,
                        f"Cold-start ROC AUC {cold_auc:.3f}"
                        if cold_auc
                        else "Cold-start split unavailable",
                        "Use species/protein-family-disjoint external validation.",
                    ),
                    QualityGate(
                        "PPI-CAL",
                        "Probability calibration",
                        "pass" if calibration_error <= 0.10 else "review",
                        max(0.0, 100.0 * (1.0 - calibration_error)),
                        f"Weighted calibration error {calibration_error:.3f}",
                        "Recalibrate on representative independent data.",
                    ),
                    QualityGate(
                        "PPI-OOD",
                        "Candidate domain coverage",
                        "pass" if (ood["ood_status"] == "high").sum() == 0 else "review",
                        100.0 * float((ood["ood_status"] != "high").mean()),
                        f"{int((ood['ood_status'] == 'high').sum())} high-OOD candidates",
                        "Treat high-OOD candidates as low-confidence hypotheses.",
                    ),
                ]
            )
            manifest = build_run_manifest(
                project_code=PROJECT_CODE,
                project_name=PROJECT_NAME,
                parameters=parameters,
                inputs={"training_pairs": training, "candidate_pairs": pd.DataFrame(candidates)},
                outputs=outputs,
                scientific_boundary=BOUNDARY,
            )
            model_card = model_card_payload(
                project_code=PROJECT_CODE,
                title=PROJECT_NAME,
                intended_use="Prioritize candidate protein pairs for research follow-up.",
                out_of_scope=[
                    "Experimental interaction claims",
                    "Clinical decisions",
                    "Species transfer without validation",
                ],
                methodology=[
                    "Sequence-derived pair features",
                    algorithm,
                    "Pair-split and protein-disjoint evaluation",
                    "Calibration, OOD and decision-curve review",
                ],
                metrics={
                    **result.metrics,
                    "cold_start_roc_auc": cold_auc,
                    "weighted_calibration_error": calibration_error,
                },
                validation=[
                    "Stratified held-out pair split",
                    "Protein-disjoint split when feasible",
                    "Bootstrap confidence intervals",
                    "Candidate domain audit",
                ],
                limitations=[
                    BOUNDARY,
                    "Feature representation is sequence-composition based and does not encode structure, localization or experimental context.",
                ],
                quality_gates=gates,
                run_fingerprint=manifest["run_fingerprint"],
            )
            bundle = build_project_bundle(
                project_code=PROJECT_CODE,
                project_name=PROJECT_NAME,
                parameters=parameters,
                inputs={"training_pairs": training, "candidate_pairs": pd.DataFrame(candidates)},
                outputs=outputs,
                scientific_boundary=BOUNDARY,
                notes="Deep-validation PPI research bundle.",
                quality_gates=gates,
                summary={
                    "Training pairs": len(training),
                    "Candidate pairs": len(candidates),
                    "Pair ROC AUC": round(result.metrics["roc_auc"], 4),
                    "Cold-start ROC AUC": round(cold_auc, 4),
                    "Quality score": round(
                        overall_quality_score(
                            [
                                QualityGate(
                                    row.gate_id,
                                    row.name,
                                    row.status,
                                    row.score,
                                    row.evidence,
                                    row.recommendation,
                                )
                                for row in gates.itertuples(index=False)
                            ]
                        ),
                        2,
                    ),
                },
                methods=model_card["methodology"],
                model_card=model_card,
            )
            quality_score = float(
                gates.assign(
                    weight=gates["status"]
                    .map({"pass": 1.0, "review": 0.6, "block": 0.0})
                    .fillna(0.0)
                )
                .eval("score * weight")
                .mean()
            )
            register_run(
                RUN_REGISTRY,
                run_fingerprint=manifest["run_fingerprint"],
                project_code=PROJECT_CODE,
                project_name=PROJECT_NAME,
                status="qualified" if (gates["status"] == "block").sum() == 0 else "blocked",
                quality_score=quality_score,
                input_rows=len(training) + len(candidates),
                output_rows=sum(len(frame) for frame in outputs.values()),
                parameters=parameters,
                metrics={**result.metrics, "cold_start_roc_auc": cold_auc},
            )
        st.session_state["ppi_equal_depth_result"] = {
            "comparison": comparison,
            "result": result,
            "scored": scored,
            "features": features,
            "pr": pr_points,
            "thresholds": thresholds,
            "calibration": calibration,
            "leakage": leakage,
            "network_edges": network_edges,
            "network_nodes": network_nodes,
            "qc": qc_table,
            "bundle": bundle,
            "manifest": manifest,
            "parameters": parameters,
            "cold_metrics": cold_metrics,
            "cold_predictions": cold_predictions,
            "bootstrap_metrics": bootstrap_metrics,
            "ood": ood,
            "decision_curve": decision_curve,
            "topology": topology,
            "quality_gates": gates,
            "model_card": model_card,
            "model_artifact": model_artifact,
        }
        st.toast("PPI workbench completed", icon="✅")
    except Exception as exc:
        st.error(f"PPI workbench could not run: {exc}")

payload = st.session_state.get("ppi_equal_depth_result")
if payload:
    result = payload["result"]
    metric_cards(
        [
            ("ROC AUC", f"{result.metrics['roc_auc']:.3f}", "Held-out pair split"),
            ("Balanced accuracy", f"{result.metrics['balanced_accuracy']:.3f}", None),
            ("F1 score", f"{result.metrics['f1']:.3f}", None),
            ("Candidates scored", f"{len(payload['scored']):,}", None),
        ]
    )
    tabs = st.tabs(
        [
            "Executive summary",
            "Algorithm benchmark",
            "Evaluation curves",
            "Threshold & calibration",
            "Interpretability",
            "Candidate predictions",
            "Interaction network",
            "Data & leakage QC",
            "Deep validation & assurance",
            "Exports & model card",
        ]
    )
    with tabs[0]:
        section_title("Project outcome", "◎")
        best_algorithm = payload["comparison"].iloc[0]
        summary = pd.DataFrame(
            [
                ("Selected algorithm", result.algorithm),
                ("Best cross-validated algorithm", best_algorithm["algorithm"]),
                ("Training pairs", int(result.metrics["training_pairs"])),
                ("Held-out pairs", int(result.metrics["test_pairs"])),
                ("High-confidence candidate edges", len(payload["network_edges"])),
                ("Run fingerprint", payload["manifest"]["run_fingerprint"]),
            ],
            columns=["Measure", "Value"],
        )
        smart_dataframe(summary, height=310)
        insight_callout("Evidence interpretation", result.warning or BOUNDARY, "warning")
    with tabs[1]:
        st.plotly_chart(
            px.bar(
                payload["comparison"],
                x="algorithm",
                y=["roc_auc", "balanced_accuracy", "f1", "precision", "recall"],
                barmode="group",
                title="Cross-validated algorithm comparison",
            ),
            width="stretch",
        )
        smart_dataframe(payload["comparison"], height=280)
    with tabs[2]:
        left, right = st.columns(2)
        with left:
            roc = result.roc_points.copy()
            st.plotly_chart(
                px.line(
                    roc, x="false_positive_rate", y="true_positive_rate", title="Held-out ROC curve"
                ),
                width="stretch",
            )
        with right:
            st.plotly_chart(
                px.line(
                    payload["pr"],
                    x="recall",
                    y="precision",
                    title="Held-out precision–recall curve",
                ),
                width="stretch",
            )
        confusion = pd.DataFrame(
            result.confusion, index=["Actual 0", "Actual 1"], columns=["Predicted 0", "Predicted 1"]
        )
        st.plotly_chart(
            px.imshow(
                confusion,
                text_auto=True,
                title=f"Confusion matrix at threshold {result.decision_threshold:.2f}",
            ),
            width="stretch",
        )
        smart_dataframe(result.predictions, height=420)
    with tabs[3]:
        st.plotly_chart(
            px.line(
                payload["thresholds"],
                x="threshold",
                y=["precision", "recall", "specificity", "f1", "balanced_accuracy"],
                title="Decision-threshold trade-offs",
            ),
            width="stretch",
        )
        left, right = st.columns([1.2, 1])
        with left:
            st.plotly_chart(
                px.scatter(
                    payload["calibration"],
                    x="mean_predicted_probability",
                    y="observed_interaction_rate",
                    size="pairs",
                    hover_name="probability_bin",
                    title="Probability calibration",
                ),
                width="stretch",
            )
        with right:
            selected = payload["thresholds"].iloc[
                (payload["thresholds"]["threshold"] - payload["parameters"]["decision_threshold"])
                .abs()
                .argsort()[:1]
            ]
            smart_dataframe(selected, height=180)
            smart_dataframe(payload["calibration"], height=300)
    with tabs[4]:
        st.plotly_chart(
            px.bar(
                result.feature_importance.sort_values("importance"),
                x="importance",
                y="feature",
                orientation="h",
                title="Global feature importance",
            ),
            width="stretch",
        )
        smart_dataframe(result.feature_importance, height=400)
        with st.expander("Engineered pair-feature matrix", expanded=False):
            smart_dataframe(payload["features"], height=500)
    with tabs[5]:
        minimum_probability = st.slider(
            "Minimum displayed probability", 0.0, 1.0, 0.0, 0.05, key="ppi_result_filter"
        )
        filtered_scores = payload["scored"][
            payload["scored"]["interaction_probability"] >= minimum_probability
        ]
        st.plotly_chart(
            px.histogram(
                payload["scored"],
                x="interaction_probability",
                color="confidence_band",
                nbins=20,
                title="Candidate probability distribution",
            ),
            width="stretch",
        )
        smart_dataframe(filtered_scores, height=520)
        st.download_button(
            "Download candidate scores",
            payload["scored"].to_csv(index=False),
            "ppi_candidate_scores.csv",
            "text/csv",
            width="stretch",
        )
    with tabs[6]:
        st.plotly_chart(
            _network_figure(payload["network_edges"], payload["network_nodes"]), width="stretch"
        )
        left, right = st.columns(2)
        with left:
            smart_dataframe(payload["network_nodes"], height=360)
        with right:
            smart_dataframe(payload["network_edges"], height=360)
    with tabs[7]:
        left, right = st.columns(2)
        with left:
            section_title("Dataset quality", "✓")
            smart_dataframe(payload["qc"], height=390)
        with right:
            section_title("Split leakage audit", "⌁")
            smart_dataframe(payload["leakage"], height=390)
        insight_callout(
            "Why this matters",
            "A random pair split can share the same proteins between train and test sets. This may overestimate generalization to unseen proteins.",
            "warning",
        )
    with tabs[8]:
        left, right = st.columns(2)
        with left:
            section_title("Protein-disjoint generalization", "⌁")
            smart_dataframe(payload["cold_metrics"], height=220)
            smart_dataframe(payload["bootstrap_metrics"], height=300)
        with right:
            section_title("Candidate domain & network assurance", "◉")
            st.plotly_chart(
                px.histogram(
                    payload["ood"],
                    x="nearest_training_distance",
                    color="ood_status",
                    title="Candidate out-of-domain distances",
                ),
                width="stretch",
            )
            smart_dataframe(payload["topology"], height=250)
        st.plotly_chart(
            px.line(
                payload["decision_curve"],
                x="threshold",
                y=["model_net_benefit", "treat_all_net_benefit", "treat_none_net_benefit"],
                title="Decision-curve screening utility",
            ),
            width="stretch",
        )
        smart_dataframe(payload["quality_gates"], height=360)
        insight_callout(
            "Qualification boundary",
            "Passing internal gates means the software run is coherent; it does not convert predictions into experimental PPI evidence.",
            "warning",
        )
    with tabs[9]:
        smart_json(
            payload["model_card"],
            title="Professional model card",
            download_name="ppi_model_card.json",
            key="ppi_model_card_download",
        )
        smart_json(
            payload["manifest"],
            title="Reproducibility manifest",
            download_name="ppi_manifest.json",
            key="ppi_manifest_download",
        )
        st.download_button(
            "Download complete PPI project bundle (.zip)",
            payload["bundle"],
            "BIO-PPI-ML_project_bundle.zip",
            "application/zip",
            width="stretch",
            key="ppi_bundle_download",
        )
        st.download_button(
            "Download reusable fitted PPI model bundle",
            payload["model_artifact"],
            f"ppi_model_{result.model_fingerprint[:16]}.bioippimodel",
            "application/octet-stream",
            width="stretch",
            key="ppi_model_download",
        )
else:
    section_title("Professional capability map", "▦")
    smart_dataframe(
        pd.DataFrame(
            [
                (
                    "Input & QC",
                    "Labelled pair schema, amino-acid validation, duplicate/self-pair and identifier conflict audits",
                ),
                (
                    "Modelling",
                    "Sequence-derived pair features, three final algorithms and cross-validated comparison",
                ),
                (
                    "Evaluation",
                    "ROC, precision–recall, confusion matrix, threshold analysis and calibration",
                ),
                (
                    "Interpretability",
                    "Global feature importance and transparent pair-feature matrix",
                ),
                (
                    "Screening",
                    "Candidate probability ranking, confidence bands and interaction-network exploration",
                ),
                ("Reproducibility", "SHA-256 input/output manifest and downloadable project ZIP"),
            ],
            columns=["Layer", "Implemented capability"],
        ),
        height=360,
    )

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
