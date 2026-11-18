"""Run canonical and legacy Education surfaces through Streamlit AppTest."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    "pages/141_Shiro_AI_Studio.py",
    "pages/153_BioIntel_Academy_Lecture_Studio.py",
    "pages/155_Education_Intelligence_Hub.py",
    "pages/339_BioIntel_Education_Home.py",
    "pages/340_BioIntel_Classroom.py",
    "pages/342_BioIntel_Academy_and_Lecture_Studio.py",
    "pages/343_BioIntel_Education_Universe.py",
    "pages/344_BioIntel_Examination_Command_Center.py",
    "pages/345_BioIntel_Education_Intelligence_Hub.py",
    "pages/354_BioIntel_Final_Runtime_Evidence_and_Scientific_Workbench_Center.py",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    results = []
    for relative in PAGES:
        page = root / relative
        try:
            app = AppTest.from_file(str(page), default_timeout=args.timeout).run(timeout=args.timeout)
            exceptions = [item.message for item in app.exception]
        except Exception as exc:
            exceptions = [f"{type(exc).__name__}: {exc}"]
        results.append({"page": relative, "passed": not exceptions, "exceptions": exceptions})
    payload = {
        "schema": "biointel.education.streamlit-qualification.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "routes": len(results),
        "passed": sum(item["passed"] for item in results),
        "exceptions": sum(len(item["exceptions"]) for item in results),
        "results": results,
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] == payload["routes"] else 1


if __name__ == "__main__":
    raise SystemExit(main())