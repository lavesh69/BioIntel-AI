from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from biointel.neuro_cns.catalog import MODULES, MODULE_BY_KEY, WORKSPACES, module_rows, workspace_modules
from biointel.neuro_cns.visuals_v209 import portfolio_figures
from biointel.demo_coverage_v209.ui import render_generated_demo_panel
from biointel.scientific_resources_v209.ui import render_scientific_resources_panel
from biointel.neuro_cns.advanced import (
    ADVANCED_FEATURES,
    aggregation_mutation_engineering,
    brain_digital_twin_viewer,
    compound_optimization_board,
    dose_to_effect_simulator,
    experimental_model_selection_assistant,
    multiomics_disease_signature_builder,
    neurophysiology_review_board,
    rare_neurological_disease_board,
    safety_margin_matrix,
)
from biointel.neuro_cns.chemistry import (
    bbb_batch,
    bbb_permeability,
    bbb_reference_validation,
    blood_csf_barrier,
    cns_adme_transporters,
    cns_drug_adme_workflow,
    cns_drug_likeness,
    receptor_occupancy,
    receptor_occupancy_kinetics,
    simulate_brain_exposure,
    simulate_brain_exposure_population,
)
from biointel.neuro_cns.clinical import trial_intelligence
from biointel.neuro_cns.completion import (
    COMPLETION_FEATURES,
    build_resource_binding,
    dataset_drift_monitor,
    deidentify_frame,
    leakage_split_audit,
    multisite_reproducibility_analyzer,
    persist_resource_binding,
    privacy_scan_frame,
    professional_pdf_report,
    release_evidence_pack,
    specialist_engine_inventory,
    study_design_power_planner,
)
from biointel.neuro_cns.consistency import evaluate_results, result_quality_summary
from biointel.neuro_cns.hardening import safe_execute
from biointel.neuro_cns.max_potential import (
    MAX_POTENTIAL_FEATURES,
    applicability_domain_inspector,
    batch_pipeline_orchestrator,
    benchmark_validation_center,
    contradiction_resolution_board,
    evidence_knowledge_graph,
    failure_recovery_center,
    maximum_potential_release_dashboard,
    resource_qualification_manager,
    uncertainty_sensitivity_lab,
)
from biointel.neuro_cns.projects import list_projects, load_project, load_project_bytes, project_json, save_project
from biointel.neuro_cns.production import (
    PRODUCTION_FEATURES,
    authorize_action,
    compute_qualification_profile,
    controlled_release_status,
    crash_diagnostics_bundle,
    create_review_record,
    create_update_snapshot,
    demo_pack_zip,
    load_demo_asset,
    official_resource_plan,
    publication_export_pack,
    role_access_matrix,
    specialist_engine_installation_plan,
    validate_benchmark_registry,
    verify_demo_pack,
)
from biointel.neuro_cns.demo_showcase import run_complete_demo_showcase
from biointel.neuro_cns.provenance import resource_registry_frame
from biointel.neuro_cns.recommendations import gate_summary, recommendation_frame
from biointel.neuro_cns.workflows import DISEASE_WORKFLOWS, compound_to_clinic_workflow, disease_workflow_plan, target_to_translation_workflow
from biointel.neuro_cns.demos import (
    DEMO_AGGREGATION_SEQUENCE,
    DEMO_GPCR_SEQUENCE,
    DEMO_PROTEIN_SEQUENCE,
    DEMO_SMILES,
    binding_profile,
    cohort,
    eeg,
    omics,
    roi_timeseries,
    trials,
    variants,
)
from biointel.neuro_cns.genetics import parse_vcf_text, prioritize_variants, variant_interpretation_workflow
from biointel.neuro_cns.imaging import connectivity_from_timeseries, load_dicom_series, load_image_payload, optional_adapter_status, profile_image_array, volume_qc_workflow
from biointel.neuro_cns.omics import biomarker_discovery, biomarker_discovery_workflow
from biointel.neuro_cns.precision import precision_neurology_workflow, stratify_research_cohort
from biointel.neuro_cns.reporting import bundle_html, bundle_json, bundle_markdown, bundle_pdf
from biointel.neuro_cns.safety import aggregation_risk, cns_side_effects, off_target_neurotoxicity, off_target_safety_workflow
from biointel.neuro_cns.signals import analyze_neural_signals, load_signal_payload, neural_signal_workflow, optional_signal_adapter_status
from biointel.neuro_cns.targets import (
    brain_expression_profile,
    expression_atlas_analysis,
    classify_gpcr,
    classify_ion_channel,
    disease_target_table,
    model_organism_cross_reference,
    neuroinflammation_lookup,
    pathway_mapping,
    sequence_topology_track,
    target_evidence_graph,
    target_mechanism_workflow,
    target_registry_frame,
    target_tagging,
)
from biointel.neuro_cns.ingestion import read_tabular_bytes
from biointel.neuro_cns.visuals import (
    chemistry_figures,
    connectivity_figures,
    expression_atlas_figures,
    imaging_slice_figures,
    omics_figures,
    pk_figures,
    precision_figures,
    safety_figures,
    sequence_topology_figure,
    signal_figures,
    target_evidence_graph_figure,
    trial_figures,
    variant_figures,
)
from biointel.neuro_cns.ui_v207 import render_step207_neuro_feature, render_step207_neuro_portfolio
from biointel.module_features_v208.ui import render_feature_center as render_v208_feature_center, render_single_feature as render_v208_single_feature
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json, workflow_status
from biointel.ui.theme import hero, section_title


RESULT_STATE_KEY = "_biointel_neuro_cns_results"
ERROR_STATE_KEY = "_biointel_neuro_cns_errors"
EXECUTION_STATE_KEY = "_biointel_neuro_cns_execution"


def _result_store() -> dict[str, Any]:
    current = st.session_state.get(RESULT_STATE_KEY)
    if not isinstance(current, dict):
        current = {}
        st.session_state[RESULT_STATE_KEY] = current
    return current


def _save_result(key: str, result: Any) -> None:
    store = _result_store()
    store[key] = result
    st.session_state[RESULT_STATE_KEY] = store


def _safe_run(key: str, label: str, function: Callable[[], Any], *, store: bool = True) -> Any | None:
    with workflow_status(label):
        envelope = safe_execute(key, function, inputs={"operation": label}, include_safe_traceback=False)
    history = st.session_state.get(EXECUTION_STATE_KEY)
    if not isinstance(history, list):
        history = []
    history.append({
        "module_key": key,
        "status": envelope.status,
        "elapsed_ms": envelope.elapsed_ms,
        "peak_memory_mb": envelope.peak_memory_mb,
        "input_fingerprint_sha256": envelope.input_fingerprint_sha256,
        "warnings": list(envelope.warnings),
    })
    st.session_state[EXECUTION_STATE_KEY] = history[-500:]
    if envelope.status == "failed":
        error = envelope.error
        errors = st.session_state.get(ERROR_STATE_KEY)
        if not isinstance(errors, list):
            errors = []
        errors.append({
            "error_id": f"{key}_{len(errors) + 1}",
            "module_key": key,
            "error_type": error.error_type if error else "Error",
            "message": error.message if error else "Unknown execution error",
            "recovery_code": error.recovery_code if error else "ENGINE_FAILURE",
        })
        st.session_state[ERROR_STATE_KEY] = errors[-500:]
        st.error(f"{error.error_type if error else 'Error'}: {error.message if error else 'Unknown execution error'}")
        st.caption(f"Recovery code: {error.recovery_code if error else 'ENGINE_FAILURE'} · Run fingerprint: {envelope.input_fingerprint_sha256[:16]}")
        return None
    for warning in envelope.warnings:
        st.warning(warning)
    if store:
        _save_result(key, envelope.result)
    return envelope.result


def _csv_upload(label: str, key: str, *, help_text: str | None = None) -> pd.DataFrame | None:
    uploaded = st.file_uploader(label, type=["csv", "tsv", "txt"], key=key, help=help_text)
    if uploaded is None:
        return None
    try:
        payload = read_tabular_bytes(uploaded.getvalue(), uploaded.name)
    except Exception as exc:
        st.error(f"Upload could not be read: {exc}")
        return None
    size_mb = payload.size_bytes / (1024 ** 2)
    st.caption(f"Loaded {payload.filename} · {size_mb:.2f} MB · SHA-256 {payload.sha256[:12]}…")
    if payload.preview_only:
        st.warning(
            f"Large file was safely staged on disk. The interactive editor shows the first {payload.preview_rows:,} rows; "
            "run results from this preview must not be treated as a full-file analysis."
        )
    return payload.frame


def _show_module_header(module_key: str) -> None:
    module = MODULE_BY_KEY[module_key]
    st.subheader(f"{module.number}. {module.title}")
    st.caption(module.description)
    metric_cards(
        [
            ("Workspace", module.workspace, None),
            ("Basis", module.basis, None),
            ("Readiness", module.readiness, None),
            ("Output boundary", "Research", module.boundary),
        ]
    )
    scientific_boundary_banner(source_kind="demo_reference", release_eligible=False, message=module.boundary)


def _show_simple_result(result: Any, module_key: str) -> None:
    if result is None:
        return
    if isinstance(result, pd.DataFrame):
        smart_dataframe(result, key=f"neuro_result_{module_key}")
        st.download_button(
            "Download CSV",
            result.to_csv(index=False).encode("utf-8"),
            f"biointel_neuro_{module_key}.csv",
            "text/csv",
            key=f"download_{module_key}_csv",
            width="stretch",
        )
    elif isinstance(result, dict):
        smart_json(result, title="Result", download_name=f"biointel_neuro_{module_key}.json", key=f"result_{module_key}")
    else:
        st.write(result)



def _render_bbb() -> None:
    mode = st.radio(
        "Workflow",
        ["Single compound", "Batch table", "Validate against measured labels"],
        horizontal=True,
        key="bbb_mode",
    )
    if mode == "Single compound":
        preset = st.selectbox("Example", list(DEMO_SMILES), key="bbb_preset")
        smiles = st.text_input("SMILES", value=DEMO_SMILES[preset], key="bbb_smiles")
        compound_id = st.text_input("Compound ID", value=preset, key="bbb_id")
        if st.button("Run BBB screen", type="primary", key="run_bbb"):
            result = _safe_run("bbb_permeability", "Calculating transparent BBB descriptors", lambda: bbb_permeability(smiles, compound_id))
            if not result:
                return
            metric_cards([
                ("Classification", result["classification"], None),
                ("Probability proxy", result.get("local_probability_proxy"), "Local deterministic proxy"),
                ("CNS MPO proxy", result["cns_mpo_proxy"]["score"], "Maximum 6"),
                ("Rules passed", f"{result['rules_passed']}/{result['rules_total']}", None),
            ])
            for warning in result.get("warnings", []):
                st.warning(warning)
            figures = chemistry_figures(result)
            if "mpo" in figures:
                st.plotly_chart(figures["mpo"], width="stretch")
            tabs = st.tabs(["Descriptors", "Rule audit", "Applicability", "Boundary"])
            with tabs[0]:
                smart_dataframe(pd.DataFrame([result["descriptors"]]), key="bbb_desc")
            with tabs[1]:
                smart_dataframe(pd.DataFrame([{"rule": key, "passed": value} for key, value in result["rule_results"].items()]), key="bbb_rules")
            with tabs[2]:
                smart_json(result.get("applicability_domain", {}), title="Applicability-domain review", key="bbb_domain")
            with tabs[3]:
                st.info(result["scientific_boundary"])
            _save_result("bbb_permeability", result)
    elif mode == "Batch table":
        base = pd.DataFrame([{"compound_id": name, "smiles": smiles} for name, smiles in DEMO_SMILES.items()])
        uploaded = _csv_upload("Upload compound CSV/TSV", "bbb_batch_upload")
        editor = st.data_editor(uploaded if uploaded is not None else base, num_rows="dynamic", width="stretch", key="bbb_batch_editor")
        if st.button("Run batch BBB screen", type="primary", key="run_bbb_batch"):
            result = _safe_run("bbb_permeability", "Screening compound batch", lambda: bbb_batch(editor.to_dict(orient="records")))
            if result is None:
                return
            smart_dataframe(result, key="bbb_batch_result")
            if isinstance(result, pd.DataFrame) and "classification" in result:
                counts = result["classification"].value_counts().rename_axis("classification").reset_index(name="count")
                st.plotly_chart(px.bar(counts, x="classification", y="count", title="BBB batch classification"), width="stretch")
            _save_result("bbb_permeability", result)
    else:
        st.caption("Upload measured BBB labels to evaluate the local transparent screen. This is internal validation, not external certification.")
        uploaded = _csv_upload("Upload measured BBB reference CSV/TSV", "bbb_reference_upload")
        if uploaded is None:
            st.info("Required columns: a SMILES column and a measured BBB label column. Optional compound ID is supported.")
            return
        columns = list(uploaded.columns)
        c1, c2, c3 = st.columns(3)
        smiles_column = c1.selectbox("SMILES column", columns, index=columns.index("smiles") if "smiles" in columns else 0, key="bbb_ref_smiles")
        label_column = c2.selectbox("Measured label column", columns, index=columns.index("bbb_label") if "bbb_label" in columns else min(1, len(columns)-1), key="bbb_ref_label")
        id_options = ["<generated>"] + columns
        id_column = c3.selectbox("Compound ID column", id_options, key="bbb_ref_id")
        if st.button("Evaluate BBB reference set", type="primary", key="run_bbb_reference"):
            result = _safe_run(
                "bbb_permeability",
                "Evaluating measured BBB reference set",
                lambda: bbb_reference_validation(uploaded, smiles_column=smiles_column, label_column=label_column, id_column=None if id_column == "<generated>" else id_column),
            )
            if not result:
                return
            metrics = result["validation_metrics"]
            metric_cards([
                ("Evaluated", metrics.get("evaluated_rows"), None),
                ("Balanced accuracy", metrics.get("balanced_accuracy", "Not estimable"), None),
                ("Brier score", metrics.get("brier_score", "Not estimable"), None),
                ("Unique scaffolds", metrics.get("unique_scaffolds"), None),
            ])
            for warning in result.get("warnings", []):
                st.warning(warning)
            tabs = st.tabs(["Validation rows", "Calibration", "Metrics"])
            with tabs[0]: smart_dataframe(result["evaluated_compounds"], key="bbb_reference_rows")
            with tabs[1]: smart_dataframe(result["calibration_table"], key="bbb_reference_calibration")
            with tabs[2]: smart_json(metrics, title="Validation metrics", key="bbb_reference_metrics")
            _save_result("bbb_reference_validation", result)


def _render_target_tagging() -> None:
    identifier = st.text_input("Target identifier (gene, UniProt or name)", value="DRD2", key="target_identifier")
    sequence = st.text_area("Optional protein sequence", height=160, key="target_sequence")
    evidence = _csv_upload("Optional target/pathway/disease evidence table", "target_evidence_upload")
    if st.button("Build integrated target review", type="primary", key="run_target_tag"):
        result = _safe_run(
            "neuro_target_curation",
            "Building target, pathway and evidence review",
            lambda: target_mechanism_workflow(identifier, sequence=sequence or None, evidence_frame=evidence),
        )
        if not result:
            return
        tagging = result["target_tagging"]
        metric_cards([
            ("Neuro relevant", tagging.get("is_neuro_relevant"), None),
            ("Evidence score", tagging.get("evidence_score"), tagging.get("evidence_level")),
            ("Disease links", tagging.get("disease_association_count"), None),
            ("Registry match", tagging.get("matched_by") or "No bundled match", None),
        ])
        graph = result["evidence_graph"]
        st.plotly_chart(target_evidence_graph_figure(graph), width="stretch")
        tabs = st.tabs(["Target profile", "Pathways", "Evidence edges", "Conflicts", "Sequence"])
        with tabs[0]: smart_json(tagging, title="Target tagging", key="target_tagging_result")
        with tabs[1]: smart_json(result["pathway_mapping"], title="Pathway mapping", key="target_pathway_result")
        with tabs[2]: smart_dataframe(graph["edges"], key="target_graph_edges")
        with tabs[3]: smart_dataframe(graph["conflicting_evidence"], key="target_graph_conflicts")
        with tabs[4]:
            topology = result.get("sequence_topology")
            if topology:
                st.plotly_chart(sequence_topology_figure(topology), width="stretch")
                smart_dataframe(topology["motifs"], key="target_topology_motifs")
            else:
                st.info("Add a protein sequence to review topology and motifs.")
        _save_result("neuro_target_curation", result)
    with st.expander("Browse bundled target registry"):
        smart_dataframe(target_registry_frame(), key="neuro_target_registry")


