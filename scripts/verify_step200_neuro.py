from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REQUIRED = (
    "src/biointel/neuro_cns/safety.py",
    "src/biointel/neuro_cns/advanced.py",
    "src/biointel/neuro_cns/hardening.py",
    "src/biointel/neuro_cns/max_potential.py",
    "src/biointel/neuro_cns/ui.py",
    "pages/263_Neuro_CNS_Intelligence_Studio.py",
    "data/neuro_cns/step200_max_potential_feature_registry.json",
    "STEP200_NEURO_CNS_RELEASE.json",
    "STEP200_NEURO_TEST_STATUS.json",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--pytest", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: object) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    missing = [item for item in REQUIRED if not (root / item).is_file()]
    add("critical Step200 files", not missing, missing or "complete")

    missing_markers = [part for part in range(1, 6) if not (root / ".release_parts" / f"step200_part{part}.ok").is_file()]
    add("five Step200 part markers", not missing_markers, missing_markers or "complete")

    try:
        payload = json.loads((root / "data/neuro_cns/step200_max_potential_feature_registry.json").read_text(encoding="utf-8"))
        ok = payload.get("step") == 200 and payload.get("step200_control_systems") == 9 and payload.get("advanced_systems_total") == 18
        add("feature registry", ok, payload)
    except Exception as exc:
        add("feature registry", False, f"{type(exc).__name__}: {exc}")

    sys.path.insert(0, str(root / "src"))
    try:
        package = importlib.import_module("biointel.neuro_cns")
        max_module = importlib.import_module("biointel.neuro_cns.max_potential")
        hardening = importlib.import_module("biointel.neuro_cns.hardening")
        ok = package.__version__ == "200.0" and len(max_module.MAX_POTENTIAL_FEATURES) == 9 and callable(hardening.safe_execute)
        add("Python imports", ok, {"version": package.__version__, "max_features": len(max_module.MAX_POTENTIAL_FEATURES)})
    except Exception as exc:
        add("Python imports", False, f"{type(exc).__name__}: {exc}")

    if args.pytest:
        command = [
            sys.executable, "-m", "pytest", "-q",
            "tests/test_neuro_cns_studio.py",
            "tests/test_neuro_cns_page.py",
            "tests/test_neuro_cns_step198_hardening.py",
            "tests/test_neuro_cns_step199_advanced.py",
            "tests/test_neuro_cns_step200_max_potential.py",
        ]
        completed = subprocess.run(command, cwd=root, text=True, capture_output=True, encoding="utf-8", errors="replace")
        add("focused Neuro test suite", completed.returncode == 0, (completed.stdout + "\n" + completed.stderr)[-4000:])

    passed = all(bool(row["passed"]) for row in checks)
    report = {
        "schema": "biointel.neuro-cns.step200-verification.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "passed": passed,
        "checks": checks,
        "native_windows_execution": "requires execution on the target Windows machine",
    }
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
