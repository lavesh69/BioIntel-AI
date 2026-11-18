from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

from biointel import __version__

from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.theme import section_title
from biointel.ui.runtime_guard import write_runtime_error
from biointel.ui.workflow import read_uploaded_table, render_upload_preflight

from .artifacts_v209 import build_result_bundle, json_safe
from .bioinformatics import (
    BIOINFORMATICS_V208_FEATURES,
    build_reproducibility_manifest,
    external_tool_readiness,
    genomic_cohort_qc,
    microbiome_contamination_qc,
    multiomics_batch_qc,
    single_cell_qc,
    spatial_omics_qc,
)
from .demos import demo_payload
from .discovery import (
    DISCOVERY_V208_FEATURES,
    admet_calibration_and_domain,
    antibody_developability,
    assay_design_and_power,
    docking_validation,
    lead_optimization_ranking,
    neoantigen_prioritization,
    protein_design_qc,
    standardize_compounds,
)
from .ingestion import format_support_table, optional_adapter_status
from .ingestion_v209 import read_zip_tables_bytes, structured_payload_from_zip
from .lab import (
    LAB_V208_FEATURES,
    autonomous_experiment_plan,
    bioprocess_time_series,
    gene_therapy_vector_qc,
    high_content_plate_qc,
    metagenomics_control_qc,
    microscopy_image_qc,
    organoid_3d_analysis,
    primer_crispr_qc,
    synthetic_construct_qc,
)
from .neuro import (
    NEURO_V208_FEATURES,
    autonomic_hrv_analysis,
    connectome_community_analysis,
    eeg_meg_research_pipeline,
    epilepsy_diary_analysis,
    expression_atlas_analysis,
    movement_disorder_quantification,
    multimodal_neurodegeneration_progression,
    neuro_oncology_board,
    neuro_omics_biomarker_validation,
    neurocritical_care_trends,
    neuroimaging_volume_workflow,
    neuropathology_image_analysis,
    normalize_neuro_variants,
    normalize_trial_portfolio,
    precision_neurology_consensus,
    simulate_multicompartment_neuro_pk,
    speech_language_biomarker_analysis,
    target_evidence_graph,
)
from .execution import execute_feature
from .visuals import figures_for_result

CATEGORY_FEATURES = {
    "Neuro/CNS": NEURO_V208_FEATURES,
    "Bioinformatics": BIOINFORMATICS_V208_FEATURES,
    "Discovery": DISCOVERY_V208_FEATURES,
    "Lab Analytics": LAB_V208_FEATURES,
}

_IMAGE_FEATURES = {"advanced_neuroimaging", "neuropathology", "microscopy_qc"}
_NO_UPLOAD_FEATURES = {"format_readiness", "tool_readiness", "reproducibility", "advanced_neuro_pk", "assay_planning", "experiment_planner", "synthetic_biology", "gene_therapy"}


def _read_zip_tables(uploaded: Any) -> dict[str, Any]:
    uploaded.seek(0)
    return read_zip_tables_bytes(uploaded.read())


