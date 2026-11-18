from __future__ import annotations

import io
import json
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.neuro_cns import PRODUCTION_FEATURES, __version__
from biointel.neuro_cns.catalog import MODULES
from biointel.neuro_cns.demo_showcase import run_complete_demo_showcase
from biointel.neuro_cns.production import (
    controlled_release_status,
    crash_diagnostics_bundle,
    demo_pack_zip,
    official_resource_plan,
    specialist_engine_installation_plan,
    verify_demo_pack,
)
from biointel.neuro_cns.reporting import bundle_pdf


EXPECTED_MODULE_KEYS = frozenset(module.key for module in MODULES)
EXPECTED_MODULE_NUMBERS = [module.number for module in MODULES]


def is_step202_or_later(version: str) -> bool:
    try:
        return int(version.split(".", 1)[0]) >= 202
    except (AttributeError, ValueError):
        return False


def main() -> int:
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: object) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    add("Step202+ Neuro/CNS version", is_step202_or_later(__version__), __version__)
    add("10 production systems", len(PRODUCTION_FEATURES) == 10, len(PRODUCTION_FEATURES))

    demo_status = verify_demo_pack(ROOT)
    add("demo pack integrity", bool(demo_status["passed"]), {"files": demo_status.get("dataset_count"), "errors": demo_status.get("errors")})

    results = run_complete_demo_showcase()
    actual_module_keys = frozenset(results)
    missing_module_keys = sorted(EXPECTED_MODULE_KEYS - actual_module_keys)
    unexpected_module_keys = sorted(actual_module_keys - EXPECTED_MODULE_KEYS)
    add(
        f"{len(EXPECTED_MODULE_KEYS)}-module demo execution",
        len(results) == len(EXPECTED_MODULE_KEYS),
        {"expected": len(EXPECTED_MODULE_KEYS), "received": len(results)},
    )
    add(
        "demo module keys match canonical catalog",
        actual_module_keys == EXPECTED_MODULE_KEYS,
        {
            "missing": missing_module_keys,
            "unexpected": unexpected_module_keys,
        },
    )

    pdf = bundle_pdf(results, project_name="Step202 runtime self-test")
    add("PDF report", pdf.startswith(b"%PDF") and len(pdf) > 10_000, len(pdf))

    demo_zip = demo_pack_zip(ROOT)
    try:
        with zipfile.ZipFile(io.BytesIO(demo_zip)) as archive:
            names = archive.namelist()
            zip_ok = any(name.endswith("manifest.json") for name in names) and len(names) >= 20
    except Exception as exc:
        zip_ok = False
        names = [str(exc)]
    add("demo ZIP", zip_ok, len(names))

    plan = official_resource_plan()
    covered_module_numbers = plan.get("covered_modules", [])
    add(
        f"resource plan covers {len(EXPECTED_MODULE_NUMBERS)} catalog modules",
        bool(plan["all_modules_covered"])
        and covered_module_numbers == EXPECTED_MODULE_NUMBERS,
        {
            "expected": EXPECTED_MODULE_NUMBERS,
            "received": covered_module_numbers,
        },
    )

    engine_plan = specialist_engine_installation_plan(run_version_checks=False)
    add("engine plan generated", len(engine_plan["plan"]) >= 10, len(engine_plan["plan"]))

    release = controlled_release_status(results=results, test_failures=0, native_windows_qualified=False)
    add("release gate fail-closed", not release["controlled_release_eligible"], release["release_tier"])

    diagnostics = crash_diagnostics_bundle(ROOT, error_message="runtime self-test")
    add("diagnostic ZIP", diagnostics.startswith(b"PK"), len(diagnostics))

    passed = all(bool(row["passed"]) for row in checks)
    report = {
        "schema": "biointel.step202.runtime-self-test.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "passed": passed,
        "checks": checks,
    }
    output = ROOT / "reports" / "step202-runtime-self-test.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
