from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.step122.protein_design import (
    build_protein_design_plan,
    execute_protein_design_plan,
    stage_protein_design_input,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a protected BioIntel Step 122 protein-design request")
    parser.add_argument("request", type=Path, help="JSON request based on data/templates/step122")
    parser.add_argument("--execute", action="store_true", help="Execute instead of saving a dry-run plan")
    parser.add_argument("--force", action="store_true", help="Re-run a completed request")
    args = parser.parse_args()

    request_path = args.request.expanduser().resolve()
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    if payload.get("schema") != "biointel.step122.protein_design_request.v1":
        raise ValueError("Unsupported request schema")
    backend = str(payload["backend"])
    workspace = Path(payload.get("workspace", "workspace/protein_design_runs"))
    if not workspace.is_absolute():
        workspace = (ROOT / workspace).resolve()
    source = Path(payload["input_path"]).expanduser().resolve()
    staged = stage_protein_design_input(
        workspace=workspace,
        source_path=source,
        run_name=str(payload.get("run_name", backend)),
    )
    plan = build_protein_design_plan(
        backend,
        run_directory=staged["run_directory"],
        input_path=staged["input_path"],
        parameters=payload.get("parameters", {}),
    )
    dry_run = not args.execute or bool(payload.get("dry_run", False) and not args.execute)
    timeout = max(1, int(payload.get("timeout_hours", 48))) * 3600
    result = execute_protein_design_plan(plan, timeout_seconds=timeout, force=args.force, dry_run=dry_run)
    summary = {
        "schema": result.schema,
        "run_id": result.run_id,
        "backend": result.backend,
        "status": result.status,
        "resumed": result.resumed,
        "run_directory": result.run_directory,
        "manifest_path": result.manifest_path,
        "output_files": len(result.outputs),
        "candidates": len(result.candidates),
        "release_gate": result.release_gate,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
