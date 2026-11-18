from __future__ import annotations
from .._streamlit_compat import st

def render_empty_state(title: str, detail: str, *, icon: str = ":material/inbox:", action_label: str | None = None, action_key: str | None = None) -> bool:
    with st.container(border=True, horizontal_alignment="center"):
        st.subheader(f"{icon} {title}")
        st.caption(detail, text_alignment="center")
        if action_label:
            return st.button(action_label, key=action_key, icon=":material/add:")
    return False