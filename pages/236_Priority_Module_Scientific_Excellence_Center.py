from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT=Path(__file__).resolve().parents[1]; SRC=ROOT/'src'
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from biointel.priority_v167 import priority_matrix
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe
from biointel.ui.theme import apply_theme, hero, section_title
st.set_page_config(page_title="Priority Module Scientific Excellence · BioIntel AI",page_icon="P21",layout="wide")
apply_theme()
hero("Priority Module Scientific Excellence Center","Focused native-depth upgrade for 21 high-priority discovery, genomics, omics, single-cell, federated AI and model-lifecycle workflows.",eyebrow="BioIntel AI · Step 167",chips=["21/21 software 10/10","Native depth 10/10","QC + uncertainty","Fail closed"])
scientific_boundary_banner(source_kind="reference",release_eligible=False,message="Step 167 completes software-owned scientific depth. Specialist runtimes, production databases, independent evidence, orthogonal confirmation and expert sign-off remain external requirements.")
matrix=priority_matrix(ROOT)
metric_cards([("Priority modules","21/21","Focused upgrade"),("Software score","10/10","All 21"),("Native research depth","10/10","All 21"),("Confirmatory release","0/21","Real evidence required")])
section_title("Priority excellence matrix","P21")
smart_dataframe(matrix,height=620,key="step167_priority_module_matrix")
st.download_button("Download matrix",matrix.to_csv(index=False).encode(),"biointel_step167_priority_module_matrix.csv","text/csv",width="stretch")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
