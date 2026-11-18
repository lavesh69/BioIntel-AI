from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.governance.governance_registry import (
    MILESTONE_STATUSES,
    STANDARD_GATES,
    create_decision,
    create_milestone,
    delete_milestone,
    list_decisions,
    list_gates,
    list_milestones,
    project_governance_snapshot,
    update_milestone,
    upsert_gate,
)
from biointel.portfolio.project_registry import list_projects
from biointel.ui.phase108_visuals import render_phase108_visual_suite  # noqa: E402
from biointel.ui.theme import (
    apply_theme,
    badge,
    executive_kpis,
    hero,
    professional_strip,
    section_title,
)

REGISTRY = ROOT / "reports" / "projects.sqlite3"

st.set_page_config(
    page_title="Governance Hub · BioIntel AI",
    page_icon="🛡️",
    layout="wide",
)

apply_theme()

hero(
    "Professional controls for milestones, decisions and approval gates.",
    (
        "Create traceable delivery milestones, preserve decision rationale "
        "and manage release gates for every research project."
    ),
    eyebrow="Quality-Hardened · Governance Hub",
    chips=[
        "Milestones",
        "Decision log",
        "Approval gates",
        "Traceable evidence",
    ],
)

projects = list_projects(REGISTRY, include_archived=False)
if not projects:
    st.info("Create a project in Project Portfolio before adding governance controls.")
    st.stop()

selected_id = st.selectbox(
    "Research project",
    [project.project_id for project in projects],
    format_func=lambda project_id: next(
        (
            f"{project.project_code} · {project.name}"
            for project in projects
            if project.project_id == project_id
        ),
        project_id,
    ),
)
selected = next(project for project in projects if project.project_id == selected_id)
snapshot = project_governance_snapshot(
    REGISTRY,
    selected_id,
)
summary = snapshot["summary"]

if summary["gates_rejected"]:
    badge(
        f"● {summary['gates_rejected']} rejected gate(s)",
        "danger",
    )
elif summary["milestones_blocked"]:
    badge(
        f"● {summary['milestones_blocked']} blocked milestone(s)",
        "warning",
    )
else:
    badge("● Governance controls healthy", "success")

professional_strip(
    f"{selected.project_code} · {selected.name}",
    (
        f"{summary['milestones_completed']}/"
        f"{summary['milestones_total']} milestones complete · "
        f"{summary['approved_decisions']} approved decisions · "
        f"{summary['gates_approved']} approved gates"
    ),
)

executive_kpis(
    [
        (
            "Milestones",
            str(summary["milestones_total"]),
            (
                f"{summary['milestones_completed']} completed · "
                f"{summary['milestones_blocked']} blocked"
            ),
        ),
        (
            "Completion",
            f"{summary['milestone_completion_percent']}%",
            "Delivery evidence across all milestones",
        ),
        (
            "Decisions",
            str(summary["decisions_total"]),
            f"{summary['approved_decisions']} approved",
        ),
        (
            "Approval gates",
            str(summary["gates_total"]),
            (f"{summary['gates_approved']} approved · " f"{summary['gates_pending']} pending"),
        ),
    ]
)

milestone_tab, decision_tab, gate_tab, matrix_tab = st.tabs(
    [
        "Milestones",
        "Decision log",
        "Approval gates",
        "Governance matrix",
    ]
)

