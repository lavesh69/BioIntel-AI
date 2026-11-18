from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from biointel.shiro.integrations.evidence import NormalizedEvidence


def normalize_module_result(
    module_id: str,
    analysis_id: str,
    summary: str,
    *,
    parameters: Mapping[str, Any] | None = None,
    quality_control: Mapping[str, Any] | None = None,
    result_rows: Sequence[Mapping[str, Any]] = (),
    synthetic: bool = False,
) -> NormalizedEvidence:
    clean_module = module_id.strip()
    clean_analysis = analysis_id.strip()
    if not clean_module or not clean_analysis:
        raise ValueError("Module ID and analysis ID are required.")
    bounded_rows = [dict(row) for row in result_rows[:100]]
    payload = {
        "module_id": clean_module,
        "analysis_id": clean_analysis,
        "summary": summary.strip(),
        "parameters": dict(parameters or {}),
        "quality_control": dict(quality_control or {}),
        "selected_result_rows": bounded_rows,
        "row_limit": 100,
        "raw_results_included": False,
    }
    return NormalizedEvidence(
        filename=f"module-{clean_module}-{clean_analysis}.json",
        content=json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
        source_type="module_result",
        metadata={
            "module_id": clean_module, "analysis_id": clean_analysis,
            "adapter": "shiro-module-result-v1", "selected_rows": len(bounded_rows),
        },
        synthetic=synthetic,
    )