from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, Sequence

from biointel.shiro.models import Citation, LanguageInfo, RetrievalResult, SourceRecord


class GenerationProvider(Protocol):
    name: str
    model: str
    external: bool

    def generate(
        self,
        question: str,
        evidence: Sequence[RetrievalResult],
        citations: Sequence[Citation],
        language: LanguageInfo,
        *,
        history: Sequence[dict[str, Any]] = (),
        attachments: Sequence[SourceRecord] = (),
        cancelled: Callable[[], bool] | None = None,
    ) -> str:
        ...
