from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument('--root',default='.');args=parser.parse_args();root=Path(args.root).resolve()
    proc=subprocess.run([sys.executable,str(root/'scripts/step166_validate_six_modules.py'),'--root',str(root)],cwd=root,text=True,capture_output=True)
    checks=[{'check':'Step 166 validation','passed':proc.returncode==0,'detail':proc.stdout[-4000:] if proc.stdout else proc.stderr[-4000:]},{'check':'Version marker','passed':(root/'VERSION').read_text().strip()=='13.8.0','detail':(root/'VERSION').read_text().strip()},{'check':'Six-module assets','passed':len(list((root/'data/step166').glob('*/*.json')))==18,'detail':f"{len(list((root/'data/step166').glob('*/*.json')))} assets"}]
    payload={'schema':'biointel.step166.release-doctor.v1','status':'passed' if all(x['passed'] for x in checks) else 'failed','checks':checks,'external_claims_not_inferred':True}
    (root/'reports/step166_release_doctor.json').write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps(payload,indent=2));return 0 if payload['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
