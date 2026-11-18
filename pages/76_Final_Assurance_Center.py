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

from biointel.assurance import build_final_assurance_cached  # noqa: E402
from biointel.ui.components import scientific_boundary_banner  # noqa: E402
from biointel.ui.theme import apply_theme, badge, hero, section_title  # noqa: E402

st.set_page_config(page_title="Final Assurance Center · BioIntel AI", page_icon="🏁", layout="wide")
apply_theme()


@st.cache_data(ttl=300, show_spinner=False)
def _snapshot(root_text: str) -> dict[str, object]:
    # Default-load uses the last verified snapshot. A fresh repository-wide audit
    # is explicit because it scans source, databases, evidence and integrity gates.
    return build_final_assurance_cached(Path(root_text), validate_fingerprint=False)


refresh_assurance = st.button(
    "Run fresh assurance audit",
    type="secondary",
    help="Recompute every repository, database, evidence and production-readiness check.",
)
if refresh_assurance:
    with st.spinner("Running full assurance audit…"):
        report = build_final_assurance_cached(ROOT, force_refresh=True)
    _snapshot.clear()
else:
    report = _snapshot(str(ROOT))
hero(
    "Final Platform Assurance Center",
    "One evidence-aware view of implementation quality, measured qualification, repository integrity and authentic external proof boundaries.",
    eyebrow=f"BioIntel AI · Final Maximum Improvement · v{report['version']}",
    chips=[
        f"Implementation {report['implementation_score']:.1f}/10",
        f"Verifiable evidence {report['verifiable_evidence_score']:.1f}/10",
        f"Bundled public evidence {report['bundled_public_external_evidence_score']:.1f}/10",
        f"Product-specific external evidence {report['authentic_external_evidence_score']:.1f}/10",
        f"Real validation {report['real_external_validation_score']:.1f}/10",
        f"{report['database_health']['healthy_count']}/{report['database_health']['database_count']} databases healthy",
    ],
)

if report["implementation_score"] >= 9.5:
    badge("● Final implementation assurance passed", "success")
else:
    badge("● Final implementation assurance requires review", "warning")

scientific_boundary_banner(
    source_kind="mixed_evidence",
    release_eligible=False,
    message=report["boundary"],
)

section_title("Assurance matrix", "🛡️")
rows = pd.DataFrame(report["checks"])
status_order = {"ready": 0, "external_required": 1, "review": 2}
rows["_order"] = rows["status"].map(status_order).fillna(9)
rows = rows.sort_values(["_order", "label"]).drop(columns=["_order"])
st.dataframe(
    rows,
    width="stretch",
    hide_index=True,
    column_config={
        "label": st.column_config.TextColumn("Area", width="large"),
        "status": st.column_config.TextColumn("Status"),
        "score": st.column_config.ProgressColumn(
            "Score", min_value=0.0, max_value=10.0, format="%.1f/10"
        ),
        "evidence": st.column_config.TextColumn("Evidence", width="large"),
        "key": None,
    },
)

c1, c2, c3, c4 = st.columns(4)
c1.metric(
    "Databases",
    f"{report['database_health']['healthy_count']}/{report['database_health']['database_count']}",
)
c2.metric("Valid relationships", f"{report['relationship_health'].get('valid_edges', 0):,}")
c3.metric(
    "Repository checks",
    f"{sum(bool(v.get('passed')) for v in report['repository_audit']['checks'].values())}/{len(report['repository_audit']['checks'])}",
)
c4.metric(
    "Verified evidence artifacts",
    f"{report['evidence']['artifact_integrity']['verified_count']}/{report['evidence']['artifact_integrity']['artifact_count']}",
)

section_title("Actionable findings", "🔎")
findings: list[dict[str, str]] = []
for name, check in report["repository_audit"]["checks"].items():
    if not check.get("passed"):
        findings.append(
            {"source": f"repository:{name}", "finding": json.dumps(check, default=str)[:800]}
        )
for item in report["runtime_configuration"].get("findings", []):
    findings.append(
        {
            "source": "runtime_configuration",
            "finding": f"{item['severity']}: {item['message']} — {item['remediation']}",
        }
    )
for item in report["production_readiness"].get("blockers", []):
    findings.append(
        {"source": "production_readiness", "finding": f"{item['label']}: {item['message']}"}
    )
if findings:
    st.dataframe(pd.DataFrame(findings), width="stretch", hide_index=True)
else:
    st.success(
        "No internal implementation blockers detected. Remaining gaps require authentic third-party evidence or real operating history."
    )

section_title("Export", "📦")
st.download_button(
    "Download final assurance JSON",
    data=json.dumps(report, indent=2, sort_keys=True, default=str),
    file_name="biointel_final_assurance.json",
    mime="application/json",
    width="stretch",
    key="final_assurance_download",
)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='final_assurance', title='Final Assurance Center', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
