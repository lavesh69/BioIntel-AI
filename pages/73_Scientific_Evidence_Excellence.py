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

from biointel.scientific import (  # noqa: E402
    ScientificEvidenceLake,
    build_scientific_credibility_audit,
    build_scientific_excellence_readiness,
)
from biointel.ui.components import scientific_boundary_banner, smart_dataframe  # noqa: E402
from biointel.ui.theme import apply_theme, badge, hero, insight_callout, section_title  # noqa: E402

st.set_page_config(page_title="Scientific Evidence Excellence · BioIntel AI", page_icon="🧬", layout="wide")
apply_theme()


@st.cache_data(ttl=60, show_spinner=False)
def _snapshot(root_text: str):
    root = Path(root_text)
    return {
        "excellence": build_scientific_excellence_readiness(root),
        "credibility": build_scientific_credibility_audit(root),
    }


snapshot = _snapshot(str(ROOT))
report = snapshot["excellence"]
credibility = snapshot["credibility"]
summary = report["summary"]
hero(
    "Scientific Evidence Excellence",
    "Provider-authenticated evidence, assay quality, biological and clinical coverage, DTI benchmarking, external validation and blinded prospective studies.",
    eyebrow="Scientific evidence, independent validation and wet-lab readiness",
    chips=[
        f"Implementation {report['implementation_average']:.1f}/10",
        f"Current evidence {report['evidence_average']:.1f}/10",
        f"{summary['providers']} official providers",
        f"{summary['records']} immutable seed records",
    ],
)

badge("● Scientific implementation framework complete" if report["implementation_average"] == 10 else "● Scientific implementation gaps remain", "success" if report["implementation_average"] == 10 else "warning")
try:
    st.page_link("pages/74_DTI_Validation_Evidence_Center.py", label="Open DTI Validation & Wet-Lab Evidence Center")
except (KeyError, RuntimeError):
    st.info("Open DTI Validation & Wet-Lab Evidence Center from the sidebar.")
scientific_boundary_banner(
    source_kind="provider_reference",
    release_eligible=False,
    message=(
        "10/10 implementation readiness means the system can acquire, hash, normalize, review and validate real evidence. "
        "It does not mean the bundled seed catalog is a complete clinical or wet-lab validation corpus."
    ),
)

metrics = st.columns(6)
metrics[0].metric("Official providers", summary["providers"])
metrics[1].metric("Snapshots", summary["snapshots"])
metrics[2].metric("Evidence records", summary["records"])
metrics[3].metric("Organisms", summary["organisms"])
metrics[4].metric("Assay types", summary["assay_types"])
metrics[5].metric("Independent studies", summary["independent_completed_studies"])

matrix_tab, providers_tab, validation_tab, credibility_tab, qualification_tab = st.tabs([
    "Scientific matrix", "Evidence lake", "Validation protocols", "Credibility audit", "Qualification boundary"
])

with matrix_tab:
    frame = pd.DataFrame(report["capabilities"])
    chart = px.bar(frame.sort_values("evidence_score"), x=["implementation_score", "evidence_score"], y="label", orientation="h", barmode="group", range_x=[0, 10], labels={"value":"Score", "label":"Capability", "variable":"Score type"})
    chart.update_layout(height=max(600, len(frame) * 42), legend_title_text="")
    st.plotly_chart(chart, width="stretch")
    display = frame.rename(columns={
        "label":"Capability", "implementation_score":"Implementation", "implementation_status":"Implementation status",
        "evidence_score":"Current evidence", "evidence_status":"Evidence status", "controls":"Controls",
        "missing":"Missing", "certification_boundary":"Boundary",
    })
    display["Controls"] = display["Controls"].apply(lambda values: " • ".join(values))
    display["Missing"] = display["Missing"].apply(lambda values: " • ".join(values))
    smart_dataframe(display[["Capability","Implementation","Current evidence","Evidence status","Controls","Missing","Boundary"]], height=620,
                    columns={"Implementation": st.column_config.ProgressColumn("Implementation", min_value=0, max_value=10, format="%.1f"),
                             "Current evidence": st.column_config.ProgressColumn("Current evidence", min_value=0, max_value=10, format="%.1f")})

with providers_tab:
    lake = ScientificEvidenceLake(ROOT / "reports" / "scientific_evidence.sqlite3")
    integrity = lake.verify_integrity()
    st.success("Evidence-chain integrity verified") if integrity["ok"] else st.error("Evidence-chain integrity failed")
    st.code(json.dumps(integrity, indent=2), language="json")
    st.markdown("**Live synchronization**")
    st.code("python scripts/sync_scientific_evidence.py chembl --limit 1000\npython scripts/sync_scientific_evidence.py uniprot --query 'reviewed:true' --limit 500\npython scripts/sync_scientific_evidence.py clinicaltrials --query oncology --limit 1000\npython scripts/sync_scientific_evidence.py rcsb --pdb-id 1CRN", language="bash")
    insight_callout("Provider authenticity", "Every response is restricted to an official HTTPS host, stored with a SHA-256 checksum, retrieval timestamp, ETag/Last-Modified metadata when available, provider release and licence profile.", "info")

