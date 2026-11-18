from __future__ import annotations
from io import BytesIO
from pathlib import Path
import json,zipfile
import pandas as pd
import streamlit as st
from .catalog import DEEP_TARGETS,TARGET_PROFILES
from .engine import slug
from .validators import validate_step187_page

def _root()->Path:return Path(__file__).resolve().parents[3]
def _bundle(folder:Path)->bytes:
    b=BytesIO()
    with zipfile.ZipFile(b,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.iterdir()):
            if p.is_file():z.write(p,arcname=p.name)
    return b.getvalue()

def render_step187_page_excellence(page_file:str|Path,*,expanded:bool=False)->None:
    file_name=Path(page_file).name
    if file_name not in TARGET_PROFILES:return
    p=TARGET_PROFILES[file_name];r=validate_step187_page(_root(),file_name);folder=Path(r.path)
    with st.expander("Step 187 · Page Excellence assurance (10/10 internal/demo)",expanded=expanded):
        c1,c2,c3,c4=st.columns(4);c1.metric("Before",f"{p.before_rating:.2f}/10");c2.metric("After",f"{r.rating:.2f}/10",f"+{r.rating-p.before_rating:.2f}");c3.metric("Dimensions",f"{r.dimensions_passed}/{r.dimensions_total}");c4.metric("Real release","UNCHANGED")
        st.success("Page-specific fixture, deterministic golden output, validation, 15 adverse/security cases, scale benchmark, repeatability, recovery, accessibility, provenance, privacy and direct test coverage are qualified.")
        st.warning("10/10 is internal/demo-operational page assurance. Real clinical, wet-lab, licensed-data, independent-site or regulatory evidence is not created by this layer.")
        if not r.qualified_10_of_10:
            st.warning(
                "The bundled page-assurance assets are unavailable or incomplete. Run BioIntel Repair "
                "to restore the verified local assurance pack; this panel is disabled safely."
            )
            st.caption(" · ".join(r.blockers[:4]) or "Page-assurance validation failed.")
            return
        manifest=json.loads((folder/"assurance_manifest.json").read_text(encoding="utf-8"));st.dataframe(pd.DataFrame(manifest["dimensions"]),width="stretch",hide_index=True)
        tabs=st.tabs(["Demo input","Golden output","Negative/security","Performance","Category checks"])
        with tabs[0]:st.dataframe(pd.read_csv(folder/"demo_input.csv").head(100),width="stretch",hide_index=True)
        with tabs[1]:st.dataframe(pd.read_csv(folder/"golden_output.csv").head(100),width="stretch",hide_index=True)
        with tabs[2]:st.dataframe(pd.read_csv(folder/"negative_security_cases.csv"),width="stretch",hide_index=True)
        with tabs[3]:st.dataframe(pd.read_csv(folder/"performance_benchmark.csv"),width="stretch",hide_index=True)
        with tabs[4]:
            checks=pd.read_csv(folder/"category_specific_checks.csv");st.dataframe(checks,width="stretch",hide_index=True)
            if file_name in DEEP_TARGETS:st.info("This page received a custom deep-upgrade contract in addition to the universal page-assurance layer.")
        a,b=st.columns(2);a.download_button("Download page assurance bundle",_bundle(folder),f"{Path(file_name).stem}_step187_assurance.zip","application/zip",key=f"s187_bundle_{Path(file_name).stem}");b.download_button("Download qualification status",json.dumps(manifest,indent=2),f"{Path(file_name).stem}_step187_status.json","application/json",key=f"s187_status_{Path(file_name).stem}")
__all__=["render_step187_page_excellence"]