def _render_pathway() -> None:
    identifier = st.text_input("Target identifier", value="HTR2A", key="pathway_target")
    evidence = _csv_upload("Optional pathway/disease evidence table", "pathway_evidence_upload")
    if st.button("Map neurotransmitter pathways", type="primary", key="run_pathway"):
        result = _safe_run(
            "neurotransmitter_pathway",
            "Mapping pathways and evidence provenance",
            lambda: target_mechanism_workflow(identifier, evidence_frame=evidence),
        )
        if not result:
            return
        pathway = result["pathway_mapping"]
        graph = result["evidence_graph"]
        metric_cards([
            ("Target", pathway.get("target") or identifier, None),
            ("Pathways", len(pathway.get("pathways", [])), None),
            ("Graph nodes", len(graph.get("nodes", [])), None),
            ("Graph edges", len(graph.get("edges", [])), None),
        ])
        st.plotly_chart(target_evidence_graph_figure(graph), width="stretch")
        tabs = st.tabs(["Pathway mapping", "Evidence edges", "Conflict review"])
        with tabs[0]: smart_json(pathway, title="Pathway mapping", key="pathway_result")
        with tabs[1]: smart_dataframe(graph["edges"], key="pathway_edges")
        with tabs[2]: smart_dataframe(graph["conflicting_evidence"], key="pathway_conflicts")
        _save_result("neurotransmitter_pathway", result)

def _sequence_input(key: str, default: str) -> str:
    uploaded = st.file_uploader("Upload FASTA/TXT", type=["fasta", "fa", "faa", "txt"], key=f"{key}_upload")
    default_value = uploaded.getvalue().decode("utf-8", errors="replace") if uploaded else default
    return st.text_area("Protein sequence", value=default_value, height=230, key=f"{key}_sequence")



def _render_ion_channel() -> None:
    sequence = _sequence_input("ion", DEMO_PROTEIN_SEQUENCE)
    if st.button("Review ion-channel topology", type="primary", key="run_ion"):
        result = _safe_run("ion_channel_classifier", "Scanning ion-channel architecture", lambda: sequence_topology_track(sequence, protein_class="ion_channel"))
        if not result:
            return
        classification = result["ion_channel_classification"]
        metric_cards([
            ("Ion channel", classification["is_ion_channel"], None),
            ("Subtype", classification["subtype"] or "Not assigned", None),
            ("Confidence", classification["confidence"], classification.get("confidence_score")),
            ("TM-like segments", len(result["transmembrane_like_segments"]), None),
        ])
        st.plotly_chart(sequence_topology_figure(result), width="stretch")
        tabs = st.tabs(["Motifs", "Segments", "Classification", "Boundary"])
        with tabs[0]: smart_dataframe(result["motifs"], key="ion_motifs")
        with tabs[1]: smart_dataframe(result["transmembrane_like_segments"], key="ion_segments")
        with tabs[2]: smart_json(classification, title="Ion-channel classification", key="ion_classification")
        with tabs[3]: st.info(result["scientific_boundary"])
        _save_result("ion_channel_classifier", result)


def _render_gpcr() -> None:
    sequence = _sequence_input("gpcr", DEMO_GPCR_SEQUENCE)
    if st.button("Review GPCR topology", type="primary", key="run_gpcr"):
        result = _safe_run("gpcr_classifier", "Scanning GPCR architecture", lambda: sequence_topology_track(sequence, protein_class="gpcr"))
        if not result:
            return
        classification = result["gpcr_classification"]
        metric_cards([
            ("Neuro GPCR", classification["is_neuro_gpcr"], None),
            ("Family", classification["receptor_family"] or "Not assigned", None),
            ("Confidence", classification["confidence"], classification.get("confidence_score")),
            ("TM-like segments", len(result["transmembrane_like_segments"]), None),
        ])
        st.plotly_chart(sequence_topology_figure(result), width="stretch")
        tabs = st.tabs(["Motifs", "Segments", "Classification", "Boundary"])
        with tabs[0]: smart_dataframe(result["motifs"], key="gpcr_motifs")
        with tabs[1]: smart_dataframe(result["transmembrane_like_segments"], key="gpcr_segments")
        with tabs[2]: smart_json(classification, title="GPCR classification", key="gpcr_classification")
        with tabs[3]: st.info(result["scientific_boundary"])
        _save_result("gpcr_classifier", result)

def _render_disease_targets() -> None:
    col1, col2 = st.columns(2)
    disease = col1.text_input("Disease contains", value="Alzheimer", key="disease_filter")
    target = col2.text_input("Optional exact target", key="disease_target_filter")
    if st.button("Search disease-target evidence", type="primary", key="run_disease_targets"):
        result = _safe_run("cns_disease_targets", "Searching disease-target table", lambda: disease_target_table(disease or None, target or None))
        _show_simple_result(result, "cns_disease_targets")


def _render_cns_drug_likeness() -> None:
    preset = st.selectbox("Example", list(DEMO_SMILES), key="druglike_preset")
    smiles = st.text_input("SMILES", value=DEMO_SMILES[preset], key="druglike_smiles")
    if st.button("Score CNS drug-likeness", type="primary", key="run_druglike"):
        result = _safe_run("cns_drug_likeness", "Calculating CNS drug-likeness", lambda: cns_drug_likeness(smiles))
        if result:
            metric_cards(
                [
                    ("Composite score", result["composite_score"], "0–100 transparent screen"),
                    ("Rating", result["rating"], None),
                    ("P-gp proxy", result["pgp_efflux_proxy"], None),
                    ("Stability proxy", result["metabolic_stability_proxy"], None),
                ]
            )
            smart_dataframe(
                pd.DataFrame([{"factor": key, **value} for key, value in result["factors"].items()]),
                key="druglike_factors",
            )
            if result["warnings"]:
                st.warning("; ".join(result["warnings"]))
            _save_result("cns_drug_likeness", result)


def _binding_profile_editor(prefix: str) -> pd.DataFrame:
    uploaded = _csv_upload("Upload target-binding profile", f"{prefix}_upload")
    base = uploaded if uploaded is not None else binding_profile()
    return st.data_editor(base, num_rows="dynamic", width="stretch", key=f"{prefix}_editor")



def _render_off_target() -> None:
    editor = _binding_profile_editor("offtarget")
    columns = list(editor.columns)
    target_column = next((column for column in columns if str(column).lower() in {"target", "target_id", "gene"}), None)
    target_values = sorted(editor[target_column].dropna().astype(str).unique().tolist()) if target_column else []
    c1, c2, c3 = st.columns(3)
    primary_target = c1.selectbox("Primary target", ["<none>"] + target_values, key="offtarget_primary")
    free_concentration = c2.number_input("Optional free brain concentration (nM)", min_value=0.0, value=20.0, key="offtarget_concentration")
    exposure_factor = c3.number_input("Brain-exposure factor", min_value=0.0, value=1.0, key="offtarget_exposure_factor")
    metabolite = _csv_upload("Optional active-metabolite binding profile", "offtarget_metabolite_upload")
    if st.button("Build exposure-aware safety review", type="primary", key="run_offtarget"):
        result = _safe_run(
            "off_target_neurotoxicity",
            "Reviewing targets, metabolites, occupancy and panel coverage",
            lambda: off_target_safety_workflow(
                editor.to_dict(orient="records"),
                primary_target=None if primary_target == "<none>" else primary_target,
                brain_exposure_factor=exposure_factor,
                free_brain_concentration=free_concentration,
                metabolite_rows=() if metabolite is None else metabolite.to_dict(orient="records"),
            ),
        )
        if not result:
            return
        flags = result["off_target_flags"]
        metric_cards([
            ("Off-target flags", flags.get("flag_count"), None),
            ("Unknown targets", len(result["unmatched_or_unknown_targets"]), None),
            ("Metabolite rows", result.get("metabolite_rows"), None),
            ("Family panels", len(result["target_family_coverage"]), None),
        ])
        for warning in result.get("warnings", []): st.warning(warning)
        figures = safety_figures(result)
        if "occupancy" in figures: st.plotly_chart(figures["occupancy"], width="stretch")
        if "coverage" in figures: st.plotly_chart(figures["coverage"], width="stretch")
        tabs = st.tabs(["Flags", "Occupancy", "Safety margins", "Coverage", "Unknown/not tested"])
        with tabs[0]: smart_dataframe(flags.get("flags", []), key="offtarget_flags")
        with tabs[1]: smart_dataframe(result["occupancy"], key="offtarget_occupancy")
        with tabs[2]: smart_dataframe(result["safety_margins"], key="offtarget_margins")
        with tabs[3]: smart_dataframe(result["target_family_coverage"], key="offtarget_coverage")
        with tabs[4]: smart_dataframe(result["unmatched_or_unknown_targets"], key="offtarget_unknown")
        _save_result("off_target_neurotoxicity", result)

def _render_aggregation() -> None:
    sequence = _sequence_input("aggregation", DEMO_AGGREGATION_SEQUENCE)
    col1, col2 = st.columns(2)
    window = col1.slider("Window size", 7, 21, 9, 2, key="agg_window")
    threshold = col2.slider("Risk threshold", 0.40, 0.90, 0.62, 0.01, key="agg_threshold")
    if st.button("Analyze aggregation propensity", type="primary", key="run_aggregation"):
        result = _safe_run("aggregation_risk", "Scanning aggregation windows", lambda: aggregation_risk(sequence, window, threshold))
        if result:
            metric_cards(
                [
                    ("Overall score", result["aggregation_risk_score"], None),
                    ("Risk band", result["risk_band"], None),
                    ("High-risk regions", len(result["high_risk_regions"]), None),
                    ("Sequence length", result["sequence_length"], None),
                ]
            )
            track = pd.DataFrame(result["position_track"])
            fig = px.line(track, x="start_position", y="local_score", title="Aggregation-propensity position track")
            fig.add_hline(y=threshold, line_dash="dash")
            st.plotly_chart(fig, width="stretch")
            smart_dataframe(result["high_risk_regions"], key="agg_regions")
            _save_result("aggregation_risk", result)



def _render_side_effects() -> None:
    editor = _binding_profile_editor("sideeffects")
    exposure_factor = st.number_input("Brain-exposure factor", min_value=0.0, value=1.0, key="sideeffects_exposure")
    if st.button("Estimate CNS side-effect patterns", type="primary", key="run_sideeffects"):
        result = _safe_run(
            "cns_side_effects",
            "Estimating transparent target-pattern associations",
            lambda: off_target_safety_workflow(editor.to_dict(orient="records"), brain_exposure_factor=exposure_factor),
        )
        if not result:
            return
        side_effect_result = result["side_effect_estimates"]
        estimates = pd.DataFrame(side_effect_result.get("side_effect_estimates", []))
        coverage = side_effect_result.get("coverage", {})
        metric_cards([
            ("Covered targets", coverage.get("covered_targets"), None),
            ("Coverage fraction", coverage.get("coverage_fraction"), None),
            ("Effect categories", len(estimates), None),
            ("Unknown targets", len(result["unmatched_or_unknown_targets"]), None),
        ])
        if side_effect_result.get("coverage_warning"): st.warning(side_effect_result["coverage_warning"])
        figures = safety_figures(result)
        if "side_effects" in figures: st.plotly_chart(figures["side_effects"], width="stretch")
        tabs = st.tabs(["Estimates", "Contributing targets", "Coverage", "Boundary"])
        with tabs[0]: smart_dataframe(estimates, key="side_effect_estimates")
        with tabs[1]:
            contributing = []
            for row in side_effect_result.get("side_effect_estimates", []):
                for target in row.get("contributing_targets", []):
                    contributing.append({"side_effect_category": row.get("side_effect_category"), **target})
            smart_dataframe(pd.DataFrame(contributing), key="side_effect_contributors")
        with tabs[2]: smart_json(coverage, title="Association-map coverage", key="side_effect_coverage")
        with tabs[3]: st.info(result["scientific_boundary"])
        _save_result("cns_side_effects", result)

def _render_neuroinflammation() -> None:
    identifier = st.text_input("Target identifier", value="TREM2", key="neuroinflam_target")
    if st.button("Check neuroinflammation relevance", type="primary", key="run_neuroinflam"):
        result = _safe_run("neuroinflammation", "Checking neuroinflammation registry", lambda: neuroinflammation_lookup(identifier))
        _show_simple_result(result, "neuroinflammation")


def _render_blood_csf() -> None:
    preset = st.selectbox("Example", list(DEMO_SMILES), key="csf_preset")
    smiles = st.text_input("SMILES", value=DEMO_SMILES[preset], key="csf_smiles")
    if st.button("Run provisional blood-CSF screen", type="primary", key="run_csf"):
        result = _safe_run("blood_csf_barrier", "Calculating blood-CSF proxy", lambda: blood_csf_barrier(smiles))
        if result:
            metric_cards(
                [
                    ("Classification", result["csf_permeability_classification"], None),
                    ("Provisional score", result["provisional_score"], None),
                    ("Methodology", result["methodology_status"], None),
                ]
            )
            smart_dataframe(pd.DataFrame([result["descriptor_values"]]), key="csf_descriptors")
            _save_result("blood_csf_barrier", result)


def _render_model_organism() -> None:
    identifier = st.text_input("Target identifier", value="SNCA", key="model_target")
    if st.button("Find model-organism records", type="primary", key="run_models"):
        result = _safe_run("model_organism", "Cross-referencing model organisms", lambda: model_organism_cross_reference(identifier))
        if result:
            smart_dataframe(result["available_models"], key="model_organisms")
            _save_result("model_organism", result)



def _render_adme() -> None:
    preset = st.selectbox("Example", list(DEMO_SMILES), key="adme_preset")
    smiles = st.text_input("SMILES", value=DEMO_SMILES[preset], key="adme_smiles")
    reference = _csv_upload("Optional reference chemical-space table", "adme_reference_upload")
    reference_column = None
    if reference is not None:
        reference_column = st.selectbox("Reference SMILES column", list(reference.columns), index=list(reference.columns).index("smiles") if "smiles" in reference.columns else 0, key="adme_reference_column")
    if st.button("Run integrated CNS ADME screen", type="primary", key="run_adme"):
        result = _safe_run(
            "cns_adme_transporters",
            "Calculating BBB, drug-likeness, transporter and ADME proxies",
            lambda: cns_drug_adme_workflow(smiles, reference_frame=reference, reference_smiles_column=reference_column or "smiles"),
        )
        if not result:
            return
        bbb = result["bbb_screen"]
        adme = result["adme_transporter_screen"]
        druglike = result["cns_drug_likeness"]
        metric_cards([
            ("BBB class", bbb.get("classification"), None),
            ("Drug-likeness", druglike.get("composite_score"), druglike.get("rating")),
            ("P-gp proxy", adme.get("pgp_substrate_proxy"), None),
            ("Clearance risk", adme.get("clearance_risk_proxy"), None),
        ])
        for warning in result.get("warnings", []): st.warning(warning)
        figures = chemistry_figures(result)
        if "mpo" in figures: st.plotly_chart(figures["mpo"], width="stretch")
        if "chemical_space" in figures: st.plotly_chart(figures["chemical_space"], width="stretch")
        tabs = st.tabs(["ADME/transport", "BBB", "Drug-likeness", "Blood-CSF", "Reference space"])
        with tabs[0]:
            smart_json(adme, title="ADME and transporter screen", key="adme_screen")
            smart_dataframe(pd.DataFrame([adme.get("cyp_alerts", {})]), key="adme_cyp")
        with tabs[1]: smart_json(bbb, title="BBB screen", key="adme_bbb")
        with tabs[2]: smart_json(druglike, title="CNS drug-likeness", key="adme_druglike")
        with tabs[3]: smart_json(result["blood_csf_screen"], title="Blood-CSF screen", key="adme_csf")
        with tabs[4]: smart_json(result.get("reference_chemical_space") or {"status": "No reference table supplied"}, title="Reference chemical space", key="adme_reference")
        _save_result("cns_adme_transporters", result)


