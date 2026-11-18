"""Small deterministic helpers shared by Education demo generators."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .manifest import DEMO_SEED_VERSION, DEMO_TIMESTAMP


def stable_id(prefix: str, *parts: object) -> str:
    """Return a readable stable identifier with a collision-resistant suffix."""
    source = ":".join(str(part).strip().lower() for part in parts)
    slug = re.sub(r"[^a-z0-9]+", "-", source).strip("-")[:32] or "record"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:10]
    return f"demo-{prefix}-{slug}-{digest}"


def synthetic_metadata(
    scenario: str,
    institution_id: str = "",
    persona_id: str = "",
) -> dict[str, Any]:
    """Return the permanent metadata contract required on synthetic records."""
    return {
        "is_demo": True,
        "data_origin": "synthetic_demo",
        "demo_scenario": scenario,
        "seed_version": DEMO_SEED_VERSION,
        "created_by_demo_seed": True,
        "demo_institution_id": institution_id,
        "demo_persona_id": persona_id,
        "created_at": DEMO_TIMESTAMP,
        "updated_at": DEMO_TIMESTAMP,
    }
