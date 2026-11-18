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

from biointel.ui.components import scientific_boundary_banner, smart_dataframe
from biointel.ui.operational_canvas import render_operational_canvas
from biointel.ui.theme import apply_theme, hero, section_title
from biointel.ui.visual_polish import render_metric_board
from biointel.universal_platform_v189 import PROFILES, rating_matrix, validate_module
from biointel.universal_platform_v189.generator import module_folder, shared_db
from biointel.universal_platform_v189.platform import connect


st.set_page_config(
    page_title="Step 189 Universal Production Platform · BioIntel AI",
    page_icon="🧬",
    layout="wide",
)
apply_theme()
frame = rating_matrix(ROOT)
qualified = int(frame.qualified_10_of_10.sum())

hero(
    "Step 189 · Universal Production Platform",
    "A shared operational layer for projects, samples, engines, references, jobs, provenance, handoffs, reporting, monitoring, review and diagnostics.",
    eyebrow="Shared services · operational traceability · evidence-bound release",
    chips=["Projects & samples", "Jobs & recovery", "Provenance", "No automatic release"],
)
scientific_boundary_banner(
    source_kind="universal_production_platform",
    release_eligible=False,
    message="Shared services and local operational controls do not replace licensed engines, authorised databases, clinical or wet-lab evidence, independent review or formal release approval.",
)
render_metric_board(
    [
        ("Modules qualified", f"{qualified}/{len(frame)}", "Internal platform-dimension status.", "success"),
        ("Average rating", f"{frame.after_step189_rating.mean():.2f}/10", "Software-owned platform assessment.", "info"),
        ("Platform dimensions", f"{int(frame.dimensions_passed.sum())}/{int(frame.dimensions_total.sum())}", "Documented shared-service controls.", "neutral"),
        ("Controlled release", "PENDING", "External evidence and approvals remain required.", "warning"),
    ]
)

portfolio_tab, services_tab, module_tab = st.tabs([
    "Platform portfolio", "Shared services", "Module readiness"
])

with portfolio_tab:
    section_title("Platform readiness portfolio", "📊")
    smart_dataframe(frame, height=620, key="step189_portfolio")
    st.download_button(
        "Download platform rating matrix",
        frame.to_csv(index=False).encode("utf-8"),
        "step189_platform_rating_matrix.csv",
        "text/csv",
        width="stretch",
    )

with services_tab:
    section_title("Shared-service registry", "🗄️")
    with connect(shared_db(ROOT)) as conn:
        counts = [
            {"Service": name.replace("_", " ").title(), "Records": conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]}
            for name in (
                "projects", "samples", "assets", "engines", "references_registry", "jobs",
                "handoffs", "provenance", "reviews", "metrics", "errors",
            )
        ]
    smart_dataframe(pd.DataFrame(counts), height=430, key="step189_services")

with module_tab:
    section_title("Module production-readiness workbench", "🧭")
    module = st.selectbox("Inspect module", list(PROFILES), format_func=lambda key: PROFILES[key].title)
    result = validate_module(ROOT, module)
    folder = module_folder(ROOT, module)
    render_operational_canvas(
        "Module platform readiness",
        {"module": module, "rating": result.rating, "qualified": result.qualified_10_of_10, "blockers": result.blockers},
        workflow=("Preflight", "Projects & samples", "Jobs & recovery", "Review"),
    )
    engines_tab, references_tab, preflight_tab = st.tabs(["Engine status", "Reference status", "Preflight"])
    with engines_tab:
        smart_dataframe(pd.read_csv(folder / "engine_status.csv"), height=420, key=f"step189_engines_{module}")
    with references_tab:
        smart_dataframe(pd.read_csv(folder / "reference_status.csv"), height=420, key=f"step189_refs_{module}")
    with preflight_tab:
        render_operational_canvas(
            "Preflight outcome",
            json.loads((folder / "preflight.json").read_text(encoding="utf-8")),
            workflow=("System checks", "Reference checks", "Queue checks", "Ready state"),
        )
