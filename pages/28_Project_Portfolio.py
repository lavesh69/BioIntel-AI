from __future__ import annotations

import html
import json
import sqlite3
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.database.core import managed_connect  # noqa: E402

from biointel.data.dataset_registry import list_datasets
from biointel.portfolio.project_exchange import (
    import_project_bundle,
    project_bundle_json,
)
from biointel.portfolio.project_registry import (
    VALID_STATUSES,
    create_project,
    delete_project,
    list_project_events,
    list_projects,
    portfolio_summary,
    update_project,
)
from biointel.training.model_catalog import sync_model_catalog
from biointel.ui.theme import (
    apply_theme,
    badge,
    executive_kpis,
    hero,
    professional_strip,
)
from biointel.ui.workflow import read_uploaded_text, render_upload_preflight

REGISTRY = ROOT / "reports" / "projects.sqlite3"

st.set_page_config(
    page_title="Project Portfolio · BioIntel AI",
    page_icon="📁",
    layout="wide",
)

apply_theme()

hero(
    "Manage research projects with professional portfolio discipline.",
    (
        "Track objectives, ownership labels, priorities, target dates, "
        "dataset provenance and model linkage without requiring an account."
    ),
    eyebrow="Quality-Hardened · Controlled Project Portfolio",
    chips=[
        "Multi-project",
        "Priority tracking",
        "Dataset linkage",
        "Model linkage",
    ],
)

projects = list_projects(REGISTRY)
summary = portfolio_summary(REGISTRY)

if summary["overdue"]:
    badge(
        f"● {summary['overdue']} overdue project(s)",
        "danger",
    )
elif summary["due_soon"]:
    badge(
        f"● {summary['due_soon']} project target(s) due soon",
        "warning",
    )
else:
    badge("● Portfolio schedule healthy", "success")

executive_kpis(
    [
        (
            "Total projects",
            str(summary["total"]),
            "All locally registered research initiatives",
        ),
        (
            "Active / validation",
            str(summary["active"]),
            "Projects currently progressing",
        ),
        (
            "Critical priority",
            str(summary["critical"]),
            "Projects requiring senior attention",
        ),
        (
            "Overdue",
            str(summary["overdue"]),
            f"{summary['due_soon']} target(s) due within 14 days",
        ),
    ]
)

overview_tab, create_tab, manage_tab, review_tab, exchange_tab = st.tabs(
    [
        "Portfolio overview",
        "Create project",
        "Manage project",
        "Review board",
        "Import / export",
    ]
)

with overview_tab:
    if not projects:
        st.info("No projects registered. Use Create project to add the first initiative.")
    else:
        with managed_connect(REGISTRY) as connection:
            resource_counts = {row[0]: int(row[1]) for row in connection.execute("SELECT project_id,COUNT(*) FROM project_resources GROUP BY project_id")}
        table = pd.DataFrame(
            [
                {
                    "Code": project.project_code,
                    "Project": project.name,
                    "Status": project.status,
                    "Priority": project.priority,
                    "Owner label": project.owner_label or "Not assigned",
                    "Target date": project.target_date,
                    "Dataset linked": bool(project.dataset_sha256),
                    "Model linked": bool(project.model_filename),
                    "Resource links": resource_counts.get(project.project_id, 0),
                    "Updated": project.updated_at_utc,
                }
                for project in projects
            ]
        )
        st.dataframe(
            table,
            width="stretch",
            hide_index=True,
        )

        chart_left, chart_right = st.columns(2)
        with chart_left:
            status_counts = (
                table["Status"].value_counts().rename_axis("Status").reset_index(name="Projects")
            )
            st.plotly_chart(
                px.bar(
                    status_counts,
                    x="Status",
                    y="Projects",
                    title="Portfolio by status",
                ),
                width="stretch",
            )
        with chart_right:
            priority_counts = (
                table["Priority"]
                .value_counts()
                .rename_axis("Priority")
                .reset_index(name="Projects")
            )
            st.plotly_chart(
                px.pie(
                    priority_counts,
                    names="Priority",
                    values="Projects",
                    hole=0.55,
                    title="Portfolio by priority",
                ),
                width="stretch",
            )

        export_left, export_right = st.columns(2)
        export_left.download_button(
            "Download portfolio CSV",
            table.to_csv(index=False),
            "biointel_project_portfolio.csv",
            "text/csv",
            width="stretch",
        )
        export_right.download_button(
            "Download portfolio JSON",
            json.dumps(
                [asdict(project) for project in projects],
                indent=2,
                default=str,
            ),
            "biointel_project_portfolio.json",
            "application/json",
            width="stretch",
        )

