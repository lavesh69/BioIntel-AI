from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    "pages/90_Clinical_Pharma_Validation_Center.py",
    "pages/14_External_Validation_Drift.py",
    "pages/47_Benchmark_Leakage_Lab.py",
    "pages/74_DTI_Validation_Evidence_Center.py",
    "pages/69_Scientific_Data_Readiness.py",
    "pages/7_Model_Evaluation.py",
    "pages/11_Experiment_Registry.py",
    "pages/21_Dataset_Registry_Lineage.py",
    "pages/101_Biomedical_Knowledge_Graph_Copilot.py",
    "pages/31_Evidence_Package_Studio.py",
    "pages/30_Governance_Hub.py",
    "pages/45_Scientific_Release_Gate.py",
    "pages/85_Provider_Integration_Center.py",
    "pages/106_Reference_Database_Manager.py",
]
WORKER = r'''
import json,sys,traceback
from streamlit.testing.v1 import AppTest
page=sys.argv[1]
out={"page":page,"passed":False,"exceptions":[],"selector_options":0}
try:
    app=AppTest.from_file(page,default_timeout=180).run(timeout=180)
    out["exceptions"]=[str(x.value) for x in app.exception]
    for widget in app.selectbox:
        if getattr(widget,"label","")=="Visual view":
            out["selector_options"]=len(getattr(widget,"options",[]) or [])
    out["passed"]=not out["exceptions"] and out["selector_options"]==5
except Exception as exc:
    out["exceptions"]=[repr(exc),traceback.format_exc()]
print(json.dumps(out))
'''


def main() -> int:
    rows = []
    for relative in PAGES:
        completed = subprocess.run(
            [sys.executable, "-c", WORKER, str(ROOT / relative)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        payload = None
        for line in reversed(completed.stdout.splitlines()):
            if line.strip().startswith("{"):
                payload = json.loads(line)
                break
        if payload is None:
            payload = {
                "page": relative,
                "passed": False,
                "exceptions": [completed.stderr or completed.stdout or "Worker produced no JSON"],
                "selector_options": 0,
            }
        rows.append(payload)
        print(json.dumps(payload))
    report = {
        "schema": "biointel.step108.page-runtime.v1",
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "pages": rows,
        "pages_total": len(rows),
        "pages_passed": sum(bool(row.get("passed")) for row in rows),
        "visual_options_verified": sum(int(row.get("selector_options", 0)) for row in rows),
    }
    output = ROOT / "reports/step108_page_runtime.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report: {output}")
    return 0 if report["pages_passed"] == report["pages_total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
