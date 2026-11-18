from __future__ import annotations

import json
import sqlite3
from biointel.database.core import managed_connect
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from biointel.innovation.advanced_engines import workflow_dag_from_blocks
from biointel.innovation.engines import WORKFLOW_TEMPLATES

from .executor import execute_workflow_v3
from .provenance import hash_json, sha256_file, utc_now
from .registry import WorkflowRegistry
from .scientific_quality import assess_quality


def run_self_test(root: str | Path) -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    root_path.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str, metrics: dict[str, Any] | None = None) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail, "metrics": metrics or {}})

    try:
        quality = assess_quality()
        record("quality_model", quality.implementation_readiness >= 9, "Implementation and scientific evidence are scored separately.", quality.to_dict())
    except Exception as exc:
        record("quality_model", False, str(exc))

    try:
        registry = WorkflowRegistry(root_path / "self_test_registry.sqlite3")
        report = registry.integrity_report()
        record("registry_integrity", report["healthy"], "SQLite registry quick check and foreign keys.", report)
    except Exception as exc:
        record("registry_integrity", False, str(exc))

    try:
        template = WORKFLOW_TEMPLATES["Protein engineering"]
        dag = workflow_dag_from_blocks(template)
        run = execute_workflow_v3(
            dag,
            root_path / "workflow_runs",
            "quality10_self_test",
            parameters={"candidate_limit": 20, "fail_on_quality_gate": False},
            registry_path=root_path / "self_test_registry.sqlite3",
            source_kind="demo",
            synthetic=True,
        )
        report_path = Path(run.output_directory) / "run_summary.json"
        record(
            "workflow_execution",
            run.status == "completed" and report_path.is_file(),
            "Dependency-aware built-in workflow executed with persisted provenance.",
            {"run_id": run.run_id, "status": run.status, "steps": len(run.steps), "summary_sha256": sha256_file(report_path)},
        )
    except Exception as exc:
        record("workflow_execution", False, str(exc))

    try:
        with managed_connect(root_path / "self_test_registry.sqlite3") as connection:
            counts = {
                "runs": connection.execute("SELECT COUNT(*) FROM workflow_runs").fetchone()[0],
                "steps": connection.execute("SELECT COUNT(*) FROM workflow_steps").fetchone()[0],
                "artifacts": connection.execute("SELECT COUNT(*) FROM workflow_artifacts").fetchone()[0],
            }
        record("provenance_persistence", counts["runs"] >= 1 and counts["steps"] >= 1 and counts["artifacts"] >= 1, "Run, step and artifact records persisted.", counts)
    except Exception as exc:
        record("provenance_persistence", False, str(exc))

    payload = {
        "schema": "biointel.step95.quality10.self-test.v1",
        "generated_at": utc_now(),
        "status": "passed" if all(item["passed"] for item in checks) else "failed",
        "checks": checks,
    }
    payload["report_sha256"] = hash_json(payload)
    (root_path / "quality10_self_test.json").write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return payload
