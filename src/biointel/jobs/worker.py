from __future__ import annotations

from biointel.runtime_paths import runtime_database_path, runtime_report_path

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from biointel.chemistry.admet import profile_admet, profile_dict
from biointel.bioinformatics_peak_v138.scientific import analyse_module
from biointel.bioinformatics_peak_v138.catalog import MODULE_BY_KEY as BIOINFORMATICS_PEAK_MODULES
from biointel.database.core import optimize_database
from biointel.discovery.preparation import preparation_dict, prepare_molecular_states
from biointel.integrations.public_sync import sync_chembl_activities, sync_uniprot_reviewed
from biointel.intelligence.data_intelligence import database_paths
from biointel.jobs.local_queue import JobRecord, LocalJobQueue
from biointel.native.engines import build_engine_plan, execute_engine_plan, plan_to_dict, run_to_dict
from biointel.neuro_cns.jobs import execute_neuro_job_payload
from biointel.native.formats import parse_native_path
from biointel.nextgen.native_execution_v136 import execute_native_pipeline_job
from biointel.step101.reference_lifecycle import ReferenceLifecycleManager
from biointel.step101.reports import UnifiedScientificReportBuilder
from biointel.step101.ui_regression import run_ui_regression
from biointel.step101.performance import audit_ui_source
from biointel.utils.diagnostics import diagnostic_summary, run_diagnostics


class JobPaused(RuntimeError):
    def __init__(self, checkpoint: dict[str, Any] | None = None):
        super().__init__("Job paused")
        self.checkpoint = checkpoint or {}


class JobCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkerRunResult:
    processed: bool
    job_id: str | None
    job_type: str | None
    status: str
    message: str


