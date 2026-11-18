from __future__ import annotations
from collections.abc import Sequence

def workflow_state(stages: Sequence[str], current: str) -> list[dict[str, str | bool]]:
    normalized=[str(stage) for stage in stages]
    index=normalized.index(current) if current in normalized else -1
    return [{"stage":stage,"complete":index >= position and index >= 0,"current":position == index} for position,stage in enumerate(normalized)]

def render_workflow(stages: Sequence[str], current: str, *, title: str = "Workflow") -> None:
    from .._streamlit_compat import st
    st.subheader(title)
    with st.container(horizontal=True):
        for item in workflow_state(stages,current):
            label=str(item["stage"]).replace("_"," ").title()
            if item["current"]:
                st.badge(label, color="blue", icon=":material/play_circle:")
            elif item["complete"]:
                st.badge(label, color="green", icon=":material/check_circle:")
            else:
                st.badge(label, color="gray", icon=":material/radio_button_unchecked:")