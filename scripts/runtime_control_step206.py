from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from step206_contract import stable_launcher_path, user_data_directory

ROOT = Path(__file__).resolve().parents[1]


def _load_operations() -> tuple[object, object]:
    source = str(ROOT / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    from biointel.operations.runtime_control import inspect_local_runtime, stop_local_runtime

    return inspect_local_runtime, stop_local_runtime


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("status", "stop", "restart"))
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    inspect_local_runtime, stop_local_runtime = _load_operations()
    user_data = user_data_directory()

    if args.action == "status":
        result = inspect_local_runtime(root, user_data)
        print(json.dumps(result, indent=2))
        return 0

    result = stop_local_runtime(root, user_data)
    print(json.dumps(result, indent=2))
    if result.get("state") not in {"stopped", "not-running"}:
        return 1
    if args.action == "restart":
        launcher = stable_launcher_path()
        if not launcher.is_file():
            launcher = root / "RUN_BOTH_WINDOWS.bat"
        if not launcher.is_file():
            print("BioIntel launcher missing hai. INSTALL_WINDOWS.bat dobara run karein.")
            return 1
        if os.name == "nt":
            completed = subprocess.run(["cmd", "/c", "call", str(launcher)], check=False)
        else:
            completed = subprocess.run([str(root / ".venv" / "Scripts" / "python.exe"), str(root / "scripts" / "run_biointel_step206.py")], check=False)
        return int(completed.returncode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