def _render_pk() -> None:
    c1, c2, c3, c4 = st.columns(4)
    initial = c1.number_input("Initial/dose concentration", min_value=0.0, value=100.0, key="pk_initial")
    half_life = c2.number_input("Half-life (hours)", min_value=0.01, value=8.0, key="pk_half")
    duration = c3.number_input("Duration (hours)", min_value=0.1, value=72.0, key="pk_duration")
    route = c4.selectbox("Route model", ["iv", "oral"], key="pk_route")
    c5, c6, c7, c8 = st.columns(4)
    passive = c5.number_input("Passive permeability factor", min_value=0.001, value=1.0, key="pk_passive")
    efflux = c6.number_input("Efflux ratio", min_value=0.0, value=1.5, key="pk_efflux")
    fup = c7.slider("Fraction unbound plasma", 0.01, 1.0, 0.20, 0.01, key="pk_fup")
    fub = c8.slider("Fraction unbound brain", 0.01, 1.0, 0.10, 0.01, key="pk_fub")
    c9, c10, c11, c12 = st.columns(4)
    threshold = c9.number_input("Effective unbound threshold", min_value=0.0, value=5.0, key="pk_threshold")
    dose_count = c10.number_input("Dose count", min_value=1, max_value=100, value=3, step=1, key="pk_dose_count")
    interval = c11.number_input("Dosing interval (hours)", min_value=0.1, value=24.0, key="pk_interval")
    absorption_half = c12.number_input("Absorption half-life (hours)", min_value=0.01, value=1.0, disabled=route != "oral", key="pk_absorption")
    c13, c14 = st.columns(2)
    simulations = c13.slider("Uncertainty simulations", 10, 500, 100, 10, key="pk_simulations")
    common_cv = c14.slider("Parameter coefficient of variation", 0.0, 1.0, 0.20, 0.05, key="pk_cv")
    if st.button("Simulate population brain exposure", type="primary", key="run_pk"):
        parameters = {
            "initial_plasma_concentration": initial,
            "half_life_hours": half_life,
            "duration_hours": duration,
            "passive_permeability_factor": passive,
            "efflux_ratio": efflux,
            "fraction_unbound_plasma": fup,
            "fraction_unbound_brain": fub,
            "effective_threshold": threshold,
            "route": route,
            "absorption_half_life_hours": absorption_half if route == "oral" else None,
            "dose_count": int(dose_count),
            "dosing_interval_hours": interval,
        }
        variable_parameters = ["initial_plasma_concentration", "half_life_hours", "passive_permeability_factor", "efflux_ratio", "fraction_unbound_plasma", "fraction_unbound_brain"]
        result = _safe_run(
            "brain_exposure_pk",
            "Propagating PK and brain-exposure uncertainty",
            lambda: simulate_brain_exposure_population(parameters, coefficient_of_variation={name: common_cv for name in variable_parameters}, simulations=simulations),
        )
        if not result:
            return
        summary = result["simulation_summary"]
        metric_cards([
            ("Simulations", result["simulations"], None),
            ("Median peak brain", round(float(summary["peak_brain_unbound"].median()), 4), None),
            ("Median Kp,uu,brain", round(float(summary["kp_uu_brain"].median()), 4), None),
            ("Median time above threshold", round(float(summary["time_above_effective_threshold_hours"].median()), 3), "hours"),
        ])
        figures = pk_figures(population_result=result)
        if "exposure" in figures: st.plotly_chart(figures["exposure"], width="stretch")
        tabs = st.tabs(["Percentile curve", "Simulation summaries", "Uncertainty", "Boundary"])
        with tabs[0]: smart_dataframe(result["percentile_curve"], key="pk_percentile_curve")
        with tabs[1]: smart_dataframe(summary, key="pk_simulation_summary")
        with tabs[2]: smart_json(result["coefficient_of_variation"], title="Declared parameter uncertainty", key="pk_uncertainty")
        with tabs[3]: st.info(result["scientific_boundary"])
        _save_result("brain_exposure_pk", result)


def _render_occupancy() -> None:
    source = st.radio("Exposure input", ["Constant concentration", "Latest PK median curve", "Upload exposure curve"], horizontal=True, key="occ_source")
    exposure_curve = None
    constant_concentration = 20.0
    if source == "Constant concentration":
        constant_concentration = st.number_input("Free brain concentration (same units as affinity)", min_value=0.0, value=20.0, key="occ_conc")
    elif source == "Latest PK median curve":
        previous = _result_store().get("brain_exposure_pk")
        if isinstance(previous, dict) and isinstance(previous.get("percentile_curve"), pd.DataFrame):
            exposure_curve = previous["percentile_curve"][["time_hours", "brain_unbound_p50"]].rename(columns={"brain_unbound_p50": "brain_unbound"})
            st.caption("Using the median brain-unbound curve from the latest PK run.")
        else:
            st.warning("Run Brain Exposure PK first, or upload an exposure curve.")
    else:
        uploaded = _csv_upload("Upload exposure curve", "occupancy_curve_upload")
        if uploaded is not None:
            time_col = st.selectbox("Time column", list(uploaded.columns), index=list(uploaded.columns).index("time_hours") if "time_hours" in uploaded.columns else 0, key="occ_time_column")
            concentration_candidates = [column for column in uploaded.columns if column != time_col]
            concentration_col = st.selectbox("Concentration column", concentration_candidates, index=concentration_candidates.index("brain_unbound") if "brain_unbound" in concentration_candidates else 0, key="occ_concentration_column")
            exposure_curve = uploaded[[time_col, concentration_col]].rename(columns={time_col: "time_hours", concentration_col: "brain_unbound"})
    base = pd.DataFrame([
        {"target": "DRD2", "kd": 5.0, "kon": 0.10, "koff": 0.50, "role": "primary"},
        {"target": "HTR2A", "kd": 35.0, "kon": np.nan, "koff": np.nan, "role": "off_target"},
        {"target": "H1", "kd": 12.0, "kon": np.nan, "koff": np.nan, "role": "off_target"},
    ])
    editor = st.data_editor(base, num_rows="dynamic", width="stretch", key="occ_editor")
    if st.button("Calculate receptor occupancy", type="primary", key="run_occ"):
        if exposure_curve is None and source != "Constant concentration":
            st.error("No valid exposure curve is available.")
            return
        if source == "Constant concentration":
            result = _safe_run("receptor_occupancy", "Calculating equilibrium occupancy", lambda: receptor_occupancy(constant_concentration, editor.to_dict(orient="records")))
            if result is None:
                return
            smart_dataframe(result, key="occ_result")
            if not result.empty:
                st.plotly_chart(px.bar(result.dropna(subset=["occupancy_percent"]), x="target", y="occupancy_percent", color="role", title="Equilibrium target engagement"), width="stretch")
        else:
            result = _safe_run("receptor_occupancy", "Calculating time-resolved target occupancy", lambda: receptor_occupancy_kinetics(exposure_curve, editor.to_dict(orient="records")))
            if not result:
                return
            figures = pk_figures(occupancy_result=result)
            if "occupancy" in figures: st.plotly_chart(figures["occupancy"], width="stretch")
            tabs = st.tabs(["Occupancy curve", "Target summary", "Boundary"])
            with tabs[0]: smart_dataframe(result["occupancy_curve"], key="occ_curve")
            with tabs[1]: smart_dataframe(result["target_summary"], key="occ_summary")
            with tabs[2]: st.info(result["scientific_boundary"])
        _save_result("receptor_occupancy", result)

def _render_neurogenetics() -> None:
    uploaded = st.file_uploader("Upload VCF or annotated CSV/TSV", type=["vcf", "txt", "csv", "tsv"], key="variant_upload")
    base: pd.DataFrame
    if uploaded:
        raw = uploaded.getvalue()
        try:
            if uploaded.name.lower().endswith((".vcf", ".txt")):
                base = parse_vcf_text(raw.decode("utf-8", errors="replace"))
            else:
                base = read_tabular_bytes(raw, uploaded.name).frame
        except Exception as exc:
            st.error(f"Variant file could not be read: {exc}")
            return
    else:
        base = variants()
    editor = st.data_editor(base, num_rows="dynamic", width="stretch", key="variant_editor")
    c1, c2, c3 = st.columns(3)
    genome_build = c1.selectbox("Genome build", ["Auto detect", "GRCh37", "GRCh38", "Unspecified"], key="variant_build")
    minimum_quality = c2.number_input("Minimum QUAL", min_value=0.0, value=0.0, key="variant_min_qual")
    require_pass = c3.checkbox("Require PASS/. FILTER", key="variant_require_pass")
    phenotype_text = st.text_input("Phenotype/HPO terms, comma separated", key="variant_phenotypes", help="Matched only against annotations already supplied in the uploaded table.")
    if st.button("Build neurological variant review", type="primary", key="run_variants"):
        selected_build = None if genome_build == "Auto detect" else "unspecified" if genome_build == "Unspecified" else genome_build
        result = _safe_run(
            "neurogenetics",
            "Normalizing and prioritizing variants",
            lambda: variant_interpretation_workflow(
                editor,
                genome_build=selected_build,
                phenotype_terms=[token.strip() for token in phenotype_text.split(",") if token.strip()],
                minimum_quality=minimum_quality,
                require_pass_filter=require_pass,
            ),
        )
        if not result:
            return
        build = result.get("build_detection", {})
        summary = result.get("input_summary", {})
        prioritized = result.get("prioritized_variants", pd.DataFrame())
        metric_cards([
            ("Genome build", build.get("genome_build"), build.get("confidence")),
            ("Allele rows", summary.get("expanded_allele_rows"), None),
            ("High-priority", int((prioritized.get("priority_band") == "high").sum()) if isinstance(prioritized, pd.DataFrame) and not prioritized.empty else 0, None),
            ("Evidence conflicts", len(result.get("evidence_conflicts", pd.DataFrame())), None),
        ])
        if build.get("warning"):
            st.warning(build["warning"])
        figures = variant_figures(result)
        tabs = st.tabs(["Prioritized variants", "Evidence", "Compound-het review", "Conflicts/QC"])
        with tabs[0]:
            if "priority" in figures:
                st.plotly_chart(figures["priority"], width="stretch")
            smart_dataframe(prioritized, key="variant_prioritized")
        with tabs[1]:
            if "evidence" in figures:
                st.plotly_chart(figures["evidence"], width="stretch")
        with tabs[2]:
            smart_dataframe(result.get("compound_heterozygous_candidates", pd.DataFrame()), key="variant_compound_het")
        with tabs[3]:
            smart_dataframe(result.get("evidence_conflicts", pd.DataFrame()), key="variant_conflicts")
            smart_json({"build_detection": build, "input_summary": summary, "scientific_boundary": result.get("scientific_boundary")}, title="Variant QC and boundary", key="variant_qc")
        _save_result("neurogenetics", result)

def _render_expression() -> None:
    mode = st.radio("Atlas source", ["Bundled labelled demo/reference", "Uploaded expression atlas"], horizontal=True, key="expression_mode")
    identifier = st.text_input("Target identifier", value="TREM2", key="expression_target")
    atlas_frame: pd.DataFrame | None = None
    mapping: dict[str, str | None] = {}
    source_name = "BioIntel bundled target registry"
    source_version = "bundled snapshot"
    disease_filter = None
    stage_filter = None
    sample_filter = None
    if mode == "Uploaded expression atlas":
        atlas_frame = _csv_upload(
            "Upload long-form expression CSV/TSV",
            "expression_atlas_upload",
            help_text="Expected columns include gene/target, expression and at least one brain-region or cell-type field.",
        )
        if atlas_frame is not None and not atlas_frame.empty:
            columns = list(atlas_frame.columns)
            options = ["<auto>"] + columns
            c1, c2, c3, c4 = st.columns(4)
            mapping["gene_column"] = c1.selectbox("Gene/target column", options, key="expression_gene_col")
            mapping["expression_column"] = c2.selectbox("Expression column", options, key="expression_value_col")
            mapping["region_column"] = c3.selectbox("Brain-region column", options, key="expression_region_col")
            mapping["cell_type_column"] = c4.selectbox("Cell-type column", options, key="expression_cell_col")
            c5, c6, c7 = st.columns(3)
            mapping["disease_column"] = c5.selectbox("Disease/condition column", options, key="expression_disease_col")
            mapping["developmental_stage_column"] = c6.selectbox("Developmental-stage column", options, key="expression_stage_col")
            mapping["sample_type_column"] = c7.selectbox("Sample/modality column", options, key="expression_sample_col")
            f1, f2, f3 = st.columns(3)
            disease_filter = f1.text_input("Optional exact disease filter", key="expression_disease_filter") or None
            stage_filter = f2.text_input("Optional exact stage filter", key="expression_stage_filter") or None
            sample_filter = f3.text_input("Optional exact sample-type filter", key="expression_sample_filter") or None
            s1, s2 = st.columns(2)
            source_name = s1.text_input("Source/dataset name", value="Uploaded expression atlas", key="expression_source_name")
            source_version = s2.text_input("Source version/date", value="unspecified", key="expression_source_version")
    if st.button("Analyze brain expression atlas", type="primary", key="run_expression"):
        kwargs = {key: (None if value == "<auto>" else value) for key, value in mapping.items()}
        result = _safe_run(
            "brain_expression_atlas",
            "Building expression atlas review",
            lambda: expression_atlas_analysis(
                identifier,
                atlas_frame,
                **kwargs,
                disease_filter=disease_filter,
                developmental_stage_filter=stage_filter,
                sample_type_filter=sample_filter,
                source_name=source_name,
                source_version=source_version,
            ),
        )
        if not result:
            return
        if not result.get("found"):
            st.info(result.get("coverage_warning", "No matching expression rows were found."))
            smart_json(result.get("provenance", {}), title="Source provenance", key="expression_missing_provenance")
            return
        metric_cards([
            ("Top region", result.get("top_region") or "Not available", None),
            ("Top cell type", result.get("top_cell_type") or "Not available", None),
            ("Matched rows", result.get("matched_rows", "Bundled summary"), None),
            ("Regional specificity", result.get("regional_tau_specificity"), "Tau 0–1"),
        ])
        figures = expression_atlas_figures(result)
        tabs = st.tabs(["Regional", "Cell types", "Conditions/stages", "Provenance"])
        with tabs[0]:
            if "regional" in figures:
                st.plotly_chart(figures["regional"], width="stretch")
            smart_dataframe(result.get("regional_summary", pd.DataFrame()), key="expression_regional_table")
        with tabs[1]:
            if "cell_type" in figures:
                st.plotly_chart(figures["cell_type"], width="stretch")
            smart_dataframe(result.get("cell_type_summary", pd.DataFrame()), key="expression_cell_table")
        with tabs[2]:
            if "disease" in figures:
                st.plotly_chart(figures["disease"], width="stretch")
            smart_dataframe(result.get("disease_summary", pd.DataFrame()), key="expression_disease_table")
            smart_dataframe(result.get("developmental_summary", pd.DataFrame()), key="expression_stage_table")
        with tabs[3]:
            smart_json({
                "provenance": result.get("provenance"),
                "filters_applied": result.get("filters_applied"),
                "column_mapping": result.get("column_mapping"),
                "scientific_boundary": result.get("scientific_boundary"),
            }, title="Atlas provenance and boundary", key="expression_provenance")
        _save_result("brain_expression_atlas", result)


def _render_omics() -> None:
    uploaded = _csv_upload("Upload omics matrix", "omics_upload", help_text="Rows are samples; one column must define exactly two groups.")
    base = uploaded if uploaded is not None else omics()
    preview = st.data_editor(base, num_rows="dynamic", width="stretch", key="omics_editor")
    if preview.empty or len(preview.columns) < 2:
        st.info("Add at least a group column and one numeric feature.")
        return
    columns = list(preview.columns)
    group_column = st.selectbox("Two-group column", columns, index=columns.index("group") if "group" in columns else 0, key="omics_group")
    optional = ["<none>"] + columns
    c1, c2, c3 = st.columns(3)
    batch_column = c1.selectbox("Optional batch column", optional, key="omics_batch")
    identifier_column = c2.selectbox("Optional sample-ID column", optional, index=optional.index("sample_id") if "sample_id" in optional else 0, key="omics_identifier")
    covariates = c3.multiselect("Reserve covariates from feature selection", [column for column in columns if column != group_column], key="omics_covariates")
    c4, c5, c6 = st.columns(3)
    minimum_non_missing = c4.slider("Minimum non-missing fraction", 0.30, 1.00, 0.70, 0.05, key="omics_non_missing")
    selected_features = c5.number_input("Features selected per CV fold", min_value=1, max_value=max(1, len(columns) - 1), value=min(10, max(1, len(columns) - 1)), key="omics_selected_features")
    permutations = c6.slider("Permutation iterations", 0, 100, 20, 5, key="omics_permutations")
    if st.button("Run leakage-aware biomarker discovery", type="primary", key="run_omics"):
        result = _safe_run(
            "neuro_omics_biomarkers",
            "Running biomarker discovery and internal validation",
            lambda: biomarker_discovery_workflow(
                preview,
                group_column,
                batch_column=None if batch_column == "<none>" else batch_column,
                identifier_column=None if identifier_column == "<none>" else identifier_column,
                covariate_columns=covariates,
                minimum_non_missing_fraction=minimum_non_missing,
                selected_feature_count=int(selected_features),
                permutation_iterations=int(permutations),
            ),
        )
        if not result:
            return
        metrics = result.get("model_metrics", {})
        metric_cards([
            ("Samples", metrics.get("samples"), None),
            ("Candidate features", metrics.get("candidate_features"), None),
            ("CV ROC AUC", metrics.get("direction_adjusted_roc_auc"), "Internal only"),
            ("Permutation p", metrics.get("permutation_p_value"), None),
        ])
        for warning in result.get("warnings", []):
            st.warning(warning)
        figures = omics_figures(result)
        tabs = st.tabs(["Feature ranking", "Multivariate validation", "Batch/QC", "Boundary"])
        with tabs[0]:
            if "volcano" in figures:
                st.plotly_chart(figures["volcano"], width="stretch")
            smart_dataframe(result.get("feature_ranking", pd.DataFrame()), key="omics_ranking")
        with tabs[1]:
            for key in ("coefficients", "calibration", "permutation"):
                if key in figures:
                    st.plotly_chart(figures[key], width="stretch")
            smart_dataframe(result.get("selected_feature_coefficients", pd.DataFrame()), key="omics_coefficients")
            smart_dataframe(result.get("calibration_table", pd.DataFrame()), key="omics_calibration")
        with tabs[2]:
            batch = result.get("batch_association", {})
            if batch:
                smart_json({key: value for key, value in batch.items() if key != "contingency_table"}, title="Batch association", key="omics_batch_assoc")
                if isinstance(batch.get("contingency_table"), pd.DataFrame):
                    smart_dataframe(batch["contingency_table"].reset_index(), key="omics_batch_contingency")
            smart_dataframe(result.get("missingness", pd.DataFrame()), key="omics_missingness")
        with tabs[3]:
            st.warning(result.get("scientific_boundary"))
        _save_result("neuro_omics_biomarkers", result)


