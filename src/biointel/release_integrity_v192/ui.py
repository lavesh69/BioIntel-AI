from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from .audit import load_module_status


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def render_step192_release_integrity(module_key: str, *, expanded: bool = False) -> None:
    root = _root()
    try:
        status = load_module_status(root, module_key)
    except Exception as exc:  # UI must never break the host module.
        with st.expander("Step 192 · Release integrity & publication readiness", expanded=False):
            st.warning(f"Step 192 status could not be loaded: {type(exc).__name__}: {exc}")
        return

    with st.expander("Step 192 · Release integrity & publication readiness", expanded=expanded):
        cols = st.columns(4)
        cols[0].metric("Publication assets", "Ready" if status["assets_present"] else "Missing")
        cols[1].metric("Preprint package", "Ready" if status["preprint_ready"] else "Pending")
        cols[2].metric("Controlled release", "Eligible" if status["controlled_release_eligible"] else "Blocked")
        cols[3].metric("Release version", "15.0.0")
        st.caption("Internal reproducibility and publication assets do not replace independent scientific, clinical, wet-lab, instrument, licensing or regulatory evidence.")
        st.markdown("**Intended use**")
        st.write(status["intended_use"])
        st.markdown("**Limitations**")
        limitations = status["limitations"]
        if isinstance(limitations, list):
            st.dataframe(pd.DataFrame({"Limitation": limitations}), width="stretch", hide_index=True)
        else:
            st.write(limitations)
        if status["external_blockers"]:
            st.info("External blockers: " + ", ".join(str(item) for item in status["external_blockers"]))
        benchmark = status.get("benchmark", {})
        if benchmark:
            st.download_button(
                "Download module publication benchmark summary",
                json.dumps(benchmark, indent=2, default=str),
                file_name=f"{module_key}_publication_benchmark_summary.json",
                mime="application/json",
                key=f"step192_publication_{module_key}",
            )
