from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    relative = Path(sys.argv[1])
    page = ROOT / relative
    result = {"page": relative.as_posix(), "passed": False, "exceptions": []}
    try:
        app = AppTest.from_file(str(page), default_timeout=55)
        app.run(timeout=55)
        result["exceptions"] = [str(item.value) for item in app.exception]
        result["errors"] = [str(item.value) for item in app.error]
        result["passed"] = not result["exceptions"]
    except Exception as exc:  # noqa: BLE001
        result["exceptions"] = [f"{type(exc).__name__}: {exc}"]
    print(json.dumps(result, ensure_ascii=False), flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    raise SystemExit(main())
