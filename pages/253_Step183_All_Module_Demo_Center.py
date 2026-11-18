from __future__ import annotations

import sys
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.portfolio_demo_v183 import portfolio_demo_detail_matrix, portfolio_demo_matrix
from biointel.ui.theme import apply_theme

st.set_page_config(page_title="Step 183 All-Module Demo Center · BioIntel AI", page_icon="🧪", layout="wide")
apply_theme()
st.title("🧪 Step 183 · All 80 Modules Demo Center")
st.warning("Demo operational ratings are not real scientific validation ratings. Synthetic files never unlock controlled scientific release.")
summary = portfolio_demo_matrix(ROOT)
details = portfolio_demo_detail_matrix(ROOT)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Modules demo-ready", f"{int(summary.demo_ready.sum())}/80")
c2.metric("Average demo rating", f"{summary.demo_operational_rating.mean():.2f}/10")
c3.metric("Internal software", "80/80 at 10/10")
c4.metric("Controlled release", "0/80")
st.subheader("Module-wise demo-assisted ratings")
st.dataframe(summary.sort_values(["demo_operational_rating", "module_title"], ascending=[False, True]), width="stretch", hide_index=True)
st.subheader("Bundle verification")
st.dataframe(details, width="stretch", hide_index=True)
st.download_button("Download ratings CSV", summary.to_csv(index=False), "STEP183_80_MODULE_DEMO_RATINGS.csv", "text/csv")
st.download_button("Download validation CSV", details.to_csv(index=False), "STEP183_80_MODULE_DEMO_DETAILS.csv", "text/csv")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
