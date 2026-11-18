from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.omics.integration import (
    canonical_correlation,
    integrate_omics_advanced,
    integrated_nmf,
    integrated_pca,
)
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe
from biointel.ui.scientific_visuals import render_generic_visual_explorer
from biointel.ui.performance import read_csv_cached
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.workflow import (
    analysis_run,
    read_uploaded_table,
    render_methodology,
    render_upload_preflight,
)

DEMO = ROOT / "data" / "bioinformatics_demo"
st.set_page_config(page_title="Omics Integration Hub · BioIntel AI", page_icon="🔗", layout="wide")
apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("multiomics", key_prefix="step116_66_Omics_Integration_Hub_multiomics_1", expanded=False)
hero(
    "Omics Integration Hub",
    "Integrate two or three numeric omics layers with strict sample-ID validation, matched/unmatched audits, layer weighting, PCA, NMF and canonical-correlation views.",
    eyebrow="BioIntel AI · Multi-omics Workbench",
    chips=["Sample audit", "3-layer support", "Layer weights", "PCA", "NMF", "CCA"],
)
scientific_boundary_banner(
    source_kind="demo_reference",
    release_eligible=False,
    message="Bundled matrices are simulated. Study-level conclusions require modality-specific preprocessing, covariates, batch control and independent validation.",
)
render_methodology(
    method="Strict sample identity validation, configurable joins/imputation, per-layer scaling and complementary latent-factor analyses.",
    assumptions=[
        "Each layer has unique sample IDs.",
        "Rows are samples and remaining columns are numeric features.",
    ],
    limitations=[
        "PCA/NMF/CCA are exploratory and do not replace disease-specific multi-view validation."
    ],
    validation=[
        "Review unmatched samples, missingness, factor stability and layer-specific preprocessing."
    ],
)

section_title("Input matrices", "📥")
columns = st.columns(3)
uploads = {
    "transcriptomics": columns[0].file_uploader(
        "Transcriptomics matrix", type=["csv", "tsv"], key="omics_transcript"
    ),
    "proteomics": columns[1].file_uploader(
        "Proteomics matrix", type=["csv", "tsv"], key="omics_protein"
    ),
    "additional": columns[2].file_uploader(
        "Optional third omics matrix", type=["csv", "tsv"], key="omics_additional"
    ),
}
for name, upload in uploads.items():
    render_upload_preflight(
        upload,
        key=f"omics_{name}",
        allowed_extensions=["csv", "tsv"],
        soft_limit_mb=40,
        hard_limit_mb=200,
    )


def load_frame(upload, fallback: Path | None) -> pd.DataFrame | None:
    if upload:
        return read_uploaded_table(upload)
    return read_csv_cached(fallback) if fallback else None


matrices = {
    "transcriptomics": load_frame(uploads["transcriptomics"], DEMO / "demo_transcriptomics.csv"),
    "proteomics": load_frame(uploads["proteomics"], DEMO / "demo_proteomics.csv"),
}
additional = load_frame(uploads["additional"], None)
if additional is not None:
    matrices["additional"] = additional
matrices = {name: frame for name, frame in matrices.items() if frame is not None}

with st.form("omics_integration_form"):
    sample_columns = {}
    selector_columns = st.columns(len(matrices))
    for index, (name, frame) in enumerate(matrices.items()):
        default = "sample" if "sample" in frame.columns else frame.columns[0]
        sample_columns[name] = selector_columns[index].selectbox(
            f"{name.title()} sample column",
            frame.columns.tolist(),
            index=frame.columns.get_loc(default),
        )
    controls = st.columns(5)
    join = controls[0].selectbox(
        "Sample join",
        ["inner", "outer"],
        format_func=lambda value: "Matched samples only"
        if value == "inner"
        else "Keep all samples",
    )
    missing_label = controls[1].selectbox(
        "Missing values",
        [
            "Median imputation",
            "Zero imputation",
            "Drop incomplete samples",
            "Drop incomplete features",
        ],
    )
    transform_label = controls[2].selectbox(
        "Transformation", ["Z-score", "Log2(x+1) + Z-score", "No scaling"]
    )
    feature_limit = controls[3].number_input("Features per layer", 10, 20000, 1000, 50)
    latent_method = controls[4].selectbox("Primary latent view", ["PCA", "NMF"])
    weight_columns = st.columns(len(matrices))
    weights = {
        name: weight_columns[index].number_input(f"{name.title()} weight", 0.1, 10.0, 1.0, 0.1)
        for index, name in enumerate(matrices)
    }
    components = st.slider("Latent components", 2, 10, 3)
    run = st.form_submit_button("Integrate omics matrices", type="primary", width="stretch")

