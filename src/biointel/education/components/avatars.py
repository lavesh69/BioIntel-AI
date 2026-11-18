from __future__ import annotations
from .._streamlit_compat import st

def initials(name: str) -> str:
    parts=[part for part in str(name).strip().split() if part]
    return "".join(part[0].upper() for part in parts[:2]) or "BI"

def render_identity(name: str, role: str, *, verified: bool = False) -> None:
    with st.container(border=True, height="stretch"):
        st.badge(initials(name), icon=":material/person:", color="blue")
        st.markdown(f"**{name}**")
        st.caption(role.replace("_"," ").title())
        if verified:
            st.badge("Verified", icon=":material/verified:", color="green")