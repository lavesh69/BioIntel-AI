from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.realworld import build_step42_maximum_evidence  # noqa: E402
from biointel.ui.components import smart_dataframe  # noqa: E402
from biointel.ui.theme import apply_theme, badge, hero, insight_callout, section_title  # noqa: E402

st.set_page_config(page_title="Maximum Verifiable Evidence · BioIntel AI", page_icon="🏭", layout="wide")
apply_theme()


@st.cache_data(ttl=30, show_spinner=False)
def _load(root_text: str) -> dict[str, object]:
    return build_step42_maximum_evidence(Path(root_text))


report = _load(str(ROOT))
frame = pd.DataFrame(report["capabilities"])
integrity = report["artifact_integrity"]

hero(
    "Maximum Verifiable Operations Evidence",
    "Separate what the repository implements, what has been measured and checksum-verified, and what still requires genuine customers, regulators, journals or production operating history.",
    eyebrow="Maximum non-fabricated operational evidence",
    chips=[
        f"Implementation {report['implementation_average']:.1f}/10",
        f"Verifiable {report['verifiable_average']:.1f}/10",
        f"Authentic external {report['authentic_external_average']:.1f}/10",
        f"{integrity['verified_count']}/{integrity['artifact_count']} artifacts verified",
    ],
)

badge(
    "● Checksum-bound measured evidence verified" if integrity["ok"] else "● Evidence artifact integrity requires attention",
    "success" if integrity["ok"] else "danger",
)
insight_callout(
    "Three evidence levels",
    "Implementation readiness can reach 10/10 through code and controls. Verifiable evidence comes from measured load, restore, isolation, failover, deployment and reproducibility qualification. Authentic external evidence requires independent customers, regulators, journals, laboratories or real production history.",
    "info",
)

metrics = st.columns(6)
metrics[0].metric("Implementation", f"{report['implementation_average']:.1f}/10")
metrics[1].metric("Verifiable evidence", f"{report['verifiable_average']:.1f}/10")
metrics[2].metric("External evidence", f"{report['authentic_external_average']:.1f}/10")
metrics[3].metric("Strong areas", report["strong_verifiable_areas"])
metrics[4].metric("Evidence artifacts", integrity["artifact_count"])
metrics[5].metric("Integrity failures", len(integrity["failures"]))

matrix_tab, measured_tab, artifacts_tab, external_tab = st.tabs(
    ["Three-score matrix", "Measured qualification", "Artifact integrity", "External proof still required"]
)

with matrix_tab:
    chart_frame = frame[frame["key"] != "overall_platform_maturity"].sort_values("maximum_current_score")
    chart = px.bar(
        chart_frame,
        x=["implementation_score", "verifiable_score", "authentic_external_score"],
        y="label",
        orientation="h",
        barmode="group",
        range_x=[0, 10],
        labels={"value": "Score", "label": "Area", "variable": "Evidence level"},
    )
    chart.update_layout(height=max(760, len(chart_frame) * 44), legend_title_text="")
    st.plotly_chart(chart, width="stretch")

    display = frame.rename(
        columns={
            "label": "Area",
            "implementation_score": "Implementation",
            "verifiable_score": "Measured/verifiable",
            "authentic_external_score": "Authentic external",
            "maximum_current_score": "Current maximum",
            "ceiling_without_external_evidence": "Internal ceiling",
            "evidence_level": "Evidence level",
        }
    )
    smart_dataframe(
        display[["Area", "Implementation", "Measured/verifiable", "Authentic external", "Current maximum", "Internal ceiling", "Evidence level"]],
        height=760,
        columns={
            "Implementation": st.column_config.ProgressColumn("Implementation", min_value=0, max_value=10, format="%.1f"),
            "Measured/verifiable": st.column_config.ProgressColumn("Measured/verifiable", min_value=0, max_value=10, format="%.1f"),
            "Authentic external": st.column_config.ProgressColumn("Authentic external", min_value=0, max_value=10, format="%.1f"),
            "Current maximum": st.column_config.ProgressColumn("Current maximum", min_value=0, max_value=10, format="%.1f"),
        },
    )

with measured_tab:
    section_title("Executed qualification evidence", "📏")
    status_rows = [
        {"Measurement": key.replace("_", " ").title(), "Passed": bool(value)}
        for key, value in report["measurement_status"].items()
    ]
    smart_dataframe(pd.DataFrame(status_rows), height=520)
    st.code(
        "python scripts/run_step42_verifiable_evidence.py --load-requests 400 --tenant-iterations 1000\n"
        "python scripts/qualify_step42_maximum_evidence.py",
        language="bash",
    )
    insight_callout(
        "Measured in this release",
        "The evidence pack includes all-database checksum restore, 1,000 tenant isolation and traversal-denial checks, concurrent API load, primary-to-secondary service failover, Helm/Kubernetes controls, cloud IaC, publication reproducibility, GxP/security controls and SLSA-compatible provenance.",
        "success",
    )

with artifacts_tab:
    section_title("Cryptographic evidence index", "🔐")
    artifact_rows = [
        {"Artifact": key, "Verified": value}
        for key, value in integrity["verified"].items()
    ]
    smart_dataframe(pd.DataFrame(artifact_rows), height=570)
    st.code(json.dumps(integrity, indent=2, sort_keys=True), language="json")

with external_tab:
    missing_rows: list[dict[str, object]] = []
    for row in report["capabilities"]:
        if row["authentic_external_score"] >= 10:
            continue
        missing_rows.append(
            {
                "Area": row["label"],
                "Measured score": row["verifiable_score"],
                "Maximum without external proof": row["ceiling_without_external_evidence"],
                "External proof needed": " • ".join(row["missing_external_proof"]),
            }
        )
    smart_dataframe(pd.DataFrame(missing_rows), height=760)
    insight_callout(
        "No fabricated claims",
        "A customer signature, DOI, regulatory decision, inspection result, multi-site laboratory outcome or 90-day production history is never inferred from local tests. Importing authentic signed evidence through the validation evidence registry can raise the corresponding external score to 10/10.",
        "warning",
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