if not run:
    metric_cards(
        [
            (f"{name.title()} rows", f"{len(frame):,}", f"{frame.shape[1]} columns")
            for name, frame in matrices.items()
        ]
    )
    st.info(
        "Configure sample columns and submit. Duplicate or empty sample IDs are blocked before any merge."
    )
    st.stop()

missing_map = {
    "Median imputation": "median",
    "Zero imputation": "zero",
    "Drop incomplete samples": "drop_samples",
    "Drop incomplete features": "drop_features",
}
transform_map = {"Z-score": "zscore", "Log2(x+1) + Z-score": "log1p_zscore", "No scaling": "none"}
try:
    with analysis_run("Validating sample identity and integrating omics layers"):
        result = integrate_omics_advanced(
            matrices,
            sample_columns=sample_columns,
            join=join,
            missing_policy=missing_map[missing_label],
            transform=transform_map[transform_label],
            feature_limit=int(feature_limit),
            layer_weights=weights,
        )
        if latent_method == "PCA":
            latent = integrated_pca(result.integrated, components=int(components))
            loadings = None
        else:
            latent, loadings = integrated_nmf(result.integrated, components=int(components))
except Exception as exc:
    st.error(f"Integration stopped safely: {exc}")
    st.stop()

metric_cards(
    [
        ("Integrated samples", len(result.integrated), join),
        ("Integrated features", result.integrated.shape[1] - 1, None),
        ("Fully matched samples", len(result.matched_samples), None),
        ("Layers", len(matrices), ", ".join(matrices)),
    ]
)

tabs = st.tabs(
    ["Latent view", "Sample audit", "Layer audit", "CCA", "Integrated matrix", "Exports"]
)
with tabs[0]:
    smart_dataframe(latent, height=360)
    render_generic_visual_explorer(
        latent,
        key="omics_latent_visuals",
        secondary=loadings,
        heading="Integrated latent-space visual analytics",
    )
    component_columns = [
        column
        for column in latent.columns
        if column.startswith("PC") or column.startswith("Factor")
    ]
    if len(component_columns) >= 2:
        st.plotly_chart(
            px.scatter(
                latent,
                x=component_columns[0],
                y=component_columns[1],
                hover_name="sample",
                title=f"Integrated {latent_method} sample map",
            ),
            width="stretch",
        )
    if loadings is not None:
        smart_dataframe(loadings, height=340)
with tabs[1]:
    smart_dataframe(result.sample_audit, height=500)
    missing = result.sample_audit[~result.sample_audit["matched_all_layers"]]
    if not missing.empty:
        st.warning(
            f"{len(missing)} samples are not present in every layer. Review before biological interpretation."
        )
with tabs[2]:
    smart_dataframe(result.layer_summary, height=300)
with tabs[3]:
    if len(matrices) >= 2:
        names = list(matrices)
        try:
            cca_scores, cca_summary = canonical_correlation(
                matrices[names[0]],
                matrices[names[1]],
                left_sample_column=sample_columns[names[0]],
                right_sample_column=sample_columns[names[1]],
                components=min(int(components), 5),
            )
            smart_dataframe(cca_summary, height=240)
            smart_dataframe(cca_scores, height=360)
        except Exception as exc:
            st.info(f"CCA unavailable for these inputs: {exc}")
with tabs[4]:
    smart_dataframe(result.integrated, height=520)
    render_generic_visual_explorer(
        result.integrated,
        key="omics_integrated_matrix_visuals",
        secondary=result.layer_summary,
        heading="Integrated matrix visual analytics",
    )
with tabs[5]:
    st.download_button(
        "Download integrated matrix",
        result.integrated.to_csv(index=False),
        "integrated_omics.csv",
        "text/csv",
        width="stretch",
    )
    st.download_button(
        "Download sample audit",
        result.sample_audit.to_csv(index=False),
        "omics_sample_audit.csv",
        "text/csv",
        width="stretch",
    )
    st.download_button(
        "Download layer audit",
        result.layer_summary.to_csv(index=False),
        "omics_layer_audit.csv",
        "text/csv",
        width="stretch",
    )

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("multiomics", key_prefix="step110_66_Omics_Integration_Hub_multiomics")

# Step 115 non-chart visual: multiomics_canvas
from biointel.ui.non_chart_scientific_visuals import render_non_chart_visual as _render_step115_non_chart
_render_step115_non_chart("multiomics_canvas", key_prefix="step115_66_Omics_Integration_Hub_multiomics_canvas", expanded=False)

# STEP127_SCIENTIFIC_DEPTH_OMICS_INTEGRATION
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('omics_integration', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='omics_integration', title='Omics Integration Hub', category='Bioinformatics')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='omics_integration', title='Omics Integration Hub', category='Bioinformatics')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
