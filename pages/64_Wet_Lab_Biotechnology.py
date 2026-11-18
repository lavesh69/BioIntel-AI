from __future__ import annotations

import secrets
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel import __version__
from biointel.biotech.assays import bioprocess_yields, growth_metrics, qpcr_delta_delta_ct
from biointel.biotech.assays_advanced import (
    bioprocess_advanced_metrics,
    bioprocess_batch_comparison,
    bioprocess_pat_monitor,
    bioprocess_sensor_metrics,
    bootstrap_elisa_unknown_intervals,
    compare_enzyme_models,
    compare_inhibition_models,
    convert_absorbance_slope_to_rate,
    elisa_assay_qc,
    elisa_hook_effect_screen,
    elisa_parallelism_recovery_qc,
    elisa_validation_summary,
    extract_initial_rates,
    fit_elisa_calibration,
    fit_enzyme_model,
    global_inhibition_fit,
    inverse_calibration_with_flags,
    melt_curve_qc,
    qpcr_amplification_curve_qc,
    qpcr_control_qc,
    qpcr_group_statistics,
    qpcr_multi_reference,
    qpcr_reference_gene_stability,
    qpcr_standard_curve,
)
from biointel.biotech.experimental_design import (
    cluster_adjusted_sample_size,
    correlation_sample_size,
    equivalence_sample_size,
    noninferiority_sample_size,
    one_way_anova_sample_size,
    paired_sample_size,
    plate_randomization,
    randomized_assignment,
    repeated_measures_sample_size,
    sensitivity_curve,
    two_group_sample_size,
    two_proportion_sample_size,
)
from biointel.biotech.lab_import import list_excel_sheets, read_lab_table
from biointel.biotech.flow_cytometry import (
    apply_compensation,
    arcsinh_transform,
    audit_gate_hierarchy,
    derive_compensation_matrix,
    fmo_threshold,
    flow_qc,
    flow_release_gate,
    population_summary,
    rectangular_gate,
    singlet_gate,
    validate_control_manifest,
)
from biointel.native.formats import parse_native_source
from biointel.biotech.lab_registry import record_run
from biointel.biotech.lab_reporting import build_lab_run_bundle
from biointel.biotech.lab_schema import (
    apply_column_mapping,
    column_mapping_ready,
    infer_column_mapping,
    plate_coordinates,
    plate_map_audit,
    plate_spatial_qc,
)
from biointel.ui.components import (
    metric_cards,
    result_summary,
    scientific_boundary_banner,
    smart_dataframe,
    smart_json,
)
from biointel.ui.performance import read_csv_cached
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title
from biointel.ui.workflow import (
    analysis_run,
    read_uploaded_table,
    render_methodology,
    render_upload_preflight,
)

DEMO = ROOT / "data" / "bioinformatics_demo"
st.set_page_config(page_title="Wet-Lab Biotechnology · BioIntel AI", page_icon="🧪", layout="wide")
apply_theme()

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('flow_cytometry', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'flow_cytometry', expanded=False)
# STEP178_19_MODULE_CLINICAL_OPERATIONAL_PRIVACY_ML_ASSURANCE
from biointel.target_modules_v178.ui import render_step178_module_upgrade
render_step178_module_upgrade('flow_cytometry', expanded=False)


# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("wetlab", key_prefix="step116_64_Wet_Lab_Biotechnology_wetlab_1", expanded=False)
_render_step116_module_experience("flow_cytometry", key_prefix="step116_64_Wet_Lab_Biotechnology_flow_cytometry_2", expanded=False)
hero(
    "Wet-Lab Biotechnology",
    "Schema-aware qPCR, ELISA, enzyme-kinetics, bioprocess and experimental-design analytics with plate QC, calibration diagnostics, uncertainty and auditable exports.",
    eyebrow="BioIntel AI · Laboratory Analytics",
    chips=["Schema mapping", "Plate QC", "4PL/5PL", "Advanced kinetics", "Design + randomization"],
)
scientific_boundary_banner(
    source_kind="demo_reference",
    release_eligible=False,
    message="Bundled assay data are simulated. Confirm units, controls, calibration, instrument QC, SOP acceptance criteria and raw-data traceability before reporting results.",
)
render_methodology(
    method="Transparent assay calculations with explicit schema mapping, plate-layout checks, replicate diagnostics and statistical uncertainty.",
    assumptions=["Mapped columns, units, plate roles, calibrators and dilution factors accurately represent the experiment."],
    limitations=["Automated analysis cannot replace assay-specific validation, instrument software review or regulated laboratory controls."],
    validation=["Retain immutable raw exports and plate maps.", "Review controls, residuals, recovery, replicate CV and acceptance thresholds before release."],
)

template_pack = ROOT / "data" / "lab_templates" / "LAB_ANALYTICS_TEMPLATE_PACK.zip"
if template_pack.exists():
    st.download_button(
        "Download instrument/schema template pack",
        template_pack.read_bytes(),
        "LAB_ANALYTICS_TEMPLATE_PACK.zip",
        "application/zip",
        width="stretch",
        key="wet_lab_template_pack",
    )


registry_row = st.columns([1, 1, 2])
save_to_registry = registry_row[0].toggle("Save successful runs", value=False, help="Persist input/output hashes and parameters in the local Lab Run Registry.")
operator_name = registry_row[1].text_input("Operator", value="local_user", disabled=not save_to_registry)
registry_row[2].caption("Every completed analysis can export a checksum-bound reproducibility ZIP. Registry writes are opt-in and local.")


def recommendations_panel(items: list[str], *, title: str = "Recommended next actions") -> None:
    clean = [str(item) for item in items if str(item).strip()]
    if not clean:
        return
    with st.expander(title, expanded=True):
        for item in clean:
            st.markdown(f"- {item}")


def persist_and_bundle(
    *,
    workflow: str,
    input_frame: pd.DataFrame,
    outputs: dict[str, object],
    parameters: dict[str, object],
    recommendations: list[str],
    source_filename: str,
    key: str,
) -> None:
    bundle = build_lab_run_bundle(
        workflow=workflow,
        input_frame=input_frame,
        outputs=outputs,
        parameters=parameters,
        recommendations=recommendations,
        source_filename=source_filename,
    )
    st.download_button(
        "Download complete reproducibility bundle",
        bundle,
        f"{key}_lab_run_bundle.zip",
        "application/zip",
        width="stretch",
        key=f"{key}_bundle_download",
    )
    if save_to_registry:
        run_id = record_run(
            workflow=workflow,
            input_frame=input_frame,
            parameters=parameters,
            outputs=outputs,
            recommendations=recommendations,
            source_filename=source_filename,
            operator=operator_name or "local_user",
            software_version=__version__,
        )
        st.success(f"Saved to Lab Run Registry · {run_id}")


def load_lab_upload(uploaded_file, *, key: str) -> pd.DataFrame:
    sheets = list_excel_sheets(uploaded_file)
    selected_sheet: str | int = 0
    if sheets:
        selected_sheet = st.selectbox("Workbook sheet", sheets, key=f"{key}_sheet")
    return read_lab_table(uploaded_file, sheet_name=selected_sheet)


def mapping_controls(frame: pd.DataFrame, assay: str, required: list[str], optional: list[str], key: str) -> dict[str, str]:
    inferred = infer_column_mapping(frame, assay)
    columns = ["— Not mapped —", *map(str, frame.columns)]
    mapping: dict[str, str] = {}
    with st.expander("Column mapping and schema audit", expanded=True):
        grid = st.columns(3)
        for index, canonical in enumerate([*required, *optional]):
            inferred_column = inferred.get(canonical)
            default_index = columns.index(inferred_column) if inferred_column in columns else 0
            selected = grid[index % 3].selectbox(
                f"{canonical.replace('_', ' ').title()}{' *' if canonical in required else ''}",
                columns,
                index=default_index,
                key=f"{key}_{canonical}",
            )
            if selected != columns[0]:
                mapping[canonical] = selected
        missing = [column for column in required if column not in mapping]
        duplicates = sorted({value for value in mapping.values() if list(mapping.values()).count(value) > 1})
        if missing:
            st.warning("Map required columns: " + ", ".join(missing))
        elif duplicates:
            st.error("One source column cannot represent multiple biological fields: " + ", ".join(duplicates))
        else:
            st.success("Required schema mapping is complete and one-to-one.")
        unused = [str(column) for column in frame.columns if str(column) not in set(mapping.values())]
        if unused:
            st.caption(f"{len(unused)} unmapped instrument/metadata columns will be preserved as meta__ fields in exports.")
    return mapping


qpcr_tab, elisa_tab, enzyme_tab, bioprocess_tab, flow_tab, design_tab = st.tabs(
    ["qPCR", "ELISA", "Enzyme kinetics", "Bioprocess", "Flow cytometry", "Experimental design"]
)

