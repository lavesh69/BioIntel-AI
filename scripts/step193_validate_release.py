from __future__ import annotations
import argparse, hashlib, json, sys
from datetime import UTC, datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from biointel.mandatory_completion_v193.catalog import RELEASE_VERSION, TARGET_MODULES, PAGE_TO_MODULES
from biointel.mandatory_completion_v193.qualification import validate_module

PART_MARKERS=tuple(f'.release_parts/step193_part{i}.ok' for i in range(1,5))

def sha256(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
 return h.hexdigest()

def main()->int:
 p=argparse.ArgumentParser(); p.add_argument('--root',default='.'); p.add_argument('--output'); p.add_argument('--allow-uninstalled',action='store_true'); p.add_argument('--deep-hashes',action='store_true'); args=p.parse_args()
 root=Path(args.root).resolve(); checks=[]
 def add(name,passed,detail,severity='critical'): checks.append({'name':name,'passed':bool(passed),'detail':str(detail),'severity':severity})
 required=['app.py','INSTALL_WINDOWS.bat','RUN_BOTH_WINDOWS.bat','scripts/install_windows_step193.py','scripts/step193_self_test.py','scripts/step193_build_mandatory_completion.py','pages/262_Step193_Mandatory_Module_Completion_Install_Repair_Center.py','STEP193_RELEASE.json','STEP193_PACKAGE_PART_ASSIGNMENT.json','STEP193_SOURCE_MANIFEST_SHA256.json']
 missing=[x for x in required if not (root/x).is_file()]; add('required Step 193 files',not missing,missing or 'complete')
 missing_markers=[x for x in PART_MARKERS if not (root/x).is_file()]; add('four Step 193 part markers',not missing_markers,missing_markers or 'complete')
 try:
  import biointel
  add('version consistency',biointel.__version__==RELEASE_VERSION,f'{biointel.__version__} expected {RELEASE_VERSION}')
 except Exception as exc:add('version consistency',False,exc)
 missing_hooks=[]
 for page in PAGE_TO_MODULES:
  path=root/'pages'/page
  if not path.is_file() or 'STEP193_MANDATORY_COMPLETION_HOOK' not in path.read_text(encoding='utf-8-sig',errors='replace'):missing_hooks.append(page)
 add('79 major page hooks',not missing_hooks,f'missing={len(missing_hooks)}')
 qualification_bad=[]
 for key in TARGET_MODULES:
  q=validate_module(root,key)
  if not q.qualified: qualification_bad.append(f'{key}:{q.blockers}')
 add('80 module mandatory qualification',not qualification_bad,f'qualified={80-len(qualification_bad)}/80')
 try:
  assignment=json.loads((root/'STEP193_PACKAGE_PART_ASSIGNMENT.json').read_text())['assignments']
  absent=[x for x in assignment if not (root/x).is_file()]
  add('package assignment completeness',not absent,f'entries={len(assignment)}, missing={len(absent)}')
 except Exception as exc:add('package assignment completeness',False,exc)
 if args.deep_hashes:
  try:
   manifest=json.loads((root/'STEP193_SOURCE_MANIFEST_SHA256.json').read_text())['entries']; bad=[]
   for row in manifest:
    path=root/row['path']
    if not path.is_file() or path.stat().st_size!=row['size_bytes'] or sha256(path)!=row['sha256']:bad.append(row['path'])
   add('deep source hashes',not bad,f'checked={len(manifest)}, bad={len(bad)}')
  except Exception as exc:add('deep source hashes',False,exc)
 installed=args.allow_uninstalled or (root/'.venv/Scripts/python.exe').is_file(); add('installed environment',installed,'allowed before install' if args.allow_uninstalled else '.venv/Scripts/python.exe')
 failures=[x for x in checks if not x['passed'] and x['severity']=='critical']
 result={'schema':'biointel.step193.release-validation.v1','release_version':RELEASE_VERSION,'generated_at_utc':datetime.now(UTC).isoformat(),'passed':not failures,'checks':checks,'critical_failures':failures}
 output=Path(args.output) if args.output else root/'reports/step193/extracted_release_validation.json'
 if not output.is_absolute(): output=root/output
 output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(result,indent=2,default=str)+'\n')
 print(json.dumps(result,indent=2,default=str)); return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