def _uploaded_payload(feature_key: str) -> tuple[Any | None, dict[str, Any] | None]:
    if feature_key in _NO_UPLOAD_FEATURES:
        return None, None
    structured = {"microbiome_controls", "admet_calibration", "protein_design", "primer_crispr"}
    if feature_key in _IMAGE_FEATURES:
        uploaded = st.file_uploader(
            "Local image/NumPy input",
            type=["npy", "png", "jpg", "jpeg", "tif", "tiff"],
            key=f"v209_upload_{feature_key}",
        )
        allowed = ("npy", "png", "jpg", "jpeg", "tif", "tiff")
    else:
        allowed_types = ["csv", "tsv", "txt", "zip"] if feature_key in structured else ["csv", "tsv", "txt"]
        uploaded = st.file_uploader(
            "Local input file" if feature_key not in structured else "Local table or multi-file ZIP",
            type=allowed_types,
            key=f"v209_upload_{feature_key}",
            help="Files above 100 MB are staged locally for background-safe inspection; up to 1 GB is accepted.",
        )
        allowed = tuple(allowed_types)
    if uploaded is None:
        return None, None
    profile = render_upload_preflight(
        uploaded,
        key=f"v209_preflight_{feature_key}",
        allowed_extensions=allowed,
        soft_limit_mb=100,
        hard_limit_mb=1024,
        module_key=f"v209_{feature_key}",
    )
    if profile is None or profile.requires_staging:
        return None, profile.to_dict() if profile is not None else None
    try:
        uploaded.seek(0)
        lower_name = uploaded.name.lower()
        if lower_name.endswith(".zip"):
            payload = structured_payload_from_zip(feature_key, _read_zip_tables(uploaded))
        elif feature_key in _IMAGE_FEATURES:
            if lower_name.endswith(".npy"):
                payload = np.load(uploaded, allow_pickle=False)
            else:
                with Image.open(uploaded) as image:
                    width, height = image.size
                    frames = int(getattr(image, "n_frames", 1) or 1)
                    if width * height * frames > 100_000_000:
                        raise ValueError("Image dimensions exceed the 100-million-pixel interactive safety boundary.")
                    image.verify()
                uploaded.seek(0)
                with Image.open(uploaded) as image:
                    payload = np.asarray(image.copy())
        else:
            payload = read_uploaded_table(uploaded)
    except Exception as exc:
        error_id, _ = write_runtime_error(f"module_features_v209.upload.{feature_key}", exc)
        st.error(f"Input could not be opened safely · {error_id}")
        st.caption("No online result was claimed. Check the file structure, delimiter and required columns, then retry.")
        return None, profile.to_dict()
    metadata = profile.to_dict()
    metadata["source"] = "local_upload"
    return payload, metadata

def _run_neuro(feature_key: str, payload: Any) -> dict[str, Any]:
    if feature_key == "advanced_eeg_meg":
        if isinstance(payload, dict):
            return eeg_meg_research_pipeline(payload["data"], sampling_rate=payload["sampling_rate"], time_col=payload.get("time_col"))
        return eeg_meg_research_pipeline(payload, sampling_rate=float(st.session_state.get("v208_eeg_fs", 128.0)), time_col="time" if "time" in payload.columns else None)
    if feature_key == "advanced_neuroimaging":
        if isinstance(payload, dict):
            return neuroimaging_volume_workflow(payload["volume"], voxel_spacing_mm=payload.get("voxel_spacing_mm"), atlas=payload.get("atlas"))
        return neuroimaging_volume_workflow(np.asarray(payload))
    if feature_key == "advanced_neurogenetics":
        return normalize_neuro_variants(payload, hpo_terms=[term.strip() for term in st.session_state.get("v208_hpo_terms", "seizure, developmental delay").split(",") if term.strip()])
    if feature_key == "advanced_expression_atlas":
        return expression_atlas_analysis(payload)
    if feature_key == "advanced_neuro_omics":
        return neuro_omics_biomarker_validation(payload, group_col="group")
    if feature_key == "advanced_precision_neurology":
        return precision_neurology_consensus(payload)
    if feature_key == "advanced_neuro_pk":
        values = payload or {}
        return simulate_multicompartment_neuro_pk(**values)
    if feature_key == "advanced_target_evidence":
        return target_evidence_graph(payload)
    if feature_key == "advanced_trial_intelligence":
        return normalize_trial_portfolio(payload)
    if feature_key == "neuro_oncology":
        return neuro_oncology_board(payload)
    if feature_key == "epilepsy_diary":
        return epilepsy_diary_analysis(payload)
    if feature_key == "movement_disorders":
        if isinstance(payload, dict):
            return movement_disorder_quantification(payload["data"], sampling_rate=payload["sampling_rate"])
        return movement_disorder_quantification(payload, sampling_rate=float(st.session_state.get("v208_move_fs", 50.0)))
    if feature_key == "autonomic_hrv":
        return autonomic_hrv_analysis(payload)
    if feature_key == "speech_language":
        return speech_language_biomarker_analysis(payload)
    if feature_key == "neurodegeneration_progression":
        return multimodal_neurodegeneration_progression(payload)
    if feature_key == "neuropathology":
        return neuropathology_image_analysis(np.asarray(payload))
    if feature_key == "neurocritical_care":
        return neurocritical_care_trends(payload)
    raise KeyError(feature_key)


