from __future__ import annotations
from collections.abc import Iterable, Mapping
from typing import Any, Callable
from .._streamlit_compat import st

def breadcrumbs(items: Iterable[str]) -> None:
    st.caption("  /  ".join(str(item) for item in items if item))

def command_palette(actions: Iterable[Mapping[str, Any]], *, key: str, on_select: Callable[[str], None] | None = None) -> str | None:
    permitted=[item for item in actions if bool(item.get("allowed",True))]
    if not permitted:
        st.caption("No command-palette actions are available for this role.")
        return None
    by_id={str(item["id"]):item for item in permitted}
    query=st.selectbox("Command palette", ["",*by_id], format_func=lambda value:"Search actions…" if not value else str(by_id[value].get("label",value)), key=key)
    if query:
        item=by_id[query]
        st.caption(str(item.get("detail","Permission-aware Education action")))
        if st.button("Run action", icon=":material/bolt:", key=f"{key}_run"):
            if on_select:
                on_select(query)
            return query
    return None