from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.operational_v164 import provisioning_catalog, runtime_inventory  # noqa: E402


def _commands(frame, backend: str, environment: str) -> list[list[str]]:
    commands: list[list[str]] = []
    for row in frame.to_dict(orient="records"):
        if bool(row["manual_distribution"]):
            continue
        conda = [v.strip() for v in str(row["conda_packages"]).split(",") if v.strip()]
        pip = [v.strip() for v in str(row["pip_packages"]).split(",") if v.strip()]
        if backend == "micromamba" and conda:
            commands.append(["micromamba", "install", "-y", "-n", environment, "-c", "conda-forge", "-c", "bioconda", "--strict-channel-priority", *conda])
        elif backend == "conda" and conda:
            commands.append(["conda", "install", "-y", "-n", environment, "-c", "conda-forge", "-c", "bioconda", "--strict-channel-priority", *conda])
        elif backend == "pip" and pip:
            commands.append([sys.executable, "-m", "pip", "install", "--upgrade", *pip])
    return commands


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or execute Step 164 specialist runtime provisioning commands.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--engine", action="append", default=[])
    parser.add_argument("--backend", choices=["micromamba", "conda", "pip"], default="micromamba")
    parser.add_argument("--environment", default="biointel-step164")
    parser.add_argument("--execute", action="store_true", help="Execute network/package-manager commands. Omit for safe dry-run.")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    selected = args.engine or None
    catalog = provisioning_catalog(selected)
    commands = _commands(catalog, args.backend, args.environment)
    results = []
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    for command in commands:
        if args.execute:
            completed = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True, check=False)
            results.append({"command": command, "return_code": completed.returncode, "stdout_tail": completed.stdout[-2000:], "stderr_tail": completed.stderr[-2000:]})
        else:
            results.append({"command": command, "return_code": None, "dry_run": True})
    inventory = runtime_inventory(selected)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(reports / "step164_runtime_inventory.csv", index=False)
    payload = {
        "schema": "biointel.step164.runtime-manager.v1",
        "backend": args.backend,
        "environment": args.environment,
        "execute": args.execute,
        "recipes": int(len(catalog)),
        "automatic_commands": len(commands),
        "manual_provider_installations": int(catalog["manual_distribution"].astype(bool).sum()),
        "installed_after_probe": int(inventory["installed"].astype(bool).sum()),
        "commands": results,
        "licences_and_provider_terms_not_auto_accepted": True,
    }
    (reports / "step164_runtime_manager.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for item in results:
        print(" ".join(shlex.quote(v) for v in item["command"]))
    print(json.dumps({k: v for k, v in payload.items() if k != "commands"}, indent=2, sort_keys=True))
    return 0 if all(item.get("return_code") in {None, 0} for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