with qpcr_tab:
    upload = st.file_uploader("qPCR CSV/TSV/Excel", type=["csv", "tsv", "xlsx", "xlsm"], key="wet_qpcr")
    render_upload_preflight(upload, key="wet_qpcr", allowed_extensions=["csv", "tsv", "xlsx", "xlsm"], soft_limit_mb=10, hard_limit_mb=50)
    raw = load_lab_upload(upload, key="qpcr") if upload else read_csv_cached(DEMO / "demo_qpcr.csv")
    smart_dataframe(raw.head(500), height=250)
    mapping = mapping_controls(raw, "qpcr", ["sample", "target_ct", "reference_ct"], ["group", "replicate", "well"], "qpcr_map")
    if column_mapping_ready(mapping, required=("sample", "target_ct", "reference_ct")):
        frame = apply_column_mapping(raw, mapping, required=["sample", "target_ct", "reference_ct"], preserve_unmapped=True)
        calibrator = st.selectbox("Calibrator sample", sorted(frame["sample"].astype(str).unique()), key="qpcr_calibrator")
        row = st.columns(4)
        target_efficiency = row[0].number_input("Target amplification factor", 1.01, 2.20, 2.00, 0.01)
        reference_efficiency = row[1].number_input("Reference amplification factor", 1.01, 2.20, 2.00, 0.01)
        maximum_ct = row[2].number_input("Maximum accepted Ct", 20.0, 50.0, 40.0, 0.5)
        replicate_sd_limit = row[3].number_input("Maximum technical-replicate SD", 0.05, 5.0, 0.50, 0.05)
        with st.expander("Optional standard-curve efficiency", expanded=False):
            standard_upload = st.file_uploader("Standards CSV/Excel with concentration and Ct", type=["csv", "tsv", "xlsx", "xlsm"], key="qpcr_standard_curve")
            if standard_upload:
                standards = load_lab_upload(standard_upload, key="qpcr_standards")
                concentration_column = st.selectbox("Concentration column", standards.columns, key="qpcr_std_conc")
                ct_column = st.selectbox("Ct column", standards.columns, key="qpcr_std_ct")
                try:
                    efficiency = qpcr_standard_curve(standards[concentration_column], standards[ct_column])
                    result_summary(efficiency, title="Standard-curve efficiency")
                    if 1.0 < float(efficiency["amplification_factor"]) <= 2.2:
                        target_efficiency = float(efficiency["amplification_factor"])
                except Exception as exc:
                    st.error(f"Standard-curve analysis failed: {exc}")
        with st.expander("Raw amplification-curve QC", expanded=False):
            raw_curve_upload = st.file_uploader(
                "Raw amplification curves CSV/TSV/Excel",
                type=["csv", "tsv", "xlsx", "xlsm"],
                key="qpcr_raw_curves",
                help="Required fields: reaction, cycle and fluorescence. This screening QC does not replace validated instrument Cq algorithms.",
            )
            if raw_curve_upload:
                curve_frame = load_lab_upload(raw_curve_upload, key="qpcr_raw_curves")
                curve_columns = list(curve_frame.columns)
                curve_grid = st.columns(5)
                curve_reaction = curve_grid[0].selectbox("Reaction column", curve_columns, key="qpcr_curve_reaction")
                curve_cycle = curve_grid[1].selectbox("Cycle column", curve_columns, key="qpcr_curve_cycle")
                curve_signal = curve_grid[2].selectbox("Fluorescence column", curve_columns, key="qpcr_curve_signal")
                curve_baseline = curve_grid[3].number_input("Baseline cycles", 3, 20, 10, 1, key="qpcr_curve_baseline")
                curve_threshold = curve_grid[4].number_input("Threshold fraction", 0.05, 0.80, 0.20, 0.05, key="qpcr_curve_threshold")
                if st.button("Inspect amplification curves", key="qpcr_curve_run", disabled=len({curve_reaction, curve_cycle, curve_signal}) < 3):
                    try:
                        curve_detail, curve_summary = qpcr_amplification_curve_qc(
                            curve_frame,
                            reaction_column=curve_reaction,
                            cycle_column=curve_cycle,
                            fluorescence_column=curve_signal,
                            baseline_cycles=int(curve_baseline),
                            threshold_fraction=float(curve_threshold),
                        )
                        smart_dataframe(curve_summary, height=260)
                        if not curve_detail.empty:
                            plot_frame = curve_detail.rename(columns={curve_reaction: "reaction", curve_cycle: "cycle"})
                            st.plotly_chart(
                                px.line(plot_frame, x="cycle", y="baseline_corrected_fluorescence", color="reaction", title="Baseline-corrected amplification curves"),
                                width="stretch",
                            )
                        recommendations_panel([
                            "Review curves without a threshold crossing, with low signal-to-noise or irregular amplification before accepting exported Cq values.",
                            "Retain instrument method, baseline/threshold algorithm, chemistry and raw fluorescence export in the MIQE record.",
                        ], title="Raw-curve recommendations")
                    except Exception as exc:
                        st.error(f"Raw amplification-curve QC failed: {exc}")
        plate_format = st.radio("Plate format", [96, 384], horizontal=True, key="qpcr_plate_format", disabled="well" not in frame.columns)
        if "well" in frame.columns:
            smart_json(plate_map_audit(frame, plate_format=int(plate_format)), title="Plate-layout audit", key="qpcr_plate_audit")
        if st.button("Run qPCR analysis", type="primary", width="stretch"):
            try:
                with analysis_run("Calculating efficiency-aware relative expression and replicate QC"):
                    result = qpcr_delta_delta_ct(
                        frame,
                        sample_column="sample",
                        target_ct_column="target_ct",
                        reference_ct_column="reference_ct",
                        calibrator_sample=calibrator,
                        target_efficiency=float(target_efficiency),
                        reference_efficiency=float(reference_efficiency),
                        maximum_ct=float(maximum_ct),
                        replicate_sd_limit=float(replicate_sd_limit),
                    )
                if "group" in frame.columns:
                    sample_groups = frame[["sample", "group"]].drop_duplicates("sample")
                    result = result.merge(sample_groups, on="sample", how="left")
                metric_cards([
                    ("Measurements", len(frame), None),
                    ("Samples", frame["sample"].nunique(), None),
                    ("Calibrator", calibrator, None),
                    ("QC review", int((result["replicate_qc_status"] == "Review").sum()), None),
                ])
                smart_dataframe(result, height=430)
                result["expression_error_plus"] = result["relative_expression_ci95_upper"] - result["relative_expression"]
                result["expression_error_minus"] = result["relative_expression"] - result["relative_expression_ci95_lower"]
                st.plotly_chart(
                    px.bar(
                        result,
                        x="sample",
                        y="relative_expression",
                        color="replicate_qc_status",
                        error_y="expression_error_plus",
                        error_y_minus="expression_error_minus",
                        title="Relative expression with propagated 95% uncertainty",
                    ),
                    width="stretch",
                )
                if "group" in result.columns and result["group"].nunique() >= 2:
                    reference_group = st.selectbox("Reference group for inference", sorted(result["group"].astype(str).unique()), key="qpcr_reference_group")
                    summary, tests = qpcr_group_statistics(result, group_column="group", reference_group=reference_group)
                    section_title("Biological-group summary", "◫")
                    smart_dataframe(summary, height=260)
                    smart_dataframe(tests, height=260)
                qpcr_recommendations = []
                if (result["replicate_qc_status"] == "Review").any():
                    qpcr_recommendations.append("Repeat or review samples exceeding the technical-replicate SD acceptance limit.")
                if (result["undetermined_measurements"] > 0).any():
                    qpcr_recommendations.append("Investigate undetermined/high-Ct reactions and confirm NTC/no-RT controls before interpretation.")
                if not (1.8 <= float(target_efficiency) <= 2.1 and 1.8 <= float(reference_efficiency) <= 2.1):
                    qpcr_recommendations.append("Confirm target and reference amplification efficiencies with assay-specific standard curves.")
                qpcr_recommendations.append("Use biological replicate-level ΔCt/log2 expression for group inference; technical replicates are summarized within sample.")
                recommendations_panel(qpcr_recommendations)
                st.download_button("Download qPCR results", result.to_csv(index=False), "qpcr_results.csv", "text/csv", width="stretch")
                persist_and_bundle(
                    workflow="qPCR efficiency-aware relative expression",
                    input_frame=frame,
                    outputs={"qpcr_results": result},
                    parameters={
                        "calibrator": calibrator,
                        "target_efficiency": target_efficiency,
                        "reference_efficiency": reference_efficiency,
                        "maximum_ct": maximum_ct,
                        "replicate_sd_limit": replicate_sd_limit,
                    },
                    recommendations=qpcr_recommendations,
                    source_filename=getattr(upload, "name", "demo_qpcr.csv"),
                    key="qpcr",
                )
            except Exception as exc:
                st.error(f"qPCR analysis could not run: {exc}")
        with st.expander("Long-format multi-reference qPCR"):
            long_upload = st.file_uploader(
                "Long-format qPCR CSV/TSV/Excel/RDML",
                type=["csv", "tsv", "xlsx", "xlsm", "rdml"],
                key="qpcr_long_format",
                help="Required: sample, gene, ct. Optional: target/group. Select two or more reference genes for geometric normalization.",
            )
            if long_upload:
                long_frame = load_lab_upload(long_upload, key="qpcr_long")
                long_columns = list(long_frame.columns)
                long_grid = st.columns(4)
                long_sample = long_grid[0].selectbox("Sample column", long_columns, key="qpcr_long_sample")
                long_gene = long_grid[1].selectbox("Gene column", long_columns, key="qpcr_long_gene")
                long_ct = long_grid[2].selectbox("Ct column", long_columns, key="qpcr_long_ct")
                long_target = long_grid[3].selectbox("Target/role column", long_columns, key="qpcr_long_target")
                selected_long_columns = [long_sample, long_gene, long_ct, long_target]
                if len(set(selected_long_columns)) < len(selected_long_columns):
                    st.error("Sample, gene, Ct and role must map to four distinct source columns.")
                genes = sorted(long_frame[long_gene].astype(str).unique())
                reference_genes = st.multiselect("Reference genes", genes, default=genes[: min(2, len(genes))], key="qpcr_reference_genes")
                long_calibrator = st.selectbox("Calibrator sample", sorted(long_frame[long_sample].astype(str).unique()), key="qpcr_long_calibrator")
                if len(reference_genes) >= 2:
                    try:
                        stability = qpcr_reference_gene_stability(
                            long_frame,
                            sample_column=long_sample,
                            gene_column=long_gene,
                            ct_column=long_ct,
                            candidate_genes=reference_genes,
                        )
                        smart_dataframe(stability, height=230)
                    except Exception as exc:
                        st.warning(f"Reference-gene stability could not be estimated: {exc}")
                role_values = set(long_frame[long_target].astype(str).str.lower())
                if role_values & {"ntc", "negative", "no_rt", "no-rt", "positive", "positive_control", "extraction_control", "ipc"}:
                    try:
                        control_qc = qpcr_control_qc(long_frame, role_column=long_target, ct_column=long_ct)
                        smart_dataframe(control_qc, height=220)
                    except Exception as exc:
                        st.warning(f"Control-well QC could not run: {exc}")
                if st.button("Run multi-reference qPCR", key="qpcr_run_multi_reference", disabled=len(set(selected_long_columns)) < len(selected_long_columns)):
                    try:
                        multi = qpcr_multi_reference(
                            long_frame,
                            sample_column=long_sample,
                            gene_column=long_gene,
                            ct_column=long_ct,
                            target_column=long_target,
                            reference_genes=reference_genes,
                            calibrator_sample=long_calibrator,
                            maximum_ct=float(maximum_ct),
                        )
                        smart_dataframe(multi, height=360)
                        st.plotly_chart(px.bar(multi, x=long_sample, y="relative_expression", color=long_gene, barmode="group", title="Multi-reference normalized expression"), width="stretch")
                        st.download_button("Download multi-reference qPCR", multi.to_csv(index=False), "qpcr_multi_reference.csv", "text/csv", width="stretch")
                    except Exception as exc:
                        st.error(f"Multi-reference qPCR failed: {exc}")

        with st.expander("Optional melt-curve QC"):
            melt_upload = st.file_uploader("Melt curve CSV/Excel", type=["csv", "tsv", "xlsx", "xlsm"], key="qpcr_melt")
            if melt_upload:
                melt = load_lab_upload(melt_upload, key="qpcr_melt")
                columns = st.columns(2)
                temperature_column = columns[0].selectbox("Temperature column", melt.columns, key="melt_temp")
                fluorescence_column = columns[1].selectbox("Fluorescence column", melt.columns, key="melt_fluor")
                if st.button("Analyse melt curve", key="run_melt"):
                    try:
                        melt_result = melt_curve_qc(melt[temperature_column], melt[fluorescence_column])
                        smart_json({key: value for key, value in melt_result.items() if key not in {"temperature", "negative_derivative"}}, title="Melt-curve QC", key="melt_qc_json")
                        plot = pd.DataFrame({"temperature": melt_result["temperature"], "negative_derivative": melt_result["negative_derivative"]})
                        st.plotly_chart(px.line(plot, x="temperature", y="negative_derivative", title="Melt derivative"), width="stretch")
                    except Exception as exc:
                        st.error(f"Melt-curve analysis failed: {exc}")

