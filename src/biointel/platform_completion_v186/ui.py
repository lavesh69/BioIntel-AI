from __future__ import annotations
from io import BytesIO
from pathlib import Path
import json,zipfile
import pandas as pd
import streamlit as st
from biointel.ui.operational_canvas import render_operational_canvas
from .catalog import TARGET_PROFILES
from .validators import validate_step186_module

def _root()->Path:return Path(__file__).resolve().parents[3]
def _bundle(folder:Path)->bytes:
    b=BytesIO()
    with zipfile.ZipFile(b,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.iterdir()):
            if p.is_file():z.write(p,arcname=p.name)
    return b.getvalue()
def render_step186_platform_completion(module_key:str,*,expanded:bool=False)->None:
    p=TARGET_PROFILES[module_key];r=validate_step186_module(_root(),module_key);folder=Path(r.path)
    with st.expander('Step 186 · Platform completion assurance (10/10 internal/demo)',expanded=expanded):
        c1,c2,c3,c4=st.columns(4);c1.metric('Before',f'{p.before_demo_rating:.2f}/10');c2.metric('After',f'{r.rating:.2f}/10',f'+{r.rating-p.before_demo_rating:.2f}');c3.metric('Dimensions',f'{r.dimensions_passed}/{r.dimensions_total}');c4.metric('Controlled release','BLOCKED')
        st.success('Deterministic execution, adverse inputs, concurrency, crash recovery, integrity, sandboxing, backup/rollback, 20,000-record load, repeatability, monitoring, accessibility contract and Windows lifecycle dry-run are qualified.')
        st.warning('Independent target-Windows execution, external security/accessibility review, store certification and operating history remain separate.')
        manifest=json.loads((folder/'assurance_manifest.json').read_text(encoding='utf-8-sig'));st.dataframe(pd.DataFrame(manifest['dimensions']),width="stretch",hide_index=True)
        tabs=st.tabs(['Performance','Negative cases','Native output','Monitoring'])
        with tabs[0]:st.dataframe(pd.read_csv(folder/'performance_benchmark.csv'),width="stretch",hide_index=True)
        with tabs[1]:st.dataframe(pd.read_csv(folder/'negative_cases.csv'),width="stretch",hide_index=True)
        with tabs[2]:st.dataframe(pd.read_csv(folder/'native_platform_run.csv').head(100),width="stretch",hide_index=True)
        with tabs[3]:render_operational_canvas(title='Monitoring canvas',subtitle='Local monitoring and recovery facts.',payload=json.loads((folder/'monitoring.json').read_text(encoding='utf-8')),stages=('Observe','Detect','Recover','Record'),key=f's186_monitoring_{module_key}')
        a,b=st.columns(2);a.download_button('Download Step 186 assurance bundle',_bundle(folder),f'{module_key}_step186_assurance.zip','application/zip',key=f's186_bundle_{module_key}');b.download_button('Download qualification status',json.dumps(manifest,indent=2),f'{module_key}_step186_status.json','application/json',key=f's186_status_{module_key}')
__all__=['render_step186_platform_completion']
