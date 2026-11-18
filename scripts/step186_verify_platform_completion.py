from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'src'
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))
from biointel.platform_completion_v186 import TARGET_MODULES,step186_rating_matrix,step186_validation_matrix
if __name__=='__main__':
    r=step186_rating_matrix(ROOT);v=step186_validation_matrix(ROOT);result={'modules':len(r),'qualified':int(r.qualified_10_of_10.sum()),'average':round(float(r.after_platform_completion_rating.mean()),3),'blockers':int(v.blockers.map(bool).sum())};print(json.dumps(result,indent=2));raise SystemExit(0 if result['qualified']==len(TARGET_MODULES) and result['blockers']==0 else 1)
