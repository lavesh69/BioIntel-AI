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

from biointel.compliance import controls as compliance_controls  # noqa: E402
from biointel.fair import evaluate_fair_object  # noqa: E402
from biointel.maturity import build_maturity_readiness  # noqa: E402
from biointel.research import evaluate_academic_readiness, evaluate_pharma_readiness  # noqa: E402
from biointel.ui.components import scientific_boundary_banner, smart_dataframe  # noqa: E402
from biointel.ui.theme import apply_theme, badge, hero, insight_callout, section_title  # noqa: E402

st.set_page_config(page_title="Compliance & Research Readiness · BioIntel AI", page_icon="✅", layout="wide")
apply_theme()


@st.cache_data(ttl=60, show_spinner=False)
def _maturity(root_text: str) -> dict[str, object]:
    return build_maturity_readiness(Path(root_text))


report = _maturity(str(ROOT))
hero(
    "Compliance & Research Readiness",
    "Operational controls for regulatory/GxP readiness, FAIR data, reproducibility, enterprise SaaS, academic publication and pharmaceutical R&D.",
    eyebrow="10/10 implementation frameworks · evidence and certification remain independent",
    chips=[
        f"Implementation {report['implementation_average']:.1f}/10",
        f"Evidence diagnostic {report['evidence_average']:.1f}/10",
        f"{len(report['areas'])} maturity areas",
        "Dual-score protection",
    ],
)

badge("● All requested implementation frameworks complete", "success")
scientific_boundary_banner(
    source_kind="demo_reference",
    release_eligible=False,
    message=(
        "A 10/10 implementation score means tested software controls, policies, CI and documentation exist. "
        "It is not FDA approval, GxP certification, clinical validity, peer-review acceptance or proof that bundled synthetic models are scientifically valid."
    ),
)

areas = pd.DataFrame(report["areas"])
metric_cols = st.columns(4)
metric_cols[0].metric("Implementation", f"{report['implementation_average']:.1f}/10")
metric_cols[1].metric("Evidence diagnostic", f"{report['evidence_average']:.1f}/10")
metric_cols[2].metric("Complete frameworks", int((areas["implementation_score"] == 10).sum()))
metric_cols[3].metric("Evidence-blocked", int((areas["evidence_status"] == "blocked").sum()))

figure_data = areas[["label", "implementation_score", "evidence_score"]].copy()
figure_data["evidence_score"] = figure_data["evidence_score"].fillna(0)
figure_data = figure_data.melt(
    id_vars="label",
    value_vars=["implementation_score", "evidence_score"],
    var_name="Score type",
    value_name="Score",
)
figure_data["Score type"] = figure_data["Score type"].map(
    {"implementation_score": "Implementation", "evidence_score": "Current evidence"}
)
figure = px.bar(
    figure_data,
    x="Score",
    y="label",
    color="Score type",
    barmode="group",
    orientation="h",
    range_x=[0, 10],
    title="Implementation readiness versus current validated evidence",
)
figure.update_layout(height=max(620, len(areas) * 42), yaxis_title="", legend_title="")
st.plotly_chart(figure, width="stretch")

maturity_tab, fair_tab, academic_tab, pharma_tab, controls_tab = st.tabs(
    ["Maturity matrix", "FAIR evaluator", "Academic package", "Pharma R&D package", "Control catalog"]
)

