from __future__ import annotations

import platform
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.bioinformatics_capabilities import capabilities_dict
from biointel.ui.components import (
    metric_cards,
    scientific_boundary_banner,
    smart_dataframe,
    source_badges,
)
from biointel.ui.theme import apply_theme, hero, section_title

st.set_page_config(page_title="Bioinformatics Capability Center · BioIntel AI", page_icon="🛠️", layout="wide")
apply_theme()
hero(
    "Bioinformatics Capability Center",
    "Understand what works locally, which specialist tools are optional and exactly what each missing capability changes in the workflow.",
    eyebrow="BioIntel AI · Runtime Intelligence",
    chips=["Bioinformatics capability map", "Python modules", "External binaries", "Version-aware install guidance"],
)
scientific_boundary_banner(
    source_kind="verified_public_reference",
    release_eligible=False,
    message="Capability detection reports software availability only. It does not certify analytical validation, reference databases or regulatory suitability.",
)

frame = pd.DataFrame(capabilities_dict())
frame["status"] = frame["available"].map({True: "Available", False: "Optional / missing"})
filters = st.columns([1, 1, 1.5])
category = filters[0].selectbox("Category", ["All", *sorted(frame["category"].unique())])
status = filters[1].selectbox("Status", ["All", "Available", "Optional / missing"])
search = filters[2].text_input("Search capabilities", placeholder="alignment, variants, docking…")
filtered = frame.copy()
if category != "All":
    filtered = filtered[filtered["category"] == category]
if status != "All":
    filtered = filtered[filtered["status"] == status]
if search:
    haystack = filtered[["name", "purpose", "provider"]].fillna("").astype(str).agg(" ".join, axis=1)
    filtered = filtered[haystack.str.contains(search, case=False, regex=False)]

available = int(frame["available"].sum())
metric_cards([
    ("Capabilities detected", f"{available}/{len(frame)}", None),
    ("Python modules", int((frame["category"] == "Python").sum()), None),
    ("External tools", int((frame["category"] == "External").sum()), None),
    ("Optional gaps", int((~frame["available"]).sum()), None),
])
source_badges([
    ("Python", platform.python_version()),
    ("OS", platform.system()),
    ("Architecture", platform.machine()),
    ("Project", "BioIntel AI Bioinformatics Excellence"),
])

chart = frame.groupby(["category", "status"]).size().reset_index(name="capabilities")
st.plotly_chart(px.bar(chart, x="category", y="capabilities", color="status", barmode="stack", title="Runtime capability coverage"), width="stretch")
smart_dataframe(
    filtered[["name", "category", "status", "purpose", "installation_hint"]],
    height=480,
    columns={
        "status": st.column_config.TextColumn("Status", help="Detected in the current runtime"),
        "installation_hint": st.column_config.TextColumn("Install guidance"),
    },
)

section_title("Workflow impact", "🧭")
missing = frame[~frame["available"]]
if missing.empty:
    st.success("All optional scientific capabilities in the current catalogue are detected.")
else:
    for _, row in missing.iterrows():
        with st.expander(f"{row['name']} — {row['purpose']}"):
            st.write(row["installation_hint"])
            st.caption("Install only from a trusted source and validate the tool/version against your scientific workflow before use.")

st.download_button("Download capability report", frame.to_csv(index=False), "bioinformatics_capabilities.csv", "text/csv", width="stretch")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
