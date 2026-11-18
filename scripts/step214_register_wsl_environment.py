from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from biointel.engine_platform_v196 import EngineStateStore
from biointel.engine_platform_v196.acquisition import acquisition_recipes
from biointel.engine_platform_v196.state import utc_now
from biointel.native.engines import ENGINE_REGISTRY


def _wrapper_text(python: Path, proxy: Path, distribution: str, environment: str, engine: str) -> str:
    return (
        "@echo off\r\n"
        "setlocal EnableExtensions DisableDelayedExpansion\r\n"
        f'"{python}" "{proxy}" --distribution "{distribution}" --environment "{environment}" --engine "{engine}" -- %*\r\n'
        "exit /b %ERRORLEVEL%\r\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Register a BioIntel micromamba environment through safe Windows wrappers.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--user-data", type=Path, required=True)
    parser.add_argument("--distribution", default="Ubuntu")
    parser.add_argument("--environment", default="biointel-engines-v196")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    user_data = args.user_data.resolve()
    wrappers = user_data / "Tools" / "WSL2" / "bin"
    wrappers.mkdir(parents=True, exist_ok=True)
    proxy = root / "scripts" / "step214_wsl_engine_proxy.py"
    python = Path(sys.executable).resolve()
    store = EngineStateStore(user_data=user_data)
    rows = []
    for recipe in acquisition_recipes(root=root):
        if recipe.mode != "wsl2-micromamba":
            continue
        wrapper = wrappers / f"{recipe.engine}.cmd"
        wrapper.write_text(_wrapper_text(python, proxy, args.distribution, args.environment, recipe.engine), encoding="utf-8", newline="")
        digest = hashlib.sha256(wrapper.read_bytes()).hexdigest()
        spec = ENGINE_REGISTRY[recipe.engine]
        completed = subprocess.run(
            [str(wrapper), *spec.version_args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        version = (completed.stdout + "\n" + completed.stderr).strip()[:2000]
        available = completed.returncode == 0 or bool(version)
        state = "installed-unqualified" if available else "wsl-environment-engine-missing"
        store.upsert_engine(
            recipe.engine,
            state=state,
            backend="wsl2-micromamba",
            version=version,
            executable=str(wrapper),
            executable_sha256=digest,
            qualified=False,
            last_probe_utc=utc_now(),
            message=f"WSL2 distribution={args.distribution}; environment={args.environment}",
        )
        rows.append({"engine": recipe.engine, "available": available, "state": state, "wrapper": str(wrapper), "version": version})
    payload = {
        "schema": "biointel.wsl2-engine-registration.v1",
        "distribution": args.distribution,
        "environment": args.environment,
        "registered": len(rows),
        "available": sum(bool(item["available"]) for item in rows),
        "rows": rows,
        "claim_boundary": "Registered WSL wrappers are available-unqualified until target-machine qualification specifications pass.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
