from __future__ import annotations
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any
import pandas as pd

def count_rows(rows: Iterable[Mapping[str, Any]], field: str, *, label: str = "Category", value_label: str = "Records") -> list[dict[str, Any]]:
    counts = Counter(str(row.get(field) or "Unknown") for row in rows)
    return [{label: key.replace("_", " ").title(), value_label: value} for key, value in sorted(counts.items())]

def dated_counts(rows: Iterable[Mapping[str, Any]], field: str, *, period: str = "month", date_label: str = "Period", value_label: str = "Records") -> list[dict[str, Any]]:
    counts: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        raw = str(row.get(field) or "")[:10]
        if not raw:
            continue
        try:
            moment = datetime.fromisoformat(raw)
        except ValueError:
            continue
        key = moment.strftime("%Y-%m" if period == "month" else "%Y-%m-%d")
        counts[key] += 1
    return [{date_label: key, value_label: counts[key]} for key in sorted(counts)]

def _frame(rows: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(list(rows))

def render_bar(rows: Iterable[Mapping[str, Any]], x: str, y: str, *, title: str, horizontal: bool = False, empty_detail: str = "No persisted records are available for this chart.") -> bool:
    from .._streamlit_compat import st
    from .empty_states import render_empty_state
    frame = _frame(rows)
    with st.container(border=True, height="stretch"):
        st.subheader(title)
        if frame.empty or x not in frame or y not in frame or not pd.to_numeric(frame[y], errors="coerce").fillna(0).abs().sum():
            render_empty_state("No chart data", empty_detail, icon=":material/bar_chart:")
            return False
        st.bar_chart(frame, x=x, y=y, horizontal=horizontal)
        st.caption(chart_text_alternative(frame.to_dict("records"), x, y))
    return True

def render_line(rows: Iterable[Mapping[str, Any]], x: str, y: str, *, title: str, empty_detail: str = "No persisted time-series data is available.") -> bool:
    from .._streamlit_compat import st
    from .empty_states import render_empty_state
    frame = _frame(rows)
    with st.container(border=True, height="stretch"):
        st.subheader(title)
        if frame.empty or x not in frame or y not in frame or not pd.to_numeric(frame[y], errors="coerce").fillna(0).abs().sum():
            render_empty_state("No trend data", empty_detail, icon=":material/query_stats:")
            return False
        st.line_chart(frame, x=x, y=y)
        st.caption(chart_text_alternative(frame.to_dict("records"), x, y))
    return True

def render_heatmap(rows: Iterable[Mapping[str, Any]], x: str, y: str, value: str, *, title: str, empty_detail: str = "No persisted matrix data is available.") -> bool:
    from .._streamlit_compat import st
    from .empty_states import render_empty_state
    frame = _frame(rows)
    with st.container(border=True, height="stretch"):
        st.subheader(title)
        if frame.empty or any(column not in frame for column in (x, y, value)):
            render_empty_state("No matrix data", empty_detail, icon=":material/grid_view:")
            return False
        pivot = frame.pivot_table(index=y, columns=x, values=value, aggfunc="mean", fill_value=0)
        if pivot.empty:
            render_empty_state("No matrix data", empty_detail, icon=":material/grid_view:")
            return False
        st.dataframe(pivot.style.background_gradient(cmap="Blues"), hide_index=False)
        st.caption(f"Matrix of {value} across {len(pivot.index)} {y.lower()} values and {len(pivot.columns)} {x.lower()} values.")
    return True

def chart_text_alternative(rows: list[Mapping[str, Any]], x: str, y: str) -> str:
    if not rows:
        return "Chart alternative: no data."
    numeric = [(str(row.get(x, "Unknown")), float(row.get(y) or 0)) for row in rows]
    peak = max(numeric, key=lambda item: item[1])
    total = sum(value for _, value in numeric)
    return f"Chart alternative: {len(numeric)} points; total {total:g}; highest {peak[0]} at {peak[1]:g}."

def render_metric_explanation(definition: str, formula: str, included: str, excluded: str, date_range: str, completeness: float, calculated_at: str, limitations: str) -> None:
    from .._streamlit_compat import st
    with st.expander("How this metric is calculated", icon=":material/info:"):
        st.markdown(f"**Definition:** {definition}\n\n**Formula:** `{formula}`\n\n**Included events:** {included}\n\n**Excluded events:** {excluded}\n\n**Date range:** {date_range}\n\n**Data completeness:** {max(0,min(100,completeness)):.0f}%\n\n**Last calculated:** {calculated_at}\n\n**Limitations:** {limitations}")