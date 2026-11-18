from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from biointel import __version__


def json_safe(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return {"type": "dataframe", "rows": int(len(value)), "columns": [str(column) for column in value.columns]}
    if isinstance(value, pd.Series):
        return value.to_list()
    if isinstance(value, np.ndarray):
        return {"type": "ndarray", "shape": list(value.shape), "dtype": str(value.dtype)}
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def build_result_bundle(feature_key: str, result: dict[str, Any], *, release: str = __version__) -> bytes:
    if not feature_key.strip() or not isinstance(result, dict):
        raise ValueError("A feature key and result mapping are required.")
    buffer = io.BytesIO()
    manifest: dict[str, Any] = {
        "schema": "biointel.feature-result-bundle.v209.v1",
        "feature_key": feature_key,
        "release": release,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_kind": result.get("_run_provenance", {}).get("source_kind", "unknown") if isinstance(result.get("_run_provenance"), dict) else "unknown",
        "scientific_boundary": result.get("scientific_boundary", "Research-only output."),
        "clinical_release_eligible": False,
        "files": [],
    }
    metadata: dict[str, Any] = {}
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for key, value in sorted(result.items()):
            safe_key = "".join(character if character.isalnum() or character in "-_" else "-" for character in str(key))
            if isinstance(value, pd.DataFrame):
                name = f"tables/{safe_key}.csv"
                archive.writestr(name, value.to_csv(index=False).encode("utf-8"))
                manifest["files"].append({"name": name, "kind": "table", "rows": len(value), "columns": len(value.columns)})
            elif isinstance(value, np.ndarray):
                name = f"arrays/{safe_key}.npy"
                array_buffer = io.BytesIO()
                np.save(array_buffer, value, allow_pickle=False)
                archive.writestr(name, array_buffer.getvalue())
                manifest["files"].append({"name": name, "kind": "array", "shape": list(value.shape), "dtype": str(value.dtype)})
            else:
                metadata[str(key)] = json_safe(value)
        archive.writestr("metadata.json", json.dumps(metadata, indent=2, ensure_ascii=False, default=str).encode("utf-8"))
        manifest["files"].append({"name": "metadata.json", "kind": "metadata"})
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False, default=str).encode("utf-8"))
        archive.writestr(
            "README.md",
            (
                f"# BioIntel AI result bundle — {feature_key}\n\n"
                "This archive contains locally calculated research-software outputs, parameters and provenance. "
                "It is not clinical validation, regulatory approval, a diagnostic report or proof of online evidence.\n"
            ).encode("utf-8"),
        )
    return buffer.getvalue()


__all__ = ["json_safe", "build_result_bundle"]
