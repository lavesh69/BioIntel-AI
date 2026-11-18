from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from biointel.universal_platform_v189 import build_step189
if __name__ == "__main__":
    print(build_step189(ROOT))
