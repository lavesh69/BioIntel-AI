from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from biointel.engine_platform_v196 import EngineManager


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--user-data", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    user_data = args.user_data or (Path(os.environ["BIOINTEL_USER_DATA_DIR"]) if os.environ.get("BIOINTEL_USER_DATA_DIR") else args.root / "UserData")
    manager = EngineManager(project=args.root, user_data=user_data)
    report = manager.health_report()
    report["bootstrap"] = {
        "state_database_initialized": True,
        "external_downloads_performed": False,
        "external_engines_installed": False,
        "policy": "fail-closed until qualified pack or release manifest is supplied",
    }
    output = args.output or user_data / "reports" / "step213-engine-platform-bootstrap.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["registered_engines"] == 76 and report["advanced_adapters"] == 12 and report["production_services"] == 6 and report["database"]["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
