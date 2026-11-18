from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PAGES = [
    "pages/90_Clinical_Pharma_Validation_Center.py",
    "pages/14_External_Validation_Drift.py",
    "pages/47_Benchmark_Leakage_Lab.py",
    "pages/69_Scientific_Data_Readiness.py",
    "pages/101_Biomedical_Knowledge_Graph_Copilot.py",
    "pages/164_Visual_Interaction_Accessibility_Workspace.py",
]
WORKER = r'''
import json,sys,traceback
from streamlit.testing.v1 import AppTest
page=sys.argv[1]
out={"page":page,"passed":False,"exceptions":[],"visual_layout":False,"accessibility":False,"visual_options":0}
try:
    app=AppTest.from_file(page,default_timeout=150).run(timeout=150)
    out["exceptions"]=[str(x.value) for x in app.exception]
    for widget in app.radio:
        if getattr(widget,"label","")=="Visual layout":
            out["visual_layout"]=set(widget.options)=={"Single visual","Compare two visuals"}
    for widget in app.selectbox:
        label=getattr(widget,"label","")
        if label=="Visual view": out["visual_options"]=len(widget.options or [])
        if label=="Visual accessibility": out["accessibility"]=len(widget.options or [])==4
    if page.endswith("164_Visual_Interaction_Accessibility_Workspace.py"):
        out["passed"]=not out["exceptions"] and len(app.tabs)==4
    else:
        out["passed"]=not out["exceptions"] and out["visual_layout"] and out["accessibility"] and out["visual_options"]==5
except Exception as exc:
    out["exceptions"]=[repr(exc),traceback.format_exc()]
print(json.dumps(out))
'''


def main() -> int:
    tests = [
        "tests/test_step107_scientific_visual_excellence.py",
        "tests/test_step108_decision_visuals.py",
        "tests/test_step109_visual_interaction.py",
        "tests/visual/test_semantic_visual_regression.py::test_semantic_manifest_integrity",
    ]
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *tests],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=420,
        check=False,
    )
    pages: list[dict[str, object]] = []
    for relative in RUNTIME_PAGES:
        worker = subprocess.run(
            [sys.executable, "-c", WORKER, str(ROOT / relative)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=210,
            check=False,
        )
        payload = None
        for line in reversed(worker.stdout.splitlines()):
            if line.strip().startswith("{"):
                payload = json.loads(line)
                break
        if payload is None:
            payload = {
                "page": relative,
                "passed": False,
                "exceptions": [worker.stderr or worker.stdout or "Worker produced no JSON"],
            }
        pages.append(payload)
        print(json.dumps(payload))
    report = {
        "schema": "biointel.step109.visual-interaction-verification.v1",
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "pytest_returncode": completed.returncode,
        "pytest_stdout": completed.stdout,
        "pytest_stderr": completed.stderr,
        "runtime_pages_total": len(pages),
        "runtime_pages_passed": sum(bool(row.get("passed")) for row in pages),
        "runtime_pages": pages,
    }
    output = ROOT / "reports/step109_visual_interaction_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(completed.stdout)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr)
    print(f"Report: {output}")
    return 0 if completed.returncode == 0 and report["runtime_pages_passed"] == len(pages) else 1


if __name__ == "__main__":
    raise SystemExit(main())
