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

from biointel.production_enablement_v217 import (
    readiness_table_rows,
    scan_production_enablement,
)
from biointel.ui.theme import apply_theme, hero, section_title

st.set_page_config(
    page_title="Production Enablement Center · BioIntel AI",
    page_icon=":material/fact_check:",
    layout="wide",
)
apply_theme()


@st.cache_data(ttl="30s", max_entries=4, show_spinner=False)
def _snapshot(root_text: str) -> dict[str, object]:
    return scan_production_enablement(Path(root_text))


report = _snapshot(str(ROOT))
engine = report["engine_inventory"]
models = report["model_inventory"]

hero(
    "Production Enablement Center",
    "Release controls for scientific execution, enterprise deployment, interoperability and external evidence.",
    eyebrow="Step217 · V20.0 · Fail-closed production controls",
    chips=[
        f"{report['internal_controls_ready']}/{report['capability_count']} controls installed",
        f"{engine['qualified_on_target']}/{engine['registered']} engines qualified",
        f"{models['qualified_candidates']} qualified model candidates",
        f"{len(report['p0_blockers'])} P0 evidence blockers",
    ],
)

with st.container(horizontal=True):
    st.metric(
        "Internal controls",
        f"{report['internal_controls_ready']}/{report['capability_count']}",
        "installed",
        border=True,
    )
    st.metric(
        "Release eligible",
        f"{report['release_eligible_capabilities']}/{report['capability_count']}",
        "evidence-gated",
        border=True,
    )
    st.metric(
        "Qualified engines",
        f"{engine['qualified_on_target']}/{engine['registered']}",
        "target machine",
        border=True,
    )
    st.metric(
        "Qualified models",
        models["qualified_candidates"],
        f"{models['synthetic_demo_quarantined']} demo quarantined",
        border=True,
    )

if report["p0_blockers"]:
    st.warning(
        "P0 release remains blocked: " + ", ".join(report["p0_blockers"]),
        icon=":material/warning:",
    )
else:
    st.success("All P0 production-enablement gates are satisfied.", icon=":material/check_circle:")

view = st.segmented_control(
    "View",
    ["Priorities", "Evidence blockers", "Architecture"],
    default="Priorities",
)

if view == "Priorities":
    priorities = st.pills(
        "Priority",
        ["P0", "P1", "P2", "External"],
        default=["P0", "P1"],
        selection_mode="multi",
    )
    rows = [
        row
        for row in readiness_table_rows(report)
        if not priorities or row["Priority"] in priorities
    ]
    st.dataframe(
        pd.DataFrame(rows),
        width="stretch",
        hide_index=True,
        column_config={
            "Priority": st.column_config.TextColumn("Priority", pinned=True),
            "Capability": st.column_config.TextColumn("Capability", width="large"),
            "Control": st.column_config.TextColumn("Control"),
            "Evidence": st.column_config.TextColumn("Evidence"),
            "Release eligible": st.column_config.CheckboxColumn("Release eligible"),
            "Detail": st.column_config.TextColumn("Detail", width="large"),
        },
    )
elif view == "Evidence blockers":
    blocker_rows = []
    for capability in report["capabilities"]:
        for blocker in capability["blockers"]:
            blocker_rows.append(
                {
                    "Priority": capability["priority"],
                    "Capability": capability["feature"],
                    "Blocker": blocker,
                    "External input": ", ".join(capability["external_inputs"]),
                }
            )
    st.dataframe(
        pd.DataFrame(blocker_rows),
        width="stretch",
        hide_index=True,
        column_config={
            "Priority": st.column_config.TextColumn("Priority", pinned=True),
            "Capability": st.column_config.TextColumn("Capability", width="large"),
            "Blocker": st.column_config.TextColumn("Blocker", width="large"),
            "External input": st.column_config.TextColumn("External input", width="large"),
        },
    )
else:
    architecture = report["information_architecture"]
    section_title("Workspace surfaces", ":material/account_tree:")
    architecture_rows = [
        {"Surface": key, "Pages": value}
        for key, value in architecture.items()
        if key != "Total"
    ]
    st.dataframe(
        pd.DataFrame(architecture_rows),
        width="stretch",
        hide_index=True,
        column_config={
            "Surface": st.column_config.TextColumn("Surface", pinned=True),
            "Pages": st.column_config.NumberColumn("Pages", format="%d"),
        },
    )
    st.caption(
        "Operational modules are the default discovery surface. Platform, assurance and internal implementation pages remain available through explicit filters."
    )

st.caption(report["claim_boundary"])
st.download_button(
    "Download Step217 readiness report",
    data=json.dumps(report, indent=2, sort_keys=True),
    file_name="biointel-step217-production-enablement.json",
    mime="application/json",
    icon=":material/download:",
)
