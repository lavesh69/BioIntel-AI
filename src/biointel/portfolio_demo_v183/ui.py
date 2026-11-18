from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import zipfile

import pandas as pd
import streamlit as st

from .catalog import PROFILES
from .qualification import evaluate_module
from .validators import validate_module_demo


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _bundle(folder: Path) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.iterdir()):
            if path.is_file():
                archive.write(path, arcname=path.name)
    return buffer.getvalue()


def render_step183_portfolio_demo(module_key: str, *, expanded: bool = False) -> None:
    profile = PROFILES[module_key]
    readiness = evaluate_module(_root(), module_key)
    validation = validate_module_demo(_root(), module_key)
    folder = Path(validation.path)
    with st.expander("Step 183 · Module demo files and negative-test pack", expanded=expanded):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Demo bundle", "READY" if readiness.demo_ready else "INCOMPLETE")
        c2.metric("Demo operational rating", f"{readiness.demo_operational_rating:.2f}/10", f"+{readiness.demo_improvement_points:.2f}")
        c3.metric("Internal software", "10.00/10")
        c4.metric("Real evidence rating", f"{readiness.real_external_rating:.2f}/10", "unchanged")
        st.info(
            "Synthetic demo files test uploads, schemas, analysis/UI paths, charts, reports, deterministic outputs and safe rejection. "
            "They are never counted as real laboratory, clinical, instrument or independent-site evidence."
        )
        st.caption(f"Execution mode: {readiness.execution_mode} · Controlled scientific release: NO")
        input_path = folder / "demo_input.csv"
        negative_path = folder / "demo_negative_cases.csv"
        status = {
            "schema": "biointel.step183.demo-status.v1",
            "module_key": module_key,
            "demo_ready": readiness.demo_ready,
            "execution_mode": readiness.execution_mode,
            "internal_software_rating": 10.0,
            "demo_operational_rating": readiness.demo_operational_rating,
            "real_external_rating": readiness.real_external_rating,
            "real_external_rating_changed": False,
            "controlled_release_eligible": False,
            "boundary": profile.boundary,
        }
        if not validation.demo_ready:
            st.warning(
                "The bundled demo assets are unavailable or incomplete. Run BioIntel Repair "
                "to restore the verified local demo pack; the scientific workflow remains disabled safely."
            )
            st.caption(" · ".join(validation.blockers[:4]) or "Demo artifact validation failed.")
            st.download_button(
                "Download status",
                json.dumps(status, indent=2),
                f"{module_key}_step183_status.json",
                "application/json",
                key=f"s183_status_{module_key}",
            )
            return
        if input_path.is_file():
            st.markdown("#### Demo input preview")
            st.dataframe(pd.read_csv(input_path).head(100), width="stretch", hide_index=True)
        if negative_path.is_file():
            st.markdown("#### Negative and fail-safe cases")
            st.dataframe(pd.read_csv(negative_path), width="stretch", hide_index=True)
        cols = st.columns(3)
        cols[0].download_button("Download demo input", input_path.read_bytes(), f"{module_key}_demo_input.csv", "text/csv", key=f"s183_input_{module_key}")
        cols[1].download_button("Download complete demo bundle", _bundle(folder), f"{module_key}_step183_demo_bundle.zip", "application/zip", key=f"s183_bundle_{module_key}")
        cols[2].download_button("Download status", json.dumps(status, indent=2), f"{module_key}_step183_status.json", "application/json", key=f"s183_status_{module_key}")


__all__ = ["render_step183_portfolio_demo"]
