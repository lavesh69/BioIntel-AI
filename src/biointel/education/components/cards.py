from __future__ import annotations
from collections.abc import Iterable, Mapping
from typing import Any
from .._streamlit_compat import st
from .status import status_badge

def metric_grid(items: Iterable[Mapping[str, Any]]) -> None:
    with st.container(horizontal=True):
        for item in items:
            kwargs: dict[str, Any] = {"label": str(item["label"]), "value": item.get("value", 0), "border": True}
            if item.get("delta") is not None:
                kwargs["delta"] = item["delta"]
            if item.get("help"):
                kwargs["help"] = str(item["help"])
            trend = item.get("trend")
            if trend:
                kwargs["chart_data"] = list(trend)
                kwargs["chart_type"] = str(item.get("chart_type", "line"))
            st.metric(**kwargs)

def identity_card(title: str, subtitle: str, *, icon: str = ":material/science:", badges: Iterable[tuple[str, str]] = (), progress: float | None = None, caption: str = "") -> None:
    with st.container(border=True, height="stretch"):
        st.subheader(f"{icon} {title}")
        st.caption(subtitle)
        if badges:
            with st.container(horizontal=True):
                for label, state in badges:
                    status_badge(state, label=label)
        if progress is not None:
            value = max(0.0, min(1.0, float(progress)))
            st.progress(value, text=f"{value * 100:.0f}% complete")
        if caption:
            st.caption(caption)