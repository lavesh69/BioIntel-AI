from __future__ import annotations
import argparse, json, os, subprocess, sys, tempfile
from pathlib import Path

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='.'); args=ap.parse_args()
    root=Path(args.root).resolve(); checks=[]
    def add(name,ok,detail): checks.append({'name':name,'passed':bool(ok),'detail':detail})
    pre=(root/'scripts/step202_preflight.py').read_text(encoding='utf-8-sig',errors='replace')
    ins=(root/'scripts/install_windows_step196.py').read_text(encoding='utf-8-sig',errors='replace')
    manifest=json.loads((root/'STEP196_SOURCE_MANIFEST_SHA256.json').read_text(encoding='utf-8-sig'))
    paths={str(x.get('path','')) for x in manifest.get('entries',[]) if isinstance(x,dict)}
    add('mutable report directory excluded',not any(path.startswith('reports/') for path in paths),{'tracked_report_entries':sum(path.startswith('reports/') for path in paths)})
    add('mutable preflight report excluded','reports/step203-preflight.json' not in paths and 'reports/step203-preflight-runtime.json' not in paths,{'tracked':sorted(p for p in paths if 'step203-preflight' in p)})
    add('preflight external report','LOCALAPPDATA' in pre and 'BioIntelAI' in pre and 'step203-preflight-runtime.json' in pre,'LocalAppData first with runtime fallback')
    validator_pos=ins.find('scripts/step196_validate_release.py'); preflight_pos=ins.find('scripts/step202_preflight.py',validator_pos)
    add('immutable validation first',validator_pos>=0 and preflight_pos>validator_pos,{'validator_pos':validator_pos,'preflight_pos':preflight_pos})
    add('installer explicit external output','str(USER_DATA / "reports" / "step203-preflight.json")' in ins,'explicit separated UserData report')
    passed=all(x['passed'] for x in checks)
    report={'schema':'biointel.step203.1.integrity-gate-hotfix.v1','passed':passed,'checks':checks}
    print(json.dumps(report,indent=2)); return 0 if passed else 1
if __name__=='__main__': raise SystemExit(main())
