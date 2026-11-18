from __future__ import annotations

import hashlib
import json
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

from biointel.innovation.advanced_engines import (
    biomarker_model_advanced,
    external_validate_biomarker,
)
from biointel.innovation.engines import demo_multiomics
from biointel.innovation.excellence_ui import render_biomarker_excellence
from biointel.innovation.professional_ui import render_biomarker_professional
from biointel.ui.components import (
    metric_cards,
    scientific_boundary_banner,
    smart_dataframe,
    smart_json,
)
from biointel.ui.theme import apply_theme, hero, insight_callout
from biointel.ui.workflow import analysis_run, read_uploaded_table, render_upload_preflight

st.set_page_config(
    page_title="Multi-Omics Biomarker Discovery Studio · BioIntel AI",
    page_icon="📈",
    layout="wide",
)
apply_theme()

from biointel.ui.scientific_integrations import render_page_integrations as _render_biointel_integrations
_render_biointel_integrations("pages/102_Multi_Omics_Biomarker_Discovery.py", key_prefix="102_multi_omics_biomarker_discovery", expanded=False)

# STEP196_CONTEXTUAL_ONLINE_RESEARCH_HOOK · TOP RELEVANT WEBSITES
from biointel.contextual_research_v196.ui import render_contextual_online_research as _render_step196_contextual_online_research
_render_step196_contextual_online_research('multiomics_biomarker_discovery', expanded=False)

# STEP196_P0_P1_PRIORITY_UPGRADE_HOOK
from biointel.proof_gates_v10.ui import render_module_priority_workbench as _render_step196_p0_p1_priority_workbench
_render_step196_p0_p1_priority_workbench(ROOT, 'multiomics_biomarker_discovery', expanded=False)
# STEP178_19_MODULE_CLINICAL_OPERATIONAL_PRIVACY_ML_ASSURANCE
from biointel.target_modules_v178.ui import render_step178_module_upgrade
render_step178_module_upgrade('multiomics_biomarker_discovery', expanded=False)


# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("biomarker_discovery", key_prefix="step116_102_Multi_Omics_Biomarker_Discovery_biomarker_discovery_1", expanded=False)
hero(
    "Multi-Omics Biomarker Discovery Studio Pro",
    "Train leakage-controlled biomarker models only when you press Run. Expensive nested cross-validation is no longer repeated on every slider or tab interaction.",
    eyebrow="Step 97 · Responsive, upload-safe translational modelling",
    chips=["Run-on-demand", "Nested CV", "In-fold preprocessing", "95% CI", "Permutation test", "External cohort"],
)
scientific_boundary_banner(
    source_kind="synthetic",
    release_eligible=False,
    message=(
        "Exploratory modelling only. Biomarker claims require prespecified endpoints, a locked pipeline, "
        "genuinely independent cohorts, clinical utility assessment and prospective validation."
    ),
)

source = st.radio(
    "Development cohort",
    ["Deterministic multi-omics demo", "Upload CSV/TSV/Excel"],
    horizontal=True,
)
upload = st.file_uploader(
    "Development table with sample_id, binary outcome and numeric omics features",
    type=["csv", "tsv", "txt", "csv.gz", "tsv.gz", "xlsx", "xlsm", "xls", "ods", "zip"],
    disabled=source.startswith("Deterministic"),
    key="biomarker_development_upload",
)
profile = render_upload_preflight(
    upload,
    key="biomarker_development",
    allowed_extensions=["csv", "tsv", "txt", "csv.gz", "tsv.gz", "xlsx", "xlsm", "xls", "ods", "zip"],
    soft_limit_mb=40,
    hard_limit_mb=350,
)
try:
    data = read_uploaded_table(upload, max_cells=15_000_000) if upload else demo_multiomics()
except Exception as exc:
    st.error(f"Development cohort could not be loaded: {exc}")
    st.stop()

if data.empty or data.shape[1] < 3:
    st.error("The development cohort must contain rows and at least three columns.")
    st.stop()
if len(data) < 20:
    st.error("At least 20 samples are required for nested cross-validation.")
    st.stop()

st.caption(f"Loaded {len(data):,} samples × {data.shape[1]:,} columns")
with st.expander("Preview and schema", expanded=False):
    smart_dataframe(data.head(200), height=330, key="biomarker_development_preview")

