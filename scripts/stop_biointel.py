from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.operations.runtime_control import stop_local_runtime


def main() -> int:
    parser = argparse.ArgumentParser(description="Stop only the current local BioIntel runtime.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    args = parser.parse_args()
    if args.delay_seconds > 0:
        time.sleep(min(15.0, args.delay_seconds))
    local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    user_data = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or local / "BioIntelAI" / "UserData")
    result = stop_local_runtime(Path(args.root), user_data)
    print(json.dumps(result, indent=2))
    return 0 if result.get("state") in {"not-running", "stop-requested"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
