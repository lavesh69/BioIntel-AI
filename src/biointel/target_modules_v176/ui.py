from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from .catalog import TARGET_PROFILES
from .runtime import host_summary, probe_engines, probe_references


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _status_metric(frame: pd.DataFrame, column: str, expected: object) -> str:
    if frame.empty:
        return "0/0"
    passed = int(frame[column].eq(expected).sum())
    return f"{passed}/{len(frame)}"


def render_target_module_upgrade(module_key: str, *, expanded: bool = False) -> None:
    profile = TARGET_PROFILES[module_key]
    with st.expander("Step 176 · 17-module operational excellence", expanded=expanded):
        st.markdown(
            "This layer adds a module-specific workflow contract, executable runtime/reference doctor, "
            "fail-closed release gates and a reproducible qualification export. It does not fabricate "
            "licensed data, wet-lab evidence or expert approval."
        )
        workflow_tab, runtime_tab, gates_tab, export_tab = st.tabs(["Workflow", "Runtime & references", "Release gates", "Export"])
        with workflow_tab:
            left, right = st.columns(2)
            with left:
                st.markdown("#### Qualified workflow contract")
                for index, item in enumerate(profile.workflow, start=1):
                    st.markdown(f"**{index}.** {item}")
            with right:
                st.markdown("#### Required result package")
                for item in profile.required_outputs:
                    st.markdown(f"- {item}")
            st.info(profile.boundary)

        with runtime_tab:
            execute = st.checkbox("Run non-destructive --version smoke probes", value=False, key=f"step176_probe_{module_key}")
            try:
                engines = probe_engines(module_key, execute_smoke_tests=execute)
                references = probe_references(_root(), module_key)
            except Exception as exc:  # keep all scientific pages fail-safe
                st.error(f"Runtime doctor stopped safely: {exc}")
                engines, references = pd.DataFrame(), pd.DataFrame()
            c1, c2, c3 = st.columns(3)
            c1.metric("Engines discovered" if not execute else "Engines smoke-qualified", _status_metric(engines, "discovered" if not execute else "probe_status", True if not execute else "pass"))
            c2.metric("References present", _status_metric(references, "present", True))
            c3.metric("References qualified", _status_metric(references, "qualification_status", "qualified"))
            st.markdown("#### Specialist engines")
            st.dataframe(engines, width="stretch", hide_index=True)
            st.markdown("#### Production references")
            st.dataframe(references, width="stretch", hide_index=True)
            st.caption(f"Host: {json.dumps(host_summary(), ensure_ascii=False)}")

        with gates_tab:
            st.markdown("#### Mandatory evidence gates")
            gate_values: dict[str, bool] = {}
            for index, gate in enumerate(profile.quality_gates):
                gate_values[gate] = st.checkbox(gate, value=False, key=f"step176_gate_{module_key}_{index}")
            completed = sum(gate_values.values())
            st.progress(completed / max(len(gate_values), 1))
            if completed == len(gate_values):
                st.success("Module-level gate checklist complete. Independent evidence and formal release review are still required.")
            else:
                st.warning(f"Fail-closed: {len(gate_values) - completed} mandatory gate(s) remain incomplete.")

        with export_tab:
            payload = {
                "schema": "biointel.step176.target-module-qualification.v1",
                "module_key": module_key,
                "module_title": profile.title,
                "workflow": list(profile.workflow),
                "quality_gates": list(profile.quality_gates),
                "required_outputs": list(profile.required_outputs),
                "scientific_boundary": profile.boundary,
                "host": host_summary(),
                "decision": "research-only-fail-closed until runtime, reference and external evidence are complete",
            }
            st.download_button(
                "Download qualification contract",
                data=json.dumps(payload, indent=2, ensure_ascii=False),
                file_name=f"{module_key}_step176_qualification_contract.json",
                mime="application/json",
                key=f"step176_download_{module_key}",
            )


__all__ = ["render_target_module_upgrade"]