with maturity_tab:
    section_title("Requested 10/10 implementation areas", "🏁")
    display = areas.copy()
    display["passed_controls"] = display["passed_controls"].apply(lambda values: " • ".join(values or []))
    display["failed_controls"] = display["failed_controls"].apply(lambda values: " • ".join(values or []))
    display = display.rename(
        columns={
            "label": "Area",
            "implementation_score": "Implementation",
            "implementation_status": "Implementation status",
            "evidence_score": "Current evidence",
            "evidence_status": "Evidence status",
            "passed_controls": "Implemented controls",
            "failed_controls": "Missing controls",
            "boundary": "Certification/evidence boundary",
        }
    )
    smart_dataframe(
        display[
            [
                "Area",
                "Implementation",
                "Implementation status",
                "Current evidence",
                "Evidence status",
                "Implemented controls",
                "Missing controls",
                "Certification/evidence boundary",
            ]
        ],
        height=650,
        columns={
            "Implementation": st.column_config.ProgressColumn(
                "Implementation", min_value=0.0, max_value=10.0, format="%.1f"
            ),
            "Current evidence": st.column_config.NumberColumn("Current evidence", format="%.1f"),
        },
    )
    insight_callout(
        "Why two scores?",
        "Software can implement rigorous controls, but it cannot manufacture authentic data, inspection evidence, prospective experiments, independent replication or operational history. Keeping both scores visible prevents misleading 10/10 claims.",
        "info",
    )

with fair_tab:
    section_title("Machine-actionable FAIR assessment", "🔎")
    fair_template = {
        "persistent_identifier": "doi:10.1234/example.dataset",
        "data_identifier": "doi:10.1234/example.dataset",
        "title": "Reviewed scientific dataset",
        "description": "Curated experimental measurements with provenance.",
        "creators": [{"name": "Research Team"}],
        "keywords": ["biotechnology", "assay", "reviewed"],
        "indexed": True,
        "index_name": "Institutional Repository",
        "access_protocol": "https",
        "access_url": "https://data.example.org/example.dataset",
        "access_rights": "restricted",
        "authorization_documented": True,
        "metadata_persistence_policy": True,
        "tombstone_url": "https://data.example.org/example.dataset/tombstone",
        "representation_language": "json-ld",
        "vocabularies": ["https://www.ebi.ac.uk/ols4/ontologies/bao"],
        "qualified_references": [{"type": "isDescribedBy", "id": "doi:10.1234/article"}],
        "publisher": "Research Institute",
        "version": "1.0.0",
        "resource_type": "dataset",
        "distributions": [{"name": "data.csv", "sha256": "a" * 64}],
        "license": "CC-BY-4.0",
        "provenance": {
            "source": "reviewed provider release",
            "generated_at": "2026-07-05T00:00:00+00:00",
            "agent": "curation-team",
            "activity": "curation and review",
        },
        "community_standards": ["BioAssay Ontology", "JSON-LD"],
        "schema_version": "1.0",
    }
    fair_text = st.text_area(
        "FAIR metadata JSON",
        value=json.dumps(fair_template, indent=2),
        height=360,
        key="fair_metadata_json",
    )
    if st.button("Evaluate FAIR object", type="primary", key="evaluate_fair"):
        try:
            fair_report = evaluate_fair_object(json.loads(fair_text)).to_dict()
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            st.error(f"Metadata could not be evaluated: {exc}")
        else:
            fair_cols = st.columns(5)
            fair_cols[0].metric("Overall", f"{fair_report['score']:.1f}/10")
            fair_cols[1].metric("Findable", f"{fair_report['findable']:.1f}")
            fair_cols[2].metric("Accessible", f"{fair_report['accessible']:.1f}")
            fair_cols[3].metric("Interoperable", f"{fair_report['interoperable']:.1f}")
            fair_cols[4].metric("Reusable", f"{fair_report['reusable']:.1f}")
            fair_frame = pd.DataFrame(fair_report["checks"]).rename(
                columns={
                    "principle": "Principle",
                    "label": "Requirement",
                    "passed": "Passed",
                    "evidence": "Evidence",
                    "remediation": "Remediation",
                }
            )
            smart_dataframe(
                fair_frame,
                height=520,
                columns={"Passed": st.column_config.CheckboxColumn("Passed")},
            )

