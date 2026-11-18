from __future__ import annotations

import argparse
import json
import os
import sys
sys.dont_write_bytecode = True
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
os.environ["PYTHONPATH"] = str(SRC) + os.pathsep + os.environ.get("PYTHONPATH", "")


def _entrypoints() -> list[Path]:
    return [ROOT / "app.py", *sorted((ROOT / "pages").glob("*.py"))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=35)
    args = parser.parse_args()

    from streamlit.testing.v1 import AppTest

    pages = _entrypoints()
    selected = pages[args.start : args.end + 1]
    rows: list[dict[str, object]] = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for offset, page in enumerate(selected, start=args.start):
        started = time.perf_counter()
        exceptions: list[str] = []
        ui_errors: list[str] = []
        try:
            app = AppTest.from_file(str(page), default_timeout=args.timeout)
            app.run(timeout=args.timeout)
            exceptions = [str(item.value) for item in app.exception]
            ui_errors = [str(item.value) for item in app.error]
        except BaseException as exc:  # process-isolated runtime boundary
            exceptions = [f"{type(exc).__name__}: {exc}"]
        row = {
            "index": offset,
            "page": page.relative_to(ROOT).as_posix(),
            "passed": not exceptions and not ui_errors,
            "exceptions": exceptions,
            "ui_errors": ui_errors,
            "seconds": round(time.perf_counter() - started, 3),
        }
        rows.append(row)
        args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return 0 if all(bool(row["passed"]) for row in rows) else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
