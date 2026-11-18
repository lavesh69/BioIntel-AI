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

from biointel.quality.capability_readiness import build_target_capability_readiness  # noqa: E402
from biointel.quality.scorecard import build_quality_scorecard  # noqa: E402
from biointel.ui.components import scientific_boundary_banner, smart_dataframe  # noqa: E402
from biointel.ui.theme import apply_theme, badge, hero, insight_callout, section_title  # noqa: E402

st.set_page_config(page_title="Platform Quality Center · BioIntel AI", page_icon="🛡️", layout="wide")
apply_theme()


@st.cache_data(ttl=60, show_spinner=False)
def _quality_snapshot(root_text: str) -> dict[str, object]:
    return build_quality_scorecard(Path(root_text))


@st.cache_data(ttl=60, show_spinner=False)
def _capability_snapshot(root_text: str) -> dict[str, object]:
    return build_target_capability_readiness(Path(root_text))


report = _quality_snapshot(str(ROOT))
capability_report = _capability_snapshot(str(ROOT))
overall = float(report["overall_score"])
target = float(report["target_score"])

hero(
    "Platform Quality Center",
    "Evidence-based diagnostics for scientific data, model validation, engineering, user experience, security and production deployment.",
    eyebrow="Engineering excellence, compliance, FAIR, reproducibility, ML and deployment maturity · measurable, not cosmetic",
    chips=[
        f"Overall diagnostic {overall:.1f}/10",
        f"Target {target:.1f}/10",
        f"{len(report['dimensions'])} measured dimensions",
        "External-data blockers identified",
    ],
)

if overall >= target:
    badge("● Platform quality target reached", "success")
elif overall >= 7.0:
    badge("● Strong software foundation · scientific evidence gaps remain", "warning")
else:
    badge("● Quality program active · critical dimensions remain below target", "danger")

scientific_boundary_banner(
    source_kind="demo_reference",
    release_eligible=False,
    message=(
        "This scorecard measures observable implementation and registry evidence. It does not turn synthetic data into real science, "
        "and it is not a regulatory or publication certification."
    ),
)

section_title("Quality overview", "📊")
metrics = st.columns(4)
metrics[0].metric("Overall", f"{overall:.1f}/10", delta=f"Target {target:.1f}")
metrics[1].metric("Groups", len(report["group_scores"]))
metrics[2].metric("Critical blockers", sum(item["score"] < 5 for item in report["blockers"]))
metrics[3].metric(
    "External-data blockers",
    sum(bool(item["requires_external_data"]) for item in report["blockers"]),
)

section_title("Requested 10/10 upgrades", "✅")
target_areas = report["target_assurance"]["areas"]
target_columns = st.columns(len(target_areas))
for column, area in zip(target_columns, target_areas, strict=True):
    column.metric(area["label"], f"{float(area['score']):.1f}/10")
    column.caption(f"{len(area['passed_controls'])} verified controls")

if report["target_assurance"]["all_targets_complete"]:
    st.success(
        "Code maintainability, accessibility, frontend performance, ML model-quality controls and validation-evidence readiness all pass the 10/10 implementation target."
    )
insight_callout(
    "Scientific truth remains protected",
    report["target_assurance"]["dual_score_policy"],
    "info",
)

section_title("User experience 10/10 upgrade", "🧭")
ux_report = report["user_experience_assurance"]
ux_columns = st.columns(len(ux_report["areas"]))
for column, area in zip(ux_columns, ux_report["areas"], strict=True):
    column.metric(area["label"], f"{float(area['score']):.1f}/10")
    column.caption(f"{len(area['passed_controls'])} verified controls")
if ux_report["all_targets_complete"]:
    st.success(
        "User experience now reaches the 10/10 implementation target: consistent interaction patterns, contextual help, workflow continuity, global discovery and category-safe back/forward navigation are verified."
    )