def _render_eeg() -> None:
    adapters = optional_signal_adapter_status()
    uploaded = st.file_uploader(
        "Upload EEG/MEG signal",
        type=["csv", "tsv", "txt", "edf", "bdf", "fif"],
        key="eeg_upload",
        help="CSV/TSV/TXT work in the core build. EDF/BDF/FIF require the optional qualified MNE adapter.",
    )
    payload_meta: dict[str, Any] = {"format": "labelled synthetic demo CSV", "adapter_status": adapters}
    detected_rate: float | None = None
    if uploaded is not None:
        loaded = _safe_run("_signal_upload", "Loading neural signal", lambda: load_signal_payload(uploaded.getvalue(), uploaded.name), store=False)
        if loaded is None:
            return
        base = loaded["frame"]
        detected_rate = loaded.get("sampling_rate_hz")
        payload_meta = loaded.get("metadata", payload_meta)
    else:
        base = eeg()
    default_rate = float(detected_rate or 256.0)
    c1, c2, c3 = st.columns(3)
    sample_rate = c1.number_input("Sampling rate (Hz)", min_value=2.0, value=default_rate, key="eeg_rate")
    time_options = ["<none>"] + list(base.columns)
    time_column = c2.selectbox("Time column", time_options, index=time_options.index("time") if "time" in time_options else 0, key="eeg_time")
    event_column = c3.selectbox("Optional event-marker column", time_options, key="eeg_event")
    c4, c5, c6 = st.columns(3)
    reference_mode = c4.selectbox("Reference", ["average", "median", "none"], key="eeg_reference")
    bad_policy = c5.selectbox("Bad-channel handling", ["flag_only", "interpolate", "exclude"], key="eeg_bad_policy")
    run_ica = c6.checkbox("Run ICA component review", key="eeg_ica")
    c7, c8, c9 = st.columns(3)
    low_cut = c7.number_input("High-pass cutoff (Hz)", min_value=0.01, value=0.5, key="eeg_low_cut")
    high_cut = c8.number_input("Low-pass cutoff (Hz)", min_value=1.0, value=min(80.0, sample_rate * 0.45), key="eeg_high_cut")
    notch = c9.selectbox("Line-noise notch", ["None", "50 Hz", "60 Hz"], key="eeg_notch")
    c10, c11 = st.columns(2)
    epoch_before = c10.number_input("Epoch before event (s)", min_value=0.0, value=0.2, key="eeg_epoch_before")
    epoch_after = c11.number_input("Epoch after event (s)", min_value=0.01, value=0.8, key="eeg_epoch_after")
    st.caption(f"Loaded format: {payload_meta.get('format')} · Optional adapter status: {payload_meta.get('adapter_status')}")
    st.dataframe(base.head(200), width="stretch")
    if st.button("Analyze neural signals", type="primary", key="run_eeg"):
        notch_hz = None if notch == "None" else float(notch.split()[0])
        result = _safe_run(
            "eeg_meg_analytics",
            "Preprocessing neural signals and building review outputs",
            lambda: neural_signal_workflow(
                base,
                sample_rate,
                None if time_column == "<none>" else time_column,
                event_column=None if event_column == "<none>" else event_column,
                reference_mode=reference_mode,
                bad_channel_policy=bad_policy,
                low_cut_hz=low_cut,
                high_cut_hz=high_cut,
                line_noise_hz=notch_hz,
                epoch_before_seconds=epoch_before,
                epoch_after_seconds=epoch_after,
                run_ica_review=run_ica,
            ),
        )
        if not result:
            return
        metric_cards([
            ("Channels", result["channel_count"], None),
            ("Duration", result["duration_seconds"], "seconds"),
            ("Signal quality", result["signal_quality_grade"], None),
            ("Initial bad channels", len(result.get("bad_channels_initial", [])), None),
        ])
        for warning in result.get("workflow_warnings", []):
            st.warning(warning)
        figures = signal_figures(result)
        tabs = st.tabs(["Waveforms/QC", "Spectrum", "Time-frequency", "ERP/events", "ICA/connectivity"])
        with tabs[0]:
            if "waveform" in figures:
                st.plotly_chart(figures["waveform"], width="stretch")
            smart_dataframe(result["channel_summary"], key="eeg_summary")
        with tabs[1]:
            if "psd" in figures:
                st.plotly_chart(figures["psd"], width="stretch")
        with tabs[2]:
            if "spectrogram" in figures:
                st.plotly_chart(figures["spectrogram"], width="stretch")
            smart_dataframe(result.get("spectrogram", pd.DataFrame()).head(1000), key="eeg_spectrogram_table")
        with tabs[3]:
            if "evoked" in figures:
                st.plotly_chart(figures["evoked"], width="stretch")
            smart_dataframe(result.get("event_summary", pd.DataFrame()), key="eeg_event_summary")
            smart_dataframe(result.get("candidate_events", pd.DataFrame()), key="eeg_events")
        with tabs[4]:
            smart_dataframe(result.get("ica_component_review", pd.DataFrame()), key="eeg_ica_review")
            if isinstance(result.get("channel_correlation"), pd.DataFrame) and not result["channel_correlation"].empty:
                st.plotly_chart(px.imshow(result["channel_correlation"], text_auto=".2f", aspect="auto", title="Channel correlation"), width="stretch")
            smart_dataframe(result.get("band_coherence", pd.DataFrame()), key="eeg_coherence")
        _save_result("eeg_meg_analytics", result)


def _render_imaging() -> None:
    mode = st.radio("Analysis mode", ["Image/volume array", "ROI connectivity"], horizontal=True, key="imaging_mode")
    if mode == "Image/volume array":
        adapters = optional_adapter_status()
        uploads = st.file_uploader(
            "Upload NPY, CSV, image, NIfTI or one DICOM series",
            type=["npy", "csv", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "nii", "gz", "dcm", "dicom"],
            key="image_upload",
            accept_multiple_files=True,
            help="Select multiple files only for one DICOM series. NIfTI/DICOM require their optional adapters.",
        )
        image_metadata: dict[str, Any] = {"format": "labelled synthetic demo", "optional_adapters": adapters}
        if not uploads:
            x, y, z = np.mgrid[-1:1:48j, -1:1:48j, -1:1:32j]
            array = np.exp(-((x / 0.45) ** 2 + (y / 0.38) ** 2 + (z / 0.55) ** 2))
            st.caption("Using a labelled synthetic 3D Gaussian volume for software demonstration.")
        elif len(uploads) == 1:
            payload = _safe_run("_image_upload", "Loading image/volume", lambda: load_image_payload(uploads[0].getvalue(), uploads[0].name), store=False)
            if payload is None:
                return
            array = payload["array"]
            image_metadata = payload["metadata"]
        elif all(item.name.lower().endswith((".dcm", ".dicom")) for item in uploads):
            payload = _safe_run("_dicom_series_upload", "Loading DICOM series", lambda: load_dicom_series([(item.name, item.getvalue()) for item in uploads]), store=False)
            if payload is None:
                return
            array = payload["array"]
            image_metadata = payload["metadata"]
        else:
            st.error("Multiple-file upload is supported only for a single DICOM series. Select one non-DICOM file per run.")
            return
        st.caption(f"Format: {image_metadata.get('format')} · Shape: {list(array.shape)} · Optional adapters: {adapters}")
        c1, c2, c3 = st.columns(3)
        threshold_method = c1.selectbox("Automatic threshold", ["otsu", "mean_plus_1.5sd", "percentile_95"], key="image_threshold_method")
        threshold_mode = c2.checkbox("Set threshold manually", key="image_manual_threshold")
        minimum_component = c3.number_input("Minimum component voxels", min_value=1, value=1, key="image_min_component")
        threshold = st.number_input("Manual threshold", value=float(np.nanmean(array) + 1.5 * np.nanstd(array)), key="image_threshold") if threshold_mode else None
        atlas_upload = st.file_uploader("Optional atlas-label NPY with matching spatial shape", type=["npy"], key="image_atlas_upload")
        atlas_labels = None
        if atlas_upload is not None:
            try:
                atlas_labels = np.load(io.BytesIO(atlas_upload.getvalue()), allow_pickle=False)
            except Exception as exc:
                st.error(f"Atlas label array could not be read: {exc}")
                return
        if st.button("Run image/volume QC", type="primary", key="run_image"):
            result = _safe_run(
                "neuroimaging_connectomics",
                "Running orientation, volume and atlas QC",
                lambda: volume_qc_workflow(
                    array,
                    metadata=image_metadata,
                    threshold=threshold,
                    threshold_method=threshold_method,
                    minimum_component_voxels=int(minimum_component),
                    atlas_labels=atlas_labels,
                ),
            )
            if not result:
                return
            profile = result["profile"]
            orientation = result["orientation_qc"]
            metric_cards([
                ("Dimensions", profile["dimensions"], None),
                ("Segmented volume", profile["segmented_volume_mm3"], "mm³"),
                ("Components", profile["connected_components"], None),
                ("Anisotropy", orientation.get("anisotropy_ratio"), None),
            ])
            for warning in orientation.get("warnings", []):
                st.warning(warning)
            figures = imaging_slice_figures(result)
            tabs = st.tabs(["Orthogonal slices", "Segmentation/QC", "Atlas", "4D motion"])
            with tabs[0]:
                for key in ("axis_0", "axis_1", "axis_2", "plane"):
                    if key in figures:
                        st.plotly_chart(figures[key], width="stretch")
            with tabs[1]:
                smart_json({"profile": profile, "orientation_qc": orientation, "source_metadata": image_metadata}, title="Imaging QC", key="image_qc")
            with tabs[2]:
                if "atlas" in figures:
                    st.plotly_chart(figures["atlas"], width="stretch")
                smart_dataframe(result.get("atlas_summary", pd.DataFrame()), key="image_atlas_summary")
            with tabs[3]:
                if "motion" in figures:
                    st.plotly_chart(figures["motion"], width="stretch")
                smart_dataframe(result.get("motion_qc", pd.DataFrame()), key="image_motion_qc")
            _save_result("neuroimaging_connectomics", result)
    else:
        uploaded = _csv_upload("Upload ROI time-series CSV", "roi_upload")
        base = uploaded if uploaded is not None else roi_timeseries()
        time_options = ["<none>"] + list(base.columns)
        time_column = st.selectbox("Time column", time_options, index=time_options.index("time") if "time" in time_options else 0, key="roi_time")
        confounds = st.multiselect("Optional confound columns", [column for column in base.columns if column != time_column], key="roi_confounds")
        edge_threshold = st.slider("Absolute edge threshold", 0.0, 1.0, 0.30, 0.05, key="roi_edge_threshold")
        st.dataframe(base.head(100), width="stretch")
        if st.button("Calculate connectivity", type="primary", key="run_connectivity"):
            result = _safe_run(
                "neuroimaging_connectomics",
                "Calculating ROI connectivity and network QC",
                lambda: connectivity_from_timeseries(
                    base,
                    None if time_column == "<none>" else time_column,
                    confound_columns=tuple(confounds),
                    threshold_absolute=edge_threshold,
                ),
            )
            if not result:
                return
            network = result.get("network_summary", {})
            metric_cards([
                ("ROIs", result.get("roi_count"), None),
                ("Timepoints", result.get("timepoints"), None),
                ("Edges", network.get("edge_count"), None),
                ("Network density", network.get("network_density"), None),
            ])
            figures = connectivity_figures(result)
            if "matrix" in figures:
                st.plotly_chart(figures["matrix"], width="stretch")
            if "network" in figures:
                st.plotly_chart(figures["network"], width="stretch")
            smart_dataframe(result["strongest_connections"], key="connectivity_edges")
            smart_dataframe(network.get("nodes", pd.DataFrame()), key="connectivity_nodes")
            _save_result("neuroimaging_connectomics", result)


def _render_trials() -> None:
    uploaded = _csv_upload("Upload CNS trial/evidence table", "trials_upload")
    base = uploaded if uploaded is not None else trials()
    editor = st.data_editor(base, num_rows="dynamic", width="stretch", key="trials_editor")
    c1, c2, c3 = st.columns(3)
    source_name = c1.text_input("Evidence source", value="Bundled labelled demo" if uploaded is None else "Uploaded offline evidence table", key="trials_source")
    source_version = c2.text_input("Source version/date", value="demo-reference" if uploaded is None else "user supplied", key="trials_version")
    currency_days = c3.number_input("Stale after days", min_value=30, max_value=3650, value=365, step=30, key="trials_currency")
    if st.button("Build clinical evidence intelligence", type="primary", key="run_trials"):
        result = _safe_run(
            "cns_clinical_trials",
            "Normalizing trial records and evidence provenance",
            lambda: trial_intelligence(editor, currency_warning_days=int(currency_days), source_name=source_name, source_version=source_version),
        )
        if not result:
            return
        metrics = result["portfolio_metrics"]
        metric_cards([
            ("Trials", metrics.get("deduplicated_trial_records"), None),
            ("Active", metrics.get("active_records"), None),
            ("Attrition fraction", metrics.get("attrition_fraction"), None),
            ("Stale records", metrics.get("stale_records"), None),
        ])
        figures = trial_figures(result)
        for key in ("phase", "status", "compound_target", "endpoint"):
            if key in figures: st.plotly_chart(figures[key], width="stretch")
        tabs = st.tabs(["Normalized trials", "Status/phase", "Compounds & targets", "Endpoints", "Attrition", "Quality & provenance"])
        with tabs[0]: smart_dataframe(result["normalized_trials"], key="trial_normalized")
        with tabs[1]:
            smart_dataframe(result["status_summary"], key="trial_status")
            smart_dataframe(result["phase_summary"], key="trial_phase")
        with tabs[2]: smart_dataframe(result["compound_target_summary"], key="trial_compound_target")
        with tabs[3]:
            smart_dataframe(result["endpoint_summary"], key="trial_endpoint_summary")
            smart_dataframe(result["endpoint_records"], key="trial_endpoint_records")
        with tabs[4]: smart_dataframe(result["attrition_records"], key="trial_attrition")
        with tabs[5]:
            if result["evidence_gaps"]: st.warning("Evidence gaps: " + "; ".join(result["evidence_gaps"]))
            smart_json(result["source_provenance"], title="Source provenance", key="trial_provenance")
            smart_json(result["input_quality"], title="Input quality", key="trial_quality")
            smart_dataframe(result["duplicate_records"], key="trial_duplicates")
            smart_dataframe(result["stale_records"], key="trial_stale")
        _save_result("cns_clinical_trials", result)

