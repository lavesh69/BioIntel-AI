from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from .catalog import PROFILES
from .engine import bundle_bytes
from .qualification import validate_module

def _root() -> Path:
    return Path(__file__).resolve().parents[3]

def render_step193_mandatory_completion(module_key: str, *, expanded: bool=False) -> None:
    if module_key not in PROFILES:
        return
    root=_root(); result=validate_module(root,module_key); folder=Path(result.path)
    with st.expander("Step 193 · Mandatory Feature Completion & Install Safety", expanded=expanded):
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Internal rating", f"{result.rating:.2f}/10")
        c2.metric("Mandatory checks", f"{result.passed}/{result.total}")
        c3.metric("Autosave/recovery", "Ready" if result.qualified else "Review")
        c4.metric("Controlled release", "Blocked")
        if result.qualified:
            st.success("Mandatory governance, recovery, isolation, resource, confidence, integrity, review, migration, accessibility, security, diagnostics and monitoring contracts are complete.")
        else:
            st.error("Blockers: " + ", ".join(result.blockers))
        manifest=json.loads((folder/"qualification_manifest.json").read_text(encoding="utf-8"))
        st.dataframe(pd.DataFrame(manifest["dimensions"]), width="stretch", hide_index=True)
        st.caption("Internal/software qualification only. Authentic external scientific evidence remains required for controlled release.")
        st.download_button("Download Step 193 module completion bundle", bundle_bytes(folder), f"{module_key}_step193_mandatory_completion.zip", "application/zip", key=f"s193_bundle_{module_key}")

__all__=["render_step193_mandatory_completion"]
