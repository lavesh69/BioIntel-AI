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

from biointel.intelligence.data_intelligence import (
    all_database_health,
    backup_all_databases,
    export_all_databases_json,
    optimize_all_databases,
    universal_search,
)
from biointel.ui.components import smart_json
from biointel.ui.navigation import PAGE_BY_KEY
from biointel.ui.theme import (
    apply_theme,
    badge,
    command_bar,
    database_cards,
    executive_kpis,
    hero,
    insight_callout,
    professional_strip,
    section_title,
)

st.set_page_config(
    page_title="Data Intelligence Hub · BioIntel AI",
    page_icon="🗄️",
    layout="wide",
)

apply_theme()
health = all_database_health(ROOT)
databases = health["databases"]
professional = health["professional_warehouses"]

hero(
    "Eight databases. One connected research operating layer.",
    (
        "Search knowledge, inspect assets, monitor performance and manage "
        "all indexed local databases from a unified professional command hub."
    ),
    eyebrow="Quality-Hardened · Data Intelligence Hub",
    chips=[
        "3 new warehouses",
        f"{health['total_rows']:,} indexed rows",
        f"{health['total_indices']} indices",
        "WAL + integrity checks",
    ],
)

badge(
    (
        "● All database systems healthy"
        if health["healthy_count"] == health["database_count"]
        else "● Database review required"
    ),
    "success" if health["healthy_count"] == health["database_count"] else "warning",
)

professional_strip(
    "Professional database fabric",
    (
        f"{health['database_count']} SQLite systems · "
        f"{health['health_percent']:.0f}% integrity · "
        f"{health['total_bytes'] / (1024 * 1024):.2f} MB indexed metadata"
    ),
)

executive_kpis(
    [
        (
            "Database systems",
            str(health["database_count"]),
            "Three registries, three warehouses and one download registry",
        ),
        (
            "Indexed rows",
            f"{health['total_rows']:,}",
            "Cross-database searchable operational records",
        ),
        (
            "Indices",
            f"{health['total_indices']:,}",
            "Targeted query and lineage acceleration",
        ),
        (
            "Health",
            f"{health['health_percent']:.0f}%",
            "PRAGMA integrity and WAL readiness",
        ),
    ]
)

section_title("Professional warehouses", "🗄️")
knowledge_summary = professional["knowledge"]["summary"]
analytics_summary = professional["analytics"]["summary"]
asset_summary = professional["assets"]["summary"]

database_cards(
    [
        {
            "icon": "🧠",
            "title": "Research Knowledge Warehouse",
            "copy": (
                "Entities, DTI relationships, protocols, models, datasets "
                "and full-text research search."
            ),
            "status": ("healthy" if professional["knowledge"]["healthy"] else "review"),
            "stats": [
                ("Entities", f"{knowledge_summary['entities']:,}"),
                ("Relations", f"{knowledge_summary['relations']:,}"),
                ("Protocols", f"{knowledge_summary['protocols']:,}"),
            ],
        },
        {
            "icon": "📈",
            "title": "Analytics & Observability",
            "copy": (
                "Run telemetry, performance trends, quality snapshots, "
                "system samples and operational alerts."
            ),
            "status": ("healthy" if professional["analytics"]["healthy"] else "review"),
            "stats": [
                ("Events", f"{analytics_summary['run_events']:,}"),
                ("Success", f"{analytics_summary['success_rate']:.1f}%"),
                ("Alerts", f"{analytics_summary['alerts']:,}"),
            ],
        },
        {
            "icon": "📚",
            "title": "Research Assets & Collections",
            "copy": (
                "Searchable files, models, reports, datasets, bookmarks, "
                "tags, notes and executive favourites."
            ),
            "status": ("healthy" if professional["assets"]["healthy"] else "review"),
            "stats": [
                ("Assets", f"{asset_summary['assets']:,}"),
                ("Tags", f"{asset_summary['tags']:,}"),
                ("Notes", f"{asset_summary['notes']:,}"),
            ],
        },
    ]
)

search_tab, health_tab, operations_tab = st.tabs(
    [
        "Universal Search",
        "Database Health",
        "Operations & Export",
    ]
)

