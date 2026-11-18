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

from biointel.intelligence.knowledge_warehouse import (
    knowledge_health,
    knowledge_relations,
    knowledge_summary,
    list_protocols,
    list_saved_queries,
    search_knowledge,
)
from biointel.ui.components import smart_json
from biointel.ui.theme import (
    apply_theme,
    badge,
    command_bar,
    density_bar,
    executive_kpis,
    hero,
    insight_callout,
    section_title,
)

st.set_page_config(
    page_title="Knowledge Warehouse · BioIntel AI",
    page_icon="🧠",
    layout="wide",
)

apply_theme()
database = ROOT / "reports" / "knowledge.sqlite3"
summary = knowledge_summary(database)
health = knowledge_health(database)

hero(
    "Searchable research knowledge with traceable relationships.",
    (
        "Discover compounds, sequences, targets, datasets, models, projects, "
        "modules, protocols and benchmark relationships in one indexed warehouse."
    ),
    eyebrow="Quality-Hardened · Research Knowledge Warehouse",
    chips=[
        f"{summary.entities:,} entities",
        f"{summary.relations:,} relations",
        f"{summary.protocols} protocols",
        "FTS5 search",
    ],
)

badge(
    (
        "● Knowledge warehouse healthy"
        if health["healthy"]
        else "● Knowledge warehouse requires review"
    ),
    "success" if health["healthy"] else "warning",
)

executive_kpis(
    [
        (
            "Entities",
            f"{summary.entities:,}",
            "Compounds, sequences, datasets, models and projects",
        ),
        (
            "Relations",
            f"{summary.relations:,}",
            "Training, lineage and benchmark associations",
        ),
        (
            "Protocols",
            f"{summary.protocols:,}",
            "Professional controlled research workflows",
        ),
        (
            "Saved searches",
            f"{summary.saved_queries:,}",
            "Pinned discovery shortcuts",
        ),
    ]
)

search_tab, relations_tab, protocols_tab, taxonomy_tab = st.tabs(
    [
        "Search & Discover",
        "Relationship Explorer",
        "Protocol Library",
        "Taxonomy",
    ]
)

with search_tab:
    command_bar(
        "Full-text knowledge search",
        "Filter indexed entities by type, status and confidence.",
    )
    controls = st.columns([3, 1.3, 1.3, 1])
    query = controls[0].text_input(
        "Search query",
        value="extra trees",
        placeholder="Search compounds, targets, models, projects…",
    )
    entity_types = ["all", *summary.entity_types.keys()]
    entity_type = controls[1].selectbox(
        "Entity type",
        entity_types,
    )
    statuses = ["all", *summary.statuses.keys()]
    status = controls[2].selectbox(
        "Status",
        statuses,
    )
    limit = controls[3].selectbox(
        "Limit",
        [25, 50, 100, 200, 500],
        index=2,
    )

    results = search_knowledge(
        database,
        query,
        entity_type=entity_type,
        status=status,
        limit=limit,
    )
    st.caption(f"{len(results):,} result(s) returned from indexed knowledge.")
    if results:
        frame = pd.DataFrame(results)
        display_columns = [
            column
            for column in [
                "entity_type",
                "name",
                "summary",
                "status",
                "confidence",
                "source",
                "external_id",
            ]
            if column in frame.columns
        ]
        st.dataframe(
            frame[display_columns],
            width="stretch",
            hide_index=True,
        )
        st.download_button(
            "Download search results CSV",
            frame.to_csv(index=False),
            "knowledge_search_results.csv",
            "text/csv",
        )

        selected_name = st.selectbox(
            "Inspect entity",
            frame["name"].tolist(),
        )
        selected = frame.loc[frame["name"] == selected_name].iloc[0]
        with st.expander(
            f"Entity details · {selected_name}",
            expanded=True,
        ):
            detail_columns = st.columns([2, 1])
            with detail_columns[0]:
                st.markdown(f"### {selected['name']}")
                st.write(selected["summary"])
                st.caption(f"Source: {selected['source']}")
            with detail_columns[1]:
                st.metric(
                    "Confidence",
                    f"{float(selected['confidence']) * 100:.1f}%",
                )
                st.metric(
                    "Status",
                    str(selected["status"]),
                )
            try:
                metadata = json.loads(str(selected.get("metadata_json", "{}")))
                smart_json(metadata)
            except json.JSONDecodeError:
                pass
    else:
        insight_callout(
            "No matching entities",
            "Try a broader term or clear the type/status filters.",
            "🔎",
        )

    section_title("Pinned saved searches", "★")
    saved = pd.DataFrame(list_saved_queries(database))
    st.dataframe(
        saved,
        width="stretch",
        hide_index=True,
    )

with relations_tab:
    command_bar(
        "Relationship explorer",
        "Inspect incoming and outgoing knowledge graph links.",
    )
    seed_results = search_knowledge(
        database,
        "",
        limit=250,
    )
    seed_frame = pd.DataFrame(seed_results)
    if seed_frame.empty:
        st.info("No knowledge entities are available.")
    else:
        selected_name = st.selectbox(
            "Choose an entity",
            seed_frame["name"].tolist(),
            key="relation_entity",
        )
        selected_id = str(
            seed_frame.loc[
                seed_frame["name"] == selected_name,
                "entity_id",
            ].iloc[0]
        )
        relations = pd.DataFrame(
            knowledge_relations(
                database,
                selected_id,
                limit=500,
            )
        )
        if relations.empty:
            st.info("This entity has no registered relationships.")
        else:
            st.dataframe(
                relations,
                width="stretch",
                hide_index=True,
            )
            relation_counts = relations["relation_type"].value_counts()
            st.bar_chart(relation_counts)

with protocols_tab:
    categories = [
        "all",
        "Data",
        "Sequence",
        "Chemistry",
        "Modeling",
        "Validation",
        "Governance",
    ]
    category = st.selectbox(
        "Protocol category",
        categories,
    )
    protocols = list_protocols(
        database,
        category=category,
    )
    st.caption(f"{len(protocols)} professional protocol(s)")
    for protocol in protocols:
        with st.expander(f"{protocol['name']} · {protocol['risk_level']} risk"):
            st.write(protocol["objective"])
            steps = json.loads(protocol["steps_json"])
            for index, step in enumerate(
                steps,
                start=1,
            ):
                st.markdown(f"**{index}.** {step}")
            st.success(protocol["acceptance_criteria"])
            st.caption(f"Tags: {protocol['tags']}")

with taxonomy_tab:
    section_title("Entity distribution", "◈")
    maximum = max(
        summary.entity_types.values(),
        default=1,
    )
    for label, value in summary.entity_types.items():
        density_bar(
            label.replace("_", " ").title(),
            value,
            maximum,
            display_value=f"{value:,}",
        )

    section_title("Status distribution", "◎")
    status_frame = pd.DataFrame(
        [
            {
                "Status": key,
                "Entities": value,
            }
            for key, value in summary.statuses.items()
        ]
    )
    st.dataframe(
        status_frame,
        width="stretch",
        hide_index=True,
    )

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='knowledge_warehouse', title='Knowledge Warehouse', category='Intelligence')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
