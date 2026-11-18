from __future__ import annotations

import importlib.util
import os
from typing import Any

import pandas as pd

from .catalog import PRODUCTION_SERVICES


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def production_service_status(*, include_network_probe: bool = False) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in PRODUCTION_SERVICES:
        package = str(item["package"])
        environment = str(item["environment"])
        configured_value = os.environ.get(environment, "").strip()
        package_available = importlib.util.find_spec(package) is not None
        configured = bool(configured_value)
        if item["service"] == "crdt":
            configured = _truthy(configured_value)
        state = "ready-for-configuration" if package_available else "optional-package-missing"
        if package_available and configured:
            state = "configured-unprobed"
        rows.append(
            {
                **item,
                "package_available": package_available,
                "configured": configured,
                "network_probe_performed": False,
                "healthy": False,
                "state": state,
                "note": "Network probing is opt-in and is not performed by default." if not include_network_probe else "Network probe adapters are provider-specific and remain disabled until credentials are supplied.",
            }
        )
    return pd.DataFrame(rows)