with elisa_tab:
    upload = st.file_uploader("ELISA plate CSV/TSV/Excel", type=["csv", "tsv", "xlsx", "xlsm"], key="wet_elisa")
    render_upload_preflight(upload, key="wet_elisa", allowed_extensions=["csv", "tsv", "xlsx", "xlsm"], soft_limit_mb=10, hard_limit_mb=50)
    raw = load_lab_upload(upload, key="elisa") if upload else read_csv_cached(DEMO / "demo_elisa.csv")
    mapping = mapping_controls(raw, "elisa", ["type", "concentration", "absorbance"], ["name", "dilution_factor", "expected_concentration", "well", "plate"], "elisa_map")
    if column_mapping_ready(mapping, required=("type", "concentration", "absorbance")):
        frame = apply_column_mapping(raw, mapping, required=["type", "concentration", "absorbance"], preserve_unmapped=True)
        if "dilution_factor" not in frame.columns:
            frame["dilution_factor"] = 1.0
        editable = st.data_editor(frame, width="stretch", hide_index=True, num_rows="dynamic", key="elisa_plate_editor")
        plate_format = st.radio("ELISA plate format", [96, 384], horizontal=True, key="elisa_plate_format", disabled="well" not in editable.columns)
        if "well" in editable.columns:
            audit = plate_map_audit(editable, plate_format=int(plate_format), plate_column="plate" if "plate" in editable.columns else None)
            smart_json(audit, title="Plate-layout audit", key="elisa_plate_audit")
            coordinates = plate_coordinates(editable, plate_format=int(plate_format))
            heat = coordinates.dropna(subset=["plate_row", "plate_column"])
            if not heat.empty:
                st.plotly_chart(px.density_heatmap(heat, x="plate_column", y="plate_row", z="absorbance", histfunc="avg", title="Plate response heatmap"), width="stretch")
                spatial_qc = plate_spatial_qc(
                    editable,
                    value_column="absorbance",
                    plate_format=int(plate_format),
                    plate_column="plate" if "plate" in editable.columns else None,
                )
                if not spatial_qc.empty:
                    smart_dataframe(spatial_qc, height=220)
        row = st.columns(3)
        model_options = row[0].multiselect("Calibration models", ["4PL", "5PL", "log-linear", "linear"], default=["4PL", "5PL", "log-linear"])
        st.caption("LLOQ/ULOQ range safety is enforced: out-of-range unknowns are flagged for dilution/repeat instead of silently exporting extreme concentrations.")
        maximum_cv = row[1].number_input("Maximum standard replicate CV %", 1.0, 100.0, 20.0, 1.0)
        blank_mode = row[2].selectbox("Blank handling", ["Use blank wells", "No blank correction"])
        if st.button("Fit calibration and quantify unknowns", type="primary", width="stretch"):
            try:
                types = editable["type"].astype(str).str.lower()
                standards = editable[types.eq("standard")].copy()
                unknowns = editable[types.eq("unknown")].copy()
                blanks = editable[types.isin(["blank", "negative", "background"])].copy()
                blank_mean = float(pd.to_numeric(blanks["absorbance"], errors="coerce").mean()) if blank_mode == "Use blank wells" and not blanks.empty else 0.0
                standards["absorbance"] = pd.to_numeric(standards["absorbance"], errors="coerce") - blank_mean
                unknowns["blank_corrected_absorbance"] = pd.to_numeric(unknowns["absorbance"], errors="coerce") - blank_mean
                with analysis_run("Fitting weighted calibration models and assay QC"):
                    calibration = fit_elisa_calibration(
                        standards,
                        candidate_models=tuple(model_options),
                        maximum_replicate_cv_percent=float(maximum_cv),
                    )
                    quantification = inverse_calibration_with_flags(
                        unknowns["blank_corrected_absorbance"],
                        model=calibration["selected_model"],
                        parameters=calibration["parameters"],
                        concentration_range=calibration["concentration_range"],
                        response_range=calibration["response_range"],
                    )
                dilution = pd.to_numeric(unknowns["dilution_factor"], errors="coerce").fillna(1.0).to_numpy(float)
                unknowns["raw_extrapolated_concentration"] = quantification["raw_extrapolated_concentration"].to_numpy(float) * dilution
                unknowns["estimated_concentration"] = quantification["estimated_concentration"].to_numpy(float) * dilution
                unknowns["quantification_status"] = quantification["quantification_status"].to_numpy()
                unknowns["recommendation"] = quantification["recommendation"].to_numpy()
                intervals = bootstrap_elisa_unknown_intervals(
                    standards,
                    unknowns["blank_corrected_absorbance"],
                    model=calibration["selected_model"],
                    iterations=150,
                )
                unknowns["ci95_lower"] = intervals["ci95_lower"].to_numpy(float) * dilution
                unknowns["ci95_upper"] = intervals["ci95_upper"].to_numpy(float) * dilution
                hook_screen = elisa_hook_effect_screen(standards)
                validation_checks, validation_summary = elisa_validation_summary(
                    calibration,
                    unknowns,
                    maximum_standard_cv_percent=float(maximum_cv),
                )
                result_summary({"selected_model": calibration["selected_model"], **calibration["parameters"], "blank_mean": blank_mean, **hook_screen}, title="Calibration selection")
                result_summary(validation_summary, title="Run-validation screening")
                smart_dataframe(validation_checks, height=260)
                smart_dataframe(calibration["fit_table"], height=260)
                smart_dataframe(calibration["standard_qc"], height=280)
                residuals = calibration["residuals"]
                st.plotly_chart(px.scatter(residuals, x="predicted", y="residual", color="replicate_qc", hover_data=["concentration"], title="Calibration residuals"), width="stretch")
                smart_dataframe(unknowns, height=360)
                assay_qc = elisa_assay_qc(editable, response_column="absorbance")
                result_summary(
                    {
                        "z_prime": assay_qc["z_prime"],
                        "z_prime_status": assay_qc["z_prime_status"],
                        "positive_controls": assay_qc["positive_controls"],
                        "negative_controls": assay_qc["negative_controls"],
                    },
                    title="Assay control QC",
                )
                if not assay_qc["replicate_qc"].empty:
                    smart_dataframe(assay_qc["replicate_qc"], height=260)
                if "name" in unknowns.columns:
                    parallelism, recovery = elisa_parallelism_recovery_qc(unknowns)
                    section_title("Dilution parallelism and recovery", "↔")
                    smart_dataframe(parallelism, height=260)
                    if not recovery.empty:
                        smart_dataframe(recovery, height=260)
                elisa_recommendations = []
                if (unknowns["quantification_status"] != "In range").any():
                    elisa_recommendations.append("Repeat or dilute samples outside the calibrated response range; unsafe extrapolated values are excluded from estimated_concentration.")
                if (calibration["standard_qc"]["replicate_qc"] == "Review").any():
                    elisa_recommendations.append("Review standard replicates exceeding the configured CV or lacking replicate support before accepting the run.")
                if calibration.get("failures"):
                    elisa_recommendations.append("Review blocked calibration models and use 5PL only with at least eight concentration levels and stable parameter covariance.")
                if hook_screen.get("hook_flag"):
                    elisa_recommendations.append("Potential hook effect detected; repeat high samples at additional dilutions.")
                recommendations_panel(elisa_recommendations)
                st.download_button("Download ELISA quantified samples", unknowns.to_csv(index=False), "elisa_quantification.csv", "text/csv", width="stretch")
                persist_and_bundle(
                    workflow="ELISA calibration and quantification",
                    input_frame=editable,
                    outputs={"quantified_samples": unknowns, "calibration_models": calibration["fit_table"], "standard_qc": calibration["standard_qc"], "assay_qc": assay_qc, "validation_checks": validation_checks, "validation_summary": validation_summary},
                    parameters={"models": model_options, "maximum_cv_percent": maximum_cv, "blank_mode": blank_mode, "selected_model": calibration["selected_model"]},
                    recommendations=elisa_recommendations,
                    source_filename=getattr(upload, "name", "demo_elisa.csv"),
                    key="elisa",
                )
            except Exception as exc:
                st.error(f"ELISA analysis could not run: {exc}")