with create_tab:
    datasets = list_datasets(ROOT / "reports" / "datasets.sqlite3")
    models = sync_model_catalog(ROOT / "models")

    dataset_options = {
        "No dataset linked": None,
        **{
            (
                f"{item.dataset_name} {item.dataset_version} " f"({item.dataset_sha256[:10]}…)"
            ): item.dataset_sha256
            for item in datasets
        },
    }
    model_options = {
        "No model linked": None,
        **{item.filename: item.filename for item in models if item.state != "archived"},
    }

    with st.form("create_project_form"):
        first, second, third = st.columns(3)
        code = first.text_input(
            "Project code",
            placeholder="BTX-001",
        )
        name = second.text_input(
            "Project name",
            placeholder="Kinase inhibitor validation",
        )
        owner = third.text_input(
            "Owner label",
            placeholder="Research lead / team label",
        )

        status_col, priority_col, date_col = st.columns(3)
        status = status_col.selectbox(
            "Status",
            sorted(VALID_STATUSES),
            index=sorted(VALID_STATUSES).index("Planning"),
        )
        priority = priority_col.selectbox(
            "Priority",
            ["Critical", "High", "Medium", "Low"],
            index=2,
        )
        use_target = date_col.checkbox(
            "Set target date",
            value=False,
        )
        target = date_col.date_input(
            "Target date",
            value=date.today(),
            disabled=not use_target,
        )

        objective = st.text_area(
            "Objective",
            placeholder=(
                "Describe the research question, intended outcome " "and validation goal."
            ),
            height=120,
        )
        tags = st.text_input(
            "Tags",
            placeholder="kinase, oncology, validation",
        )

        dataset_label = st.selectbox(
            "Linked dataset",
            list(dataset_options),
        )
        model_label = st.selectbox(
            "Linked model",
            list(model_options),
        )
        notes = st.text_area(
            "Portfolio notes",
            height=100,
        )
        submitted = st.form_submit_button(
            "Create professional project record",
            type="primary",
        )

    if submitted:
        try:
            created = create_project(
                REGISTRY,
                project_code=code,
                name=name,
                status=status,
                priority=priority,
                objective=objective,
                owner_label=owner,
                tags=tags,
                target_date=(target.isoformat() if use_target else None),
                dataset_sha256=dataset_options[dataset_label],
                model_filename=model_options[model_label],
                notes=notes,
            )
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success(f"Created {created.project_code}: {created.name}")
            st.rerun()

with manage_tab:
    projects = list_projects(REGISTRY)
    if not projects:
        st.info("Create a project before using management controls.")
    else:
        selected_id = st.selectbox(
            "Project",
            [project.project_id for project in projects],
            format_func=lambda project_id: next(
                (
                    f"{project.project_code} · {project.name}"
                    for project in projects
                    if project.project_id == project_id
                ),
                project_id,
            ),
        )
        selected = next(project for project in projects if project.project_id == selected_id)
        with managed_connect(REGISTRY) as connection:
            selected_resources = pd.read_sql_query(
                "SELECT resource_type,resource_id,relation_type,status,notes,created_at_utc FROM project_resources WHERE project_id=? ORDER BY resource_type,relation_type",
                connection,
                params=(selected_id,),
            )
        st.subheader("Scientific resource lineage")
        if selected_resources.empty:
            st.info("No scientific resources are linked to this project yet.")
        else:
            st.dataframe(selected_resources, width="stretch", hide_index=True)

        datasets = list_datasets(ROOT / "reports" / "datasets.sqlite3")
        models = sync_model_catalog(ROOT / "models")
        dataset_values = [None, *[item.dataset_sha256 for item in datasets]]
        model_values = [
            None,
            *[item.filename for item in models if item.state != "archived"],
        ]

        with st.form("update_project_form"):
            first, second, third = st.columns(3)
            code = first.text_input(
                "Project code",
                value=selected.project_code,
            )
            name = second.text_input(
                "Project name",
                value=selected.name,
            )
            owner = third.text_input(
                "Owner label",
                value=selected.owner_label,
            )

            status = st.selectbox(
                "Status",
                sorted(VALID_STATUSES),
                index=sorted(VALID_STATUSES).index(selected.status),
            )
            priority_values = [
                "Critical",
                "High",
                "Medium",
                "Low",
            ]
            priority = st.selectbox(
                "Priority",
                priority_values,
                index=priority_values.index(selected.priority),
            )
            use_target = st.checkbox(
                "Set target date",
                value=selected.target_date is not None,
            )
            target = st.date_input(
                "Target date",
                value=(
                    date.fromisoformat(selected.target_date)
                    if selected.target_date
                    else date.today()
                ),
                disabled=not use_target,
            )

            objective = st.text_area(
                "Objective",
                value=selected.objective,
                height=120,
            )
            tags = st.text_input(
                "Tags",
                value=", ".join(selected.tags),
            )
            dataset_value = st.selectbox(
                "Linked dataset SHA-256",
                dataset_values,
                index=(
                    dataset_values.index(selected.dataset_sha256)
                    if selected.dataset_sha256 in dataset_values
                    else 0
                ),
                format_func=lambda value: ("No dataset linked" if value is None else value),
            )
            model_value = st.selectbox(
                "Linked model",
                model_values,
                index=(
                    model_values.index(selected.model_filename)
                    if selected.model_filename in model_values
                    else 0
                ),
                format_func=lambda value: ("No model linked" if value is None else value),
            )
            notes = st.text_area(
                "Notes",
                value=selected.notes,
                height=100,
            )
            updated = st.form_submit_button(
                "Save project changes",
                type="primary",
            )

        if updated:
            try:
                record = update_project(
                    REGISTRY,
                    selected.project_id,
                    project_code=code,
                    name=name,
                    status=status,
                    priority=priority,
                    objective=objective,
                    owner_label=owner,
                    tags=tags,
                    target_date=(target.isoformat() if use_target else None),
                    dataset_sha256=dataset_value,
                    model_filename=model_value,
                    notes=notes,
                )
            except Exception as exc:
                st.error(str(exc))
            else:
                st.success(f"Updated {record.project_code}")
                st.rerun()

        with st.expander("Project activity history"):
            events = list_project_events(
                REGISTRY,
                project_id=selected.project_id,
            )
            st.dataframe(
                pd.DataFrame([asdict(event) for event in events]),
                width="stretch",
                hide_index=True,
            )

        with st.expander("Delete project record"):
            st.warning(
                "This removes local project metadata and project events. "
                "Datasets and model files are not deleted."
            )
            confirm = st.checkbox(
                f"Confirm deletion of {selected.project_code}",
                key="confirm_project_delete",
            )
            if st.button(
                "Delete project",
                disabled=not confirm,
            ):
                if delete_project(
                    REGISTRY,
                    selected.project_id,
                ):
                    st.success("Project record deleted.")
                    st.rerun()

