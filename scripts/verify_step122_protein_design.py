from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

checks: list[dict[str, object]] = []

def add(name: str, passed: bool, detail: str) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def main() -> int:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    add("Version", version == "13.2.0", f"VERSION={version}")

    from biointel.step122.protein_design import BACKENDS, protein_design_preflight, stage_protein_design_input

    add("Protected backends", len(BACKENDS) == 5, ", ".join(BACKENDS))
    page = (ROOT / "pages/96_AI_Protein_Design_Lab.py").read_text(encoding="utf-8")
    add("Page integration", "render_protein_design_execution_upgrade" in page, "Step 122 panel connected")
    add("No shell execution", "shell=True" not in (ROOT / "src/biointel/step122/protein_design.py").read_text(encoding="utf-8"), "argument-vector execution only")

    with tempfile.TemporaryDirectory(prefix="biointel-step122-verify-") as temporary:
        workspace = Path(temporary) / "runs"
        staged = stage_protein_design_input(workspace=workspace, sequence="ACDEFGHIKLMNPQRSTVWY", run_name="verification")
        add("Immutable staging", Path(staged["input_path"]).is_file() and bool(staged["input_sha256"]), staged["run_id"])
        preflight = protein_design_preflight(workspace)
        add("Runtime preflight", len(preflight["backends"]) == 5, f"{len(preflight['backends'])}/5 backend rows")
        add("Evidence boundary", "does not validate" in preflight["boundary"].lower(), preflight["boundary"])

    templates = [
        ROOT / "data/templates/step122/proteinmpnn_request.json",
        ROOT / "data/templates/step122/rfdiffusion_request.json",
        ROOT / "data/templates/step122/colabfold_request.json",
    ]
    add("Request templates", all(path.is_file() for path in templates), f"{sum(path.is_file() for path in templates)}/3 present")
    add("Windows launchers", (ROOT / "VERIFY_STEP122_WINDOWS.bat").is_file() and (ROOT / "RUN_PROTEIN_DESIGN_PIPELINE_WINDOWS.bat").is_file(), "verification and headless launchers")

    report = {
        "schema": "biointel.step122.verification.v1",
        "release": version,
        "passed": sum(bool(item["passed"]) for item in checks),
        "total": len(checks),
        "checks": checks,
    }
    output = ROOT / "reports" / "step122_protein_design_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for item in checks:
        print(("PASS" if item["passed"] else "FAIL") + f" | {item['name']} | {item['detail']}")
    print(f"Summary: {report['passed']}/{report['total']} passed")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