class LocalWorker:
    """Dependency-light local worker for supported BioIntel background jobs.

    The worker only claims job types it knows how to execute, so historical/demo queue
    records are never accidentally processed by a new release.
    """

    def __init__(self, project_root: str | Path, *, worker_id: str = "local-worker") -> None:
        self.root = Path(project_root).resolve()
        self.worker_id = worker_id
        self.queue = LocalJobQueue(runtime_database_path(self.root, "jobs.sqlite3"))
        self.handlers: dict[str, Callable[[JobRecord], dict[str, Any]]] = {
            "scientific_sync_chembl": self._sync_chembl,
            "scientific_sync_uniprot": self._sync_uniprot,
            "database_optimize": self._optimize_databases,
            "system_diagnostics": self._diagnostics,
            "discovery_batch_triage": self._discovery_batch_triage,
            "ui_regression_run": self._ui_regression_run,
            "unified_report_generate": self._unified_report_generate,
            "reference_asset_verify": self._reference_asset_verify,
            "ui_performance_audit": self._ui_performance_audit,
            "scientific_large_file_inspect": self._scientific_large_file_inspect,
            "native_format_parse": self._native_format_parse,
            "native_engine_execute": self._native_engine_execute,
            "nextgen_native_pipeline": self._nextgen_native_pipeline,
            "bioinformatics_peak_analysis_v138": self._bioinformatics_peak_analysis_v138,
            "neuro_cns_analysis": self._neuro_cns_analysis,
        }

    def _control(self, job: JobRecord, checkpoint: dict[str, Any] | None = None) -> None:
        state = self.queue.control_state(job.job_id)
        self.queue.heartbeat_job(job.job_id, worker_id=self.worker_id)
        if state["cancel_requested"]:
            raise JobCancelled("Job cancelled")
        if state["pause_requested"]:
            raise JobPaused(checkpoint)

    def _sync_chembl(self, job: JobRecord) -> dict[str, Any]:
        payload = job.payload
        self.queue.update_progress(job.job_id, progress_percent=15, stage="prepare", message="Validating ChEMBL sync options")
        result = sync_chembl_activities(
            self.root,
            maximum_records=int(payload.get("maximum_records", 1000)),
            organism=str(payload.get("organism", "Homo sapiens")),
        )
        self.queue.update_progress(job.job_id, progress_percent=90, stage="validate", message="ChEMBL payload stored and checksummed")
        return asdict(result)

    def _sync_uniprot(self, job: JobRecord) -> dict[str, Any]:
        payload = job.payload
        self.queue.update_progress(job.job_id, progress_percent=15, stage="prepare", message="Validating UniProt sync options")
        result = sync_uniprot_reviewed(
            self.root,
            maximum_records=int(payload.get("maximum_records", 1000)),
            organism_id=int(payload.get("organism_id", 9606)),
        )
        self.queue.update_progress(job.job_id, progress_percent=90, stage="validate", message="UniProt payload stored and checksummed")
        return asdict(result)

    def _optimize_databases(self, job: JobRecord) -> dict[str, Any]:
        paths = database_paths(self.root)
        selected = job.payload.get("databases") or list(paths)
        output: dict[str, Any] = {}
        total = max(len(selected), 1)
        for index, key in enumerate(selected, 1):
            if key not in paths:
                output[str(key)] = {"status": "skipped", "reason": "unknown database"}
                continue
            self.queue.update_progress(
                job.job_id,
                progress_percent=10 + 75 * index / total,
                stage="execute",
                message=f"Optimizing {key}",
            )
            output[key] = optimize_database(paths[key])
        return output

    def _diagnostics(self, job: JobRecord) -> dict[str, Any]:
        self.queue.update_progress(job.job_id, progress_percent=30, stage="execute", message="Running platform diagnostics")
        checks = run_diagnostics(self.root)
        return {
            "summary": diagnostic_summary(checks),
            "checks": [check.to_dict() for check in checks],
        }

    def _discovery_batch_triage(self, job: JobRecord) -> dict[str, Any]:
        payload = job.payload
        rows = list(payload.get("rows") or [])
        mode = str(payload.get("preparation_mode", "neutral_parent"))
        ph = payload.get("ph")
        deduplicate = bool(payload.get("deduplicate", True))
        results: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        total = max(len(rows), 1)
        seen: set[str] = set()
        for index, row in enumerate(rows, start=1):
            self._control(job, {"next_row": index, "profiles": len(results), "failures": len(failures)})
            try:
                preparation = prepare_molecular_states(
                    str(row.get("smiles", "")), mode=mode, ph=ph
                )
                profile = profile_dict(profile_admet(preparation.standardized_parent_smiles))
                identity = str(profile.get("inchikey") or profile["standardized_smiles"])
                if deduplicate and identity in seen:
                    continue
                seen.add(identity)
                results.append(
                    {
                        "source_row": index,
                        "compound_id": row.get("compound_id") or f"row_{index}",
                        **profile,
                        "molecular_preparation": preparation_dict(preparation),
                    }
                )
            except Exception as exc:
                failures.append(
                    {
                        "source_row": index,
                        "compound_id": row.get("compound_id"),
                        "smiles": row.get("smiles"),
                        "error": str(exc),
                    }
                )
            if index == 1 or index == len(rows) or index % max(1, len(rows) // 20) == 0:
                self.queue.update_progress(
                    job.job_id,
                    progress_percent=5 + 85 * index / total,
                    stage="execute",
                    message=f"Profiled {index}/{len(rows)} molecules",
                )
        return {
            "profiles": results,
            "failures": failures,
            "profile_count": len(results),
            "failure_count": len(failures),
            "deduplicated": deduplicate,
        }

    def _ui_regression_run(self, job: JobRecord) -> dict[str, Any]:
        payload = job.payload
        self._control(job, {"stage": "starting"})
        self.queue.update_progress(job.job_id, progress_percent=10, stage="discover", message="Discovering Streamlit pages")
        result = run_ui_regression(
            self.root,
            mode=str(payload.get("mode", "static")),
            selected_pages=payload.get("selected_pages") or None,
            timeout_seconds=int(payload.get("timeout_seconds", 30)),
            output_dir=runtime_report_path(self.root, "ui_regression"),
        )
        self.queue.update_progress(job.job_id, progress_percent=95, stage="finalize", message="UI regression artifacts generated")
        return result

    def _unified_report_generate(self, job: JobRecord) -> dict[str, Any]:
        payload = job.payload
        self._control(job, {"stage": "collect"})
        self.queue.update_progress(job.job_id, progress_percent=15, stage="collect", message="Collecting workspace evidence")
        builder = UnifiedScientificReportBuilder(self.root)
        bundle = builder.build(
            title=str(payload.get("title", "BioIntel AI Unified Scientific Report")),
            notes=str(payload.get("notes", "")),
            reviewer=str(payload.get("reviewer", "")),
            sections=payload.get("sections") or None,
        )
        directory = runtime_report_path(self.root, "generated")
        directory.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in bundle.title)[:80] or "scientific_report"
        path = directory / f"{safe}-{job.job_id[-8:]}.zip"
        path.write_bytes(bundle.zip_bytes())
        self.queue.update_progress(job.job_id, progress_percent=95, stage="finalize", message="Report bundle written")
        return {"bundle_path": str(path.relative_to(self.root)), "size_bytes": path.stat().st_size, "manifest": bundle.manifest}

    def _reference_asset_verify(self, job: JobRecord) -> dict[str, Any]:
        asset_root = Path(os.environ.get("BIOINTEL_REFERENCE_ASSETS_DIR") or self.root / "data" / "reference_assets")
        manager = ReferenceLifecycleManager(asset_root)
        asset_id = str(job.payload.get("asset_id", ""))
        self.queue.update_progress(job.job_id, progress_percent=20, stage="verify", message=f"Verifying {asset_id}")
        self._control(job, {"asset_id": asset_id})
        return manager.verify_installed(asset_id)

    def _ui_performance_audit(self, job: JobRecord) -> dict[str, Any]:
        self.queue.update_progress(job.job_id, progress_percent=25, stage="scan", message="Auditing page performance structure")
        self._control(job, {"stage": "scan"})
        result = audit_ui_source(self.root)
        output = runtime_report_path(self.root, "ui_performance_audit.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return {**result, "artifact": str(output.relative_to(self.root))}

    def _scientific_large_file_inspect(self, job: JobRecord) -> dict[str, Any]:
        payload = job.payload
        source = Path(str(payload.get("path", ""))).expanduser().resolve()
        user_root = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or self.root / "UserData").resolve()
        allowed = (user_root / "staged_uploads").resolve()
        try:
            source.relative_to(allowed)
        except ValueError as exc:
            raise ValueError("Large-file job path is outside the protected staging directory") from exc
        if not source.is_file():
            raise FileNotFoundError(source)
        size = source.stat().st_size
        if size > 1024 * 1024 * 1024:
            raise ValueError("Staged file exceeds the 1 GB limit")
        self.queue.update_progress(job.job_id, progress_percent=10, stage="verify_path", message="Validated staged file path and size")
        digest = hashlib.sha256()
        sampled = bytearray()
        newline_count = 0
        processed = 0
        with source.open("rb") as handle:
            while True:
                self._control(job, {"processed_bytes": processed})
                chunk = handle.read(4 * 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                newline_count += chunk.count(b"\n")
                if len(sampled) < 4 * 1024 * 1024:
                    sampled.extend(chunk[: 4 * 1024 * 1024 - len(sampled)])
                processed += len(chunk)
                self.queue.update_progress(
                    job.job_id,
                    progress_percent=min(85.0, 15.0 + 70.0 * processed / max(size, 1)),
                    stage="stream_hash",
                    message=f"Stream-verified {processed / 1024 / 1024:.1f} MB",
                )
        sample = bytes(sampled)
        null_fraction = sample.count(b"\x00") / max(len(sample), 1)
        text_like = null_fraction < 0.01
        self.queue.update_progress(job.job_id, progress_percent=92, stage="sample", message="Created bounded file profile")
        return {
            "module_key": str(payload.get("module_key", "")),
            "original_name": str(payload.get("original_name", source.name)),
            "path": str(source),
            "size_bytes": size,
            "sha256": digest.hexdigest(),
            "extension": source.suffix.lower(),
            "sample_bytes": len(sample),
            "sample_is_text_like": text_like,
            "sample_null_fraction": null_fraction,
            "newline_count": newline_count if text_like else None,
            "status": "validated_for_module_specific_background_processing",
        }

    def _native_format_parse(self, job: JobRecord) -> dict[str, Any]:
        payload = job.payload
        source = Path(str(payload.get("path", ""))).expanduser().resolve()
        user_root = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or self.root / "UserData").resolve()
        allowed = (user_root / "staged_uploads").resolve()
        try:
            source.relative_to(allowed)
        except ValueError as exc:
            raise ValueError("Native parser path is outside the protected staging directory") from exc
        if not source.is_file():
            raise FileNotFoundError(source)
        self.queue.update_progress(job.job_id, progress_percent=10, stage="detect", message="Detecting native scientific format")
        self._control(job, {"stage": "detect"})
        result = parse_native_path(
            source,
            preferred_viewer=str(payload.get("viewer_key", "")) or None,
            max_records=max(1000, min(int(payload.get("max_records", 100000)), 500000)),
            format_key=str(payload.get("format_key", "")) or None,
        )
        self.queue.update_progress(job.job_id, progress_percent=75, stage="parse", message=f"Decoded {result.record_count:,} bounded preview records")
        output_dir = user_root / "native_results" / job.job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        preview_path = output_dir / "primary_preview.csv.gz"
        result.primary.to_csv(preview_path, index=False, compression="gzip")
        secondary_files: dict[str, str] = {}
        for key, frame in result.secondary.items():
            path = output_dir / f"{key}.csv.gz"
            frame.to_csv(path, index=False, compression="gzip")
            secondary_files[key] = str(path)
        summary = result.summary()
        summary.pop("preview_array", None)
        summary_path = output_dir / "native_parse_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8")
        self.queue.update_progress(job.job_id, progress_percent=95, stage="finalize", message="Native parser artifacts written with provenance")
        return {
            "summary": summary,
            "primary_preview": str(preview_path),
            "secondary_files": secondary_files,
            "summary_path": str(summary_path),
        }

    def _nextgen_native_pipeline(self, job: JobRecord) -> dict[str, Any]:
        def progress(percent: float, stage: str, message: str) -> None:
            self.queue.update_progress(
                job.job_id,
                progress_percent=max(0.0, min(float(percent), 100.0)),
                stage=stage,
                message=message,
            )

        def control(checkpoint: dict[str, Any]) -> None:
            self._control(job, checkpoint)

        return execute_native_pipeline_job(
            self.root,
            job.payload,
            job_id=job.job_id,
            progress=progress,
            control=control,
        )

    def _native_engine_execute(self, job: JobRecord) -> dict[str, Any]:
        payload = job.payload
        user_root = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or self.root / "UserData").resolve()
        allowed = (user_root / "native_engine_workspace").resolve()
        allowed.mkdir(parents=True, exist_ok=True)
        workdir = Path(str(payload.get("workdir", allowed))).expanduser().resolve()
        try:
            workdir.relative_to(allowed)
        except ValueError as exc:
            raise ValueError("Native-engine work directory is outside the protected workspace") from exc
        self.queue.update_progress(job.job_id, progress_percent=10, stage="plan", message="Validating external scientific-engine plan")
        self._control(job, {"stage": "plan"})
        plan = build_engine_plan(str(payload.get("plan_key", "")), workdir=workdir, **dict(payload.get("parameters") or {}))
        self.queue.update_progress(job.job_id, progress_percent=25, stage="execute", message=f"Executing {plan.engine_key} without a shell")
        run = execute_engine_plan(
            plan,
            timeout_seconds=max(10, min(int(payload.get("timeout_seconds", 3600)), 86400)),
            stdout_to_output=bool(payload.get("stdout_to_output", False)),
        )
        if run.return_code != 0:
            raise RuntimeError(f"External engine exited with code {run.return_code}: {run.stderr[-1000:]}")
        self.queue.update_progress(job.job_id, progress_percent=95, stage="validate", message="External engine outputs checksummed")
        return {"plan": plan_to_dict(plan), "run": run_to_dict(run)}

    def _bioinformatics_peak_analysis_v138(self, job: JobRecord) -> dict[str, Any]:
        payload = job.payload
        module_key = str(payload.get("module_key", ""))
        if module_key not in BIOINFORMATICS_PEAK_MODULES:
            raise KeyError(f"Unknown Step 138 bioinformatics module: {module_key}")
        user_root = Path(os.environ.get("BIOINTEL_USER_DATA_DIR") or self.root / "UserData").resolve()
        allowed = (user_root / "staged_uploads" / "bioinformatics_peak_v138").resolve()
        source = Path(str(payload.get("path", ""))).expanduser().resolve()
        try:
            source.relative_to(allowed)
        except ValueError as exc:
            raise ValueError("Step 138 background input is outside the protected staging directory") from exc
        if not source.is_file():
            raise FileNotFoundError(source)
        self.queue.update_progress(job.job_id, progress_percent=8, stage="verify", message="Verifying staged scientific input")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        expected = str(payload.get("sha256", ""))
        if expected and digest.lower() != expected.lower():
            raise ValueError("Staged input checksum mismatch")
        self._control(job, {"stage": "verified", "sha256": digest})

        self.queue.update_progress(job.job_id, progress_percent=20, stage="parse", message="Reading bounded scientific table")
        frame = pd.read_csv(source, compression="gzip", nrows=250_000, low_memory=False)
        if frame.empty:
            raise ValueError("The staged scientific table is empty")
        parameters = dict(payload.get("parameters") or {})
        threshold = float(parameters.get("priority_threshold", 0.70))
        self._control(job, {"stage": "parsed", "rows": len(frame), "columns": len(frame.columns)})

        self.queue.update_progress(job.job_id, progress_percent=45, stage="analyse", message="Running deep bioinformatics analysis")
        bundle = analyse_module(frame, module_key, threshold=threshold, parameters=parameters)
        self._control(job, {"stage": "analysed", "result_rows": len(bundle.result)})

        self.queue.update_progress(job.job_id, progress_percent=78, stage="export", message="Writing reproducibility artifacts")
        output_dir = user_root / "bioinformatics_peak_results" / job.job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        result_path = output_dir / "result.csv.gz"
        quality_path = output_dir / "quality_gates.csv"
        summary_path = output_dir / "summary.json"
        bundle.result.to_csv(result_path, index=False, compression="gzip")
        bundle.quality.to_csv(quality_path, index=False)
        summary_path.write_text(json.dumps(bundle.summary, indent=2, sort_keys=True, default=str), encoding="utf-8")
        table_paths: dict[str, str] = {}
        for name, table in bundle.extras.items():
            if not isinstance(table, pd.DataFrame):
                continue
            path = output_dir / f"{name}.csv.gz"
            table.head(250_000).to_csv(path, index=False, compression="gzip")
            table_paths[name] = str(path)
        output_manifest = {
            "schema": "biointel.bioinformatics_peak.background_result.v138",
            "module_key": module_key,
            "source_sha256": digest,
            "source_rows_read": len(frame),
            "result_rows": len(bundle.result),
            "quality_status": bundle.summary.get("quality_status"),
            "result_path": str(result_path),
            "quality_path": str(quality_path),
            "summary_path": str(summary_path),
            "table_paths": table_paths,
            "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
        }
        manifest_path = output_dir / "result_manifest.json"
        manifest_path.write_text(json.dumps(output_manifest, indent=2, sort_keys=True, default=str), encoding="utf-8")
        self.queue.update_progress(job.job_id, progress_percent=95, stage="validate", message="Validating background result artifacts")
        return {**output_manifest, "manifest_path": str(manifest_path)}

    def _persist_result_artifact(self, job: JobRecord, result: dict[str, Any]) -> dict[str, Any]:
        directory = runtime_report_path(self.root, "job_artifacts")
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / f"{job.job_id}.json"
        output.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        try:
            relative_path = output.relative_to(self.root).as_posix()
        except ValueError:
            user_data_root = self.queue.path.parent.parent if self.queue.path.parent.name == "databases" else self.queue.path.parent
            try:
                relative_path = output.relative_to(user_data_root).as_posix()
            except ValueError:
                relative_path = f"job_artifacts/{output.name}"
        return self.queue.add_artifact(
            job.job_id,
            artifact_type="job_result_json",
            relative_path=relative_path,
            sha256=digest,
            size_bytes=output.stat().st_size,
            metadata={"job_type": job.job_type, "generated_by": self.worker_id},
        )


    def _neuro_cns_analysis(self, job: JobRecord) -> dict[str, Any]:
        self.queue.update_progress(job.job_id, progress_percent=10, stage="validate_input", message="Validating Neuro/CNS background payload")
        self._control(job, {"stage": "validate_input"})
        self.queue.update_progress(job.job_id, progress_percent=25, stage="execute_neuro_engine", message="Running Neuro/CNS engine")
        result = execute_neuro_job_payload(job.payload)
        self._control(job, {"stage": "quality_checks"})
        self.queue.update_progress(job.job_id, progress_percent=90, stage="quality_checks", message="Neuro/CNS result serialized and bounded")
        return result

    def run_once(self) -> WorkerRunResult:
        self.queue.heartbeat(
            self.worker_id,
            status="online",
            capabilities={"job_types": sorted(self.handlers)},
            metadata={"runner": "biointel.jobs.worker.LocalWorker"},
        )
        job: JobRecord | None = None
        for job_type in self.handlers:
            job = self.queue.claim_next(job_type=job_type, worker_id=self.worker_id)
            if job is not None:
                break
        if job is None:
            return WorkerRunResult(False, None, None, "idle", "No supported queued job is available.")
        if job.cancel_requested:
            self.queue.request_cancel(job.job_id)
            return WorkerRunResult(True, job.job_id, job.job_type, "cancelled", "Job was cancelled before execution.")
        try:
            self.queue.update_progress(job.job_id, progress_percent=5, stage="prepare", message="Worker started job")
            result = self.handlers[job.job_type](job)
            self._persist_result_artifact(job, result)
            completed = self.queue.complete(job.job_id, result)
            self.queue.heartbeat(self.worker_id, status="online", current_job_id=None, capabilities={"job_types": sorted(self.handlers)})
            return WorkerRunResult(True, completed.job_id, completed.job_type, completed.status, "Job completed successfully.")
        except JobPaused as exc:
            paused = self.queue.mark_paused(job.job_id, checkpoint=exc.checkpoint)
            self.queue.heartbeat(self.worker_id, status="online", current_job_id=None, capabilities={"job_types": sorted(self.handlers)})
            return WorkerRunResult(True, paused.job_id, paused.job_type, paused.status, "Job paused at a safe checkpoint.")
        except JobCancelled as exc:
            cancelled = self.queue.fail(job.job_id, str(exc), retry=False)
            self.queue.heartbeat(self.worker_id, status="online", current_job_id=None, capabilities={"job_types": sorted(self.handlers)})
            return WorkerRunResult(True, cancelled.job_id, cancelled.job_type, cancelled.status, str(exc))
        except Exception as exc:
            failed = self.queue.fail(job.job_id, str(exc), retry=True)
            self.queue.heartbeat(self.worker_id, status="degraded", current_job_id=None, capabilities={"job_types": sorted(self.handlers)}, metadata={"last_error": str(exc)[:500]})
            return WorkerRunResult(True, failed.job_id, failed.job_type, failed.status, str(exc))

    def run_forever(self, *, poll_seconds: float = 2.0) -> None:
        while True:
            result = self.run_once()
            if not result.processed:
                time.sleep(max(float(poll_seconds), 0.25))
