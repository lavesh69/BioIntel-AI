from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.quality_v160 import portfolio_quality_matrix, portfolio_quality_summary  # noqa: E402
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json  # noqa: E402
from biointel.ui.theme import apply_theme, hero, section_title  # noqa: E402

st.set_page_config(page_title="Module Quality 10/10 · BioIntel AI", page_icon="Q10", layout="wide")
apply_theme()
hero(
    "Module Quality 10/10 Command Center",
    "Verify the same ten software-owned quality controls across all 80 scientific modules without confusing internal engineering completeness with external scientific validation.",
    eyebrow="BioIntel AI · Step 160 Maximum Internal Module Quality",
    chips=["80 module contracts", "Full-input integrity", "Checksum-bound outputs", "Reproducibility signatures", "Fail-closed evidence gates"],
)
scientific_boundary_banner(
    source_kind="reference",
    release_eligible=False,
    message="10/10 on this screen means internal software quality controls are complete. Specialist binaries, licensed/qualified references, independent experiments, clinical evidence and regulatory authorization remain separate requirements.",
)


@st.cache_data(ttl=120, show_spinner=False)
def _matrix():
    return portfolio_quality_matrix(ROOT)


matrix = _matrix()
summary = portfolio_quality_summary(matrix)
metric_cards([
    ("Scientific modules", summary["modules"], "Registered profiles"),
    ("Internal 10/10", f"{summary['internal_10_of_10']}/{summary['modules']}", "Ten software-owned dimensions"),
    ("Specialist complete", f"{summary['specialist_runtime_complete']}/{summary['modules']}", "Detected third-party runtimes"),
    ("External release eligible", summary["external_release_eligible"], "Independent evidence + references"),
])

section_title("Module-by-module quality matrix", "✅")
view = st.selectbox(
    "View",
    ["All modules", "Internal quality below 10/10", "Specialist runtime incomplete", "References incomplete", "External evidence incomplete"],
    key="step160_quality_filter",
)
visible = matrix.copy()
if view == "Internal quality below 10/10":
    visible = visible.loc[visible.internal_quality_score < 10.0]
elif view == "Specialist runtime incomplete":
    visible = visible.loc[visible.specialist_engines_detected < visible.specialist_engines_required]
elif view == "References incomplete":
    visible = visible.loc[visible.qualified_references < visible.required_references]
elif view == "External evidence incomplete":
    visible = visible.loc[visible.external_evidence_score < 100.0]

columns = [
    "module_key",
    "title",
    "native_family",
    "internal_quality_rating",
    "dimensions_passed",
    "dimensions_total",
    "specialist_engines_detected",
    "specialist_engines_required",
    "qualified_references",
    "required_references",
    "external_evidence_score",
    "external_release_eligible",
    "blockers",
]
smart_dataframe(visible[columns], height=600, key="step160_quality_matrix")

st.download_button(
    "Download complete Step 160 module quality matrix",
    data=matrix.drop(columns=["checks"], errors="ignore").to_csv(index=False).encode("utf-8"),
    file_name="biointel_step160_module_quality_matrix.csv",
    mime="text/csv",
    width="stretch",
)

with st.expander("How 10/10 is calculated", expanded=False):
    st.markdown(
        "Each module must pass input contract, data integrity, deterministic execution, resource safety, failure isolation, provenance, result integrity, specialist-adapter planning, evidence gating and usable export controls. "
        "A module can therefore be internally 10/10 while still being blocked from confirmatory or clinical release because a third-party runtime, reference database or independent validation record is absent."
    )
    smart_json(summary, title="Step 160 quality summary", download_name="biointel_step160_quality_summary.json", key="step160_quality_summary")
    st.download_button(
        "Download JSON summary",
        data=json.dumps(summary, indent=2).encode("utf-8"),
        file_name="biointel_step160_quality_summary.json",
        mime="application/json",
        width="stretch",
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