with st.form("biomarker_model_settings", clear_on_submit=False):
    cols = st.columns(6)
    outcome = cols[0].selectbox(
        "Outcome",
        data.columns,
        index=data.columns.get_loc("outcome") if "outcome" in data.columns else 0,
    )
    batch = cols[1].selectbox(
        "Batch",
        ["None"] + data.columns.tolist(),
        index=(data.columns.tolist().index("batch") + 1) if "batch" in data.columns else 0,
    )
    model_name = cols[2].selectbox(
        "Model", ["Logistic L1", "Logistic L2", "Random Forest", "Gradient Boosting"]
    )
    outer = cols[3].slider("Outer folds", 2, 8, 3)
    inner = cols[4].slider("Inner folds", 2, 5, 2)
    permutations = cols[5].slider("Null permutations", 0, 200, 20, 10)
    run_model = st.form_submit_button(
        "Run leakage-controlled biomarker analysis",
        type="primary",
        width="stretch",
    )

# A deterministic signature prevents stale results from being shown after inputs change.
data_digest = hashlib.sha256(
    pd.util.hash_pandas_object(data, index=True).values.tobytes()
).hexdigest()
run_signature = hashlib.sha256(
    json.dumps(
        {
            "data": data_digest,
            "outcome": str(outcome),
            "batch": str(batch),
            "model": str(model_name),
            "outer": int(outer),
            "inner": int(inner),
            "permutations": int(permutations),
        },
        sort_keys=True,
    ).encode("utf-8")
).hexdigest()

if run_model:
    try:
        with analysis_run("Running nested cross-validation and uncertainty analysis") as workflow:
            workflow.stage("Validating cohort and outcome", progress=0.12)
            outcome_values = pd.to_numeric(data[outcome], errors="coerce")
            if outcome_values.isna().any() or set(outcome_values.astype(int).unique()) - {0, 1}:
                raise ValueError("The selected outcome must contain only binary values 0 and 1.")
            if batch != "None" and batch == outcome:
                raise ValueError("Outcome and batch must use different columns.")
            workflow.stage("Fitting nested cross-validation pipeline", progress=0.28)
            result = biomarker_model_advanced(
                data,
                outcome,
                None if batch == "None" else batch,
                model_name,
                outer,
                inner,
                permutations,
            )
            workflow.stage("Preparing calibration and feature evidence", progress=0.92)
        st.session_state["biomarker_cached_result"] = result
        st.session_state["biomarker_cached_signature"] = run_signature
    except Exception as exc:
        st.error(f"Model training could not complete: {exc}")

result = st.session_state.get("biomarker_cached_result")
result_signature = st.session_state.get("biomarker_cached_signature")
if result is None or result_signature != run_signature:
    st.info(
        "Configure the analysis and press **Run leakage-controlled biomarker analysis**. "
        "The page no longer launches nested CV automatically during every UI rerun."
    )
    pre_features = [
        column for column in data.select_dtypes(include=[np.number]).columns
        if column != outcome and (batch == "None" or column != batch)
    ]
    render_biomarker_excellence(data, outcome, pre_features, None)
    st.stop()

metrics = result["metrics"]
metric_cards(
    [
        ("Samples", metrics["samples"], None),
        ("Features", metrics["features"], None),
        (
            "ROC-AUC",
            f"{metrics['roc_auc']:.3f}",
            f"95% CI {metrics['roc_auc_ci_low']:.3f}–{metrics['roc_auc_ci_high']:.3f}",
        ),
        (
            "Average precision",
            f"{metrics['average_precision']:.3f}",
            f"95% CI {metrics['ap_ci_low']:.3f}–{metrics['ap_ci_high']:.3f}",
        ),
        ("Balanced accuracy", f"{metrics['balanced_accuracy']:.3f}", None),
        ("Brier", f"{metrics['brier']:.3f}", None),
        (
            "Permutation p",
            f"{metrics['permutation_p']:.3f}"
            if np.isfinite(metrics["permutation_p"])
            else "Not run",
            None,
        ),
        ("Model", metrics["model"], None),
    ]
)

