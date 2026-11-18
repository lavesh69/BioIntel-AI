from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]; SRC=ROOT/"src"
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from biointel.operational_assurance_v185 import TARGET_MODULES,validate_step185_module
rows=[validate_step185_module(ROOT,k) for k in TARGET_MODULES]
result={"schema":"biointel.step185.verify.v1","modules":len(rows),"qualified_10_of_10":sum(r.qualified_10_of_10 for r in rows),"failures":{r.module_key:list(r.blockers) for r in rows if not r.qualified_10_of_10},"real_external_evidence":0,"controlled_release_eligible":0}
print(json.dumps(result,indent=2)); raise SystemExit(0 if not result["failures"] else 1)
