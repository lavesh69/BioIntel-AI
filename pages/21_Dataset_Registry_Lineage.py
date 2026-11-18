from __future__ import annotations

import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.database.core import managed_connect  # noqa: E402

from biointel.data.dataset_registry import (
    dataset_record_json,
    delete_dataset_record,
    lineage_edges,
    list_datasets,
    register_dataset,
)
from biointel.data.profiling import profile_dataframe
from biointel.data.readiness import dataset_readiness_rows, platform_readiness_summary

REGISTRY = ROOT / "reports" / "datasets.sqlite3"

from biointel.ui.components import smart_json
from biointel.ui.phase108_visuals import render_phase108_visual_suite  # noqa: E402
from biointel.ui.theme import (
    apply_theme,
    hero,
)
from biointel.ui.workflow import read_uploaded_table, render_upload_preflight

st.set_page_config(
    page_title="Dataset Registry & Lineage · BioIntel AI",
    page_icon="🧾",
    layout="wide",
)

apply_theme()

# STEP116_MODULE_EXPERIENCE_2_TO_9
from biointel.ui.module_experience_2_9 import render_module_experience as _render_step116_module_experience
_render_step116_module_experience("dataset_registry", key_prefix="step116_21_Dataset_Registry_Lineage_dataset_registry_1", expanded=False)
hero("🧾 Dataset Registry & Lineage", "Guided scientific analysis with validated inputs, clear status, professional results and export-ready outputs.", eyebrow="BioIntel AI · Scientific Intelligence for Life Sciences")
st.caption(
    "Register dataset versions by SHA-256 and inspect linked files, samples, QC metrics, column semantics and lineage."
)

register_tab, registry_tab, lineage_tab = st.tabs(["Register and profile", "Registry", "Lineage"])

with register_tab:
    uploaded = st.file_uploader(
        "Upload CSV",
        type=["csv"],
        key="dataset_registry_upload",
    )
    render_upload_preflight(
        uploaded, key="dataset_registry", allowed_extensions=["csv"], soft_limit_mb=100, hard_limit_mb=1024
    )
    if uploaded is None:
        st.info("Upload a CSV to profile and register it.")
    else:
        if uploaded.size > 100 * 1024 * 1024:
            st.warning("This file is within the 1 GB upload limit but exceeds the 100 MB interactive-analysis threshold. Use the Background Job Center for disk-backed profiling.")
            st.stop()
        try:
            dataframe = read_uploaded_table(uploaded)
            profile = profile_dataframe(dataframe)
        except Exception as exc:
            st.error(f"Could not profile CSV: {exc}")
            st.stop()

        columns = st.columns(5)
        columns[0].metric("Rows", profile.row_count)
        columns[1].metric("Columns", profile.column_count)
        columns[2].metric(
            "Duplicate rows",
            profile.duplicate_rows,
        )
        columns[3].metric(
            "Missing cells",
            profile.total_missing_values,
        )
        columns[4].metric(
            "Memory",
            f"{profile.memory_bytes / 1024:.1f} KB",
        )

        if profile.warnings:
            for warning in profile.warnings:
                st.warning(warning)

        profile_tab, outlier_tab, preview_tab = st.tabs(
            ["Column profile", "Numeric outliers", "Preview"]
        )
        profile_tab.dataframe(
            profile.column_profile,
            width="stretch",
            hide_index=True,
        )
        outlier_tab.dataframe(
            profile.numeric_outliers,
            width="stretch",
            hide_index=True,
        )
        preview_tab.dataframe(
            dataframe.head(100),
            width="stretch",
            hide_index=True,
        )

        existing = list_datasets(REGISTRY)
        parent_options = {
            "No parent dataset": None,
            **{
                (
                    f"{record.dataset_name} "
                    f"{record.dataset_version} "
                    f"({record.dataset_sha256[:10]}…)"
                ): record.dataset_sha256
                for record in existing
            },
        }

        with st.form("register_dataset_form"):
            left, middle, right = st.columns(3)
            name = left.text_input(
                "Dataset name",
                value=Path(uploaded.name).stem,
            )
            version = middle.text_input(
                "Dataset version",
                value="1.0",
            )
            task = right.selectbox(
                "Task type",
                [
                    "classification",
                    "regression",
                    "unlabelled",
                ],
            )
            source = st.text_input(
                "Source / provenance",
                value="Local CSV upload",
            )
            activity_type = st.text_input(
                "Activity type, when applicable",
            )
            parent_label = st.selectbox(
                "Parent dataset",
                list(parent_options),
            )
            notes = st.text_area("Notes")
            submitted = st.form_submit_button(
                "Register dataset version",
                type="primary",
            )

        if submitted:
            try:
                record = register_dataset(
                    REGISTRY,
                    dataframe,
                    dataset_name=name,
                    dataset_version=version,
                    task_type=task,
                    source_description=source,
                    activity_type=activity_type or None,
                    parent_sha256=parent_options[parent_label],
                    notes=notes,
                    metadata={
                        "duplicate_rows": profile.duplicate_rows,
                        "missing_fraction": profile.missing_fraction,
                        "memory_bytes": profile.memory_bytes,
                    },
                )
            except Exception as exc:
                st.error(f"Registration failed: {exc}")
            else:
                st.success("Dataset registered: " f"{record.dataset_sha256}")
                st.download_button(
                    "Download dataset registry record",
                    dataset_record_json(record),
                    f"{record.dataset_name}_{record.dataset_version}_record.json",
                    "application/json",
                )