def _render_precision() -> None:
    uploaded = _csv_upload("Upload de-identified cohort feature table", "precision_upload")
    base = uploaded if uploaded is not None else cohort()
    editor = st.data_editor(base, num_rows="dynamic", width="stretch", key="precision_editor")
    if editor.empty:
        st.info("Add de-identified cohort rows before analysis.")
        return
    columns = list(editor.columns)
    options = ["<none>"] + columns
    id_options = ["<generated>"] + columns
    c1, c2, c3 = st.columns(3)
    identifier = c1.selectbox("Sample identifier", id_options, index=id_options.index("sample_id") if "sample_id" in id_options else 0, key="precision_id")
    auto_clusters = c2.checkbox("Recommend cluster count", value=True, key="precision_auto_clusters")
    clusters = c3.slider("Cluster count", 2, min(8, max(2, len(editor) - 1)), 3, disabled=auto_clusters, key="precision_clusters")
    c4, c5, c6, c7 = st.columns(4)
    subgroup = c4.selectbox("Subgroup column", options, key="precision_subgroup")
    outcome = c5.selectbox("Outcome column", options, key="precision_outcome")
    subject = c6.selectbox("Longitudinal subject", options, key="precision_subject")
    time_column = c7.selectbox("Longitudinal time", options, key="precision_time")
    confounds = st.multiselect("Confound columns to reserve and audit", columns, key="precision_confounds")
    consensus_iterations = st.slider("Consensus seed iterations", 5, 60, 20, 5, key="precision_consensus_iterations")
    if st.button("Run consensus research stratification", type="primary", key="run_precision"):
        result = _safe_run(
            "precision_neurology",
            "Clustering cohort with stability and confound review",
            lambda: precision_neurology_workflow(
                editor,
                identifier_column=None if identifier == "<generated>" else identifier,
                cluster_count=None if auto_clusters else clusters,
                subgroup_column=None if subgroup == "<none>" else subgroup,
                outcome_column=None if outcome == "<none>" else outcome,
                subject_column=None if subject == "<none>" else subject,
                time_column=None if time_column == "<none>" else time_column,
                confound_columns=tuple(confounds),
                consensus_iterations=consensus_iterations,
            ),
        )
        if not result:
            return
        metrics = result["quality_metrics"]
        metric_cards([
            ("Samples", metrics.get("samples"), None),
            ("Features", metrics.get("features"), None),
            ("Clusters", metrics.get("clusters"), None),
            ("Stability", metrics.get("bootstrap_stability"), metrics.get("quality_band")),
        ])
        for warning in result.get("quality_warnings", []):
            st.warning(warning)
        figures = precision_figures(result)
        tabs = st.tabs(["Clusters", "Consensus/stability", "Confounds/subgroups", "Longitudinal", "Features"])
        with tabs[0]:
            if "clusters" in figures:
                st.plotly_chart(figures["clusters"], width="stretch")
            smart_dataframe(result["assignments"], key="precision_assignments")
        with tabs[1]:
            if "consensus" in figures:
                st.plotly_chart(figures["consensus"], width="stretch")
            if "stability" in figures:
                st.plotly_chart(figures["stability"], width="stretch")
            smart_dataframe(result.get("consensus_assignments", pd.DataFrame()), key="precision_consensus")
            smart_dataframe(result.get("candidate_cluster_metrics", pd.DataFrame()), key="precision_candidates")
        with tabs[2]:
            smart_dataframe(result.get("confound_review", pd.DataFrame()), key="precision_confound_review")
            smart_dataframe(result.get("subgroup_imbalance_review", pd.DataFrame()), key="precision_subgroup_review")
        with tabs[3]:
            if "trajectory" in figures:
                st.plotly_chart(figures["trajectory"], width="stretch")
            smart_dataframe(result.get("longitudinal_trajectories", pd.DataFrame()), key="precision_trajectories")
            smart_dataframe(result.get("cluster_transitions", pd.DataFrame()), key="precision_transitions")
        with tabs[4]:
            smart_dataframe(result["cluster_centers"], key="precision_centers")
            smart_dataframe(result["pca_loadings"], key="precision_loadings")
        _save_result("precision_neurology", result)

RENDERERS: dict[str, Callable[[], None]] = {
    "bbb_permeability": _render_bbb,
    "neuro_target_curation": _render_target_tagging,
    "neurotransmitter_pathway": _render_pathway,
    "ion_channel_classifier": _render_ion_channel,
    "gpcr_classifier": _render_gpcr,
    "cns_disease_targets": _render_disease_targets,
    "cns_drug_likeness": _render_cns_drug_likeness,
    "off_target_neurotoxicity": _render_off_target,
    "aggregation_risk": _render_aggregation,
    "cns_side_effects": _render_side_effects,
    "neuroinflammation": _render_neuroinflammation,
    "blood_csf_barrier": _render_blood_csf,
    "model_organism": _render_model_organism,
    "cns_adme_transporters": _render_adme,
    "brain_exposure_pk": _render_pk,
    "receptor_occupancy": _render_occupancy,
    "neurogenetics": _render_neurogenetics,
    "brain_expression_atlas": _render_expression,
    "neuro_omics_biomarkers": _render_omics,
    "eeg_meg_analytics": _render_eeg,
    "neuroimaging_connectomics": _render_imaging,
    "cns_clinical_trials": _render_trials,
    "precision_neurology": _render_precision,
    "neurovascular_research": lambda: render_step207_neuro_feature("neurovascular_research", safe_run=_safe_run, save_result=_save_result, csv_upload=_csv_upload),
    "sleep_circadian": lambda: render_step207_neuro_feature("sleep_circadian", safe_run=_safe_run, save_result=_save_result, csv_upload=_csv_upload),
    "fluid_biomarkers": lambda: render_step207_neuro_feature("fluid_biomarkers", safe_run=_safe_run, save_result=_save_result, csv_upload=_csv_upload),
    "digital_neurology": lambda: render_step207_neuro_feature("digital_neurology", safe_run=_safe_run, save_result=_save_result, csv_upload=_csv_upload),
    "neuroimmune_interactions": lambda: render_step207_neuro_feature("neuroimmune_interactions", safe_run=_safe_run, save_result=_save_result, csv_upload=_csv_upload),
    "cognitive_trajectory": lambda: render_step207_neuro_feature("cognitive_trajectory", safe_run=_safe_run, save_result=_save_result, csv_upload=_csv_upload),
    "neurorehabilitation": lambda: render_step207_neuro_feature("neurorehabilitation", safe_run=_safe_run, save_result=_save_result, csv_upload=_csv_upload),
    "polypharmacy_cns": lambda: render_step207_neuro_feature("polypharmacy_cns", safe_run=_safe_run, save_result=_save_result, csv_upload=_csv_upload),
    "brain_network_vulnerability": lambda: render_step207_neuro_feature("brain_network_vulnerability", safe_run=_safe_run, save_result=_save_result, csv_upload=_csv_upload),
    "neurodevelopmental_trajectory": lambda: render_step207_neuro_feature("neurodevelopmental_trajectory", safe_run=_safe_run, save_result=_save_result, csv_upload=_csv_upload),
    "neuro_oncology": lambda: render_v208_single_feature("Neuro/CNS", "neuro_oncology"),
    "epilepsy_diary": lambda: render_v208_single_feature("Neuro/CNS", "epilepsy_diary"),
    "movement_disorders": lambda: render_v208_single_feature("Neuro/CNS", "movement_disorders"),
    "autonomic_hrv": lambda: render_v208_single_feature("Neuro/CNS", "autonomic_hrv"),
    "speech_language": lambda: render_v208_single_feature("Neuro/CNS", "speech_language"),
    "neurodegeneration_progression": lambda: render_v208_single_feature("Neuro/CNS", "neurodegeneration_progression"),
    "neuropathology": lambda: render_v208_single_feature("Neuro/CNS", "neuropathology"),
    "neurocritical_care": lambda: render_v208_single_feature("Neuro/CNS", "neurocritical_care"),
}


def _render_overview() -> None:
    section_title(f"{len(MODULES)}-engine Neuro/CNS portfolio", "🧠")
    rows = pd.DataFrame(module_rows())
    metric_cards(
        [
            ("Sub-modules", len(MODULES), None),
            ("Workspaces", len(WORKSPACES), None),
            ("Deterministic/curated core", int(rows["readiness"].str.contains("Functional").sum()), None),
            ("Controlled clinical release", "Not eligible", "Requires independent evidence and responsible sign-off"),
        ]
    )
    workspace = st.selectbox("Filter portfolio", ["All", *WORKSPACES], key="neuro_overview_workspace")
    display = rows if workspace == "All" else rows[rows["workspace"] == workspace]
    smart_dataframe(
        display[["number", "title", "workspace", "basis", "readiness", "description", "boundary"]],
        key="neuro_portfolio",
        height=600,
    )
    figures = portfolio_figures(workspace_modules(workspace) if workspace != "All" else MODULES)
    if figures:
        visual_tabs = st.tabs(["Workspace coverage", "Workflow depth", "Readiness map"])
        for tab, key in zip(visual_tabs, ("workspace_coverage", "module_io_depth", "readiness_map")):
            with tab:
                if key in figures:
                    st.plotly_chart(figures[key], width="stretch", key=f"neuro_v209_portfolio_{key}_{workspace}")
    st.info(
        f"The {len(MODULES)} modules are implemented as independent backend engines inside one unified Neuro/CNS Studio. "
        "Curated and deterministic functions run locally; predictive-looking outputs remain explicitly screening/exploratory."
    )


def _render_guided_workflows() -> None:
    section_title("Guided Neuro/CNS workflows", "↗")
    st.caption("Workflows coordinate existing engines; they do not erase each engine's scientific boundary.")
    tabs = st.tabs(["Disease plan", "Compound → clinic", "Target → translation"])
    with tabs[0]:
        disease = st.selectbox("Disease workflow", list(DISEASE_WORKFLOWS), key="guided_disease")
        plan = disease_workflow_plan(disease)
        smart_dataframe(pd.DataFrame(plan["sequence"]), key="guided_disease_plan")
        st.info(plan["boundary"])
    with tabs[1]:
        preset = st.selectbox("Compound example", list(DEMO_SMILES), key="workflow_compound_preset")
        smiles = st.text_input("SMILES", DEMO_SMILES[preset], key="workflow_compound_smiles")
        include_binding = st.checkbox("Include demonstration target-binding profile", value=True, key="workflow_binding")
        include_pk = st.checkbox("Include brain-exposure PK simulation", value=True, key="workflow_pk")
        include_occupancy = st.checkbox("Include receptor occupancy", value=True, key="workflow_occupancy")
        if st.button("Run compound-to-clinic workflow", type="primary", key="run_compound_workflow"):
            pk_parameters = {
                "initial_plasma_concentration": 100.0,
                "half_life_hours": 6.0,
                "duration_hours": 24.0,
                "passive_permeability_factor": 0.75,
                "efflux_ratio": 0.35,
                "fraction_unbound_plasma": 0.10,
                "fraction_unbound_brain": 0.08,
            } if include_pk else None
            affinity_rows = [
                {"target": "DRD2", "kd": 10.0, "unit": "nM", "role": "primary"},
                {"target": "HTR2A", "kd": 45.0, "unit": "nM", "role": "off_target"},
            ] if include_occupancy else None
            payload = _safe_run(
                "compound_to_clinic_workflow",
                "Running integrated compound workflow",
                lambda: compound_to_clinic_workflow(
                    smiles,
                    compound_id=preset,
                    binding_rows=binding_profile().to_dict(orient="records") if include_binding else None,
                    pk_parameters=pk_parameters,
                    free_brain_concentration=25.0 if include_occupancy else None,
                    affinity_rows=affinity_rows,
                ),
            )
            if payload:
                for key, value in payload["results"].items():
                    _save_result(key, value)
                smart_dataframe(payload["consistency_findings"], key="compound_workflow_findings")
                smart_json(payload["quality_summary"], title="Workflow quality summary", key="compound_workflow_quality")
    with tabs[2]:
        identifier = st.text_input("Target identifier", value="DRD2", key="workflow_target_identifier")
        sequence = st.text_area("Optional FASTA/protein sequence", value="", height=140, key="workflow_target_sequence")
        if st.button("Run target-to-translation workflow", type="primary", key="run_target_workflow"):
            payload = _safe_run(
                "target_to_translation_workflow",
                "Running integrated target workflow",
                lambda: target_to_translation_workflow(identifier, sequence=sequence or None),
            )
            if payload:
                for key, value in payload["results"].items():
                    _save_result(key, value)
                smart_dataframe(payload["consistency_findings"], key="target_workflow_findings")
                smart_json(payload["quality_summary"], title="Workflow quality summary", key="target_workflow_quality")