with st.expander("Review user-experience controls", expanded=False):
    ux_rows = []
    for area in ux_report["areas"]:
        passed = set(area["passed_controls"])
        for control, evidence in zip(
            [*area["passed_controls"], *area["failed_controls"]],
            area["evidence"],
            strict=False,
        ):
            ux_rows.append(
                {
                    "Area": area["label"],
                    "Control": control,
                    "Status": "Passed" if control in passed else "Incomplete",
                    "Evidence": evidence,
                }
            )
    smart_dataframe(ux_rows, height=480)
    st.caption(ux_report["boundary"])

group_frame = pd.DataFrame(
    [
        {"Group": key, "Score": value, "Target": target}
        for key, value in report["group_scores"].items()
    ]
).sort_values("Score")
figure = px.bar(
    group_frame,
    x="Score",
    y="Group",
    orientation="h",
    text="Score",
    range_x=[0, 10],
    title="Quality by platform layer",
)
figure.add_vline(x=target, line_dash="dash", annotation_text="Target")
figure.update_traces(texttemplate="%{text:.1f}", textposition="outside")
figure.update_layout(height=max(360, len(group_frame) * 68), showlegend=False)
st.plotly_chart(figure, width="stretch")

capability_tab, summary_tab, blockers_tab, models_tab, methodology_tab = st.tabs(
    [
        "10/10 implementation targets",
        "Dimension scorecard",
        "Priority blockers",
        "Model audit",
        "Methodology",
    ]
)

with capability_tab:
    implementation_average = float(capability_report["implementation_average"])
    st.metric("Requested implementation readiness", f"{implementation_average:.1f}/10")
    st.caption(
        "Implementation readiness measures whether the engineering controls exist and are tested. "
        "Scientific evidence scores stay separate and cannot be raised by code alone."
    )
    capability_frame = pd.DataFrame(capability_report["capabilities"])
    capability_frame["controls"] = capability_frame["controls"].apply(
        lambda values: " • ".join(values or [])
    )
    capability_frame["missing"] = capability_frame["missing"].apply(
        lambda values: " • ".join(values or [])
    )
    capability_frame = capability_frame.rename(
        columns={
            "program": "Program",
            "label": "Capability",
            "implementation_score": "Implementation",
            "implementation_status": "Implementation status",
            "evidence_score": "Current evidence",
            "evidence_status": "Evidence status",
            "controls": "Implemented controls",
            "missing": "Missing implementation",
            "boundary": "Evidence boundary",
        }
    )
    smart_dataframe(
        capability_frame[
            [
                "Program",
                "Capability",
                "Implementation",
                "Implementation status",
                "Current evidence",
                "Evidence status",
                "Implemented controls",
                "Missing implementation",
                "Evidence boundary",
            ]
        ],
        height=520,
        columns={
            "Implementation": st.column_config.ProgressColumn(
                "Implementation", min_value=0.0, max_value=10.0, format="%.1f"
            ),
            "Current evidence": st.column_config.NumberColumn("Current evidence", format="%.1f"),
        },
    )
    insight_callout(
        "Dual-score protection",
        "All requested maturity areas now have complete 10/10 repository-level implementation frameworks. Regulatory, GxP and scientific evidence scores remain separate because certification, authentic data, independent validation and operating history cannot be manufactured by code. This prevents fake certification.",
        "info",
    )

with summary_tab:
    dimensions = pd.DataFrame(report["dimensions"])
    display = dimensions.rename(
        columns={
            "label": "Dimension",
            "group": "Group",
            "score": "Score",
            "target": "Target",
            "status": "Status",
            "evidence": "Evidence",
            "next_action": "Next action",
            "externally_blocked": "Needs real external evidence",
        }
    )[
        [
            "Group",
            "Dimension",
            "Score",
            "Target",
            "Status",
            "Evidence",
            "Next action",
            "Needs real external evidence",
        ]
    ]
    smart_dataframe(
        display.sort_values(["Group", "Score"]),
        height=650,
        columns={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0.0, max_value=10.0, format="%.1f"
            ),
            "Target": st.column_config.NumberColumn("Target", format="%.1f"),
            "Needs real external evidence": st.column_config.CheckboxColumn("External dependency"),
        },
    )

