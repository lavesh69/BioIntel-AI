from __future__ import annotations

"""Streamlit surfaces for the P0/P1 local evidence workflow."""

from pathlib import Path

import pandas as pd
import streamlit as st

from biointel.ui.components import scientific_boundary_banner, smart_dataframe
from biointel.ui.theme import section_title
from biointel.ui.visual_polish import render_metric_board

from .catalog import GATE_LABELS, GATE_ORDER, PRIORITY_MODULES, priority_requirement_rows
from .functional import (
    execution_contract_bytes,
    execution_portfolio_rows,
    module_execution_contract,
    prepare_functional_workspaces,
    run_execution_preflight,
)
from .registry import DISALLOWED_EVIDENCE_CLASSES, PriorityEvidenceRegistry


_EVIDENCE_CLASSES = (
    "authentic",
    "external",
    "provider-authorized",
    "internal-controlled",
    "demo",
    "template",
    "simulation",
    "synthetic",
    "rehearsal",
)


def _registry(root: Path) -> PriorityEvidenceRegistry:
    return PriorityEvidenceRegistry(root)


def _gate_frame(result: dict) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Gate": row["gate_label"],
                "Artifacts": row["artifact_count"],
                "Review-ready candidates": row["candidate_count"],
                "Rejected demo/template": row["rejected_evidence_count"],
                "State": row["state"],
                "Requirement": row["requirement"],
            }
            for row in result["gates"]
        ]
    )


def _execution_history_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "When": row["created_at"],
                "Action": row["action"],
                "Status": row["status"],
                "Execution key": row["execution_key"],
                "SHA-256": row["sha256"],
            }
            for row in rows
        ]
    )


