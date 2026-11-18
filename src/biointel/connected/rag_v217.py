from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

import numpy as np

_CITATION = re.compile(r"\[EVIDENCE:([A-Za-z0-9._:-]+)\]")


@dataclass(frozen=True)
class EvidenceChunk:
    evidence_id: str
    text: str
    source_uri: str
    source_sha256: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RetrievedEvidence:
    chunk: EvidenceChunk
    score: float


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    evidence: tuple[RetrievedEvidence, ...]
    model_id: str
    qualification_id: str
    citations: tuple[str, ...]


class EmbeddingProvider(Protocol):
    model_id: str
    qualification_id: str

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        ...


class GeneratorProvider(Protocol):
    model_id: str
    qualification_id: str

    def generate(self, *, question: str, evidence_context: str) -> str:
        ...


class VectorEvidenceIndex:
    def __init__(
        self,
        chunks: Sequence[EvidenceChunk],
        vectors: np.ndarray,
        *,
        embedding_model_id: str,
        qualification_id: str,
    ) -> None:
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[0] != len(chunks) or not chunks:
            raise ValueError("Vector matrix must contain one row per evidence chunk.")
        if not qualification_id.strip():
            raise PermissionError("Embedding index requires qualification evidence.")
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if np.any(norms <= 0):
            raise ValueError("Embedding vectors must be non-zero.")
        self.chunks = tuple(chunks)
        self.vectors = matrix / norms
        self.embedding_model_id = embedding_model_id
        self.qualification_id = qualification_id

    @classmethod
    def build(
        cls,
        chunks: Sequence[EvidenceChunk],
        provider: EmbeddingProvider,
    ) -> "VectorEvidenceIndex":
        if not provider.qualification_id.strip():
            raise PermissionError("Embedding provider is not qualified.")
        vectors = provider.embed([chunk.text for chunk in chunks])
        return cls(
            chunks,
            vectors,
            embedding_model_id=provider.model_id,
            qualification_id=provider.qualification_id,
        )

    def search(self, query_vector: np.ndarray, *, limit: int = 8) -> tuple[RetrievedEvidence, ...]:
        query = np.asarray(query_vector, dtype=np.float32).reshape(-1)
        if query.shape[0] != self.vectors.shape[1]:
            raise ValueError("Query embedding dimension does not match the evidence index.")
        norm = float(np.linalg.norm(query))
        if norm <= 0:
            raise ValueError("Query embedding is empty.")
        scores = self.vectors @ (query / norm)
        indices = np.argsort(-scores)[: max(1, min(int(limit), 50))]
        return tuple(
            RetrievedEvidence(self.chunks[int(index)], float(scores[int(index)]))
            for index in indices
        )


class EvidenceGroundedRag:
    def __init__(
        self,
        index: VectorEvidenceIndex,
        embedding_provider: EmbeddingProvider,
        generator: GeneratorProvider,
    ) -> None:
        if not embedding_provider.qualification_id.strip():
            raise PermissionError("Embedding provider is not qualified.")
        if embedding_provider.model_id != index.embedding_model_id:
            raise ValueError("Embedding provider does not match the evidence index.")
        if not generator.qualification_id.strip():
            raise PermissionError("Generator is not qualified.")
        self.index = index
        self.embedding_provider = embedding_provider
        self.generator = generator

    def answer(self, question: str, *, limit: int = 8) -> RagAnswer:
        clean = " ".join(question.split())
        if not clean:
            raise ValueError("A question is required.")
        query = self.embedding_provider.embed([clean])
        retrieved = self.index.search(query[0], limit=limit)
        context = "\n\n".join(
            f"[EVIDENCE:{item.chunk.evidence_id}]\n"
            f"Source: {item.chunk.source_uri}\n"
            f"Content: {item.chunk.text}"
            for item in retrieved
        )
        answer = self.generator.generate(question=clean, evidence_context=context).strip()
        citations = tuple(dict.fromkeys(_CITATION.findall(answer)))
        allowed = {item.chunk.evidence_id for item in retrieved}
        invalid = sorted(set(citations) - allowed)
        if invalid:
            raise ValueError("Generator cited evidence outside the retrieved context: " + ", ".join(invalid))
        if not citations:
            raise ValueError("Generator response contains no evidence citations.")
        return RagAnswer(
            answer=answer,
            evidence=retrieved,
            model_id=self.generator.model_id,
            qualification_id=self.generator.qualification_id,
            citations=citations,
        )


def evidence_only_summary(
    question: str,
    evidence: Sequence[RetrievedEvidence],
) -> str:
    lines = [f"Evidence retrieved for: {question}", ""]
    for item in evidence:
        lines.append(
            f"- [EVIDENCE:{item.chunk.evidence_id}] {item.chunk.text} ({item.chunk.source_uri})"
        )
    lines.append("")
    lines.append("No generative interpretation was run.")
    return "\n".join(lines)
