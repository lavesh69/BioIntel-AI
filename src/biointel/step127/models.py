from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

StageMode = Literal["built-in", "adapter", "external-validation"]


@dataclass(frozen=True)
class StageSpec:
    key: str
    label: str
    mode: StageMode
    purpose: str
    tools: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    required_inputs: tuple[str, ...] = ()
    validation_gate: str = ""


@dataclass(frozen=True)
class ModuleSpec:
    key: str
    title: str
    domain: str
    page_path: str
    summary: str
    accepted_formats: tuple[str, ...]
    native_formats: tuple[str, ...]
    stages: tuple[StageSpec, ...]
    features_added: tuple[str, ...]
    statistical_requirements: tuple[str, ...]
    release_blockers: tuple[str, ...]
    evidence_boundary: str
    locked_source: bool = False
    python_packages: tuple[str, ...] = ()
    tags: tuple[str, ...] = field(default_factory=tuple)
