from __future__ import annotations

import sys
from pathlib import Path
import json
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.nextgen.intelligence import list_scenarios
from biointel.ui.components import metric_cards, scientific_chart_card, scientific_table
from biointel.ui.theme import apply_theme, hero

st.set_page_config(page_title="Scientific Scenario & Sensitivity Lab · BioIntel AI", page_icon="🧪", layout="wide")
apply_theme()
hero(
    "Scientific Scenario & Sensitivity Lab",
    "Compare saved threshold and prioritisation scenarios without overwriting the original scientific result.",
    eyebrow="BioIntel AI 13.2 · Step 132",
    chips=["Sensitivity", "Scenario history", "Assumption audit", "Reproducible comparison"],
)

scenarios = list_scenarios(ROOT)
if scenarios.empty:
    st.info("No saved scenarios yet. Run a next-generation module and open **Scientific intelligence → Scenario simulator**.")
    st.stop()

module_options = sorted(scenarios["module_key"].astype(str).unique().tolist())
selected_modules = st.multiselect("Modules", module_options, default=module_options[: min(3, len(module_options))])
filtered = scenarios[scenarios["module_key"].astype(str).isin(selected_modules)] if selected_modules else scenarios
metric_cards([
    ("Saved scenarios", len(filtered), "Current filter"),
    ("Modules", filtered["module_key"].nunique(), "Scientific domains"),
    ("Parameters", filtered["parameter"].nunique(), "Sensitivity dimensions"),
    ("Latest", filtered["created_at_utc"].max(), "UTC"),
])
scientific_table(filtered.drop(columns=["results_json", "values_json"], errors="ignore"), key="step130_scenarios", height=420, file_name="saved_scientific_scenarios.csv")

records = []
for _, row in filtered.head(100).iterrows():
    try:
        values = json.loads(row["results_json"])
    except Exception:
        values = []
    for item in values:
        records.append({"scenario_id": row["scenario_id"], "module_key": row["module_key"], **item})
long = pd.DataFrame(records)
if not long.empty and {"threshold", "result_rows"}.issubset(long.columns):
    long["threshold"] = pd.to_numeric(long["threshold"], errors="coerce")
    long["result_rows"] = pd.to_numeric(long["result_rows"], errors="coerce")
    plot = long.dropna(subset=["threshold", "result_rows"])
    if not plot.empty:
        fig = px.line(plot, x="threshold", y="result_rows", color="module_key", line_group="scenario_id", markers=True, title="Cross-module threshold sensitivity")
        scientific_chart_card(
            fig,
            title="Cross-module threshold sensitivity",
            interpretation="Compares candidate-count sensitivity across saved modules and scenarios.",
            data=plot,
            method="Saved deterministic scenario reruns",
            key="step130_cross_module_sensitivity",
            module_key="scenario_sensitivity_lab",
        )

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='scenario_sensitivity_lab', title='Scientific Scenario & Sensitivity Lab', category='Intelligence')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
