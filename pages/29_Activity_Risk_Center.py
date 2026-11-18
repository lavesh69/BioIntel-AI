from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.operations.activity_center import (
    activity_export,
    build_timeline,
    dismiss_alert,
    load_activity_state,
    mark_activity_reviewed,
    save_activity_state,
    visible_alerts,
)
from biointel.ui.components import smart_json
from biointel.ui.navigation import PAGE_BY_KEY
from biointel.ui.theme import (
    apply_theme,
    badge,
    executive_kpis,
    hero,
    professional_strip,
    section_title,
    timeline,
)

st.set_page_config(
    page_title="Activity & Risk Center · BioIntel AI",
    page_icon="🔔",
    layout="wide",
)

apply_theme()

hero(
    "Operational awareness without noise.",
    (
        "Review automatic risks, dismiss resolved alerts and follow a unified "
        "timeline of projects, experiments and audit events."
    ),
    eyebrow="Quality-Hardened · Activity & Risk Center",
    chips=[
        "Priority alerts",
        "Project events",
        "Experiment timeline",
        "Local state",
    ],
)

alerts = visible_alerts(ROOT)
timeline_items = build_timeline(ROOT)
state = load_activity_state(ROOT)

counts = {
    "Critical": sum(alert.severity == "Critical" for alert in alerts),
    "Warning": sum(alert.severity == "Warning" for alert in alerts),
    "Info": sum(alert.severity == "Info" for alert in alerts),
}

if counts["Critical"]:
    badge(
        f"● {counts['Critical']} critical alert(s)",
        "danger",
    )
elif counts["Warning"]:
    badge(
        f"● {counts['Warning']} warning alert(s)",
        "warning",
    )
else:
    badge("● No critical operational alerts", "success")

executive_kpis(
    [
        (
            "Critical",
            str(counts["Critical"]),
            "Immediate operational attention",
        ),
        (
            "Warnings",
            str(counts["Warning"]),
            "Items requiring planned review",
        ),
        (
            "Information",
            str(counts["Info"]),
            "Advisory workspace improvements",
        ),
        (
            "Timeline events",
            str(len(timeline_items)),
            (
                "Last reviewed "
                + (str(state["last_reviewed_utc"]) if state["last_reviewed_utc"] else "not yet")
            ),
        ),
    ]
)

alerts_tab, timeline_tab, export_tab = st.tabs(
    [
        "Open alerts",
        "Unified timeline",
        "Export & state",
    ]
)

with alerts_tab:
    section_title("Priority alerts", "!")
    filter_left, filter_right = st.columns(2)
    severity_filter = filter_left.multiselect(
        "Severity",
        ["Critical", "Warning", "Info"],
        default=["Critical", "Warning", "Info"],
    )
    categories = sorted({alert.category for alert in alerts})
    category_filter = filter_right.multiselect(
        "Category",
        categories,
        default=categories,
    )

    filtered = [
        alert
        for alert in alerts
        if alert.severity in severity_filter and alert.category in category_filter
    ]

    if not filtered:
        st.success("No visible alerts match the selected filters.")
    else:
        for alert in filtered:
            tone = (
                "danger"
                if alert.severity == "Critical"
                else "warning" if alert.severity == "Warning" else "success"
            )
            with st.container(border=True):
                header_left, header_middle, header_right = st.columns([4, 1.2, 0.8])
                header_left.markdown(f"### {alert.title}")
                with header_middle:
                    badge(
                        f"● {alert.severity}",
                        tone,
                    )
                if alert.dismissible:
                    if header_right.button(
                        "Dismiss",
                        key=f"dismiss_{alert.item_id}",
                    ):
                        dismiss_alert(
                            ROOT,
                            alert.item_id,
                        )
                        st.rerun()

                st.write(alert.message)
                st.caption(f"{alert.category} · {alert.source}")
                if alert.action_key and alert.action_key in PAGE_BY_KEY:
                    page = PAGE_BY_KEY[alert.action_key]
                    try:
                        st.page_link(
                            page.path,
                            label=f"Open {page.title}",
                            icon=page.icon,
                        )
                    except (KeyError, RuntimeError):
                        st.caption(f"Open {page.title} from the sidebar.")

with timeline_tab:
    professional_strip(
        "Unified evidence timeline",
        (
            "Project updates, training experiments and privacy-safe "
            "audit events are ordered by time."
        ),
    )
    source_filter = st.multiselect(
        "Timeline categories",
        sorted({item.category for item in timeline_items}),
        default=sorted({item.category for item in timeline_items}),
    )
    selected_timeline = [item for item in timeline_items if item.category in source_filter]
    timeline(
        [
            {
                "title": item.title,
                "meta": (f"{item.timestamp_utc} · " f"{item.category}"),
                "copy": item.message,
            }
            for item in selected_timeline[:100]
        ]
    )
    if st.button("Mark activity as reviewed"):
        mark_activity_reviewed(ROOT)
        st.success("Review timestamp saved locally.")
        st.rerun()

with export_tab:
    section_title("Activity export", "⬇")
    export_data = activity_export(ROOT)
    st.download_button(
        "Download activity center JSON",
        json.dumps(
            export_data,
            indent=2,
            default=str,
        ),
        "biointel_activity_center.json",
        "application/json",
        type="primary",
    )

    alert_table = pd.DataFrame([asdict(alert) for alert in alerts])
    if not alert_table.empty:
        st.download_button(
            "Download visible alerts CSV",
            alert_table.to_csv(index=False),
            "biointel_visible_alerts.csv",
            "text/csv",
        )

    smart_json(state)

    confirm_reset = st.checkbox(
        "Confirm dismissed-alert reset",
    )
    if st.button(
        "Restore all dismissed alerts",
        disabled=not confirm_reset,
    ):
        state["dismissed"] = []
        save_activity_state(ROOT, state)
        st.success("Dismissed alerts restored.")
        st.rerun()

st.info(
    "Alert state and review timestamps are stored locally in "
    "reports/activity_state.json. No account or remote notification service is used."
)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='activity_center', title='Activity & Risk Center', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
