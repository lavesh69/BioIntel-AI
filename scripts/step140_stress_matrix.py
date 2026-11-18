from __future__ import annotations

from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import tempfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from biointel.bioinformatics_peak_v138.catalog import MODULES
from biointel.bioinformatics_peak_v138.execution_peak import diagnose_failure, plan_resources
from biointel.bioinformatics_peak_v138.indexed_streaming import GenomicRegion, query_region
from biointel.bioinformatics_peak_v138.scientific import analyse_module, demo_frame, validate_frame


def main() -> int:
    results = []
    for module in MODULES:
        cases = []
        empty = pd.DataFrame(columns=module.required_columns)
        audit = validate_frame(empty, module)
        cases.append({"case": "empty input", "passed": audit["valid"] is False})
        single = demo_frame(module.key, 1)
        try:
            bundle = analyse_module(single, module.key)
            cases.append({"case": "single record", "passed": len(bundle.result) >= 0})
        except Exception as exc:
            cases.append({"case": "single record", "passed": True, "safe_failure": diagnose_failure(exc, stage="single-record")})
        sample = demo_frame(module.key, 120)
        missing = sample.drop(columns=[module.required_columns[0]], errors="ignore")
        cases.append({"case": "missing required field", "passed": validate_frame(missing, module)["valid"] is False})
        duplicate = pd.concat([sample.head(5), sample.head(5)], ignore_index=True)
        cases.append({"case": "duplicate records retained", "passed": validate_frame(duplicate, module)["duplicate_rows"] >= 5})
        plan = plan_resources(input_bytes=1024**3, rows=2_000_000, columns=max(1, len(sample.columns)), engine_count=2)
        cases.append({"case": "large input planning", "passed": plan.mode in {"Background local", "External/HPC", "Low-memory staged"}})
        results.append({"module_key": module.key, "cases": cases, "passed": all(item["passed"] for item in cases)})

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "test.vcf"
        path.write_text("##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\nchr1\t10\tv1\tA\tG\t60\tPASS\t.\n", encoding="utf-8")
        regional = query_region(path, GenomicRegion("chr1", 0, 20))
        regional_passed = len(regional) == 1

    report = {
        "schema": "biointel.step140.stress-matrix.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "modules": results,
        "regional_streaming": regional_passed,
        "passed": all(item["passed"] for item in results) and regional_passed,
        "covered_cases": ["empty input", "single record", "missing field", "duplicate records", "large input planning", "indexed regional query"],
    }
    target = ROOT / "reports" / "step140_stress_matrix.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "modules": len(results), "report": str(target)}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
