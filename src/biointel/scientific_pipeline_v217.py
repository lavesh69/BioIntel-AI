from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import uuid4

from biointel.engine_platform_v196.state import EngineStateStore

_SECRET = re.compile(r"(?i)(token|secret|password|api[_-]?key|authorization)")
_SAFE_OUTPUT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,240}$")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class PipelineSpec:
    workflow_id: str
    engine: str
    command: tuple[str, ...]
    outputs: Mapping[str, str]
    timeout_seconds: int = 900
    minimum_input_bytes: int = 1
    minimum_output_bytes: int = 1


@dataclass(frozen=True)
class StageEvidence:
    stage: str
    status: str
    started_at_utc: str
    finished_at_utc: str
    details: dict[str, Any]


@dataclass(frozen=True)
class PipelineResult:
    run_id: str
    workflow_id: str
    engine: str
    passed: bool
    workspace: str
    stages: tuple[StageEvidence, ...]
    parsed_results: dict[str, Any]
    provenance_path: str
    report_path: str
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["stages"] = [asdict(item) for item in self.stages]
        payload["errors"] = list(self.errors)
        return payload


class QualifiedPipelineExecutor:
    """Run native scientific commands only after target-machine qualification.

    Commands are argument arrays and execute with shell=False. Every run records
    input hashes, QC, executable identity, output hashes, parsed results, provenance
    and a machine-readable report in an isolated workspace.
    """

    def __init__(
        self,
        store: EngineStateStore,
        workspace_root: str | Path,
        *,
        base_environment: Mapping[str, str] | None = None,
    ) -> None:
        self.store = store
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        source = dict(os.environ if base_environment is None else base_environment)
        self.environment = {
            key: value
            for key, value in source.items()
            if not _SECRET.search(key)
        }
        self.environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})

    @staticmethod
    def _safe_output(workspace: Path, relative: str) -> Path:
        normalized = str(relative).replace("\\", "/")
        if not _SAFE_OUTPUT.fullmatch(normalized) or normalized.startswith("/"):
            raise ValueError(f"Unsafe output path: {relative}")
        target = (workspace / normalized).resolve()
        try:
            target.relative_to(workspace)
        except ValueError as exc:
            raise ValueError(f"Output escapes workspace: {relative}") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def _expand_command(
        template: tuple[str, ...],
        *,
        executable: Path,
        workspace: Path,
        inputs: Mapping[str, Path],
        outputs: Mapping[str, Path],
    ) -> tuple[str, ...]:
        if not template:
            raise ValueError("Pipeline command is empty.")
        replacements = {
            "{executable}": str(executable),
            "{workspace}": str(workspace),
            **{f"{{input:{key}}}": str(value) for key, value in inputs.items()},
            **{f"{{output:{key}}}": str(value) for key, value in outputs.items()},
        }
        expanded: list[str] = []
        for raw in template:
            value = str(raw)
            for marker, replacement in replacements.items():
                value = value.replace(marker, replacement)
            if any(character in value for character in ("\x00", "\r", "\n")):
                raise ValueError("Command contains an unsafe control character.")
            if re.search(r"\{(?:input|output):[^}]+\}", value):
                raise ValueError(f"Unresolved command placeholder: {value}")
            expanded.append(value)
        if Path(expanded[0]).expanduser().resolve() != executable:
            raise ValueError("The first command argument must be the qualified executable.")
        return tuple(expanded)

    def run(
        self,
        spec: PipelineSpec,
        input_files: Mapping[str, str | Path],
        *,
        parser: Callable[[Mapping[str, Path]], Mapping[str, Any]] | None = None,
        extra_environment: Mapping[str, str] | None = None,
    ) -> PipelineResult:
        engine = self.store.get_engine(spec.engine)
        if not engine or not bool(engine.get("qualified")) or engine.get("state") != "qualified-ready":
            raise PermissionError(f"Engine '{spec.engine}' is not target-machine qualified.")
        executable = Path(str(engine.get("executable", ""))).expanduser().resolve()
        if not executable.is_file():
            raise FileNotFoundError(f"Qualified executable is missing: {executable}")
        actual_executable_hash = sha256_file(executable)
        if actual_executable_hash != str(engine.get("executable_sha256", "")).lower():
            raise PermissionError("Qualified executable hash changed after qualification.")

        inputs = {str(key): Path(value).expanduser().resolve() for key, value in input_files.items()}
        if not inputs:
            raise ValueError("At least one raw input is required.")
        for key, path in inputs.items():
            if not path.is_file():
                raise FileNotFoundError(f"Input '{key}' is missing: {path}")

        run_id = "pipeline-" + uuid4().hex
        workspace = (self.workspace_root / run_id).resolve()
        workspace.mkdir(parents=True)
        outputs = {
            str(key): self._safe_output(workspace, str(relative))
            for key, relative in spec.outputs.items()
        }
        command = self._expand_command(
            spec.command,
            executable=executable,
            workspace=workspace,
            inputs=inputs,
            outputs=outputs,
        )
        operation_id = "operation-" + uuid4().hex
        self.store.start_operation(
            operation_id,
            "scientific-pipeline",
            engine=spec.engine,
            request={"run_id": run_id, "workflow_id": spec.workflow_id},
        )

        stages: list[StageEvidence] = []
        errors: list[str] = []
        parsed: dict[str, Any] = {}
        provenance_path = workspace / "provenance.json"
        report_path = workspace / "pipeline_report.json"

        def record(stage: str, status: str, started: str, details: dict[str, Any]) -> None:
            stages.append(StageEvidence(stage, status, started, _utc_now(), details))

        try:
            started = _utc_now()
            input_rows = []
            for key, path in inputs.items():
                size = path.stat().st_size
                input_rows.append(
                    {"key": key, "path": str(path), "size_bytes": size, "sha256": sha256_file(path)}
                )
                if size < max(1, int(spec.minimum_input_bytes)):
                    errors.append(f"Input '{key}' is smaller than the workflow minimum.")
            record("raw_input", "passed" if not errors else "failed", started, {"files": input_rows})
            if errors:
                raise ValueError("; ".join(errors))

            started = _utc_now()
            duplicate_hashes = len({row["sha256"] for row in input_rows}) != len(input_rows)
            qc = {
                "input_count": len(input_rows),
                "total_bytes": sum(row["size_bytes"] for row in input_rows),
                "duplicate_content_detected": duplicate_hashes,
            }
            record("quality_control", "passed", started, qc)

            environment = dict(self.environment)
            for key, value in (extra_environment or {}).items():
                if _SECRET.search(str(key)):
                    raise ValueError(f"Secret-like environment key is not accepted: {key}")
                environment[str(key)] = str(value)
            started = _utc_now()
            completed = subprocess.run(
                list(command),
                cwd=workspace,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(1, min(int(spec.timeout_seconds), 86_400)),
                check=False,
                shell=False,
            )
            execution = {
                "return_code": int(completed.returncode),
                "command": list(command),
                "stdout": completed.stdout[-50_000:],
                "stderr": completed.stderr[-50_000:],
                "executable": str(executable),
                "executable_sha256": actual_executable_hash,
                "engine_version": str(engine.get("version", "")),
            }
            record(
                "native_engine_execution",
                "passed" if completed.returncode == 0 else "failed",
                started,
                execution,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"Native engine returned code {completed.returncode}.")

            started = _utc_now()
            output_rows = []
            for key, path in outputs.items():
                if not path.is_file():
                    errors.append(f"Expected output '{key}' is missing.")
                    continue
                size = path.stat().st_size
                if size < max(1, int(spec.minimum_output_bytes)):
                    errors.append(f"Output '{key}' is smaller than the workflow minimum.")
                output_rows.append(
                    {"key": key, "path": str(path), "size_bytes": size, "sha256": sha256_file(path)}
                )
            record("result_validation", "passed" if not errors else "failed", started, {"files": output_rows})
            if errors:
                raise ValueError("; ".join(errors))

            started = _utc_now()
            if parser is not None:
                value = parser(outputs)
                if not isinstance(value, Mapping):
                    raise TypeError("Pipeline parser must return a mapping.")
                parsed = json.loads(json.dumps(dict(value), default=str))
            else:
                parsed = {"outputs": output_rows}
            record("native_result_parsing", "passed", started, {"keys": sorted(parsed)})

            provenance = {
                "schema": "biointel.scientific-pipeline-provenance.v217",
                "run_id": run_id,
                "workflow_id": spec.workflow_id,
                "engine": spec.engine,
                "qualified_engine": True,
                "executable": str(executable),
                "executable_sha256": actual_executable_hash,
                "input_files": input_rows,
                "output_files": output_rows,
                "command": list(command),
                "generated_at_utc": _utc_now(),
            }
            provenance_path.write_text(
                json.dumps(provenance, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            record(
                "provenance",
                "passed",
                _utc_now(),
                {"path": str(provenance_path), "sha256": sha256_file(provenance_path)},
            )
        except Exception as exc:
            if str(exc) not in errors:
                errors.append(str(exc))

        passed = not errors
        result = PipelineResult(
            run_id=run_id,
            workflow_id=spec.workflow_id,
            engine=spec.engine,
            passed=passed,
            workspace=str(workspace),
            stages=tuple(stages),
            parsed_results=parsed,
            provenance_path=str(provenance_path) if provenance_path.is_file() else "",
            report_path=str(report_path),
            errors=tuple(errors),
        )
        report_path.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        self.store.finish_operation(
            operation_id,
            "completed" if passed else "failed",
            {"run_id": run_id, "report_path": str(report_path), "errors": errors},
        )
        return result