performance_tab, features_tab, predictions_tab, external_tab, reproducibility_tab = st.tabs(
    ["Performance", "Feature evidence", "Predictions", "External validation", "Reproducibility"]
)
with performance_tab:
    c1, c2 = st.columns(2)
    with c1:
        roc = result["roc"]
        fig = px.line(roc, x="fpr", y="tpr", title="Nested-CV ROC curve")
        fig.add_shape(type="line", x0=0, y0=0, x1=1, y1=1, line={"dash": "dash"})
        st.plotly_chart(fig, width="stretch")
    with c2:
        pr = result["pr"]
        st.plotly_chart(
            px.line(pr, x="recall", y="precision", title="Nested-CV precision–recall curve"),
            width="stretch",
        )
    c3, c4 = st.columns(2)
    with c3:
        cal = result["calibration"]
        fig = px.line(
            cal,
            x="predicted_probability",
            y="observed_frequency",
            markers=True,
            title="Calibration",
        )
        fig.add_shape(type="line", x0=0, y0=0, x1=1, y1=1, line={"dash": "dash"})
        st.plotly_chart(fig, width="stretch")
    with c4:
        folds = result["fold_metrics"]
        st.plotly_chart(
            px.box(
                folds.melt(
                    id_vars="fold",
                    value_vars=["roc_auc", "average_precision", "balanced_accuracy"],
                ),
                x="variable",
                y="value",
                points="all",
                title="Outer-fold stability",
            ),
            width="stretch",
        )
    smart_dataframe(result["fold_metrics"], height=280, key="biomarker_fold_metrics")

with features_tab:
    importance = result["importance"].head(40)
    st.plotly_chart(
        px.bar(
            importance.sort_values("importance"),
            x="importance",
            y="feature",
            color="omics_layer",
            error_x="importance_sd",
            orientation="h",
            title="Permutation importance on locked final model",
        ),
        width="stretch",
    )
    smart_dataframe(result["importance"], height=480, key="biomarker_importance_pro")
    st.download_button(
        "Export feature evidence",
        result["importance"].to_csv(index=False).encode(),
        "multiomics_feature_evidence.csv",
        "text/csv",
    )

with predictions_tab:
    predictions = result["predictions"]
    st.plotly_chart(
        px.histogram(
            predictions,
            x="probability",
            color="observed",
            barmode="overlay",
            nbins=25,
            title="Out-of-fold probability distribution",
        ),
        width="stretch",
    )
    smart_dataframe(predictions, height=430, key="biomarker_predictions_pro")
    st.download_button(
        "Export OOF predictions",
        predictions.to_csv(index=False).encode(),
        "multiomics_oof_predictions.csv",
        "text/csv",
    )

with external_tab:
    external_upload = st.file_uploader(
        "Optional independent cohort CSV/TSV/Excel",
        type=["csv", "tsv", "txt", "csv.gz", "tsv.gz", "xlsx", "xlsm", "xls", "ods", "zip"],
        key="external_cohort",
    )
    render_upload_preflight(
        external_upload,
        key="biomarker_external",
        allowed_extensions=["csv", "tsv", "txt", "csv.gz", "tsv.gz", "xlsx", "xlsm", "xls", "ods", "zip"],
        soft_limit_mb=40,
        hard_limit_mb=350,
    )
    if external_upload:
        if st.button("Run external-cohort validation", type="primary", width="stretch"):
            try:
                external = read_uploaded_table(external_upload, max_cells=15_000_000)
                external_outcome = outcome if outcome in external.columns else None
                if external_outcome is None:
                    raise ValueError(
                        f"External cohort is missing the locked outcome column: {outcome}"
                    )
                ext = external_validate_biomarker(
                    result["model"], result["features"], external, external_outcome
                )
                st.session_state["biomarker_external_result"] = ext
            except Exception as exc:
                st.error(f"External validation could not complete: {exc}")
        ext = st.session_state.get("biomarker_external_result")
        if ext:
            metric_cards(
                [
                    ("External samples", ext["samples"], None),
                    ("External ROC-AUC", f"{ext['roc_auc']:.3f}", None),
                    ("External AP", f"{ext['average_precision']:.3f}", None),
                    ("External Brier", f"{ext['brier']:.3f}", None),
                ]
            )
            smart_dataframe(ext["predictions"], height=380, key="external_predictions")
    else:
        st.info(
            "Upload a genuinely independent cohort with the same locked feature columns to evaluate transportability."
        )

