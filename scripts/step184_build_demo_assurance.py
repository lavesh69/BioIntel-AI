from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.demo_assurance_v184 import build_step184

if __name__ == "__main__":
    result = build_step184(ROOT)
    print(result)
