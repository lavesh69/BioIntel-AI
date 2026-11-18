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

from biointel.scientific_execution_v190 import PROFILES, rating_matrix, validate_module
from biointel.scientific_execution_v190.generator import connect, module_folder, shared_db
from biointel.ui.components import scientific_boundary_banner, smart_dataframe
from biointel.ui.operational_canvas import render_operational_canvas
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.visual_polish import render_metric_board


st.set_page_config(
    page_title="Step 190 Scientific Execution & Interoperability · BioIntel AI",
    page_icon="🧪",
    layout="wide",
)
apply_theme()
frame = rating_matrix(ROOT)
qualified = int(frame.qualified_10_of_10.sum())

hero(
    "Step 190 · Scientific Execution & Interoperability",
    "Review deterministic execution, specialist-engine readiness, standards bridges, truth benchmarks, streaming, viewers, uncertainty and update-impact controls.",
    eyebrow="Native execution · standards bridge · evidence-aware interoperability",
    chips=["Execution matrix", "Format bridges", "Truth benchmarks", "Fail-closed release"],
)
scientific_boundary_banner(
    source_kind="scientific_execution_interoperability",
    release_eligible=False,
    message="A compatibility bridge is not formal standards certification. External engines, official licensed references and independent scientific evidence remain separate controlled-release requirements.",
)
render_metric_board(
    [
        ("Modules qualified", f"{qualified}/{len(frame)}", "Internal execution-control status.", "success"),
        ("Average rating", f"{frame.after_step190_rating.mean():.2f}/10", "Software-owned execution assessment.", "info"),
        ("Execution controls", f"{int(frame.dimensions_passed.sum())}/{int(frame.dimensions_total.sum())}", "Documented execution and bridge controls.", "neutral"),
        ("Controlled release", "PENDING", "External evidence and approvals remain required.", "warning"),
    ]
)

portfolio_tab, registry_tab, module_tab = st.tabs([
    "Execution portfolio", "Execution registry", "Module workbench"
])
with portfolio_tab:
    section_title("Scientific execution portfolio", "📊")
    smart_dataframe(frame, height=620, key="step190_portfolio")
    st.download_button(
        "Download execution rating matrix",
        frame.to_csv(index=False).encode("utf-8"),
        "step190_execution_rating_matrix.csv",
        "text/csv",
        width="stretch",
    )

with registry_tab:
    section_title("Execution registry", "🗄️")
    with connect(shared_db(ROOT)) as conn:
        counts = [
            {"Service": name.replace("_", " ").title(), "Records": conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]}
            for name in ("module_runs", "engine_matrix", "benchmark_metrics", "standard_artifacts")
        ]
    smart_dataframe(pd.DataFrame(counts), height=360, key="step190_registry")

with module_tab:
    section_title("Module execution workbench", "🧭")
    module = st.selectbox("Inspect module", list(PROFILES), format_func=lambda key: PROFILES[key].title)
    result = validate_module(ROOT, module)
    folder = module_folder(ROOT, module)
    render_operational_canvas(
        "Scientific execution readiness",
        {"module": module, "rating": result.rating, "qualified": result.qualified_10_of_10, "blockers": result.blockers},
        workflow=("Input", "Execution", "Interoperability", "Qualification"),
    )
    engine_tab, benchmark_tab, bridge_tab, readiness_tab = st.tabs(["Engine adapters", "Truth benchmarks", "Format bridge", "Readiness"])
    with engine_tab:
        smart_dataframe(pd.read_csv(folder / "engine_adapter_matrix.csv"), height=420, key=f"step190_engines_{module}")
    with benchmark_tab:
        smart_dataframe(pd.read_csv(folder / "truth_benchmark_metrics.csv"), height=420, key=f"step190_benchmarks_{module}")
    with bridge_tab:
        smart_dataframe(pd.read_csv(folder / "standard_formats" / "format_bridge_manifest.csv"), height=420, key=f"step190_bridge_{module}")
    with readiness_tab:
        render_operational_canvas(
            "Production-readiness matrix",
            json.loads((folder / "production_readiness_matrix.json").read_text(encoding="utf-8")),
            workflow=("Inputs", "Native execution", "Standards bridge", "Evidence boundary"),
        )
