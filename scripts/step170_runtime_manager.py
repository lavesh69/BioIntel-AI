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

from biointel.runtime_v170 import Step170Registry, engine_catalog, probe_engines, provisioning_commands


def _run(command: list[str], root: Path) -> dict[str, object]:
    proc = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return {"command": command, "return_code": proc.returncode, "stdout_tail": proc.stdout[-4000:], "stderr_tail": proc.stderr[-4000:]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Step 170 specialist runtime manager")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--environment", default="biointel-step170")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--engine", action="append", default=[])
    args = parser.parse_args()
    root = Path(args.root).resolve()
    plan = provisioning_commands(root, environment=args.environment)
    selected = set(args.engine)
    if selected:
        catalog = engine_catalog()
        unknown = selected.difference(set(catalog["engine"]))
        if unknown:
            raise SystemExit(f"Unknown engines: {sorted(unknown)}")
        conda = []
        pip = []
        for row in catalog.loc[catalog["engine"].isin(selected)].to_dict(orient="records"):
            conda.extend(v.strip() for v in str(row["conda_packages"]).split(",") if v.strip())
            pip.extend(v.strip() for v in str(row["pip_packages"]).split(",") if v.strip())
        commands = []
        if conda:
            commands.append(["micromamba", "install", "-y", "-n", args.environment, "-c", "conda-forge", "-c", "bioconda", "--strict-channel-priority", *sorted(set(conda))])
        if pip:
            commands.append(["micromamba", "run", "-n", args.environment, "python", "-m", "pip", "install", "--upgrade", *sorted(set(pip))])
    else:
        commands = plan["automatic_commands"]
    results = []
    for command in commands:
        print(" ".join(shlex.quote(v) for v in command))
        results.append(_run(command, root) if args.execute else {"command": command, "return_code": None, "dry_run": True})
    inventory = probe_engines()
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    inventory.to_csv(reports / "step170_runtime_inventory.csv", index=False)
    payload = {
        "schema": "biointel.step170.runtime-manager.v1",
        "execute": args.execute,
        "environment": args.environment,
        "engine_catalog_size": 53,
        "automatic_commands": len(commands),
        "manual_provider_installations": len(plan["manual_installations"]),
        "installed_detected": int(inventory["installed"].sum()),
        "smoke_tests_passed": int(inventory["smoke_test_passed"].sum()),
        "fully_qualified": int(inventory["qualified"].sum()),
        "commands": results,
        "licences_not_auto_accepted": True,
        "runtime_is_managed_outside_application_archives": True,
    }
    (reports / "step170_runtime_manager.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "commands"}, indent=2))
    return 0 if all(row.get("return_code") in {None, 0} for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
