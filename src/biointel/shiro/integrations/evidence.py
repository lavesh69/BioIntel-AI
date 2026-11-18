from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NormalizedEvidence:
    filename: str
    content: bytes
    source_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    internal: bool = True
    external: bool = False
    synthetic: bool = False
    confidential: bool = True