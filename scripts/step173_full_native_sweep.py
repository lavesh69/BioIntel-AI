from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.scientific_depth import MODULE_PROFILES, native_input_template, run_native_workflow

rows = []
for module_key in MODULE_PROFILES:
    try:
        result = run_native_workflow(
            module_key,
            native_input_template(module_key, demonstration=True),
            metadata={"analysis_mode": "interactive", "project_root": str(ROOT)},
        )
        passed = result.status in {"pass", "review"} and "step173_final_readiness" in result.tables
        gate = result.tables.get("step173_final_readiness")
        practical = float(gate.iloc[0]["actual_practical_readiness_rating"]) if gate is not None and not gate.empty else None
        rows.append({"module_key": module_key, "passed": passed, "status": result.status, "tables": len(result.tables), "practical_rating": practical, "error": ""})
    except Exception as exc:
        rows.append({"module_key": module_key, "passed": False, "status": "error", "tables": 0, "practical_rating": None, "error": f"{type(exc).__name__}: {exc}"})
report = {
    "schema": "biointel.step173.full-native-sweep.v1",
    "version": "14.5.0",
    "status": "passed" if all(row["passed"] for row in rows) and len(rows) == 80 else "failed",
    "modules": len(rows),
    "passed": sum(row["passed"] for row in rows),
    "failed": sum(not row["passed"] for row in rows),
    "rows": rows,
}
out = ROOT / "reports" / "step173_full_native_sweep.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: report[key] for key in ("schema", "version", "status", "modules", "passed", "failed")}, indent=2))
raise SystemExit(0 if report["status"] == "passed" else 1)
