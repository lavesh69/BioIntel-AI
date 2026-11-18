from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Protocol, Sequence

from biointel.shiro.exceptions import EmbeddingModelUnavailableError, IndexMismatchError

_TOKEN = re.compile(r"[^\W_]+(?:[-.:/][^\W_]+)*", re.UNICODE)


class EmbeddingProvider(Protocol):
    model_name: str
    model_version: str
    dimension: int
    preprocessing_version: str

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        ...


class HashEmbeddingProvider:
    """Deterministic, dependency-free local embeddings; no model download or network use."""

    model_name = "hash-multilingual"
    model_version = "1"
    preprocessing_version = "shiro-normalize-v1"

    def __init__(self, dimension: int = 384) -> None:
        if dimension < 64:
            raise ValueError("Embedding dimension must be at least 64.")
        self.dimension = int(dimension)

    @staticmethod
    def _features(text: str) -> list[str]:
        normalized = " ".join(text.casefold().split())
        tokens = _TOKEN.findall(normalized)
        features = list(tokens)
        for token in tokens:
            if len(token) >= 5:
                features.extend(f"#{token[index:index + 3]}" for index in range(len(token) - 2))
        return features

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        rows: list[tuple[float, ...]] = []
        for text in texts:
            vector = [0.0] * self.dimension
            for feature in self._features(text):
                digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
                index = int.from_bytes(digest[:8], "little") % self.dimension
                sign = 1.0 if digest[8] & 1 else -1.0
                vector[index] += sign
            norm = math.sqrt(sum(value * value for value in vector))
            rows.append(tuple(value / norm for value in vector) if norm else tuple(vector))
        return rows


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))

class LocalSentenceTransformerEmbeddingProvider:
    """Optional local multilingual embeddings; never downloads a model unless explicitly allowed."""

    model_version = "sentence-transformers-local-v1"
    preprocessing_version = "shiro-normalize-v1"

    def __init__(self, model_name: str, *, allow_downloads: bool = False) -> None:
        if not model_name.strip():
            raise EmbeddingModelUnavailableError("Set SHIRO_EMBEDDING_MODEL to a local sentence-transformers model name or path.")
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingModelUnavailableError(
                "sentence-transformers is not installed. Install it explicitly, then place/download the model yourself; Shiro will not download it silently."
            ) from exc
        try:
            self._model: Any = SentenceTransformer(model_name, local_files_only=not allow_downloads)
        except Exception as exc:
            mode = "Explicit downloads were allowed." if allow_downloads else "Silent model downloads are disabled."
            raise EmbeddingModelUnavailableError(f"Local embedding model is unavailable: {model_name}. {mode}") from exc
        self.model_name = model_name
        self.dimension = int(self._model.get_sentence_embedding_dimension())
        if self.dimension < 64:
            raise IndexMismatchError("The configured embedding model returned an invalid vector dimension.")

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        try:
            values = self._model.encode(
                list(texts), batch_size=32, normalize_embeddings=True,
                show_progress_bar=False, convert_to_numpy=True,
            )
        except Exception as exc:
            raise EmbeddingModelUnavailableError("The local embedding model failed while embedding a batch.") from exc
        rows = [tuple(float(value) for value in row) for row in values]
        if any(len(row) != self.dimension for row in rows):
            raise IndexMismatchError("Embedding dimensions changed during indexing; rebuild was stopped.")
        return rows


def build_embedding_provider(provider: str, model_name: str, dimension: int, *, allow_downloads: bool = False) -> EmbeddingProvider:
    selected = provider.strip().casefold()
    if selected in {"local", "hash", "hash-local"}:
        return HashEmbeddingProvider(dimension)
    if selected in {"sentence-transformers", "sentence_transformers"}:
        return LocalSentenceTransformerEmbeddingProvider(model_name, allow_downloads=allow_downloads)
    raise EmbeddingModelUnavailableError(f"Unsupported embedding provider: {provider}")