def _render_advanced_additions() -> None:
    section_title("Nine advanced Neuro/CNS additions", "✦")
    st.caption("Step199 laboratories coordinate the original 23 engines; Step207 adds ten translational research workflows while preserving research-only boundaries.")
    feature_names = [title for _, title, _ in ADVANCED_FEATURES]
    tabs = st.tabs(feature_names)

    with tabs[0]:
        st.subheader("CNS Compound Optimization Board")
        base = pd.DataFrame([
            {"compound_id": name, "smiles": smiles, "potency_nm": value}
            for (name, smiles), value in zip(DEMO_SMILES.items(), [500, 800, 20, 5000])
        ])
        uploaded = _csv_upload("Optional analogue CSV/TSV", "advanced_compound_upload")
        editor = st.data_editor(uploaded if uploaded is not None else base, num_rows="dynamic", width="stretch", key="advanced_compound_editor")
        reference = st.text_input("Reference compound ID", value=str(editor.iloc[0]["compound_id"]) if not editor.empty else "", key="advanced_compound_reference")
        if st.button("Optimize analogue series", type="primary", key="run_advanced_compound"):
            result = _safe_run("advanced_compound_optimization", "Comparing CNS objectives", lambda: compound_optimization_board(editor.to_dict(orient="records"), reference_compound_id=reference or None))
            if result:
                metric_cards([("Recommended", result["recommended_screening_candidate"] or "None", None), ("Pareto candidates", len(result["pareto_optimal_compounds"]), None), ("Compounds", len(result["comparison"]), None)])
                smart_dataframe(result["comparison"], key="advanced_compound_comparison")
                smart_json({"weights": result["weights"], "boundary": result["scientific_boundary"]}, title="Optimization method", key="advanced_compound_method")

    with tabs[1]:
        st.subheader("CNS Safety Margin Matrix")
        concentration = st.number_input("Free brain concentration", min_value=0.0, value=20.0, key="advanced_safety_concentration")
        unit = st.selectbox("Concentration unit", ["nM", "uM", "pM"], key="advanced_safety_unit")
        base = pd.DataFrame([
            {"target": "DRD2", "kd": 5.0, "unit": "nM", "role": "primary"},
            {"target": "HTR2A", "kd": 50.0, "unit": "nM", "role": "off_target"},
            {"target": "SCN1A", "kd": 120.0, "unit": "nM", "role": "off_target"},
        ])
        editor = st.data_editor(base, num_rows="dynamic", width="stretch", key="advanced_safety_editor")
        primary = st.text_input("Primary target(s), comma separated", value="DRD2", key="advanced_safety_primary")
        if st.button("Calculate safety margins", type="primary", key="run_advanced_safety"):
            result = _safe_run("advanced_safety_margin", "Calculating target occupancy margins", lambda: safety_margin_matrix(concentration, editor.to_dict(orient="records"), concentration_unit=unit, primary_targets=[value.strip() for value in primary.split(",") if value.strip()]))
            if result:
                metric_cards([("Overall flag", result["overall_flag"], None), ("High off-targets", result["high_off_target_count"], None), ("Moderate off-targets", result["moderate_off_target_count"], None)])
                smart_dataframe(result["matrix"], key="advanced_safety_matrix")

    with tabs[2]:
        st.subheader("Aggregation Mutation Engineering Lab")
        sequence = st.text_area("Reference protein sequence", value=DEMO_AGGREGATION_SEQUENCE, height=170, key="advanced_aggregation_sequence")
        default_ref = "M1T" if sequence.strip().upper().startswith("M") else f"{sequence.strip().upper()[:1]}1T"
        mutations = st.text_area("Substitution hypotheses, one per line", value=default_ref, height=100, key="advanced_mutations")
        if st.button("Compare mutation hypotheses", type="primary", key="run_advanced_aggregation"):
            result = _safe_run("advanced_aggregation_engineering", "Scoring aggregation deltas", lambda: aggregation_mutation_engineering(sequence, [line.strip() for line in mutations.splitlines() if line.strip()]))
            if result:
                smart_dataframe(result["mutation_comparison"], key="advanced_mutation_comparison")
                if not result["screening_rescue_candidates"].empty:
                    smart_dataframe(result["screening_rescue_candidates"], key="advanced_rescue_candidates")
                st.warning(result["scientific_boundary"])

    with tabs[3]:
        st.subheader("Experimental Model Selection Assistant")
        target = st.text_input("Target", value="TREM2", key="advanced_model_target")
        disease = st.text_input("Disease context", value="Alzheimer disease", key="advanced_model_disease")
        context = st.selectbox("Experimental objective", ["mechanism", "genetic", "patient-specific", "pharmacology", "neuroinflammation"], key="advanced_model_context")
        if st.button("Rank experimental models", type="primary", key="run_advanced_model"):
            result = _safe_run("advanced_model_selection", "Ranking experimental systems", lambda: experimental_model_selection_assistant(target, disease=disease or None, desired_context=context))
            if result:
                metric_cards([("Primary model", result["recommended_primary_model"], None), ("Orthogonal model", result["recommended_orthogonal_model"], None)])
                smart_dataframe(result["ranked_models"], key="advanced_model_ranking")

    with tabs[4]:
        st.subheader("Dose-to-Brain-to-Effect Simulator")
        c1, c2, c3 = st.columns(3)
        initial = c1.number_input("Initial/Cmax concentration", min_value=0.0, value=100.0, key="advanced_dose_initial")
        half_life = c2.number_input("Half-life (h)", min_value=0.01, value=6.0, key="advanced_dose_half")
        duration = c3.number_input("Duration (h)", min_value=1.0, value=24.0, key="advanced_dose_duration")
        p1, p2, p3, p4 = st.columns(4)
        passive = p1.number_input("Passive factor", min_value=0.001, value=0.8, key="advanced_dose_passive")
        efflux = p2.number_input("Efflux ratio", min_value=0.0, value=0.3, key="advanced_dose_efflux")
        fup = p3.number_input("Fraction unbound plasma", min_value=0.001, max_value=1.0, value=0.1, key="advanced_dose_fup")
        fub = p4.number_input("Fraction unbound brain", min_value=0.001, max_value=1.0, value=0.08, key="advanced_dose_fub")
        affinities = st.data_editor(pd.DataFrame([{"target": "DRD2", "kd": 5.0, "unit": "nM"}, {"target": "HTR2A", "kd": 60.0, "unit": "nM"}]), num_rows="dynamic", width="stretch", key="advanced_dose_affinities")
        primary = st.text_input("Primary targets", value="DRD2", key="advanced_dose_primary")
        if st.button("Simulate dose-to-effect", type="primary", key="run_advanced_dose"):
            params = {"initial_plasma_concentration": initial, "half_life_hours": half_life, "duration_hours": duration, "passive_permeability_factor": passive, "efflux_ratio": efflux, "fraction_unbound_plasma": fup, "fraction_unbound_brain": fub}
            result = _safe_run("advanced_dose_effect", "Simulating exposure and occupancy", lambda: dose_to_effect_simulator(params, affinities.to_dict(orient="records"), primary_targets=[value.strip() for value in primary.split(",") if value.strip()]))
            if result:
                metric_cards([("Effect-window time", f"{result['time_inside_effect_window_hours']} h", None), ("Peak free brain", result["pk"]["peak_brain_unbound"], None), ("Kp,uu", result["pk"]["kp_uu_brain"], None)])
                curve = result["dose_to_effect_curve"]
                st.plotly_chart(px.line(curve, x="time_hours", y=["primary_occupancy_max", "off_target_occupancy_max"], title="Time-resolved target occupancy"), width="stretch")
                smart_dataframe(curve, key="advanced_dose_curve")

    with tabs[5]:
        st.subheader("Rare Neurological Disease Board")
        uploaded = _csv_upload("Optional annotated variant CSV/TSV", "advanced_rare_variant_upload")
        frame = uploaded if uploaded is not None else variants()
        smart_dataframe(frame, key="advanced_rare_input")
        phenotypes = st.text_input("Phenotype/HPO terms, comma separated", value="seizure, developmental delay", key="advanced_rare_phenotypes")
        disease = st.text_input("Disease context", value="Epilepsy", key="advanced_rare_disease")
        if st.button("Build rare disease board", type="primary", key="run_advanced_rare"):
            result = _safe_run("advanced_rare_disease", "Integrating variant and Neuro context", lambda: rare_neurological_disease_board(frame, phenotype_terms=[value.strip() for value in phenotypes.split(",") if value.strip()], disease=disease or None))
            if result:
                smart_dataframe(result["gene_summary"], key="advanced_rare_gene_summary")
                smart_dataframe(result["variant_board"], key="advanced_rare_variant_board", height=500)

    with tabs[6]:
        st.subheader("Neuro Multi-Omics Disease Signature Builder")
        uploaded = _csv_upload("Optional omics CSV/TSV", "advanced_signature_upload")
        frame = uploaded if uploaded is not None else omics()
        group = st.selectbox("Group column", list(frame.columns), index=list(frame.columns).index("group") if "group" in frame.columns else 0, key="advanced_signature_group")
        max_features = st.slider("Maximum signature features", 2, 20, 6, key="advanced_signature_count")
        if st.button("Build cross-validated signature", type="primary", key="run_advanced_signature"):
            result = _safe_run("advanced_multiomics_signature", "Building disease signature", lambda: multiomics_disease_signature_builder(frame, group, maximum_features=max_features))
            if result:
                metric_cards([("Cross-validated AUC", result["cross_validated_auc"], None), ("Features", len(result["selected_signature_features"]), None), ("Samples", len(result["sample_scores"]), None)])
                smart_dataframe(result["selected_signature_features"], key="advanced_signature_features")
                smart_dataframe(result["sample_scores"], key="advanced_signature_scores")

    with tabs[7]:
        st.subheader("Digital Neurophysiology Review Board")
        uploaded = _csv_upload("Optional EEG/MEG time-series CSV/TSV", "advanced_review_signal_upload")
        frame = uploaded if uploaded is not None else eeg()
        rate = st.number_input("Sampling rate (Hz)", min_value=2.0, value=256.0, key="advanced_review_rate")
        time_column = st.selectbox("Time column", ["None", *frame.columns.astype(str).tolist()], index=1 if "time" in frame.columns else 0, key="advanced_review_time")
        reviewer = st.data_editor(pd.DataFrame(columns=["channel", "time_seconds", "decision", "note"]), num_rows="dynamic", width="stretch", key="advanced_review_annotations")
        if st.button("Build synchronized review board", type="primary", key="run_advanced_review"):
            result = _safe_run("advanced_neurophysiology_review", "Analyzing and synchronizing review", lambda: neurophysiology_review_board(frame, rate, None if time_column == "None" else time_column, reviewer_event_rows=reviewer.to_dict(orient="records")))
            if result:
                metric_cards([("Signal quality", result["signal_quality_grade"], None), ("Candidate events", len(result["reviewed_events"]), None), ("Review completion", f"{result['review_completion_fraction']:.0%}", None)])
                smart_dataframe(result["channel_review_board"], key="advanced_review_channels")
                smart_dataframe(result["reviewed_events"], key="advanced_review_events")

    with tabs[8]:
        st.subheader("3D Brain Digital Twin Viewer")
        uploaded = st.file_uploader("Optional NPY brain/volume array", type=["npy"], key="advanced_twin_upload")
        if uploaded is not None:
            volume = np.load(io.BytesIO(uploaded.getvalue()), allow_pickle=False)
        else:
            volume = np.zeros((24, 24, 16), dtype=float)
            volume[5:18, 7:20, 4:13] = 1.0
            volume[9:15, 10:17, 6:11] = 2.0
        threshold = st.number_input("Display threshold", value=float(np.nanpercentile(volume, 90)), key="advanced_twin_threshold")
        if st.button("Build 3D digital twin", type="primary", key="run_advanced_twin"):
            result = _safe_run("advanced_brain_digital_twin", "Generating 3D surface", lambda: brain_digital_twin_viewer(volume, threshold=threshold))
            if result:
                surface = result["surface_points"]
                metric_cards([("Surface points", result["surface_point_count"], None), ("Downsampled", result["downsampled"], None), ("Shape", " × ".join(map(str, result["shape"])), None)])
                if not surface.empty:
                    figure = go.Figure(data=[go.Scatter3d(x=surface["x"], y=surface["y"], z=surface["z"], mode="markers", marker={"size": 2, "color": surface["intensity"], "colorscale": "Viridis", "opacity": 0.65})])
                    figure.update_layout(height=650, scene={"aspectmode": "data"}, title="Exploratory 3D brain/volume surface")
                    st.plotly_chart(figure, width="stretch")
                st.warning(result["scientific_boundary"])


def _render_max_potential_systems() -> None:
    section_title("Nine maximum-potential systems", "◆")
    st.caption("Step200 evidence, validation, applicability, uncertainty, recovery and release-control systems now cover all 41 Neuro/CNS modules.")
    names = [title for _, title, _ in MAX_POTENTIAL_FEATURES]
    tabs = st.tabs(names)
    results = _result_store()

    with tabs[0]:
        st.subheader("Neuro Evidence Knowledge Graph")
        if not results:
            st.info("Run one or more modules first; the graph never invents unsupported biological links.")
        elif st.button("Build evidence graph", type="primary", key="run_max_evidence_graph"):
            output = _safe_run("max_evidence_graph", "Building evidence graph", lambda: evidence_knowledge_graph(results))
            if output:
                metric_cards([("Nodes", output["node_count"], None), ("Edges", output["edge_count"], None), ("Orphans", output["orphan_node_count"], None)])
                smart_dataframe(output["nodes"], key="max_evidence_nodes")
                smart_dataframe(output["edges"], key="max_evidence_edges")

    with tabs[1]:
        st.subheader("Benchmark Validation Center")
        rng = np.random.default_rng(42)
        labels = rng.integers(0, 2, 160)
        demo = pd.DataFrame({"label": labels, "score": np.clip(labels * 0.55 + rng.normal(0.22, 0.18, len(labels)), 0, 1), "site": np.where(np.arange(len(labels)) % 2, "Site-B", "Site-A")})
        uploaded = _csv_upload("Optional benchmark CSV/TSV", "max_benchmark_upload")
        frame = uploaded if uploaded is not None else demo
        columns = frame.columns.astype(str).tolist()
        label_column = st.selectbox("Binary label column", columns, index=columns.index("label") if "label" in columns else 0, key="max_benchmark_label")
        score_column = st.selectbox("Probability/score column", columns, index=columns.index("score") if "score" in columns else min(1, len(columns)-1), key="max_benchmark_score")
        group_options = ["None", *columns]
        group_column = st.selectbox("Optional subgroup/site column", group_options, index=group_options.index("site") if "site" in group_options else 0, key="max_benchmark_group")
        threshold = st.slider("Decision threshold", 0.05, 0.95, 0.50, 0.01, key="max_benchmark_threshold")
        if st.button("Run locked benchmark summary", type="primary", key="run_max_benchmark"):
            output = _safe_run("max_benchmark_validation", "Calculating benchmark metrics", lambda: benchmark_validation_center(frame, label_column=label_column, score_column=score_column, threshold=threshold, group_column=None if group_column == "None" else group_column))
            if output:
                smart_dataframe(output["metrics"], key="max_benchmark_metrics")
                smart_dataframe(output["calibration"], key="max_benchmark_calibration")
                smart_dataframe(output["subgroup_performance"], key="max_benchmark_subgroups")

    with tabs[2]:
        st.subheader("Applicability Domain Inspector")
        rng = np.random.default_rng(7)
        reference = pd.DataFrame(rng.normal(size=(120, 5)), columns=[f"feature_{i}" for i in range(1, 6)])
        query = pd.DataFrame(rng.normal(size=(12, 5)), columns=reference.columns)
        query.loc[0] = 7.0
        if st.button("Inspect reference/query domain", type="primary", key="run_max_domain"):
            output = _safe_run("max_applicability_domain", "Calculating robust feature-space distances", lambda: applicability_domain_inspector(reference, query))
            if output:
                metric_cards([("Inside fraction", f"{output['inside_fraction']:.0%}", None), ("Reference rows", output["reference_rows"], None), ("Query rows", output["query_rows"], None)])
                smart_dataframe(output["assessment"], key="max_domain_assessment")

    with tabs[3]:
        st.subheader("Uncertainty & Sensitivity Lab")
        c1, c2 = st.columns(2)
        concentration = c1.number_input("Free brain concentration (nM)", min_value=0.001, value=20.0, key="max_unc_concentration")
        affinity = c2.number_input("Affinity Kd (nM)", min_value=0.001, value=5.0, key="max_unc_affinity")
        cv = st.slider("Parameter coefficient of variation", 0.01, 0.80, 0.20, 0.01, key="max_unc_cv")
        if st.button("Propagate uncertainty", type="primary", key="run_max_uncertainty"):
            evaluator = lambda free_brain_nm, kd_nm: 100.0 * free_brain_nm / (free_brain_nm + kd_nm)
            output = _safe_run("max_uncertainty", "Running Monte Carlo uncertainty analysis", lambda: uncertainty_sensitivity_lab(evaluator, {"free_brain_nm": concentration, "kd_nm": affinity}, {"free_brain_nm": {"distribution": "lognormal", "cv": cv, "minimum": 0.0}, "kd_nm": {"distribution": "lognormal", "cv": cv, "minimum": 0.0001}}, iterations=500))
            if output:
                smart_json(output["output_summary"], title="Occupancy uncertainty", key="max_unc_summary")
                smart_dataframe(output["sensitivity"], key="max_unc_sensitivity")

    with tabs[4]:
        st.subheader("Scientific Resource Qualification Manager")
        output = resource_qualification_manager()
        metric_cards([("Resource-ready", output["resource_ready_modules"], None), ("Exploratory", output["exploratory_modules"], None), ("Blocked", output["blocked_modules"], None), ("Completion", f"{output['completion_fraction']:.0%}", None)])
        smart_dataframe(output["modules"], key="max_resource_modules", height=560)
        smart_dataframe(output["resources"], key="max_resource_rows")

    with tabs[5]:
        st.subheader("Cross-Module Contradiction Resolver")
        output = contradiction_resolution_board(results)
        metric_cards([("Open findings", output["open_count"], None), ("High severity", output["high_count"], None), ("Auto-fixable input issues", output["auto_fixable_count"], None)])
        smart_dataframe(output["board"], key="max_contradiction_board")
        st.warning(output["scientific_boundary"])

    with tabs[6]:
        st.subheader("Resilient Batch Pipeline Orchestrator")
        tasks = [
            {"task_id": "caffeine", "module_key": "bbb_permeability", "compound_rows": [{"compound_id": "caffeine", "smiles": DEMO_SMILES["Caffeine"]}]},
            {"task_id": "invalid_isolated", "module_key": "bbb_permeability", "compound_rows": [{"compound_id": "invalid", "smiles": "not-a-smiles"}]},
        ]
        st.code(json.dumps(tasks, indent=2), language="json")
        if st.button("Run isolated batch tasks", type="primary", key="run_max_batch"):
            from biointel.neuro_cns.jobs import execute_neuro_job_payload
            output = _safe_run("max_batch_orchestrator", "Executing isolated Neuro tasks", lambda: batch_pipeline_orchestrator(tasks, executor=execute_neuro_job_payload, continue_on_error=True))
            if output:
                metric_cards([("Submitted", output["submitted"], None), ("Completed", output["completed"], None), ("Failed", output["failed"], None)])
                smart_dataframe(pd.DataFrame(output["tasks"]), key="max_batch_tasks")

    with tabs[7]:
        st.subheader("Failure Mode & Recovery Center")
        errors = st.session_state.get(ERROR_STATE_KEY)
        if not isinstance(errors, list) or not errors:
            st.info("No captured Neuro/CNS execution failures in this session. Invalid tasks are isolated and recorded when they occur.")
        else:
            output = failure_recovery_center(errors)
            metric_cards([("Captured errors", output["error_count"], None), ("Retry-safe", output["retry_safe_count"], None)])
            smart_dataframe(output["errors"], key="max_recovery_errors")
            smart_dataframe(output["category_summary"], key="max_recovery_categories")

    with tabs[8]:
        st.subheader("Maximum-Potential Release Dashboard")
        output = maximum_potential_release_dashboard(results)
        metric_cards([("Software readiness", output["average_software_readiness"], "/10"), ("Scientific readiness", output["average_scientific_readiness"], "/10"), ("Overall readiness", output["average_overall_readiness"], "/10"), ("Controlled release", "Eligible" if output["controlled_release_eligible"] else "Blocked", None)])
        smart_dataframe(output["module_dashboard"], key="max_release_dashboard", height=620)
        for blocker in output["blockers"]:
            st.warning(blocker)