with review_tab:
    projects = list_projects(
        REGISTRY,
        include_archived=False,
    )
    professional_strip(
        "Portfolio review board",
        (
            "Projects are grouped by lifecycle status and ordered "
            "by priority for structured weekly review."
        ),
    )
    statuses = [
        "Planning",
        "Active",
        "Validation",
        "Paused",
        "Completed",
    ]
    columns = st.columns(len(statuses))
    for column, status_name in zip(
        columns,
        statuses,
        strict=True,
    ):
        with column:
            st.markdown(f"### {status_name}")
            group = [project for project in projects if project.status == status_name]
            if not group:
                st.caption("No projects")
            for project in group:
                st.markdown(
                    f"""
                    <div class="bio-card">
                      <div class="bio-card-title">
                        {html.escape(project.project_code)}
                      </div>
                      <div class="bio-card-copy">
                        {html.escape(project.name)}<br>
                        <strong>{html.escape(project.priority)}</strong><br>
                        {html.escape(project.target_date or "No target date")}
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


with exchange_tab:
    professional_strip(
        "Controlled project exchange",
        (
            "Export one project with milestones, decisions and gates, "
            "or import a validated bundle using a new unique project code."
        ),
    )

    current_projects = list_projects(
        REGISTRY,
        include_archived=True,
    )
    if current_projects:
        export_id = st.selectbox(
            "Project to export",
            [project.project_id for project in current_projects],
            format_func=lambda project_id: next(
                (
                    f"{project.project_code} · {project.name}"
                    for project in current_projects
                    if project.project_id == project_id
                ),
                project_id,
            ),
            key="project_exchange_export_id",
        )
        export_project = next(
            project for project in current_projects if project.project_id == export_id
        )
        st.download_button(
            "Download controlled project bundle",
            project_bundle_json(
                REGISTRY,
                export_id,
            ),
            f"{export_project.project_code}_project_bundle.json",
            "application/json",
            type="primary",
        )
    else:
        st.info("No project is available for export.")

    st.divider()
    uploaded_bundle = st.file_uploader(
        "Import controlled project JSON",
        type=["json"],
        key="project_bundle_import",
    )
    render_upload_preflight(
        uploaded_bundle, key="project_bundle", allowed_extensions=["json"], soft_limit_mb=1, hard_limit_mb=5
    )
    if uploaded_bundle is not None:
        if uploaded_bundle.size > 5 * 1024 * 1024:
            st.error("Project bundle exceeds the 5 MB limit.")
        else:
            try:
                payload = json.loads(read_uploaded_text(uploaded_bundle, encoding="utf-8"))
                source_code = str(
                    payload.get("project", {}).get(
                        "project_code",
                        "IMPORTED",
                    )
                )
            except Exception as exc:
                st.error(f"Could not read project bundle: {exc}")
            else:
                import_code = st.text_input(
                    "New unique project code",
                    value=f"{source_code}-COPY",
                    key="project_bundle_import_code",
                )
                suffix = st.text_input(
                    "Optional project-name suffix",
                    value="(Imported)",
                    key="project_bundle_import_suffix",
                )
                st.caption(
                    "Dataset and model links are preserved as references. "
                    "Missing linked evidence will appear as readiness gaps."
                )
                if st.button(
                    "Import project and governance records",
                    type="primary",
                ):
                    try:
                        imported = import_project_bundle(
                            REGISTRY,
                            payload,
                            project_code=import_code,
                            name_suffix=suffix,
                        )
                    except Exception as exc:
                        st.error(f"Import failed: {exc}")
                    else:
                        st.success(f"Imported {imported.project_code}: {imported.name}")
                        st.rerun()

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='project_portfolio', title='Project Portfolio', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
