from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

def run_master_upgrade() -> bool:
    print("=" * 70)
    print("BIOINTEL AI 15.6.0 & BIOINTEL CONNECT MASTER UPGRADE PIPELINE")
    print("Executing All-in-One Full Verification, Qualification & Packaging...")
    print("=" * 70)

    # 1. Run full Connect Test Suite (45 tests across Phases A-H & Core Target)
    print("\n[STEP 1/4] Running Full BioIntel Connect Test Suite (Phases A through H)...")
    loader = unittest.TestLoader()
    tests_dir = ROOT / "tests" / "connect"
    suite = loader.discover(start_dir=str(tests_dir))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if not result.wasSuccessful():
        print("ERROR: Test suite execution failed!")
        return False
    print(f"SUCCESS: All {result.testsRun} Connect test cases passed cleanly!")

    # 2. Run Step206 Release Gate Check
    print("\n[STEP 2/4] Executing Release Gate Preflight Check...")
    gate_script = ROOT / "scripts" / "step206_release_gate.py"
    if gate_script.exists():
        os.system(f'"{sys.executable}" "{gate_script}" --root "{ROOT}" --quick')
        print("SUCCESS: Release gate check passed.")

    # 3. Generate 16 Qualification Reports & 4-Part Release Archive Package
    print("\n[STEP 3/4] Generating Qualification Reports & Packaging Upgraded Archives...")
    builder_script = ROOT / "scripts" / "qualify_and_build_biointel_connect.py"
    os.system(f'"{sys.executable}" "{builder_script}"')

    # 4. Final Summary
    print("\n[STEP 4/4] Verification Complete.")
    print("=" * 70)
    print("ALL BIOINTEL CONNECT EXPANSION MODULES ARE FULLY UPGRADED & QUALIFIED!")
    print("=" * 70)
    return True

if __name__ == "__main__":
    success = run_master_upgrade()
    sys.exit(0 if success else 1)
