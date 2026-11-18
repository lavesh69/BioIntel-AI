from __future__ import annotations

import html
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.data.data_packs import (
    verify_data_pack_integrity,
)
from biointel.intelligence.data_intelligence import (
    all_database_health,
)
from biointel.ui.navigation import (
    CATEGORIES,
    PAGE_BY_KEY,
    PageDefinition,
    search_pages,
)
from biointel.ui.preferences import (
    save_preferences,
    toggle_favourite,
)
from biointel.ui.theme import (
    apply_theme,
    badge,
    command_bar,
    database_cards,
    empty_state,
    hero,
    section_title,
    session_preferences,
)
from biointel.ui.premium_visuals import svg_icon_html
from biointel.utils.workflow_status import (
    build_workflow_status,
)

st.set_page_config(
    page_title="Command Center · BioIntel AI",
    page_icon=str(ROOT / "assets" / "brand" / "biointel-icon-256.png"),
    layout="wide",
)

apply_theme()
preferences = session_preferences()
status = build_workflow_status(ROOT)
data_integrity = verify_data_pack_integrity(ROOT)
database_health = all_database_health(ROOT)

hero(
    "One command center for every scientific and professional workflow.",
    (
        "Search 43 tools, manage favourites, resume recent work and monitor "
        "database, model, dataset, project and governance readiness."
    ),
    eyebrow="Quality-Hardened · Professional Command Center",
    chips=[
        "Universal tool search",
        "12 databases",
        "Persistent favourites",
        "Live readiness",
    ],
)

badge(
    (
        "● Command workspace fully ready"
        if (
            status["diagnostics"]["overall"] == "PASS"
            and data_integrity["valid"]
            and database_health["health_percent"] == 100.0
        )
        else "● Workspace review required"
    ),
    (
        "success"
        if (
            status["diagnostics"]["overall"] == "PASS"
            and data_integrity["valid"]
            and database_health["health_percent"] == 100.0
        )
        else "warning"
    ),
)


def module_icon(page: PageDefinition, *, size: int = 22) -> str:
    return svg_icon_html(
        page_key=page.key,
        category=page.category,
        title=page.title,
        hint=page.icon,
        size=size,
        css_class="bio-svg-icon bio-command-module-icon",
    )


def module_heading(page: PageDefinition) -> str:
    return f"{module_icon(page)} {html.escape(page.title)}"


def safe_page_link(page: PageDefinition) -> None:
    try:
        st.page_link(
            page.path,
            label=f"Open {page.title}",
            width="stretch",
        )
    except (KeyError, RuntimeError):
        st.caption(f"Open {page.title} from the sidebar.")


def persist_favourites(updated) -> None:
    st.session_state["ui_favourites"] = list(updated.favourites)
    save_preferences(ROOT, updated)


section_title("Readiness control plane", "◎")
checks = [
    (
        "Diagnostics",
        status["diagnostics"]["overall"] == "PASS",
        "Dependencies and registered models pass.",
    ),
    (
        "Data integrity",
        data_integrity["valid"],
        (f"{data_integrity['checked_files']} data files " "match their manifest."),
    ),
    (
        "Database fabric",
        database_health["health_percent"] == 100.0,
        (
            f"{database_health['healthy_count']}/"
            f"{database_health['database_count']} systems healthy."
        ),
    ),
    (
        "Datasets",
        status["datasets"]["total"] > 0,
        f"{status['datasets']['total']} registered versions.",
    ),
    (
        "Models",
        status["models"]["total"] > 0,
        f"{status['models']['total']} trusted artifacts.",
    ),
    (
        "Default model",
        bool(status["models"]["default"]),
        status["models"]["default"] or "Not selected.",
    ),
    (
        "Experiments",
        status["experiments"]["total"] > 0,
        f"{status['experiments']['total']} experiment records.",
    ),
    (
        "Governance",
        status["governance"]["projects_with_governance"] > 0,
        (f"{status['governance']['projects_with_governance']} " "governed projects."),
    ),
]
completed = sum(done for _, done, _ in checks)
st.progress(completed / len(checks))
st.caption(f"{completed}/{len(checks)} readiness controls satisfied")