def _render_completion_systems() -> None:
    section_title("Remaining completion systems", "✓")
    st.caption("Step201 completion systems cover the prior software-side gaps: resource binding, specialist-engine qualification, privacy, study design, leakage, drift, multi-site reproducibility, PDF reporting and integrity-preserving evidence packs.")
    tabs = st.tabs([title for _, title, _ in COMPLETION_FEATURES])

    with tabs[0]:
        st.subheader("Scientific Resource Binding Studio")
        uploaded = st.file_uploader("Upload local scientific resource", type=["csv", "tsv", "txt", "json", "fasta", "fa", "faa", "vcf"], key="step201_resource_upload")
        c1, c2 = st.columns(2)
        resource_id = c1.text_input("Resource ID", value="approved_neuro_resource", key="step201_resource_id")
        provider = c2.text_input("Provider", value="User-approved provider", key="step201_resource_provider")
        release_version = c1.text_input("Provider release/version", value="v1.0", key="step201_resource_release")
        kind = c2.text_input("Resource kind", value="Neuro/CNS reference dataset", key="step201_resource_kind")
        licence_status = c1.selectbox("Licence status", ["not-reviewed", "reviewed-restricted", "approved", "verified"], key="step201_resource_licence")
        commercial_status = c2.selectbox("Commercial-use status", ["unknown", "not-allowed", "allowed", "not-applicable", "approved"], key="step201_resource_commercial")
        schema_version = c1.text_input("Schema version", value="1", key="step201_resource_schema")
        validation_status = c2.selectbox("Validation status", ["unreviewed", "schema-checked", "qualified", "externally-validated", "schema-and-content-qualified"], key="step201_resource_validation")
        notes = st.text_area("Binding notes", height=80, key="step201_resource_notes")
        if uploaded is not None and st.button("Validate binding", type="primary", key="step201_validate_binding"):
            result = _safe_run(
                "completion_resource_binding",
                "Validating local resource binding",
                lambda: build_resource_binding(
                    uploaded.getvalue(), file_name=uploaded.name, resource_id=resource_id, provider=provider,
                    release_version=release_version, kind=kind, licence_status=licence_status,
                    commercial_use_status=commercial_status, schema_version=schema_version,
                    validation_status=validation_status, notes=notes,
                ),
            )
            if result:
                smart_json(result, title="Validated binding", key="step201_binding_result")
                st.download_button("Download binding JSON", json.dumps(result, indent=2, default=str).encode("utf-8"), f"{resource_id}-binding.json", "application/json", key="step201_download_binding", width="stretch")
                if st.button("Persist binding locally", key="step201_persist_binding"):
                    saved = _safe_run(
                        "completion_resource_binding_persist",
                        "Persisting resource binding",
                        lambda: persist_resource_binding(result, uploaded.getvalue(), registry_directory=Path.home() / ".biointel" / "neuro_cns" / "resources"),
                    )
                    if saved:
                        st.success(f"Binding registry: {saved['registry_path']}")

    with tabs[1]:
        st.subheader("Specialist Engine Qualification Center")
        run_versions = st.checkbox("Run lightweight version commands", value=False, key="step201_engine_versions")
        if st.button("Inspect specialist engines", type="primary", key="step201_engine_scan"):
            result = _safe_run("completion_engine_qualification", "Inspecting specialist engines", lambda: specialist_engine_inventory(run_version_checks=run_versions))
            if result:
                metric_cards([("Installed", result["installed_count"], None), ("Missing", result["missing_count"], None), ("Controlled release", "Blocked", "Detection is not qualification")])
                smart_dataframe(result["engines"], key="step201_engine_inventory", height=540)
                st.warning(result["scientific_boundary"])

    with tabs[2]:
        st.subheader("Privacy & De-identification Guard")
        demo = pd.DataFrame({
            "patient_id": ["10000001", "10000002", "10000003"],
            "email": ["a@example.org", "b@example.org", "c@example.org"],
            "visit_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "biomarker": [1.2, 2.4, 1.8],
        })
        uploaded = _csv_upload("Optional cohort CSV/TSV", "step201_privacy_upload")
        frame = uploaded if uploaded is not None else demo
        smart_dataframe(frame.head(100), key="step201_privacy_preview")
        if st.button("Scan privacy risk", type="primary", key="step201_privacy_scan"):
            result = _safe_run("completion_privacy_scan", "Scanning direct identifiers", lambda: privacy_scan_frame(frame))
            if result:
                metric_cards([("High finding groups", result["high_finding_groups"], None), ("Export block recommended", result["export_block_recommended"], None), ("Cells sampled", result["cells_sampled"], None)])
                smart_dataframe(result["findings"], key="step201_privacy_findings")
        drop_cols = st.multiselect("Drop columns", list(map(str, frame.columns)), default=[col for col in frame.columns if str(col).lower() in {"email"}], key="step201_privacy_drop")
        hash_cols = st.multiselect("Hash/pseudonymize columns", list(map(str, frame.columns)), default=[col for col in frame.columns if str(col).lower() in {"patient_id"}], key="step201_privacy_hash")
        date_cols = st.multiselect("Shift date columns", list(map(str, frame.columns)), default=[col for col in frame.columns if "date" in str(col).lower()], key="step201_privacy_dates")
        shift_days = st.number_input("Date shift days", min_value=-3650, max_value=3650, value=30, key="step201_privacy_shift")
        deidentified = deidentify_frame(frame, drop_columns=drop_cols, hash_columns=hash_cols, date_columns=date_cols, date_shift_days=int(shift_days))
        st.download_button("Download de-identified CSV", deidentified.to_csv(index=False).encode("utf-8"), "neuro_cohort_deidentified.csv", "text/csv", key="step201_privacy_download", width="stretch")

    with tabs[3]:
        st.subheader("Study Design & Power Planner")
        design = st.selectbox("Design", ["two_group_continuous", "paired_continuous", "binary"], key="step201_power_design")
        effect = st.number_input("Effect size (standardized difference; for binary, absolute rate difference)", min_value=0.01, value=0.50, step=0.05, key="step201_power_effect")
        alpha = st.number_input("Two-sided alpha", min_value=0.001, max_value=0.20, value=0.05, step=0.005, key="step201_power_alpha")
        power = st.number_input("Power", min_value=0.50, max_value=0.99, value=0.80, step=0.01, key="step201_power_target")
        dropout = st.number_input("Dropout fraction", min_value=0.0, max_value=0.70, value=0.10, step=0.05, key="step201_power_dropout")
        baseline = st.number_input("Baseline event rate (binary only)", min_value=0.01, max_value=0.99, value=0.30, step=0.05, key="step201_power_baseline")
        if st.button("Calculate study size", type="primary", key="step201_power_run"):
            result = _safe_run("completion_study_design", "Calculating analytic sample size", lambda: study_design_power_planner(design=design, effect_size=float(effect), alpha=float(alpha), power=float(power), dropout_fraction=float(dropout), baseline_rate=float(baseline) if design == "binary" else None))
            if result:
                metric_cards([("Total N", result["total_n"], None), ("Control N", result["control_n"], None), ("Treatment N", result["treatment_n"], None)])
                smart_json(result, title="Study design plan", key="step201_power_result")

    with tabs[4]:
        st.subheader("Data Leakage & Cohort Split Auditor")
        base = pd.DataFrame({
            "subject_id": ["S1", "S2", "S3", "S4", "S1", "S6"],
            "site": ["A", "A", "B", "B", "A", "C"],
            "split": ["train", "train", "test", "test", "test", "validation"],
            "feature_1": [0.1, 0.2, 0.8, 0.9, 0.1, 0.6],
            "outcome": [0, 0, 1, 1, 0, 1],
            "outcome_copy": [0, 0, 1, 1, 0, 1],
        })
        uploaded = _csv_upload("Optional modelling table", "step201_leakage_upload")
        frame = uploaded if uploaded is not None else base
        columns = list(map(str, frame.columns))
        outcome = st.selectbox("Outcome column", columns, index=columns.index("outcome") if "outcome" in columns else 0, key="step201_leakage_outcome")
        split = st.selectbox("Split column", ["None", *columns], index=columns.index("split") + 1 if "split" in columns else 0, key="step201_leakage_split")
        subject = st.selectbox("Subject ID column", ["None", *columns], index=columns.index("subject_id") + 1 if "subject_id" in columns else 0, key="step201_leakage_subject")
        groups = st.multiselect("Group columns that must stay within one split", columns, default=["site"] if "site" in columns else [], key="step201_leakage_groups")
        if st.button("Audit leakage", type="primary", key="step201_leakage_run"):
            result = _safe_run("completion_leakage_audit", "Auditing cohort leakage", lambda: leakage_split_audit(frame, outcome_column=outcome, split_column=None if split == "None" else split, subject_id_column=None if subject == "None" else subject, group_columns=groups))
            if result:
                metric_cards([("Critical", result["critical_findings"], None), ("High", result["high_findings"], None), ("Release blocked", result["release_blocked"], None)])
                smart_dataframe(result["findings"], key="step201_leakage_findings")

    with tabs[5]:
        st.subheader("Dataset Drift & Monitoring Center")
        rng = np.random.default_rng(42)
        reference_demo = pd.DataFrame({"age": rng.normal(55, 10, 200), "biomarker": rng.normal(0, 1, 200), "site": rng.choice(["A", "B"], 200)})
        current_demo = pd.DataFrame({"age": rng.normal(63, 12, 180), "biomarker": rng.normal(0.6, 1.2, 180), "site": rng.choice(["A", "B", "C"], 180)})
        ref_upload = _csv_upload("Reference CSV/TSV", "step201_drift_reference")
        cur_upload = _csv_upload("Current CSV/TSV", "step201_drift_current")
        reference = ref_upload if ref_upload is not None else reference_demo
        current = cur_upload if cur_upload is not None else current_demo
        common = sorted(set(map(str, reference.columns)) & set(map(str, current.columns)))
        features = st.multiselect("Features", common, default=common, key="step201_drift_features")
        if st.button("Measure drift", type="primary", key="step201_drift_run"):
            result = _safe_run("completion_drift_monitor", "Measuring distribution drift", lambda: dataset_drift_monitor(reference, current, features=features))
            if result:
                metric_cards([("Status", result["monitoring_status"], None), ("Critical features", result["critical_features"], None), ("Warning features", result["warning_features"], None)])
                smart_dataframe(result["drift"], key="step201_drift_table")

    with tabs[6]:
        st.subheader("Multi-Site Reproducibility Analyzer")
        base = pd.DataFrame({"site": ["Site-A", "Site-B", "Site-C", "Site-D"], "estimate": [0.52, 0.40, 0.61, 0.30], "standard_error": [0.10, 0.12, 0.11, 0.14]})
        uploaded = _csv_upload("Optional site-level estimates", "step201_multisite_upload")
        editor = st.data_editor(uploaded if uploaded is not None else base, num_rows="dynamic", width="stretch", key="step201_multisite_editor")
        if st.button("Analyze reproducibility", type="primary", key="step201_multisite_run"):
            result = _safe_run("completion_multisite", "Estimating cross-site reproducibility", lambda: multisite_reproducibility_analyzer(editor, site_column="site", estimate_column="estimate", standard_error_column="standard_error"))
            if result:
                metric_cards([("Sites", result["site_count"], None), ("Random effect", round(result["random_effect"], 4), None), ("I²", f"{result['i_squared_percent']:.1f}%", result["heterogeneity_grade"])])
                smart_dataframe(result["site_results"], key="step201_multisite_results")
                smart_json({k: v for k, v in result.items() if k != "site_results"}, title="Reproducibility summary", key="step201_multisite_summary")

    with tabs[7]:
        st.subheader("Professional PDF Scientific Report")
        results = _result_store()
        if not results:
            st.info("Run one or more modules before exporting a PDF report.")
        else:
            project = st.text_input("PDF project name", value="BioIntel Neuro/CNS", key="step201_pdf_project")
            analyst = st.text_input("PDF analyst/reviewer", value="", key="step201_pdf_analyst")
            notes = st.text_area("PDF notes", height=80, key="step201_pdf_notes")
            pdf_bytes = professional_pdf_report(results, project_name=project, analyst=analyst, notes=notes, execution_history=st.session_state.get(EXECUTION_STATE_KEY, []), error_records=st.session_state.get(ERROR_STATE_KEY, []))
            st.download_button("Download professional PDF", pdf_bytes, "BioIntel-Neuro-CNS-Scientific-Report.pdf", "application/pdf", key="step201_pdf_download", width="stretch")

    with tabs[8]:
        st.subheader("Release Evidence Pack Builder")
        results = _result_store()
        if not results:
            st.info("Run one or more modules before building an evidence pack.")
        else:
            project = st.text_input("Evidence-pack project name", value="BioIntel Neuro/CNS", key="step201_pack_project")
            analyst = st.text_input("Evidence-pack reviewer", value="", key="step201_pack_analyst")
            pack = release_evidence_pack(results, project_name=project, analyst=analyst, execution_history=st.session_state.get(EXECUTION_STATE_KEY, []), error_records=st.session_state.get(ERROR_STATE_KEY, []), engine_inventory=specialist_engine_inventory(run_version_checks=False))
            st.download_button("Download release evidence ZIP", pack, "BioIntel-Neuro-CNS-Release-Evidence-Pack.zip", "application/zip", key="step201_pack_download", width="stretch")
            st.warning("The pack preserves integrity and review context; controlled release still requires approved evidence and responsible sign-off.")

def _render_quality_and_resources() -> None:
    section_title("Scientific quality, consistency & resources", "✓")
    results = _result_store()
    if results:
        summary = result_quality_summary(results)
        metric_cards([
            ("Completed module results", summary["module_results"], None),
            ("High findings", summary["high_findings"], None),
            ("Medium findings", summary["medium_findings"], None),
            ("Status", summary["status"], None),
        ])
        smart_dataframe(evaluate_results(results), key="neuro_consistency_findings")
    else:
        st.info("Run modules to activate cross-module consistency checks.")
    st.subheader("Scientific resource registry")
    resources = resource_registry_frame()
    smart_dataframe(resources, key="neuro_resource_registry")
    st.download_button(
        "Download resource registry CSV",
        resources.to_csv(index=False).encode("utf-8"),
        "BioIntel-Neuro-Resource-Registry.csv",
        "text/csv",
        width="stretch",
        key="download_neuro_resource_registry",
    )
    adapter_rows = [
        {"adapter_group": "Neuroimaging", **optional_adapter_status()},
        {"adapter_group": "Neural signals", **optional_signal_adapter_status()},
    ]
    st.subheader("Step202 module-wise hardening and maximum-potential matrix")
    recommendations = recommendation_frame()
    smart_dataframe(recommendations, key="neuro_step200_recommendations", height=620)
    st.subheader("Remaining qualification gates")
    smart_dataframe(gate_summary(), key="neuro_step200_gate_summary")
    st.subheader("Optional specialist adapters")
    smart_dataframe(pd.DataFrame(adapter_rows), key="neuro_optional_adapters")
    st.warning("Installed adapters still require target-machine qualification, version locking, test data and licence review before controlled use.")