def render_module_priority_workbench(root: str | Path, module_key: str, *, expanded: bool = False) -> None:
    """Embed a module-specific P0/P1 workbench only for priority modules."""
    profile = PRIORITY_MODULES.get(module_key)
    if profile is None:
        return
    registry = _registry(Path(root))
    key_prefix = f"p0p1_{module_key}"
    with st.expander(f"{profile.priority} priority evidence workbench · {profile.title}", expanded=expanded):
        result = registry.verify_module(module_key)
        execution_contract = module_execution_contract(root, module_key)
        staged_inputs = registry.execution_input_rows(module_key)
        functional_workspace = registry.functional_workspace_root / module_key
        ready_gates = sum(row["state"] == "ready-for-manual-review" for row in result["gates"])
        render_metric_board(
            [
                ("Priority", profile.priority, "Execution order for remediation.", "danger" if profile.priority == "P0" else "warning"),
                ("Review-ready gates", f"{ready_gates}/4", "Candidate evidence still requires manual review.", "info"),
                ("Manual-review candidate", "YES" if result["candidate_for_manual_review"] else "NO", "Never an automatic approval.", "success" if result["candidate_for_manual_review"] else "warning"),
                ("Controlled release", "NOT AUTOMATED", "Local staging cannot unlock release.", "warning"),
            ]
        )
        smart_dataframe(_gate_frame(result), height=360, key=f"{key_prefix}_gates")

        with st.expander("Functional local execution", expanded=False):
            st.caption(execution_contract["execution_surface"])
            execution_cards = [
                ("Execution key", execution_contract["execution_key"], "Canonical identity shared by the module workflow and audit records.", "info"),
                ("Adapter", execution_contract["adapter_label"], "Installed local route for this module.", "success"),
                ("Workspace", "Prepared" if functional_workspace.is_dir() else "Not prepared", "Creates only local documentation and empty folders; existing user data is preserved.", "success" if functional_workspace.is_dir() else "warning"),
                ("Staged inputs", len(staged_inputs), "User-supplied source files, hashed locally; not a proof-gate decision.", "info"),
            ]
            render_metric_board(execution_cards)
            st.caption(f"Module page: `{execution_contract['page'] or 'binding unavailable'}`")
            if execution_contract["adapter"] == "native_pipeline":
                st.info("This page already includes the direct Native pipeline controls for bounded parsing, persistent local jobs and pause/resume. Use them after this preflight when the required local engines and references are ready.")

            controls = st.columns(3, gap="small")
            if controls[0].button("Prepare functional workspace", key=f"{key_prefix}_functional_workspace", width="stretch"):
                try:
                    written = prepare_functional_workspaces(root, module_key, registry=registry)
                    st.success(f"Prepared {len(written)} local execution files. Existing user files were preserved.")
                except Exception as exc:
                    st.error(f"Functional workspace was not prepared: {exc}")
            if controls[1].button("Run local execution preflight", key=f"{key_prefix}_functional_preflight", width="stretch"):
                try:
                    preflight = run_execution_preflight(root, module_key, registry=registry)
                    state = preflight["status"]
                    if state == "adapter-repair-required":
                        st.error("Local execution adapter needs repair. The saved preflight record lists the blocked check.")
                    elif state == "workspace-preparation-required":
                        st.warning("Prepare the local functional workspace before supplying or running an input.")
                    else:
                        st.success(f"Preflight saved locally · {state.replace('-', ' ')}")
                    st.dataframe(pd.DataFrame(preflight["checks"]), width="stretch", hide_index=True)
                except Exception as exc:
                    st.error(f"Execution preflight could not complete: {exc}")
            controls[2].download_button(
                "Download execution contract",
                data=execution_contract_bytes(root, module_key),
                file_name=f"{module_key}_execution_contract.json",
                mime="application/json",
                key=f"{key_prefix}_execution_contract_download",
                width="stretch",
            )

            with st.expander("Stage an authorised production input locally", expanded=False):
                execution_upload = st.file_uploader(
                    "Input file for this module's installed workflow",
                    key=f"{key_prefix}_execution_input_upload",
                    help="The file is copied locally in chunks, SHA-256 recorded and limited to 1 GiB. This does not upload it to a public service or qualify it as evidence.",
                )
                execution_source = st.text_input(
                    "Source / protocol / accession reference",
                    key=f"{key_prefix}_execution_input_source",
                    placeholder="Required local or authorised source reference",
                )
                execution_notes = st.text_area(
                    "Input notes",
                    key=f"{key_prefix}_execution_input_notes",
                    max_chars=4000,
                    placeholder="Schema, sample scope, permissions, build/version or intended hand-off",
                )
                if st.button(
                    "Stage local input and calculate SHA-256",
                    key=f"{key_prefix}_execution_input_stage",
                    disabled=execution_upload is None,
                    width="stretch",
                ):
                    assert execution_upload is not None
                    try:
                        execution_upload.seek(0)
                        staged = registry.stage_execution_input(
                            module_key,
                            execution_upload,
                            original_name=execution_upload.name,
                            source_reference=execution_source,
                            notes=execution_notes,
                            expected_size_bytes=int(getattr(execution_upload, "size", 0) or 0),
                        )
                        st.success(f"Input staged locally · SHA-256 {staged['sha256']} · no proof-gate or release state changed.")
                    except Exception as exc:
                        st.error(f"Input was not staged: {exc}")
                st.caption("Staged production input is intentionally separate from the four proof gates. Add a genuine, review-ready artifact to the appropriate proof gate when it is suitable for responsible review.")

            history = registry.execution_rows(module_key, limit=8)
            if history:
                smart_dataframe(_execution_history_frame(history), height=260, key=f"{key_prefix}_execution_history")
            else:
                st.caption("No execution preflight or workspace record has been written for this module yet.")

        with st.expander("Stage a locally supplied evidence artifact", expanded=False):
            gate = st.selectbox(
                "Proof gate",
                list(GATE_ORDER),
                format_func=lambda value: GATE_LABELS[value],
                key=f"{key_prefix}_gate",
            )
            uploaded = st.file_uploader(
                "Evidence artifact",
                key=f"{key_prefix}_upload",
                help="The app calculates SHA-256 during local staging. Do not upload sensitive data to any public service.",
            )
            source_reference = st.text_input(
                "Source / protocol / record reference",
                key=f"{key_prefix}_source",
                placeholder="Local protocol ID, DOI, registry reference or controlled source identifier",
            )
            reviewer = st.text_input(
                "Named reviewer or responsible role",
                key=f"{key_prefix}_reviewer",
                placeholder="Required before an artifact can become a manual-review candidate",
            )
            evidence_class = st.selectbox(
                "Evidence class",
                _EVIDENCE_CLASSES,
                key=f"{key_prefix}_class",
                help="Demo, template, simulation, synthetic and rehearsal artifacts are stored for transparency but cannot satisfy a proof gate.",
            )
            review_status = st.selectbox(
                "Review state",
                ("draft", "submitted", "review-ready"),
                key=f"{key_prefix}_status",
            )
            notes = st.text_area("Notes", key=f"{key_prefix}_notes", max_chars=4000)
            if evidence_class in DISALLOWED_EVIDENCE_CLASSES:
                st.warning("This evidence class is explicitly non-qualifying. It will not increase readiness or unlock release.")
            if st.button("Stage locally and calculate SHA-256", key=f"{key_prefix}_stage", disabled=uploaded is None, width="stretch"):
                assert uploaded is not None
                try:
                    uploaded.seek(0)
                    record = registry.stage_stream(
                        module_key,
                        gate,
                        uploaded,
                        original_name=uploaded.name,
                        source_reference=source_reference,
                        reviewer=reviewer,
                        evidence_class=evidence_class,
                        review_status=review_status,
                        notes=notes,
                    )
                    st.success(f"Staged locally · SHA-256 {record['sha256']} · no qualification state changed.")
                except Exception as exc:
                    st.error(f"Evidence was not staged: {exc}")

        action_left, action_right = st.columns(2, gap="small")
        if action_left.button("Draft gate manifest", key=f"{key_prefix}_manifest", width="stretch"):
            gate = st.session_state.get(f"{key_prefix}_gate", GATE_ORDER[0])
            try:
                manifest = registry.write_gate_manifest(
                    module_key,
                    str(gate),
                    reviewer=st.session_state.get(f"{key_prefix}_reviewer", ""),
                    source_reference=st.session_state.get(f"{key_prefix}_source", ""),
                    notes=st.session_state.get(f"{key_prefix}_notes", ""),
                )
                st.success(f"Draft manifest created locally · SHA-256 {manifest['sha256']}")
            except Exception as exc:
                st.error(f"Manifest was not created: {exc}")
        if action_right.button("Verify four local proof gates", key=f"{key_prefix}_verify", width="stretch"):
            st.dataframe(_gate_frame(registry.verify_module(module_key)), width="stretch", hide_index=True)


