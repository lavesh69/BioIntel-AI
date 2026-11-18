from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.nextgen.biomedical_expansion import NEW_BIOMEDICAL_KEYS
from biointel.nextgen.catalog import MODULE_BY_KEY
from biointel.nextgen.scientific import analyse, demo_frame, normalise
from biointel.ui.nextgen_specialist_canvases import _PROFILES
from biointel.ui.scientific_visuals import build_scientific_visuals

LOCKED_HASHES = {
    "pages/6_DTI_Predictor.py": "84b3ecec1356b7239a057459210af4cd130c57c08dd9449b7239d1fe5954e0cc",
    "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
    "pages/109_Lab_Instrument_Import_Center.py": "22b5aba5bfea37bb1ef330ed7cca3773467463f883189602d96a0151311c8f70",
    "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "eadaef1a283a5fa11ce6b243aa561508ba9ceba9f6fdcc207f4853ccf7d86905",
    "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def main() -> int:
    checks: list[dict[str, Any]] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    checks.append(check("version", version == "13.2.0", f"VERSION={version}"))

    release = json.loads((ROOT / "STEP129_RELEASE.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / "config/step129_nextgen_depth_visuals.json").read_text(encoding="utf-8"))
    checks.append(check("release configuration", release.get("version") == "13.2.0" and config.get("release") == "13.2.0", "Step 129 release/config aligned"))
    checks.append(check("module count", len(NEW_BIOMEDICAL_KEYS) == 15, f"modules={len(NEW_BIOMEDICAL_KEYS)}"))
    checks.append(check("specialist canvases", set(_PROFILES) == set(NEW_BIOMEDICAL_KEYS), f"canvases={len(_PROFILES)}"))

    module_results: dict[str, Any] = {}
    all_analyses = True
    all_visuals = True
    all_extras = True
    for key in sorted(NEW_BIOMEDICAL_KEYS):
        module = MODULE_BY_KEY[key]
        data = normalise(demo_frame(module, 120), module)
        result, summary, secondary, extras = analyse(data, module, 0.7)
        visuals = build_scientific_visuals(key, data=data, result=result, secondary=secondary, extras=extras)
        module_results[key] = {
            "input_rows": len(data),
            "result_rows": len(result),
            "extra_tables": sorted(extras),
            "visuals": [visual.title for visual in visuals],
        }
        all_analyses &= bool(not data.empty and not result.empty and summary.get("module") == key)
        all_visuals &= len(visuals) == 5 and len({visual.title for visual in visuals}) == 5
        all_extras &= len(extras) >= 2
    checks.append(check("module analyses", all_analyses, "15/15 deterministic module analyses produced results"))
    checks.append(check("specialist visuals", all_visuals, "75/75 module-specific visuals available"))
    checks.append(check("advanced tables", all_extras, "Every module produced at least two advanced tables"))

    locked_ok = True
    locked_actual: dict[str, str] = {}
    for rel, expected in LOCKED_HASHES.items():
        actual = sha(ROOT / rel)
        locked_actual[rel] = actual
        locked_ok &= actual == expected
    checks.append(check("locked modules", locked_ok, "5/5 protected pages remain byte-identical to Step 128"))

    required_files = [
        ROOT / "src/biointel/ui/nextgen_specialist_canvases.py",
        ROOT / "tests/test_step129_nextgen_depth_visuals_stability.py",
        ROOT / "STEP129_NEXTGEN_FEATURE_DEPTH_VISUALS_STABILITY_REPORT.md",
        ROOT / "VERIFY_STEP129_WINDOWS.bat",
    ]
    checks.append(check("release files", all(path.exists() and path.stat().st_size > 0 for path in required_files), f"files={len(required_files)}"))

    payload = {
        "schema": "biointel.step129.verification.v1",
        "version": version,
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "module_results": module_results,
        "locked_hashes": locked_actual,
    }
    output = ROOT / "reports/step129_nextgen_depth_visuals_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    for item in checks:
        print(("PASS" if item["passed"] else "FAIL"), item["name"], "-", item["detail"])
    print("report:", output)
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