with registry_tab:
    records = list_datasets(REGISTRY)
    readiness_rows = dataset_readiness_rows(ROOT)
    readiness_by_hash = {row["dataset_sha256"]: row for row in readiness_rows}
    readiness_summary = platform_readiness_summary(ROOT)["datasets"]
    coverage_metrics = st.columns(5)
    coverage_metrics[0].metric("Datasets", readiness_summary.get("datasets", 0))
    coverage_metrics[1].metric("With files", readiness_summary.get("with_files", 0))
    coverage_metrics[2].metric("With schema", readiness_summary.get("with_columns", 0))
    coverage_metrics[3].metric("With QC", readiness_summary.get("with_qc", 0))
    coverage_metrics[4].metric("Average readiness", f"{float(readiness_summary.get('average_readiness') or 0):.1f}%")
    if not records:
        st.info("No datasets registered yet.")
    else:
        table = pd.DataFrame(
            [
                {
                    "Name": item.dataset_name,
                    "Version": item.dataset_version,
                    "Task": item.task_type,
                    "Rows": item.row_count,
                    "SHA-256": item.dataset_sha256,
                    "Parent": item.parent_sha256,
                    "Created": item.created_at_utc,
                    "Source": item.source_description,
                    "Files": int(readiness_by_hash.get(item.dataset_sha256, {}).get("file_count") or 0),
                    "Samples": int(readiness_by_hash.get(item.dataset_sha256, {}).get("sample_count") or 0),
                    "QC": int(readiness_by_hash.get(item.dataset_sha256, {}).get("qc_count") or 0),
                    "Readiness": float(readiness_by_hash.get(item.dataset_sha256, {}).get("readiness_score") or 0),
                    "Scientific status": readiness_by_hash.get(item.dataset_sha256, {}).get("scientific_status") or "not calculated",
                }
                for item in records
            ]
        )
        st.dataframe(
            table,
            width="stretch",
            hide_index=True,
        )
        selected_hash = st.selectbox(
            "Inspect dataset",
            [item.dataset_sha256 for item in records],
            format_func=lambda value: next(
                (
                    f"{item.dataset_name} " f"{item.dataset_version} " f"({value[:12]}…)"
                    for item in records
                    if item.dataset_sha256 == value
                ),
                value,
            ),
        )
        selected = next(item for item in records if item.dataset_sha256 == selected_hash)
        smart_json(asdict(selected))
        with managed_connect(REGISTRY) as connection:
            connection.row_factory = sqlite3.Row
            detail_view = st.selectbox(
                "Dataset detail view",
                ["Files", "Samples", "QC metrics", "Column dictionary", "Provenance", "Readiness issues"],
                key="dataset_registry_detail_view",
            )
            detail_queries = {
                "Files": "SELECT * FROM dataset_files WHERE dataset_sha256=? ORDER BY role, relative_path",
                "Samples": "SELECT * FROM dataset_samples WHERE dataset_sha256=? ORDER BY sample_name LIMIT 5000",
                "QC metrics": "SELECT * FROM dataset_qc_metrics WHERE dataset_sha256=? ORDER BY scope, metric_name",
                "Column dictionary": "SELECT * FROM dataset_columns WHERE dataset_sha256=? ORDER BY ordinal_position",
                "Provenance": "SELECT * FROM dataset_provenance WHERE dataset_sha256=? ORDER BY provider, source_type",
                "Readiness issues": "SELECT severity, category, message, resolution_status, created_at_utc FROM dataset_validation_issues WHERE dataset_sha256=? ORDER BY severity, category",
            }
            try:
                detail_rows = [dict(row) for row in connection.execute(detail_queries[detail_view], (selected_hash,)).fetchall()]
            except sqlite3.OperationalError:
                detail_rows = []
            if detail_rows:
                st.dataframe(pd.DataFrame(detail_rows), width="stretch", hide_index=True)
            else:
                st.info("No extended scientific-registry records are available for this dataset.")
        st.download_button(
            "Download registry CSV",
            table.to_csv(index=False),
            "dataset_registry.csv",
            "text/csv",
        )

        with st.expander("Remove registry record"):
            st.warning("This removes metadata only. It does not delete any CSV.")
            confirm = st.checkbox(
                f"Confirm removal of {selected_hash[:12]}…",
                key="confirm_dataset_registry_delete",
            )
            if st.button(
                "Remove dataset record",
                disabled=not confirm,
            ):
                if delete_dataset_record(
                    REGISTRY,
                    selected_hash,
                ):
                    st.success("Registry record removed.")
                    st.rerun()