def _render_production_systems(project_root: Path) -> None:
    section_title("Step202 production readiness, installation & demo systems", "⚙")
    st.caption("Ten final software-side systems for official-resource binding plans, specialist-engine setup, benchmark qualification, one-click demonstrations, update rollback, role access, review, compute qualification, diagnostics and controlled exports.")
    tabs = st.tabs([feature[1] for feature in PRODUCTION_FEATURES])

    with tabs[0]:
        st.subheader("Official Data Pack Manager")
        plan = official_resource_plan()
        metric_cards([("Planned resources", plan["resource_count"], None), ("Modules covered", len(plan["covered_modules"]), None), ("Official data bundled", "No", "User-approved binding required")])
        smart_dataframe(plan["resources"], key="step202_resource_plan", height=520)
        st.warning(plan["scientific_boundary"])

    with tabs[1]:
        st.subheader("Specialist Engine Installation & Qualification")
        run_versions = st.checkbox("Probe installed engine versions", value=False, key="step202_engine_versions")
        if st.button("Scan specialist engines", type="primary", key="step202_scan_engines"):
            output = _safe_run("step202_engine_plan", "Scanning specialist engines", lambda: specialist_engine_installation_plan(run_version_checks=run_versions))
            if output:
                smart_dataframe(output["plan"], key="step202_engine_plan_table", height=520)
                metric_cards([("Installed", output["installed_count"], None), ("Pending", output["pending_count"], None), ("Auto-install candidates", output["automatic_install_candidates"], None)])
                st.warning(output["scientific_boundary"])

    with tabs[2]:
        st.subheader("External Benchmark Qualification Center")
        demo_registry = load_demo_asset("benchmark_registry_template.csv", project_root)
        uploaded = _csv_upload("Optional benchmark registry CSV", "step202_benchmark_registry")
        frame = uploaded if uploaded is not None else demo_registry
        smart_dataframe(frame, key="step202_benchmark_input")
        if st.button("Validate benchmark registry", type="primary", key="step202_validate_benchmarks"):
            output = _safe_run("step202_benchmark_registry", "Checking external benchmark gates", lambda: validate_benchmark_registry(frame.to_dict(orient="records")))
            if output:
                smart_dataframe(output["benchmarks"], key="step202_benchmark_output")
                metric_cards([("Qualified modules", output["qualified_modules"], None), ("Submitted modules", output["submitted_modules"], None), ("Coverage", f"{output['coverage_fraction']:.1%}", None)])

    with tabs[3]:
        st.subheader("One-Click 41-Module Demo Showcase")
        status = verify_demo_pack(project_root)
        metric_cards([("Demo assets", status.get("dataset_count", 0), None), ("Integrity", "PASS" if status["passed"] else "FAIL", None), ("Real patient data", "No", "Synthetic demonstration only")])
        smart_dataframe(status["files"], key="step202_demo_manifest", height=460)
        c1, c2 = st.columns(2)
        if c1.button("Run all 41 demo modules", type="primary", disabled=not status["passed"], key="step202_run_complete_demo"):
            output = _safe_run("step202_complete_demo", "Running 41-module synthetic demonstration", run_complete_demo_showcase, store=False)
            if output:
                st.session_state[RESULT_STATE_KEY] = output
                st.success(f"Loaded {len(output)}/41 module results into the current session. Open Unified report to export JSON, HTML, Markdown or PDF.")
        if status["passed"]:
            c2.download_button("Download complete demo data pack", demo_pack_zip(project_root), "BioIntel-Neuro-Step202-Demo-Pack.zip", "application/zip", width="stretch", key="step202_download_demo_pack")
        st.warning(status["scientific_boundary"])

    with tabs[4]:
        st.subheader("Signed Update & Rollback Center")
        st.caption("Creates a local integrity snapshot before an update. Cryptographic publisher signing must still be supplied by the release owner.")
        snapshot_paths = [
            "src/biointel/neuro_cns", "data/neuro_cns", "pages/263_Neuro_CNS_Intelligence_Studio.py",
            "INSTALL_WINDOWS.bat", "RUN_BOTH_WINDOWS.bat", "requirements.lock",
        ]
        if st.button("Build pre-update Neuro snapshot", type="primary", key="step202_snapshot"):
            expanded: list[str] = []
            for relative in snapshot_paths:
                target = project_root / relative
                if target.is_dir():
                    expanded.extend(str(path.relative_to(project_root)) for path in target.rglob("*") if path.is_file())
                elif target.is_file():
                    expanded.append(relative)
            payload = _safe_run("step202_update_snapshot", "Building integrity snapshot", lambda: create_update_snapshot(project_root, include_paths=expanded, label="Step202-pre-update"), store=False)
            if payload:
                st.download_button("Download rollback snapshot", payload, "BioIntel-Step202-Neuro-Rollback-Snapshot.zip", "application/zip", width="stretch", key="step202_snapshot_download")

    with tabs[5]:
        st.subheader("Enterprise Security & Role Access")
        smart_dataframe(role_access_matrix(), key="step202_role_matrix", height=360)
        c1, c2 = st.columns(2)
        role = c1.selectbox("Role", ["viewer", "researcher", "reviewer", "release_manager", "administrator"], key="step202_role")
        action = c2.selectbox("Action", ["view_results", "run_modules", "save_project", "review_results", "approve_release", "bind_resources", "manage_updates", "manage_engines"], key="step202_action")
        decision = authorize_action(role, action)
        st.success("Allowed") if decision["allowed"] else st.error("Blocked")
        st.caption(decision["reason"])

    with tabs[6]:
        st.subheader("Multi-Reviewer Scientific Sign-off")
        results = _result_store()
        reviewer = st.text_input("Reviewer", value="", key="step202_reviewer")
        role = st.selectbox("Reviewer role", ["reviewer", "release_manager", "administrator"], key="step202_reviewer_role")
        decision = st.selectbox("Decision", ["acknowledge_exploratory", "request_changes", "approve", "reject"], key="step202_review_decision")
        selected = st.multiselect("Reviewed module results", sorted(results), default=sorted(results)[:5], key="step202_review_modules")
        comments = st.text_area("Review comments", value="", key="step202_review_comments")
        if st.button("Create immutable review record", disabled=not bool(results), key="step202_create_review"):
            record = _safe_run("step202_review_record", "Creating review record", lambda: create_review_record(reviewer=reviewer, role=role, decision=decision, module_keys=selected, comments=comments, evidence=results), store=False)
            if record:
                reviews = st.session_state.get("_biointel_neuro_reviews")
                if not isinstance(reviews, list):
                    reviews = []
                reviews.append(record)
                st.session_state["_biointel_neuro_reviews"] = reviews[-200:]
                smart_json(record)

    with tabs[7]:
        st.subheader("Background Compute & Performance Qualification")
        c1, c2, c3 = st.columns(3)
        rows = c1.number_input("Rows", min_value=0, value=10000, step=1000, key="step202_compute_rows")
        columns = c2.number_input("Columns", min_value=0, value=50, step=10, key="step202_compute_columns")
        size_mb = c3.number_input("Input size MB", min_value=0.0, value=25.0, step=5.0, key="step202_compute_size")
        workload = st.selectbox("Workload", ["tabular", "multiomics", "variant_annotation", "neurophysiology", "neuroimaging"], key="step202_compute_workload")
        profile = compute_qualification_profile(rows=int(rows), columns=int(columns), byte_size=int(size_mb * 1024 * 1024), workload=workload)
        smart_json(profile)

    with tabs[8]:
        st.subheader("Crash Diagnostics & Recovery Center")
        error_message = st.text_area("Optional error description", value="", key="step202_diag_error")
        if st.button("Build privacy-redacted diagnostic ZIP", type="primary", key="step202_build_diagnostics"):
            payload = _safe_run("step202_diagnostics", "Building diagnostic support bundle", lambda: crash_diagnostics_bundle(project_root, error_message=error_message), store=False)
            if payload:
                st.download_button("Download diagnostics", payload, "BioIntel-Step202-Neuro-Diagnostics.zip", "application/zip", width="stretch", key="step202_diag_download")

    with tabs[9]:
        st.subheader("Controlled Release & Publication Export")
        results = _result_store()
        reviews = st.session_state.get("_biointel_neuro_reviews") if isinstance(st.session_state.get("_biointel_neuro_reviews"), list) else []
        status = controlled_release_status(results=results, review_records=reviews, test_failures=0, native_windows_qualified=False)
        smart_json(status)
        project_name = st.text_input("Publication project name", value="BioIntel Neuro/CNS Step202", key="step202_publication_name")
        methods = st.text_area("Methods", value="Synthetic demonstration or user-supplied research workflow. Complete before publication.", key="step202_publication_methods")
        limitations = st.text_area("Limitations", value="Research-only outputs; approved resources, external validation and expert review are required.", key="step202_publication_limitations")
        if results:
            payload = publication_export_pack(results, project_name=project_name, methods=methods, limitations=limitations, release_status=status)
            st.download_button("Download publication/release export pack", payload, "BioIntel-Neuro-Step202-Publication-Pack.zip", "application/zip", width="stretch", key="step202_publication_download")
        else:
            st.info("Run modules or the one-click demo before building an export pack.")

def _render_projects() -> None:
    section_title("Persistent Neuro projects", "▣")
    results = _result_store()
    project_name = st.text_input("Project name", value="Neuro-CNS-Project", key="neuro_project_name")
    analyst = st.text_input("Analyst/reviewer", value="", key="neuro_project_analyst")
    notes = st.text_area("Project notes", value="", height=100, key="neuro_project_notes")
    if st.button("Save current project locally", type="primary", disabled=not bool(results), key="save_neuro_project"):
        saved = _safe_run(
            "_project_save",
            "Saving project",
            lambda: save_project(project_name, results, metadata={"analyst": analyst, "notes": notes, "step": "202"}),
            store=False,
        )
        if saved:
            st.success(f"Saved locally: {saved}")
    projects = list_projects()
    if projects.empty:
        st.info("No saved Neuro/CNS projects were found in the local project directory.")
    else:
        smart_dataframe(projects, key="saved_neuro_projects")
        labels = {f"{row.project_name} · {row.saved_at_utc}": row.path for row in projects.itertuples()}
        selected = st.selectbox("Open saved project", list(labels), key="load_neuro_project_select")
        if st.button("Load selected project", key="load_neuro_project"):
            payload = _safe_run("_project_load", "Loading project", lambda: load_project(labels[selected]), store=False)
            if payload:
                st.session_state[RESULT_STATE_KEY] = payload["results"]
                st.success(f"Loaded {len(payload['results'])} module result(s).")
                st.rerun()
    uploaded_project = st.file_uploader("Import portable Neuro project JSON", type=["json"], key="import_neuro_project")
    if uploaded_project is not None and st.button("Load imported project", key="load_imported_neuro_project"):
        payload = _safe_run("_project_import", "Importing project", lambda: load_project_bytes(uploaded_project.getvalue()), store=False)
        if payload:
            st.session_state[RESULT_STATE_KEY] = payload["results"]
            st.success(f"Imported {len(payload['results'])} module result(s).")
            st.rerun()
    if results:
        st.download_button(
            "Download portable project JSON",
            project_json(project_name, results, metadata={"analyst": analyst, "notes": notes, "step": "202"}).encode("utf-8"),
            f"{project_name or 'BioIntel-Neuro-Project'}.json",
            "application/json",
            width="stretch",
            key="download_portable_neuro_project",
        )


def _render_reports() -> None:
    section_title("Unified Neuro report & session history", "▤")
    results = _result_store()
    if not results:
        st.info("Run one or more Neuro/CNS modules to build a unified report.")
        return
    project_name = st.text_input("Report project name", value="BioIntel Neuro/CNS", key="report_project_name")
    analyst = st.text_input("Report analyst/reviewer", value="", key="report_analyst")
    notes = st.text_area("Report notes", value="", height=90, key="report_notes")
    rows = []
    for key, value in results.items():
        module = MODULE_BY_KEY.get(key)
        rows.append(
            {
                "module": module.title if module else key.replace("_", " ").title(),
                "result_type": type(value).__name__,
                "records": len(value) if isinstance(value, (pd.DataFrame, dict, list, tuple)) else None,
            }
        )
    smart_dataframe(rows, key="neuro_report_history")
    smart_dataframe(evaluate_results(results), key="neuro_report_consistency")
    col1, col2, col3, col4 = st.columns(4)
    metadata = {
        "project_name": project_name,
        "analyst": analyst,
        "notes": notes,
        "execution_history": st.session_state.get(EXECUTION_STATE_KEY) if isinstance(st.session_state.get(EXECUTION_STATE_KEY), list) else [],
        "error_records": st.session_state.get(ERROR_STATE_KEY) if isinstance(st.session_state.get(ERROR_STATE_KEY), list) else [],
    }
    col1.download_button(
        "Download JSON",
        bundle_json(results, **metadata).encode("utf-8"),
        "BioIntel-Neuro-CNS-Unified-Report.json",
        "application/json",
        width="stretch",
        key="neuro_json_report",
    )
    col2.download_button(
        "Download HTML",
        bundle_html(results, **metadata).encode("utf-8"),
        "BioIntel-Neuro-CNS-Unified-Report.html",
        "text/html",
        width="stretch",
        key="neuro_html_report",
    )
    col3.download_button(
        "Download Markdown",
        bundle_markdown(results, **metadata).encode("utf-8"),
        "BioIntel-Neuro-CNS-Unified-Report.md",
        "text/markdown",
        width="stretch",
        key="neuro_markdown_report",
    )
    col4.download_button(
        "Download PDF",
        bundle_pdf(results, **metadata),
        "BioIntel-Neuro-CNS-Unified-Report.pdf",
        "application/pdf",
        width="stretch",
        key="neuro_pdf_report",
    )
    evidence_pack = release_evidence_pack(
        results,
        project_name=project_name,
        analyst=analyst,
        notes=notes,
        execution_history=metadata["execution_history"],
        error_records=metadata["error_records"],
        engine_inventory=specialist_engine_inventory(run_version_checks=False),
    )
    st.download_button(
        "Download complete release evidence pack",
        evidence_pack,
        "BioIntel-Neuro-CNS-Release-Evidence-Pack.zip",
        "application/zip",
        width="stretch",
        key="neuro_evidence_pack",
    )
    if st.button("Clear Neuro/CNS session results", key="clear_neuro_results"):
        st.session_state[RESULT_STATE_KEY] = {}
        st.rerun()

def render_neuro_cns_studio(project_root: Path | None = None) -> None:
    hero(
        "Neuro/CNS Intelligence Studio",
        "Forty-one integrated research engines plus advanced validation, privacy, production and release-control systems for CNS discovery, safety, genetics, omics, neurophysiology, imaging, digital neurology and translation.",
        eyebrow="BioIntel AI · Unified local-first neuroscience workspace",
        chips=["41 sub-modules", "17 Step208 deep workflows", "5 workspaces", "8 new Neuro domains", "Evidence-gated release"],
    )
    scientific_boundary_banner(
        source_kind="demo_reference",
        release_eligible=False,
        message="Software functionality is available for research screening and workflow testing. Clinical diagnosis, treatment recommendations, medical-device use and controlled scientific release require approved data, independent validation and responsible review.",
    )

    main_tabs = st.tabs(["Overview", "Run a module", "10 Step207 Neuro additions", "17 Step208 deep workflows", "9 advanced laboratories", "9 max-potential systems", "9 completion systems", "10 production systems", "Guided workflows", "Quality & resources", "Projects", "Unified report", "Architecture & boundaries"])
    with main_tabs[0]:
        _render_overview()
    with main_tabs[1]:
        workspace = st.selectbox("Workspace", WORKSPACES, key="neuro_workspace")
        options = workspace_modules(workspace)
        labels = {f"{module.number}. {module.title}": module.key for module in options}
        selected_label = st.selectbox("Neuro/CNS module", list(labels), key="neuro_module_select")
        selected_key = labels[selected_label]
        _show_module_header(selected_key)
        renderer = RENDERERS[selected_key]
        renderer()
        selected_module = MODULE_BY_KEY[selected_key]
        render_generated_demo_panel(
            selected_key,
            selected_module.title,
            "Neuro/CNS",
            expanded=False,
        )
        render_scientific_resources_panel(
            selected_key,
            selected_module.title,
            "Neuro/CNS",
            prefix=f"neuro_v209_resources_{selected_key}",
            expanded=False,
        )
    with main_tabs[2]:
        render_step207_neuro_portfolio(safe_run=_safe_run)
    with main_tabs[3]:
        render_v208_feature_center("Neuro/CNS")
    with main_tabs[4]:
        _render_advanced_additions()
    with main_tabs[5]:
        _render_max_potential_systems()
    with main_tabs[6]:
        _render_completion_systems()
    with main_tabs[7]:
        _render_production_systems(project_root or Path.cwd())
    with main_tabs[8]:
        _render_guided_workflows()
    with main_tabs[9]:
        _render_quality_and_resources()
    with main_tabs[10]:
        _render_projects()
    with main_tabs[11]:
        _render_reports()
    with main_tabs[12]:
        st.markdown(
            """
### Architecture

The user sees one Neuro/CNS Studio, while each scientific capability remains an independent backend engine. Shared components include molecular descriptors, a versioned CNS target registry, sequence topology utilities, evidence-aware result schemas and a unified report bundle.

### Fail-closed boundaries

- Invalid structures, sequences and missing required columns return explicit errors.
- Unknown targets are reported as unmatched rather than forced into a class.
- Missing side-effect associations are excluded and shown as coverage gaps, never interpreted as zero risk.
- Blood-CSF, aggregation, side-effect, imaging and patient-stratification outputs are labelled exploratory.
- Bundled target/expression/side-effect content is demo/reference material and does not satisfy licensing, external validation or clinical release gates.

### Core file support

SMILES, FASTA/TXT, CSV/TSV, VCF-like tables, NPY, common 2D images, longitudinal assessments, wearable-sensor tables, user-annotated medication tables and square connectivity matrices are supported locally. NIfTI/DICOM and EDF/BDF/FIF are adapter-aware: they activate only when their optional packages are installed, and remain explicitly unqualified until target-machine verification. Guided workflows, resource bindings, specialist-engine inventory, privacy scanning, leakage auditing, drift monitoring, PDF reporting, release evidence packs, consistency checks and persistent project files preserve scientific context across runs.
"""
        )
