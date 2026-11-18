import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.database.migrations import optimize_existing_registries

def main():
    print("[BioIntel AI] Running Database Indexing & Search Latency Optimization...")
    results = optimize_existing_registries(ROOT)
    print(json.dumps(results, indent=2))
    print("[BioIntel AI] All search indexes optimized successfully!")

if __name__ == "__main__":
    main()