with enzyme_tab:
    with st.expander("Extract initial rates from reaction progress curves", expanded=False):
        progress_upload = st.file_uploader("Progress-curve CSV/TSV/Excel", type=["csv", "tsv", "xlsx", "xlsm"], key="wet_enzyme_progress")
        if progress_upload:
            progress = load_lab_upload(progress_upload, key="enzyme_progress")
            progress_columns = list(progress.columns)
            progress_grid = st.columns(5)
            reaction_col = progress_grid[0].selectbox("Reaction identifier", progress_columns, key="progress_reaction")
            time_col = progress_grid[1].selectbox("Time column", progress_columns, key="progress_time")
            signal_col = progress_grid[2].selectbox("Signal/product column", progress_columns, key="progress_signal")
            expected_direction = progress_grid[3].selectbox("Expected signal direction", ["increasing", "decreasing", "auto"], key="progress_direction")
            minimum_rate_r2 = progress_grid[4].number_input("Minimum window R²", 0.50, 1.00, 0.95, 0.01, key="progress_r2")
            convert_absorbance = st.toggle("Convert absorbance slope with Beer-Lambert", value=False, key="progress_beer_lambert")
            conversion = st.columns(3)
            extinction_coefficient = conversion[0].number_input("Extinction coefficient", 1e-9, 1e9, 1.0, disabled=not convert_absorbance)
            path_length = conversion[1].number_input("Path length (cm)", 0.001, 100.0, 1.0, disabled=not convert_absorbance)
            dilution_factor = conversion[2].number_input("Dilution factor", 0.001, 1e9, 1.0, disabled=not convert_absorbance)
            if st.button("Extract initial-rate windows", key="extract_initial_rates"):
                try:
                    rates = extract_initial_rates(
                        progress,
                        reaction_column=reaction_col,
                        time_column=time_col,
                        signal_column=signal_col,
                        expected_direction=expected_direction,
                        minimum_r_squared=float(minimum_rate_r2),
                    )
                    if convert_absorbance:
                        rates["converted_rate"] = convert_absorbance_slope_to_rate(
                            rates["initial_rate"],
                            extinction_coefficient=float(extinction_coefficient),
                            path_length_cm=float(path_length),
                            dilution_factor=float(dilution_factor),
                        )
                    smart_dataframe(rates, height=300)
                    rate_recommendations = []
                    if (rates["qc_status"] == "Review").any():
                        rate_recommendations.append("Review reaction direction, lag phase and the selected linear window for reactions marked Review.")
                    rate_recommendations.append("Confirm blank correction, time units and signal-to-product conversion before fitting kinetics.")
                    recommendations_panel(rate_recommendations)
                    st.download_button("Download extracted initial rates", rates.to_csv(index=False), "enzyme_initial_rates.csv", "text/csv", width="stretch")
                    persist_and_bundle(
                        workflow="Enzyme initial-rate extraction",
                        input_frame=progress,
                        outputs={"initial_rates": rates},
                        parameters={"expected_direction": expected_direction, "minimum_r_squared": minimum_rate_r2, "beer_lambert_conversion": convert_absorbance},
                        recommendations=rate_recommendations,
                        source_filename=getattr(progress_upload, "name", "enzyme_progress.csv"),
                        key="enzyme_initial_rate",
                    )
                except Exception as exc:
                    st.error(f"Initial-rate extraction could not run: {exc}")
    upload = st.file_uploader("Enzyme kinetics CSV/TSV/Excel", type=["csv", "tsv", "xlsx", "xlsm"], key="wet_enzyme")
    render_upload_preflight(upload, key="wet_enzyme", allowed_extensions=["csv", "tsv", "xlsx", "xlsm"], soft_limit_mb=10, hard_limit_mb=50)
    raw = load_lab_upload(upload, key="enzyme") if upload else read_csv_cached(DEMO / "demo_enzyme_kinetics.csv")
    mapping = mapping_controls(raw, "enzyme", ["substrate", "velocity"], ["condition", "inhibitor", "replicate", "weight"], "enzyme_map")
    if column_mapping_ready(mapping, required=("substrate", "velocity")):
        frame = apply_column_mapping(raw, mapping, required=["substrate", "velocity"], preserve_unmapped=True)
        conditions = sorted(frame["condition"].astype(str).unique()) if "condition" in frame.columns else ["All data"]
        row = st.columns(4)
        selected_condition = row[0].selectbox("Condition", conditions)
        model = row[1].selectbox("Kinetic model", ["Automatic AICc comparison", "michaelis_menten", "hill", "substrate_inhibition"])
        weighted = row[2].toggle("Weight by replicate variance", value=True)
        enzyme_concentration = row[3].number_input("Enzyme concentration (optional)", 0.0, 1e12, 0.0, help="Used to calculate kcat in compatible concentration units.")
        condition_frame = frame[frame["condition"].astype(str) == selected_condition].copy() if "condition" in frame.columns else frame.copy()
        selected = condition_frame.copy()
        baseline_inhibitor = None
        if "inhibitor" in condition_frame.columns and pd.to_numeric(condition_frame["inhibitor"], errors="coerce").nunique() >= 2:
            inhibitor_levels = sorted(pd.to_numeric(condition_frame["inhibitor"], errors="coerce").dropna().unique())
            baseline_inhibitor = st.selectbox("Inhibitor level for baseline kinetic fit", inhibitor_levels, index=0)
            selected = condition_frame[pd.to_numeric(condition_frame["inhibitor"], errors="coerce") == float(baseline_inhibitor)].copy()
        grouped = selected.groupby("substrate", as_index=False)["velocity"].agg(["mean", "std", "count"]).reset_index()
        grouped["std"] = grouped["std"].fillna(0.0)
        grouped["weight"] = np.where(grouped["std"] > 0, 1 / np.square(grouped["std"]), 1.0)
        st.plotly_chart(px.scatter(selected, x="substrate", y="velocity", color="replicate" if "replicate" in selected.columns else None, title=f"Kinetics · {selected_condition}"), width="stretch")
        if st.button("Fit kinetic model", type="primary", width="stretch"):
            try:
                with analysis_run("Fitting nonlinear kinetic model and diagnostics"):
                    model_comparison = compare_enzyme_models(
                        grouped["substrate"],
                        grouped["mean"],
                        weights=grouped["weight"] if weighted else None,
                    )
                    selected_model = str(model_comparison.iloc[0]["model"]) if model == "Automatic AICc comparison" else model
                    result = fit_enzyme_model(grouped["substrate"], grouped["mean"], model=selected_model, weights=grouped["weight"] if weighted else None)
                if enzyme_concentration > 0 and "vmax" in result["parameters"]:
                    result["parameters"]["kcat"] = float(result["parameters"]["vmax"] / enzyme_concentration)
                    if "km" in result["parameters"] and result["parameters"]["km"] > 0:
                        result["parameters"]["kcat_over_km"] = float(result["parameters"]["kcat"] / result["parameters"]["km"])
                result_summary({key: value for key, value in result.items() if key not in {"predicted_velocity", "residuals"}}, title="Kinetic parameters")
                smart_dataframe(model_comparison, height=230)
                diagnostics = grouped.copy()
                diagnostics["predicted_velocity"] = result["predicted_velocity"]
                diagnostics["residual"] = result["residuals"]
                st.plotly_chart(px.line(diagnostics.sort_values("substrate"), x="substrate", y=["mean", "predicted_velocity"], markers=True, title="Observed and fitted velocity"), width="stretch")
                st.plotly_chart(px.scatter(diagnostics, x="predicted_velocity", y="residual", title="Kinetic residuals"), width="stretch")
                smart_dataframe(diagnostics, height=320)
                if "inhibitor" in condition_frame.columns and pd.to_numeric(condition_frame["inhibitor"], errors="coerce").nunique() >= 2:
                    section_title("Inhibition-mechanism comparison", "⌁")
                    inhibition_comparison = compare_inhibition_models(
                        condition_frame["substrate"],
                        condition_frame["inhibitor"],
                        condition_frame["velocity"],
                    )
                    smart_dataframe(inhibition_comparison, height=260)
                    if not inhibition_comparison.empty and inhibition_comparison.iloc[0]["status"] == "Fitted":
                        inhibition = global_inhibition_fit(
                            condition_frame["substrate"],
                            condition_frame["inhibitor"],
                            condition_frame["velocity"],
                            model=str(inhibition_comparison.iloc[0]["model"]),
                        )
                        result_summary({key: value for key, value in inhibition.items() if key not in {"predicted_velocity", "residuals"}}, title="Best-supported inhibition parameters")
                enzyme_recommendations = []
                if not result.get("covariance_ok", False):
                    enzyme_recommendations.append("Parameter covariance is unstable; add concentration levels or replicates before interpreting parameters.")
                if model_comparison.iloc[0].get("delta_aicc", 0) >= 4:
                    enzyme_recommendations.append("No kinetic model has strong support; inspect residuals and experimental range.")
                enzyme_recommendations.append("Report substrate, velocity, enzyme concentration and time units with blank-correction and initial-rate window settings.")
                recommendations_panel(enzyme_recommendations)
                persist_and_bundle(
                    workflow="Enzyme kinetic model fitting",
                    input_frame=condition_frame,
                    outputs={"fit_diagnostics": diagnostics, "model_comparison": model_comparison, "selected_fit": result},
                    parameters={"condition": selected_condition, "baseline_inhibitor": baseline_inhibitor, "weighted": weighted, "selected_model": selected_model, "enzyme_concentration": enzyme_concentration},
                    recommendations=enzyme_recommendations,
                    source_filename=getattr(upload, "name", "demo_enzyme_kinetics.csv"),
                    key="enzyme_kinetics",
                )
            except Exception as exc:
                st.error(f"Kinetic fitting could not run: {exc}")

