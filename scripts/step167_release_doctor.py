from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--root',default='.'); args=parser.parse_args(); root=Path(args.root).resolve()
    proc=subprocess.run([sys.executable,str(root/'scripts/step167_validate_priority_modules.py'),'--root',str(root)],cwd=root,text=True,capture_output=True)
    assets=len(list((root/'data/step167').glob('*/*.json')))
    checks=[{'check':'Step 167 validation','passed':proc.returncode==0,'detail':(proc.stdout or proc.stderr)[-4000:]},{'check':'Version marker','passed':(root/'VERSION').read_text().strip()=='13.9.0','detail':(root/'VERSION').read_text().strip()},{'check':'Priority assets','passed':assets==63,'detail':f'{assets} assets'}]
    payload={'schema':'biointel.step167.release-doctor.v1','status':'passed' if all(x['passed'] for x in checks) else 'failed','checks':checks,'external_claims_not_inferred':True}
    (root/'reports'/'step167_release_doctor.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8'); print(json.dumps(payload,indent=2)); return 0 if payload['status']=='passed' else 1
if __name__=='__main__': raise SystemExit(main())
