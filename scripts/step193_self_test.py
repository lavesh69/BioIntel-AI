from __future__ import annotations

import argparse
import compileall
import importlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def check(name: str, fn: Callable[[], str], severity: str = "critical") -> dict[str, Any]:
    started = time.perf_counter()
    try:
        return {
            "name": name,
            "status": "PASS",
            "severity": severity,
            "detail": fn(),
            "seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        return {
            "name": name,
            "status": "FAIL",
            "severity": severity,
            "detail": f"{type(exc).__name__}: {exc}",
            "seconds": round(time.perf_counter() - started, 3),
        }


def _version_tuple(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value)
    return tuple(int(part) for part in numbers[:4]) or (0,)


def _read_assignment(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    match = re.search(
        rf"^\s*{re.escape(name)}\s*=\s*['\"]([^'\"]+)['\"]",
        text,
        flags=re.MULTILINE,
    )
    if not match:
        raise RuntimeError(f"{name} was not found in {path.relative_to(path.parents[2])}")
    return match.group(1).strip()


def version_contract(root: Path) -> str:
    current = (root / "VERSION").read_text(encoding="utf-8-sig").strip()
    package = _read_assignment(root / "src" / "biointel" / "__init__.py", "__version__")
    baseline = _read_assignment(
        root / "src" / "biointel" / "mandatory_completion_v193" / "catalog.py",
        "RELEASE_VERSION",
    )
    if not current or package != current:
        raise RuntimeError(f"package={package!r} VERSION={current!r}")
    if _version_tuple(baseline) > _version_tuple(current):
        raise RuntimeError(
            f"mandatory baseline {baseline} is newer than current release {current}"
        )
    return (
        f"BioIntel AI {current}; Step 193 mandatory baseline "
        f"{baseline} is backward-compatible"
    )


def installer_contract(root: Path) -> str:
    bat_path = root / "INSTALL_WINDOWS.bat"
    locator_path = root / "scripts" / "find_python311_windows.ps1"
    if not bat_path.is_file():
        raise RuntimeError("INSTALL_WINDOWS.bat missing")
    if not locator_path.is_file():
        raise RuntimeError("scripts/find_python311_windows.ps1 missing")

    bat = bat_path.read_text(encoding="utf-8-sig", errors="replace")
    helper_match = re.search(r"scripts[\\/](install_windows_step\d+\.py)", bat, re.IGNORECASE)
    marker_match = re.search(r"step(\d+)_part%%P\.ok", bat, re.IGNORECASE)
    if not helper_match:
        raise RuntimeError("active Windows installer helper is not referenced")
    if not marker_match:
        raise RuntimeError("active release-part markers are not checked")
    if "find_python311_windows.ps1" not in bat:
        raise RuntimeError("Python 3.11 locator is not referenced")

    helper_rel = Path("scripts") / helper_match.group(1)
    helper_path = root / helper_rel
    if not helper_path.is_file():
        raise RuntimeError(f"active installer helper missing: {helper_rel.as_posix()}")
    helper = helper_path.read_text(encoding="utf-8-sig", errors="replace")
    required_helper_tokens = (
        "step193_self_test.py",
        "--allow-degraded",
        "verify_windows_wheelhouse.py",
        "step196_preinstall_contract.py",
        "setup_scientific_runtime_windows.py",
        "launch_scientific_runtime_setup",
    )
    missing = [token for token in required_helper_tokens if token not in helper]
    if missing:
        raise RuntimeError("active installer helper contract missing: " + ", ".join(missing))

    active_step = int(marker_match.group(1))
    release_manifest = root / f"STEP{active_step}_RELEASE.json"
    if not release_manifest.is_file():
        raise RuntimeError(f"active release manifest missing: {release_manifest.name}")
    release = json.loads(release_manifest.read_text(encoding="utf-8-sig"))
    if int(release.get("step", 0) or 0) != active_step:
        raise RuntimeError(
            f"release manifest step mismatch: marker={active_step}, manifest={release.get('step')}"
        )

    return f"Step {active_step} markers, {helper_rel.as_posix()} and Python locator aligned"


def run(root: Path, allow_degraded: bool = False, contract_only: bool = False) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append(check("Version compatibility", lambda: version_contract(root)))
    checks.append(check("Windows installer contract", lambda: installer_contract(root)))

    if not contract_only:
        def imports() -> str:
            names = ["numpy", "pandas", "scipy", "sklearn", "streamlit", "fastapi", "Bio", "rdkit"]
            return ", ".join(
                f"{name}={getattr(importlib.import_module(name), '__version__', 'installed')}"
                for name in names
            )

        checks.append(check("Core scientific imports", imports))

        def completion() -> str:
            # Import the scientific module graph only after the virtual environment
            # has been installed. Contract-only preflight must stay stdlib-only.
            from biointel.mandatory_completion_v193 import TARGET_MODULES, validate_module

            bad = {
                key: validate_module(root, key).blockers
                for key in TARGET_MODULES
                if not validate_module(root, key).qualified
            }
            if bad:
                raise RuntimeError(str(bad)[:1000])
            return "80/80 mandatory module qualification passed"

        checks.append(check("Step 193 mandatory module completion", completion))

        def compile_project() -> str:
            ok = all(
                compileall.compile_dir(str(root / name), quiet=1, force=False)
                for name in ("src", "pages", "scripts")
            )
            if not ok:
                raise RuntimeError("Compilation failed")
            return "src, pages and scripts compiled"

        checks.append(check("Python compilation", compile_project))

    critical = [
        row for row in checks
        if row["status"] != "PASS" and row["severity"] == "critical"
    ]
    return {
        "schema": "biointel.step193.self-test.v3",
        "status": "PASS" if not critical else ("DEGRADED" if allow_degraded else "FAIL"),
        "passed": not critical,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output")
    parser.add_argument("--allow-degraded", action="store_true")
    parser.add_argument("--contract-only", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    result = run(root, args.allow_degraded, args.contract_only)
    output = Path(args.output) if args.output else root / "reports" / "step193" / "self_test.json"
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
