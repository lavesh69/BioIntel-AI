from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.major_module_standard_v188 import COMPULSORY_DIMENSIONS, STANDARD_TABS, step188_rating_matrix
from biointel.ui.theme import apply_theme

st.set_page_config(page_title="Step 188 Universal Major Module Standard · BioIntel AI", page_icon="🧭", layout="wide")
apply_theme()
st.title("Step 188 · Universal Major Module Standard")
st.caption("12-tab lifecycle and 20 compulsory operational dimensions across all 80 major modules.")
frame = step188_rating_matrix(ROOT)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Major modules", f"{len(frame)}/80")
c2.metric("10/10 qualified", f"{int(frame.qualified_10_of_10.sum())}/80")
c3.metric("Compulsory dimensions", f"{int(frame.dimensions_passed.sum())}/{int(frame.dimensions_total.sum())}")
c4.metric("Controlled release", "PENDING")
st.success("All major modules have the standard lifecycle: Overview → Demo → Inputs → QC → Analysis → Results → Visuals → Validation → Interpretation → Report → History → Qualification.")
st.warning("Internal/demo qualification does not create real laboratory, clinical, instrument, licensed-data, independent-site or regulatory evidence.")
with st.expander("Standard lifecycle tabs", expanded=True):
    st.dataframe(pd.DataFrame({"order": range(1, len(STANDARD_TABS)+1), "tab": STANDARD_TABS}), width="stretch", hide_index=True)
with st.expander("Compulsory 20-dimension rubric", expanded=False):
    st.dataframe(pd.DataFrame({"order": range(1, len(COMPULSORY_DIMENSIONS)+1), "dimension": COMPULSORY_DIMENSIONS}), width="stretch", hide_index=True)
st.dataframe(frame[["module_key", "module_title", "page", "rating", "dimensions_passed", "dimensions_total", "tabs_passed", "tabs_total", "qualified_10_of_10", "controlled_release_eligible"]], width="stretch", hide_index=True)
st.download_button("Download Step 188 module rating matrix", frame.to_csv(index=False), "STEP188_80_MAJOR_MODULE_RATINGS.csv", "text/csv")