with blockers_tab:
    blockers = pd.DataFrame(report["blockers"])
    if blockers.empty:
        st.success("No dimensions are below the strong threshold.")
    else:
        blockers = blockers.rename(
            columns={
                "dimension": "Dimension",
                "score": "Current score",
                "action": "Required action",
                "requires_external_data": "Needs external data",
            }
        )
        smart_dataframe(
            blockers,
            height=560,
            columns={
                "Current score": st.column_config.ProgressColumn(
                    "Current score", min_value=0.0, max_value=10.0, format="%.1f"
                ),
                "Needs external data": st.column_config.CheckboxColumn("External dependency"),
            },
        )
        insight_callout(
            "Important limitation",
            "Implementation readiness can reach 10/10 through tested controls. Real scientific authenticity, prospective validation, regulatory status and GxP evidence require licensed data, independent experiments, validation, trained operations and quality approval.",
            "warning",
        )

with models_tab:
    audit = report["model_audit"]
    model_metrics = st.columns(5)
    model_metrics[0].metric("Models", audit["model_count"])
    model_metrics[1].metric("Synthetic", audit["synthetic_models"])
    model_metrics[2].metric("Negative R²", audit["negative_r2_models"])
    model_metrics[3].metric("Robust splits", audit["robust_split_models"])
    model_metrics[4].metric("Release eligible", audit["release_eligible_models"])
    model_rows = pd.DataFrame(audit["models"])
    if not model_rows.empty:
        for field in ("blockers", "warnings"):
            model_rows[field] = model_rows[field].apply(lambda values: " • ".join(values or []))
        model_rows = model_rows.rename(
            columns={
                "model_file": "Model",
                "task": "Task",
                "synthetic_demo": "Synthetic",
                "split_strategy": "Split",
                "score": "Quality score",
                "release_eligible": "Release eligible",
                "blockers": "Blockers",
                "warnings": "Warnings",
            }
        )
        smart_dataframe(
            model_rows[
                [
                    "Model",
                    "Task",
                    "Synthetic",
                    "Split",
                    "Quality score",
                    "Release eligible",
                    "Blockers",
                    "Warnings",
                ]
            ].sort_values("Quality score"),
            height=620,
            columns={
                "Quality score": st.column_config.ProgressColumn(
                    "Quality score", min_value=0.0, max_value=100.0, format="%.1f"
                ),
                "Synthetic": st.column_config.CheckboxColumn("Synthetic"),
                "Release eligible": st.column_config.CheckboxColumn("Release eligible"),
            },
        )

with methodology_tab:
    st.markdown(report["methodology"])
    st.markdown(
        """
        **Scoring principles**

        - Registry volume does not equal scientific authenticity.
        - Synthetic/demo data never satisfies real-evidence release gates.
        - ML quality-control readiness is scored separately from authentic model evidence; synthetic models remain scientifically blocked.
        - A scientific release candidate must beat baseline performance, use leakage-resistant splitting, include uncertainty evidence and pass independent validation.
        - Production configuration is checked separately from whether PostgreSQL, Redis and object storage are actually used by every repository.
        - Scores are recalculated from the current workspace, so real imports, validation reports and infrastructure changes can move them.
        - A 10/10 implementation score is not FDA approval, GxP certification, clinical validity, peer-review acceptance or proof that synthetic models are scientifically valid.
        """
    )

st.download_button(
    "Download quality report",
    data=json.dumps(report, indent=2, sort_keys=True, default=str),
    file_name="biointel_platform_quality_report.json",
    mime="application/json",
    width="stretch",
)

# STEP136_NON_AI_VISUAL_PEAK_SUITE
from biointel.ui.domain_visual_peak import render_peak_visual_suite as _render_peak_visual_suite
_render_peak_visual_suite(page_key='platform_quality', title='Platform Quality Center', category='Start')

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