def _run_bioinformatics(feature_key: str, payload: Any) -> dict[str, Any]:
    if feature_key == "format_readiness":
        return {"format_support": format_support_table(), "optional_adapters": optional_adapter_status(), "summary": {"formats": len(format_support_table()), "available_optional_adapters": int(optional_adapter_status()["available"].sum())}, "scientific_boundary": "Capability status only; target-machine validation is required."}
    if feature_key == "genomic_cohort_qc":
        return genomic_cohort_qc(payload)
    if feature_key == "single_cell_qc":
        if isinstance(payload, dict):
            return single_cell_qc(payload["matrix"], gene_names=payload.get("gene_names"))
        return single_cell_qc(payload)
    if feature_key == "spatial_qc":
        return spatial_omics_qc(payload)
    if feature_key == "multiomics_qc":
        return multiomics_batch_qc(payload)
    if feature_key == "microbiome_controls":
        if isinstance(payload, dict):
            return microbiome_contamination_qc(payload["abundance"], payload["metadata"])
        raise ValueError("Uploaded microbiome input needs a separate abundance matrix and metadata table; use the labelled demo or the native microbiome module.")
    if feature_key == "tool_readiness":
        table = external_tool_readiness()
        return {"tools": table, "summary": {"tools": len(table), "available": int(table["available"].sum())}, "scientific_boundary": "Tool discovery does not qualify scientific correctness."}
    if feature_key == "reproducibility":
        return build_reproducibility_manifest(parameters={"feature_center": "Bioinformatics V208"})
    raise KeyError(feature_key)


def _run_discovery(feature_key: str, payload: Any) -> dict[str, Any]:
    if feature_key == "compound_standardization":
        return standardize_compounds(payload)
    if feature_key == "docking_validation":
        return docking_validation(payload)
    if feature_key == "admet_calibration":
        if not isinstance(payload, dict):
            raise ValueError("ADMET calibration needs separate reference and query datasets; use the labelled demo or specialist module.")
        return admet_calibration_and_domain(payload["reference"], payload["query"])
    if feature_key == "lead_optimization":
        return lead_optimization_ranking(payload, maximize=["potency", "selectivity"], minimize=["clearance", "toxicity"])
    if feature_key == "protein_design":
        if not isinstance(payload, dict):
            raise ValueError("Protein design QC needs a reference sequence and candidates; use the labelled demo or specialist module.")
        return protein_design_qc(payload["reference"], payload["candidates"], conserved_positions=payload.get("conserved_positions", ()))
    if feature_key == "antibody_developability":
        return antibody_developability(payload)
    if feature_key == "neoantigen":
        return neoantigen_prioritization(payload)
    if feature_key == "assay_planning":
        values = payload or {}
        return assay_design_and_power(**values)
    raise KeyError(feature_key)


def _run_lab(feature_key: str, payload: Any) -> dict[str, Any]:
    if feature_key == "microscopy_qc":
        return microscopy_image_qc(np.asarray(payload))
    if feature_key == "plate_qc":
        return high_content_plate_qc(payload)
    if feature_key == "bioprocess":
        return bioprocess_time_series(payload)
    if feature_key == "metagenomics_controls":
        return metagenomics_control_qc(payload)
    if feature_key == "synthetic_biology":
        values = payload or {}
        return synthetic_construct_qc(**values)
    if feature_key == "primer_crispr":
        if not isinstance(payload, dict):
            raise ValueError("Primer/CRISPR QC needs target and optional genome sequence; use the labelled demo or specialist module.")
        return primer_crispr_qc(**payload)
    if feature_key == "organoid":
        return organoid_3d_analysis(payload)
    if feature_key == "gene_therapy":
        values = payload or {}
        return gene_therapy_vector_qc(**values)
    if feature_key == "experiment_planner":
        values = payload or {}
        return autonomous_experiment_plan(**values)
    raise KeyError(feature_key)


def _run(category: str, feature_key: str, payload: Any) -> dict[str, Any]:
    if category == "Neuro/CNS":
        return _run_neuro(feature_key, payload)
    if category == "Bioinformatics":
        return _run_bioinformatics(feature_key, payload)
    if category == "Discovery":
        return _run_discovery(feature_key, payload)
    if category == "Lab Analytics":
        return _run_lab(feature_key, payload)
    raise KeyError(category)


