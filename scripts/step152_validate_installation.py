from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a merged BioIntel AI Step 152 folder.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--allow-uninstalled", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    checks: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []

    def check(key: str, passed: bool, message: str = "") -> None:
        checks.append({"key": key, "passed": bool(passed), "message": message})
        if not passed:
            failures.append({"key": key, "message": message})

    base_validator = root / "scripts" / "step150_validate_installation.py"
    check("step150_validator_present", base_validator.is_file(), str(base_validator))
    if base_validator.is_file():
        command = [sys.executable, str(base_validator), "--root", str(root)]
        if args.allow_uninstalled:
            command.append("--allow-uninstalled")
        completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
        check("step150_base_validation", completed.returncode == 0, completed.stdout[-1500:] + completed.stderr[-750:])

    for part in range(1, 5):
        marker = root / ".release_parts" / f"step152_part{part}.ok"
        check(f"step152_part_{part}", marker.is_file(), marker.as_posix())

    critical_manifest = root / "release" / "step152_critical_hashes.json"
    check("critical_manifest_present", critical_manifest.is_file(), critical_manifest.as_posix())
    if critical_manifest.is_file():
        payload = json.loads(critical_manifest.read_text(encoding="utf-8"))
        for relative, expected in payload.get("files", {}).items():
            path = root / relative
            if not path.is_file():
                check(f"critical_file:{relative}", False, "missing")
                continue
            actual = sha256(path)
            check(f"critical_file:{relative}", actual == expected, f"expected={expected} actual={actual}")

    release_file = root / "STEP152_RELEASE.json"
    check("release_metadata", release_file.is_file(), release_file.as_posix())
    if release_file.is_file():
        release = json.loads(release_file.read_text(encoding="utf-8"))
        check("release_step", release.get("step") == 152, str(release.get("step")))
        check("regression_failures_zero", release.get("tests", {}).get("failed") == 0, str(release.get("tests")))
        check("native_workflows_complete", release.get("native_workflows") == 80, str(release.get("native_workflows")))

    source_checks = {
        "native_orchestrator": "src/biointel/scientific_depth/native_workflows.py",
        "native_omics": "src/biointel/scientific_depth/native_omics_workflows.py",
        "native_advanced": "src/biointel/scientific_depth/native_advanced_workflows.py",
        "native_tests": "tests/test_step152_native_scientific_core.py",
    }
    for key, relative in source_checks.items():
        path = root / relative
        check(key, path.is_file() and path.stat().st_size > 500, relative)

    report = {
        "schema": "biointel.step152.validation-report.v1",
        "root": str(root),
        "checks": checks,
        "failures": failures,
        "passed": not failures,
    }
    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "step152_installation_validation.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"REPORT_PATH={report_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
