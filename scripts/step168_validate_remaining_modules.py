from __future__ import annotations
import argparse, json, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
if str(SRC) not in sys.path: sys.path.insert(0, str(SRC))
from biointel.priority_v168 import TARGETS, ALL_MODULES, ensure_step168_assets, ensure_step168_database, priority_matrix, universal_evidence_matrix
from biointel.scientific_depth import native_input_template, run_native_workflow
from biointel.scientific_depth.profiles import MODULE_PROFILES

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--root',default='.'); args=parser.parse_args(); root=Path(args.root).resolve()
    written=ensure_step168_assets(root)
    db=ensure_step168_database(root,[(k,v.title) for k,v in MODULE_PROFILES.items()])
    matrix=priority_matrix(root); universal=universal_evidence_matrix()
    rows=[]
    for key in TARGETS:
        result=run_native_workflow(key,native_input_template(key,demonstration=True),metadata={'project_root':str(root)})
        rows.append({'module_key':key,'status':result.status,'focused_gate':'step168_remaining_module_excellence_gate' in result.tables,'universal_gate':'step168_universal_external_evidence_gate' in result.tables,'software_score':result.summary.get('step168_remaining_module_software_score',0),'native_depth_score':result.summary.get('step168_remaining_module_native_depth_score',0),'evidence_framework_score':result.summary.get('step168_external_evidence_operations_framework_score',0)})
    universal_rows=[]
    for key in ALL_MODULES:
        result=run_native_workflow(key,native_input_template(key,demonstration=True),metadata={'project_root':str(root)})
        universal_rows.append({'module_key':key,'status':result.status,'universal_gate':'step168_universal_external_evidence_gate' in result.tables,'evidence_framework_score':result.summary.get('step168_external_evidence_operations_framework_score',0)})
    with sqlite3.connect(db) as conn:
        integrity=conn.execute('PRAGMA integrity_check').fetchone()[0]
        fk=conn.execute('PRAGMA foreign_key_check').fetchall()
        module_count=conn.execute('SELECT COUNT(*) FROM modules').fetchone()[0]
    passed=(len(written)==620 and len(matrix)==35 and len(universal)==80 and all(r['status'] in {'pass','review'} and r['focused_gate'] and r['universal_gate'] and r['software_score']==10 and r['native_depth_score']==10 and r['evidence_framework_score']==10 for r in rows) and all(r['status'] in {'pass','review'} and r['universal_gate'] and r['evidence_framework_score']==10 for r in universal_rows) and integrity=='ok' and not fk and module_count==80)
    payload={'schema':'biointel.step168.validation.v1','status':'passed' if passed else 'failed','focused_modules':rows,'universal_modules':universal_rows,'json_assets':len(written),'database_integrity':integrity,'database_fk_violations':len(fk),'database_modules':module_count}
    (root/'reports'/'step168_validation.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':payload['status'],'focused_modules':len(rows),'universal_modules':len(universal_rows),'assets':len(written),'database_integrity':integrity},indent=2)); return 0 if passed else 1
if __name__=='__main__': raise SystemExit(main())
