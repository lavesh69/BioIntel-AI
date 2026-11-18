from __future__ import annotations
from typing import Any
from .._streamlit_compat import st

def theme_snapshot() -> dict[str, Any]:
    theme=getattr(st.context,"theme",None)
    return {"type":getattr(theme,"type","dark"),"primary_color":getattr(theme,"primaryColor",None),"background_color":getattr(theme,"backgroundColor",None)}

def reduced_motion_enabled(key: str = "education_reduced_motion") -> bool:
    st.session_state.setdefault(key,False)
    return st.toggle("Reduced motion", key=key, help="Disables optional motion cues; all core interactions remain available.")