with reproducibility_tab:
    reproducibility = {
        "schema": "biointel.biomarker.study.v3",
        "model": metrics["model"],
        "outer_folds": metrics["outer_folds"],
        "inner_folds": metrics["inner_folds"],
        "best_parameters": result["best_parameters"],
        "features": result["features"],
        "input_sha256": profile.sha256 if profile else data_digest,
        "run_signature": run_signature,
        "development_metrics": {
            key: value for key, value in metrics.items() if isinstance(value, (str, int, float))
        },
        "guardrails": [
            "Run-on-demand; no hidden retraining on widget changes",
            "Imputation inside pipeline",
            "Feature selection inside pipeline",
            "Batch correction inside every CV fold",
            "Out-of-fold predictions",
            "Bootstrap confidence intervals",
            "Full pipeline-refit permutation null test",
        ],
    }
    smart_json(reproducibility, key="biomarker_reproducibility")
    st.download_button(
        "Download reproducibility manifest",
        json.dumps(reproducibility, indent=2, default=str).encode(),
        "biomarker_reproducibility_manifest.json",
        "application/json",
        width="stretch",
    )
    insight_callout(
        "Evidence boundary",
        "High internal cross-validation performance is not external validation. Release eligibility requires an independent locked cohort, prespecified acceptance criteria and documented clinical or biological utility.",
        tone="warning",
    )

# Step 99 module excellence layer
render_biomarker_excellence(data, outcome, result["features"], result["predictions"])

# Step 100 professional integration and optimization layer
render_biomarker_professional(data, outcome, result["features"], result["predictions"])

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("multiomics", key_prefix="step110_102_Multi_Omics_Biomarker_Discovery_multiomics")

# Step 115 scientific depth, validation and optimization layer
from biointel.scientific_depth import render_depth_upgrade_panel as _render_step114_depth

_render_step114_depth("multiomics_biomarker_core", None, key_prefix="step114_multiomics_biomarker_core", expanded=False)

# Step 115 non-chart visual: multiomics_canvas
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("multiomics_canvas", key_prefix="step115_102_Multi_Omics_Biomarker_Discovery_multiomics_canvas", expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='multiomics_biomarker', title='Multi-Omics Biomarker Discovery Studio', category='AI Lab')

# Step 183 all-module synthetic demo bundle
from biointel.portfolio_demo_v183.ui import render_step183_portfolio_demo as _render_step183_portfolio_demo
_render_step183_portfolio_demo("multiomics_biomarker_discovery", expanded=False)


# Step 185 operational assurance panel (synthetic/demo boundary preserved)
try:
    from biointel.operational_assurance_v185.ui import render_step185_operational_assurance as _render_step185_operational_assurance
    _render_step185_operational_assurance("multiomics_biomarker_discovery")
except Exception as _step185_exc:
    try:
        import streamlit as st
        st.info(f"Step 185 assurance panel unavailable: {_step185_exc}")
    except Exception:
        pass

# STEP188_MAJOR_MODULE_STANDARD_HOOK
from biointel.major_module_standard_v188.ui import render_step188_major_module_standard as _render_step188_major_module_standard
_render_step188_major_module_standard('multiomics_biomarker_discovery', expanded=False)

# STEP189_UNIVERSAL_PLATFORM_HOOK
from biointel.universal_platform_v189.ui import render_step189_universal_platform as _render_step189_universal_platform
_render_step189_universal_platform('multiomics_biomarker_discovery', expanded=False)

# STEP190_SCIENTIFIC_EXECUTION_HOOK
from biointel.scientific_execution_v190.ui import render_step190_scientific_execution as _render_step190_scientific_execution
_render_step190_scientific_execution('multiomics_biomarker_discovery', expanded=False)

# STEP192_RELEASE_INTEGRITY_PUBLICATION_HOOK
from biointel.release_integrity_v192.ui import render_step192_release_integrity as _render_step192_release_integrity
_render_step192_release_integrity('multiomics_biomarker_discovery', expanded=False)


# STEP193_MANDATORY_COMPLETION_HOOK
from biointel.mandatory_completion_v193.ui import render_step193_mandatory_completion as _render_step193_mandatory_completion
_render_step193_mandatory_completion('multiomics_biomarker_discovery', expanded=False)

