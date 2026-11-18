from __future__ import annotations

import argparse
import compileall
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.release_integrity_v192.audit import RELEASE_VERSION, run_release_audit


def check(name: str, fn: Callable[[], str], *, severity: str = "critical") -> dict[str, Any]:
    started = time.perf_counter()
    try:
        detail = fn()
        return {"name": name, "status": "PASS", "severity": severity, "detail": detail, "seconds": round(time.perf_counter() - started, 3)}
    except Exception as exc:
        return {"name": name, "status": "FAIL", "severity": severity, "detail": f"{type(exc).__name__}: {exc}", "seconds": round(time.perf_counter() - started, 3)}


def run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    checks: list[dict[str, Any]] = []

    def version() -> str:
        import biointel
        if biointel.__version__ != RELEASE_VERSION:
            raise RuntimeError(f"biointel.__version__={biointel.__version__}, expected={RELEASE_VERSION}")
        return f"BioIntel AI {biointel.__version__}"

    checks.append(check("Version consistency", version))

    def imports() -> str:
        names = ["numpy", "pandas", "scipy", "sklearn", "streamlit", "fastapi", "Bio", "rdkit"]
        loaded = []
        for name in names:
            module = importlib.import_module(name)
            loaded.append(f"{name}={getattr(module, '__version__', 'installed')}")
        return ", ".join(loaded)

    checks.append(check("Core scientific imports", imports))

    def release_audit() -> str:
        result = run_release_audit(root, deep_hashes=False)
        if not result["passed"]:
            failed = [item["name"] for item in result["critical_failures"]]
            raise RuntimeError("; ".join(failed))
        return f"{len(result['checks'])} release checks passed"

    checks.append(check("Step 192 release audit", release_audit))

    def compile_project() -> str:
        targets = [root / "src", root / "pages", root / "scripts"]
        ok = all(compileall.compile_dir(str(target), quiet=1, force=False) for target in targets)
        if not ok:
            raise RuntimeError("One or more Python files failed compilation")
        return "src, pages and scripts compiled"

    checks.append(check("Python compilation", compile_project))

    def upload_smoke() -> str:
        from biointel.io.uploads import read_uploaded_table_bytes
        result = read_uploaded_table_bytes(b"sample,value\nA,1\nB,2\n", "step192.csv")
        if result.frame.shape != (2, 2):
            raise RuntimeError(f"unexpected shape {result.frame.shape}")
        return "CSV parser passed"

    checks.append(check("Upload parser smoke", upload_smoke))

    critical = [item for item in checks if item["status"] != "PASS" and item["severity"] == "critical"]
    return {"schema": "biointel.step192.self-test.v1", "status": "PASS" if not critical else "FAIL", "passed": not critical, "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output")
    parser.add_argument("--allow-degraded", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    result = run(root)
    output = Path(args.output) if args.output else root / "reports" / "step192" / "self_test.json"
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