with milestone_tab:
    section_title("Create milestone", "◆")
    with st.form("create_milestone_form"):
        first, second, third = st.columns(3)
        title = first.text_input(
            "Milestone title",
            placeholder="External validation complete",
        )
        status = second.selectbox(
            "Status",
            [
                "Planned",
                "In Progress",
                "Blocked",
                "Completed",
                "Cancelled",
            ],
        )
        use_due_date = third.checkbox(
            "Set due date",
            value=True,
        )
        due_date = third.date_input(
            "Due date",
            value=date.today(),
            disabled=not use_due_date,
        )
        owner = st.text_input(
            "Owner label",
            placeholder="Validation lead",
        )
        acceptance = st.text_area(
            "Acceptance criteria",
            placeholder=(
                "Define the objective evidence required to consider " "this milestone complete."
            ),
            height=100,
        )
        evidence = st.text_input(
            "Evidence reference",
            placeholder="Report filename, experiment ID or registry SHA-256",
        )
        notes = st.text_area(
            "Notes",
            height=80,
        )
        created = st.form_submit_button(
            "Create milestone",
            type="primary",
        )

    if created:
        try:
            record = create_milestone(
                REGISTRY,
                selected_id,
                title=title,
                status=status,
                due_date=(due_date.isoformat() if use_due_date else None),
                owner_label=owner,
                acceptance_criteria=acceptance,
                evidence_reference=evidence,
                notes=notes,
            )
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success(f"Milestone created: {record.title}")
            st.rerun()

    milestones = list_milestones(
        REGISTRY,
        selected_id,
    )
    section_title("Milestone register", "▣")
    if not milestones:
        st.info("No milestones recorded.")
    else:
        milestone_table = pd.DataFrame([asdict(item) for item in milestones])
        st.dataframe(
            milestone_table,
            width="stretch",
            hide_index=True,
        )

        selected_milestone_id = st.selectbox(
            "Manage milestone",
            [item.milestone_id for item in milestones],
            format_func=lambda milestone_id: next(
                (
                    f"{item.title} · {item.status}"
                    for item in milestones
                    if item.milestone_id == milestone_id
                ),
                milestone_id,
            ),
        )
        current = next(item for item in milestones if item.milestone_id == selected_milestone_id)

        with st.form("update_milestone_form"):
            update_title = st.text_input(
                "Title",
                value=current.title,
            )
            update_status = st.selectbox(
                "Milestone status",
                sorted(MILESTONE_STATUSES),
                index=sorted(MILESTONE_STATUSES).index(current.status),
            )
            update_use_date = st.checkbox(
                "Maintain due date",
                value=current.due_date is not None,
            )
            update_date = st.date_input(
                "Due date",
                value=(date.fromisoformat(current.due_date) if current.due_date else date.today()),
                disabled=not update_use_date,
            )
            update_owner = st.text_input(
                "Owner label",
                value=current.owner_label,
            )
            update_acceptance = st.text_area(
                "Acceptance criteria",
                value=current.acceptance_criteria,
            )
            update_evidence = st.text_input(
                "Evidence reference",
                value=current.evidence_reference,
            )
            update_notes = st.text_area(
                "Notes",
                value=current.notes,
            )
            updated = st.form_submit_button(
                "Save milestone",
                type="primary",
            )

        if updated:
            try:
                record = update_milestone(
                    REGISTRY,
                    selected_milestone_id,
                    title=update_title,
                    status=update_status,
                    due_date=(update_date.isoformat() if update_use_date else None),
                    owner_label=update_owner,
                    acceptance_criteria=update_acceptance,
                    evidence_reference=update_evidence,
                    notes=update_notes,
                )
            except Exception as exc:
                st.error(str(exc))
            else:
                st.success(f"Milestone updated: {record.title}")
                st.rerun()

        with st.expander("Delete milestone record"):
            confirm = st.checkbox(
                f"Confirm deletion of {current.title}",
                key="confirm_milestone_delete",
            )
            if st.button(
                "Delete milestone",
                disabled=not confirm,
            ):
                if delete_milestone(
                    REGISTRY,
                    selected_milestone_id,
                ):
                    st.success("Milestone deleted.")
                    st.rerun()

