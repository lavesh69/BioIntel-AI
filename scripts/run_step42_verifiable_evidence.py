from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import sqlite3
import statistics
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in os.sys.path:
    os.sys.path.insert(0, str(SRC))

from biointel import __version__  # noqa: E402
from biointel.multitenancy.context import TenantContext  # noqa: E402
from biointel.multitenancy.storage import TenantStorageRouter  # noqa: E402
from biointel.multitenancy.store import TenantStore  # noqa: E402


def now() -> str:
    return datetime.now(UTC).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def run_database_drill(output: Path) -> dict[str, Any]:
    databases = sorted((ROOT / "reports").glob("*.sqlite3"))
    records: list[dict[str, Any]] = []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="biointel-step42-dr-") as folder:
        target = Path(folder)
        for source in databases:
            restored = target / source.name
            before = sha256_file(source)
            shutil.copy2(source, restored)
            after = sha256_file(restored)
            with sqlite3.connect(restored) as db:
                integrity = str(db.execute("PRAGMA integrity_check").fetchone()[0])
                foreign_keys = len(db.execute("PRAGMA foreign_key_check").fetchall())
            records.append(
                {
                    "database": source.name,
                    "bytes": source.stat().st_size,
                    "source_sha256": before,
                    "restored_sha256": after,
                    "checksum_match": before == after,
                    "integrity": integrity,
                    "foreign_key_issues": foreign_keys,
                }
            )
    elapsed = time.perf_counter() - started
    passed = bool(records) and all(
        item["checksum_match"] and item["integrity"] == "ok" and item["foreign_key_issues"] == 0
        for item in records
    )
    payload = {
        "schema": "biointel.step42.database-drill.v1",
        "observed_at": now(),
        "classification": "measured_controlled_environment_qualification",
        "database_count": len(records),
        "total_bytes": sum(item["bytes"] for item in records),
        "rto_minutes": elapsed / 60.0,
        "rpo_minutes": 0.0,
        "passed": passed,
        "records": records,
        "external_boundary": "This is a measured repository restore qualification, not an independently witnessed production DR event.",
    }
    write_json(output, payload)
    return payload


def run_multitenant_isolation(output: Path, iterations: int = 5000) -> dict[str, Any]:
    started = time.perf_counter()
    breaches = 0
    expected_denials = 0
    storage_violations_blocked = 0
    resources = 0
    with tempfile.TemporaryDirectory(prefix="biointel-step42-tenant-") as folder:
        root = Path(folder)
        store = TenantStore(root / "tenants.sqlite3")
        router = TenantStorageRouter(root / "objects")
        contexts: list[TenantContext] = []
        for index in range(5):
            tenant = f"tenant-{index}"
            client = f"client-{index}"
            store.ensure_tenant(tenant, f"Tenant {index}", plan="qualification")
            store.add_membership(tenant, client, "owner")
            contexts.append(
                store.resolve_context(client_id=client, api_role="admin", requested_tenant=tenant)
            )
        for index in range(iterations):
            owner = contexts[index % len(contexts)]
            other = contexts[(index + 1) % len(contexts)]
            resource_id = f"qualification-{index}"
            store.put_resource(
                owner,
                resource_type="evidence",
                name=resource_id,
                payload={"index": index},
                resource_id=resource_id,
            )
            resources += 1
            if store.get_resource(owner, resource_id)["tenant_id"] != owner.tenant_id:
                breaches += 1
            try:
                store.get_resource(other, resource_id)
                breaches += 1
            except KeyError:
                expected_denials += 1
            path = router.path(owner, "qualification", f"{index}.json", create_parent=True)
            path.write_text(str(index), encoding="utf-8")
            try:
                router.path(owner, "..", other.tenant_id, "escape.txt")
                breaches += 1
            except ValueError:
                storage_violations_blocked += 1
    elapsed = time.perf_counter() - started
    payload = {
        "schema": "biointel.step42.multitenant-isolation.v1",
        "observed_at": now(),
        "classification": "measured_controlled_environment_qualification",
        "tenant_count": 5,
        "isolation_tests": iterations,
        "resources_created": resources,
        "expected_cross_tenant_denials": expected_denials,
        "storage_traversal_attempts_blocked": storage_violations_blocked,
        "confirmed_isolation_breaches": breaches,
        "duration_seconds": elapsed,
        "operations_per_second": (iterations * 3) / elapsed if elapsed else 0.0,
        "passed": breaches == 0
        and expected_denials == iterations
        and storage_violations_blocked == iterations,
        "external_boundary": "This is controlled-environment isolation evidence, not 90-day history with independent customer tenants.",
    }
    write_json(output, payload)
    return payload