def _render_result(feature_key: str, result: dict[str, Any]) -> None:
    summary = result.get("summary") or result.get("metrics")
    if isinstance(summary, dict):
        cards = []
        for key, value in list(summary.items())[:4]:
            if isinstance(value, float):
                display = f"{value:.4g}"
            elif isinstance(value, (list, tuple, dict)):
                display = len(value)
            else:
                display = value
            cards.append((key.replace("_", " ").title(), display, None))
        if cards:
            metric_cards(cards)
    provenance = result.get("_run_provenance")
    if isinstance(provenance, dict):
        st.caption(
            f"Input: {provenance.get('source_label', provenance.get('source_kind', 'unknown'))} · "
            f"Runtime: {float(provenance.get('duration_seconds', 0.0)):.2f}s · Release: {provenance.get('release', __version__)}"
        )
    figures = figures_for_result(feature_key, result)
    tables = [(key, value) for key, value in result.items() if isinstance(value, pd.DataFrame)]
    tab_names = []
    if figures:
        tab_names.append("Scientific visuals")
    if tables:
        tab_names.append("Result tables & exports")
    tab_names.append("Method, bundle & boundary")
    tabs = st.tabs(tab_names)
    index = 0
    if figures:
        with tabs[index]:
            for name, figure in figures.items():
                st.plotly_chart(figure, width="stretch", key=f"v209_fig_{feature_key}_{name}")
        index += 1
    if tables:
        with tabs[index]:
            for name, table in tables:
                st.markdown(f"**{name.replace('_', ' ').title()}**")
                smart_dataframe(table, key=f"v209_table_{feature_key}_{name}", height=380)
                st.download_button(
                    f"Download {name.replace('_', ' ')} CSV",
                    table.to_csv(index=False).encode("utf-8"),
                    f"BioIntel-{feature_key}-{name}.csv",
                    "text/csv",
                    key=f"v209_download_{feature_key}_{name}",
                )
        index += 1
    with tabs[index]:
        metadata = {key: json_safe(value) for key, value in result.items() if not isinstance(value, pd.DataFrame)}
        smart_json(metadata, title="Method metadata", download_name=f"BioIntel-{feature_key}-metadata.json", key=f"v209_meta_{feature_key}")
        bundle = build_result_bundle(feature_key, result)
        st.download_button(
            "Download complete result & provenance bundle",
            bundle,
            f"BioIntel-{feature_key}-Result-Bundle.zip",
            "application/zip",
            key=f"v209_bundle_{feature_key}",
            width="stretch",
        )
        scientific_boundary_banner(
            source_kind="research_software",
            release_eligible=False,
            message=str(result.get("scientific_boundary", "Research-only output.")),
        )