with bioprocess_tab:
    upload = st.file_uploader("Bioprocess time-series CSV/TSV/Excel", type=["csv", "tsv", "xlsx", "xlsm"], key="wet_bioprocess")
    render_upload_preflight(upload, key="wet_bioprocess", allowed_extensions=["csv", "tsv", "xlsx", "xlsm"], soft_limit_mb=20, hard_limit_mb=100)
    raw = load_lab_upload(upload, key="bioprocess") if upload else read_csv_cached(DEMO / "demo_bioprocess.csv")
    mapping = mapping_controls(raw, "bioprocess", ["time", "biomass", "substrate", "product"], ["replicate", "batch", "feed", "volume", "bleed", "ph", "do", "temperature", "agitation", "airflow", "our", "cer", "kla", "oxygen_saturation", "event"], "bioprocess_map")
    if column_mapping_ready(mapping, required=("time", "biomass", "substrate", "product")):
        frame = apply_column_mapping(raw, mapping, required=["time", "biomass", "substrate", "product"], preserve_unmapped=True)
        process_mode = st.selectbox("Process mode", ["Batch", "Fed-batch", "Continuous", "Perfusion"], key="bioprocess_mode")
        batch_column = "batch" if "batch" in frame.columns else "replicate" if "replicate" in frame.columns else None
        unit_row = st.columns(4)
        time_unit = unit_row[0].selectbox("Time unit", ["h", "min", "s", "day"], index=0)
        concentration_unit = unit_row[1].selectbox("Biomass/substrate/product unit", ["g/L", "mg/L", "OD", "mol/L", "custom"], index=0)
        volume_unit = unit_row[2].selectbox("Volume unit", ["L", "mL", "µL", "custom"], index=0)
        rate_unit = unit_row[3].text_input("Feed/rate unit", value="L/h")
        variables = [column for column in frame.columns if column != "time" and pd.api.types.is_numeric_dtype(frame[column])]
        selected_vars = st.multiselect("Trajectory variables", variables, default=variables[: min(6, len(variables))])
        if selected_vars:
            long = frame.melt(id_vars="time", value_vars=selected_vars, var_name="variable", value_name="value")
            st.plotly_chart(px.line(long, x="time", y="value", color="variable", title="Bioprocess trajectory"), width="stretch")
        if st.button("Calculate process performance", type="primary", width="stretch"):
            try:
                with analysis_run("Calculating batch-aware growth, yield and dynamic productivity metrics"):
                    trajectory, advanced = bioprocess_advanced_metrics(
                        frame,
                        batch_column=batch_column,
                        process_mode=process_mode,
                        volume_column="volume" if "volume" in frame.columns else None,
                        feed_column="feed" if "feed" in frame.columns else None,
                        bleed_column="bleed" if "bleed" in frame.columns else None,
                    )
                    sensor_parts = []
                    process_rows = []
                    grouped_batches = frame.groupby(batch_column, dropna=False) if batch_column else [("single_batch", frame)]
                    for batch_name, batch_frame in grouped_batches:
                        batch_trajectory = trajectory[trajectory[batch_column].astype(str) == str(batch_name)].copy() if batch_column else trajectory.copy()
                        enriched_batch, batch_sensor = bioprocess_sensor_metrics(batch_trajectory)
                        sensor_parts.append(enriched_batch)
                        batch_yields = bioprocess_yields(batch_frame)
                        batch_growth = growth_metrics(batch_frame["time"], batch_frame["biomass"])
                        process_rows.append({
                            "batch": str(batch_name),
                            **{f"yield_{key}": value for key, value in batch_yields.items() if not isinstance(value, list)},
                            **{f"growth_{key}": value for key, value in batch_growth.items()},
                            **{f"sensor_{key}": value for key, value in batch_sensor.items()},
                        })
                    trajectory = pd.concat(sensor_parts, ignore_index=True)
                    process_summary = pd.DataFrame(process_rows)
                result_summary({"process_mode": process_mode, "batch_count": len(process_summary), **{key: value for key, value in advanced.items() if key != "batch_summary"}}, title="Process performance")
                smart_dataframe(process_summary, height=300)
                rate_columns = [column for column in ["biomass_rate", "substrate_consumption_rate", "product_formation_rate", "specific_growth_rate", "specific_productivity", "respiratory_quotient", "oxygen_transfer_rate", "cumulative_feed"] if column in trajectory.columns]
                st.plotly_chart(px.line(trajectory, x="time", y=rate_columns, title="Dynamic process and sensor rates"), width="stretch")
                smart_dataframe(trajectory, height=420)
                pat_variables = [column for column in selected_vars if column in trajectory.columns]
                if pat_variables:
                    pat_detail, pat_summary = bioprocess_pat_monitor(
                        trajectory,
                        variables=pat_variables,
                        batch_column=batch_column,
                    )
                    section_title("Retrospective PAT control screening", "⌁")
                    smart_dataframe(pat_summary, height=280)
                    flagged_pat = pat_detail[pat_detail["pat_status"] == "Review"] if not pat_detail.empty else pd.DataFrame()
                    if not flagged_pat.empty:
                        smart_dataframe(flagged_pat, height=240)
                        st.warning("PAT screening found observations outside robust retrospective limits. Confirm against validated CPP/CQA limits and process events.")
                else:
                    pat_detail, pat_summary = pd.DataFrame(), pd.DataFrame()
                if batch_column and frame[batch_column].nunique() >= 2:
                    aligned_batches, batch_summary = bioprocess_batch_comparison(frame, batch_column=batch_column)
                    section_title("Golden-batch comparison", "◎")
                    smart_dataframe(batch_summary, height=300)
                    if not aligned_batches.empty:
                        selected_batch_variable = st.selectbox("Golden-batch variable", sorted(aligned_batches["variable"].unique()), key="bioprocess_golden_variable")
                        batch_plot = aligned_batches[aligned_batches["variable"] == selected_batch_variable]
                        st.plotly_chart(px.line(batch_plot, x="normalized_time", y="value", color="batch", title=f"Aligned batches · {selected_batch_variable}"), width="stretch")
                bioprocess_recommendations = []
                mode_status = str(advanced.get("mode_specific_status", ""))
                if mode_status.startswith("Review"):
                    bioprocess_recommendations.append(mode_status.replace("Review: ", "Add ").capitalize() + " before using mode-specific mass balances.")
                if batch_column and frame[batch_column].nunique() >= 2:
                    bioprocess_recommendations.append("Review batch-specific summaries and golden-batch deviations; do not pool repeated time points across reactors.")
                bioprocess_recommendations.append(f"Confirm unit consistency: time={time_unit}, concentration={concentration_unit}, volume={volume_unit}, rate={rate_unit}.")
                bioprocess_recommendations.append("For live PAT use, connect validated historian/OPC-UA data and laboratory-defined CPP/CQA alarm limits.")
                recommendations_panel(bioprocess_recommendations)
                st.download_button("Download enriched bioprocess trajectory", trajectory.to_csv(index=False), "bioprocess_enriched.csv", "text/csv", width="stretch")
                persist_and_bundle(
                    workflow=f"{process_mode} bioprocess analytics",
                    input_frame=frame,
                    outputs={"enriched_trajectory": trajectory, "batch_process_summary": process_summary, "advanced_summary": advanced, "pat_detail": pat_detail, "pat_summary": pat_summary},
                    parameters={"process_mode": process_mode, "batch_column": batch_column, "time_unit": time_unit, "concentration_unit": concentration_unit, "volume_unit": volume_unit, "rate_unit": rate_unit},
                    recommendations=bioprocess_recommendations,
                    source_filename=getattr(upload, "name", "demo_bioprocess.csv"),
                    key="bioprocess",
                )
            except Exception as exc:
                st.error(f"Bioprocess analysis could not run: {exc}")


