from __future__ import annotations

import json
from pathlib import Path
import streamlit as st

from .qualification import demo_detail_matrix, evaluate_demo_module


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def render_step182_demo_evidence(module_key: str, *, expanded: bool = False) -> None:
    with st.expander("Step 182 · Synthetic demo evidence files", expanded=expanded):
        readiness = evaluate_demo_module(_root(), module_key)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Demo packs", f"{readiness.demo_packs_ready}/{readiness.demo_packs_required}")
        c2.metric("Demo execution", "READY" if readiness.demo_execution_ready else "INCOMPLETE")
        c3.metric("Real evidence", "0/5")
        c4.metric("Controlled release", "NO")
        st.warning("DEMO ONLY: synthetic files exercise uploads, metrics, charts and gates. They are never counted as real external evidence and cannot unlock controlled release.")
        frame = demo_detail_matrix(_root(), module_key).copy()
        frame["metrics"] = frame["metrics"].map(lambda value: json.dumps(value, ensure_ascii=False, default=str))
        frame["blockers"] = frame["blockers"].map(lambda value: " | ".join(value))
        st.dataframe(frame, width="stretch", hide_index=True)
        payload = {
            "schema": "biointel.step182.demo-readiness.v1",
            "module_key": module_key,
            "demo_packs_ready": readiness.demo_packs_ready,
            "demo_packs_required": readiness.demo_packs_required,
            "demo_execution_ready": readiness.demo_execution_ready,
            "real_evidence_packs": 0,
            "controlled_release_eligible": False,
        }
        st.download_button(
            "Download demo readiness status",
            json.dumps(payload, indent=2),
            f"{module_key}_step182_demo_status.json",
            "application/json",
            key=f"s182_{module_key}",
        )


__all__ = ["render_step182_demo_evidence"]
