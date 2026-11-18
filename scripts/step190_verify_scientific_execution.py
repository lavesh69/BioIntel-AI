from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from biointel.scientific_execution_v190 import EXECUTION_DIMENSIONS, TARGET_MODULES, rating_matrix, validate_module
from biointel.scientific_execution_v190.generator import connect, shared_db

def main()->int:
    frame=rating_matrix(ROOT)
    bad={k:list(validate_module(ROOT,k).blockers) for k in TARGET_MODULES if not validate_module(ROOT,k).qualified_10_of_10}
    with connect(shared_db(ROOT)) as conn:
        counts={name:conn.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] for name in ('module_runs','engine_matrix','benchmark_metrics','standard_artifacts')}
        integrity=conn.execute('PRAGMA integrity_check').fetchone()[0]
    result={'schema':'biointel.step190.verification.v1','status':'passed' if not bad and len(frame)==80 and integrity=='ok' else 'failed',
            'modules':len(frame),'qualified':int(frame.qualified_10_of_10.sum()),'dimensions_per_module':len(EXECUTION_DIMENSIONS),
            'dimensions_passed':int(frame.dimensions_passed.sum()),'dimensions_total':int(frame.dimensions_total.sum()),
            'database_counts':counts,'database_integrity':integrity,'blockers':bad,'controlled_release_eligible':False}
    (ROOT/'STEP190_VERIFICATION.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2));return 0 if result['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
