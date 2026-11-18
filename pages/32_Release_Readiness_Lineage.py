from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.governance.reproducibility import (
    build_lineage_graph,
    project_readiness,
)
from biointel.portfolio.project_registry import list_projects
from biointel.ui.components import smart_json
from biointel.ui.navigation import PAGE_BY_KEY
from biointel.ui.theme import (
    apply_theme,
    badge,
    executive_kpis,
    hero,
    professional_strip,
    section_title,
    status_chips,
)
from biointel.utils.audit_log import verify_audit_chain

REGISTRY = ROOT / "reports" / "projects.sqlite3"


@st.cache_data(ttl=120, show_spinner=False)
def _cached_release_snapshot(root_text: str, project_id: str):
    root = Path(root_text)
    return {
        "readiness": project_readiness(root, project_id),
        "lineage": build_lineage_graph(root, project_id),
        "audit": verify_audit_chain(root / "reports" / "audit.jsonl"),
    }


st.set_page_config(
    page_title="Release Readiness & Lineage · BioIntel AI",
    page_icon="🧭",
    layout="wide",
)

apply_theme()

hero(
    "See exactly what stands between a project and controlled release.",
    (
        "Score release readiness, inspect blockers, verify audit integrity "
        "and visualise project-to-data-to-model lineage."
    ),
    eyebrow="Quality-Hardened · Release Readiness & Lineage",
    chips=[
        "Readiness matrix",
        "Evidence blockers",
        "Lineage graph",
        "Audit integrity",
    ],
)

projects = list_projects(REGISTRY, include_archived=True)
if not projects:
    st.info("Create a project before reviewing release readiness.")
    st.stop()

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

snapshot = _cached_release_snapshot(str(ROOT), selected_id)
readiness = snapshot["readiness"]
lineage = snapshot["lineage"]
audit = snapshot["audit"]

if readiness["percent"] >= 90:
    badge("● Controlled release ready", "success")
elif readiness["percent"] >= 75:
    badge("● Validation ready; release controls remain", "warning")
else:
    badge("● Release evidence incomplete", "danger")

professional_strip(
    f"{selected.project_code} · {readiness['label']}",
    (
        f"Readiness {readiness['score']}/{readiness['maximum']} · "
        f"{len(readiness['blockers'])} major blocker(s) · "
        f"{readiness['matching_experiments']} matching experiment(s)"
    ),
)

executive_kpis(
    [
        (
            "Readiness",
            f"{readiness['percent']}%",
            readiness["label"],
        ),
        (
            "Major blockers",
            str(len(readiness["blockers"])),
            "Zero-point controls worth at least 10 points",
        ),
        (
            "Lineage nodes",
            str(len(lineage["nodes"])),
            f"{len(lineage['edges'])} evidence relationship(s)",
        ),
        (
            "Audit chain",
            "Verified" if audit["valid"] else "Failed",
            (f"{audit['chained_events']} chained · {audit['legacy_events']} legacy"),
        ),
    ]
)

release_lineage_view = st.radio(
    "Release and lineage view",
    ["Readiness matrix", "Lineage graph", "Audit integrity"],
    horizontal=True,
    key="release_lineage_view",
    label_visibility="collapsed",
)

if release_lineage_view == "Readiness matrix":
    section_title("Release-control matrix", "◎")
    criteria = pd.DataFrame(readiness["criteria"])
    st.dataframe(
        criteria,
        width="stretch",
        hide_index=True,
        column_config={
            "earned": st.column_config.ProgressColumn(
                "Earned",
                min_value=0,
                max_value=max(
                    int(criteria["maximum"].max()),
                    1,
                ),
            ),
        },
    )

    if readiness["blockers"]:
        st.error("Major release blockers")
        for blocker in readiness["blockers"]:
            st.markdown(f"- {blocker}")
    else:
        st.success("No major release blockers detected.")

    status_chips(
        [
            (
                "🧾",
                ("Dataset linked" if readiness["linked_dataset_found"] else "Dataset missing"),
            ),
            (
                "🧠",
                ("Model linked" if readiness["linked_model_found"] else "Model missing"),
            ),
            (
                "🧪",
                f"{readiness['matching_experiments']} experiment(s)",
            ),
            (
                "🔗",
                ("Audit verified" if readiness["audit_integrity"]["valid"] else "Audit failed"),
            ),
        ]
    )

    shortcut_columns = st.columns(3)
    shortcuts = [
        (
            "governance_hub",
            "Open Governance Hub",
        ),
        (
            "project_portfolio",
            "Open Project Portfolio",
        ),
        (
            "evidence_studio",
            "Build Evidence Package",
        ),
    ]
    for column, (page_key, label) in zip(
        shortcut_columns,
        shortcuts,
        strict=True,
    ):
        page = PAGE_BY_KEY[page_key]
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

