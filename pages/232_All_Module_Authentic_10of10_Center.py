from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.excellence_v163 import module_excellence_matrix, module_excellence_summary  # noqa: E402
from biointel.readiness_v161 import runtime_recipe_catalog  # noqa: E402
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe, smart_json  # noqa: E402
from biointel.ui.theme import apply_theme, hero, section_title  # noqa: E402

st.set_page_config(page_title="All-Module Authentic 10/10 · BioIntel AI", page_icon="X10", layout="wide")
apply_theme()
hero(
    "All-Module Authentic 10/10 Center",
    "Verify software-owned 10/10 controls, managed specialist adapters, task-specific benchmark specifications, reference acquisition manifests and fail-closed scientific release decisions across all modules.",
    eyebrow="BioIntel AI · Step 163 All-Module Excellence",
    chips=["80 module contracts", "53 runtime locks", "Task-specific benchmarks", "Authenticity guards", "No fake release claims"],
)
scientific_boundary_banner(
    source_kind="reference",
    release_eligible=False,
    message="Step 163 makes every software-owned module control complete and enforceable. Licensed tools, production database releases, independent studies, wet-lab evidence and regulatory outcomes remain external artifacts and are never fabricated.",
)


@st.cache_data(ttl=120, show_spinner=False)
def _matrix() -> pd.DataFrame:
    return module_excellence_matrix(ROOT)


@st.cache_data(ttl=120, show_spinner=False)
def _runtime() -> pd.DataFrame:
    return runtime_recipe_catalog()


matrix = _matrix()
runtime = _runtime()
summary = module_excellence_summary(matrix)
metric_cards(
    [
        ("Software-owned 10/10", f"{summary.get('software_owned_10of10', 0)}/{summary.get('modules', 0)}", "Every module"),
        ("Runtime adapter contracts", f"{len(runtime)}/{len(runtime)}", "Version/hash/self-test required"),
        ("Task-specific benchmark specs", f"{summary.get('benchmark_specs_10of10', 0)}/{summary.get('modules', 0)}", "Domain evidence template"),
        ("Real-world release eligible", summary.get("real_world_release_eligible", 0), "External evidence required"),
    ]
)

section_title("All-module excellence matrix", "X10")
view = st.selectbox(
    "View",
    ["All modules", "Specialist-engine modules", "Reference-heavy modules", "External actions remaining"],
    key="step163_view",
)
visible = matrix.copy()
if view == "Specialist-engine modules":
    visible = visible.loc[visible["specialist_engines_required"] > 0]
elif view == "Reference-heavy modules":
    visible = visible.sort_values(["production_references_required", "title"], ascending=[False, True])
elif view == "External actions remaining":
    visible = visible.loc[~visible["real_world_release_eligible"].astype(bool)]
smart_dataframe(visible, height=620, key="step163_matrix")
st.download_button(
    "Download Step 163 module excellence matrix",
    matrix.to_csv(index=False).encode("utf-8"),
    "biointel_step163_module_excellence_matrix.csv",
    "text/csv",
    width="stretch",
)

section_title("Specialist runtime lock contracts", "RT")
smart_dataframe(runtime, height=480, key="step163_runtime")
st.caption("Each engine has a provisioning strategy, version probe, checksum requirement, protected execution plan and runtime self-test requirement. Availability and licensing are detected separately from contract completeness.")

section_title("What 10/10 means", "TR")
smart_json(
    {
        "10_of_10_software_owned": [
            "Input integrity and schema checks",
            "Deterministic native execution",
            "Bounded memory and crash-loop protection",
            "Complete output and reproducibility manifests",
            "Managed specialist-tool adapter and lock contract",
            "Production-reference acquisition and qualification manifest",
            "Task-specific benchmark and acceptance specification",
            "Synthetic/wrong-domain model quarantine",
            "Uncertainty, limitations and claim policy",
            "Fail-closed external release decision",
        ],
        "still_requires_real_external_artifacts": [
            "Licensed or separately installed specialist tools/model weights",
            "Complete production database releases",
            "Task-specific authentic cohorts",
            "Independent and prospective validation",
            "Wet-lab or orthogonal confirmation",
            "Domain expert, clinical or regulatory approval where applicable",
        ],
    },
    title="Step 163 rating policy",
    key="step163_policy",
)
st.download_button(
    "Download summary JSON",
    json.dumps(summary, indent=2).encode("utf-8"),
    "biointel_step163_summary.json",
    "application/json",
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
