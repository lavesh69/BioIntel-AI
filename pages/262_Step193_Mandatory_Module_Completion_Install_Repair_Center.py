from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.mandatory_completion_v193 import MANDATORY_DIMENSIONS, PROFILES, database_path, rating_matrix
from biointel.ui.components import scientific_boundary_banner, smart_dataframe
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.visual_polish import render_metric_board


st.set_page_config(
    page_title="Step 193 Mandatory Completion & Install Repair · BioIntel AI",
    page_icon="🛡️",
    layout="wide",
)
apply_theme()
frame = rating_matrix(ROOT)
qualified = int(frame.qualified.sum())

hero(
    "Step 193 · Mandatory Completion & Install Repair",
    "A clear operational overview of mandatory module controls, completeness status and the local shared-state baseline used by installation and repair workflows.",
    eyebrow="Mandatory controls · install resilience · external evidence remains separate",
    chips=["Mandatory dimensions", "Local completeness", "Repair-aware", "Fail-closed release"],
)
scientific_boundary_banner(
    source_kind="mandatory_module_completion",
    release_eligible=False,
    message="This centre validates software and module completeness. It does not manufacture wet-lab, clinical, instrument, licensed-data, independent-review or regulatory evidence.",
)
render_metric_board(
    [
        ("Modules", f"{qualified}/{len(frame)}", "Modules meeting the local completion check.", "success"),
        ("Mandatory controls", f"{int(frame.checks_passed.sum())}/{int(frame.checks_total.sum())}", "Documented mandatory control checks.", "info"),
        ("Internal rating", f"{frame.after_step193_rating.mean():.2f}/10", "Software-owned completeness assessment.", "neutral"),
        ("Controlled release", "EXTERNAL EVIDENCE PENDING", "Formal release requires independent evidence.", "warning"),
    ]
)

portfolio_tab, controls_tab, state_tab = st.tabs([
    "Completion portfolio", "Mandatory controls", "Shared-state overview"
])
with portfolio_tab:
    section_title("Module completion matrix", "📊")
    smart_dataframe(frame, height=620, key="step193_matrix")
    st.download_button(
        "Download mandatory completion matrix",
        frame.to_csv(index=False).encode("utf-8"),
        "step193_mandatory_completion_matrix.csv",
        "text/csv",
        width="stretch",
    )
with controls_tab:
    section_title("Mandatory dimensions", "✓")
    smart_dataframe(
        pd.DataFrame({"Dimension": MANDATORY_DIMENSIONS, "Required": True}),
        height=500,
        key="step193_dimensions",
    )
with state_tab:
    section_title("Shared-state overview", "🗄️")
    st.caption(f"Local shared-state database: {database_path(ROOT).name}")
    selected = st.selectbox("Inspect module profile", list(PROFILES), format_func=lambda key: PROFILES[key].title)
    profile = PROFILES[selected]
    smart_dataframe(pd.DataFrame([profile.__dict__]), height=260, key="step193_profile")
