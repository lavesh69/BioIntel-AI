from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from .catalog import PROFILES
from .qualification import evidence_detail_matrix, evaluate_module


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def render_step181_external_readiness(module_key: str, *, expanded: bool = False) -> None:
    if module_key not in PROFILES:
        raise KeyError(module_key)
    profile = PROFILES[module_key]
    with st.expander("Step 181 · Real external evidence qualification", expanded=expanded):
        readiness = evaluate_module(_root(), module_key)
        first, second, third, fourth = st.columns(4)
        first.metric("Workflow readiness", "10/10")
        second.metric("Evidence packs", f"{readiness.evidence_packs_qualified}/{readiness.evidence_packs_required}")
        third.metric("Completion", f"{100 * readiness.evidence_completion_fraction:.0f}%")
        fourth.metric("Controlled release", "YES" if readiness.controlled_release_eligible else "NO")
        st.caption(profile.weakness_summary)
        frame = evidence_detail_matrix(_root(), module_key)
        display = frame.copy()
        display["metrics"] = display["metrics"].map(lambda value: json.dumps(value, ensure_ascii=False, default=str))
        display["blockers"] = display["blockers"].map(lambda value: " | ".join(value))
        st.dataframe(display, width="stretch", hide_index=True)
        st.info(
            "Evidence folders are under UserData/step181/evidence. Add real data, update SHA-256 and provenance fields, "
            "obtain reviewer approval, then run VERIFY_STEP181_EXTERNAL_EVIDENCE_WINDOWS.bat."
        )
        if readiness.controlled_release_eligible:
            st.success("All real-world evidence packs qualify. Formal controlled-release review may proceed.")
        else:
            st.warning("Fail-closed: real evidence is incomplete. No scientific, clinical or wet-lab claim is promoted.")
        payload = {
            "schema": "biointel.step181.module-external-readiness.v1",
            "module_key": module_key,
            "module_title": profile.title,
            "workflow_rating": 10.0,
            "evidence_packs_required": readiness.evidence_packs_required,
            "evidence_packs_qualified": readiness.evidence_packs_qualified,
            "controlled_release_eligible": readiness.controlled_release_eligible,
            "remaining_evidence": readiness.remaining_evidence,
            "release_boundary": profile.release_boundary,
        }
        st.download_button(
            "Download Step 181 readiness status",
            json.dumps(payload, indent=2, ensure_ascii=False),
            f"{module_key}_step181_external_readiness.json",
            "application/json",
            key=f"s181_{module_key}",
        )


__all__ = ["render_step181_external_readiness"]