flow_depth_data = pd.DataFrame()
flow_source_mode = "no_data"
flow_run_summary: dict[str, object] = {}
flow_evidence_metadata: dict[str, object] = {}
with flow_tab:
    section_title("Flow-cytometry compensation, QC and hierarchical gating", "🧪")
    st.caption("Reads native FCS event data or tabular exports, applies an explicit compensation matrix, supports arcsinh transformation, control-aware thresholds and auditable gates.")
    flow_upload = st.file_uploader(
        "FCS or event table",
        type=["fcs", "csv", "tsv", "xlsx", "xlsm"],
        key="wet_flow_upload",
    )
    use_flow_demo = st.toggle("Use deterministic demonstration events", value=flow_upload is None, key="wet_flow_demo")
    flow_source_name = "demo_flow_events.csv"
    flow_metadata: dict[str, object] = {"source_kind": "deterministic_demonstration"}
    if flow_upload is not None:
        flow_source_name = getattr(flow_upload, "name", "flow_events")
        if str(flow_source_name).lower().endswith(".fcs"):
            try:
                native = parse_native_source(flow_upload, preferred_viewer="flow_gating", max_records=300_000, format_key="fcs")
                flow_raw = native.primary.copy()
                flow_metadata = native.summary()
                if native.truncated:
                    st.warning(f"Interactive preview loaded {len(flow_raw):,} of {native.total_records or 'unknown'} events. Use the background queue for a complete large-file run.")
            except Exception as exc:
                st.error(f"FCS decoding stopped safely: {exc}")
                flow_raw = pd.DataFrame()
        else:
            try:
                flow_raw = load_lab_upload(flow_upload, key="flow")
                flow_metadata = {"source_kind": "uploaded_event_table", "source": flow_source_name, "records": len(flow_raw)}
            except Exception as exc:
                st.error(f"Flow event table could not be read: {exc}")
                flow_raw = pd.DataFrame()
    elif use_flow_demo:
        rng = np.random.default_rng(120)
        n_events = 12_000
        population = rng.choice(["lymphocyte", "monocyte", "debris"], size=n_events, p=[0.62, 0.25, 0.13])
        fsc = np.where(population == "lymphocyte", rng.normal(55_000, 8_000, n_events), np.where(population == "monocyte", rng.normal(82_000, 10_000, n_events), rng.normal(18_000, 6_000, n_events)))
        ssc = np.where(population == "lymphocyte", rng.normal(22_000, 5_000, n_events), np.where(population == "monocyte", rng.normal(55_000, 9_000, n_events), rng.normal(12_000, 4_000, n_events)))
        cd3_true = np.where(population == "lymphocyte", rng.lognormal(8.8, 0.42, n_events), rng.lognormal(6.4, 0.5, n_events))
        cd19_true = np.where((population == "lymphocyte") & (rng.random(n_events) < 0.34), rng.lognormal(8.5, 0.4, n_events), rng.lognormal(6.1, 0.45, n_events))
        observed_cd3 = cd3_true + 0.08 * cd19_true
        observed_cd19 = cd19_true + 0.05 * cd3_true
        flow_raw = pd.DataFrame({
            "event_id": [f"E{i + 1:06d}" for i in range(n_events)],
            "Time": np.linspace(0, 420, n_events),
            "FSC-A": np.clip(fsc, 50, None),
            "FSC-H": np.clip(fsc * rng.normal(0.98, 0.06, n_events), 50, None),
            "SSC-A": np.clip(ssc, 20, None),
            "CD3-A": np.clip(observed_cd3, 0, None),
            "CD19-A": np.clip(observed_cd19, 0, None),
        })
    else:
        flow_raw = pd.DataFrame()

    if not flow_raw.empty:
        numeric_channels = [str(column) for column in flow_raw.columns if pd.to_numeric(flow_raw[column], errors="coerce").notna().mean() >= 0.9]
        if len(numeric_channels) < 2:
            st.error("At least two numeric event channels are required.")
        else:
            smart_json(flow_metadata, title="FCS/event-source metadata", key="wet_flow_metadata")
            with st.expander("Raw event preview", expanded=False):
                smart_dataframe(flow_raw.head(1_000), height=320, key="wet_flow_preview")

            identity_candidates = [column for column in flow_raw.columns if column not in numeric_channels]
            control_row = st.columns(3)
            event_id_column = control_row[0].selectbox("Event ID column", ["None", *map(str, flow_raw.columns)], index=(1 + list(map(str, flow_raw.columns)).index("event_id")) if "event_id" in flow_raw.columns else 0, key="wet_flow_event_id")
            time_default = numeric_channels.index("Time") + 1 if "Time" in numeric_channels else 0
            time_channel = control_row[1].selectbox("Acquisition time channel", ["None", *numeric_channels], index=time_default, key="wet_flow_time")
            transform_cofactor = control_row[2].number_input("Arcsinh cofactor", min_value=1.0, max_value=10_000.0, value=150.0, step=10.0, key="wet_flow_cofactor")

            fluorescence_default = [channel for channel in numeric_channels if not any(token in channel.upper() for token in ("FSC", "SSC", "TIME", "WIDTH", "HEIGHT"))][:8]
            fluorescence_channels = st.multiselect("Fluorescence channels", numeric_channels, default=fluorescence_default, key="wet_flow_fluorescence")

            control_manifest = pd.DataFrame(columns=["control_type", "channel", "events", "panel_version", "instrument_id", "lot_id", "file_name"])
            if fluorescence_channels:
                with st.expander("Control manifest and panel provenance", expanded=True):
                    st.caption("Release-grade analysis requires an unstained control, a single-stain control for every fluorescence channel, locked panel/instrument metadata, and an FMO control for the reported positive gate.")
                    control_upload = st.file_uploader(
                        "Control manifest (CSV/TSV/Excel)",
                        type=["csv", "tsv", "xlsx", "xlsm"],
                        key="wet_flow_control_manifest",
                    )
                    if control_upload is not None:
                        try:
                            control_manifest = load_lab_upload(control_upload, key="flow_control_manifest")
                        except Exception as exc:
                            st.error(f"Control manifest could not be read: {exc}")
                    elif use_flow_demo:
                        rows = [{"control_type": "unstained", "channel": "", "events": 2_500, "panel_version": "DEMO-PANEL-1", "instrument_id": "DEMO-CYTOMETER", "lot_id": "DEMO", "file_name": "demo_unstained.csv"}]
                        rows.extend({"control_type": "single_stain", "channel": channel, "events": 2_500, "panel_version": "DEMO-PANEL-1", "instrument_id": "DEMO-CYTOMETER", "lot_id": "DEMO", "file_name": f"demo_single_{channel}.csv"} for channel in fluorescence_channels)
                        control_manifest = pd.DataFrame(rows)
                        st.info("A deterministic demonstration control manifest is shown. Demonstration evidence remains blocked from scientific release.")
                    else:
                        template_rows = [{"control_type": "unstained", "channel": "", "events": 0, "panel_version": "", "instrument_id": "", "lot_id": "", "file_name": ""}]
                        template_rows.extend({"control_type": "single_stain", "channel": channel, "events": 0, "panel_version": "", "instrument_id": "", "lot_id": "", "file_name": ""} for channel in fluorescence_channels)
                        control_manifest = st.data_editor(pd.DataFrame(template_rows), num_rows="dynamic", width="stretch", key="wet_flow_control_editor")
                    try:
                        preliminary_control_audit = validate_control_manifest(control_manifest, fluorescence_channels, minimum_events=500)
                        smart_dataframe(preliminary_control_audit.checks, height=280, key="wet_flow_control_checks_pre")
                    except Exception as exc:
                        preliminary_control_audit = validate_control_manifest(pd.DataFrame(), fluorescence_channels, minimum_events=500)
                        st.error(f"Control manifest validation stopped safely: {exc}")

            processed = flow_raw.copy()
            compensation_manifest: dict[str, object] = {"applied": False, "matrix_source": "none"}
            if fluorescence_channels:
                apply_comp = st.toggle("Apply spillover compensation", value=False, key="wet_flow_apply_comp")
                if apply_comp:
                    compensation_source = st.selectbox(
                        "Compensation source",
                        ["Instrument/export matrix", "Derive from single-stain event files", "Exploratory/manual matrix"],
                        key="wet_flow_compensation_source",
                    )
                    default_matrix = pd.DataFrame(np.eye(len(fluorescence_channels)), index=fluorescence_channels, columns=fluorescence_channels)
                    if use_flow_demo and len(fluorescence_channels) >= 2:
                        default_matrix.iloc[0, 1] = 0.08
                        default_matrix.iloc[1, 0] = 0.05
                    matrix_to_apply = default_matrix
                    derivation_manifest: dict[str, object] = {}
                    if compensation_source == "Derive from single-stain event files":
                        st.caption("Upload the unstained event table and one event table per selected fluorescence channel. The spillover matrix is estimated from robust positive-control medians.")
                        unstained_upload = st.file_uploader("Unstained event table", type=["csv", "tsv", "xlsx", "xlsm"], key="wet_flow_unstained_events")
                        single_stain_frames: dict[str, pd.DataFrame] = {}
                        for channel in fluorescence_channels:
                            single_upload = st.file_uploader(f"Single-stain events · {channel}", type=["csv", "tsv", "xlsx", "xlsm"], key=f"wet_flow_single_{channel}")
                            if single_upload is not None:
                                try:
                                    single_stain_frames[channel] = load_lab_upload(single_upload, key=f"flow_single_{channel}")
                                except Exception as exc:
                                    st.warning(f"{channel} single-stain control could not be read: {exc}")
                        if unstained_upload is not None and len(single_stain_frames) == len(fluorescence_channels):
                            try:
                                unstained_frame = load_lab_upload(unstained_upload, key="flow_unstained_events")
                                matrix_to_apply, derivation_manifest = derive_compensation_matrix(single_stain_frames, fluorescence_channels, unstained_events=unstained_frame)
                                st.success("Compensation matrix derived from explicit single-stain controls.")
                                smart_dataframe(matrix_to_apply.reset_index(names="detector"), height=260, key="wet_flow_derived_matrix")
                            except Exception as exc:
                                st.error(f"Compensation derivation stopped safely: {exc}")
                        else:
                            st.info("Upload the complete unstained and single-stain control set to derive the matrix.")
                    else:
                        matrix_to_apply = st.data_editor(default_matrix, width="stretch", key="wet_flow_matrix")
                    try:
                        processed, compensation_manifest = apply_compensation(processed, fluorescence_channels, matrix_to_apply)
                        compensation_manifest.update(derivation_manifest)
                        compensation_manifest["applied"] = True
                        compensation_manifest["matrix_source"] = {
                            "Instrument/export matrix": "instrument/export",
                            "Derive from single-stain event files": "single-stain controls",
                            "Exploratory/manual matrix": "exploratory/manual",
                        }[compensation_source]
                        if not control_manifest.empty:
                            compensation_manifest["control_manifest_sha256"] = preliminary_control_audit.summary.get("manifest_sha256")
                        if compensation_source == "Instrument/export matrix":
                            compensation_manifest["method"] = "instrument/export matrix"
                        elif compensation_source == "Exploratory/manual matrix":
                            compensation_manifest["method"] = "exploratory manual spillover matrix"
                        st.success("Compensation matrix validated and applied.")
                    except Exception as exc:
                        st.error(f"Compensation was not applied: {exc}")
                apply_transform = st.toggle("Apply arcsinh transformation to fluorescence channels", value=True, key="wet_flow_transform")
                if apply_transform:
                    try:
                        processed = arcsinh_transform(processed, fluorescence_channels, transform_cofactor)
                    except Exception as exc:
                        st.error(f"Transformation was not applied: {exc}")

            flow_depth_data = processed.copy()
            qc = flow_qc(
                processed,
                event_id_column=None if event_id_column == "None" else event_id_column,
                time_column=None if time_channel == "None" else time_channel,
                channels=numeric_channels,
                minimum_events=1_000,
            )
            result_summary(qc.summary, title="Flow acquisition QC summary")
            smart_dataframe(qc.checks, height=260, key="wet_flow_qc_checks")
            smart_dataframe(qc.channel_metrics, height=300, key="wet_flow_channel_metrics")
            if not qc.flagged_events.empty:
                with st.expander("Saturation/flagged-event preview", expanded=False):
                    smart_dataframe(qc.flagged_events, height=280, key="wet_flow_flagged")

            scatter_row = st.columns(2)
            x_channel = scatter_row[0].selectbox("Gating X channel", numeric_channels, index=numeric_channels.index("FSC-A") if "FSC-A" in numeric_channels else 0, key="wet_flow_x")
            y_channel = scatter_row[1].selectbox("Gating Y channel", numeric_channels, index=numeric_channels.index("SSC-A") if "SSC-A" in numeric_channels else min(1, len(numeric_channels) - 1), key="wet_flow_y")
            plot_frame = processed[[x_channel, y_channel]].dropna()
            if len(plot_frame) > 50_000:
                plot_frame = plot_frame.sample(50_000, random_state=120)
            st.plotly_chart(px.scatter(plot_frame, x=x_channel, y=y_channel, opacity=0.25, title="Event density and gate planning"), width="stretch")

            x_values = pd.to_numeric(processed[x_channel], errors="coerce")
            y_values = pd.to_numeric(processed[y_channel], errors="coerce")
            x_low, x_high = np.nanpercentile(x_values, [5, 95])
            y_low, y_high = np.nanpercentile(y_values, [5, 95])
            gate_row = st.columns(4)
            gate_x_min = gate_row[0].number_input("X minimum", value=float(x_low), key="wet_flow_xmin")
            gate_x_max = gate_row[1].number_input("X maximum", value=float(x_high), key="wet_flow_xmax")
            gate_y_min = gate_row[2].number_input("Y minimum", value=float(y_low), key="wet_flow_ymin")
            gate_y_max = gate_row[3].number_input("Y maximum", value=float(y_high), key="wet_flow_ymax")

            populations: dict[str, pd.DataFrame] = {"All events": processed}
            gates = []
            parent_frame = processed
            if st.toggle("Apply singlet gate before rectangle gate", value="FSC-A" in processed.columns and "FSC-H" in processed.columns, key="wet_flow_singlets"):
                area_options = [channel for channel in numeric_channels if channel.upper().endswith("-A") or "AREA" in channel.upper()]
                height_options = [channel for channel in numeric_channels if channel.upper().endswith("-H") or "HEIGHT" in channel.upper()]
                if area_options and height_options:
                    singlet_cols = st.columns(3)
                    area_channel = singlet_cols[0].selectbox("Area channel", area_options, key="wet_flow_area")
                    height_channel = singlet_cols[1].selectbox("Height channel", height_options, key="wet_flow_height")
                    ratio_tolerance = singlet_cols[2].slider("Singlet ratio tolerance", 0.05, 0.45, 0.18, 0.01, key="wet_flow_singlet_tol")
                    try:
                        singlets = singlet_gate(parent_frame, area_channel, height_channel, ratio_tolerance=ratio_tolerance)
                        gates.append(singlets)
                        populations[singlets.name] = singlets.events
                        parent_frame = singlets.events
                    except Exception as exc:
                        st.warning(f"Singlet gate skipped: {exc}")

            try:
                primary_gate = rectangular_gate(
                    parent_frame,
                    x_channel,
                    y_channel,
                    x_min=gate_x_min,
                    x_max=gate_x_max,
                    y_min=gate_y_min,
                    y_max=gate_y_max,
                    name="Primary population",
                    parent=gates[-1].name if gates else "All events",
                )
                gates.append(primary_gate)
                populations[primary_gate.name] = primary_gate.events
            except Exception as exc:
                st.error(f"Primary gate could not be applied: {exc}")

            threshold_manifest: dict[str, object] = {}
            positive_channel = ""
            fmo_upload = None
            if fluorescence_channels:
                positive_channel = st.selectbox("Marker-positive threshold channel", fluorescence_channels, key="wet_flow_positive_channel")
                fmo_upload = st.file_uploader("FMO/control event table (CSV/TSV/Excel)", type=["csv", "tsv", "xlsx", "xlsm"], key="wet_flow_fmo")
                if fmo_upload is not None:
                    try:
                        fmo_frame = load_lab_upload(fmo_upload, key="flow_fmo")
                        threshold = fmo_threshold(fmo_frame, positive_channel)
                        threshold_manifest = {"channel": positive_channel, "method": "FMO 99.5th percentile", "threshold": threshold, "control_file": getattr(fmo_upload, "name", "control")}
                        st.success(f"FMO-derived {positive_channel} threshold: {threshold:.4g}")
                    except Exception as exc:
                        st.warning(f"FMO threshold unavailable: {exc}")
                else:
                    reference_population = populations.get("Primary population", processed)
                    threshold = float(pd.to_numeric(reference_population[positive_channel], errors="coerce").quantile(0.95))
                    threshold_manifest = {"channel": positive_channel, "method": "exploratory 95th percentile (no FMO control)", "threshold": threshold}
                    st.warning("No FMO control was supplied. The displayed threshold is exploratory and must not be treated as a validated positive gate.")
                if "Primary population" in populations:
                    marker_positive = populations["Primary population"].loc[pd.to_numeric(populations["Primary population"][positive_channel], errors="coerce") >= threshold].copy()
                    populations[f"{positive_channel} positive"] = marker_positive

                final_control_manifest = control_manifest.copy()
                if fmo_upload is not None:
                    fmo_row = {
                        "control_type": "fmo",
                        "channel": positive_channel,
                        "events": int(len(fmo_frame)) if "fmo_frame" in locals() else 0,
                        "panel_version": str(final_control_manifest.get("panel_version", pd.Series([""])).dropna().astype(str).replace("", np.nan).dropna().iloc[0]) if "panel_version" in final_control_manifest and not final_control_manifest["panel_version"].replace("", np.nan).dropna().empty else "",
                        "instrument_id": str(final_control_manifest.get("instrument_id", pd.Series([""])).dropna().astype(str).replace("", np.nan).dropna().iloc[0]) if "instrument_id" in final_control_manifest and not final_control_manifest["instrument_id"].replace("", np.nan).dropna().empty else "",
                        "lot_id": "",
                        "file_name": getattr(fmo_upload, "name", "fmo_control"),
                    }
                    final_control_manifest = pd.concat([final_control_manifest, pd.DataFrame([fmo_row])], ignore_index=True)
                elif use_flow_demo:
                    demo_fmo = {"control_type": "fmo", "channel": positive_channel, "events": 2_500, "panel_version": "DEMO-PANEL-1", "instrument_id": "DEMO-CYTOMETER", "lot_id": "DEMO", "file_name": f"demo_fmo_{positive_channel}.csv"}
                    final_control_manifest = pd.concat([final_control_manifest, pd.DataFrame([demo_fmo])], ignore_index=True)
                try:
                    control_audit = validate_control_manifest(final_control_manifest, fluorescence_channels, require_fmo_channels=[positive_channel], minimum_events=500)
                except Exception as exc:
                    st.error(f"Final control audit stopped safely: {exc}")
                    control_audit = validate_control_manifest(pd.DataFrame(), fluorescence_channels, require_fmo_channels=[positive_channel], minimum_events=500)
            else:
                control_audit = None

            gate_table = audit_gate_hierarchy(gates, minimum_events=50)
            summary_channels = fluorescence_channels[:6] if fluorescence_channels else [x_channel, y_channel]
            population_table = population_summary(populations, summary_channels)
            section_title("Hierarchical gating audit", "⌁")
            smart_dataframe(gate_table, height=260, key="wet_flow_gate_audit")
            smart_dataframe(population_table, height=320, key="wet_flow_population_summary")

            section_title("Evidence and release gate", "🛡️")
            release_cols = st.columns(2)
            instrument_qc_confirmed = release_cols[0].checkbox("Daily instrument QC passed and is documented", value=False, key="wet_flow_instrument_qc")
            reviewer = release_cols[1].text_input("Independent gating reviewer", value="", key="wet_flow_reviewer", placeholder="Name or controlled reviewer ID")
            if control_audit is not None:
                smart_dataframe(control_audit.checks, height=320, key="wet_flow_control_checks_final")
                release_gate = flow_release_gate(
                    qc,
                    control_audit,
                    compensation_manifest,
                    gates,
                    reviewer=reviewer,
                    instrument_qc_confirmed=instrument_qc_confirmed,
                    source_mode=str(flow_metadata.get("source_kind", "uploaded")),
                )
                smart_dataframe(release_gate.checks, height=300, key="wet_flow_release_checks")
                if release_gate.release_ready:
                    st.success("Flow-cytometry evidence gate passed for controlled research release.")
                else:
                    st.warning("Release remains blocked: " + ", ".join(release_gate.blockers))
            else:
                release_gate = None
                st.warning("No fluorescence channels were selected; control-aware release assessment is unavailable.")

            flow_source_mode = str(flow_metadata.get("source_kind", "uploaded"))
            flow_run_summary = release_gate.summary if release_gate is not None else {"release_ready": False, "blockers": ["No fluorescence/control assessment"]}
            flow_evidence_metadata = {
                "reviewer": reviewer,
                "instrument_qc_confirmed": instrument_qc_confirmed,
                "control_manifest_sha256": control_audit.summary.get("manifest_sha256") if control_audit is not None else None,
                "compensation_source": compensation_manifest.get("matrix_source"),
                "reference_release": str(control_audit.summary.get("panel_versions", [""])[0]) if control_audit is not None and control_audit.summary.get("panel_versions") else "",
                "software_version": "BioIntel AI Step 151",
            }

            flow_recommendations = [
                "Use single-stained controls and instrument-specific spillover values; do not estimate a production compensation matrix from study samples.",
                "Use unstained, FMO and biological controls with a prespecified gating hierarchy and locked transformations.",
                "Review time drift, saturation, doublets and representative event plots before releasing population frequencies.",
                "For multi-panel studies, retain panel version, antibody lot, fluorochrome, voltage and instrument QC metadata.",
            ]
            recommendations_panel(flow_recommendations)
            flow_outputs = {
                "qc_summary": qc.summary,
                "qc_checks": qc.checks,
                "channel_metrics": qc.channel_metrics,
                "gate_audit": gate_table,
                "population_summary": population_table,
                "compensation": compensation_manifest,
                "threshold": threshold_manifest,
                "source_metadata": flow_metadata,
                "control_audit": control_audit.summary if control_audit is not None else {},
                "control_checks": control_audit.checks if control_audit is not None else pd.DataFrame(),
                "release_gate": release_gate.summary if release_gate is not None else {},
                "release_checks": release_gate.checks if release_gate is not None else pd.DataFrame(),
            }
            persist_and_bundle(
                workflow="Flow cytometry compensation and hierarchical gating",
                input_frame=processed,
                outputs=flow_outputs,
                parameters={
                    "numeric_channels": numeric_channels,
                    "fluorescence_channels": fluorescence_channels,
                    "arcsinh_cofactor": transform_cofactor,
                    "x_channel": x_channel,
                    "y_channel": y_channel,
                },
                recommendations=flow_recommendations,
                source_filename=flow_source_name,
                key="flow_cytometry",
            )


