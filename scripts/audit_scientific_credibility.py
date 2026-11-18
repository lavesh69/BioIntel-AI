from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.scientific.credibility import write_scientific_credibility_audit

if __name__ == "__main__":
    path = write_scientific_credibility_audit(ROOT)
    print(json.dumps({"report": str(path), "ok": True}, indent=2))
