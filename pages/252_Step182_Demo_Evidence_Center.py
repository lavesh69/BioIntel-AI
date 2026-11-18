from __future__ import annotations

import json
import sys
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.external_demo_v182 import demo_detail_matrix, demo_qualification_matrix
from biointel.ui.theme import apply_theme

st.set_page_config(page_title="Step 182 Demo Evidence · BioIntel AI", page_icon="🧪", layout="wide")
apply_theme()
st.title("🧪 Step 182 · Synthetic Demo Evidence Center")
st.warning("These 25 packs are synthetic test fixtures. Demo execution can be 25/25 while real external evidence remains 0/25 and controlled release remains blocked.")
summary = demo_qualification_matrix(ROOT)
details = demo_detail_matrix(ROOT)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Modules demo-ready", f"{int(summary.demo_execution_ready.sum())}/5")
c2.metric("Demo packs ready", f"{int(details.demo_ready.sum())}/25")
c3.metric("Real evidence", "0/25")
c4.metric("Controlled release", "NO")
st.subheader("Module summary")
st.dataframe(summary, width="stretch", hide_index=True)
st.subheader("All demo packs")
display = details.copy()
display["metrics"] = display["metrics"].map(lambda x: json.dumps(x, ensure_ascii=False, default=str))
display["blockers"] = display["blockers"].map(lambda x: " | ".join(x))
st.dataframe(display, width="stretch", hide_index=True)
st.download_button("Download demo module summary", summary.to_csv(index=False), "step182_demo_module_summary.csv", "text/csv")
st.download_button("Download demo pack details", details.to_csv(index=False), "step182_demo_pack_details.csv", "text/csv")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
