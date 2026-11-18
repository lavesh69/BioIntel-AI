from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.stability_v159.module_health import (  # noqa: E402
    page_source_health,
    reliability_summary,
    runtime_diagnostic_index,
    scientific_module_health,
)
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json  # noqa: E402
from biointel.ui.theme import apply_theme, hero, section_title  # noqa: E402

st.set_page_config(page_title="Module Reliability Command Center · BioIntel AI", page_icon="MR", layout="wide")
apply_theme()
hero(
    "Module Reliability Command Center",
    "Inspect internal contracts, specialist-runtime gaps, reference readiness, source integrity, resource pressure and protected failure diagnostics across the complete application.",
    eyebrow="BioIntel AI · Step 159 Runtime Resilience",
    chips=["Resource-aware execution", "Crash-loop circuit breaker", "Atomic diagnostics", "230-screen source audit", "Fail-closed science"],
)
scientific_boundary_banner(
    source_kind="reference",
    release_eligible=False,
    message="This command center verifies software-owned reliability controls. It does not manufacture external clinical, laboratory, regulatory or licensed-data evidence.",
)

@st.cache_data(ttl=60, show_spinner=False)
def _summary():
    return reliability_summary(ROOT)

@st.cache_data(ttl=120, show_spinner=False)
def _modules():
    return scientific_module_health(ROOT)

@st.cache_data(ttl=120, show_spinner=False)
def _pages():
    return page_source_health(ROOT)

summary = _summary()
metric_cards([
    ("Scientific modules", summary["scientific_modules"], "Registered profiles"),
    ("Internal complete", summary["internal_complete"], "Software-owned contracts"),
    ("Screens clean", f"{summary['pages_syntax_clean']}/{summary['pages']}", "Present and syntax-valid"),
    ("Protected diagnostics", summary["runtime_diagnostics"], "Redacted native failures"),
])

resources = summary["resources"]
resource_cols = st.columns(4)
resource_cols[0].metric("Available memory", f"{resources['available_memory_bytes'] / 1024**3:.1f} GiB")
resource_cols[1].metric("Memory pressure", f"{resources['memory_pressure'] * 100:.0f}%")
resource_cols[2].metric("CPU threads", resources["cpu_count"])
resource_cols[3].metric("Free disk", f"{resources['disk_free_bytes'] / 1024**3:.1f} GiB")

module_tab, page_tab, diagnostic_tab, manifest_tab = st.tabs(["Scientific modules", "Application screens", "Failure diagnostics", "Manifest"])
with module_tab:
    section_title("Module readiness matrix", "🧬")
    modules = _modules()
    view = st.selectbox(
        "Filter",
        ["All", "Specialist runtime incomplete", "References incomplete", "External validation required"],
        key="step159_module_filter",
    )
    module_view = modules.copy()
    if view == "Specialist runtime incomplete":
        module_view = module_view.loc[module_view.specialist_runtime_score < 100]
    elif view == "References incomplete":
        module_view = module_view.loc[module_view.reference_score < 100]
    elif view == "External validation required":
        module_view = module_view.loc[module_view.external_validation_required.astype(bool)]
    smart_dataframe(module_view, height=560, key="step159_module_health")
    st.download_button(
        "Download module health matrix",
        data=modules.to_csv(index=False).encode("utf-8"),
        file_name="biointel_step159_module_health.csv",
        mime="text/csv",
        width="stretch",
    )

with page_tab:
    section_title("Screen source qualification", "🖥️")
    pages = _pages()
    smart_dataframe(pages, height=560, key="step159_page_health")
    if not pages.empty and (not pages.exists.all() or not pages.syntax_ok.all()):
        st.error("One or more application screens require repair.")
    else:
        st.success("All registered application screens are present and syntax-valid.")

with diagnostic_tab:
    section_title("Protected native-failure diagnostics", "🛡️")
    diagnostics = runtime_diagnostic_index(ROOT)
    if diagnostics.empty:
        st.success("No persisted native-workflow failure diagnostics are present.")
    else:
        smart_dataframe(diagnostics, height=420, key="step159_diagnostics")
        st.caption("Files are locally stored with secret-bearing metadata redacted. Review them from System Diagnostics before deletion.")

with manifest_tab:
    smart_json(
        summary,
        title="Step 159 reliability manifest",
        download_name="biointel_step159_reliability_manifest.json",
        key="step159_reliability_manifest",
    )
    st.download_button(
        "Download JSON manifest",
        data=json.dumps(summary, indent=2, default=str).encode("utf-8"),
        file_name="biointel_step159_reliability_manifest.json",
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
