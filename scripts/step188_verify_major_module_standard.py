from __future__ import annotations
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'src'
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))
from biointel.major_module_standard_v188 import COMPULSORY_DIMENSIONS, STANDARD_TABS, TARGET_MODULES, step188_rating_matrix, validate_module

def main()->int:
    frame=step188_rating_matrix(ROOT)
    bad={key:list(validate_module(ROOT,key).blockers) for key in TARGET_MODULES if not validate_module(ROOT,key).qualified_10_of_10}
    result={
        'schema':'biointel.step188.verification.v1',
        'status':'passed' if not bad and len(frame)==80 and frame.qualified_10_of_10.all() else 'failed',
        'modules':len(frame),
        'qualified':int(frame.qualified_10_of_10.sum()),
        'dimensions_passed':int(frame.dimensions_passed.sum()),
        'dimensions_total':int(frame.dimensions_total.sum()),
        'tabs_per_module':len(STANDARD_TABS),
        'compulsory_dimensions_per_module':len(COMPULSORY_DIMENSIONS),
        'blockers':bad,
        'controlled_release_eligible':False,
    }
    (ROOT/'STEP188_VERIFICATION.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
