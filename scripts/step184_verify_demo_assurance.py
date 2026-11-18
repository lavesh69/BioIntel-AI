from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.demo_assurance_v184 import TARGET_MODULES, validate_step184_module

if __name__ == "__main__":
    failed = []
    for key in TARGET_MODULES:
        result = validate_step184_module(ROOT, key)
        if not result.qualified_10_of_10:
            failed.append((key, list(result.blockers)))
    print(f"STEP184_QUALIFIED={len(TARGET_MODULES)-len(failed)}/{len(TARGET_MODULES)}")
    if failed:
        for item in failed:
            print(item)
        raise SystemExit(1)
