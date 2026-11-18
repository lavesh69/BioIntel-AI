from __future__ import annotations
from .._streamlit_compat import st

def confirmation(label: str, *, key: str, detail: str) -> bool:
    with st.container(border=True):
        st.warning(detail, icon=":material/warning:")
        return st.checkbox(label, key=key)