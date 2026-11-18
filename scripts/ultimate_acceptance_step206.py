from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from step206_contract import (
    PACKAGE_GENERATION,
    PRODUCT_VERSION,
    RELEASE_STEP,
    REQUIRED_PYTHON,
    user_data_directory,
)

ROOT = Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _run(name: str, command: list[str], root: Path, env: dict[str, str], timeout: int = 600) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
        )
        return {
            "name": name,
            "passed": result.returncode == 0,
            "return_code": result.returncode,
            "command": [Path(item).name if index == 0 else item for index, item in enumerate(command)],
            "stdout_tail": result.stdout[-4000:],
            "stderr_tail": result.stderr[-4000:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"name": name, "passed": False, "error": f"{type(exc).__name__}: {exc}"}


def _path_round_trip() -> dict[str, Any]:
    base = Path(tempfile.mkdtemp(prefix="biointel acceptance space üñîçødé "))
    try:
        payload = "BioIntel Unicode and spaces round-trip ✓\n"
        path = base / "project space नमूना" / "evidence üñîçødé.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        passed = path.read_text(encoding="utf-8") == payload
        return {"name": "spaces and Unicode path round-trip", "passed": passed, "path_length": len(str(path))}
    except OSError as exc:
        return {"name": "spaces and Unicode path round-trip", "passed": False, "error": str(exc)}
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _write_reports(output: Path, payload: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    markdown = output.with_suffix(".md")
    lines = [
        f"# BioIntel AI Step{RELEASE_STEP} Ultimate Acceptance",
        "",
        f"Generated: {payload['generated_at_utc']}",
        f"Software gates: {'PASS' if payload['software_gate_passed'] else 'FAIL'}",
        f"Native Windows gate: {'PASS' if payload['native_windows_gate_passed'] else 'NOT PASSED'}",
        f"Release ready on this host: {'YES' if payload['release_ready_on_this_host'] else 'NO'}",
        "",
        "## Checks",
        "",
        "| Check | Class | Result |",
        "|---|---|---|",
    ]
    for check in payload["checks"]:
        lines.append(f"| {check['name']} | {check.get('classification', 'software')} | {'PASS' if check.get('passed') else 'FAIL'} |")
    lines.extend(
        [
            "",
            "## Evidence-bound external gates",
            "",
            *[f"- {item}" for item in payload["external_evidence_gates"]],
            "",
            "These external gates cannot be converted into a pass by a command-line flag; attach authentic target/site evidence.",
        ]
    )
    markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Run BioIntel AI Step{RELEASE_STEP} final software and target-Windows acceptance gates.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--output")
    parser.add_argument("--require-native-windows", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    native_windows = os.name == "nt" and platform.system().casefold() == "windows"
    exact_runtime = sys.version_info[:2] == REQUIRED_PYTHON and struct.calcsize("P") * 8 == 64
    env = os.environ.copy()
    env.update({"PYTHONPATH": str(root / "src"), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})

    checks: list[dict[str, Any]] = [
        {
            "name": "supported native Windows host",
            "classification": "native-windows",
            "passed": native_windows,
            "detail": platform.platform(),
        },
        {
            "name": "CPython 3.11.x x64 runtime",
            "classification": "native-windows",
            "passed": exact_runtime,
            "detail": {"version": sys.version.split()[0], "bits": struct.calcsize("P") * 8},
        },
    ]
    path_check = _path_round_trip()
    path_check["classification"] = "software"
    checks.append(path_check)

    release_gate = [sys.executable, str(root / "scripts" / "step206_release_gate.py"), "--root", str(root), "--deep-hashes"]
    if not native_windows:
        release_gate.append("--allow-builder-python")
    commands = [
        ("deep source/release integrity", release_gate, 900),
        ("dependency lock integrity", [sys.executable, str(root / "scripts" / "verify_dependency_lock.py"), "--root", str(root)], 300),
        ("offline Windows wheelhouse integrity", [sys.executable, str(root / "scripts" / "verify_windows_wheelhouse.py"), "--root", str(root)], 600),
        (
            "central registry integrity",
            [
                sys.executable,
                "-c",
                "from biointel.product_registry import registry_integrity; r=registry_integrity(); print(r); raise SystemExit(0 if r['healthy'] else 1)",
            ],
            300,
        ),
        ("Python and SQLite static qualification", [sys.executable, str(root / "scripts" / "step173_static_qualification.py")], 900),
    ]
    for name, command, timeout in commands:
        check = _run(name, command, root, env, timeout)
        check["classification"] = "software"
        checks.append(check)

    verification = [sys.executable, str(root / "scripts" / "verify_step206_windows_install_run.py"), "--root", str(root)]
    if native_windows:
        verification.extend(("--installed-python", sys.executable))
    else:
        verification.append("--allow-builder-python")
    check = _run("Windows installer/runtime contract", verification, root, env, 600)
    check["classification"] = "software"
    checks.append(check)

    if native_windows and exact_runtime:
        check = _run(
            "isolated native UI/API/worker startup and cleanup",
            [sys.executable, str(root / "scripts" / "windows_smoke_test_step206.py"), "--root", str(root)],
            root,
            env,
            600,
        )
        check["classification"] = "native-windows"
        checks.append(check)
    else:
        checks.append(
            {
                "name": "isolated native UI/API/worker startup and cleanup",
                "classification": "native-windows",
                "passed": False,
                "skipped": True,
                "detail": "Requires the managed exact Python runtime on physical Windows.",
            }
        )

    software_checks = [row for row in checks if row.get("classification") == "software"]
    windows_checks = [row for row in checks if row.get("classification") == "native-windows"]
    software_passed = all(bool(row.get("passed")) for row in software_checks)
    native_passed = bool(windows_checks) and all(bool(row.get("passed")) for row in windows_checks)
    payload = {
        "schema": f"biointel.step{RELEASE_STEP}.ultimate-acceptance.v2",
        "generated_at_utc": _now(),
        "product": "BioIntel AI",
        "version": PRODUCT_VERSION,
        "build_number": f"Step{RELEASE_STEP}-{PACKAGE_GENERATION}",
        "root": str(root),
        "host": {"platform": platform.platform(), "native_windows": native_windows, "python": sys.version.split()[0]},
        "software_gate_passed": software_passed,
        "native_windows_gate_passed": native_passed,
        "release_ready_on_this_host": software_passed and native_passed,
        "checks": checks,
        "external_evidence_gates": [
            "Code-signing identity and certificate-chain review",
            "Antivirus/EDR compatibility on supported organisational policy",
            "Optional GPU and laboratory-instrument qualification on intended hardware",
            "Licensed engines, model weights and reference databases with authentic licence/checksum evidence",
            "Representative workload capacity, recovery and equivalence evidence",
            "Independent scientific, clinical, regulatory or wet-lab validation appropriate to intended use",
        ],
        "claim_boundary": "Passing this runner qualifies the included software controls on the executing host. It does not manufacture external scientific, clinical, regulatory, licence, instrument or operating-history evidence.",
    }
    output = Path(args.output).expanduser() if args.output else user_data_directory() / "reports" / f"step{RELEASE_STEP}-ultimate-acceptance.json"
    if not output.is_absolute():
        output = root / output
    _write_reports(output.resolve(), payload)
    payload["report_path"] = str(output.resolve())
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    passed = payload["release_ready_on_this_host"] if args.require_native_windows else software_passed
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
