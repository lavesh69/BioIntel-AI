from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.automation import (
    DEFAULT_WORKFLOWS,
    list_workflow_runs,
    register_default_workflows,
    resume_workflow_run,
    start_workflow_run,
    update_workflow_step,
    workflow_run_snapshot,
)
from biointel.data.data_packs import (
    data_library_summary,
)
from biointel.intelligence.data_intelligence import (
    all_database_health,
)
from biointel.observability.analytics_store import (
    module_performance,
)
from biointel.ui.navigation import PAGE_BY_KEY
from biointel.ui.theme import (
    apply_theme,
    badge,
    command_bar,
    database_cards,
    feature_card,
    hero,
    section_title,
)
from biointel.utils.workflow_status import (
    build_workflow_status,
)

st.set_page_config(
    page_title="Workflow Dashboard · BioIntel AI",
    page_icon="📍",
    layout="wide",
)

apply_theme()


def _workspace_signature() -> tuple[int, ...]:
    paths = [
        ROOT / "reports" / "analytics.sqlite3",
        ROOT / "reports" / "datasets.sqlite3",
        ROOT / "reports" / "experiments.sqlite3",
        ROOT / "reports" / "projects.sqlite3",
        ROOT / "data" / "complete_data_library" / "manifest.json",
    ]
    return tuple(path.stat().st_mtime_ns if path.is_file() else 0 for path in paths)


@st.cache_data(ttl=60, show_spinner=False)
def _workflow_snapshot(root_text: str, signature: tuple[int, ...]):
    del signature
    root = Path(root_text)
    status = build_workflow_status(root)
    data_library = data_library_summary(root)
    database_health = all_database_health(root)
    performance = pd.DataFrame(
        module_performance(
            root / "reports" / "analytics.sqlite3",
            days=30,
            limit=100,
        )
    )
    return status, data_library, database_health, performance


status, data_library, database_health, performance = _workflow_snapshot(
    str(ROOT), _workspace_signature()
)

hero(
    "Research operations, databases and scientific readiness in one pulse.",
    (
        "Monitor datasets, models, experiments, projects, governance, "
        "database health and module performance—then move directly "
        "to the next evidence-backed action."
    ),
    eyebrow="Quality-Hardened · Professional Workflow Dashboard",
    chips=[
        "12 databases",
        "Scientific readiness",
        "Operational analytics",
        "Release controls",
    ],
)

top = st.columns(6)
top[0].metric(
    "Databases",
    database_health["database_count"],
)
top[1].metric(
    "Datasets",
    status["datasets"]["total"],
)
top[2].metric(
    "Models",
    status["models"]["total"],
)
top[3].metric(
    "Experiments",
    status["experiments"]["total"],
)
top[4].metric(
    "Projects",
    status["projects"]["total"],
)
top[5].metric(
    "Diagnostics",
    status["diagnostics"]["overall"],
)

if status["diagnostics"]["overall"] == "PASS" and database_health["health_percent"] == 100.0:
    badge(
        "● Scientific and database operations healthy",
        "success",
    )
else:
    badge(
        "● Workflow review required",
        "warning",
    )

section_title("Recommended next action", "→")
actions = st.columns(4)
recommendations = [
    (
        "data_intelligence",
        "Search intelligence",
        "Use universal search across knowledge, assets and analytics.",
        "🗄️",
    ),
    (
        "dti_predictor",
        "Run prediction",
        "Use the selected default model for single or batch DTI prediction.",
        "🎯",
    ),
    (
        "report_studio",
        "Create evidence report",
        "Export a printable workspace and model evidence summary.",
        "📝",
    ),
    (
        "release_readiness",
        "Review release controls",
        "Inspect blockers, lineage and approval gates.",
        "🧭",
    ),
]
for column, (
    key,
    title,
    copy,
    icon,
) in zip(actions, recommendations, strict=True):
    with column:
        feature_card(title, copy, icon)
        page = PAGE_BY_KEY[key]
        try:
            st.page_link(
                page.path,
                label=f"Open {page.title}",
                icon=page.icon,
                width="stretch",
            )
        except (KeyError, RuntimeError):
            st.caption(f"Open {page.title} from the sidebar.")