if release_lineage_view == "Lineage graph":
    section_title("Project evidence lineage", "↔")
    node_type_order = [
        "project",
        "dataset",
        "model",
        "experiment",
        "milestone",
        "decision",
        "gate",
    ]
    x_positions = {node_type: index for index, node_type in enumerate(node_type_order)}
    grouped: dict[str, list[dict[str, str]]] = {}
    for node in lineage["nodes"]:
        grouped.setdefault(node["type"], []).append(node)

    positions: dict[str, tuple[float, float]] = {}
    for node_type, nodes in grouped.items():
        count = len(nodes)
        for index, node in enumerate(nodes):
            y = 0.0 if count == 1 else index - (count - 1) / 2
            positions[node["id"]] = (
                float(x_positions.get(node_type, 0)),
                float(y),
            )

    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for edge in lineage["edges"]:
        source = positions.get(edge["source"])
        target = positions.get(edge["target"])
        if source and target:
            edge_x.extend([source[0], target[0], None])
            edge_y.extend([source[1], target[1], None])

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=edge_x,
            y=edge_y,
            mode="lines",
            line={
                "width": 1.3,
                "color": "rgba(148,163,184,.35)",
            },
            hoverinfo="skip",
            name="Evidence links",
        )
    )

    for node_type, nodes in grouped.items():
        figure.add_trace(
            go.Scatter(
                x=[positions[node["id"]][0] for node in nodes],
                y=[positions[node["id"]][1] for node in nodes],
                mode="markers+text",
                text=[node["label"] for node in nodes],
                textposition="top center",
                marker={
                    "size": 18 if node_type == "project" else 13,
                    "line": {
                        "width": 1,
                        "color": "#E2E8F0",
                    },
                },
                name=node_type.title(),
                customdata=[node["id"] for node in nodes],
                hovertemplate=(
                    f"<b>%{{text}}</b><br>Type: {node_type}<br>ID: %{{customdata}}<extra></extra>"
                ),
            )
        )

    figure.update_layout(
        height=620,
        title="Project-to-evidence lineage",
        xaxis={
            "tickmode": "array",
            "tickvals": list(range(len(node_type_order))),
            "ticktext": [item.title() for item in node_type_order],
            "showgrid": False,
            "zeroline": False,
        },
        yaxis={
            "showticklabels": False,
            "showgrid": False,
            "zeroline": False,
        },
    )
    st.plotly_chart(
        figure,
        width="stretch",
    )

    edge_frame = pd.DataFrame(lineage["edges"])
    st.dataframe(
        edge_frame,
        width="stretch",
        hide_index=True,
    )
    st.download_button(
        "Download lineage JSON",
        json.dumps(
            lineage,
            indent=2,
            default=str,
        ),
        f"{selected.project_code}_lineage.json",
        "application/json",
    )

if release_lineage_view == "Audit integrity":
    section_title("Audit-chain verification", "🔗")
    if audit["valid"]:
        st.success("Audit chain is internally consistent.")
    else:
        st.error("Audit chain verification failed. Review the errors below.")

    audit_metrics = st.columns(4)
    audit_metrics[0].metric(
        "Total events",
        audit["total_events"],
    )
    audit_metrics[1].metric(
        "Chained events",
        audit["chained_events"],
    )
    audit_metrics[2].metric(
        "Legacy events",
        audit["legacy_events"],
    )
    audit_metrics[3].metric(
        "Errors",
        len(audit["errors"]),
    )
    smart_json(audit)

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
