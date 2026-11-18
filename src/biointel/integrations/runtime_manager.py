from __future__ import annotations

"""Audited execution layer for BioIntel scientific integrations.

Normal product surfaces receive only BioIntel public identities. Internal package,
repository and executable identifiers remain confined to protected diagnostics and
legally required component notices.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence

from biointel.tools.runtime import resolve_tool, run_tool_audited

ROOT = Path(__file__).resolve().parents[3]
WORKER = ROOT / "scripts" / "biointel_scientific_worker.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_root() -> Path:
    explicit = os.environ.get("BIOINTEL_SCIENTIFIC_RUNTIME_ROOT", "").strip()
    if explicit:
        return Path(os.path.expandvars(explicit)).expanduser()
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        return Path(local) / "BioIntelAI" / "ScientificRuntimes"
    return Path.home() / ".biointel" / "scientific-runtimes"


def user_data_root() -> Path:
    explicit = os.environ.get("BIOINTEL_USER_DATA_DIR", "").strip()
    if explicit:
        return Path(os.path.expandvars(explicit)).expanduser()
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        return Path(local) / "BioIntelAI" / "UserData"
    return Path.home() / ".biointel" / "user-data"


def runtime_state_path() -> Path:
    return runtime_root() / "state" / "runtime-state.json"


def load_runtime_state() -> dict[str, Any]:
    path = runtime_state_path()
    if not path.is_file():
        return {"schema": "biointel.scientific-runtime-state.v2", "profiles": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": "biointel.scientific-runtime-state.v2", "profiles": {}}
    return payload if isinstance(payload, dict) else {"profiles": {}}


def _profile_state(profile_id: str) -> dict[str, Any]:
    profiles = load_runtime_state().get("profiles", {})
    if isinstance(profiles, dict):
        value = profiles.get(profile_id, {})
        return value if isinstance(value, dict) else {}
    return {}


def runtime_python(profile_id: str) -> Path | None:
    if profile_id == "core":
        return Path(sys.executable)
    state = _profile_state(profile_id)
    explicit = str(state.get("python", "")).strip()
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(os.path.expandvars(explicit)).expanduser())
    root = runtime_root()
    candidates.extend(
        [
            root / "mamba" / "envs" / profile_id / "python.exe",
            root / "mamba" / "envs" / profile_id / "bin" / "python",
            root / "profiles" / profile_id / "Scripts" / "python.exe",
            root / "profiles" / profile_id / "bin" / "python",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def python_probe(profile_id: str, modules: Sequence[str], distributions: Sequence[str] = ()) -> dict[str, Any]:
    interpreter = runtime_python(profile_id)
    if interpreter is None:
        return {"available": False, "detected": 0, "required": len(modules), "version": None, "detail": "Runtime not installed"}
    if not modules:
        return {"available": True, "detected": 1, "required": 1, "version": None, "detail": "Runtime interpreter detected"}
    script = (
        "import importlib.util,importlib.metadata,json;"
        f"mods={list(modules)!r};dists={list(distributions)!r};"
        "ready=[importlib.util.find_spec(x) is not None for x in mods];"
        "version=None;"
        "\nfor d in dists:\n"
        "  try:\n    version=importlib.metadata.version(d);break\n  except importlib.metadata.PackageNotFoundError:\n    pass\n"
        "print(json.dumps({'ready':ready,'version':version}))"
    )
    try:
        completed = subprocess.run(
            [str(interpreter), "-c", script],
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
        payload = json.loads((completed.stdout or "{}").strip().splitlines()[-1]) if completed.stdout else {}
        ready = [bool(value) for value in payload.get("ready", [])]
        detected = sum(ready)
        required = len(modules)
        return {
            "available": completed.returncode == 0 and detected == required,
            "detected": detected,
            "required": required,
            "version": payload.get("version"),
            "detail": "Runtime probe completed" if completed.returncode == 0 else "Runtime probe failed",
        }
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, IndexError):
        return {"available": False, "detected": 0, "required": len(modules), "version": None, "detail": "Runtime probe failed safely"}


@dataclass(frozen=True)
class IntegrationRunResult:
    schema: str
    run_id: str
    public_key: str
    name: str
    priority: str
    operation: str
    status: str
    started_at: str
    finished_at: str
    duration_seconds: float
    metrics: Mapping[str, Any]
    artifacts: tuple[Mapping[str, Any], ...]
    qualification: str
    internal_manifest: str
    message: str

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


def _artifact_records(paths: Sequence[str | Path]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for value in paths:
        path = Path(value)
        if path.is_file():
            rows.append({"name": path.name, "size_bytes": path.stat().st_size, "sha256": _sha256(path)})
    return tuple(rows)


def _safe_run_dir(public_key: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    token = hashlib.sha256(os.urandom(32)).hexdigest()[:10]
    path = user_data_root() / "scientific_runs" / public_key / f"{stamp}-{token}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _worker_execution(spec: Any, operation: str, payload: Mapping[str, Any], run_dir: Path) -> tuple[int, dict[str, Any], Path, Path]:
    interpreter = runtime_python(spec.runtime_profile)
    if interpreter is None:
        raise RuntimeError("BioIntel scientific runtime is not installed for this integration.")
    request_path = run_dir / "request.internal.json"
    result_path = run_dir / "result.internal.json"
    stdout_path = run_dir / "worker.stdout.log"
    stderr_path = run_dir / "worker.stderr.log"
    request_path.write_text(
        json.dumps(
            {
                "schema": "biointel.integration-worker-request.v2",
                "integration_id": spec.integration_id,
                "operation": operation,
                "payload": dict(payload),
                "output_dir": str(run_dir / "artifacts"),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    env["BIOINTEL_INTEGRATION_WORKER"] = "1"
    started = time.monotonic()
    completed = subprocess.run(
        [str(interpreter), str(WORKER), "--request", str(request_path), "--result", str(result_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=spec.timeout_seconds,
        check=False,
        env=env,
    )
    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")
    if result_path.is_file():
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result = {"status": "failed", "message": "Worker returned an unreadable result", "metrics": {}, "artifacts": []}
    else:
        result = {"status": "failed", "message": "Worker did not produce a result", "metrics": {}, "artifacts": []}
    result["worker_seconds"] = round(time.monotonic() - started, 4)
    return completed.returncode, result, stdout_path, stderr_path


def _required(payload: Mapping[str, Any], name: str) -> str:
    value = str(payload.get(name, "")).strip()
    if not value:
        raise ValueError(f"Required BioIntel input is missing: {name}")
    return value


def _cli_arguments(integration_id: str, operation: str, payload: Mapping[str, Any], run_dir: Path) -> tuple[str, list[str]]:
    if integration_id == "molecular_docking":
        receptor = _required(payload, "receptor_path")
        ligand = _required(payload, "ligand_path")
        output = str(run_dir / "artifacts" / "biointel_docking_output.pdbqt")
        args = ["--receptor", receptor, "--ligand", ligand, "--out", output]
        if payload.get("config_path"):
            args.extend(["--config", str(payload["config_path"])])
        if operation == "score_only":
            args.append("--score_only")
        return "vina", args
    if integration_id == "taxonomy_classification":
        database = _required(payload, "database_path")
        if operation == "database_check":
            return "kraken2-inspect", ["--db", database]
        reads = payload.get("read_paths") or []
        if isinstance(reads, str):
            reads = [reads]
        if not reads:
            raise ValueError("At least one read file is required.")
        report = str(run_dir / "artifacts" / "biointel_taxonomy_report.tsv")
        output = str(run_dir / "artifacts" / "biointel_taxonomy_assignments.txt")
        args = ["--db", database, "--report", report, "--output", output]
        if len(reads) == 2:
            args.append("--paired")
        args.extend(map(str, reads))
        return "kraken2", args
    if integration_id == "protein_design":
        input_path = _required(payload, "input_path")
        output_dir = str(run_dir / "artifacts")
        args = ["--pdb_path", input_path, "--out_folder", output_dir]
        if payload.get("num_sequences"):
            args.extend(["--num_seq_per_target", str(int(payload["num_sequences"]))])
        if operation == "score_sequence" and payload.get("fasta_path"):
            args.extend(["--score_only", "1", "--path_to_fasta", str(payload["fasta_path"])])
        return "proteinmpnn", args
    if integration_id == "workflow_automation":
        workflow = _required(payload, "workflow_path")
        args = ["--snakefile", workflow, "--cores", str(int(payload.get("cores", 1)))]
        if operation == "dry_run":
            args.append("--dry-run")
        if payload.get("configfile"):
            args.extend(["--configfile", str(payload["configfile"])])
        return "snakemake", args
    if integration_id == "pipeline_execution":
        if operation == "pipeline_catalog":
            return "nf-core", ["pipelines", "list", "--json"]
        public_aliases = {
            "biointel/rnaseq": "nf-core/rnaseq",
            "biointel/sarek": "nf-core/sarek",
            "biointel/ampliseq": "nf-core/ampliseq",
            "biointel/mag": "nf-core/mag",
        }
        pipeline_value = str(_required(payload, "pipeline"))
        pipeline = public_aliases.get(pipeline_value.casefold(), pipeline_value)
        if operation == "download_pipeline":
            output_dir = str(run_dir / "artifacts" / "pipeline_bundle")
            return "nf-core", ["pipelines", "download", pipeline, "--outdir", output_dir]
        work_dir = str(run_dir / "work")
        output_dir = str(run_dir / "artifacts")
        args = ["run", pipeline, "-work-dir", work_dir, "--outdir", output_dir]
        if payload.get("profile"):
            args.extend(["-profile", str(payload["profile"])])
        if payload.get("params_file"):
            args.extend(["-params-file", str(payload["params_file"])])
        return "nextflow", args
    raise ValueError("This BioIntel integration does not expose a CLI operation.")


def execute_integration(
    integration_id: str,
    operation: str,
    payload: Mapping[str, Any] | None = None,
) -> IntegrationRunResult:
    from biointel.integrations.scientific_components import integration_catalog

    payload = payload or {}
    specs = {item.integration_id: item for item in integration_catalog()}
    if integration_id not in specs:
        raise KeyError(f"Unknown BioIntel integration: {integration_id}")
    spec = specs[integration_id]
    if operation not in spec.operations:
        raise ValueError("Requested operation is not registered for this BioIntel integration.")
    run_dir = _safe_run_dir(spec.public_key)
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    started = time.monotonic()
    status = "failed"
    message = "BioIntel integration run failed safely."
    metrics: dict[str, Any] = {}
    artifact_paths: list[str | Path] = []
    internal_details: dict[str, Any] = {
        "schema": "biointel.integration-internal-manifest.v2",
        "run_id": run_dir.name,
        "integration_id": spec.integration_id,
        "operation": operation,
        "priority": spec.priority,
        "runtime_profile": spec.runtime_profile,
        "backend": spec.backend,
        "started_at": started_at,
    }
    try:
        if spec.backend in {"main_python", "isolated_python"}:
            returncode, worker_result, stdout_path, stderr_path = _worker_execution(spec, operation, payload, run_dir)
            internal_details.update({"returncode": returncode, "stdout": str(stdout_path), "stderr": str(stderr_path), "worker": worker_result})
            status = "completed" if returncode == 0 and worker_result.get("status") == "completed" else "failed"
            message = str(worker_result.get("message", "BioIntel operation completed." if status == "completed" else "BioIntel operation failed safely."))
            metrics = dict(worker_result.get("metrics", {}))
            artifact_paths.extend(worker_result.get("artifacts", []))
        elif spec.backend == "desktop_companion":
            interpreter = runtime_python(spec.runtime_profile)
            if interpreter is None:
                raise RuntimeError("BioIntel imaging workspace is not installed.")
            if operation == "viewer_diagnostic":
                returncode, worker_result, stdout_path, stderr_path = _worker_execution(spec, operation, payload, run_dir)
                internal_details.update({"returncode": returncode, "stdout": str(stdout_path), "stderr": str(stderr_path), "worker": worker_result})
                status = "completed" if returncode == 0 and worker_result.get("status") == "completed" else "failed"
                message = str(worker_result.get("message", "BioIntel imaging diagnostic completed."))
                metrics = dict(worker_result.get("metrics", {}))
            else:
                input_path = _required(payload, "input_path")
                process = subprocess.Popen(
                    [str(interpreter), "-m", "napari", input_path],
                    cwd=str(Path(input_path).expanduser().resolve().parent),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env={**os.environ, "PYTHONNOUSERSITE": "1"},
                )
                status = "completed"
                message = "BioIntel imaging workspace launched."
                metrics = {"process_started": True, "process_id": process.pid}
                internal_details["process_id"] = process.pid
        else:
            if operation == "technical_diagnostic":
                tool_id = spec.tool_ids[0] if spec.tool_ids else ""
                resolution = resolve_tool(tool_id) if tool_id else None
                if not resolution or not resolution.available:
                    raise RuntimeError("BioIntel specialist runtime is not installed.")
                from biointel.tools.runtime import tool_version

                status = "completed"
                message = "BioIntel specialist runtime diagnostic passed."
                metrics = {"runtime_available": True, "backend": resolution.backend, "runtime_version": tool_version(tool_id)}
                internal_details["tool_resolution"] = resolution.to_dict()
            else:
                tool, arguments = _cli_arguments(spec.integration_id, operation, payload, run_dir)
                result = run_tool_audited(tool, arguments, run_directory=run_dir / "engine", timeout_seconds=spec.timeout_seconds)
                internal_details["tool_execution"] = result.to_dict()
                status = "completed" if result.returncode == 0 else "failed"
                message = "BioIntel specialist engine completed." if status == "completed" else "BioIntel specialist engine returned a controlled failure."
                metrics = {"exit_code": result.returncode, "duration_seconds": result.duration_seconds, "backend": result.backend}
                artifact_paths.extend(path for path in (run_dir / "artifacts").rglob("*") if path.is_file())
    except subprocess.TimeoutExpired as exc:
        internal_details["error"] = {"type": type(exc).__name__, "message": str(exc)}
        status = "timed_out"
        message = "BioIntel stopped the operation after the configured timeout."
    except Exception as exc:  # fail-safe boundary for optional scientific runtimes
        internal_details["error"] = {"type": type(exc).__name__, "message": str(exc)}
        status = "failed"
        message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "BioIntel integration failed safely. Review protected diagnostics."

    finished_at = utc_now()
    duration = round(time.monotonic() - started, 4)
    internal_details.update({"finished_at": finished_at, "duration_seconds": duration, "status": status})
    manifest_path = run_dir / "internal-manifest.json"
    manifest_path.write_text(json.dumps(internal_details, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    artifacts = _artifact_records(artifact_paths)
    return IntegrationRunResult(
        schema="biointel.integration-run.public.v2",
        run_id=run_dir.name,
        public_key=spec.public_key,
        name=spec.public_name,
        priority=spec.priority,
        operation=operation,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration,
        metrics=metrics,
        artifacts=artifacts,
        qualification="Research-use technical execution; scientific, clinical and regulatory qualification remains module-specific.",
        internal_manifest=str(manifest_path),
        message=message,
    )
