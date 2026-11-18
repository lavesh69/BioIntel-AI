from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'src'
if str(SRC) not in sys.path:sys.path.insert(0,str(SRC))
from biointel.page_excellence_v187 import TARGET_PAGES,validate_step187_page
bad={f:validate_step187_page(ROOT,f).blockers for f in TARGET_PAGES if not validate_step187_page(ROOT,f).qualified_10_of_10}
print(json.dumps({"target_pages":len(TARGET_PAGES),"qualified":len(TARGET_PAGES)-len(bad),"blockers":bad},indent=2));raise SystemExit(1 if bad else 0)
