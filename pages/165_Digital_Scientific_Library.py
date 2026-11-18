from __future__ import annotations

import streamlit as st
import pandas as pd
from biointel.education.universe_workspaces_service import UniverseWorkspacesService
from biointel.ui.professional_components import render_module_hero, render_empty_state
from biointel.ui.sidebar_redesign import render_breadcrumbs, render_sidebar_redesign

render_sidebar_redesign()
render_breadcrumbs("Digital Scientific Library", "Education")

uv = UniverseWorkspacesService()
module_key = "digital_library"

render_module_hero(
    "Digital Scientific Library",
    "Open Access Textbooks, Reference Manuals & Scientific Protocols",
    icon="📖",
    badge_text="Education Universe"
)

records = uv.list_records(module_key)

t1, t2 = st.tabs(["📋 Active Workspaces", "➕ Create New Workspace Entry"])

with t1:
    st.subheader("Saved Digital Scientific Library Records")
    if not records:
        render_empty_state("No Digital Scientific Library Records Found", "Click 'Create New Workspace Entry' or Reseed Demo Data to populate.")
    else:
        for r in records:
            with st.expander(f"📖 {r['title']}"):
                st.json(r['payload'])
                if st.button("🗑️ Delete Record", key=f"del_{r['record_id']}"):
                    uv.delete_record(r['record_id'])
                    st.success("Record deleted!")
                    st.rerun()

with t2:
    st.subheader("Add New Digital Scientific Library Workspace Entry")
    w_title = st.text_input("Workspace Title:", f"New Digital Scientific Library Record")
    w_note = st.text_area("Notes / Configuration JSON:", '{"status": "active", "priority": "high"}')
    if st.button("Save Entry to Database"):
        uv.save_record(module_key, w_title, {"notes": w_note})
        st.success("Workspace entry saved!")
        st.rerun()
