from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .catalog import module_runtime_path_matrix
from .reference_kits import development_reference_readiness
from .validation_protocols import validation_protocol_readiness


def _project_root(metadata: dict[str, Any]) -> Path:
    value = str(metadata.get("project_root") or "").strip()
    if value:
        return Path(value).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def apply_step161_operational_assurance(
    *,
    module_key: str,
    metadata: dict[str, Any],
    tables: dict[str, pd.DataFrame],
    checks: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> None:
    root = _project_root(metadata)
    runtime = module_runtime_path_matrix(module_key, detect_runtime=False)
    references = development_reference_readiness(root, [module_key])
    protocols = validation_protocol_readiness(root, [module_key])

    tables.setdefault("step161_execution_paths", runtime)
    tables.setdefault("step161_development_reference_kits", references)
    tables.setdefault("step161_external_validation_protocol", protocols)

    runtime_ready = bool(not runtime.empty and runtime["operational_path_ready"].astype(bool).all())
    reference_ready = bool(references.empty or references["development_qualified"].astype(bool).all())
    protocol_ready = bool(not protocols.empty and protocols["protocol_ready"].astype(bool).all())

    checks.append(
        {
            "check": "Step 161 managed execution paths",
            "status": "pass" if runtime_ready else "fail",
            "detail": f"{int(runtime['operational_path_ready'].astype(bool).sum())}/{len(runtime)} execution paths have protected provisioning and execution contracts. Installed-tool detection remains separate.",
        }
    )
    checks.append(
        {
            "check": "Step 161 development reference kits",
            "status": "pass" if reference_ready else "fail",
            "detail": f"{int(references['development_qualified'].astype(bool).sum()) if not references.empty else 0}/{len(references)} checksum-verified development fixtures are available. They are blocked from production use.",
        }
    )
    checks.append(
        {
            "check": "Step 161 external validation protocol",
            "status": "pass" if protocol_ready else "fail",
            "detail": "A versioned independent/prospective validation protocol is present; external evidence and reviewer approval are not inferred.",
        }
    )

    metrics.extend(
        [
            {"metric": "step161_execution_paths_ready", "value": int(runtime["operational_path_ready"].astype(bool).sum()), "unit": "paths"},
            {"metric": "step161_development_references_ready", "value": int(references["development_qualified"].astype(bool).sum()) if not references.empty else 0, "unit": "assets"},
            {"metric": "step161_validation_protocol_ready", "value": int(protocol_ready), "unit": "protocol"},
            {"metric": "step161_software_upgrade_score", "value": 10.0 if runtime_ready and reference_ready and protocol_ready else 0.0, "unit": "score"},
        ]
    )


__all__ = ["apply_step161_operational_assurance"]
