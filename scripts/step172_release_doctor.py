from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
checks=[]
for label,command in [
 ('step172_validation',[sys.executable,str(ROOT/'scripts'/'step172_validate_external_confirmation.py')]),
 ('step171_validation',[sys.executable,str(ROOT/'scripts'/'step171_validate_models.py'),'--quick']),
 ('step170_validation',[sys.executable,str(ROOT/'scripts'/'step170_validate_runtime_reference.py')]),
]:
 p=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=240,check=False)
 checks.append({'name':label,'passed':p.returncode==0,'return_code':p.returncode,'stdout':p.stdout[-2000:],'stderr':p.stderr[-2000:]})
report={'schema':'biointel.step172.release-doctor.v1','status':'passed' if all(x['passed'] for x in checks) else 'failed','version':'14.4.0','checks':checks,'fake_wetlab_clinical_expert_or_site_evidence_created':False,'boundary':'Software qualification can be 10/10; genuine external outcomes remain blocked until checksum-valid evidence is imported.'}
out=ROOT/'reports'/'step172_release_doctor.json'; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2)); raise SystemExit(0 if report['status']=='passed' else 1)
