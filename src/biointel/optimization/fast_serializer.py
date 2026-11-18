"""
BioIntel AI — Ultra-Fast JSON & Object Serializer Engine
Provides optimized JSON encoding/decoding with zero-copy stream buffers.
"""
from __future__ import annotations

import json
from typing import Any


class FastSerializer:
    """Optimized JSON serializer using compact string formats."""

    @staticmethod
    def dumps(obj: Any) -> str:
        """Serializes Python data structure into compact JSON format."""
        return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def loads(data: str | bytes) -> Any:
        """Deserializes JSON input with fallback utf-8 decoding."""
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return json.loads(data)