with decision_tab:
    section_title("Record controlled decision", "✎")
    st.caption(
        "Decision records are append-only. Record a new decision with "
        "Superseded or Reversed status rather than editing history."
    )
    with st.form("create_decision_form"):
        first, second, third = st.columns(3)
        decision_title = first.text_input(
            "Decision title",
            placeholder="Adopt grouped target split",
        )
        decision_status = second.selectbox(
            "Decision status",
            [
                "Approved",
                "Proposed",
                "Superseded",
                "Reversed",
            ],
        )
        decision_date = third.date_input(
            "Decision date",
            value=date.today(),
        )
        context = st.text_area(
            "Context",
            placeholder="Describe the problem, constraints and evidence.",
            height=90,
        )
        decision_text = st.text_area(
            "Decision",
            placeholder="State exactly what was decided.",
            height=100,
        )
        rationale = st.text_area(
            "Rationale",
            placeholder="Explain why this option was selected.",
            height=100,
        )
        alternatives = st.text_area(
            "Alternatives considered",
            height=80,
        )
        impact = st.text_area(
            "Expected impact",
            height=80,
        )
        approver = st.text_input(
            "Approver/reviewer label",
        )
        decision_evidence = st.text_input(
            "Evidence reference",
        )
        recorded = st.form_submit_button(
            "Record decision",
            type="primary",
        )

    if recorded:
        try:
            record = create_decision(
                REGISTRY,
                selected_id,
                title=decision_title,
                decision=decision_text,
                status=decision_status,
                decision_date=decision_date.isoformat(),
                context=context,
                rationale=rationale,
                alternatives=alternatives,
                impact=impact,
                approver_label=approver,
                evidence_reference=decision_evidence,
            )
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success(f"Decision recorded: {record.title}")
            st.rerun()

    decisions = list_decisions(
        REGISTRY,
        selected_id,
    )
    section_title("Decision register", "▣")
    if decisions:
        st.dataframe(
            pd.DataFrame([asdict(item) for item in decisions]),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No decisions recorded.")

with gate_tab:
    section_title("Set approval gate", "✓")
    existing_gates = list_gates(
        REGISTRY,
        selected_id,
    )
    existing_by_name = {item.gate_name: item for item in existing_gates}

    with st.form("gate_form"):
        gate_mode = st.radio(
            "Gate type",
            ["Standard gate", "Custom gate"],
            horizontal=True,
        )
        if gate_mode == "Standard gate":
            gate_name = st.selectbox(
                "Gate",
                list(STANDARD_GATES),
            )
        else:
            gate_name = st.text_input(
                "Custom gate name",
            )

        current_gate = existing_by_name.get(gate_name)
        gate_status = st.selectbox(
            "Gate status",
            [
                "Pending",
                "Conditional",
                "Approved",
                "Rejected",
            ],
            index=(
                [
                    "Pending",
                    "Conditional",
                    "Approved",
                    "Rejected",
                ].index(current_gate.status)
                if current_gate
                else 0
            ),
        )
        reviewer = st.text_input(
            "Reviewer label",
            value=(current_gate.reviewer_label if current_gate else ""),
        )
        conditions = st.text_area(
            "Conditions / rejection rationale",
            value=(current_gate.conditions if current_gate else ""),
            height=100,
        )
        gate_evidence = st.text_input(
            "Evidence reference",
            value=(current_gate.evidence_reference if current_gate else ""),
        )
        set_decision_date = st.checkbox(
            "Set decision date",
            value=(current_gate is not None and current_gate.decision_date is not None),
        )
        gate_date = st.date_input(
            "Decision date",
            value=(
                date.fromisoformat(current_gate.decision_date)
                if current_gate and current_gate.decision_date
                else date.today()
            ),
            disabled=not set_decision_date,
        )
        saved = st.form_submit_button(
            "Save approval gate",
            type="primary",
        )

    if saved:
        try:
            record = upsert_gate(
                REGISTRY,
                selected_id,
                gate_name=gate_name,
                status=gate_status,
                reviewer_label=reviewer,
                conditions=conditions,
                evidence_reference=gate_evidence,
                decision_date=(gate_date.isoformat() if set_decision_date else None),
            )
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success(f"{record.gate_name}: {record.status}")
            st.rerun()

    gates = list_gates(
        REGISTRY,
        selected_id,
    )
    section_title("Approval gate register", "▣")
    if gates:
        st.dataframe(
            pd.DataFrame([asdict(item) for item in gates]),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No approval gates recorded.")

with matrix_tab:
    section_title("Governance evidence matrix", "◎")
    matrix = []
    for milestone in snapshot["milestones"]:
        matrix.append(
            {
                "Control type": "Milestone",
                "Control": milestone["title"],
                "Status": milestone["status"],
                "Evidence": milestone["evidence_reference"],
                "Owner/reviewer": milestone["owner_label"],
            }
        )
    for decision in snapshot["decisions"]:
        matrix.append(
            {
                "Control type": "Decision",
                "Control": decision["title"],
                "Status": decision["status"],
                "Evidence": decision["evidence_reference"],
                "Owner/reviewer": decision["approver_label"],
            }
        )
    for gate in snapshot["gates"]:
        matrix.append(
            {
                "Control type": "Gate",
                "Control": gate["gate_name"],
                "Status": gate["status"],
                "Evidence": gate["evidence_reference"],
                "Owner/reviewer": gate["reviewer_label"],
            }
        )
    if matrix:
        matrix_frame = pd.DataFrame(matrix)
        st.dataframe(
            matrix_frame,
            width="stretch",
            hide_index=True,
        )
        st.download_button(
            "Download governance matrix CSV",
            matrix_frame.to_csv(index=False),
            f"{selected.project_code}_governance_matrix.csv",
            "text/csv",
        )
    else:
        st.info("No governance controls available.")

    st.download_button(
        "Download governance snapshot JSON",
        json.dumps(
            snapshot,
            indent=2,
            default=str,
        ),
        f"{selected.project_code}_governance.json",
        "application/json",
    )

# Step 108 Phase 1+2 decision visual workspace
render_phase108_visual_suite("governance", ROOT, context=locals())

# STEP187_PAGE_EXCELLENCE_HOOK
import sys as _step187_sys
from pathlib import Path as _Step187Path
_step187_root = _Step187Path(__file__).resolve().parents[1]
_step187_src = _step187_root / "src"
if str(_step187_src) not in _step187_sys.path:
    _step187_sys.path.insert(0, str(_step187_src))
from biointel.page_excellence_v187.ui import render_step187_page_excellence as _render_step187_page_excellence
_render_step187_page_excellence(__file__)
