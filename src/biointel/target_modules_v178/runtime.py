from __future__ import annotations
from dataclasses import asdict, dataclass
import importlib.util, json, os, platform, shutil, subprocess
from pathlib import Path
from typing import Any
import pandas as pd
from biointel.runtime_v170.catalog import engine_catalog, reference_catalog
from .catalog import TARGET_MODULES, TARGET_PROFILES

@dataclass(frozen=True)
class EngineProbe:
    engine: str; label: str; source: str; discovered: bool; executable: str; version: str; probe_status: str; install_route: str

REFERENCE_FLAGS=('present','release_pinned','checksum_verified','licence_accepted','schema_validated','scientific_reviewed','provenance_chain_complete')
MODEL_FLAGS=('present','weights_hash_verified','provenance_recorded','licence_accepted','intended_use_locked','benchmark_passed','leakage_audit_passed','calibration_passed','subgroup_analysis_passed','robustness_passed','external_site_passed')
COHORT_FLAGS=('present','use_permission_recorded','schema_validated','endpoint_locked','split_locked','leakage_audit_passed','missingness_reviewed','subgroup_coverage_reviewed','independent','external_site_passed')
GOVERNANCE_FLAGS=('present','owner_assigned','risk_assessment_approved','privacy_security_reviewed','acceptance_plan_approved','monitoring_slo_approved','rollback_tested')
EVIDENCE_FLAGS=('independent_validation_complete','wet_lab_or_prospective_confirmation_complete','domain_expert_signoff_complete','formal_release_review_complete','rollback_rehearsal_complete','monitoring_activation_complete')

def _match(value: Any,key: str)->bool:return key in {x.strip() for x in str(value or '').split(',') if x.strip()}

def required_engines(module_key: str)->pd.DataFrame:
    if module_key not in TARGET_MODULES:raise KeyError(module_key)
    base=engine_catalog();base=base[base['modules'].map(lambda v:_match(v,module_key))].copy()
    rows=[];known=set(base.get('engine',pd.Series(dtype=str)).astype(str))
    for engine,label,route in TARGET_PROFILES[module_key].supplemental_engines:
        if engine not in known:rows.append({'engine':engine,'label':label,'install_route':route,'smoke_test':'','platform_target':'Windows/Python'})
    return pd.concat([base,pd.DataFrame(rows)],ignore_index=True,sort=False) if rows else base.reset_index(drop=True)

def required_references(module_key: str)->pd.DataFrame:
    if module_key not in TARGET_MODULES:raise KeyError(module_key)
    base=reference_catalog();base=base[base['modules'].map(lambda v:_match(v,module_key))].copy();known=set(base.get('reference_id',pd.Series(dtype=str)).astype(str))
    rows=[]
    for rid in TARGET_PROFILES[module_key].supplemental_references:
        if rid not in known:rows.append({'reference_id':rid,'label':rid.replace('-',' ').title(),'release_mode':'operator-pinned','licence_id':'source-provider-terms','expected_format':'provider-specific','download_strategy':'manual-qualified'})
    return pd.concat([base,pd.DataFrame(rows)],ignore_index=True,sort=False) if rows else base.reset_index(drop=True)

