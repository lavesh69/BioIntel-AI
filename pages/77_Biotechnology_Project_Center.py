from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.portfolio.project_registry import list_projects  # noqa: E402
from biointel.projects.catalog import PROJECT_CATALOG  # noqa: E402
from biointel.projects.portfolio import ensure_biotechnology_projects  # noqa: E402
from biointel.projects.run_registry import compare_runs, list_runs  # noqa: E402
from biointel.ui.components import scientific_boundary_banner, smart_dataframe  # noqa: E402
from biointel.ui.navigation import PAGE_BY_KEY  # noqa: E402
from biointel.ui.theme import apply_theme, badge, feature_card, hero, section_title  # noqa: E402

REGISTRY = ROOT / "reports" / "projects.sqlite3"
RUN_REGISTRY = ROOT / "reports" / "biotechnology_project_runs.sqlite3"

st.set_page_config(page_title="Biotechnology Project Center · BioIntel AI", page_icon="🧪", layout="wide")
apply_theme()

hero(
    "Biotechnology Project Center",
    "Operate five full-depth biotechnology and bioinformatics workbenches with advanced scientific diagnostics, quality gates, method cards, HTML reports, persistent run history and checksum-bound reproducibility bundles.",
    eyebrow="BioIntel AI · Professional Biotechnology Platform",
    chips=["5 deep workbenches", "Quality gates", "Run registry", "HTML reports", "Method cards"],
)
scientific_boundary_banner(
    source_kind="demo_reference",
    release_eligible=False,
    message=(
        "The bundled project datasets are deterministic demonstration assets. The workflows are implementation-ready, "
        "but biological, diagnostic or clinical conclusions require validated real data, external controls and domain review."
    ),
)

ensure_biotechnology_projects(REGISTRY)
registered = {project.project_code: project for project in list_projects(REGISTRY)}
active_count = sum(code in registered for code in [project.code for project in PROJECT_CATALOG])
if active_count == len(PROJECT_CATALOG):
    badge("● All five biotechnology projects are registered in the portfolio", "success")
else:
    badge(f"● {active_count}/{len(PROJECT_CATALOG)} biotechnology projects are registered", "warning")

section_title("Project portfolio", "🧭")
for row_start in range(0, len(PROJECT_CATALOG), 3):
    columns = st.columns(3)
    for column, project in zip(columns, PROJECT_CATALOG[row_start : row_start + 3], strict=False):
        with column:
            feature_card(project.short_title, project.objective, project.icon)
            record = registered.get(project.code)
            st.caption(
                f"{project.code} · {record.status if record else 'Module ready'} · "
                f"{record.priority if record else 'High'} priority"
            )
            page = PAGE_BY_KEY[project.key]
            try:
                st.page_link(page.path, label="Open project workbench", width="stretch")
            except (KeyError, RuntimeError):
                st.info(f"{page.title} — open it from the application navigation.")

section_title("End-to-end delivery model", "▦")
workflow_rows = []
for project in PROJECT_CATALOG:
    workflow_rows.append(
        {
            "Project": project.short_title,
            "Domain": project.domain,
            "Stage 1": project.workflow[0],
            "Stage 2": project.workflow[1],
            "Stage 3": project.workflow[2],
            "Stage 4": project.workflow[3],
            "Primary outputs": " · ".join(project.deliverables),
        }
    )
smart_dataframe(pd.DataFrame(workflow_rows), height=360)

section_title("Analysis run registry", "◴")
runs = list_runs(RUN_REGISTRY, limit=100)
if runs.empty:
    st.info("No deep-workbench runs are registered yet. Complete any project analysis to create a checksum-bound run record.")
else:
    display_runs = runs.copy()
    display_runs["parameters"] = display_runs["parameters"].map(lambda value: ", ".join(f"{key}={item}" for key, item in list(value.items())[:5]))
    display_runs["metrics"] = display_runs["metrics"].map(lambda value: ", ".join(f"{key}={item}" for key, item in list(value.items())[:5]))
    metric_columns = st.columns(4)
    metric_columns[0].metric("Registered runs", f"{len(runs):,}")
    metric_columns[1].metric("Projects represented", f"{runs['project_code'].nunique():,}")
    metric_columns[2].metric("Mean quality score", f"{runs['quality_score'].mean():.1f}")
    metric_columns[3].metric("Blocked runs", f"{int((runs['status'] == 'blocked').sum()):,}")
    smart_dataframe(display_runs, height=390)
    selected_project = st.selectbox("Compare historical runs", [project.code for project in PROJECT_CATALOG], key="biotech_run_compare")
    comparison = compare_runs(RUN_REGISTRY, project_code=selected_project, limit=20)
    if comparison.empty:
        st.caption("No runs registered for this project yet.")
    else:
        smart_dataframe(comparison, height=320)

section_title("Professional deep-development standard", "◆")
smart_dataframe(
    pd.DataFrame(
        [
            ("Scientific core", "Advanced project-specific diagnostics beyond the primary analysis result"),
            ("Validation", "Stability, uncertainty, OOD, sensitivity or permutation evidence appropriate to each domain"),
            ("Quality gates", "Structured pass/review/block evidence with explicit recommendations"),
            ("Reproducibility", "Schema-v2 manifest, environment profile and SHA-256 input/output lineage"),
            ("Reporting", "Portable HTML research report, method/model card, CSV outputs and verified ZIP bundle"),
            ("Operations", "Persistent run registry, historical comparison and API-visible project catalogue"),
            ("Boundary", "No software-generated result is presented as experimental, diagnostic or clinical proof"),
        ],
        columns=["Layer", "Implementation"],
    ),
    height=330,
)

section_title("Professional project controls", "✓")
controls = pd.DataFrame(
    [
        ("Input validation", "Implemented", "Required columns, numeric ranges, sequence alphabets and minimum sample sizes are checked."),
        ("Demo/reference labelling", "Implemented", "Bundled assets are clearly separated from real scientific evidence."),
        ("Reproducible parameters", "Implemented", "Thresholds, random seeds and model choices are explicit in every workbench."),
        ("Result visualisation", "Implemented", "Quality, embeddings, rankings, pathways, diversity and model metrics use structured views."),
        ("Exportable outputs", "Implemented", "CSV tables, schema-v2 JSON manifests, HTML reports, method cards and verified project ZIP bundles are available."),
        ("Deep scientific assurance", "Implemented", "Project-specific uncertainty, stability, OOD, sensitivity, permutation or dispersion diagnostics are included."),
        ("Run history", "Implemented", "Checksum-bound analyses are stored in a local SQLite run registry with historical comparison."),
        ("Equal-depth interaction design", "Implemented", "Each workbench includes multi-stage inputs, advanced QC, interactive analytics, interpretation views and reproducibility metadata."),
        ("Scientific release gate", "Required", "Real-data validation, expert review and independent confirmation remain external requirements."),
    ],
    columns=["Control", "Status", "Evidence"],
)
smart_dataframe(controls, height=330)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='biotechnology_projects', title='Biotechnology Project Center', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
