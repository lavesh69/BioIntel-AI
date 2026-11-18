from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.external_demo_v182 import build_demo_evidence

result = build_demo_evidence(ROOT)
print(json.dumps(result, indent=2))