section_title("Database fabric", "🗄️")
professional = database_health["professional_warehouses"]
database_cards(
    [
        {
            "icon": "🧠",
            "title": "Knowledge Warehouse",
            "copy": "Scientific entities, relationships and protocols.",
            "status": ("healthy" if professional["knowledge"]["healthy"] else "review"),
            "stats": [
                (
                    "Entities",
                    f"{professional['knowledge']['summary']['entities']:,}",
                ),
                (
                    "Relations",
                    f"{professional['knowledge']['summary']['relations']:,}",
                ),
                (
                    "Rows",
                    f"{professional['knowledge']['database']['row_count']:,}",
                ),
            ],
        },
        {
            "icon": "📈",
            "title": "Analytics Warehouse",
            "copy": "Module telemetry, data quality and system trends.",
            "status": ("healthy" if professional["analytics"]["healthy"] else "review"),
            "stats": [
                (
                    "Events",
                    f"{professional['analytics']['summary']['run_events']:,}",
                ),
                (
                    "Success",
                    f"{professional['analytics']['summary']['success_rate']:.1f}%",
                ),
                (
                    "Rows",
                    f"{professional['analytics']['database']['row_count']:,}",
                ),
            ],
        },
        {
            "icon": "📚",
            "title": "Asset Warehouse",
            "copy": "Research assets, collections, tags and notes.",
            "status": ("healthy" if professional["assets"]["healthy"] else "review"),
            "stats": [
                (
                    "Assets",
                    f"{professional['assets']['summary']['assets']:,}",
                ),
                (
                    "Tags",
                    f"{professional['assets']['summary']['tags']:,}",
                ),
                (
                    "Rows",
                    f"{professional['assets']['database']['row_count']:,}",
                ),
            ],
        },
    ]
)

section_title("30-day module performance", "📈")
if performance.empty:
    st.info("No analytics data is available.")
else:
    st.dataframe(
        performance.head(20),
        width="stretch",
        hide_index=True,
    )
    st.bar_chart(performance.head(12).set_index("module_title")[["runs"]])

section_title("Scientific portfolios", "◈")
portfolio = st.columns(4)
portfolio[0].metric(
    "Classification datasets",
    status["datasets"]["classification"],
)
portfolio[1].metric(
    "Regression datasets",
    status["datasets"]["regression"],
)
portfolio[2].metric(
    "Active models",
    status["models"]["active"],
)
portfolio[3].metric(
    "Governed projects",
    status["governance"]["projects_with_governance"],
)

packs = data_library["manifest"].get("packs", [])
benchmark = data_library["benchmark"]
section_title("Bundled full-data benchmark", "🚀")
benchmark_columns = st.columns(4)
benchmark_columns[0].metric(
    "Pack rows",
    f"{sum(int(item.get('rows', 0)) for item in packs):,}",
)
benchmark_columns[1].metric(
    "Data packs",
    len(packs),
)
benchmark_columns[2].metric(
    "Benchmark models",
    len(benchmark.get("ranking", [])),
)
benchmark_columns[3].metric(
    "Best classifier",
    benchmark.get(
        "best_models",
        {},
    )
    .get("classification", {})
    .get("model_name", "Not available"),
)

command_bar(
    "Local storage and evidence",
    (
        f"Models: {status['storage']['models_bytes'] / (1024 * 1024):.1f} MB · "
        f"Reports/databases: {status['storage']['reports_bytes'] / (1024 * 1024):.1f} MB · "
        f"External cache: {status['storage']['cache_bytes'] / (1024 * 1024):.1f} MB"
    ),
)


section_title("Resumable workflow automation", "⟳")
st.caption(
    "Start a dependency-aware scientific workflow, complete each gate, and resume safely after a failure or application restart."
)
automation_db = ROOT / "reports" / "workflow_automation.sqlite3"
register_default_workflows(automation_db)

workflow_columns = st.columns([1.8, 1.0])
definition_by_key = {item.key: item for item in DEFAULT_WORKFLOWS}
selected_definition = workflow_columns[0].selectbox(
    "Workflow template",
    options=list(definition_by_key),
    format_func=lambda key: definition_by_key[key].title,
    key="workflow_automation_template",
)
workflow_columns[0].caption(definition_by_key[selected_definition].description)
if workflow_columns[1].button(
    "Start workflow", type="primary", width="stretch", key="workflow_automation_start"
):
    st.session_state["workflow_automation_run_id"] = start_workflow_run(
        automation_db, selected_definition
    )
    st.rerun()

