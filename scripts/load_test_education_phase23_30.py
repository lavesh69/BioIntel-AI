"""Run bounded local Phase 23-30 workload probes without claiming capacity."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.education.paths import education_paths  # noqa: E402
from biointel.education.phase23_30.service import (  # noqa: E402
    EducationEnterprisePlatform,
)
from biointel.education.platform import EducationPlatform  # noqa: E402


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * percent))
    return round(ordered[index], 3)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bounded local BioIntel Education Phase 23-30 load probe"
    )
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--profile", choices=("500", "1000", "5000"), default="500")
    parser.add_argument("--operations", type=int, default=800)
    parser.add_argument("--concurrency", type=int, default=0)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    database, media = education_paths(root)
    platform = EducationPlatform(database, media)
    institution = platform._one(
        "SELECT id FROM institutions WHERE name='Phase 23-30 Load Probe'"
    )
    if institution:
        institution_id = str(institution["id"])
    else:
        institution_id = str(
            platform.create_institution(
                "phase30-load-admin",
                "Phase 23-30 Load Probe",
            )["id"]
        )
    service = EducationEnterprisePlatform(platform, root=str(root))
    profile = next(
        item
        for item in service.load_profiles()
        if int(item["users"]) == int(args.profile)
    )
    concurrency = args.concurrency or int(profile["recommended_concurrency"])
    operations = max(1, min(int(args.operations), 100_000))

    def database_read() -> None:
        service.platform._one(
            "SELECT COUNT(*) count FROM memberships WHERE institution_id=?",
            (institution_id,),
        )

    def agent_catalog() -> None:
        service.agent_registry("phase30-load-admin", institution_id)

    def release_report() -> None:
        service.database_inventory()

    def calculation() -> None:
        service.convert_unit(1.0, "ml", "ul")
        service.dilution_result(10.0, 2.0, 4.0)

    def upload_hash() -> None:
        hashlib.sha256(b"bounded-local-lecture-upload-probe" * 64).hexdigest()

    operations_by_scenario: dict[str, Callable[[], None]] = {
        "classroom_activity": database_read,
        "connect_messaging": database_read,
        "shiro_queries": agent_catalog,
        "examination_start_spike": database_read,
        "examination_submission_spike": database_read,
        "report_generation": release_report,
        "bulk_imports": calculation,
        "lecture_uploads": upload_hash,
    }
    scenarios = list(operations_by_scenario)

    def execute(index: int) -> tuple[str, float, str]:
        scenario = scenarios[index % len(scenarios)]
        started = time.perf_counter()
        try:
            operations_by_scenario[scenario]()
            return scenario, (time.perf_counter() - started) * 1000, ""
        except Exception as exc:  # load probes must retain failure evidence
            return scenario, (time.perf_counter() - started) * 1000, (
                f"{type(exc).__name__}: {exc}"
            )

    started = time.perf_counter()
    results: list[tuple[str, float, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, 256))) as executor:
        futures = [executor.submit(execute, index) for index in range(operations)]
        for future in as_completed(futures):
            results.append(future.result())
    elapsed = time.perf_counter() - started

    scenario_results = []
    for scenario in scenarios:
        rows = [row for row in results if row[0] == scenario]
        latencies = [row[1] for row in rows]
        errors = [row[2] for row in rows if row[2]]
        scenario_results.append(
            {
                "scenario": scenario,
                "classification": "measured_local_component",
                "operations": len(rows),
                "errors": len(errors),
                "sample_errors": errors[:5],
                "latency_ms": {
                    "mean": round(statistics.fmean(latencies), 3),
                    "p50": percentile(latencies, 0.50),
                    "p95": percentile(latencies, 0.95),
                    "p99": percentile(latencies, 0.99),
                },
            }
        )
    report = {
        "schema": "biointel.education.phase23-30.local-load-probe.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "requested_virtual_users": int(args.profile),
        "executed_operations": operations,
        "worker_concurrency": concurrency,
        "elapsed_seconds": round(elapsed, 3),
        "throughput_operations_per_second": round(operations / elapsed, 3),
        "error_count": sum(1 for row in results if row[2]),
        "classification": {
            "operation_metrics": "measured",
            "profile_user_count": "simulated",
            "production_capacity": "not_verified",
        },
        "warning": (
            "This bounded local component probe is not a 500/1,000/5,000-user "
            "production capacity result. Representative infrastructure, datasets, "
            "network paths, external services and user behavior were not present."
        ),
        "scenarios": scenario_results,
    }
    output = (
        Path(args.output).resolve()
        if args.output
        else root / "reports" / f"phase23-30-load-probe-{args.profile}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "operations": operations,
                "errors": report["error_count"],
                "classification": report["classification"],
            },
            ensure_ascii=True,
        )
    )
    return 0 if report["error_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
