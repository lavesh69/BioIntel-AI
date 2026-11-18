from __future__ import annotations
import argparse
import json
from pathlib import Path
from streamlit.testing.v1 import AppTest

p=argparse.ArgumentParser(); p.add_argument('page'); p.add_argument('--timeout',type=float,default=30); a=p.parse_args()
page=Path(a.page).resolve()
app=AppTest.from_file(str(page))
app.run(timeout=a.timeout)
errors=[str(item.value) for item in app.exception]
payload={'page':str(page),'passed':not errors,'errors':errors}
print(json.dumps(payload))
raise SystemExit(0 if not errors else 1)