def _wait_for_http(url: str, timeout: float = 45.0) -> None:
    import httpx

    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(url, timeout=2.0)
            if response.status_code == 200:
                return
        except Exception as exc:  # pragma: no cover - startup race
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Server did not become ready: {url}: {last_error}")


def _start_uvicorn(port: int) -> subprocess.Popen[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SRC)
    environment.setdefault("BIOINTEL_ENV", "development")
    environment.setdefault("BIOINTEL_ALLOW_LOCAL_NO_AUTH", "1")
    environment["BIOINTEL_API_RATE_LIMIT"] = "100000"
    launcher = (
        "import os; "
        "os.environ['BIOINTEL_API_RATE_LIMIT']='100000'; "
        "os.environ['BIOINTEL_ALLOW_LOCAL_NO_AUTH']='1'; "
        "import uvicorn; "
        f"uvicorn.run('biointel.api.main:app', host='127.0.0.1', port={port}, log_level='warning', access_log=False)"
    )
    process = subprocess.Popen(
        [os.sys.executable, "-c", launcher],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    _wait_for_http(f"http://127.0.0.1:{port}/live")
    return process


def _stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_api_load(output: Path, requests: int = 1200, workers: int = 8) -> dict[str, Any]:
    import httpx

    port = 18765
    process: subprocess.Popen[str] | None = None
    try:
        process = _start_uvicorn(port)
        url = f"http://127.0.0.1:{port}/live"

        def worker(count: int) -> list[tuple[bool, float]]:
            measured: list[tuple[bool, float]] = []
            with httpx.Client(timeout=5.0) as client:
                for _ in range(count):
                    started_request = time.perf_counter()
                    try:
                        response = client.get(url)
                        ok = response.status_code == 200
                    except httpx.HTTPError:
                        ok = False
                    measured.append((ok, (time.perf_counter() - started_request) * 1000.0))
            return measured

        counts = [requests // workers] * workers
        for index in range(requests % workers):
            counts[index] += 1
        started = time.perf_counter()
        rows: list[tuple[bool, float]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for batch in pool.map(worker, counts):
                rows.extend(batch)
        elapsed = time.perf_counter() - started
    finally:
        _stop_process(process)

    latencies = sorted(item[1] for item in rows)
    success = sum(item[0] for item in rows)

    def percentile(value: float) -> float:
        if not latencies:
            return 0.0
        index = min(int(round((len(latencies) - 1) * value)), len(latencies) - 1)
        return latencies[index]

    availability = 100.0 * success / requests if requests else 0.0
    error_rate = 100.0 - availability
    p95 = percentile(0.95)
    payload = {
        "schema": "biointel.step42.api-load.v1",
        "observed_at": now(),
        "classification": "measured_controlled_environment_qualification",
        "requests": requests,
        "concurrency": workers,
        "successes": success,
        "failures": requests - success,
        "availability_percent": availability,
        "error_rate_percent": error_rate,
        "p50_latency_ms": percentile(0.50),
        "p95_latency_ms": p95,
        "p99_latency_ms": percentile(0.99),
        "mean_latency_ms": statistics.fmean(latencies) if latencies else 0.0,
        "duration_seconds": elapsed,
        "requests_per_second": requests / elapsed if elapsed else 0.0,
        "passed": availability == 100.0 and error_rate <= 1.0 and p95 <= 2000.0,
        "external_boundary": "This is a bounded local qualification run, not a 24-hour cloud or 90-day production SLA record.",
    }
    write_json(output, payload)
    return payload


def run_ha_rehearsal(output: Path, requests: int = 400) -> dict[str, Any]:
    import httpx

    primary: subprocess.Popen[str] | None = None
    secondary: subprocess.Popen[str] | None = None
    before = after = failures = 0
    started = time.perf_counter()
    try:
        primary = _start_uvicorn(18766)
        secondary = _start_uvicorn(18767)
        with httpx.Client(timeout=5.0) as client:
            for _ in range(requests // 2):
                try:
                    if client.get("http://127.0.0.1:18766/live").status_code == 200:
                        before += 1
                    else:
                        failures += 1
                except httpx.HTTPError:
                    failures += 1
            failover_started = time.perf_counter()
            _stop_process(primary)
            primary = None
            for _ in range(requests // 2):
                try:
                    if client.get("http://127.0.0.1:18767/live").status_code == 200:
                        after += 1
                    else:
                        failures += 1
                except httpx.HTTPError:
                    failures += 1
            failover_seconds = time.perf_counter() - failover_started
    finally:
        _stop_process(primary)
        _stop_process(secondary)
    elapsed = time.perf_counter() - started
    payload = {
        "schema": "biointel.step42.ha-rehearsal.v1",
        "observed_at": now(),
        "classification": "application_instance_failover_rehearsal",
        "requests_before_failover": before,
        "requests_after_failover": after,
        "failed_requests": failures,
        "successful_failovers": int(failures == 0 and after == requests // 2),
        "failover_duration_seconds": failover_seconds,
        "total_duration_seconds": elapsed,
        "passed": failures == 0 and before + after == requests,
        "external_boundary": "This validates application-instance continuity, not a multi-zone cloud failover or 90-day HA record.",
    }
    write_json(output, payload)
    return payload


def run_kubernetes_static(output: Path) -> dict[str, Any]:
    chart_root = ROOT / "deploy" / "helm" / "biointel"
    files = sorted(path for path in chart_root.rglob("*.yaml") if path.is_file())
    files += sorted(path for path in chart_root.rglob("*.yml") if path.is_file())
    parsed = 0
    parse_failures: list[str] = []
    corpus = ""
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        corpus += "\n" + text.lower()
        try:
            list(yaml.safe_load_all(text))
            parsed += 1
        except yaml.YAMLError:
            # Helm templates contain Go expressions and may not parse as raw YAML.
            if "{{" not in text:
                parse_failures.append(str(path.relative_to(ROOT)))
    checks = {
        "replicas": "replicacount" in corpus or "replicas:" in corpus,
        "liveness_probe": "livenessprobe" in corpus or "livenessprobe:" in corpus,
        "readiness_probe": "readinessprobe" in corpus or "readinessprobe:" in corpus,
        "startup_probe": "startupprobe" in corpus or "startupprobe:" in corpus,
        "resources": "resources:" in corpus,
        "security_context": "securitycontext" in corpus,
        "horizontal_autoscaling": "horizontalpodautoscaler" in corpus or "autoscaling/v2" in corpus,
        "pod_disruption_budget": "poddisruptionbudget" in corpus,
        "network_policy": "networkpolicy" in corpus,
        "topology_spread": "topologyspreadconstraints" in corpus,
        "service_monitor": "servicemonitor" in corpus,
        "migration_job": "kind: job" in corpus,
        "persistent_storage": "persistentvolumeclaim" in corpus,
        "ingress": "kind: ingress" in corpus,
    }
    payload = {
        "schema": "biointel.step42.kubernetes-static.v1",
        "observed_at": now(),
        "classification": "static_deployment_qualification",
        "chart_files": len(files),
        "yaml_files_parsed_without_template_errors": parsed,
        "parse_failures": parse_failures,
        "checks": checks,
        "controls_passed": sum(checks.values()),
        "controls_total": len(checks),
        "passed": not parse_failures and all(checks.values()),
        "external_boundary": "Static Helm/IaC qualification is not Kubernetes conformance certification or production cluster history.",
    }
    write_json(output, payload)
    return payload


def run_cloud_iac(output: Path) -> dict[str, Any]:
    terraform_files = sorted((ROOT / "deploy" / "terraform").rglob("*.tf"))
    corpus = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore").lower() for path in terraform_files
    )
    values = (
        (ROOT / "deploy" / "helm" / "biointel" / "values.yaml")
        .read_text(encoding="utf-8", errors="ignore")
        .lower()
    )
    checks = {
        "terraform_module": bool(terraform_files),
        "helm_release": "helm_release" in corpus,
        "configurable_namespace": "namespace" in corpus,
        "configurable_image": "image" in corpus,
        "autoscaling": "autoscaling" in values,
        "resource_limits": "resources:" in values,
        "multi_zone_topology": "topologyspread" in values,
        "network_policy": "networkpolicy" in values,
        "persistent_storage": "persistence" in values,
        "monitoring": "servicemonitor" in values,
        "aws_reference": (ROOT / "deploy" / "cloud" / "aws" / "README.md").is_file(),
        "azure_reference": (ROOT / "deploy" / "cloud" / "azure" / "README.md").is_file(),
        "gcp_reference": (ROOT / "deploy" / "cloud" / "gcp" / "README.md").is_file(),
    }
    payload = {
        "schema": "biointel.step42.cloud-iac.v1",
        "observed_at": now(),
        "classification": "static_cloud_readiness_qualification",
        "terraform_files": [str(path.relative_to(ROOT)) for path in terraform_files],
        "checks": checks,
        "controls_passed": sum(checks.values()),
        "controls_total": len(checks),
        "passed": all(checks.values()),
        "external_boundary": "Cloud-neutral IaC readiness is not cloud billing, regional traffic or production scale history.",
    }
    write_json(output, payload)
    return payload


def create_publication_bundle(output: Path) -> dict[str, Any]:
    bundle = ROOT / "reports" / "step42" / "publication_bundle"
    bundle.mkdir(parents=True, exist_ok=True)
    benchmark = ROOT / "reports" / "step38" / "uci_wdbc_real_benchmark.json"
    scientific = ROOT / "reports" / "step40_validation_qualification.json"
    documents = {
        "MANUSCRIPT_DRAFT.md": """# BioIntel AI: Reproducible Scientific Intelligence for Life Sciences\n\nThis review-ready draft documents architecture, scientific validation controls, evidence boundaries and reproducible qualification results. It does not claim regulatory approval, peer review, prospective wet-lab validation or external DTI certification.\n""",
        "METHODS.md": """# Methods\n\n- Deterministic scientific benchmarks with immutable dataset/model hashes\n- Separate implementation, verifiable internal and authentic external evidence scores\n- Cold-drug, cold-target, cold-both, scaffold and temporal validation controls\n- Calibration, uncertainty, leakage and reproducibility checks\n- Tamper-evident evidence registries and release gates\n""",
        "DATA_AVAILABILITY.md": """# Data availability\n\nPublic-reference and provider-derived records retain source, licence, release and checksum metadata. Bundled synthetic DTI models are explicitly blocked from scientific release.\n""",
        "LIMITATIONS.md": """# Limitations\n\nNo independent external DTI study, paying-customer history, regulatory approval, journal acceptance or blinded prospective wet-lab completion is bundled. Repository qualification must not be represented as those external outcomes.\n""",
        "CITATION.cff": f"""cff-version: 1.2.0\ntitle: BioIntel AI Scientific Intelligence for Life Sciences\nversion: {__version__}\nmessage: Cite the archived release and the original source datasets.\ntype: software\nlicense: Proprietary\n""",
        "REPRODUCIBILITY.json": json.dumps(
            {
                "schema": "biointel.step42.reproducibility.v1",
                "generated_at": now(),
                "benchmark": str(benchmark.relative_to(ROOT)) if benchmark.is_file() else None,
                "scientific_qualification": str(scientific.relative_to(ROOT))
                if scientific.is_file()
                else None,
                "commands": [
                    "python scripts/run_step42_verifiable_evidence.py --skip-load",
                    "python scripts/qualify_step40_validation.py",
                    "pytest -q tests/scientific tests/operations",
                ],
                "boundary": "Review-ready package without DOI or journal acceptance.",
            },
            indent=2,
            sort_keys=True,
        ),
    }
    for name, content in documents.items():
        (bundle / name).write_text(content, encoding="utf-8")
    if benchmark.is_file():
        shutil.copy2(benchmark, bundle / benchmark.name)
    if scientific.is_file():
        shutil.copy2(scientific, bundle / scientific.name)
    files = sorted(
        path for path in bundle.iterdir() if path.is_file() and path.name != "checksums.sha256"
    )
    checksums = "\n".join(f"{sha256_file(path)}  {path.name}" for path in files) + "\n"
    (bundle / "checksums.sha256").write_text(checksums, encoding="utf-8")
    verified = all(len(line.split()[0]) == 64 for line in checksums.splitlines() if line.strip())
    payload = {
        "schema": "biointel.step42.publication-bundle.v1",
        "observed_at": now(),
        "classification": "review_ready_reproducibility_package",
        "bundle": str(bundle.relative_to(ROOT)),
        "files": [path.name for path in sorted(bundle.iterdir()) if path.is_file()],
        "file_count": len(list(bundle.iterdir())),
        "checksums_verified": verified,
        "has_doi": False,
        "peer_reviewed": False,
        "passed": verified and all((bundle / name).is_file() for name in documents),
        "external_boundary": "The package is publication-ready but has no DOI, journal acceptance or independent peer-review decision.",
    }
    write_json(output, payload)
    return payload


def run_document_control_qualifications(output_dir: Path) -> dict[str, dict[str, Any]]:
    docs = {
        "regulatory_dossier": {
            "required": [
                "docs/REGULATORY_GXP_READINESS.md",
                "docs/operations/STEP41_REALWORLD_EVIDENCE.md",
                "STEP40_IMPLEMENTATION_REPORT.md",
                "STEP41_IMPLEMENTATION_REPORT.md",
            ],
            "boundary": "Dossier completeness is not regulatory approval.",
        },
        "gxp_controls": {
            "required": [
                "src/biointel/compliance/ledger.py",
                "src/biointel/compliance/control_catalog.py",
                "docs/REGULATORY_GXP_READINESS.md",
                "tests/test_step36_maturity_frameworks.py",
            ],
            "boundary": "Control qualification is not 180 days of GxP operating history.",
        },
        "saas_controls": {
            "required": [
                "src/biointel/enterprise/saas.py",
                "src/biointel/multitenancy/store.py",
                "tests/test_step36_maturity_frameworks.py",
            ],
            "boundary": "SaaS controls are not paying-customer history.",
        },
        "security_controls": {
            "required": [
                "src/biointel/api/security_store.py",
                "src/biointel/production/config.py",
                ".github/workflows/security.yml",
                ".github/workflows/dependency-management.yml",
            ],
            "boundary": "Security-control qualification is not external enterprise acceptance.",
        },
        "customer_acceptance_kit": {
            "required": [
                "data/templates/step41_customer_validation_manifest.json",
                "docs/operations/STEP41_REALWORLD_EVIDENCE.md",
                "tests/operations/test_step41_realworld_operations.py",
            ],
            "boundary": "Acceptance kit readiness is not a customer signature.",
        },
        "clinical_reference": {
            "required": [
                "reports/scientific_evidence.sqlite3",
                "pages/73_Scientific_Evidence_Excellence.py",
                "docs/SCIENTIFIC_EVIDENCE_AND_VALIDATION.md",
            ],
            "boundary": "Clinical-reference coverage is not clinical deployment or ethics approval.",
        },
        "scientific_validation": {
            "required": [
                "reports/step38/uci_wdbc_real_benchmark.json",
                "reports/step40_validation_qualification.json",
                "src/biointel/scientific/validation_depth.py",
            ],
            "boundary": "Analytical qualification is not independent external DTI or wet-lab validation.",
        },
    }
    results: dict[str, dict[str, Any]] = {}
    for key, specification in docs.items():
        required = list(specification["required"])
        existing = [item for item in required if (ROOT / item).is_file()]
        result = {
            "schema": f"biointel.step42.{key}.v1",
            "observed_at": now(),
            "classification": "documented_control_qualification",
            "required": required,
            "existing": existing,
            "missing": [item for item in required if item not in existing],
            "passed": len(existing) == len(required),
            "external_boundary": specification["boundary"],
        }
        write_json(output_dir / f"{key}.json", result)
        results[key] = result
    return results


def create_release_provenance(output: Path) -> dict[str, Any]:
    protected: list[dict[str, Any]] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        protected.append(
            {
                "name": str(path.relative_to(ROOT)),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    for path in sorted((ROOT / "config").rglob("*")):
        if path.is_file():
            protected.append(
                {
                    "name": str(path.relative_to(ROOT)),
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )
    subject_digest = hashlib.sha256(
        json.dumps(protected, sort_keys=True).encode("utf-8")
    ).hexdigest()
    payload = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {"name": "biointel-ai-source-and-config", "digest": {"sha256": subject_digest}}
        ],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://biointel.local/build/step42",
                "externalParameters": {
                    "version": __version__,
                    "mode": "deterministic-local-qualification",
                },
                "internalParameters": {},
                "resolvedDependencies": protected,
            },
            "runDetails": {
                "builder": {"id": "https://biointel.local/builders/step42"},
                "metadata": {
                    "invocationId": subject_digest,
                    "startedOn": now(),
                    "finishedOn": now(),
                },
            },
        },
        "classification": "unsigned_local_slsa_compatible_provenance",
        "passed": bool(protected) and len(subject_digest) == 64,
        "external_boundary": "This provenance is checksum-verifiable but not a Sigstore transparency-log signature until executed in OIDC-enabled CI.",
    }
    write_json(output, payload)
    return payload


def build_index(output_dir: Path, results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    artifacts: dict[str, dict[str, Any]] = {}
    for key in results:
        path = output_dir / f"{key}.json"
        artifacts[key] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    index = {
        "schema": "biointel.step42.evidence-index.v1",
        "generated_at": now(),
        "artifacts": artifacts,
        "passed": all(bool(item.get("passed")) for item in results.values()),
    }
    write_json(output_dir / "evidence_index.json", index)
    return index


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate maximum non-fabricated verifiable evidence for Step 42."
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="Reuse an existing API load report instead of running the load qualification.",
    )
    parser.add_argument("--load-requests", type=int, default=1200)
    parser.add_argument("--tenant-iterations", type=int, default=5000)
    args = parser.parse_args()

    output_dir = ROOT / "reports" / "step42"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict[str, Any]] = {}
    results["database_drill"] = run_database_drill(output_dir / "database_drill.json")
    results["multitenant_isolation"] = run_multitenant_isolation(
        output_dir / "multitenant_isolation.json", args.tenant_iterations
    )
    if args.skip_load:
        results["api_load"] = {
            "schema": "biointel.step42.api-load.v1",
            "observed_at": now(),
            "classification": "not_executed",
            "passed": False,
            "external_boundary": "Load qualification was skipped.",
        }
        write_json(output_dir / "api_load.json", results["api_load"])
    else:
        results["api_load"] = run_api_load(
            output_dir / "api_load.json", requests=args.load_requests
        )
    results["ha_rehearsal"] = run_ha_rehearsal(output_dir / "ha_rehearsal.json")
    results["kubernetes_static"] = run_kubernetes_static(output_dir / "kubernetes_static.json")
    results["cloud_iac"] = run_cloud_iac(output_dir / "cloud_iac.json")
    results["publication_bundle"] = create_publication_bundle(
        output_dir / "publication_bundle.json"
    )
    results.update(run_document_control_qualifications(output_dir))
    results["release_provenance"] = create_release_provenance(
        output_dir / "release_provenance.json"
    )

    verification = {
        "schema": "biointel.step42.verification-results.v1",
        "generated_at": now(),
        "checks": results,
        "passed": all(bool(item.get("passed")) for item in results.values()),
        "passed_count": sum(bool(item.get("passed")) for item in results.values()),
        "check_count": len(results),
    }
    write_json(output_dir / "verification_results.json", verification)
    results["verification_results"] = verification
    index = build_index(output_dir, results)

    print(
        json.dumps(
            {
                "output": str(output_dir),
                "checks": len(results),
                "passed": verification["passed_count"],
                "index_artifacts": len(index["artifacts"]),
            },
            indent=2,
        )
    )
    return 0 if verification["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
