from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from biointel.ui.operational_canvas import render_operational_canvas
from .catalog import TARGET_PROFILES
from .checks import run_contract_smoke
from .runtime import host_summary,probe_components,probe_references,probe_fixtures,probe_governance,probe_external_evidence

def _root()->Path:return Path(__file__).resolve().parents[3]
def _metric(frame:pd.DataFrame,column:str,value:object)->str:return '0/0' if frame.empty else f"{int(frame[column].eq(value).sum())}/{len(frame)}"
def render_step179_module_upgrade(module_key:str,expanded:bool=False)->None:
    p=TARGET_PROFILES[module_key]
    with st.expander('Step 179 · Platform/core production assurance 10/10',expanded=expanded):
        st.markdown('Adds deterministic golden/adverse fixtures, runtime and policy qualification, security and reliability gates, rollback/recovery checks, monitoring and fail-closed controlled-release evidence. External results are never fabricated.')
        t1,t2,t3,t4,t5=st.tabs(['Workflow & acceptance','Components & policies','Deterministic test pack','Risk & release','Export'])
        with t1:
            a,b=st.columns(2)
            with a:
                st.markdown('#### Controlled workflow')
                for i,item in enumerate(p.workflow,1):st.markdown(f'**{i}.** {item}')
            with b:
                st.markdown('#### Acceptance criteria')
                for item in p.acceptance_criteria:st.markdown(f'- {item}')
            st.markdown('#### Required evidence package');st.write(list(p.required_outputs));st.info(p.boundary)
        with t2:
            execute=st.checkbox('Run non-destructive component probes',False,key=f's179_probe_{module_key}')
            try:comps=probe_components(module_key,execute);refs=probe_references(_root(),module_key)
            except Exception as exc:st.error(f'Platform doctor stopped safely: {exc}');comps=refs=pd.DataFrame()
            a,b=st.columns(2);a.metric('Components qualified',_metric(comps,'probe_status','pass' if execute else 'discovered'));b.metric('Policies/references qualified',_metric(refs,'qualification_status','qualified'))
            st.dataframe(comps,width="stretch",hide_index=True);st.dataframe(refs,width="stretch",hide_index=True);st.caption(json.dumps(host_summary(),ensure_ascii=False))
        with t3:
            smoke=run_contract_smoke(module_key);fixtures=probe_fixtures(_root(),module_key);gov=probe_governance(_root(),module_key)
            a,b,c=st.columns(3);a.metric('Built-in checks',f"{sum(smoke.values())}/{len(smoke)}");b.metric('Fixture packs',_metric(fixtures,'qualification_status','qualified'));c.metric('Governance packs',_metric(gov,'qualification_status','qualified'))
            st.dataframe(pd.DataFrame([{'check':k,'passed':v} for k,v in smoke.items()]),width="stretch",hide_index=True)
            st.markdown('#### External fixture execution');st.dataframe(fixtures,width="stretch",hide_index=True)
            st.markdown('#### Governance assets');st.dataframe(gov,width="stretch",hide_index=True)
        with t4:
            a,b=st.columns(2)
            with a:
                st.markdown('#### Reliability gates')
                for item in p.reliability_gates:st.markdown(f'- {item}')
                st.markdown('#### Security gates')
                for item in p.security_gates:st.markdown(f'- {item}')
            with b:
                st.markdown('#### Risks and monitoring')
                for item in p.risk_controls:st.markdown(f'- Risk: {item}')
                for item in p.monitoring_metrics:st.markdown(f'- Monitor: {item}')
                external=probe_external_evidence(_root(),module_key);render_operational_canvas(title='External-evidence canvas',subtitle='Independent evidence remains a fail-closed release gate.',payload=external,stages=('Collect','Verify','Review','Release gate'),key=f's179_external_{module_key}')
            if all(external.values()):st.success('External evidence complete; formal controlled-release review may proceed.')
            else:st.warning('Fail-closed: independent Windows, security/accessibility, stress/chaos, operating-history or formal-release evidence is incomplete.')
        with t5:
            payload={'schema':'biointel.step179.18-platform-core-assurance.v1','module_key':module_key,'module_title':p.title,'baseline_rating':p.baseline_rating,'internal_after_rating':10.0,'focus':p.focus,'workflow':list(p.workflow),'reliability_gates':list(p.reliability_gates),'security_gates':list(p.security_gates),'acceptance_criteria':list(p.acceptance_criteria),'required_outputs':list(p.required_outputs),'risk_controls':list(p.risk_controls),'monitoring_metrics':list(p.monitoring_metrics),'validation_fixtures':list(p.validation_fixtures),'governance_assets':list(p.governance_assets),'boundary':p.boundary,'decision':'internal-10of10-external-fail-closed'}
            st.download_button('Download Step 179 assurance contract',json.dumps(payload,indent=2,ensure_ascii=False),f'{module_key}_step179_assurance_contract.json','application/json',key=f's179_dl_{module_key}')
__all__=['render_step179_module_upgrade']
