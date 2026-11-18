from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from step206_contract import PRODUCT_VERSION, user_data_directory, utc_now


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = (
        Path(args.output).resolve()
        if args.output
        else user_data_directory() / "reports" / "step206-streamlit-startup-check.json"
    )
    source = str(root / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    os.environ.setdefault("PYTHONPATH", source)
    payload: dict[str, Any] = {
        "schema": "biointel.step206.streamlit-startup-check.v1",
        "generated_at": utc_now(),
        "root": str(root),
        "version": PRODUCT_VERSION,
        "passed": False,
        "exceptions": [],
    }
    try:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(root / "app.py"), default_timeout=180).run(timeout=180)
        exceptions = [str(item.value) for item in app.exception]
        payload["exceptions"] = exceptions
        payload["element_counts"] = {
            "titles": len(app.title),
            "headers": len(app.header),
            "markdown": len(app.markdown),
            "errors": len(app.error),
        }
        payload["passed"] = not exceptions
        if app.error:
            payload["visible_error_elements"] = [str(item.value) for item in app.error[:20]]
    except Exception as exc:
        payload["exceptions"] = [f"{type(exc).__name__}: {exc}"]
        payload["passed"] = False
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    print(json.dumps(payload, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
