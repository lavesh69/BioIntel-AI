from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from biointel.priority_v165 import priority_matrix
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe
from biointel.ui.theme import apply_theme, hero, section_title
st.set_page_config(page_title="Priority Module Excellence · BioIntel AI",page_icon="PX",layout="wide")
apply_theme()
hero("Priority Three-Module Excellence Center","Focused confirmatory-grade software depth for AMR Surveillance, Protein–Ligand Co-Design and Long-Read Epigenome.",eyebrow="BioIntel AI · Step 165",chips=["3/3 software 10/10","Uncertainty-aware","Evidence gated","Fail closed"])
scientific_boundary_banner(source_kind="reference",release_eligible=False,message="Step 165 completes software-owned depth. Phenotypic AST, measured binding, orthogonal methylation, independent cohorts and expert sign-off remain external requirements.")
matrix=priority_matrix(ROOT)
metric_cards([("Priority modules","3/3","Focused upgrade"),("Software score","10/10","All three"),("Confirmatory release eligible","0/3","Real evidence required"),("Claim protection","Active","Research-only fail closed")])
section_title("Focused excellence matrix","PX")
smart_dataframe(matrix,height=500,key="step165_priority_matrix")
st.download_button("Download matrix",matrix.to_csv(index=False).encode(),"biointel_step165_priority_matrix.csv","text/csv",width="stretch")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