with lineage_tab:
    records = list_datasets(REGISTRY)
    edges = lineage_edges(REGISTRY)
    if not records:
        st.info("Register datasets to create lineage.")
    else:
        nodes = pd.DataFrame(
            [
                {
                    "Dataset": (f"{item.dataset_name} " f"{item.dataset_version}"),
                    "SHA": item.dataset_sha256[:12],
                    "Parent SHA": (item.parent_sha256[:12] if item.parent_sha256 else "Root"),
                    "Rows": item.row_count,
                    "Task": item.task_type,
                }
                for item in records
            ]
        )
        st.dataframe(
            nodes,
            width="stretch",
            hide_index=True,
        )
        try:
            with managed_connect(REGISTRY) as connection:
                connection.row_factory = sqlite3.Row
                scientific_edges = [dict(row) for row in connection.execute(
                    "SELECT * FROM dataset_links ORDER BY relation_type, source_dataset_sha256"
                ).fetchall()]
        except sqlite3.OperationalError:
            scientific_edges = []
        if scientific_edges:
            st.subheader("Scientific dataset relationships")
            st.dataframe(pd.DataFrame(scientific_edges), width="stretch", hide_index=True)
        if edges:
            edge_table = pd.DataFrame(edges)
            st.dataframe(
                edge_table,
                width="stretch",
                hide_index=True,
            )
            parent_counts = edge_table["parent"].value_counts().reset_index()
            parent_counts.columns = [
                "Parent SHA-256",
                "Child versions",
            ]
            st.plotly_chart(
                px.bar(
                    parent_counts,
                    x="Parent SHA-256",
                    y="Child versions",
                    title="Dataset lineage branches",
                ),
                width="stretch",
            )
        else:
            st.info("All registered datasets are currently root versions.")

# Step 108 Phase 1+2 decision visual workspace
render_phase108_visual_suite("dataset_registry", ROOT, context=locals())

# Step 115 module-specific non-chart workspace: dataset_registry
from biointel.ui.non_chart_scientific_visuals import render_module_non_chart_panel as _render_step115_module_non_chart
_render_step115_module_non_chart("dataset_registry", key_prefix="step115_21_Dataset_Registry_Lineage_dataset_registry", expanded=False)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='dataset_registry', title='Dataset Registry & Lineage', category='Data')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
