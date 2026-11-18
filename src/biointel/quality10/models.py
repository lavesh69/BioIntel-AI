from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ArtifactRecord:
    artifact_id: str
    step_id: str
    role: str
    path: str
    sha256: str
    size_bytes: int
    media_type: str = "application/octet-stream"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StepExecutionRecord:
    run_id: str
    step_id: str
    block: str
    status: str
    started_at: str
    finished_at: str
    duration_seconds: float
    attempt: int
    depends_on: list[str] = field(default_factory=list)
    command: list[str] = field(default_factory=list)
    exit_code: int | None = None
    stdout_path: str = ""
    stderr_path: str = ""
    result_path: str = ""
    error: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    skipped_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WorkflowExecutionRecord:
    run_id: str
    workflow_name: str
    workflow_sha256: str
    status: str
    started_at: str
    finished_at: str
    duration_seconds: float
    output_directory: str
    resumed: bool
    implementation_readiness: float
    scientific_evidence_score: float
    steps: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    environment: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