with search_tab:
    command_bar(
        "Cross-database search",
        "Search knowledge entities, research assets and analytics modules together.",
    )
    query = st.text_input(
        "Search all professional databases",
        value="extra trees",
        placeholder="Try: model, sequence, 5X, governance, report, EGFR…",
    )
    limit = st.slider(
        "Results per source",
        min_value=5,
        max_value=100,
        value=25,
        step=5,
    )

    if query.strip():
        results = universal_search(
            ROOT,
            query,
            limit_per_source=limit,
        )
        count_columns = st.columns(3)
        count_columns[0].metric(
            "Knowledge results",
            results["counts"]["knowledge"],
        )
        count_columns[1].metric(
            "Asset results",
            results["counts"]["assets"],
        )
        count_columns[2].metric(
            "Analytics results",
            results["counts"]["analytics"],
        )

        knowledge_tab, assets_tab, analytics_tab = st.tabs(["Knowledge", "Assets", "Analytics"])
        with knowledge_tab:
            frame = pd.DataFrame(results["knowledge"])
            if frame.empty:
                st.info("No matching knowledge entities.")
            else:
                display = frame[
                    [
                        column
                        for column in [
                            "entity_type",
                            "name",
                            "summary",
                            "status",
                            "confidence",
                            "source",
                        ]
                        if column in frame.columns
                    ]
                ]
                st.dataframe(
                    display,
                    width="stretch",
                    hide_index=True,
                )
        with assets_tab:
            frame = pd.DataFrame(results["assets"])
            if frame.empty:
                st.info("No matching research assets.")
            else:
                display = frame[
                    [
                        column
                        for column in [
                            "asset_type",
                            "title",
                            "path",
                            "status",
                            "size_bytes",
                            "is_favourite",
                        ]
                        if column in frame.columns
                    ]
                ]
                st.dataframe(
                    display,
                    width="stretch",
                    hide_index=True,
                )
        with analytics_tab:
            frame = pd.DataFrame(results["analytics"])
            if frame.empty:
                st.info("No matching analytics modules or events.")
            else:
                st.dataframe(
                    frame,
                    width="stretch",
                    hide_index=True,
                )
    else:
        insight_callout(
            "Search across the complete research workspace",
            (
                "Use one query to discover models, datasets, compounds, "
                "targets, reports, modules and operational evidence."
            ),
            "🔎",
        )

with health_tab:
    section_title("All six database systems", "✓")
    health_rows = []
    for key, value in databases.items():
        health_rows.append(
            {
                "Database": key.title(),
                "Integrity": value["integrity"],
                "Journal": value["journal_mode"],
                "Tables": value["table_count"],
                "Indices": value["index_count"],
                "Rows": value["row_count"],
                "Size MB": round(
                    value["size_bytes"] / (1024 * 1024),
                    3,
                ),
                "Modified UTC": value["last_modified_utc"],
            }
        )
    st.dataframe(
        pd.DataFrame(health_rows),
        width="stretch",
        hide_index=True,
    )

    insight_callout(
        "Professional SQLite configuration",
        (
            "All databases use foreign keys, 30-second busy timeout, WAL "
            "journaling, memory temp store, query indices and integrity checks."
        ),
        "⚙",
    )

with operations_tab:
    command_bar(
        "Controlled database operations",
        (
            "Optimize query planners, create safe SQLite backups or export "
            "JSON snapshots without changing scientific data."
        ),
    )

    left, middle, right = st.columns(3)
    with left:
        with st.container(border=True):
            st.markdown("### ⚡ Optimize databases")
            st.write("Run `PRAGMA optimize` on all existing and new databases.")
            vacuum = st.checkbox(
                "Also VACUUM databases",
                value=False,
                help="VACUUM is slower but compacts unused pages.",
            )
            if st.button(
                "Optimize all databases",
                type="primary",
                width="stretch",
            ):
                result = optimize_all_databases(
                    ROOT,
                    vacuum=vacuum,
                )
                st.success(f"Optimized {len(result['results'])} databases.")
                smart_json(result)

    with middle:
        with st.container(border=True):
            st.markdown("### 💾 Create database backup")
            backup_directory = ROOT / "reports" / "database_backups" / "latest"
            st.write("Create consistent SQLite backup copies plus a manifest.")
            if st.button(
                "Back up all databases",
                width="stretch",
            ):
                outputs = backup_all_databases(
                    ROOT,
                    backup_directory,
                )
                st.success(f"Created {len(outputs)} database backups.")
                st.code(
                    "\n".join(outputs),
                    language=None,
                )

    with right:
        with st.container(border=True):
            st.markdown("### 📤 Export JSON snapshots")
            export_directory = ROOT / "reports" / "database_exports" / "latest"
            st.write("Export table contents to portable, reviewable JSON files.")
            if st.button(
                "Export all database JSON",
                width="stretch",
            ):
                outputs = export_all_databases_json(
                    ROOT,
                    export_directory,
                )
                st.success(f"Created {len(outputs)} JSON exports.")
                st.code(
                    "\n".join(outputs),
                    language=None,
                )

    st.download_button(
        "Download current database health JSON",
        json.dumps(
            health,
            indent=2,
            sort_keys=True,
            default=str,
        ),
        "biointel_database_health.json",
        "application/json",
    )

section_title("Open specialist workspaces", "→")
links = st.columns(4)
for column, key, label in (
    (
        links[0],
        "knowledge_warehouse",
        "Knowledge Warehouse",
    ),
    (
        links[1],
        "analytics_observability",
        "Analytics & Observability",
    ),
    (
        links[2],
        "research_assets",
        "Research Assets",
    ),
    (
        links[3],
        "command_center",
        "Command Center",
    ),
):
    page = PAGE_BY_KEY[key]
    with column:
        try:
            st.page_link(
                page.path,
                label=label,
                icon=page.icon,
                width="stretch",
            )
        except (KeyError, RuntimeError):
            st.caption(f"Open {page.title} from the sidebar.")

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='data_intelligence', title='Data Intelligence Hub', category='Intelligence')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
