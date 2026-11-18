from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]
theme=sys.argv[1]
result={'theme':theme,'passed':False,'exceptions':[]}
try:
    app=AppTest.from_file(str(ROOT/'pages/24_Appearance_Studio.py'), default_timeout=75)
    app.session_state['ui_palette']=theme
    app.session_state['ui_reduce_effects']=True
    app.session_state['ui_motion_mode']='Balanced'
    app.session_state['ui_preferences_loaded']=True
    app.run(timeout=75)
    result['exceptions']=[str(x.value) for x in app.exception]
    result['passed']=not result['exceptions']
except Exception as exc:
    result['exceptions']=[f'{type(exc).__name__}: {exc}']
print(json.dumps(result),flush=True)
os._exit(0 if result['passed'] else 1)
