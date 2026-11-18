from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.runtime_v170 import Step170Registry, engine_catalog, licence_catalog, qualification_matrix, reference_catalog
from biointel.ui.components import metric_cards, scientific_boundary_banner, smart_dataframe
from biointel.ui.operational_canvas import render_operational_canvas
from biointel.ui.theme import apply_theme, hero, section_title

st.set_page_config(page_title="Specialist Runtime & References · BioIntel AI", page_icon="R170", layout="wide")
apply_theme()
hero(
    "Specialist Runtime & Reference Qualification",
    "Install, fingerprint and qualify 53 specialist engines plus production reference releases without embedding multi-GB/TB or licence-controlled assets inside the application archives.",
    eyebrow="BioIntel AI · Step 170 · v14.2.0",
    chips=["53 engine manifests", "WSL2 + micromamba", "Licence gates", "SHA-256", "Fail closed"],
)
scientific_boundary_banner(
    source_kind="reference",
    release_eligible=False,
    message=(
        "A provisioning recipe is not an installed runtime. A completed download is not a qualified production reference. "
        "Qualification requires a pinned release, local SHA-256, provider checksum where available, captured licence evidence, "
        "schema validation, smoke/golden/negative-control tests and a named scientific reviewer."
    ),
)
registry = Step170Registry(ROOT)
status = registry.status()
engines = engine_catalog()
refs = reference_catalog()
licences = licence_catalog()


def _scientific_runtime_report() -> dict[str, object]:
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    user_data = Path(os.environ.get("BIOINTEL_USER_DATA_DIR", local / "BioIntelAI" / "UserData"))
    path = user_data / "reports" / "step196-scientific-runtime-setup.json"
    if not path.is_file():
        return {"runtime_state": "not-yet-started", "message": "Run INSTALL_WINDOWS.bat. The current installer prepares public specialist runtimes in the background after its verified core setup."}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"runtime_state": "report-unavailable", "message": f"Could not read local setup report: {type(exc).__name__}"}
    return payload if isinstance(payload, dict) else {"runtime_state": "report-unavailable", "message": "Local setup report is not a JSON object."}


state = qualification_matrix(ROOT)
engine_state = state.loc[state["kind"] == "engine"]
reference_state = state.loc[state["kind"] == "reference"]
runtime_report = _scientific_runtime_report()
metric_cards([
    ("Specialist engines", "53/53", "Provisioning manifests"),
    ("Installed on this host", str(status.get("engines_installed", 0)), "Qualification remains separate"),
    ("Reference groups", str(len(refs)), "Production catalog"),
    ("Downloaded references", str(status.get("references_downloaded", 0)), "Qualification remains separate"),
])

tab0, tab1, tab2, tab3, tab4 = st.tabs(["Installer readiness", "Engine catalog", "Reference catalog", "Licences", "Qualification state"])
with tab0:
    section_title("Automatic local readiness", "AR")
    render_operational_canvas(
        "Weak-module runtime acquisition",
        {
            "Current installer state": runtime_report.get("runtime_state", "not-yet-started"),
            "Weak modules targeted": runtime_report.get("targeted_weak_module_count", 25),
            "Targeted automatic engines": runtime_report.get("targeted_automatic_engines", 34),
            "Targeted manual/provider engines": runtime_report.get("targeted_manual_or_provider_engines", 5),
            "Small public references targeted": runtime_report.get("targeted_automatic_references", 7),
            "Installed engine records": int(engine_state.get("installed", []).sum()) if "installed" in engine_state else 0,
            "Downloaded reference records": int(reference_state.get("downloaded", []).sum()) if "downloaded" in reference_state else 0,
            "Qualified engines": int(engine_state.get("qualified", []).sum()) if "qualified" in engine_state else 0,
            "Qualified references": int(reference_state.get("qualified", []).sum()) if "qualified" in reference_state else 0,
            "Message": runtime_report.get("message", ""),
        },
        workflow=("Verified core install", "Public runtime acquisition", "Installed-state import", "Scientific qualification"),
    )
    st.caption(
        "INSTALL_WINDOWS.bat starts this background preparation automatically. WSL2/Ubuntu, storage and network availability are checked safely; "
        "provider-authorised tools, very-large references and external evidence are never falsely auto-completed."
    )
with tab1:
    section_title("Specialist runtime catalog", "Automatic, provider-managed and manual-authorized routes")
    smart_dataframe(engines, height=620, key="step170_engines")
    st.download_button("Download engine catalog", engines.to_csv(index=False).encode(), "step170_engine_catalog.csv", "text/csv", width="stretch")
with tab2:
    section_title("Production reference catalog", "Release pinning, checksums, schema validation and scientific review")
    smart_dataframe(refs, height=620, key="step170_refs")
    st.download_button("Download reference catalog", refs.to_csv(index=False).encode(), "step170_reference_catalog.csv", "text/csv", width="stretch")
with tab3:
    section_title("Licence policies", "BioIntel records terms; it does not silently accept provider licences")
    smart_dataframe(licences, height=520, key="step170_licences")
with tab4:
    section_title("Current deployment qualification", "Registry-derived and fail-closed")
    smart_dataframe(state, height=620, key="step170_state")
    st.download_button("Download qualification state", state.to_csv(index=False).encode(), "step170_qualification_state.csv", "text/csv", width="stretch")

st.info("Use only INSTALL_WINDOWS.bat, then RUN_BOTH_WINDOWS.bat. The installer manages the public runtime/reference preparation internally and records a calm pending state if Windows, network, licensing or storage requirements are not yet available.")

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
