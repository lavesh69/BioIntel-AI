from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.final_v173 import ALL_MODULES  # noqa: E402
from biointel.realworld_v174 import (  # noqa: E402
    Step174ExecutionRegistry,
    automatic_environment_probe,
    build_step174_assets,
    prepare_execution_workspace,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _workspace(module_key: str) -> Path:
    user_data = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or (ROOT / "UserData")).resolve()
    return user_data / "step174" / "execution_workspaces" / module_key


def _write_json(path: Path, value: Any, *, overwrite: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return path
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return path


def _write_text(path: Path, value: str, *, overwrite: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return path
    path.write_text(value, encoding="utf-8")
    return path


def _ensure_module(module_key: str) -> None:
    if module_key not in ALL_MODULES:
        raise SystemExit(f"Unknown module_key: {module_key}")
    prepare_execution_workspace(ROOT, module_key)


def prepare_model_cohort(module_key: str) -> list[Path]:
    _ensure_module(module_key)
    folder = _workspace(module_key) / "phase04_model_cohort"
    files = [
        _write_json(folder / "model_card.json", {
            "schema": "biointel.step174.model-card-input.v1",
            "module_key": module_key,
            "model_name": "",
            "model_version": "",
            "task_scope": "",
            "model_artifact": {"path": "", "sha256": ""},
            "training_cohort": {"path": "", "sha256": "", "provider": "", "accession_or_doi": "", "licence": ""},
            "feature_schema": {"path": "", "sha256": ""},
            "environment_lock": {"path": "", "sha256": ""},
            "training_log": {"path": "", "sha256": ""},
            "synthetic_only": False,
            "wrong_domain_substitution": False,
            "release_eligible": False,
        }),
        _write_json(folder / "cohort_manifest.json", {
            "schema": "biointel.step174.real-cohort-input.v1",
            "module_key": module_key,
            "provider": "",
            "accession_or_doi": "",
            "release_id": "",
            "licence_id": "",
            "data_path": "",
            "data_sha256": "",
            "metadata_path": "",
            "metadata_sha256": "",
            "sample_count": 0,
            "feature_count": 0,
            "organism_or_population": "",
            "site_count": 0,
            "human_data_authorized": False,
            "de_identification_verified": False,
        }),
        _write_text(folder / "README.md", "# Phase 4 model/cohort intake\n\nAttach genuine task-specific model and cohort artifacts. Do not use synthetic or wrong-domain substitutes.\n"),
    ]
    return files


def prepare_benchmark(module_key: str) -> list[Path]:
    _ensure_module(module_key)
    folder = _workspace(module_key) / "phase05_independent_benchmark"
    return [
        _write_json(folder / "benchmark_protocol.json", {
            "schema": "biointel.step174.independent-benchmark-input.v1",
            "module_key": module_key,
            "protocol_locked_before_outcomes": False,
            "development_cohort_sha256": "",
            "validation_cohort_sha256": "",
            "untouched_test_cohort_sha256": "",
            "independent_site": "",
            "primary_metric": "",
            "acceptance_threshold": None,
            "secondary_metrics": [],
            "subgroups": [],
            "leakage_audit_path": "",
            "leakage_audit_sha256": "",
            "calibration_report_path": "",
            "calibration_report_sha256": "",
            "prediction_export_path": "",
            "prediction_export_sha256": "",
            "ground_truth_path": "",
            "ground_truth_sha256": "",
            "passed": False,
        }),
        _write_text(folder / "README.md", "# Phase 5 independent benchmark\n\nLock the benchmark protocol and holdout checksums before evaluating the model.\n"),
    ]


def prepare_expert_kit(module_key: str) -> list[Path]:
    _ensure_module(module_key)
    folder = _workspace(module_key) / "phase07_expert_signoff"
    return [
        _write_json(folder / "expert_submission.json", {
            "schema": "biointel.step174.expert-signoff-input.v1",
            "module_key": module_key,
            "expert_id": "",
            "name": "",
            "domain": "",
            "institution": "",
            "independent": True,
            "approved": False,
            "credential_path": "",
            "credential_sha256": "",
            "conflict_disclosure_path": "",
            "conflict_disclosure_sha256": "",
            "review_path": "",
            "review_sha256": "",
            "signature_path": "",
            "signature_sha256": "",
            "public_key_path": "",
            "public_key_sha256": "",
        }),
        _write_text(folder / "SIGNING_COMMANDS.txt", "openssl dgst -sha256 -sign private_key.pem -out review.sig review.pdf\nopenssl dgst -sha256 -verify public_key.pem -signature review.sig review.pdf\n"),
        _write_text(folder / "README.md", "# Phase 7 expert sign-off\n\nThe expert must supply credential, conflict disclosure, signed review, detached signature and public key. Never submit a private key.\n"),
    ]


def prepare_history(module_key: str) -> list[Path]:
    _ensure_module(module_key)
    folder = _workspace(module_key) / "phase08_operating_history"
    csv_path = folder / "operating_history.csv"
    if not csv_path.exists():
        _write_text(csv_path, "run_id,started_at_utc,completed_at_utc,site_id,instrument_id,dataset_sha256,outcome,failure_code,downtime_minutes,drift_review,capa_id,reviewer\n")
    return [
        csv_path,
        _write_json(folder / "history_summary.json", {
            "schema": "biointel.step174.operating-history-input.v1",
            "module_key": module_key,
            "runs": 0,
            "successful_runs": 0,
            "failed_runs": 0,
            "downtime_minutes": 0,
            "unresolved_critical_incidents": 0,
            "drift_review_complete": False,
            "report_path": "",
            "report_sha256": "",
        }),
        _write_text(folder / "README.md", "# Phase 8 operating history\n\nAppend genuine runs and incidents. Demo runs or generated history are not eligible.\n"),
    ]


def prepare_release(module_key: str) -> list[Path]:
    _ensure_module(module_key)
    folder = _workspace(module_key) / "phase09_formal_release"
    return [
        _write_json(folder / "release_decision.json", {
            "schema": "biointel.step174.formal-release-input.v1",
            "module_key": module_key,
            "release_id": "",
            "decision": "pending",
            "quorum": 0,
            "independent_qa_approval": False,
            "domain_expert_approval": False,
            "product_owner_approval": False,
            "risk_acceptance_documented": False,
            "intended_use": "",
            "prohibited_use": "",
            "rollback_plan": "",
            "post_release_monitoring_plan": "",
            "decision_path": "",
            "decision_sha256": "",
        }),
        _write_text(folder / "README.md", "# Phase 9 formal release\n\nThe committee decision is eligible only after every required upstream phase has passed.\n"),
    ]


def result_payload(paths: list[Path]) -> dict[str, Any]:
    return {
        "status": "prepared",
        "files": [{"path": str(path), "sha256": _sha(path), "size_bytes": path.stat().st_size} for path in paths if path.is_file()],
        "external_evidence_created": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="BioIntel AI Step 174 Phase 1–9 execution manager")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("refresh")
    p = sub.add_parser("prepare-all"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("prepare-module"); p.add_argument("--module", required=True); p.add_argument("--force", action="store_true")
    sub.add_parser("environment-probe")
    for name in ("prepare-model-cohort", "prepare-benchmark", "prepare-expert-kit", "prepare-history", "prepare-release"):
        p = sub.add_parser(name); p.add_argument("--module", required=True)
    args = parser.parse_args()

    build_step174_assets(ROOT)
    registry = Step174ExecutionRegistry(ROOT)
    if args.command == "status":
        matrix = registry.latest(refresh=False)
        print(json.dumps({
            "schema": "biointel.step174.manager-status.v1",
            "version": "14.6.0",
            "modules": len(matrix),
            "software_automation_ready": int(matrix["all_phase_software_automation_available"].sum()),
            "controlled_release_eligible": int(matrix["controlled_release_eligible"].sum()),
            "average_external_phase_completion": round(float(matrix["phase_completion_fraction"].mean()), 4),
            "registry": registry.status(),
        }, indent=2)); return 0
    if args.command == "refresh":
        matrix = registry.refresh(); print(matrix.to_json(orient="records", indent=2)); return 0
    if args.command == "prepare-all":
        paths = prepare_execution_workspace(ROOT, force=args.force)
        print(json.dumps(result_payload(paths), indent=2)); return 0
    if args.command == "prepare-module":
        paths = prepare_execution_workspace(ROOT, args.module, force=args.force)
        print(json.dumps(result_payload(paths), indent=2)); return 0
    if args.command == "environment-probe":
        report = automatic_environment_probe(ROOT)
        out = ROOT / "reports" / "step174_environment_probe.json"
        _write_json(out, report, overwrite=True)
        print(json.dumps(report, indent=2)); return 0 if report["automatic_checks_passed"] else 1
    mapping = {
        "prepare-model-cohort": prepare_model_cohort,
        "prepare-benchmark": prepare_benchmark,
        "prepare-expert-kit": prepare_expert_kit,
        "prepare-history": prepare_history,
        "prepare-release": prepare_release,
    }
    paths = mapping[args.command](args.module)
    print(json.dumps(result_payload(paths), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