with design_tab:
    with st.form("experimental_design_advanced_form"):
        design_type = st.selectbox(
            "Study design",
            ["Two independent groups", "Paired measurements", "Repeated measures", "One-way ANOVA", "Two proportions", "Correlation", "Non-inferiority", "Equivalence", "Cluster randomized"],
        )
        row = st.columns(5)
        effect_size = row[0].number_input("Effect size", 0.01, 5.0, 0.8, 0.05)
        alpha = row[1].number_input("Alpha", 0.001, 0.25, 0.05, 0.001)
        power = row[2].number_input("Power", 0.50, 0.999, 0.80, 0.01)
        dropout = row[3].number_input("Dropout fraction", 0.0, 0.79, 0.10, 0.01)
        number_groups = row[4].number_input("Groups", 2, 12, 3, disabled=design_type != "One-way ANOVA")
        proportion_row = st.columns(2)
        proportion_1 = proportion_row[0].number_input("Proportion 1", 0.01, 0.99, 0.30, 0.01, disabled=design_type != "Two proportions")
        proportion_2 = proportion_row[1].number_input("Proportion 2", 0.01, 0.99, 0.55, 0.01, disabled=design_type != "Two proportions")
        advanced_row = st.columns(5)
        measurements = advanced_row[0].number_input("Repeated measurements", 2, 20, 3, disabled=design_type != "Repeated measures")
        within_correlation = advanced_row[1].number_input("Within-subject / expected correlation", -0.90, 0.95, 0.50, 0.05, disabled=design_type not in {"Repeated measures", "Correlation"})
        margin = advanced_row[2].number_input("NI/equivalence margin", 0.01, 10.0, 0.50, 0.05, disabled=design_type not in {"Non-inferiority", "Equivalence"})
        assumed_sd = advanced_row[3].number_input("Assumed outcome SD", 0.0001, 1e9, 1.0, disabled=design_type not in {"Non-inferiority", "Equivalence"})
        average_cluster_size = advanced_row[4].number_input("Average cluster size", 2.0, 10_000.0, 12.0, 1.0, disabled=design_type != "Cluster randomized")
        cluster_row = st.columns(2)
        intracluster_correlation = cluster_row[0].number_input("Intracluster correlation", 0.0, 0.99, 0.05, 0.01, disabled=design_type != "Cluster randomized")
        cluster_size_cv = cluster_row[1].number_input("Cluster-size CV", 0.0, 5.0, 0.0, 0.05, disabled=design_type != "Cluster randomized")
        total_samples = st.number_input("Samples to randomize", 4, 100_000, 24)
        groups = st.multiselect("Randomization groups", ["Control", "Treatment A", "Treatment B", "Vehicle"], default=["Control", "Treatment A"])
        blind_labels = st.toggle("Create blinded arm labels", value=True)
        secure_seed = st.toggle("Generate secure randomization seed", value=True)
        manual_seed = st.number_input("Manual reproducibility seed", 1, 2_147_483_647, 42, disabled=secure_seed)
        strata_upload = st.file_uploader("Optional sample stratification CSV", type=["csv", "tsv"], help="Columns: sample,stratum. Sample IDs must match S0001... or supplied IDs.")
        strata_sample_column = st.text_input("Strata sample column", value="sample", disabled=strata_upload is None)
        strata_value_column = st.text_input("Strata value column", value="stratum", disabled=strata_upload is None)
        plate_format = st.selectbox("Optional plate randomization", ["None", "96", "384"])
        plate_replicates = st.number_input("Plate technical replicates", 1, 8, 1, disabled=plate_format == "None")
        run = st.form_submit_button("Calculate design and randomize", type="primary", width="stretch")
    if run:
        try:
            if len(set(groups)) < 2:
                raise ValueError("Select at least two unique randomization groups.")
            if design_type == "Two independent groups":
                calculation = two_group_sample_size(float(effect_size), alpha=float(alpha), power=float(power), dropout_fraction=float(dropout))
                sensitivity_design = "two_group"
            elif design_type == "Paired measurements":
                calculation = paired_sample_size(float(effect_size), alpha=float(alpha), power=float(power), dropout_fraction=float(dropout))
                sensitivity_design = "paired"
            elif design_type == "Repeated measures":
                calculation = repeated_measures_sample_size(float(effect_size), measurements=int(measurements), within_subject_correlation=float(within_correlation), alpha=float(alpha), power=float(power), dropout_fraction=float(dropout))
                sensitivity_design = "paired"
            elif design_type == "One-way ANOVA":
                calculation = one_way_anova_sample_size(float(effect_size), int(number_groups), alpha=float(alpha), power=float(power), dropout_fraction=float(dropout))
                sensitivity_design = "anova"
            elif design_type == "Two proportions":
                calculation = two_proportion_sample_size(float(proportion_1), float(proportion_2), alpha=float(alpha), power=float(power), dropout_fraction=float(dropout))
                sensitivity_design = "two_group"
            elif design_type == "Correlation":
                calculation = correlation_sample_size(float(within_correlation), alpha=float(alpha), power=float(power), dropout_fraction=float(dropout))
                sensitivity_design = "paired"
            elif design_type == "Non-inferiority":
                calculation = noninferiority_sample_size(float(margin), assumed_standard_deviation=float(assumed_sd), alpha=float(alpha) / 2, power=float(power), dropout_fraction=float(dropout))
                sensitivity_design = "two_group"
            elif design_type == "Equivalence":
                calculation = equivalence_sample_size(float(margin), assumed_standard_deviation=float(assumed_sd), alpha=float(alpha), power=float(power), dropout_fraction=float(dropout))
                sensitivity_design = "two_group"
            else:
                base = two_group_sample_size(float(effect_size), alpha=float(alpha), power=float(power), dropout_fraction=0.0)
                calculation = cluster_adjusted_sample_size(int(base["total"]), average_cluster_size=float(average_cluster_size), intracluster_correlation=float(intracluster_correlation), cluster_size_cv=float(cluster_size_cv), dropout_fraction=float(dropout))
                sensitivity_design = "two_group"
            result_summary(calculation, title="Power-based sample size")
            curve = sensitivity_curve(sensitivity_design, [max(0.05, float(effect_size) * value) for value in (0.5, 0.75, 1.0, 1.25, 1.5)], alpha=float(alpha), power=float(power), groups=int(number_groups), dropout_fraction=float(dropout))
            st.plotly_chart(px.line(curve, x="effect_size", y="total_sample_size", markers=True, title="Effect-size sensitivity"), width="stretch")
            sample_ids = [f"S{index:04d}" for index in range(1, int(total_samples) + 1)]
            blocks = None
            if strata_upload is not None:
                strata_frame = read_uploaded_table(strata_upload)
                if strata_sample_column not in strata_frame.columns or strata_value_column not in strata_frame.columns:
                    raise ValueError("Stratification file must contain the configured sample and stratum columns.")
                blocks = dict(zip(strata_frame[strata_sample_column].astype(str), strata_frame[strata_value_column].astype(str)))
                missing_strata = [sample for sample in sample_ids if sample not in blocks]
                if missing_strata:
                    raise ValueError(f"Stratification is missing {len(missing_strata)} sample IDs; first: {missing_strata[0]}")
            assignment_seed = int(manual_seed) if not secure_seed else secrets.randbelow(2_147_483_646) + 1
            assignment = randomized_assignment(sample_ids, groups, blocks=blocks, seed=assignment_seed, blind_labels=blind_labels)
            smart_dataframe(assignment, height=360)
            st.download_button("Download randomized assignment", assignment.to_csv(index=False), "randomized_assignment.csv", "text/csv", width="stretch")
            plate = pd.DataFrame()
            if plate_format != "None":
                plate = plate_randomization(
                    sample_ids,
                    plate_format=int(plate_format),
                    replicates=int(plate_replicates),
                    seed=None if secure_seed else int(manual_seed),
                    controls={"Blank": 2, "Positive control": 2},
                    avoid_adjacent_replicates=True,
                )
                smart_dataframe(plate, height=360)
                if int(plate["adjacency_violations"].iloc[0]) > 0:
                    st.warning("A zero-adjacency layout could not be found at the requested plate occupancy; review layout_qc.")
                st.download_button("Download plate randomization", plate.to_csv(index=False), "plate_randomization.csv", "text/csv", width="stretch")
            design_recommendations = [
                "Document the scientific basis for effect size, expected SD, margin, dropout and multiplicity assumptions.",
                "Use real baseline strata such as site, batch, sex, disease severity, passage or operator; no artificial alternating strata are generated.",
                "Store the concealed allocation key separately from the blinded assignment and control any re-randomization.",
            ]
            recommendations_panel(design_recommendations)
            persist_and_bundle(
                workflow=f"Experimental design · {design_type}",
                input_frame=assignment,
                outputs={"sample_size": calculation, "randomized_assignment": assignment, "plate_randomization": plate},
                parameters={"design_type": design_type, "effect_size": effect_size, "alpha": alpha, "power": power, "dropout": dropout, "assumed_sd": assumed_sd, "secure_seed": secure_seed},
                recommendations=design_recommendations,
                source_filename=getattr(strata_upload, "name", "generated_sample_ids.csv"),
                key="experimental_design",
            )
        except Exception as exc:
            st.error(f"Experimental design could not run: {exc}")