def _local_parameter_payload(feature_key: str) -> Any:
    defaults = demo_payload(feature_key)
    if feature_key == "advanced_neuro_pk":
        values = dict(defaults or {})
        columns = st.columns(4)
        return {
            "dose_mg": float(columns[0].number_input("Dose (mg)", min_value=0.001, value=float(values.get("dose_mg", 50.0)), key="v209_pk_dose")),
            "dosing_interval_h": float(columns[1].number_input("Interval (h)", min_value=0.1, value=float(values.get("dosing_interval_h", 12.0)), key="v209_pk_interval")),
            "doses": int(columns[2].number_input("Doses", min_value=1, max_value=365, value=int(values.get("doses", 8)), key="v209_pk_doses")),
            "target_kd_nm": float(columns[3].number_input("Target Kd (nM)", min_value=0.001, value=float(values.get("target_kd_nm", 25.0)), key="v209_pk_kd")),
        }
    if feature_key == "assay_planning":
        values = dict(defaults or {})
        groups = st.text_input("Groups (comma separated)", value=", ".join(values.get("groups", [])), key="v209_assay_groups")
        columns = st.columns(2)
        return {
            "groups": [item.strip() for item in groups.split(",") if item.strip()],
            "effect_size": float(columns[0].number_input("Expected standardized effect size", min_value=0.01, value=float(values.get("effect_size", 0.8)), key="v209_assay_effect")),
            "power": float(columns[1].number_input("Target power", min_value=0.5, max_value=0.999, value=float(values.get("power", 0.85)), key="v209_assay_power")),
        }
    if feature_key == "experiment_planner":
        values = dict(defaults or {})
        groups = st.text_input("Experimental groups", value=", ".join(values.get("groups", [])), key="v209_plan_groups")
        blocks = st.text_input("Blocks", value=", ".join(values.get("blocks", [])), key="v209_plan_blocks")
        replicates = st.number_input("Replicates per group", min_value=2, max_value=1000, value=int(values.get("replicates", 6)), key="v209_plan_replicates")
        return {"groups": [item.strip() for item in groups.split(",") if item.strip()], "replicates": int(replicates), "blocks": [item.strip() for item in blocks.split(",") if item.strip()]}
    if feature_key == "synthetic_biology":
        values = dict(defaults or {})
        name = st.text_input("Construct name", value=str(values.get("construct_name", "DemoCircuit")), key="v209_construct_name")
        sequence = st.text_area("DNA sequence", value=str(values.get("sequence", "")), height=140, key="v209_construct_sequence")
        return {"sequence": sequence, "construct_name": name}
    if feature_key == "gene_therapy":
        values = dict(defaults or {})
        columns = st.columns(3)
        vector_type = columns[0].selectbox("Vector type", ["AAV", "Lentiviral", "Adenoviral", "Other"], index=0, key="v209_vector_type")
        promoter = columns[1].text_input("Promoter", value=str(values.get("promoter", "CAG")), key="v209_vector_promoter")
        tissue = columns[2].text_input("Target tissue", value=str(values.get("target_tissue", "CNS")), key="v209_vector_tissue")
        sequence = st.text_area("Vector cargo sequence", value=str(values.get("sequence", "")), height=140, key="v209_vector_sequence")
        return {"sequence": sequence, "vector_type": vector_type, "promoter": promoter, "target_tissue": tissue}
    return defaults


def _feature_options(feature_key: str) -> dict[str, Any]:
    if feature_key == "advanced_eeg_meg":
        return {"sampling_rate": float(st.session_state.get("v209_eeg_fs", 128.0))}
    if feature_key == "movement_disorders":
        return {"sampling_rate": float(st.session_state.get("v209_move_fs", 50.0))}
    if feature_key == "advanced_neurogenetics":
        terms = [term.strip() for term in str(st.session_state.get("v209_hpo_terms", "seizure, developmental delay")).split(",") if term.strip()]
        return {"hpo_terms": terms}
    return {}