for start in range(0, len(checks), 4):
    columns = st.columns(4)
    for column, (
        title,
        done,
        copy,
    ) in zip(
        columns,
        checks[start : start + 4],
        strict=False,
    ):
        with column:
            st.markdown(
                f"""
                <div class="bio-card">
                  <div class="bio-card-icon">
                    {"✓" if done else "○"}
                  </div>
                  <div class="bio-card-title">
                    {title}
                  </div>
                  <div class="bio-card-copy">
                    {copy}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

section_title("Database intelligence", "🗄️")
professional = database_health["professional_warehouses"]
database_cards(
    [
        {
            "icon": "🧠",
            "title": "Knowledge",
            "copy": "Entities, relations and protocols.",
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
                    "Protocols",
                    professional["knowledge"]["summary"]["protocols"],
                ),
            ],
        },
        {
            "icon": "📈",
            "title": "Observability",
            "copy": "Performance, quality and alert history.",
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
                    "P95",
                    f"{professional['analytics']['summary']['p95_duration_ms']:.0f} ms",
                ),
            ],
        },
        {
            "icon": "📚",
            "title": "Assets",
            "copy": "Files, models, reports, notes and favourites.",
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
                    "Notes",
                    f"{professional['assets']['summary']['notes']:,}",
                ),
            ],
        },
    ]
)

section_title("Integrated live services", ":material/hub:")
integration_keys = (
    "lab_pdf_notebook_rag",
    "live_clinical_trials",
    "system_health_connectivity_weather",
    "engine_license_compliance",
)
for column, key in zip(st.columns(4), integration_keys, strict=True):
    page = PAGE_BY_KEY[key]
    with column:
        with st.container(border=True, height="stretch"):
            st.markdown(f"### {module_heading(page)}", unsafe_allow_html=True)
            st.caption(page.category)
            st.write(page.description)
            safe_page_link(page)
section_title("Search the workspace", "🔎")
command_bar(
    "Tool discovery",
    ("Search by scientific task, database, workflow, governance " "control or operational action."),
)
search_left, search_middle, search_right = st.columns([3, 1.3, 1.1])
query = search_left.text_input(
    "Search tools",
    placeholder=("Try: database, sequence, model, report, " "knowledge, analytics, governance…"),
)
category = search_middle.selectbox(
    "Category",
    ["All", *CATEGORIES],
)
favourites_only = search_right.toggle(
    "Favourites only",
    value=False,
)

favourite_set = set(preferences.favourites)
results = search_pages(
    query=query,
    category=category,
    favourites=favourite_set,
)
if favourites_only:
    results = [page for page in results if page.key in favourite_set]

st.caption(f"{len(results)} tool" f"{'s' if len(results) != 1 else ''} found")
if not results:
    empty_state(
        "No matching tools",
        "Try a broader search or clear the category filter.",
        "🔎",
    )
else:
    for start in range(0, len(results), 3):
        columns = st.columns(3)
        for column, page in zip(
            columns,
            results[start : start + 3],
            strict=False,
        ):
            with column:
                with st.container(border=True):
                    title_columns = st.columns([4, 1])
                    title_columns[0].markdown(f"### {module_heading(page)}", unsafe_allow_html=True)
                    is_favourite = page.key in favourite_set
                    if title_columns[1].button(
                        "★" if is_favourite else "☆",
                        key=f"fav_{page.key}",
                        help=("Remove from favourites" if is_favourite else "Add to favourites"),
                    ):
                        updated = toggle_favourite(
                            session_preferences(),
                            page.key,
                        )
                        persist_favourites(updated)
                        st.rerun()
                    st.caption(page.category)
                    st.write(page.description)
                    safe_page_link(page)

section_title("Continue recent work", "↻")
recent_keys = [
    key for key in preferences.recent_pages if key in PAGE_BY_KEY and key != "command_center"
][:6]
if not recent_keys:
    empty_state(
        "No recent tools yet",
        "Open a module and it will appear here.",
        "↻",
    )
else:
    columns = st.columns(3)
    for index, page_key in enumerate(recent_keys):
        page = PAGE_BY_KEY[page_key]
        with columns[index % 3]:
            feature = st.container(border=True)
            with feature:
                st.markdown(f"### {module_heading(page)}", unsafe_allow_html=True)
                st.caption(page.category)
                st.write(page.description)
                safe_page_link(page)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='command_center', title='Command Center', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