def render_priority_upgrade_center(root: str | Path, *, key_prefix: str) -> None:
    """Render the portfolio-level P0/P1 queue, verification and safe workspace actions."""
    root_path = Path(root)
    registry = _registry(root_path)
    status = registry.status()
    render_metric_board(
        [
            ("P0 technical modules", status["p0_modules"], "Highest-priority runtime/data remediation.", "danger"),
            ("P1 scientific modules", status["p1_modules"], "Benchmark and independent-confirmation work.", "warning"),
            ("Staged artifacts", status["artifact_count"], "Locally stored and SHA-256 recorded.", "info"),
            ("Manual-review candidates", status["manual_review_candidates"], "Candidates only; no automatic promotion.", "success"),
            ("Execution records", status["execution_record_count"], "Saved local preflights and workspace preparation records.", "info"),
            ("Audit chain", "PASS" if status["audit_chain_valid"] else "REVIEW", "Tamper-evident local event chain.", "success" if status["audit_chain_valid"] else "danger"),
        ]
    )
    scientific_boundary_banner(
        source_kind="local_evidence_intake",
        release_eligible=False,
        message="The P0/P1 centre stages local artifacts and checks their SHA-256 metadata. It cannot create patient cohorts, licence rights, wet-lab outcomes, independent-site validation, ethics approvals, expert authority or regulatory clearance.",
    )

    queue_tab, execution_tab, workspace_tab, verification_tab = st.tabs([
        "Priority queue", "Functional execution", "Prepare local workspaces", "Four-gate verification"
    ])
    with queue_tab:
        tier = st.segmented_control(
            "Priority tier",
            options=("All", "P0", "P1"),
            default="All",
            key=f"{key_prefix}_tier",
        )
        rows = []
        for module in PRIORITY_MODULES.values():
            if tier != "All" and module.priority != tier:
                continue
            rows.append(
                {
                    "Priority": module.priority,
                    "Module": module.title,
                    "Module key": module.module_key,
                    "Primary next step": module.runtime_data,
                }
            )
        smart_dataframe(pd.DataFrame(rows), height=620, key=f"{key_prefix}_queue")
        module_key = st.selectbox(
            "Inspect priority module",
            [row["Module key"] for row in rows],
            format_func=lambda value: f"{PRIORITY_MODULES[value].priority} · {PRIORITY_MODULES[value].title}",
            key=f"{key_prefix}_module",
        )
        st.dataframe(pd.DataFrame(priority_requirement_rows(module_key)), width="stretch", hide_index=True)

    with execution_tab:
        rows = execution_portfolio_rows(root_path, registry)
        smart_dataframe(pd.DataFrame(rows), height=620, key=f"{key_prefix}_execution_portfolio")
        selected = st.selectbox(
            "Prepare or preflight one priority module",
            list(PRIORITY_MODULES),
            format_func=lambda value: f"{PRIORITY_MODULES[value].priority} · {PRIORITY_MODULES[value].title}",
            key=f"{key_prefix}_execution_module",
        )
        contract = module_execution_contract(root_path, selected)
        st.caption(contract["execution_surface"])
        execution_actions = st.columns(3, gap="small")
        if execution_actions[0].button("Prepare selected workspace", key=f"{key_prefix}_execution_prepare", type="primary", width="stretch"):
            try:
                written = prepare_functional_workspaces(root_path, selected, registry=registry)
                st.success(f"Prepared {len(written)} local execution files. Existing user files were preserved.")
            except Exception as exc:
                st.error(f"Workspace was not prepared: {exc}")
        if execution_actions[1].button("Run selected preflight", key=f"{key_prefix}_execution_preflight", width="stretch"):
            try:
                preflight = run_execution_preflight(root_path, selected, registry=registry)
                if preflight["status"] == "adapter-repair-required":
                    st.error("Adapter repair is required; review the saved local preflight checks.")
                elif preflight["status"] == "workspace-preparation-required":
                    st.warning("Prepare the selected functional workspace before supplying or running an input.")
                else:
                    st.success(f"Preflight saved locally · {preflight['status'].replace('-', ' ')}")
                st.dataframe(pd.DataFrame(preflight["checks"]), width="stretch", hide_index=True)
            except Exception as exc:
                st.error(f"Preflight could not complete: {exc}")
        execution_actions[2].download_button(
            "Download selected contract",
            data=execution_contract_bytes(root_path, selected),
            file_name=f"{selected}_execution_contract.json",
            mime="application/json",
            key=f"{key_prefix}_execution_download",
            width="stretch",
        )
        st.info("Stage source data from the selected module's P0/P1 workbench. The portfolio action deliberately never runs or approves a module without a user-supplied, authorised input and the module's own controls.")

    with workspace_tab:
        selected = st.selectbox(
            "Workspace scope",
            ("ALL", *PRIORITY_MODULES.keys()),
            format_func=lambda value: "All 62 priority modules" if value == "ALL" else PRIORITY_MODULES[value].title,
            key=f"{key_prefix}_workspace_module",
        )
        refresh = st.checkbox("Refresh empty template files", value=False, key=f"{key_prefix}_refresh")
        if st.button("Prepare local priority workspaces", key=f"{key_prefix}_prepare", type="primary", width="stretch"):
            written = registry.prepare_priority_workspaces(None if selected == "ALL" else selected, refresh=refresh)
            st.success(f"Prepared {len(written)} local checklist files. Existing evidence was preserved unless refresh was selected.")
        st.caption("Workspace preparation only creates local checklist drafts. It cannot mark a gate, score or release as complete.")

    with verification_tab:
        tier = st.selectbox("Verification scope", ("All", "P0", "P1"), key=f"{key_prefix}_verify_tier")
        rows = registry.verify_all(None if tier == "All" else tier)
        smart_dataframe(pd.DataFrame(rows), height=620, key=f"{key_prefix}_verification")
        st.info("A full four-gate row is a candidate for responsible manual review only. Rating promotion and controlled release are intentionally not automated.")


__all__ = ["render_module_priority_workbench", "render_priority_upgrade_center"]
