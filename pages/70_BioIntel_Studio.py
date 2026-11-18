from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.intelligence.data_intelligence import all_database_health  # noqa: E402
from biointel.operations.executive_summary import build_executive_summary  # noqa: E402
from biointel.projects.catalog import PROJECT_CATALOG  # noqa: E402
from biointel.quality.scorecard import build_quality_scorecard  # noqa: E402
from biointel.ui.components import scientific_boundary_banner  # noqa: E402
from biointel.ui.navigation import PAGE_BY_KEY, WORKFLOW_GROUPS  # noqa: E402
from biointel.ui.product_experience_v8 import module_tiles, render_product_hero  # noqa: E402
from biointel.ui.theme import (  # noqa: E402
    apply_theme,
    badge,
    hero,
    insight_callout,
    section_title,
)

st.set_page_config(page_title="BioIntel Studio · BioIntel AI", page_icon="✨", layout="wide")
apply_theme()


@st.cache_data(ttl=60, show_spinner=False)
def _snapshot(root_text: str) -> dict[str, object]:
    root = Path(root_text)
    return {
        "health": all_database_health(root),
        "executive": build_executive_summary(root),
        "quality": build_quality_scorecard(root),
    }


def _page_button(key: str, label: str | None = None) -> None:
    page = PAGE_BY_KEY.get(key)
    if not page:
        return
    try:
        st.page_link(page.path, label=label or page.title, width="stretch")
    except Exception:
        st.caption(label or page.title)


data = _snapshot(str(ROOT))
health = data["health"]
executive = data["executive"]
quality = data["quality"]
risk_counts = executive.get("risk_counts", {}) if isinstance(executive, dict) else {}
critical = int(risk_counts.get("critical", 0) or 0)

render_product_hero(
    "studio",
    "BioIntel Studio",
    "A scientific command cockpit for research data, models, bioinformatics tools, evidence review and production checks.",
    chips=(
        f"{health.get('healthy_count', 0)}/{health.get('database_count', 0)} databases healthy",
        "Evidence-gated release",
        "Guided workflow layout",
        f"Quality diagnostic {float(quality['overall_score']):.1f}/10",
    ),
)
module_tiles((
    ("DISCOVER", "Research intelligence", "Search connected providers, literature and curated evidence sources."),
    ("ANALYSE", "Bioinformatics workbenches", "Run domain-specific QC, analysis, visualisation and interpretation."),
    ("VALIDATE", "Quality and assurance", "Review leakage, external validation, governance and release blockers."),
    ("PUBLISH", "Evidence packages", "Build checksum-bound reports, exports and reproducible scientific bundles."),
))

if critical:
    badge(f"● {critical} critical release risk(s) need review", "danger")
else:
    badge("● Workspace software layer ready · scientific release remains evidence-gated", "success")

scientific_boundary_banner(
    source_kind="demo_reference",
    release_eligible=False,
    message=(
        "This Studio view intentionally separates working software readiness from scientific release readiness. "
        "Synthetic/demo assets remain useful for testing UI and pipelines, but real imported evidence is required before publication-grade claims."
    ),
)

section_title("Start here", "✨")
cols = st.columns(4)
start_cards = [
    ("1", "Measure quality", "See evidence-based scores, hard blockers and the real improvement roadmap.", "platform_quality"),
    ("2", "Add verified data", "Register provenance and curate external evidence before training or release.", "dataset_registry"),
    ("3", "Run analysis", "Use guided bioinformatics, chemistry and DTI tools from one place.", "quick_start"),
    ("4", "Validate release", "Review leakage, external validation, governance and export gates.", "scientific_release_gate"),
]
for col, (step, title, body, page_key) in zip(cols, start_cards):
    with col:
        st.markdown(
            f"""
            <div class='bio-card'>
                <div class='bio-card-kicker'>STEP {step}</div>
                <div class='bio-card-title'>{title}</div>
                <div class='bio-card-copy'>{body}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _page_button(page_key, "Open")

section_title("Applied biotechnology projects", "🧪")
st.caption("Launch five equal-depth workbenches with advanced QC, analytics, interpretation and checksum-bound project bundles.")
for row_start in range(0, len(PROJECT_CATALOG), 3):
    project_columns = st.columns(3)
    for column, project in zip(project_columns, PROJECT_CATALOG[row_start : row_start + 3], strict=False):
        with column:
            st.markdown(
                f"""
                <div class='bio-card'>
                    <div class='bio-card-kicker'>{project.code}</div>
                    <div class='bio-card-title'>{project.icon} {project.short_title}</div>
                    <div class='bio-card-copy'>{project.objective}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            _page_button(project.key, "Launch project")

section_title("Connected research intelligence", "🌐")
connected_columns = st.columns(3)
connected_cards = [
    ("BioIntel Copilot", "Free Ollama + SearXNG web AI, official scientific providers and optional OpenAI.", "biointel_copilot"),
    ("Connected Data Explorer", "Federated search across NCBI, UniProt, PubChem, RCSB, ChEMBL and more.", "connected_data_explorer"),
    ("Provider Integration Center", "Free Web AI, Ollama, SearXNG, provider health, optional OpenAI and provenance.", "provider_integration_center"),
]
for column, (title, body, page_key) in zip(connected_columns, connected_cards):
    with column:
        st.markdown(
            f"""
            <div class='bio-card'>
                <div class='bio-card-title'>{title}</div>
                <div class='bio-card-copy'>{body}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _page_button(page_key, "Open")

section_title("Category workspace", "🧭")
left, right = st.columns([1.15, 0.85])
with left:
    tabs = st.tabs(list(WORKFLOW_GROUPS.keys()))
    for tab, (_, keys) in zip(tabs, WORKFLOW_GROUPS.items()):
        with tab:
            grid = st.columns(2)
            for idx, key in enumerate(keys):
                page = PAGE_BY_KEY.get(key)
                if not page:
                    continue
                with grid[idx % 2]:
                    st.markdown(
                        f"""
                        <div class='bio-card'>
                            <div class='bio-card-title'>{page.icon} {page.title}</div>
                            <div class='bio-card-copy'>{page.description}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    _page_button(key, "Launch")
with right:
    st.markdown("#### Software health")
    st.metric("Databases", f"{health.get('healthy_count', 0)}/{health.get('database_count', 0)}")
    st.metric("Indexed rows", f"{int(health.get('total_rows', 0) or 0):,}")
    st.metric("Indices", f"{int(health.get('total_indices', 0) or 0):,}")
    insight_callout(
        "Clean UI rule",
        "Use the category tabs for daily work, the top-centre finder for any module, and the right-side settings area for interface controls.",
        "info",
    )

section_title("Priority fix board", "🧩")
blockers = list(quality.get("blockers", []))[:8]
fixes = pd.DataFrame(
    [
        [
            item.get("dimension", "Quality gap"),
            "External evidence" if item.get("requires_external_data") else "Engineering",
            item.get("action", "Review the quality center."),
        ]
        for item in blockers
    ],
    columns=["Area", "Dependency", "Action"],
)
st.dataframe(
    fixes,
    width="stretch",
    hide_index=True,
    column_config={
        "Area": st.column_config.TextColumn("Area", width="medium"),
        "Dependency": st.column_config.TextColumn("Dependency", width="small"),
        "Action": st.column_config.TextColumn("Action", width="large"),
    },
)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='biointel_studio', title='BioIntel Studio', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)

# Phase 21 Studio bridge: persistent education/scientific production is appended to the existing command cockpit.
from biointel.education.phase17_22.ui import render_studio_education_workspace as _render_studio_education_workspace
_render_studio_education_workspace(ROOT)
