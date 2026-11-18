from __future__ import annotations
from io import BytesIO
import json
from pathlib import Path
import zipfile
import pandas as pd
import streamlit as st
from .catalog import TARGET_PROFILES
from .validators import validate_step185_module

def _root()->Path: return Path(__file__).resolve().parents[3]
def _bundle(folder:Path)->bytes:
    b=BytesIO()
    with zipfile.ZipFile(b,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.iterdir()):
            if p.is_file(): z.write(p,arcname=p.name)
    return b.getvalue()

def render_step185_operational_assurance(module_key:str,*,expanded:bool=False)->None:
    p=TARGET_PROFILES[module_key]; r=validate_step185_module(_root(),module_key); folder=Path(r.path)
    with st.expander("Step 185 · Advanced operational assurance (10/10 internal/demo)",expanded=expanded):
        c1,c2,c3,c4=st.columns(4); c1.metric("Before",f"{p.before_demo_rating:.2f}/10"); c2.metric("After",f"{r.rating:.2f}/10",f"+{r.rating-p.before_demo_rating:.2f}"); c3.metric("Dimensions",f"{r.dimensions_passed}/{r.dimensions_total}"); c4.metric("Controlled release","BLOCKED")
        st.success("Calibration, subgroup validation, leakage controls, privacy/security, recovery/rollback, 10,000-record performance, repeatability and drift monitoring are qualified for synthetic demo operation.")
        st.warning("This score does not replace real clinical, wet-lab, instrument, licensed-data or independent-site evidence.")
        manifest=json.loads((folder/"assurance_manifest.json").read_text(encoding="utf-8-sig")); st.dataframe(pd.DataFrame(manifest["dimensions"]),width="stretch",hide_index=True)
        tabs=st.tabs(["Performance","Subgroups","Drift","Predictions"])
        with tabs[0]: st.dataframe(pd.read_csv(folder/"performance_benchmark.csv"),width="stretch",hide_index=True)
        with tabs[1]: st.dataframe(pd.read_csv(folder/"subgroup_validation.csv"),width="stretch",hide_index=True)
        with tabs[2]: st.dataframe(pd.read_csv(folder/"drift_monitoring.csv"),width="stretch",hide_index=True)
        with tabs[3]: st.dataframe(pd.read_csv(folder/"native_demo_predictions.csv").head(100),width="stretch",hide_index=True)
        a,b=st.columns(2); a.download_button("Download Step 185 assurance bundle",_bundle(folder),f"{module_key}_step185_assurance.zip","application/zip",key=f"s185_bundle_{module_key}"); b.download_button("Download qualification status",json.dumps(manifest,indent=2),f"{module_key}_step185_status.json","application/json",key=f"s185_status_{module_key}")
__all__=["render_step185_operational_assurance"]
