from __future__ import annotations
from dataclasses import asdict,dataclass
import importlib.util,json,os,platform,shutil,subprocess
from pathlib import Path
from typing import Any
import pandas as pd
from .catalog import TARGET_MODULES,TARGET_PROFILES

@dataclass(frozen=True)
class ComponentProbe:
    component:str;label:str;source:str;discovered:bool;location:str;version:str;probe_status:str;install_route:str
REFERENCE_FLAGS=('present','release_pinned','checksum_verified','licence_accepted','schema_validated','provenance_complete','owner_approved')
FIXTURE_FLAGS=('present','checksum_verified','expected_outputs_locked','negative_cases_present','corruption_cases_present','recovery_cases_present','scale_cases_present','cross_platform_cases_present','last_run_passed')
GOVERNANCE_FLAGS=('present','owner_assigned','risk_assessment_approved','security_reviewed','privacy_reviewed','accessibility_reviewed','acceptance_plan_approved','monitoring_slo_approved','rollback_tested')
EXTERNAL_FLAGS=('independent_validation_complete','load_stress_chaos_complete','security_review_complete','accessibility_review_complete','windows_physical_qualification_complete','operating_history_complete','formal_release_review_complete')

def required_components(module_key:str)->pd.DataFrame:
    if module_key not in TARGET_MODULES:raise KeyError(module_key)
    return pd.DataFrame([{'component':c,'label':l,'install_route':r,'platform_target':'Windows/Python','smoke_test':''} for c,l,r in TARGET_PROFILES[module_key].supplemental_components])

def required_references(module_key:str)->pd.DataFrame:
    if module_key not in TARGET_MODULES:raise KeyError(module_key)
    return pd.DataFrame([{'reference_id':r,'label':r.replace('-',' ').title(),'release_mode':'operator-pinned','licence_id':'internal-or-provider-policy','expected_format':'JSON/CSV/document','download_strategy':'manual-qualified'} for r in TARGET_PROFILES[module_key].supplemental_references])

def _probe_cmd(exe:str,execute:bool)->tuple[str,str]:
    if not execute:return 'not executed','discovered'
    try:r=subprocess.run([exe,'--version'],capture_output=True,text=True,timeout=20,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:return str(exc),'probe-failed'
    out=' '.join((r.stdout or r.stderr or '').strip().split())[:500]
    return out or f'exit={r.returncode}','pass' if r.returncode==0 else 'probe-failed'

def probe_components(module_key:str,execute_smoke_tests:bool=False)->pd.DataFrame:
    rows=[]
    for item in required_components(module_key).to_dict('records'):
        comp=str(item['component']);label=str(item['label']);route=str(item['install_route'])
        if comp.startswith('python:'):
            mod=comp.split(':',1)[1].replace('-','_');found=importlib.util.find_spec(mod) is not None
            status='pass' if found and execute_smoke_tests else ('discovered' if found else 'missing')
            rows.append(asdict(ComponentProbe(comp,label,'python-package',found,mod,'importable' if found else 'not found',status,route)));continue
        exe=shutil.which(comp) or shutil.which(comp+'.exe') or ''
        version,status=_probe_cmd(exe,execute_smoke_tests) if exe else ('not found','missing')
        rows.append(asdict(ComponentProbe(comp,label,'executable',bool(exe),exe,version,status,route)))
    return pd.DataFrame(rows)

def _load_manifest(folder:Path)->dict[str,Any]:
    for name in ('qualification_manifest.json','manifest.json','evidence_manifest.json'):
        path=folder/name
        if path.is_file():
            try:return json.loads(path.read_text(encoding='utf-8-sig'))
            except (OSError,ValueError):return {}
    return {}

def _flag(payload:dict[str,Any],name:str)->bool:
    aliases={'licence_accepted':('licence_accepted','license_accepted','terms_accepted'),'checksum_verified':('checksum_verified','sha256_verified'),'release_pinned':('release_pinned','version_locked')}
    return any(bool(payload.get(x)) for x in aliases.get(name,(name,)))

def _roots(root:Path,kind:str)->list[Path]:
    env=os.environ.get(f'BIOINTEL_{kind.upper()}_ROOT','').strip()
    vals=[Path(env).expanduser() if env else None,root/'UserData'/'step179'/kind,root/'UserData'/kind,root/'data'/kind]
    return [p.resolve() for p in vals if p is not None]

def _probe_assets(root:str|Path,kind:str,ids:tuple[str,...],flags:tuple[str,...])->pd.DataFrame:
    project=Path(root).resolve();bases=_roots(project,kind);rows=[]
    for asset_id in ids:
        folder=next((base/asset_id for base in bases if (base/asset_id).exists()),bases[0]/asset_id);payload=_load_manifest(folder) if folder.exists() else {}
        row={'asset_id':asset_id,'path':str(folder)}
        for flag in flags:row[flag]=folder.exists() if flag=='present' else _flag(payload,flag)
        row['qualification_status']='qualified' if all(bool(row[f]) for f in flags) else 'review';rows.append(row)
    return pd.DataFrame(rows)

def probe_references(root:str|Path,module_key:str)->pd.DataFrame:return _probe_assets(root,'references',tuple(required_references(module_key)['reference_id'].astype(str)),REFERENCE_FLAGS)
def probe_fixtures(root:str|Path,module_key:str)->pd.DataFrame:return _probe_assets(root,'fixtures',TARGET_PROFILES[module_key].validation_fixtures,FIXTURE_FLAGS)
def probe_governance(root:str|Path,module_key:str)->pd.DataFrame:return _probe_assets(root,'governance',TARGET_PROFILES[module_key].governance_assets,GOVERNANCE_FLAGS)
def probe_external_evidence(root:str|Path,module_key:str)->dict[str,bool]:
    folder=Path(root).resolve()/'UserData'/'step179'/'evidence'/module_key;payload=_load_manifest(folder);return {f:_flag(payload,f) for f in EXTERNAL_FLAGS}
def host_summary()->dict[str,Any]:return {'platform':platform.platform(),'python':platform.python_version(),'architecture':platform.machine(),'cpu_threads':os.cpu_count() or 0,'windows':platform.system().lower()=='windows','wsl_available':bool(shutil.which('wsl') or shutil.which('wsl.exe'))}
__all__=['REFERENCE_FLAGS','FIXTURE_FLAGS','GOVERNANCE_FLAGS','EXTERNAL_FLAGS','required_components','required_references','probe_components','probe_references','probe_fixtures','probe_governance','probe_external_evidence','host_summary']
