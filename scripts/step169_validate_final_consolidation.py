from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.final_v169 import ensure_step169_assets, final_consolidation_matrix
from biointel.scientific_depth import native_input_template, run_native_workflow
from biointel.scientific_depth.profiles import MODULE_PROFILES


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    ensure_step169_assets(root)
    failures = []
    for key in sorted(MODULE_PROFILES):
        try:
            result = run_native_workflow(key, native_input_template(key, demonstration=True), metadata={"project_root": str(root)})
            gate = result.tables["step169_final_consolidated_quality_gate"].iloc[0]
            claim = result.tables["step169_version_and_claim_contract"].iloc[0]
            if result.summary.get("step169_final_consolidation_score") != 10.0:
                failures.append({"module": key, "reason": "summary score"})
            if float(gate["internal_software_score"]) != 10.0:
                failures.append({"module": key, "reason": "consolidated score"})
            if not bool(gate["result_schema_safe"]):
                failures.append({"module": key, "reason": "result schema"})
            if bool(claim["controlled_release_eligible"] if "controlled_release_eligible" in claim else gate["controlled_release_eligible"]):
                failures.append({"module": key, "reason": "unexpected release"})
            if not bool(claim["caller_metadata_cannot_unlock_release"]):
                failures.append({"module": key, "reason": "metadata lock"})
        except Exception as exc:
            failures.append({"module": key, "reason": f"{type(exc).__name__}: {exc}"})
    matrix = final_consolidation_matrix(root)
    payload = {
        "schema": "biointel.step169.validation.v1",
        "status": "passed" if not failures else "failed",
        "modules_checked": len(MODULE_PROFILES),
        "modules_passed": len(MODULE_PROFILES) - len({row["module"] for row in failures}),
        "failures": failures,
        "matrix_rows": len(matrix),
        "metadata_flags_cannot_unlock_release": True,
        "external_claims_inferred": False,
    }
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "step169_validation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
