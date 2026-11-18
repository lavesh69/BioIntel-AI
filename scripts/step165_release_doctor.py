from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--root',default='.');a=p.parse_args();root=Path(a.root).resolve()
 checks=[]
 def add(name,passed,detail): checks.append({'check':name,'passed':bool(passed),'detail':detail})
 add('Version', (root/'VERSION').read_text().strip() in {'13.7.0','13.8.0'}, (root/'VERSION').read_text().strip())
 for path in ['STEP165_RELEASE.json','STEP165_PRIORITY_MODULE_UPGRADE_REPORT.md','pages/234_Priority_Three_Module_Excellence_Center.py','src/biointel/priority_v165/assurance.py']:
  add(path,(root/path).is_file(),'present' if (root/path).is_file() else 'missing')
 proc=subprocess.run([sys.executable,str(root/'scripts/step165_validate_priority.py'),'--root',str(root)],cwd=root,text=True,capture_output=True)
 add('Step 165 validation',proc.returncode==0,proc.stdout[-1000:] if proc.stdout else proc.stderr[-1000:])
 payload={'schema':'biointel.step165.release-doctor.v1','status':'passed' if all(x['passed'] for x in checks) else 'failed','checks':checks,'external_claims_not_inferred':True}
 (root/'reports/step165_release_doctor.json').write_text(json.dumps(payload,indent=2)+'\n')
 print(json.dumps(payload,indent=2));return 0 if payload['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
