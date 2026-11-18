from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from biointel.ui.operational_canvas import render_operational_canvas
from .catalog import TARGET_PROFILES
from .runtime import host_summary,probe_engines,probe_references,probe_models,probe_cohorts,probe_external_evidence

def _root()->Path:return Path(__file__).resolve().parents[3]
def _metric(df:pd.DataFrame,col:str,val:object)->str:return '0/0' if df.empty else f"{int(df[col].eq(val).sum())}/{len(df)}"

def render_step177_module_upgrade(module_key:str,expanded:bool=False)->None:
    p=TARGET_PROFILES[module_key]
    with st.expander('Step 177 · 21-module model, cohort & runtime qualification',expanded=expanded):
        st.markdown('Adds module-specific workflows, runtime/reference doctors, authentic model and cohort evidence contracts, leakage/calibration/subgroup checks, independent-site gates and reproducible fail-closed exports. No licensed data, wet-lab result or expert approval is fabricated.')
        t1,t2,t3,t4,t5=st.tabs(['Workflow','Runtime & references','Models & cohorts','Release gates','Export'])
        with t1:
            a,b=st.columns(2)
            with a:
                st.markdown('#### Qualified workflow contract')
                for i,x in enumerate(p.workflow,1):st.markdown(f'**{i}.** {x}')
            with b:
                st.markdown('#### Required result package')
                for x in p.required_outputs:st.markdown(f'- {x}')
            st.info(p.boundary)
        with t2:
            execute=st.checkbox('Run non-destructive engine smoke probes',False,key=f's177_probe_{module_key}')
            try:eng=probe_engines(module_key,execute); refs=probe_references(_root(),module_key)
            except Exception as exc:st.error(f'Runtime doctor stopped safely: {exc}');eng=refs=pd.DataFrame()
            c1,c2=st.columns(2); c1.metric('Engines qualified',_metric(eng,'probe_status','pass' if execute else 'discovered')); c2.metric('References qualified',_metric(refs,'qualification_status','qualified'))
            st.dataframe(eng,width="stretch",hide_index=True);st.dataframe(refs,width="stretch",hide_index=True);st.caption(json.dumps(host_summary(),ensure_ascii=False))
        with t3:
            models=probe_models(_root(),module_key);cohorts=probe_cohorts(_root(),module_key)
            c1,c2=st.columns(2);c1.metric('Models qualified',_metric(models,'qualification_status','qualified'));c2.metric('Cohorts qualified',_metric(cohorts,'qualification_status','qualified'))
            st.markdown('#### Authentic models / analytical packages');st.dataframe(models,width="stretch",hide_index=True)
            st.markdown('#### Real cohorts / independent benchmarks');st.dataframe(cohorts,width="stretch",hide_index=True)
        with t4:
            vals=[st.checkbox(g,False,key=f's177_gate_{module_key}_{i}') for i,g in enumerate(p.quality_gates)]
            external=probe_external_evidence(_root(),module_key);render_operational_canvas(title='External-evidence canvas',subtitle='External evidence remains a fail-closed release gate.',payload=external,stages=('Collect','Verify','Review','Release gate'),key=f's177_external_{module_key}')
            done=sum(vals);st.progress(done/max(len(vals),1))
            if done==len(vals) and all(external.values()):st.success('All module and external evidence gates are complete; formal controlled-release review may proceed.')
            else:st.warning('Fail-closed: incomplete runtime, model, cohort or external evidence keeps this module research-only.')
        with t5:
            payload={'schema':'biointel.step177.21-module-qualification.v1','module_key':module_key,'module_title':p.title,'workflow':list(p.workflow),'quality_gates':list(p.quality_gates),'required_outputs':list(p.required_outputs),'model_assets':list(p.model_assets),'cohort_assets':list(p.cohort_assets),'scientific_boundary':p.boundary,'decision':'research-only-fail-closed until all runtime/reference/model/cohort/external evidence is complete'}
            st.download_button('Download Step 177 qualification contract',json.dumps(payload,indent=2,ensure_ascii=False),f'{module_key}_step177_qualification_contract.json','application/json',key=f's177_dl_{module_key}')
__all__=['render_step177_module_upgrade']
