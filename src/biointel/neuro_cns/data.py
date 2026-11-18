from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=4)
def _load_json(name: str) -> dict[str, Any]:
    path = project_root() / "data" / "neuro_cns" / name
    return json.loads(path.read_text(encoding="utf-8"))


def target_registry() -> dict[str, Any]:
    return _load_json("target_registry_v1.json")


def side_effect_map() -> dict[str, Any]:
    return _load_json("side_effect_map_v1.json")


def targets() -> list[dict[str, Any]]:
    return list(target_registry().get("targets", []))


def target_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in targets():
        for token in (row.get("gene"), row.get("uniprot"), row.get("name")):
            if token:
                index[str(token).strip().upper()] = row
    return index