with academic_tab:
    section_title("Academic submission readiness", "🎓")
    st.caption("The evaluator expects protocol, ethics, methods, FAIR data and a verified reproducibility package.")
    academic_template = {
        "research_question": "Does the model generalize to unseen target families?",
        "hypothesis": "Cold-target performance exceeds the predefined baseline.",
        "protocol_id": "osf:protocol-001",
        "preregistered": True,
        "ethics_review": "not-human-subjects determination",
        "consent_or_exemption": "exempt",
        "contributors": [{"name": "Researcher", "role": "Conceptualization"}],
        "methods": "Frozen pipeline and predefined endpoints",
        "parameters": {"seed": 42},
        "data_identifier": "doi:10.1234/data",
        "data_license": "CC-BY-4.0",
        "data_availability_statement": "Controlled access repository",
        "software_identifier": "swh:1:dir:example",
        "environment_lock": "requirements.lock",
        "reproducibility_bundle_verified": True,
        "statistical_plan": "Bootstrap CI and permutation tests",
        "multiple_testing_policy": "Benjamini-Hochberg",
        "limitations": "Assay-domain shift remains possible",
        "reporting_checklist": "Field-appropriate checklist",
        "negative_results_policy": "Report all predefined endpoints",
    }
    academic_text = st.text_area(
        "Academic package JSON", value=json.dumps(academic_template, indent=2), height=360
    )
    if st.button("Evaluate academic package", type="primary"):
        try:
            academic_report = evaluate_academic_readiness(json.loads(academic_text)).to_dict()
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            st.error(f"Package could not be evaluated: {exc}")
        else:
            st.metric("Academic readiness", f"{academic_report['score']:.1f}/10")
            smart_dataframe(pd.DataFrame(academic_report["checks"]), height=480)
            st.info(academic_report["certification_boundary"])

with pharma_tab:
    section_title("Pharmaceutical R&D evidence package", "🧬")
    pharma_template = {
        "intended_use": "Research prioritization only",
        "decision_context": "Preclinical target triage",
        "protocol_id": "PROT-001",
        "protocol_status": "approved",
        "randomization": True,
        "blinding": True,
        "controls": ["positive", "negative"],
        "assay_ontology_id": "BAO:0000015",
        "acceptance_criteria": {"z_prime": ">=0.5"},
        "replicate_plan": {"technical": 3, "biological": 3},
        "sample_chain_of_custody": True,
        "compound_identity_controls": True,
        "audit_chain_verified": True,
        "electronic_signatures_verified": True,
        "controlled_records": True,
        "independent_validation": True,
        "prospective_validation": True,
        "leakage_audit": True,
        "deviation_process": True,
        "capa_process": True,
        "change_control": True,
        "independent_qa_review": True,
        "scientific_review": True,
        "signed_evidence_manifest": True,
        "release_gate_passed": True,
        "limitations_disclosed": True,
    }
    pharma_text = st.text_area(
        "Pharma R&D package JSON", value=json.dumps(pharma_template, indent=2), height=400
    )
    if st.button("Evaluate pharma R&D package", type="primary"):
        try:
            pharma_report = evaluate_pharma_readiness(json.loads(pharma_text)).to_dict()
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            st.error(f"Package could not be evaluated: {exc}")
        else:
            st.metric("Pharma R&D framework readiness", f"{pharma_report['score']:.1f}/10")
            smart_dataframe(pd.DataFrame(pharma_report["checks"]), height=480)
            st.warning(pharma_report["certification_boundary"])

with controls_tab:
    section_title("Regulatory and GxP control catalog", "📚")
    control_frame = pd.DataFrame(compliance_controls())
    control_frame["standards"] = control_frame["standards"].apply(lambda values: " • ".join(values))
    control_frame["required_evidence"] = control_frame["required_evidence"].apply(
        lambda values: " • ".join(values)
    )
    control_frame = control_frame.rename(
        columns={
            "control_id": "Control",
            "domain": "Domain",
            "title": "Title",
            "description": "Description",
            "standards": "Standards mapping",
            "required_evidence": "Required evidence",
        }
    )
    smart_dataframe(control_frame, height=650)

st.download_button(
    "Download maturity readiness report",
    data=json.dumps(report, indent=2, sort_keys=True, default=str),
    file_name="biointel_maturity_readiness.json",
    mime="application/json",
    width="stretch",
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
