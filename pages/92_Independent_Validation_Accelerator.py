from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.clinical import (  # noqa: E402
    ClinicalValidationRegistry,
    build_generic_independent_validation_starter_pack,
    build_independent_validation_accelerator_readiness,
    build_independent_validation_partner_pack,
    build_validation_action_plan,
    evaluate_real_external_validation,
    projected_score_from_control_completion,
)
from biointel.ui.components import scientific_boundary_banner, smart_dataframe  # noqa: E402
from biointel.ui.theme import apply_theme, hero, insight_callout, section_title  # noqa: E402

st.set_page_config(
    page_title="Independent Validation Accelerator · BioIntel AI",
    page_icon="🚀",
    layout="wide",
)
apply_theme()

DB_PATH = ROOT / "data" / "clinical_pharma" / "clinical_validation.sqlite3"
registry = ClinicalValidationRegistry(DB_PATH)
framework = build_independent_validation_accelerator_readiness(ROOT)
programs = registry.list_programs()

hero(
    "Independent Validation Accelerator",
    "Convert every authentic clinical/pharma evidence gap into an owner-assigned execution plan, planning projection and checksum-bound partner pack—without inflating the real score.",
    eyebrow="Step 89 · genuine path to 10/10 · no synthetic claims",
    chips=[
        f"Execution support {framework.score:.1f}/10",
        "Nine-domain action plan",
        "Uncompressed partner pack",
        "Authentic score protected",
    ],
)
scientific_boundary_banner(
    source_kind="external_evidence",
    release_eligible=False,
    message=(
        "The accelerator can make the validation process execution-ready, but it cannot manufacture "
        "independent investigators, patient outcomes, laboratory reports, publications, inspections or authorizations."
    ),
)

if not programs:
    st.info("Create a validation program in Clinical & Pharma Validation to generate a program-specific action plan.")
    try:
        starter_payload = build_generic_independent_validation_starter_pack(ROOT)
        st.download_button(
            "Download program-neutral partner starter pack",
            data=starter_payload,
            file_name="biointel_independent_validation_starter_pack.zip",
            mime="application/zip",
            width="stretch",
        )
    except (FileNotFoundError, OSError) as exc:
        st.error(f"Starter pack could not be generated: {exc}")
    st.stop()

program_id = st.selectbox(
    "Validation program",
    [item["program_id"] for item in programs],
    format_func=lambda identifier: next(
        f"{item['title']} · {item['status']}" for item in programs if item["program_id"] == identifier
    ),
)
program = next(item for item in programs if item["program_id"] == program_id)
report = evaluate_real_external_validation(registry, program_id)
actions = build_validation_action_plan(report)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Execution accelerator", f"{framework.score:.1f}/10")
m2.metric("Actual verified score", f"{report.actual_external_validation_score:.1f}/10")
m3.metric("Domains completed", f"{report.domains_at_10}/{report.total_domains}")
m4.metric("Clinical/pharma claim", "UNLOCKED" if report.release_eligible else "BLOCKED")

insight_callout(
    "What can be improved now",
    (
        "Software-side execution support is qualified at 10/10. The table below identifies the external owner, "
        "artifact and acceptance evidence required for every remaining authentic-score control."
    ),
    icon="🧭",
    tone="success" if framework.score == 10.0 else "warning",
)

plan_tab, projection_tab, export_tab, controls_tab = st.tabs(
    ["Action plan", "Planning projection", "Partner execution pack", "Framework controls"]
)

with plan_tab:
    section_title("Owner-assigned path to authentic 10/10", "📋")
    smart_dataframe(
        [
            {
                "Priority": item.priority,
                "Domain": item.label,
                "Current": item.current_score,
                "Target": item.target_score,
                "Current blocker": item.blocker,
                "External owner": item.required_owner,
                "Required artifact": item.required_artifact,
                "Acceptance evidence": item.completion_evidence,
            }
            for item in actions
        ],
        height=620,
        key="independent_validation_action_plan",
    )
    st.caption(
        "All rows require external execution. Completing software forms alone never marks a row complete."
    )

with projection_tab:
    section_title("Planning projection—not a claim", "🧮")
    st.warning(
        "Projected scores are scenario planning only. They do not update the registry, release gate or permitted claim."
    )
    completed: dict[str, int] = {}
    for rating in report.ratings:
        remaining = rating.total_controls - rating.passed_controls
        completed[rating.domain] = st.slider(
            f"Authentic controls expected to complete · {rating.label}",
            min_value=0,
            max_value=remaining,
            value=0,
            key=f"projection_{rating.domain}",
        )
    projection = projected_score_from_control_completion(report, completed)
    p1, p2 = st.columns(2)
    p1.metric("Actual verified score", f"{projection['actual_score']:.1f}/10")
    p2.metric("Planning projection", f"{projection['projected_score']:.1f}/10")
    smart_dataframe(projection["rows"], height=430, key="validation_projection_rows")
    st.caption(projection["boundary"])

with export_tab:
    section_title("Checksum-bound partner execution pack", "📦")
    st.markdown(
        "The pack includes the current authentic scorecard, blocker-to-owner action plan, blinded prediction protocol, "
        "statistical analysis outline, site responsibilities, evidence acceptance checklist and budget-aware roadmap."
    )
    try:
        payload = build_independent_validation_partner_pack(
            ROOT,
            report,
            program_title=program["title"],
        )
        st.download_button(
            "Download independent validation partner pack",
            data=payload,
            file_name=f"{program_id}_independent_validation_partner_pack.zip",
            mime="application/zip",
            width="stretch",
        )
        st.success(
            "Pack generated in ZIP_STORED mode with a SHA-256 manifest. It contains no pre-approved evidence."
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        st.error(f"Partner pack could not be generated: {exc}")

with controls_tab:
    section_title("Accelerator qualification controls", "✅")
    smart_dataframe(list(framework.controls), height=420, key="accelerator_framework_controls")
    st.caption(framework.boundary)

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