with validation_tab:
    section_title("Maximum DTI validation protocol", "🧪")
    requirements = pd.DataFrame([
        {"Stage":"Data", "Requirement":"Licensed provider snapshot, immutable checksum and assay-aware QC"},
        {"Stage":"Splits", "Requirement":"Cold-drug, cold-target, cold-both, scaffold, protein-cluster, temporal and external-source"},
        {"Stage":"Statistics", "Requirement":"Bootstrap confidence intervals, permutation tests and corrected comparisons"},
        {"Stage":"Quality", "Requirement":"Baseline-beating performance, calibration, uncertainty and leakage audits"},
        {"Stage":"External", "Requirement":"Independent dataset from a distinct provider or laboratory"},
        {"Stage":"Prospective", "Requirement":"Pre-registered protocol, locked predictions, blinded outcomes and independent review"},
    ])
    smart_dataframe(requirements, height=340)
    st.code("python scripts/register_prospective_study.py --title 'DTI prospective study' --hypothesis '...' --endpoint '...' --success '...' --model-sha256 <HASH> --dataset-sha256 <HASH>", language="bash")


with credibility_tab:
    section_title("Strict scientific credibility audit", "🛡️")
    score_cols = st.columns(4)
    score_cols[0].metric("Credibility controls", f"{credibility['credibility_controls_score']:.1f}/10")
    score_cols[1].metric("Implementation", f"{credibility['implementation_score']:.1f}/10")
    score_cols[2].metric("Verifiable evidence", f"{credibility['verifiable_evidence_score']:.1f}/10")
    score_cols[3].metric("Combined credibility", f"{credibility['combined_credibility_score']:.1f}/10")
    st.caption(
        "Implementation and real evidence are deliberately separated. Placeholder, synthetic, demo and reference-only records cannot raise the real-evidence score."
    )
    credibility_frame = pd.DataFrame(credibility["components"]).rename(
        columns={
            "label": "Credibility component",
            "score": "Score",
            "status": "Status",
            "evidence": "Evidence",
            "blocker": "Remaining blocker",
        }
    )
    smart_dataframe(
        credibility_frame[["Credibility component", "Score", "Status", "Evidence", "Remaining blocker"]],
        height=500,
        columns={
            "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=10, format="%.1f"),
        },
    )
    st.markdown("#### Claim-to-evidence eligibility")
    claim_frame = pd.DataFrame(credibility["claim_matrix"]).rename(
        columns={
            "claim": "Scientific claim",
            "eligible": "Eligible",
            "required": "Required evidence",
            "evidence": "Current verified evidence",
        }
    )
    smart_dataframe(
        claim_frame[["Scientific claim", "Eligible", "Required evidence", "Current verified evidence"]],
        height=360,
    )
    if credibility["blocked_claims"]:
        st.warning(
            "Blocked claims: " + " • ".join(credibility["blocked_claims"])
        )

    rejected = [row for row in credibility["qualified_studies"] if not row["qualified"]]
    if rejected:
        st.warning(
            f"{len(rejected)} study record(s) are excluded from strict evidence scoring because they do not meet hash, chronology, independence, blinding or review requirements."
        )
        rejected_frame = pd.DataFrame(rejected)
        rejected_frame["reasons"] = rejected_frame["reasons"].apply(lambda values: " • ".join(values))
        smart_dataframe(
            rejected_frame[["study_id", "tier", "status", "reasons"]].rename(
                columns={"study_id": "Study", "tier": "Claim tier", "status": "Status", "reasons": "Exclusion reason"}
            ),
            height=320,
        )
    audit_payload = json.dumps(credibility, indent=2, sort_keys=True)
    st.download_button(
        "Download credibility audit JSON",
        data=audit_payload,
        file_name="scientific_credibility_audit.json",
        mime="application/json",
        width="stretch",
    )
    insight_callout(
        "Evidence boundary",
        credibility["boundary"],
        "warning" if credibility["verifiable_evidence_score"] < 10 else "success",
    )

with qualification_tab:
    insight_callout(
        "What is 10/10 now",
        "Provider integration, provenance, evidence-lake integrity, assay QC, coverage targets, external-validation protocol, prospective-study locking, DTI qualification and scientific release controls are complete and testable.",
        "success",
    )
    insight_callout(
        "What still requires real-world work",
        "A true 10/10 evidence score requires thousands of reviewed experimental records, multiple independent providers, completed external benchmarks, blinded prospective wet-lab outcomes and independent scientific review. The software refuses to manufacture those claims.",
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