def _probe_cmd(exe:str,smoke:str,execute:bool)->tuple[str,str]:
    if not execute:return 'not executed','discovered'
    cmd=[x.strip() for x in str(smoke or '').split(',') if x.strip()] or [exe,'--version'];cmd[0]=exe
    try:r=subprocess.run(cmd,capture_output=True,text=True,timeout=20,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:return str(exc),'probe-failed'
    out=' '.join((r.stdout or r.stderr or '').strip().split())[:500]
    return out or f'exit={r.returncode}','pass' if r.returncode==0 else 'probe-failed'

def probe_engines(module_key:str,execute_smoke_tests:bool=False)->pd.DataFrame:
    rows=[]
    for item in required_engines(module_key).to_dict('records'):
        engine=str(item['engine']);label=str(item.get('label') or engine);route=str(item.get('install_route') or '')
        if engine.startswith('python:'):
            mod=engine.split(':',1)[1];found=importlib.util.find_spec(mod) is not None
            status='pass' if found and execute_smoke_tests else ('discovered' if found else 'missing')
            rows.append(asdict(EngineProbe(engine,label,'python-package',found,mod,'importable' if found else 'not found',status,route or 'pinned-python-venv')));continue
        candidates=[engine,str(label).split()[0],str(label).split()[0].lower()];exe=next((p for n in candidates if n and (p:=shutil.which(n))), '')
        version,status=_probe_cmd(exe,str(item.get('smoke_test') or ''),execute_smoke_tests) if exe else ('not found','missing')
        rows.append(asdict(EngineProbe(engine,label,'specialist-engine',bool(exe),exe,version,status,route)))
    return pd.DataFrame(rows)

def _roots(root:Path,kind:str)->list[Path]:
    env=os.environ.get(f'BIOINTEL_{kind.upper()}_ROOT','').strip();vals=[Path(env).expanduser() if env else None,root/'UserData'/f'{kind}s',root/'UserData'/'step178'/f'{kind}s',root/'data'/f'{kind}s']
    return [p.resolve() for p in vals if p is not None]

def _load_manifest(folder:Path)->dict[str,Any]:
    for name in ('qualification_manifest.json','manifest.json','evidence_manifest.json'):
        path=folder/name
        if path.is_file():
            try:return json.loads(path.read_text(encoding='utf-8-sig'))
            except (OSError,ValueError):return {}
    return {}

def _flag(payload:dict[str,Any],name:str)->bool:
    aliases={'licence_accepted':('licence_accepted','license_accepted','terms_accepted'),'checksum_verified':('checksum_verified','sha256_verified','provider_checksum_verified'),'release_pinned':('release_pinned','version_locked'),'scientific_reviewed':('scientific_reviewed','scientific_review_complete')}
    return any(bool(payload.get(x)) for x in aliases.get(name,(name,)))

def _probe_assets(root:str|Path,kind:str,ids:tuple[str,...],flags:tuple[str,...])->pd.DataFrame:
    project=Path(root).resolve();bases=_roots(project,kind);rows=[]
    for asset_id in ids:
        folder=next((base/asset_id for base in bases if (base/asset_id).exists()),bases[0]/asset_id);payload=_load_manifest(folder) if folder.exists() else {}
        row={'asset_id':asset_id,'path':str(folder)}
        for flag in flags:row[flag]=folder.exists() if flag=='present' else _flag(payload,flag)
        row['qualification_status']='qualified' if all(bool(row[f]) for f in flags) else 'review';rows.append(row)
    return pd.DataFrame(rows)

def probe_references(root:str|Path,module_key:str)->pd.DataFrame:return _probe_assets(root,'reference',tuple(required_references(module_key)['reference_id'].astype(str)),REFERENCE_FLAGS)
def probe_models(root:str|Path,module_key:str)->pd.DataFrame:return _probe_assets(root,'model',TARGET_PROFILES[module_key].model_assets,MODEL_FLAGS)
def probe_cohorts(root:str|Path,module_key:str)->pd.DataFrame:return _probe_assets(root,'cohort',TARGET_PROFILES[module_key].cohort_assets,COHORT_FLAGS)
def probe_governance(root:str|Path,module_key:str)->pd.DataFrame:return _probe_assets(root,'governance',TARGET_PROFILES[module_key].governance_assets,GOVERNANCE_FLAGS)
def probe_external_evidence(root:str|Path,module_key:str)->dict[str,bool]:
    folder=Path(root).resolve()/'UserData'/'step178'/'evidence'/module_key;payload=_load_manifest(folder);return {f:_flag(payload,f) for f in EVIDENCE_FLAGS}
def host_summary()->dict[str,Any]:return {'platform':platform.platform(),'python':platform.python_version(),'architecture':platform.machine(),'cpu_threads':os.cpu_count() or 0,'wsl_available':bool(shutil.which('wsl') or shutil.which('wsl.exe'))}
__all__=['REFERENCE_FLAGS','MODEL_FLAGS','COHORT_FLAGS','GOVERNANCE_FLAGS','EVIDENCE_FLAGS','required_engines','required_references','probe_engines','probe_references','probe_models','probe_cohorts','probe_governance','probe_external_evidence','host_summary']