insight_callout(
    "Laboratory boundary",
    "These tools provide auditable research calculations and QC screens. Electronic signatures, regulated LIMS validation, instrument certification and laboratory accreditation remain organisation-specific external controls.",
    "warning",
)

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("flow_gating", key_prefix="step110_64_Wet_Lab_Biotechnology_flow_gating")
_render_step110_viewer("plate_map", key_prefix="step110_64_Wet_Lab_Biotechnology_plate_map")
_render_step110_viewer("bioprocess_live", key_prefix="step110_64_Wet_Lab_Biotechnology_bioprocess_live")

# Step 115 non-chart visual: flow_gating_canvas
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("flow_gating_canvas", key_prefix="step115_64_Wet_Lab_Biotechnology_flow_gating_canvas", expanded=False)

# Step 115 non-chart visual: plate_map_editor
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("plate_map_editor", key_prefix="step115_64_Wet_Lab_Biotechnology_plate_map_editor", expanded=False)

# Step 115 non-chart visual: bioprocess_board
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("bioprocess_board", key_prefix="step115_64_Wet_Lab_Biotechnology_bioprocess_board", expanded=False)


# Step 120 flow-cytometry execution, validation and evidence gate
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step120_depth
_render_step120_depth("flow_cytometry", flow_depth_data, key_prefix="step151_flow_cytometry", expanded=False, source_mode=flow_source_mode, run_summary=flow_run_summary, evidence_metadata=flow_evidence_metadata)

# STEP127_SCIENTIFIC_DEPTH_WET_LAB
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('wet_lab', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='wetlab_biotechnology', title='Wet-Lab Biotechnology', category='Lab Analytics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='wetlab_biotechnology', title='Wet-Lab Biotechnology', category='Lab Analytics')

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("flow_cytometry", expanded=False)


# Step 185 operational assurance panel (synthetic/demo boundary preserved)
try:
    from biointel.operational_assurance_v185.ui import render_step185_operational_assurance as _render_step185_operational_assurance
    _render_step185_operational_assurance("flow_cytometry")
except Exception as _step185_exc:
    try:
        import streamlit as st
        st.info(f"Step 185 assurance panel unavailable: {_step185_exc}")
    except Exception:
        pass

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('flow_cytometry', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('flow_cytometry', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('flow_cytometry', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('flow_cytometry', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('flow_cytometry', expanded=False)

