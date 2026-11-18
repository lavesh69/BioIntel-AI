from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from biointel.database.integrity_guards import install_integrity_guards

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    result = {key: asdict(value) for key, value in install_integrity_guards(ROOT).items()}
    output = ROOT / "reports" / "generated" / "step33_integrity_guards.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
