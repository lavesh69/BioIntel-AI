from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

PART_COUNT = 5
EXPECTED_STEP = 196
EXPECTED_VERSION = "15.5.0"


def main() -> int:
    parser = argparse.ArgumentParser(description="Dependency-free Step 196 pre-install contract check")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: object) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    required = [
        "app.py",
        "INSTALL_WINDOWS.bat",
        "RUN_BOTH_WINDOWS.bat",
        "requirements.lock",
        "scripts/bootstrap.py",
        "scripts/find_python311_windows.ps1",
        "scripts/install_windows_step196.py",
        "scripts/setup_scientific_runtime_windows.py",
        "scripts/step196_validate_release.py",
        "scripts/verify_dependency_lock.py",
        "scripts/verify_windows_wheelhouse.py",
        "src/biointel/proof_gates_v10/catalog.py",
        "src/biointel/proof_gates_v10/registry.py",
        "src/biointel/proof_gates_v10/functional.py",
        "src/biointel/proof_gates_v10/ui.py",
        "STEP196_RELEASE.json",
        "STEP196_SOURCE_MANIFEST_SHA256.json",
    ]
    missing = [item for item in required if not (root / item).is_file()]
    add("required installer files", not missing, missing or "complete")

    missing_markers = [
        part
        for part in range(1, PART_COUNT + 1)
        if not (root / ".release_parts" / f"step196_part{part}.ok").is_file()
    ]
    add("five release part markers", not missing_markers, missing_markers or "complete")

    try:
        version = (root / "VERSION").read_text(encoding="utf-8-sig").strip()
        with (root / "pyproject.toml").open("rb") as handle:
            project_version = str(tomllib.load(handle).get("project", {}).get("version", "")).strip()
        release = json.loads((root / "STEP196_RELEASE.json").read_text(encoding="utf-8-sig"))
        add(
            "version contract",
            version == project_version == str(release.get("version", "")).strip() == EXPECTED_VERSION
            and int(release.get("step", 0) or 0) == EXPECTED_STEP
            and int(release.get("part_count", 0) or 0) == PART_COUNT,
            {"VERSION": version, "pyproject": project_version, "release": release},
        )
    except Exception as exc:
        add("version contract", False, f"{type(exc).__name__}: {exc}")

    try:
        bat = (root / "INSTALL_WINDOWS.bat").read_text(encoding="utf-8-sig", errors="replace")
        helper = (root / "scripts/install_windows_step196.py").read_text(encoding="utf-8-sig", errors="replace")
        expected_markers = "for %%P in (1 2 3 4 5)"
        preflight_start = helper.index("def verify_before_change")
        preflight_end = helper.index("\ndef ", preflight_start + 4)
        preflight_body = helper[preflight_start:preflight_end]
        forbidden_preinstall = "step193_self_test.py" in preflight_body
        ok = all(
            token in bat
            for token in (expected_markers, "install_windows_step196.py", "find_python311_windows.ps1")
        ) and all(
            token in helper
            for token in (
                "step196_preinstall_contract.py",
                "InterprocessFileLock",
                "launch_optional_free_web_ai_setup",
                "launch_scientific_runtime_setup",
                "CORE_IMPORTS",
            )
        ) and not forbidden_preinstall
        add("dependency-order and lock contract", ok, "complete" if ok else "contract mismatch")
    except Exception as exc:
        add("dependency-order and lock contract", False, f"{type(exc).__name__}: {exc}")

    passed = all(bool(row["passed"]) for row in checks)
    payload = {
        "schema": "biointel.step196.preinstall-contract.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "stdlib_only": True,
        "passed": passed,
        "checks": checks,
    }
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
