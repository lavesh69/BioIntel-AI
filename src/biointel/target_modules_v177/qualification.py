from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
import pandas as pd
from .catalog import TARGET_MODULES,TARGET_PROFILES
from .runtime import probe_engines,probe_references,probe_models,probe_cohorts,probe_external_evidence,required_engines,required_references

@dataclass(frozen=True)
class ModuleQualification:
    module_key:str; module_title:str; internal_upgrade_rating:float; workflow_contract_complete:bool; quality_gate_contract_complete:bool; output_contract_complete:bool; ui_hook_present:bool; engine_plan_complete:bool; reference_plan_complete:bool; model_plan_complete:bool; cohort_plan_complete:bool; engine_qualification_fraction:float; reference_qualification_fraction:float; model_qualification_fraction:float; cohort_qualification_fraction:float; external_evidence_fraction:float; controlled_release_eligible:bool; decision:str; remaining_blockers:tuple[str,...]

def _fraction(frame:pd.DataFrame,column:str,value:object)->float:
    return 1.0 if frame.empty else float(frame[column].eq(value).mean())

def evaluate_module(root:str|Path,module_key:str,execute_smoke_tests:bool=False)->ModuleQualification:
    root=Path(root).resolve(); p=TARGET_PROFILES[module_key]; page=root/p.page; text=page.read_text(encoding='utf-8-sig') if page.is_file() else ''
    hook='render_step177_module_upgrade' in text and module_key in text
    ep=required_engines(module_key); rp=required_references(module_key)
    eng=probe_engines(module_key,execute_smoke_tests); refs=probe_references(root,module_key); models=probe_models(root,module_key); cohorts=probe_cohorts(root,module_key); evidence=probe_external_evidence(root,module_key)
    checks=[len(p.workflow)>=5,len(p.quality_gates)>=6,len(p.required_outputs)>=5,bool(p.boundary),hook,not ep.empty,not rp.empty,len(p.model_assets)>=2,len(p.cohort_assets)>=2]
    internal=round(10*sum(checks)/len(checks),2)
    ef=_fraction(eng,'probe_status','pass' if execute_smoke_tests else 'discovered'); rf=_fraction(refs,'qualification_status','qualified'); mf=_fraction(models,'qualification_status','qualified'); cf=_fraction(cohorts,'qualification_status','qualified'); xf=sum(evidence.values())/len(evidence)
    eligible=bool(internal==10 and ef==rf==mf==cf==xf==1.0)
    blockers=[]
    if ef<1:blockers.append('specialist engines/runtime packages are not fully discovered and smoke-qualified')
    if rf<1:blockers.append('production references are not fully release/checksum/licence/schema/scientific qualified')
    if mf<1:blockers.append('authentic model packages lack complete provenance, benchmark, leakage, calibration, subgroup or external-site evidence')
    if cf<1:blockers.append('real cohorts lack complete permissions, schema, split, leakage, subgroup and independent external-site validation')
    if xf<1:blockers.append('wet-lab/orthogonal evidence, expert sign-off, formal release, rollback and monitoring approvals remain incomplete')
    return ModuleQualification(module_key,p.title,internal,len(p.workflow)>=5,len(p.quality_gates)>=6,len(p.required_outputs)>=5,hook,not ep.empty,not rp.empty,len(p.model_assets)>=2,len(p.cohort_assets)>=2,round(ef,4),round(rf,4),round(mf,4),round(cf,4),round(xf,4),eligible,'controlled-release-qualified' if eligible else 'research-only-fail-closed',tuple(blockers))

def qualification_matrix(root:str|Path,execute_smoke_tests:bool=False)->pd.DataFrame:
    return pd.DataFrame([asdict(evaluate_module(root,k,execute_smoke_tests)) for k in TARGET_MODULES])
__all__=['ModuleQualification','evaluate_module','qualification_matrix']