def render_single_feature(category: str, feature_key: str, *, show_title: bool = True) -> None:
    if category not in CATEGORY_FEATURES:
        raise KeyError(category)
    feature_map = {key: (title, description) for key, title, description in CATEGORY_FEATURES[category]}
    if feature_key not in feature_map:
        raise KeyError(feature_key)
    title, description = feature_map[feature_key]
    if show_title:
        st.subheader(title)
    st.info(description)
    if feature_key == "advanced_eeg_meg":
        st.session_state["v209_eeg_fs"] = st.number_input(
            "Sampling rate for uploaded table (Hz)", min_value=2.0, value=128.0, key=f"v209_eeg_fs_{feature_key}"
        )
    elif feature_key == "movement_disorders":
        st.session_state["v209_move_fs"] = st.number_input(
            "Sampling rate for uploaded table (Hz)", min_value=2.0, value=50.0, key=f"v209_move_fs_{feature_key}"
        )
    elif feature_key == "advanced_neurogenetics":
        st.session_state["v209_hpo_terms"] = st.text_input(
            "Phenotype/HPO terms", value="seizure, developmental delay", key=f"v209_hpo_terms_{feature_key}"
        )

    if feature_key in _NO_UPLOAD_FEATURES:
        source_mode = "Built-in local parameters"
        payload = _local_parameter_payload(feature_key)
        input_profile: dict[str, Any] | None = {"source": "visible_local_parameters"}
        st.caption("This workflow uses visible local parameters or local capability checks; it does not silently contact an online service.")
    else:
        source_mode = st.radio(
            "Input source",
            ["Labelled synthetic demo", "Upload local data"],
            horizontal=True,
            key=f"v209_input_source_{category}_{feature_key}",
        )
        if source_mode == "Labelled synthetic demo":
            payload = demo_payload(feature_key)
            input_profile = {"source": "deterministic_synthetic_demo", "labelled": True}
            st.caption("Using clearly labelled deterministic synthetic demonstration data. No real patient, assay or online result is implied.")
        else:
            payload, input_profile = _uploaded_payload(feature_key)
            if payload is None:
                st.info("Choose a valid local file to enable this run. BioIntel will not silently substitute demo data in upload mode.")

    if isinstance(payload, pd.DataFrame):
        smart_dataframe(payload.head(250), key=f"v209_input_{category}_{feature_key}", height=300)
    elif isinstance(payload, np.ndarray):
        st.caption(f"Array shape: {payload.shape} · dtype: {payload.dtype}")
    elif isinstance(payload, dict):
        preview = next((value for value in payload.values() if isinstance(value, pd.DataFrame)), None)
        if preview is not None:
            smart_dataframe(preview.head(250), key=f"v209_input_{category}_{feature_key}", height=300)
        else:
            st.caption("Structured local workflow parameters are ready.")

    state_key = f"v209_result_{category}_{feature_key}"
    run_disabled = payload is None and feature_key not in {"format_readiness", "tool_readiness", "reproducibility"}
    controls = st.columns([2, 1])
    run_clicked = controls[0].button(
        "Run local scientific workflow",
        type="primary",
        key=f"v209_run_{category}_{feature_key}",
        width="stretch",
        disabled=run_disabled,
    )
    if controls[1].button("Clear result", key=f"v209_clear_{category}_{feature_key}", width="stretch"):
        st.session_state.pop(state_key, None)
        st.rerun()
    if run_clicked:
        started = time.perf_counter()
        started_at = datetime.now(UTC)
        try:
            with st.status("Running local workflow…", expanded=False) as status:
                result = execute_feature(category, feature_key, payload, options=_feature_options(feature_key))
                if not isinstance(result, dict):
                    raise TypeError("Scientific workflow returned an invalid result structure.")
                duration = time.perf_counter() - started
                result["_run_provenance"] = {
                    "schema": "biointel.feature-run.v209.v1",
                    "category": category,
                    "feature_key": feature_key,
                    "release": __version__,
                    "source_kind": "local_upload" if source_mode == "Upload local data" else "deterministic_synthetic_demo" if source_mode == "Labelled synthetic demo" else "local_parameters_or_capability_check",
                    "source_label": source_mode,
                    "started_at_utc": started_at.isoformat(),
                    "finished_at_utc": datetime.now(UTC).isoformat(),
                    "duration_seconds": round(duration, 6),
                    "input_profile": json_safe(input_profile),
                    "online_result_claimed": False,
                }
                status.update(label="Workflow completed", state="complete")
            st.session_state[state_key] = result
        except Exception as exc:
            error_id, _ = write_runtime_error(f"module_features_v209.execute.{category}.{feature_key}", exc)
            st.error(f"The workflow stopped safely · {error_id}")
            st.caption("No online result was claimed and no project data was deleted. Check required columns/parameters or run the labelled demo.")
    result = st.session_state.get(state_key)
    if isinstance(result, dict):
        _render_result(feature_key, result)

def render_feature_center(category: str) -> None:
    if category not in CATEGORY_FEATURES:
        raise KeyError(category)
    features = CATEGORY_FEATURES[category]
    section_title(f"{category} maximum-potential feature center", "◆")
    st.caption(
        "Local deterministic workflows, explicit optional adapters, memory-safe upload preflight, calculated visuals, exports and fail-closed scientific boundaries."
    )
    labels = {title: key for key, title, _ in features}
    selected_title = st.selectbox("Feature workflow", list(labels), key=f"v208_feature_select_{category}")
    render_single_feature(category, labels[selected_title], show_title=False)


def render_neuro_v208_portfolio() -> None:
    render_feature_center("Neuro/CNS")
