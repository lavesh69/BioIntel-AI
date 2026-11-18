from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.integrations.chembl_dataset import ChEMBLActivityQuery, build_chembl_activity_dataset
from biointel.provenance import create_dataset_manifest, manifest_json
from biointel.ui.components import scientific_boundary_banner, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, hero
from biointel.utils.runtime_cache import read_csv_cached

st.set_page_config(page_title="ChEMBL Dataset Builder · BioIntel AI", page_icon="🧪", layout="wide")

apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("chembl", key_prefix="step116_13_ChEMBL_Dataset_Builder_chembl_1", expanded=False)
hero("🧪 ChEMBL Activity Dataset Builder", "Build assay-context-aware, identity-standardized and replicate-curated activity datasets with multi-component target protection.", eyebrow="BioIntel AI · Discovery Data Curation")
scientific_boundary_banner(source_kind="official_provider", release_eligible=False, message="ChEMBL records are provider evidence, not automatically release-ready training data. Review target components, assay confidence, duplicate measurements, conflicts, licences and leakage-resistant splits.")
st.caption(
    "Official ChEMBL/UniProt requests are cached locally for reliability. "
    "Always review assay provenance before training."
)
recipe_path = ROOT / "data" / "recipes" / "chembl_starter_targets.csv"
recipes = read_csv_cached(recipe_path) if recipe_path.is_file() else pd.DataFrame()

recipe_options = ["Custom target"]
if not recipes.empty:
    recipe_options.extend(
        [f"{row.target_chembl_id} · {row.target_name}" for row in recipes.itertuples(index=False)]
    )

selected_recipe = st.selectbox(
    "Starter target recipe",
    recipe_options,
)
if selected_recipe == "Custom target":
    default_target = "CHEMBL203"
    default_activity = "IC50"
    default_records = 500
else:
    selected_id = selected_recipe.split(" · ", 1)[0]
    recipe_row = recipes.loc[recipes["target_chembl_id"] == selected_id].iloc[0]
    default_target = str(recipe_row["target_chembl_id"])
    default_activity = str(recipe_row["suggested_activity_type"])
    default_records = int(recipe_row["suggested_max_records"])

with st.form("builder"):
    c1, c2, c3 = st.columns(3)
    target = c1.text_input(
        "Target ChEMBL ID",
        default_target,
    )
    activity_options = ["IC50", "Ki", "Kd", "EC50"]
    activity = c2.selectbox(
        "Activity type",
        activity_options,
        index=(
            activity_options.index(default_activity) if default_activity in activity_options else 0
        ),
    )
    task = c3.radio(
        "Task",
        ["regression", "classification"],
        horizontal=True,
    )
    max_records = st.number_input(
        "Max records",
        10,
        10000,
        min(default_records, 10000),
        50,
    )
    threshold = st.number_input(
        "Classification threshold nM",
        0.001,
        value=1000.0,
        disabled=task != "classification",
    )
    override = st.text_area("Optional protein sequence override")
    advanced = st.columns(3)
    component_policy = advanced[0].selectbox(
        "Multi-component target policy",
        ["block", "select", "first_with_warning"],
        help="Block is safest. Select requires a specific UniProt accession.",
    )
    selected_accession = advanced[1].text_input(
        "Selected UniProt accession",
        disabled=component_policy != "select",
    )
    aggregate_replicates = advanced[2].checkbox("Aggregate compound–target replicates", value=True)
    conflict_threshold = st.slider("Conflict threshold (pActivity log units)", 0.25, 3.0, 1.0, 0.25)
    include_context = st.checkbox("Retain assay/context fields", value=True)
    submitted = st.form_submit_button(
        "Build dataset",
        type="primary",
    )
if submitted:
    try:
        result = build_chembl_activity_dataset(
            ChEMBLActivityQuery(
                target,
                activity,
                task,
                float(threshold),
                int(max_records),
                protein_sequence_override=override or None,
                multi_component_policy=component_policy,
                selected_uniprot_accession=selected_accession or None,
                aggregate_replicates=aggregate_replicates,
                conflict_threshold_log_units=float(conflict_threshold),
                include_assay_context=include_context,
            )
        )
        st.session_state["chembl_result"] = result
    except Exception as exc:
        st.error(str(exc))
result = st.session_state.get("chembl_result")
if result:
    a, b, c, d = st.columns(4)
    a.metric("Fetched", result.metadata["fetched_records"])
    b.metric("Accepted", result.metadata["accepted_rows"])
    c.metric("Rejected", result.metadata["rejected_rows"])
    d.metric("Conflicting groups", result.metadata.get("conflicting_groups", 0))
    smart_json(result.metadata)
    t1, t2 = st.tabs(["Dataset", "Rejected"])
    with t1:
        smart_dataframe(result.dataset, height=560)
        if "conflicting_measurements" in result.dataset.columns:
            conflicts = result.dataset[result.dataset["conflicting_measurements"].fillna(False)]
            if not conflicts.empty:
                st.warning(
                    f"{len(conflicts)} aggregated group(s) exceed the configured "
                    "activity-conflict threshold."
                )
                smart_dataframe(conflicts, height=300)
    with t2:
        smart_dataframe(result.rejected, height=360)
    if not result.dataset.empty:
        manifest = create_dataset_manifest(
            result.dataset,
            f"{target}_{activity}",
            "ChEMBL-live",
            source_description="ChEMBL and UniProt",
            activity_type=activity,
        )
        st.download_button(
            "Download dataset CSV",
            result.dataset.to_csv(index=False),
            "chembl_dataset.csv",
            "text/csv",
        )
        st.download_button(
            "Download manifest", manifest_json(manifest), "chembl_manifest.json", "application/json"
        )
st.info(
    "Manual assay, relation, unit, target-component and provenance "
    "review is still required before research model training."
)

# STEP127_SCIENTIFIC_DEPTH_CHEMBL_BUILDER
from biointel.step127.ui import render_step127_upgrade_panel as _render_step127_upgrade_panel
_render_step127_upgrade_panel('chembl_builder', expanded=False)

# Targeted peak-potential assurance for Genomics, Discovery, Omics, Lab and Translational modules.
from biointel.peak_potential.ui import render_peak_session_footer
render_peak_session_footer(page_key='chembl_builder', title='ChEMBL Dataset Builder', category='Discovery')

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='chembl_builder', title='ChEMBL Dataset Builder', category='Discovery')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