runs = list_workflow_runs(automation_db, limit=50)
if runs:
    run_by_id = {item.run_id: item for item in runs}
    default_run = st.session_state.get("workflow_automation_run_id")
    if default_run not in run_by_id:
        default_run = runs[0].run_id
    run_id = st.selectbox(
        "Active workflow run",
        options=list(run_by_id),
        index=list(run_by_id).index(default_run),
        format_func=lambda value: (
            f"{run_by_id[value].workflow_title} · {run_by_id[value].status} · "
            f"{run_by_id[value].progress_percent:.0f}% · {value}"
        ),
        key="workflow_automation_active_run",
    )
    st.session_state["workflow_automation_run_id"] = run_id
    snapshot = workflow_run_snapshot(automation_db, run_id)
    run_metrics = st.columns(4)
    run_metrics[0].metric("Status", snapshot.status.title())
    run_metrics[1].metric("Progress", f"{snapshot.progress_percent:.0f}%")
    run_metrics[2].metric("Current step", snapshot.current_step or "Complete")
    run_metrics[3].metric("Run ID", snapshot.run_id)
    st.progress(snapshot.progress_percent / 100.0)

    for step in snapshot.steps:
        with st.container(border=True):
            title_columns = st.columns([2.2, 0.9, 0.9, 0.9])
            title_columns[0].markdown(f"**{int(step['ordinal']) + 1}. {step['title']}**")
            title_columns[1].caption(f"Status: `{step['status']}`")
            dependencies = step.get("dependencies") or []
            title_columns[2].caption(
                "Dependencies: " + (", ".join(dependencies) if dependencies else "None")
            )
            page_key = str(step.get("page_key") or "")
            if page_key in PAGE_BY_KEY:
                page = PAGE_BY_KEY[page_key]
                title_columns[3].page_link(
                    page.path, label="Open module", icon=page.icon, width="stretch"
                )
            controls = st.columns(4)
            disabled = step["status"] == "blocked"
            if controls[0].button(
                "Start",
                key=f"workflow_step_start_{run_id}_{step['step_key']}",
                disabled=disabled or step["status"] in {"running", "completed", "skipped"},
                width="stretch",
            ):
                update_workflow_step(automation_db, run_id, step["step_key"], "running")
                st.rerun()
            if controls[1].button(
                "Complete",
                key=f"workflow_step_complete_{run_id}_{step['step_key']}",
                disabled=disabled or step["status"] in {"completed", "skipped"},
                width="stretch",
            ):
                update_workflow_step(automation_db, run_id, step["step_key"], "completed")
                st.rerun()
            if controls[2].button(
                "Mark failed",
                key=f"workflow_step_failed_{run_id}_{step['step_key']}",
                disabled=disabled or step["status"] in {"completed", "skipped"},
                width="stretch",
            ):
                update_workflow_step(
                    automation_db, run_id, step["step_key"], "failed", message="Operator marked this step for review."
                )
                st.rerun()
            if controls[3].button(
                "Skip",
                key=f"workflow_step_skip_{run_id}_{step['step_key']}",
                disabled=disabled or step["status"] in {"completed", "skipped"},
                width="stretch",
            ):
                update_workflow_step(automation_db, run_id, step["step_key"], "skipped")
                st.rerun()
    if snapshot.status == "failed":
        if st.button("Resume failed workflow", width="stretch", key=f"workflow_resume_{run_id}"):
            resume_workflow_run(automation_db, run_id)
            st.rerun()
    st.download_button(
        "Download workflow run snapshot",
        json.dumps(snapshot.to_dict(), indent=2, sort_keys=True, default=str),
        file_name=f"{snapshot.run_id}_workflow_snapshot.json",
        mime="application/json",
        width="stretch",
        key=f"workflow_snapshot_download_{run_id}",
    )
else:
    st.info("No workflow runs exist yet. Start a template to create the first durable run.")

st.download_button(
    "Download professional workflow status JSON",
    json.dumps(
        {
            "workflow": status,
            "databases": database_health,
        },
        indent=2,
        default=str,
    ),
    "biointel_professional_workflow_status.json",
    "application/json",
)

# Step 110 advanced scientific viewers
from biointel.ui.advanced_scientific_viewers import render_embedded_viewer as _render_step110_viewer

_render_step110_viewer("workflow_dag", key_prefix="step110_20_Workflow_Dashboard_workflow_dag")

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='workflow_dashboard', title='Workflow Dashboard', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
