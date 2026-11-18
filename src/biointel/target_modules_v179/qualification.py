from __future__ import annotations
from dataclasses import asdict,dataclass
from pathlib import Path
import pandas as pd
from .catalog import TARGET_MODULES,TARGET_PROFILES
from .checks import smoke_passed
from .runtime import required_components,required_references,probe_components,probe_references,probe_fixtures,probe_governance,probe_external_evidence

@dataclass(frozen=True)
class ModuleQualification:
    module_key:str;module_title:str;baseline_rating:float;internal_after_rating:float;rating_improvement:float;improvement_percent:float
    workflow_contract_complete:bool;reliability_contract_complete:bool;security_contract_complete:bool;acceptance_contract_complete:bool;output_contract_complete:bool;risk_contract_complete:bool;monitoring_contract_complete:bool;ui_hook_present:bool
    component_plan_complete:bool;reference_plan_complete:bool;fixture_plan_complete:bool;governance_plan_complete:bool;deterministic_smoke_passed:bool
    component_qualification_fraction:float;reference_qualification_fraction:float;fixture_qualification_fraction:float;governance_qualification_fraction:float;external_evidence_fraction:float
    controlled_release_eligible:bool;decision:str;remaining_blockers:tuple[str,...]

def _fraction(frame:pd.DataFrame,column:str,value:object)->float:return 1.0 if frame.empty else float(frame[column].eq(value).mean())
def evaluate_module(root:str|Path,module_key:str,execute_component_probes:bool=False)->ModuleQualification:
    root=Path(root).resolve();p=TARGET_PROFILES[module_key];page=root/p.page;text=page.read_text(encoding='utf-8-sig') if page.is_file() else ''
    hook='render_step179_module_upgrade' in text and module_key in text
    comps_plan=required_components(module_key);refs_plan=required_references(module_key)
    comps=probe_components(module_key,execute_component_probes);refs=probe_references(root,module_key);fixtures=probe_fixtures(root,module_key);gov=probe_governance(root,module_key);external=probe_external_evidence(root,module_key)
    smoke=smoke_passed(module_key)
    checks=[len(p.workflow)>=6,len(p.reliability_gates)>=8,len(p.security_gates)>=6,len(p.acceptance_criteria)>=6,len(p.required_outputs)>=6,len(p.risk_controls)>=5,len(p.monitoring_metrics)>=4,hook,not comps_plan.empty,not refs_plan.empty,len(p.validation_fixtures)>=3,len(p.governance_assets)>=3,smoke]
    internal=round(10*sum(checks)/len(checks),2);improvement=round(internal-p.baseline_rating,2);pct=round(100*improvement/p.baseline_rating,1)
    cf=_fraction(comps,'probe_status','pass' if execute_component_probes else 'discovered');rf=_fraction(refs,'qualification_status','qualified');ff=_fraction(fixtures,'qualification_status','qualified');gf=_fraction(gov,'qualification_status','qualified');xf=sum(external.values())/len(external)
    eligible=bool(internal==10 and cf==rf==ff==gf==xf==1.0)
    blockers=[]
    if cf<1:blockers.append('required platform components are not fully discovered and smoke-qualified on the target Windows host')
    if rf<1:blockers.append('policy/reference assets lack complete release, checksum, licence, schema, provenance or owner approval')
    if ff<1:blockers.append('golden, adverse, corruption, recovery, scale and cross-platform fixtures are not fully executed and approved')
    if gf<1:blockers.append('risk, security, privacy, accessibility, acceptance, monitoring or rollback governance is incomplete')
    if xf<1:blockers.append('independent validation, load/stress/chaos, external security/accessibility, physical Windows qualification, operating history or formal review remains incomplete')
    return ModuleQualification(module_key,p.title,p.baseline_rating,internal,improvement,pct,len(p.workflow)>=6,len(p.reliability_gates)>=8,len(p.security_gates)>=6,len(p.acceptance_criteria)>=6,len(p.required_outputs)>=6,len(p.risk_controls)>=5,len(p.monitoring_metrics)>=4,hook,not comps_plan.empty,not refs_plan.empty,len(p.validation_fixtures)>=3,len(p.governance_assets)>=3,smoke,round(cf,4),round(rf,4),round(ff,4),round(gf,4),round(xf,4),eligible,'controlled-release-qualified' if eligible else 'internal-10of10-external-fail-closed',tuple(blockers))
def qualification_matrix(root:str|Path,execute_component_probes:bool=False)->pd.DataFrame:return pd.DataFrame([asdict(evaluate_module(root,k,execute_component_probes)) for k in TARGET_MODULES])
__all__=['ModuleQualification','evaluate_module','qualification_matrix']
