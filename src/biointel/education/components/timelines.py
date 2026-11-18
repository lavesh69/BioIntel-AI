from __future__ import annotations
from collections.abc import Iterable, Mapping
from typing import Any
from .._streamlit_compat import st
from .empty_states import render_empty_state
from .status import status_badge

def render_timeline(events: Iterable[Mapping[str, Any]], *, title: str = "Timeline", limit: int = 30, empty_detail: str = "Events appear after persisted Education activity is recorded.") -> int:
    rows = sorted(list(events), key=lambda item: str(item.get("when") or item.get("created_at") or ""), reverse=True)[:limit]
    st.subheader(title)
    if not rows:
        render_empty_state("No timeline events", empty_detail, icon=":material/timeline:")
        return 0
    for event in rows:
        with st.container(border=True):
            left, right = st.columns([3, 1], vertical_alignment="center")
            with left:
                st.markdown(f"**{event.get('title', 'Education activity')}**")
                st.caption(str(event.get("detail") or event.get("source") or "Persisted Education record"))
            with right:
                status_badge(event.get("state", "recorded"))
                st.caption(str(event.get("when") or event.get("created_at") or ""))
            if event.get("page"):
                try:
                    st.page_link(str(event["page"]), label="Open source workspace", icon=":material/open_in_new:")
                except (KeyError, RuntimeError):
                    st.caption(f"Source workspace: {event['page']}")
    return len(rows)