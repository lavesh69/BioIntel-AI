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

from biointel.operations.executive_summary import (
    build_executive_summary,
)
from biointel.ui.navigation import PAGE_BY_KEY
from biointel.ui.theme import (
    apply_theme,
    badge,
    executive_kpis,
    feature_card,
    hero,
    professional_strip,
    section_title,
    status_chips,
)

st.set_page_config(
    page_title="Executive Overview · BioIntel AI",
    page_icon="📈",
    layout="wide",
)

apply_theme()

hero(
    "Executive clarity for the entire research portfolio.",
    (
        "Translate projects, models, datasets, diagnostics and operational "
        "risk into one professional decision-ready overview."
    ),
    eyebrow="Quality-Hardened · Governance-aware Executive Overview",
    chips=[
        "Maturity score",
        "Portfolio risk",
        "Project priorities",
        "Decision support",
    ],
)

summary = build_executive_summary(ROOT)
portfolio = summary["portfolio"]
risk = summary["risk_counts"]
workflow = summary["workflow"]

if risk["critical"]:
    badge(
        f"● {risk['critical']} critical risk item(s)",
        "danger",
    )
elif risk["warning"]:
    badge(
        f"● {risk['warning']} warning item(s)",
        "warning",
    )
else:
    badge("● No critical operational risks", "success")

professional_strip(
    summary["maturity_label"],
    (
        f"Workspace maturity score {summary['maturity_score']}/100 · "
        f"{summary['open_alerts']} open operational alert(s)"
    ),
)

executive_kpis(
    [
        (
            "Maturity score",
            f"{summary['maturity_score']}/100",
            summary["maturity_label"],
        ),
        (
            "Active portfolio",
            str(portfolio["active"]),
            f"{portfolio['total']} total registered project(s)",
        ),
        (
            "Open alerts",
            str(summary["open_alerts"]),
            (f"{risk['critical']} critical · " f"{risk['warning']} warning"),
        ),
        (
            "Default model",
            summary["default_model"] or "Not selected",
            "Preferred trusted artifact for prediction",
        ),
    ]
)

section_title("Executive health view", "◎")
chart_left, chart_right = st.columns(2)

with chart_left:
    gauge = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=summary["maturity_score"],
            number={"suffix": "/100"},
            title={"text": "Workspace maturity"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#38BDF8"},
                "steps": [
                    {"range": [0, 30], "color": "rgba(244,63,94,.18)"},
                    {"range": [30, 50], "color": "rgba(245,158,11,.18)"},
                    {"range": [50, 70], "color": "rgba(59,130,246,.18)"},
                    {"range": [70, 85], "color": "rgba(20,184,166,.18)"},
                    {"range": [85, 100], "color": "rgba(34,197,94,.18)"},
                ],
                "threshold": {
                    "line": {"color": "#F8FAFC", "width": 3},
                    "thickness": 0.75,
                    "value": 85,
                },
            },
        )
    )
    gauge.update_layout(height=360)
    st.plotly_chart(gauge, width="stretch")

with chart_right:
    risk_chart = go.Figure(
        data=[
            go.Bar(
                x=["Critical", "Warning", "Info"],
                y=[
                    risk["critical"],
                    risk["warning"],
                    risk["info"],
                ],
                text=[
                    risk["critical"],
                    risk["warning"],
                    risk["info"],
                ],
                textposition="auto",
            )
        ]
    )
    risk_chart.update_layout(
        title="Open operational alerts",
        height=360,
        yaxis_title="Alert count",
    )
    st.plotly_chart(risk_chart, width="stretch")

section_title("Professional readiness", "◈")
score_components = summary["score_components"]
readiness_rows = pd.DataFrame(
    [
        {
            "Capability": key.replace("_", " ").title(),
            "Score": value,
            "Maximum": maximum,
            "Completion %": round(value / maximum * 100, 1),
        }
        for key, value, maximum in [
            ("diagnostics", score_components["diagnostics"], 15),
            ("datasets", score_components["datasets"], 10),
            ("models", score_components["models"], 10),
            ("default_model", score_components["default_model"], 10),
            ("experiments", score_components["experiments"], 10),
            ("active_project", score_components["active_project"], 10),
            ("linked_projects", score_components["linked_projects"], 10),
            ("governance", score_components["governance"], 15),
            ("completed_project", score_components["completed_project"], 5),
            ("reporting", score_components["reporting"], 5),
        ]
    ]
)
st.dataframe(
    readiness_rows,
    width="stretch",
    hide_index=True,
    column_config={
        "Completion %": st.column_config.ProgressColumn(
            "Completion %",
            min_value=0,
            max_value=100,
            format="%.0f%%",
        )
    },
)

section_title("Priority project board", "📌")
priority_projects = pd.DataFrame(summary["priority_projects"])
if priority_projects.empty:
    st.info("No active projects are registered. Create one in Project Portfolio.")
else:
    st.dataframe(
        priority_projects,
        width="stretch",
        hide_index=True,
    )

section_title("Decision shortcuts", "→")
shortcuts = st.columns(4)
shortcut_items = [
    (
        "project_portfolio",
        "Manage portfolio",
        "Create, link and review research projects.",
        "📁",
    ),
    (
        "activity_center",
        "Review alerts",
        "Resolve operational warnings and risks.",
        "🔔",
    ),
    (
        "report_studio",
        "Export briefing",
        "Create a polished evidence snapshot.",
        "📝",
    ),
    (
        "workflow_dashboard",
        "Open workspace",
        "Inspect models, datasets and storage.",
        "📍",
    ),
]
for column, (key, title, copy, icon) in zip(
    shortcuts,
    shortcut_items,
    strict=True,
):
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

status_chips(
    [
        ("🧾", f"{workflow['datasets']['total']} datasets"),
        ("🧠", f"{workflow['models']['total']} models"),
        ("🧪", f"{workflow['experiments']['total']} experiments"),
        ("🩺", summary["diagnostics"]["overall"]),
    ]
)

st.download_button(
    "Download executive summary JSON",
    json.dumps(summary, indent=2, default=str),
    "biointel_executive_summary.json",
    "application/json",
)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='executive_overview', title='Executive Overview', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
