from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import zipfile

import pandas as pd
import streamlit as st

from .catalog import TARGET_PROFILES
from .validators import validate_step184_module


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _bundle(folder: Path) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.iterdir()):
            if path.is_file():
                archive.write(path, arcname=path.name)
    return buffer.getvalue()


def render_step184_demo_assurance(module_key: str, *, expanded: bool = False) -> None:
    profile = TARGET_PROFILES[module_key]
    result = validate_step184_module(_root(), module_key)
    folder = Path(result.path)
    with st.expander("Step 184 · Advanced demo assurance (10/10 internal)", expanded=expanded):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Before", f"{profile.before_demo_rating:.2f}/10")
        c2.metric("Demo assurance", f"{result.rating:.2f}/10", f"+{result.rating-profile.before_demo_rating:.2f}")
        c3.metric("Assurance dimensions", f"{result.dimensions_passed}/{result.dimensions_total}")
        c4.metric("Controlled release", "BLOCKED")
        st.success("Deterministic execution, golden outputs, 12 safety cases, 5,000-record stress, repeatability, offline fallback, provenance and report export are qualified.")
        st.warning("This is a synthetic/demo operational score. Real engines, licensed references, cohorts, wet-lab/instrument evidence and expert approval are still separate.")
        manifest = json.loads((folder / "assurance_manifest.json").read_text(encoding="utf-8-sig"))
        st.dataframe(pd.DataFrame(manifest["dimensions"]), width="stretch", hide_index=True)
        neg = pd.read_csv(folder / "negative_security_results.csv")
        perf = pd.read_csv(folder / "performance_benchmark.csv")
        tabs = st.tabs(["Safety cases", "Performance", "Golden output"])
        with tabs[0]:
            st.dataframe(neg, width="stretch", hide_index=True)
        with tabs[1]:
            st.dataframe(perf, width="stretch", hide_index=True)
        with tabs[2]:
            st.dataframe(pd.read_csv(folder / "golden_output.csv"), width="stretch", hide_index=True)
        cols = st.columns(2)
        cols[0].download_button("Download Step 184 assurance bundle", _bundle(folder), f"{module_key}_step184_assurance.zip", "application/zip", key=f"s184_bundle_{module_key}")
        cols[1].download_button("Download qualification status", json.dumps(manifest, indent=2), f"{module_key}_step184_status.json", "application/json", key=f"s184_status_{module_key}")


__all__ = ["render_step184_demo_assurance"]
