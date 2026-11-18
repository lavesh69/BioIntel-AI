from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.external_readiness_v181 import PROFILES, TARGET_MODULES, evidence_detail_matrix, qualification_matrix
from biointel.ui.theme import apply_theme, hero

st.set_page_config(page_title="Step 181 External Scientific Evidence · BioIntel AI", page_icon="🔬", layout="wide")
apply_theme()
hero(
    "Step 181 · External Scientific Evidence Center",
    "Operational qualification for real models, instruments, scanners, wet-lab assays, licensed references and independent-site evidence.",
    eyebrow="No fabricated evidence · Fail-closed controlled release",
    chips=["5 modules", "25 evidence packs", "SHA-256 verification", "Quantitative acceptance gates"],
)

summary = qualification_matrix(ROOT)
details = evidence_detail_matrix(ROOT)
first, second, third, fourth = st.columns(4)
first.metric("Modules", len(summary))
second.metric("Workflow 10/10", int(summary.weakness_remediation_workflow_rating.eq(10.0).sum()))
third.metric("Qualified evidence packs", int(details.qualified.sum()))
fourth.metric("Controlled release", int(summary.controlled_release_eligible.sum()))

st.markdown("### Module readiness")
st.dataframe(summary, width="stretch", hide_index=True)

module = st.selectbox(
    "Inspect module evidence",
    TARGET_MODULES,
    format_func=lambda key: PROFILES[key].title,
)
module_details = evidence_detail_matrix(ROOT, module).copy()
module_details["metrics"] = module_details["metrics"].map(lambda value: json.dumps(value, ensure_ascii=False, default=str))
module_details["blockers"] = module_details["blockers"].map(lambda value: " | ".join(value))
st.dataframe(module_details, width="stretch", hide_index=True)

left, right = st.columns(2)
with left:
    st.download_button(
        "Download readiness summary CSV",
        summary.to_csv(index=False).encode("utf-8"),
        "step181_external_readiness_summary.csv",
        "text/csv",
    )
with right:
    st.download_button(
        "Download evidence detail CSV",
        details.to_csv(index=False).encode("utf-8"),
        "step181_external_readiness_details.csv",
        "text/csv",
    )

st.info(
    "Run BUILD_STEP181_EXTERNAL_EVIDENCE_WORKSPACES_WINDOWS.bat to create templates. Put real evidence under "
    "UserData/step181/evidence, update the manifest SHA-256 values and reviewer fields, then run "
    "VERIFY_STEP181_EXTERNAL_EVIDENCE_WINDOWS.bat."
)
st.warning(
    "The validation workflow is complete, but the package cannot manufacture wet-lab results, scanner calibration, experimental binding, "
    "independent patient cohorts or licensed third-party databases. Controlled release remains blocked until those real records qualify."
)

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
