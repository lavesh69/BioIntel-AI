from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.nextgen.catalog import NEXTGEN_MODULES, PLATFORM_MODULES, SCIENTIFIC_MODULES  # noqa: E402
from biointel.nextgen.scientific import analyse, demo_frame, normalise  # noqa: E402
from biointel.ui.navigation import PAGE_BY_KEY  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_catalog() -> dict[str, object]:
    missing: list[str] = []
    for module in NEXTGEN_MODULES:
        page = PAGE_BY_KEY.get(module.key)
        if page is None or not (ROOT / page.path).is_file():
            missing.append(module.key)
    hub = PAGE_BY_KEY.get("step104_expansion_hub")
    if hub is None or not (ROOT / hub.path).is_file():
        missing.append("step104_expansion_hub")
    return {
        "passed": not missing,
        "scientific_modules": len(SCIENTIFIC_MODULES),
        "platform_modules": len(PLATFORM_MODULES),
        "total_features": len(NEXTGEN_MODULES),
        "missing_pages": missing,
    }


def verify_scientific_engines() -> dict[str, object]:
    failures: list[dict[str, str]] = []
    passed: list[str] = []
    for module in SCIENTIFIC_MODULES:
        try:
            data = normalise(demo_frame(module, 120), module)
            result, summary, _secondary, _extras = analyse(data, module, 0.7)
            if data.empty or result.empty or summary.get("schema") != "biointel.nextgen.scientific.v1":
                raise AssertionError("Empty or invalid scientific result")
            passed.append(module.key)
        except Exception as exc:  # pragma: no cover - verification report path
            failures.append({"module": module.key, "error": f"{type(exc).__name__}: {exc}"})
    return {"passed": not failures, "passed_count": len(passed), "total": len(SCIENTIFIC_MODULES), "failures": failures}


def verify_streamlit_pages(timeout: int) -> dict[str, object]:
    from streamlit.testing.v1 import AppTest

    pages = [PAGE_BY_KEY[module.key].path for module in NEXTGEN_MODULES]
    pages.append(PAGE_BY_KEY["step104_expansion_hub"].path)
    failures: list[dict[str, object]] = []
    passed: list[str] = []
    for relative in pages:
        page = ROOT / relative
        started = time.perf_counter()
        try:
            app = AppTest.from_file(str(page), default_timeout=timeout).run(timeout=timeout)
            exception_messages = [str(item.value) for item in app.exception]
            if exception_messages:
                raise AssertionError(" | ".join(exception_messages))
            passed.append(relative)
        except Exception as exc:  # pragma: no cover - verification report path
            failures.append({
                "page": relative,
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            })
    return {"passed": not failures, "passed_count": len(passed), "total": len(pages), "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the BioIntel AI Step 104 expansion")
    parser.add_argument("--skip-ui", action="store_true", help="Skip Streamlit AppTest page checks")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--output", default="reports/step104_verification.json")
    args = parser.parse_args()

    report: dict[str, object] = {
        "schema": "biointel.step104.verification.v1",
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "catalog": verify_catalog(),
        "scientific_engines": verify_scientific_engines(),
    }
    if not args.skip_ui:
        report["streamlit_pages"] = verify_streamlit_pages(args.timeout)
    key_files = [
        ROOT / "STEP104_RELEASE.json",
        ROOT / "STEP104_OPTIMIZED_EXPANSION_REPORT.md",
        ROOT / "src/biointel/nextgen/scientific.py",
        ROOT / "src/biointel/nextgen/services.py",
        ROOT / "src/biointel/nextgen/renderer.py",
    ]
    report["key_file_hashes"] = {str(path.relative_to(ROOT)): sha256(path) for path in key_files if path.is_file()}
    checks = [value.get("passed", False) for value in report.values() if isinstance(value, dict) and "passed" in value]
    report["passed"] = all(checks)

    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
