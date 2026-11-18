from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Any

import pandas as pd

from biointel.runtime_v170.catalog import engine_catalog, reference_catalog
from .catalog import TARGET_MODULES, TARGET_PROFILES

@dataclass(frozen=True)
class EngineProbe:
    engine: str; label: str; source: str; discovered: bool; executable: str; version: str; probe_status: str; install_route: str

QUALIFICATION_FLAGS=("release_pinned","checksum_verified","licence_accepted","schema_validated","scientific_reviewed")
MODEL_FLAGS=("present","weights_hash_verified","provenance_recorded","licence_accepted","benchmark_passed","leakage_audit_passed","calibration_passed","subgroup_analysis_passed","external_site_passed")
COHORT_FLAGS=("present","use_permission_recorded","schema_validated","split_locked","leakage_audit_passed","subgroup_coverage_reviewed","independent","external_site_passed")
EVIDENCE_FLAGS=("wet_lab_or_orthogonal_complete","expert_signoff_complete","formal_release_review_complete","rollback_plan_tested","monitoring_plan_approved")

def _match(value: Any, key: str) -> bool:
    return key in {x.strip() for x in str(value or '').split(',') if x.strip()}

def required_engines(module_key: str) -> pd.DataFrame:
    if module_key not in TARGET_MODULES: raise KeyError(module_key)
    base=engine_catalog(); base=base[base['modules'].map(lambda v:_match(v,module_key))].copy()
    rows=[]
    for e,l,r in TARGET_PROFILES[module_key].supplemental_engines:
        rows.append({'engine':e,'label':l,'install_route':r,'smoke_test':'','platform_target':'Windows/Python'})
    return pd.concat([base,pd.DataFrame(rows)],ignore_index=True,sort=False) if rows else base.reset_index(drop=True)

def required_references(module_key: str) -> pd.DataFrame:
    if module_key not in TARGET_MODULES: raise KeyError(module_key)
    base=reference_catalog(); base=base[base['modules'].map(lambda v:_match(v,module_key))].copy()
    known=set(base.get('reference_id',pd.Series(dtype=str)).astype(str))
    rows=[]
    for rid in TARGET_PROFILES[module_key].supplemental_references:
        if rid not in known:
            rows.append({'reference_id':rid,'label':rid.replace('-',' ').title(),'release_mode':'operator-pinned','licence_id':'source-database-terms','expected_format':'provider-specific','download_strategy':'manual-qualified'})
    return pd.concat([base,pd.DataFrame(rows)],ignore_index=True,sort=False) if rows else base.reset_index(drop=True)

def _probe_cmd(exe: str, smoke: str, execute: bool)->tuple[str,str]:
    if not execute:return 'not executed','discovered'
    cmd=[x.strip() for x in str(smoke or '').split(',') if x.strip()] or [exe,'--version']; cmd[0]=exe
    try:c=subprocess.run(cmd,capture_output=True,text=True,timeout=15,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:return str(exc),'probe-failed'
    out=' '.join((c.stdout or c.stderr or '').strip().split())[:500]
    return out or f'exit={c.returncode}', 'pass' if c.returncode==0 else 'probe-failed'

def probe_engines(module_key: str, execute_smoke_tests: bool=False)->pd.DataFrame:
    rows=[]
    for item in required_engines(module_key).to_dict('records'):
        eng=str(item['engine']); label=str(item.get('label') or eng)
        if eng.startswith('python:'):
            mod=eng.split(':',1)[1]; found=importlib.util.find_spec(mod) is not None
            rows.append(asdict(EngineProbe(eng,label,'python-package',found,mod,'importable' if found else 'not found','pass' if found and execute_smoke_tests else ('discovered' if found else 'missing'),str(item.get('install_route') or 'pinned-python-venv')))); continue
        candidates=[eng,str(label).split()[0].lower()]; exe=next((p for n in candidates if n and (p:=shutil.which(n))), '')
        ver,status=_probe_cmd(exe,str(item.get('smoke_test') or ''),execute_smoke_tests) if exe else ('not found','missing')
        rows.append(asdict(EngineProbe(eng,label,'specialist-engine',bool(exe),exe,ver,status,str(item.get('install_route') or ''))))
    return pd.DataFrame(rows)

def _roots(root: Path, kind: str)->list[Path]:
    env=os.environ.get(f'BIOINTEL_{kind.upper()}_ROOT','').strip()
    vals=[Path(env).expanduser() if env else None,root/'UserData'/f'{kind}s',root/'UserData'/'step177'/f'{kind}s',root/'data'/f'{kind}s']
    return [p.resolve() for p in vals if p is not None]

def _load_manifest(folder: Path)->dict[str,Any]:
    for name in ('qualification_manifest.json','manifest.json','evidence_manifest.json'):
        p=folder/name
        if p.is_file():
            try:return json.loads(p.read_text(encoding='utf-8-sig'))
            except (OSError,ValueError):return {}
    return {}

def _flag(payload:dict[str,Any],name:str)->bool:
    aliases={'licence_accepted':('licence_accepted','license_accepted','terms_accepted'),'checksum_verified':('checksum_verified','sha256_verified','provider_checksum_verified'),'release_pinned':('release_pinned','version_locked'),'scientific_reviewed':('scientific_reviewed','scientific_review_complete')}
    return any(bool(payload.get(x)) for x in aliases.get(name,(name,)))

def _probe_assets(root:str|Path,module_key:str,kind:str,asset_ids:tuple[str,...],flags:tuple[str,...])->pd.DataFrame:
    project=Path(root).resolve(); bases=_roots(project,kind); rows=[]
    for aid in asset_ids:
        folder=next((b/aid for b in bases if (b/aid).exists()),bases[0]/aid); payload=_load_manifest(folder) if folder.exists() else {}
        row={'asset_id':aid,'path':str(folder)}
        for f in flags: row[f]=folder.exists() if f=='present' else _flag(payload,f)
        row['qualification_status']='qualified' if all(bool(row[f]) for f in flags) else 'review'
        rows.append(row)
    return pd.DataFrame(rows)

def probe_references(root:str|Path,module_key:str)->pd.DataFrame:
    ids=tuple(required_references(module_key)['reference_id'].astype(str)); return _probe_assets(root,module_key,'reference',ids,('present',)+QUALIFICATION_FLAGS)

def probe_models(root:str|Path,module_key:str)->pd.DataFrame:
    return _probe_assets(root,module_key,'model',TARGET_PROFILES[module_key].model_assets,MODEL_FLAGS)

def probe_cohorts(root:str|Path,module_key:str)->pd.DataFrame:
    return _probe_assets(root,module_key,'cohort',TARGET_PROFILES[module_key].cohort_assets,COHORT_FLAGS)

def probe_external_evidence(root:str|Path,module_key:str)->dict[str,bool]:
    folder=Path(root).resolve()/'UserData'/'step177'/'evidence'/module_key; payload=_load_manifest(folder)
    return {f:_flag(payload,f) for f in EVIDENCE_FLAGS}

def host_summary()->dict[str,Any]:
    return {'platform':platform.platform(),'python':platform.python_version(),'architecture':platform.machine(),'cpu_threads':os.cpu_count() or 0,'wsl_available':bool(shutil.which('wsl') or shutil.which('wsl.exe'))}

__all__=['EVIDENCE_FLAGS','host_summary','probe_engines','probe_references','probe_models','probe_cohorts','probe_external_evidence','required_engines','required_references']
