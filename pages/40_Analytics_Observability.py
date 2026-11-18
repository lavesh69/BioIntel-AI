from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.observability.analytics_store import (
    alert_overview,
    analytics_health,
    analytics_summary,
    daily_metric_series,
    module_performance,
    quality_overview,
    recent_events,
    system_overview,
)
from biointel.ui.theme import (
    apply_theme,
    badge,
    command_bar,
    executive_kpis,
    hero,
    insight_callout,
    section_title,
)

st.set_page_config(
    page_title="Analytics & Observability · BioIntel AI",
    page_icon="📈",
    layout="wide",
)

apply_theme()
database = ROOT / "reports" / "analytics.sqlite3"


@st.cache_data(ttl=60, show_spinner=False)
def _analytics_snapshot(path_text: str, modification_ns: int):
    del modification_ns
    path = Path(path_text)
    summary = analytics_summary(path)
    return summary, analytics_health(path, summary=summary)


summary, health = _analytics_snapshot(str(database), database.stat().st_mtime_ns)

hero(
    "Operational analytics for every research workflow.",
    (
        "Monitor run success, latency, processed rows, quality trends, "
        "system performance and alerts across the complete local workspace."
    ),
    eyebrow="Quality-Hardened · Analytics & Observability",
    chips=[
        f"{summary.run_events:,} events",
        f"{summary.success_rate:.1f}% success",
        f"{summary.rows_processed:,} rows processed",
        "180-day history",
    ],
)

badge(
    "● Analytics warehouse healthy" if health["healthy"] else "● Analytics review required",
    "success" if health["healthy"] else "warning",
)

executive_kpis(
    [
        (
            "Run events",
            f"{summary.run_events:,}",
            "Module, action and outcome telemetry",
        ),
        (
            "Success rate",
            f"{summary.success_rate:.2f}%",
            "Deterministic operational benchmark",
        ),
        (
            "Median latency",
            f"{summary.median_duration_ms:.0f} ms",
            "Across recorded workspace events",
        ),
        (
            "P95 latency",
            f"{summary.p95_duration_ms:.0f} ms",
            "95th percentile workflow duration",
        ),
    ]
)

analytics_observability_view = st.radio(
    "Analytics view",
    ["Executive Overview", "Module Performance", "Data Quality", "System Trends", "Alerts"],
    horizontal=True,
    key="analytics_observability_view",
    label_visibility="collapsed",
)

if analytics_observability_view == "Executive Overview":
    command_bar(
        "180-day operational trend",
        "Choose a metric to inspect its historical target and status.",
    )
    metric = st.selectbox(
        "Metric",
        [
            "success_rate",
            "median_latency",
            "p95_latency",
            "cache_hit_rate",
            "data_completeness",
            "model_availability",
            "rows_processed",
            "report_exports",
        ],
    )
    days = st.slider(
        "History window",
        min_value=14,
        max_value=180,
        value=90,
        step=7,
    )
    series = pd.DataFrame(
        daily_metric_series(
            database,
            metric,
            days=days,
        )
    )
    if not series.empty:
        series["metric_date"] = pd.to_datetime(series["metric_date"])
        st.line_chart(series.set_index("metric_date")[["metric_value"]])
        st.dataframe(
            series.tail(20),
            width="stretch",
            hide_index=True,
        )

    insight_callout(
        "Observability is local and private",
        (
            "Telemetry in this warehouse is deterministic demonstration "
            "data stored only in the local project. No external tracking "
            "or cloud analytics is used."
        ),
        "🔒",
    )

if analytics_observability_view == "Module Performance":
    days = st.selectbox(
        "Performance window",
        [7, 30, 90, 180],
        index=1,
    )
    performance = pd.DataFrame(
        module_performance(
            database,
            days=days,
            limit=200,
        )
    )
    st.dataframe(
        performance,
        width="stretch",
        hide_index=True,
    )
    if not performance.empty:
        top = performance.head(15)
        st.bar_chart(top.set_index("module_title")[["runs"]])

    section_title("Recent operational events", "↻")
    controls = st.columns(3)
    status = controls[0].selectbox(
        "Event status",
        ["all", "success", "warning", "failed"],
    )
    module = controls[1].selectbox(
        "Module",
        [
            "all",
            *sorted(
                {
                    str(item)
                    for item in performance.get(
                        "module_key",
                        pd.Series(dtype=str),
                    )
                }
            ),
        ],
    )
    limit = controls[2].selectbox(
        "Rows",
        [50, 100, 200, 500],
        index=1,
    )
    events = pd.DataFrame(
        recent_events(
            database,
            status=status,
            module_key=module,
            limit=limit,
        )
    )
    st.dataframe(
        events,
        width="stretch",
        hide_index=True,
    )

if analytics_observability_view == "Data Quality":
    quality = pd.DataFrame(quality_overview(database))
    st.dataframe(
        quality,
        width="stretch",
        hide_index=True,
    )
    if not quality.empty:
        chart = quality[
            [
                "dataset_name",
                "completeness",
                "schema_score",
            ]
        ].set_index("dataset_name")
        st.bar_chart(chart)

if analytics_observability_view == "System Trends":
    samples = pd.DataFrame(
        system_overview(
            database,
            limit=240,
        )
    )
    if not samples.empty:
        samples["captured_at_utc"] = pd.to_datetime(samples["captured_at_utc"])
        indexed = samples.set_index("captured_at_utc")
        st.line_chart(
            indexed[
                [
                    "cpu_percent",
                    "cache_hit_rate",
                ]
            ]
        )
        st.line_chart(
            indexed[
                [
                    "api_latency_ms",
                    "ui_latency_ms",
                ]
            ]
        )
        st.dataframe(
            samples.tail(30),
            width="stretch",
            hide_index=True,
        )

if analytics_observability_view == "Alerts":
    resolved = st.radio(
        "Alert view",
        ["all", "open", "resolved"],
        horizontal=True,
    )
    alerts = pd.DataFrame(
        alert_overview(
            database,
            resolved=resolved,
        )
    )
    if alerts.empty:
        st.success("No matching alerts.")
    else:
        severity_counts = alerts["severity"].value_counts()
        st.bar_chart(severity_counts)
        st.dataframe(
            alerts,
            width="stretch",
            hide_index=True,
        )

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='analytics_observability', title='Analytics & Observability', category='Intelligence')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
