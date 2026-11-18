from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--root',default='.'); args=parser.parse_args(); root=Path(args.root).resolve()
    proc=subprocess.run([sys.executable,str(root/'scripts/step168_validate_remaining_modules.py'),'--root',str(root)],cwd=root,text=True,capture_output=True)
    focused_assets=len(list((root/'data/step168/focused_modules').glob('*/*.json')))
    universal_assets=len(list((root/'data/step168/universal_evidence').glob('*/*.json')))
    page=root/'pages/237_Remaining_Modules_and_External_Evidence_10of10_Center.py'
    checks=[
        {'check':'Step 168 validation','passed':proc.returncode==0,'detail':(proc.stdout or proc.stderr)[-2000:]},
        {'check':'Version marker','passed':(root/'VERSION').read_text().strip()=='14.0.0','detail':(root/'VERSION').read_text().strip()},
        {'check':'Focused module assets','passed':focused_assets==140,'detail':f'{focused_assets}/140'},
        {'check':'Universal evidence assets','passed':universal_assets==480,'detail':f'{universal_assets}/480'},
        {'check':'Evidence registry','passed':(root/'data/databases/step168_external_evidence.sqlite').is_file(),'detail':'step168_external_evidence.sqlite'},
        {'check':'Command center page','passed':page.is_file(),'detail':str(page.relative_to(root))},
    ]
    payload={'schema':'biointel.step168.release-doctor.v1','status':'passed' if all(x['passed'] for x in checks) else 'failed','checks':checks,'external_claims_not_inferred':True,'fake_customer_clinical_wetlab_or_regulatory_history_created':False}
    (root/'reports'/'step168_release_doctor.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(payload,indent=2)); return 0 if payload['status']=='passed' else 1
if __name__=='__main__': raise SystemExit(main())
