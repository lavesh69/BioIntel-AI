from __future__ import annotations

import hashlib
import math
import re
import struct
from collections import Counter
from typing import Iterable

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]{1,}")


def tokens(text: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(str(text))]


def hashed_embedding(text: str, dimensions: int = 384) -> list[float]:
    if dimensions < 64 or dimensions > 4096:
        raise ValueError("Embedding dimensions must be between 64 and 4096.")
    values = [0.0] * dimensions
    words = tokens(text)
    features: list[str] = list(words)
    features.extend(f"{a}::{b}" for a, b in zip(words, words[1:]))
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
        index = int.from_bytes(digest[:8], "big") % dimensions
        sign = 1.0 if digest[8] & 1 else -1.0
        weight = 1.0 + min(3.0, len(feature) / 24.0)
        values[index] += sign * weight
    norm = math.sqrt(sum(value * value for value in values))
    if norm:
        values = [value / norm for value in values]
    return values


def pack_vector(values: Iterable[float]) -> bytes:
    vector = list(values)
    return struct.pack(f"<{len(vector)}f", *vector)


def unpack_vector(blob: bytes, dimensions: int) -> list[float]:
    if len(blob) != dimensions * 4:
        raise ValueError("Stored vector length does not match index dimensions.")
    return list(struct.unpack(f"<{dimensions}f", blob))


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def bm25_scores(query: str, documents: list[str], *, k1: float = 1.5, b: float = 0.75) -> list[float]:
    query_terms = list(dict.fromkeys(tokens(query)))
    if not query_terms or not documents:
        return [0.0] * len(documents)
    doc_tokens = [tokens(doc) for doc in documents]
    lengths = [len(row) for row in doc_tokens]
    average = sum(lengths) / max(1, len(lengths))
    counters = [Counter(row) for row in doc_tokens]
    df = Counter(term for term in query_terms for counts in counters if counts.get(term))
    count = len(documents)
    results: list[float] = []
    for length, counts in zip(lengths, counters):
        score = 0.0
        for term in query_terms:
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            inverse = math.log(1.0 + (count - df[term] + 0.5) / (df[term] + 0.5))
            denominator = frequency + k1 * (1 - b + b * length / max(1.0, average))
            score += inverse * (frequency * (k1 + 1)) / denominator
        results.append(score)
    maximum = max(results, default=0.0)
    return [score / maximum if maximum else 0.0 for score in results]
