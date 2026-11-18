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

from biointel.release_integrity_v192.audit import run_release_audit
from biointel.ui.components import scientific_boundary_banner, smart_dataframe
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title
from biointel.ui.visual_polish import render_metric_board

st.set_page_config(page_title="Step 192 Release Integrity · BioIntel AI", page_icon="🛡️", layout="wide")
apply_theme()
hero(
    "Step 192 · Release Integrity & Publication Center",
    "Verifies current-version consistency, offline wheelhouse health, module publication assets, page safety, database integrity and fail-closed release boundaries.",
    eyebrow="Verified packaging · recoverable installation · honest scientific claims",
)
scientific_boundary_banner(
    source_kind="release_integrity",
    release_eligible=False,
    message="A passing local package audit verifies release mechanics, not external scientific, regulatory, licensing or publication approval.",
)

@st.cache_data(show_spinner=False)
def _audit() -> dict:
    return run_release_audit(ROOT, deep_hashes=False)

result = _audit()
release_audit_passed = bool(result["passed"])
render_metric_board(
    [
        ("Release audit", "PASS" if release_audit_passed else "FAIL", "Local package-integrity outcome.", "success" if release_audit_passed else "danger"),
        ("Module publication packs", f"{sum(int(r['passed']) for r in result['publication_audit']['rows'])}/80", "Published local module assets checked.", "info"),
        ("Step 192 page hooks", str(sum(int(r['step192_hook']) for r in result['page_audit']['rows'])), "Detected release-integrity hooks.", "neutral"),
        ("Databases checked", str(len(result["database_audit"]["rows"])), "Local database integrity checks.", "info"),
        ("Controlled release", "BLOCKED", "External evidence and approvals remain required.", "warning"),
    ]
)

if result["passed"]:
    insight_callout("Internal release-integrity checks pass. External scientific, licensing and publication blockers remain fail-closed.", tone="success")
else:
    st.error("One or more critical release-integrity checks failed. Review the table below before installation or publication.")

checks_tab, publication_tab, page_tab, data_tab = st.tabs([
    "Release checks", "Publication integration", "Page safety", "Database integrity"
])
with checks_tab:
    section_title("Release checks", "✓")
    smart_dataframe(pd.DataFrame(result["checks"]), height=420, key="step192_checks")
with publication_tab:
    section_title("Module publication integration", "📦")
    smart_dataframe(pd.DataFrame(result["publication_audit"]["rows"]), height=520, key="step192_publication")
with page_tab:
    section_title("Page safety and hook coverage", "🧭")
    smart_dataframe(pd.DataFrame(result["page_audit"]["rows"]), height=520, key="step192_pages")

with data_tab:
    section_title("Database integrity", "🗄️")
    smart_dataframe(pd.DataFrame(result["database_audit"]["rows"]), height=440, key="step192_databases")

with st.expander("Honesty boundary", expanded=True):
    st.warning(
        "Synthetic/demo benchmarks verify software execution and reproducibility only. They do not prove clinical validity, wet-lab confirmation, instrument qualification, regulatory approval, licensed production-reference eligibility or superiority to established tools."
    )

st.download_button(
    "Download Step 192 release audit",
    json.dumps(result, indent=2, default=str),
    file_name="STEP192_RELEASE_AUDIT.json",
    mime="application/json",
)
