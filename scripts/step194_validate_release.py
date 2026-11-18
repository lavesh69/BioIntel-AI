from __future__ import annotations
import argparse, json, hashlib
from datetime import datetime, timezone
from pathlib import Path

def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
 return h.hexdigest()

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--root',default='.');ap.add_argument('--output');ap.add_argument('--allow-uninstalled',action='store_true');ap.add_argument('--deep-hashes',action='store_true');a=ap.parse_args()
 r=Path(a.root).resolve(); checks=[]
 def add(n,p,d):checks.append({'name':n,'passed':bool(p),'detail':str(d)})
 req=['app.py','INSTALL_WINDOWS.bat','RUN_BOTH_WINDOWS.bat','REPAIR_INSTALL_WINDOWS.bat','scripts/install_windows_step194.py','scripts/run_biointel_step194.py','requirements.lock','requirements-windows-cp311-offline.lock']
 m=[x for x in req if not (r/x).is_file()];add('required files',not m,m or 'complete')
 mm=[i for i in range(1,5) if not (r/'.release_parts'/f'step194_part{i}.ok').is_file()];add('four part markers',not mm,mm or 'complete')
 try:
  payload=json.loads((r/'STEP194_SOURCE_MANIFEST_SHA256.json').read_text()); entries=payload['entries']; bad=[]
  for row in entries:
   p=r/row['path']
   if not p.is_file() or p.stat().st_size!=row['size_bytes'] or (a.deep_hashes and sha(p)!=row['sha256']):bad.append(row['path'])
  detail=f'checked={len(entries)} bad={len(bad)}'
  if bad: detail += ' files=' + ', '.join(bad[:20])
  add('source manifest',not bad,detail)
 except Exception as e:add('source manifest',False,e)
 if not a.allow_uninstalled:add('installed environment',(r/'.venv/Scripts/python.exe').is_file(),'.venv/Scripts/python.exe')
 passed=all(x['passed'] for x in checks); out={'schema':'biointel.step194.validation.v1','generated_at':datetime.now(timezone.utc).isoformat(),'passed':passed,'checks':checks}
 op=Path(a.output) if a.output else r/'reports/step194/validation.json'; op=op if op.is_absolute() else r/op; op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,indent=2));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
