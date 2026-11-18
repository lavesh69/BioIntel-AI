from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import json
import streamlit as st

from biointel.privacy import build_privacy_inventory, clear_local_activity, export_local_activity
from biointel.ui.theme import apply_theme, badge, hero, insight_callout, section_title

ROOT = Path(__file__).resolve().parents[1]
st.set_page_config(page_title="Privacy & Security · BioIntel AI", page_icon="🔐", layout="wide")
apply_theme()

hero(
    "Privacy & Security Center",
    "Understand data handling, connected-provider boundaries and local privacy controls before deployment or store publication.",
    eyebrow="BioIntel AI · Local-first privacy · Research-use boundaries",
    chips=["No advertising SDK", "No cross-app tracking", "Explicit provider actions", "Local export controls"],
)

inventory = build_privacy_inventory(ROOT)
badge("● Research and education use · not medical diagnosis or treatment advice", "warning")

section_title("Data-handling inventory", "▤")
st.dataframe(
    inventory["categories"],
    width="stretch",
    hide_index=True,
    column_config={
        "shared_by_default": st.column_config.CheckboxColumn("Shared automatically"),
    },
)
insight_callout("External-provider rule", inventory["external_provider_rule"], tone="info")

left, right = st.columns(2)
with left:
    section_title("Local records", "◫")
    for key, value in inventory["local_records"].items():
        st.metric(key.replace("_", " ").title(), "Unavailable" if value is None else str(value))
with right:
    section_title("Operator controls", "⚙")
    export_bytes = export_local_activity(ROOT)
    st.download_button(
        "Export local privacy/activity bundle",
        data=export_bytes,
        file_name="biointel-local-activity-export.zip",
        mime="application/zip",
        width="stretch",
    )
    confirm = st.checkbox(
        "I understand this clears local preferences and text activity logs but preserves scientific datasets, models and regulated database records."
    )
    if st.button("Clear local preferences and text logs", disabled=not confirm, width="stretch"):
        result = clear_local_activity(ROOT)
        if result["completed"]:
            st.success(f"Cleared {len(result['removed'])} local file(s).")
        else:
            st.error("Some files could not be removed.")
            st.code(json.dumps(result, indent=2))

section_title("Policy documents", "§")
privacy_text = (ROOT / "docs" / "legal" / "PRIVACY_POLICY.md").read_text(encoding="utf-8")
terms_text = (ROOT / "docs" / "legal" / "TERMS_OF_USE.md").read_text(encoding="utf-8")
policy_tab, terms_tab = st.tabs(["Privacy Policy", "Terms of Use"])
with policy_tab:
    st.markdown(privacy_text)
with terms_tab:
    st.markdown(terms_text)

st.info(
    "Before public submission, the publishing organisation must provide its real legal identity, support channel and public policy URL. The repository intentionally does not invent those external details."
)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='privacy_security', title='Privacy & Security', category='Settings')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
