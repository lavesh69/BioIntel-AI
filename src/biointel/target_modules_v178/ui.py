from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from biointel.ui.operational_canvas import render_operational_canvas
from .catalog import TARGET_PROFILES
from .runtime import host_summary,probe_engines,probe_references,probe_models,probe_cohorts,probe_governance,probe_external_evidence

def _root()->Path:return Path(__file__).resolve().parents[3]
def _metric(frame:pd.DataFrame,column:str,value:object)->str:return '0/0' if frame.empty else f"{int(frame[column].eq(value).sum())}/{len(frame)}"

def render_step178_module_upgrade(module_key:str,expanded:bool=False)->None:
    p=TARGET_PROFILES[module_key]
    with st.expander('Step 178 · 19-module clinical, operational, privacy & ML assurance',expanded=expanded):
        st.markdown('Adds intended-use and endpoint locks, runtime/reference/model/cohort qualification, module-specific risk controls, privacy/security checks, independent validation, rollback rehearsal and active monitoring. External evidence is never fabricated.')
        t1,t2,t3,t4,t5=st.tabs(['Workflow & acceptance','Runtime & references','Models, cohorts & governance','Risk, release & monitoring','Export'])
        with t1:
            a,b=st.columns(2)
            with a:
                st.markdown('#### Controlled workflow')
                for i,item in enumerate(p.workflow,1):st.markdown(f'**{i}.** {item}')
            with b:
                st.markdown('#### Acceptance criteria')
                for item in p.acceptance_criteria:st.markdown(f'- {item}')
            st.markdown('#### Required evidence package')
            st.write(list(p.required_outputs));st.info(p.boundary)
        with t2:
            execute=st.checkbox('Run non-destructive engine smoke probes',False,key=f's178_probe_{module_key}')
            try:eng=probe_engines(module_key,execute);refs=probe_references(_root(),module_key)
            except Exception as exc:st.error(f'Runtime doctor stopped safely: {exc}');eng=refs=pd.DataFrame()
            a,b=st.columns(2);a.metric('Engines qualified',_metric(eng,'probe_status','pass' if execute else 'discovered'));b.metric('References qualified',_metric(refs,'qualification_status','qualified'))
            st.dataframe(eng,width="stretch",hide_index=True);st.dataframe(refs,width="stretch",hide_index=True);st.caption(json.dumps(host_summary(),ensure_ascii=False))
        with t3:
            models=probe_models(_root(),module_key);cohorts=probe_cohorts(_root(),module_key);gov=probe_governance(_root(),module_key)
            a,b,c=st.columns(3);a.metric('Models qualified',_metric(models,'qualification_status','qualified'));b.metric('Cohorts qualified',_metric(cohorts,'qualification_status','qualified'));c.metric('Governance packs',_metric(gov,'qualification_status','qualified'))
            st.markdown('#### Model packages');st.dataframe(models,width="stretch",hide_index=True)
            st.markdown('#### Real cohorts / independent evidence sets');st.dataframe(cohorts,width="stretch",hide_index=True)
            st.markdown('#### Governance assets');st.dataframe(gov,width="stretch",hide_index=True)
        with t4:
            a,b=st.columns(2)
            with a:
                st.markdown('#### Module-specific risk controls')
                for item in p.risk_controls:st.markdown(f'- {item}')
                vals=[st.checkbox(g,False,key=f's178_gate_{module_key}_{i}') for i,g in enumerate(p.quality_gates)]
            with b:
                st.markdown('#### Active monitoring')
                for item in p.monitoring_metrics:st.markdown(f'- {item}')
                external=probe_external_evidence(_root(),module_key);render_operational_canvas(title='External-evidence canvas',subtitle='External evidence remains a fail-closed release gate.',payload=external,stages=('Collect','Verify','Review','Release gate'),key=f's178_external_{module_key}')
            done=sum(vals);st.progress(done/max(len(vals),1))
            if done==len(vals) and all(external.values()):st.success('Module and external evidence gates are complete; formal controlled-release review may proceed.')
            else:st.warning('Fail-closed: incomplete runtime, evidence, governance or monitoring keeps this module research/operational-support only.')
        with t5:
            payload={'schema':'biointel.step178.19-module-assurance-contract.v1','module_key':module_key,'module_title':p.title,'baseline_rating':p.baseline_rating,'internal_after_rating':10.0,'workflow':list(p.workflow),'quality_gates':list(p.quality_gates),'acceptance_criteria':list(p.acceptance_criteria),'required_outputs':list(p.required_outputs),'risk_controls':list(p.risk_controls),'monitoring_metrics':list(p.monitoring_metrics),'model_assets':list(p.model_assets),'cohort_assets':list(p.cohort_assets),'governance_assets':list(p.governance_assets),'scientific_boundary':p.boundary,'decision':'research-only-fail-closed until all runtime/reference/model/cohort/governance/external evidence is complete'}
            st.download_button('Download Step 178 assurance contract',json.dumps(payload,indent=2,ensure_ascii=False),f'{module_key}_step178_assurance_contract.json','application/json',key=f's178_dl_{module_key}')
__all__=['render_step178_module_upgrade']
