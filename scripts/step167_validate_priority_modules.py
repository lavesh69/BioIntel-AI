from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.priority_v167 import ensure_step167_assets, priority_matrix
from biointel.priority_v167.assurance import TARGETS
from biointel.scientific_depth import native_input_template, run_native_workflow


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--root',default='.'); args=parser.parse_args(); root=Path(args.root).resolve()
    written=ensure_step167_assets(root); matrix=priority_matrix(root); rows=[]
    for key in sorted(TARGETS):
        result=run_native_workflow(key,native_input_template(key,demonstration=True),metadata={'project_root':str(root)})
        rows.append({'module_key':key,'status':result.status,'gate_present':'step167_priority_module_excellence_gate' in result.tables,'software_score':result.summary.get('step167_priority_module_software_score',0),'native_depth_score':result.summary.get('step167_native_research_depth_score',0)})
    passed=all(r['status'] in {'pass','review'} and r['gate_present'] and r['software_score']==10 and r['native_depth_score']==10 for r in rows)
    payload={'schema':'biointel.step167.validation.v1','status':'passed' if passed and len(written)==63 and len(matrix)==21 else 'failed','modules':rows,'assets':len(written)}
    (root/'reports'/'step167_validation.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8'); print(json.dumps(payload,indent=2)); return 0 if payload['status']=='passed' else 1
if __name__=='__main__': raise SystemExit(main())
