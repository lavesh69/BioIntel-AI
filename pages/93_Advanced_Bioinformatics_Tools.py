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

from biointel.tools.runtime import export_toolchain_lock, load_manifest, toolchain_preflight, tools_home
from biointel.ui.components import metric_cards, smart_dataframe, smart_json
from biointel.ui.theme import apply_theme, badge, hero, insight_callout, section_title

st.set_page_config(page_title="BioIntel Scientific Engine Center · BioIntel AI", page_icon="🧰", layout="wide")
apply_theme()
hero(
    "BioIntel Scientific Engine Center",
    "Detect BioIntel-managed runtimes, probe qualified versions, score module readiness, separate reference assets and export a reproducible BioIntel environment lock.",
    eyebrow="BioIntel AI · Step 95 toolchain upgrade",
    chips=["Native Windows", "WSL/Bioconda", "Version audit", "Module readiness", "Database provenance", "Lock export"],
)

include_versions = st.toggle("Probe installed tool versions", value=False, help="This launches detected executables with their version flags and may take several seconds.")
with st.spinner("Auditing the local scientific toolchain..."):
    report = toolchain_preflight(include_versions=include_versions)
frame = pd.DataFrame(report["tools"])
module_frame = pd.DataFrame(report["modules"])
summary = report["summary"]
metric_cards([
    ("Registered BioIntel engines", summary["registered"], None), ("Ready", summary["available"], None),
    ("Setup required", summary["missing"], None), ("Engine coverage", f"{summary['coverage']:.0%}", None),
    ("Managed runtime home", summary["tools_home"], None),
])
if summary["coverage"] == 1:
    badge("● Full registered toolchain detected", "success")
elif summary["available"]:
    badge(f"● Partial toolchain detected · {summary['available']}/{summary['registered']} ready", "warning")
else:
    badge("● Tool manager integrated · install executables before real command execution", "warning")

availability_tab, readiness_tab, database_tab, install_tab, lock_tab = st.tabs(["Tool availability", "Module readiness", "Reference databases", "Install/repair", "Reproducibility lock"])
with availability_tab:
    display = ["id", "tool", "category", "available", "backend", "purpose", "database_required"]
    if include_versions and "version" in frame:
        display.insert(4, "version")
    smart_dataframe(frame[display], height=620, key="advanced_tool_status_pro")
    public_export = frame.drop(columns=[column for column in ("executable", "path_or_command") if column in frame], errors="ignore")
    st.download_button("Export BioIntel engine status CSV", public_export.to_csv(index=False).encode(), "biointel_engine_status.csv", "text/csv")

with readiness_tab:
    st.plotly_chart(px.bar(module_frame.sort_values("readiness"), x="readiness", y="module", orientation="h", range_x=[0, 1], title="Scientific module execution readiness"), width="stretch")
    smart_dataframe(module_frame, height=450, key="tool_module_readiness")
    insight_callout("Readiness meaning", "A 100% tool score means registered executables were detected. It does not confirm reference databases, sample suitability, parameter validation or biological correctness.", tone="info")

with database_tab:
    database_rows = frame[frame["database_required"]][["tool", "database_note", "available", "backend"]].rename(columns={"tool": "Tool", "database_note": "Database boundary"})
    smart_dataframe(database_rows, height=500, key="advanced_tool_databases_pro")
    st.info("Large and frequently updated reference assets remain separate. Record provider, release, licence, download date and SHA-256 in the project evidence registry.")

with install_tab:
    section_title("Windows installer", "⚙️")
    st.code("INSTALL_ADVANCED_TOOLS_WINDOWS.bat", language="text")
    st.markdown(
        """
The installer supports two controlled layers:

1. **BioIntel portable core** for verified Windows-compatible components.
2. **BioIntel WSL scientific suite** for Linux-first workflows.

Archives are cached, wrappers are repaired on re-run, and large databases are kept outside the application package. This avoids silently shipping stale or license-restricted database snapshots.
"""
    )
    manifest = load_manifest()
    smart_json({"registered_tools": len(manifest.get("tools", [])), "tools_home": str(tools_home()), "installer": str(ROOT / "INSTALL_ADVANCED_TOOLS_WINDOWS.bat")}, key="advanced_tools_install_info")

with lock_tab:
    lock = export_toolchain_lock(include_versions=include_versions)
    smart_json(lock["module_readiness"], key="toolchain_lock_preview")
    st.download_button("Download toolchain lock JSON", json.dumps(lock, indent=2, default=str).encode(), "biointel_toolchain_lock.json", "application/json", width="stretch")
    insight_callout("Reproducibility", "Attach the exported lock to reports and workflows. Re-run version probing after any tool update, WSL environment change or database refresh.", tone="info")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
