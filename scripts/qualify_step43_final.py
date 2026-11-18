from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.assurance import build_final_assurance
from biointel.engineering.repository_audit import repository_manifest


def _run(name: str, command: list[str], *, timeout: int = 600) -> dict[str, object]:
    with (
        tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as stdout_file,
        tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as stderr_file,
    ):
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                stdout=stdout_file,
                stderr=stderr_file,
                check=False,
                timeout=timeout,
                env={**dict(__import__("os").environ), "PYTHONPATH": str(SRC)},
            )
            stdout_file.flush()
            stderr_file.flush()
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read()
            stderr = stderr_file.read()
            output = stdout + "\n" + stderr
            passed_match = re.findall(r"(\d+) passed", output)
            skipped_match = re.findall(r"(\d+) skipped", output)
            return {
                "name": name,
                "command": command,
                "returncode": completed.returncode,
                "passed": completed.returncode == 0,
                "test_count": sum(int(value) for value in passed_match),
                "skipped_count": sum(int(value) for value in skipped_match),
                "stdout_tail": stdout[-4000:],
                "stderr_tail": stderr[-4000:],
            }
        except subprocess.TimeoutExpired:
            stdout_file.flush()
            stderr_file.flush()
            stdout_file.seek(0)
            stderr_file.seek(0)
            return {
                "name": name,
                "command": command,
                "returncode": 124,
                "passed": False,
                "test_count": 0,
                "skipped_count": 0,
                "stdout_tail": stdout_file.read()[-4000:],
                "stderr_tail": (stderr_file.read() + "\nqualification command timed out")[-4000:],
            }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run final BioIntel AI release qualification")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    commands: list[tuple[str, list[str], int]] = [
        (
            "compile",
            [
                sys.executable,
                "-m",
                "compileall",
                "-q",
                "app.py",
                "pages",
                "src",
                "scripts",
                "tests",
            ],
            300,
        ),
        ("developer_doctor", [sys.executable, "scripts/dev_doctor.py"], 120),
    ]
    if not args.skip_tests:
        commands.extend(
            [
                (
                    "production_engineering_regression",
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "tests/test_step33_production_platform.py",
                        "tests/test_step35_quality_hardening.py",
                        "tests/test_step36_maturity_frameworks.py",
                        "tests/test_step36_target_quality.py",
                        "tests/test_step37_engineering_excellence.py",
                    ],
                    300,
                ),
                (
                    "scientific_regression",
                    [sys.executable, "-m", "pytest", "-q", "tests/scientific"],
                    300,
                ),
                (
                    "operations_api_drill",
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "tests/operations/test_step41_api_and_drill.py",
                    ],
                    180,
                ),
                (
                    "operations_realworld",
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "tests/operations/test_step41_realworld_operations.py",
                    ],
                    180,
                ),
                (
                    "operations_verifiable_evidence",
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "tests/operations/test_step42_maximum_verifiable_evidence.py",
                    ],
                    180,
                ),
                (
                    "api_integration",
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "tests/integration/test_api_contracts.py",
                    ],
                    180,
                ),
                (
                    "container_integration",
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "tests/integration/test_container_contract.py",
                    ],
                    120,
                ),
                (
                    "storage_integration",
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "tests/integration/test_storage_contracts.py",
                    ],
                    120,
                ),
                (
                    "final_and_visual_integrity",
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "tests/test_step43_final_assurance.py",
                        "tests/visual/test_semantic_visual_regression.py",
                    ],
                    300,
                ),
            ]
        )

    executions = []
    for name, command, timeout in commands:
        print(f"[qualification] start {name}", flush=True)
        result = _run(name, command, timeout=timeout)
        executions.append(result)
        print(f"[qualification] done {name}: {'PASS' if result['passed'] else 'FAIL'}", flush=True)
    assurance = build_final_assurance(ROOT)
    output = ROOT / "reports" / "step43_qualification.json"
    payload = {
        "schema": "biointel.step43.qualification.v1",
        "version": assurance["version"],
        "passed": all(item["passed"] for item in executions)
        and assurance["implementation_score"] >= 9.5
        and assurance["database_health"]["healthy_count"]
        == assurance["database_health"]["database_count"],
        "test_count": sum(int(item["test_count"]) for item in executions),
        "skipped_count": sum(int(item["skipped_count"]) for item in executions),
        "assurance": assurance,
        "executions": executions,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")

    manifest = repository_manifest(ROOT)
    manifest_path = ROOT / "reports" / "step43_repository_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    print(
        json.dumps(
            {
                "passed": payload["passed"],
                "output": str(output),
                "manifest": str(manifest_path),
                "implementation_score": assurance["implementation_score"],
                "verifiable_evidence_score": assurance["verifiable_evidence_score"],
                "authentic_external_evidence_score": assurance["authentic_external_evidence_score"],
                "database_health": f"{assurance['database_health']['healthy_count']}/{assurance['database_health']['database_count']}",
                "tests_passed": payload["test_count"],
                "tests_skipped": payload["skipped_count"],
            },
            indent=2,
        )
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
