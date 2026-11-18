from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import json

import pandas as pd
import plotly.express as px
import streamlit as st

from biointel.ui.components import metric_cards, scientific_chart_card, scientific_table
from biointel.ui.theme import apply_theme
from biointel.ui.visual_workspace import (
    delete_view,
    evidence_label,
    list_all_annotations,
    list_all_views,
    list_visual_errors,
)
from biointel.ui.workbench import compact_module_header

st.set_page_config(
    page_title="Visual Interaction & Accessibility Workspace · BioIntel AI",
    page_icon="📊",
    layout="wide",
)
apply_theme()
compact_module_header(
    title="Visual Interaction & Accessibility Workspace",
    summary=(
        "Review saved scientific views, compare visual configurations, manage persistent annotations, "
        "inspect visual diagnostics and export an auditable local visual-workspace record."
    ),
    icon="📊",
    category="Scientific Intelligence",
    tags=("Saved views", "Annotations", "Accessibility", "Diagnostics"),
    boundary=(
        "Saved visual configurations preserve presentation and review context. They do not replace "
        "the underlying analysis output, source data or independent scientific validation."
    ),
)

views = list_all_views()
annotations = list_all_annotations()
errors = list_visual_errors()
metric_cards(
    [
        ("Saved views", len(views), "Reusable visual configurations"),
        ("Annotations", len(annotations), "Persistent reviewer observations"),
        ("Visual diagnostics", len(errors), "Captured safe-render errors"),
        ("Evidence-labelled", int(views["evidence_status"].notna().sum()) if not views.empty else 0, "Saved views with source status"),
    ]
)

tab_views, tab_compare, tab_annotations, tab_errors = st.tabs(
    ["Saved views", "Compare", "Annotations", "Diagnostics"]
)

with tab_views:
    if views.empty:
        st.info("No saved views yet. Use **Save, annotate and report** below any scientific visual.")
    else:
        display = views.copy()
        display["Evidence"] = display["evidence_status"].map(evidence_label)
        scientific_table(
            display.drop(columns=["configuration_json", "evidence_status"], errors="ignore"),
            key="visual_workspace_views",
            title="Saved visual configurations",
            search_columns=["name", "module_key", "title", "Evidence"],
            height=430,
            file_name="biointel_saved_visual_views.csv",
        )
        view_id = st.selectbox("Manage saved view", display["view_id"].tolist(), key="visual_workspace_manage")
        selected = display.loc[display["view_id"] == view_id].iloc[0]
        with st.expander("Saved configuration", expanded=False):
            st.code(json.dumps(json.loads(selected["configuration_json"]), indent=2), language="json")
        if st.button("Delete selected saved view", type="secondary", key="visual_workspace_delete"):
            if delete_view(view_id):
                st.success("Saved view deleted. Refreshing workspace…")
                st.rerun()

with tab_compare:
    if len(views) < 2:
        st.info("Save at least two visual views before using the comparison workspace.")
    else:
        left, right = st.columns(2, gap="large")
        labels = {
            row["view_id"]: f"{row['name']} · {row['module_key']} · {row['title']}"
            for _, row in views.iterrows()
        }
        with left:
            left_id = st.selectbox("Left saved view", list(labels), format_func=labels.get, key="visual_compare_left")
        right_options = [item for item in labels if item != left_id]
        with right:
            right_id = st.selectbox("Right saved view", right_options, format_func=labels.get, key="visual_compare_right")
        selected_rows = views.set_index("view_id").loc[[left_id, right_id]].reset_index()
        parsed = []
        for _, row in selected_rows.iterrows():
            config = json.loads(row["configuration_json"])
            parsed.append(
                {
                    "View": row["name"],
                    "Module": row["module_key"],
                    "Chart": row["title"],
                    "Evidence": evidence_label(row["evidence_status"]),
                    "Accessibility": config.get("accessibility_preset", "Standard"),
                    "Selected rows": len(config.get("selected_rows", [])),
                    "Updated": row["updated_at_utc"],
                }
            )
        comparison = pd.DataFrame(parsed)
        scientific_table(
            comparison,
            key="visual_workspace_comparison_table",
            title="Saved-view comparison",
            height=240,
            file_name="biointel_saved_view_comparison.csv",
        )
        chart_data = comparison.melt(
            id_vars=["View"],
            value_vars=["Selected rows"],
            var_name="Metric",
            value_name="Value",
        )
        figure = px.bar(chart_data, x="View", y="Value", color="Metric", barmode="group")
        scientific_chart_card(
            figure,
            title="Saved-view selection comparison",
            interpretation="Compares the number of linked records preserved by the selected visual workspaces.",
            data=chart_data,
            method="Saved visual configuration comparison",
            units="Selected records",
            key="visual_workspace_comparison_chart",
            module_key="visual_workspace",
            evidence_status="reference",
            source_record_count=len(chart_data),
        )

with tab_annotations:
    if annotations.empty:
        st.info("No persistent annotations have been saved.")
    else:
        scientific_table(
            annotations,
            key="visual_workspace_annotations",
            title="Persistent visual annotations",
            search_columns=["module_key", "visual_title", "note", "created_by"],
            height=480,
            file_name="biointel_visual_annotations.csv",
        )

with tab_errors:
    if errors.empty:
        st.success("No visual rendering diagnostics have been recorded.")
    else:
        scientific_table(
            errors,
            key="visual_workspace_errors",
            title="Safe visual diagnostics",
            search_columns=["error_id", "module_key", "chart_key", "error_type", "error_message"],
            height=480,
            file_name="biointel_visual_diagnostics.csv",
        )

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("static_reporting", key_prefix="step110_164_Visual_Interaction_Accessibility_Workspace_static_reporting")
_render_step110_viewer("visual_regression", key_prefix="step110_164_Visual_Interaction_Accessibility_Workspace_visual_regression")

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='visual_interaction_workspace', title='Visual Interaction & Accessibility Workspace', category='Intelligence')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
