from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from biointel.native.engines import ENGINE_REGISTRY

from .packs import sha256_file
from .state import EngineStateStore, utc_now


@dataclass(frozen=True)
class CommandEvidence:
    command: tuple[str, ...]
    return_code: int
    stdout: str
    stderr: str
    passed: bool


@dataclass(frozen=True)
class QualificationResult:
    engine: str
    passed: bool
    executable: str
    executable_sha256: str
    version: str
    version_passed: bool
    positive: CommandEvidence
    negative: CommandEvidence
    output_hashes: tuple[dict[str, Any], ...]
    errors: tuple[str, ...]
    generated_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["positive"]["command"] = list(self.positive.command)
        payload["negative"]["command"] = list(self.negative.command)
        payload["output_hashes"] = list(self.output_hashes)
        payload["errors"] = list(self.errors)
        return payload


def _safe_command(command: list[str], executable: Path, workspace: Path) -> tuple[str, ...]:
    if not command:
        raise ValueError("Qualification command is empty.")
    expanded = []
    for index, value in enumerate(command):
        text = str(value).replace("{executable}", str(executable)).replace("{workspace}", str(workspace))
        if "\x00" in text or "\n" in text or "\r" in text:
            raise ValueError("Unsafe control character in qualification command.")
        expanded.append(text)
    first = Path(expanded[0]).expanduser().resolve()
    if first != executable.resolve():
        raise ValueError("Qualification command must execute the registered engine executable directly.")
    return tuple(expanded)


def _run(command: tuple[str, ...], cwd: Path, timeout_seconds: int, expected_codes: set[int]) -> CommandEvidence:
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1, min(timeout_seconds, 900)),
            check=False,
        )
        return CommandEvidence(command, int(completed.returncode), completed.stdout[-20000:], completed.stderr[-20000:], int(completed.returncode) in expected_codes)
    except subprocess.TimeoutExpired as exc:
        return CommandEvidence(command, -1, str(exc.stdout or "")[-20000:], str(exc.stderr or "")[-20000:], False)
    except OSError as exc:
        return CommandEvidence(command, -1, "", str(exc), False)


def qualify_engine(engine: str, spec: dict[str, Any], *, store: EngineStateStore, workspace_root: str | Path | None = None) -> QualificationResult:
    key = str(engine).lower()
    if key not in ENGINE_REGISTRY:
        raise KeyError(key)
    executable = Path(str(spec.get("executable", ""))).expanduser().resolve()
    errors: list[str] = []
    if not executable.is_file():
        raise ValueError("Qualification executable does not exist.")
    actual_hash = sha256_file(executable)
    expected_hash = str(spec.get("executable_sha256", ""))
    if not expected_hash or actual_hash != expected_hash:
        errors.append("Executable SHA-256 does not match the qualification specification.")
    version_regex = str(spec.get("version_regex", "")).strip()
    version_args = [str(value) for value in spec.get("version_args", ENGINE_REGISTRY[key].version_args)]
    timeout = int(spec.get("timeout_seconds", 60))
    version_evidence = _run(tuple([str(executable), *version_args]), executable.parent, timeout, {0})
    version_text = (version_evidence.stdout + "\n" + version_evidence.stderr).strip()
    version_passed = version_evidence.passed and bool(version_regex) and re.search(version_regex, version_text, flags=re.IGNORECASE) is not None
    if not version_passed:
        errors.append("Version probe or version-regex gate failed.")

    workspace_parent: str | None = None
    if workspace_root is not None:
        parent = Path(workspace_root).expanduser().resolve()
        parent.mkdir(parents=True, exist_ok=True)
        workspace_parent = str(parent)
    with tempfile.TemporaryDirectory(prefix=f"biointel-qualify-{key}-", dir=workspace_parent) as temporary:
        workspace = Path(temporary).resolve()
        positive_command = _safe_command([str(value) for value in spec.get("positive_command", [])], executable, workspace)
        negative_command = _safe_command([str(value) for value in spec.get("negative_command", [])], executable, workspace)
        positive = _run(positive_command, workspace, timeout, {int(value) for value in spec.get("positive_expected_codes", [0])})
        negative = _run(negative_command, workspace, timeout, {int(value) for value in spec.get("negative_expected_codes", [1])})
        if not positive.passed:
            errors.append("Positive fixture command failed.")
        if not negative.passed:
            errors.append("Negative-control command failed.")
        output_rows = []
        for item in spec.get("expected_outputs", []):
            relative = Path(str(item["path"]))
            output = (workspace / relative).resolve()
            try:
                output.relative_to(workspace)
            except ValueError as exc:
                raise ValueError("Qualification output escapes workspace.") from exc
            if not output.is_file():
                errors.append(f"Expected output missing: {relative.as_posix()}")
                continue
            digest = sha256_file(output)
            expected = str(item.get("sha256", ""))
            passed = bool(expected) and digest == expected
            if not passed:
                errors.append(f"Expected output hash failed: {relative.as_posix()}")
            output_rows.append({"path": relative.as_posix(), "sha256": digest, "expected_sha256": expected, "passed": passed})

    passed = not errors
    result = QualificationResult(
        engine=key,
        passed=passed,
        executable=str(executable),
        executable_sha256=actual_hash,
        version=version_text[:2000],
        version_passed=version_passed,
        positive=positive,
        negative=negative,
        output_hashes=tuple(output_rows),
        errors=tuple(errors),
        generated_at_utc=utc_now(),
    )
    store.record_evidence(key, "target-machine-qualification", "passed" if passed else "failed", sha256=hashlib.sha256(json.dumps(result.to_dict(), sort_keys=True).encode("utf-8")).hexdigest(), details=result.to_dict())
    current = store.get_engine(key) or {}
    store.upsert_engine(
        key,
        state="qualified-ready" if passed else "qualification-failed",
        backend=str(current.get("backend", "registered-native-installation")),
        version=version_text[:2000],
        executable=str(executable),
        executable_sha256=actual_hash,
        pack_id=str(current.get("pack_id", "")),
        qualified=passed,
        last_probe_utc=utc_now(),
        message="Target-machine qualification passed" if passed else "; ".join(errors),
    )
    return result
