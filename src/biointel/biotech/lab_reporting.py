from __future__ import annotations

import hashlib
import io
import json
import math
import platform
import zipfile
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from biointel import __version__

FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, pd.DataFrame):
        return value.where(pd.notna(value), None).to_dict(orient="records")
    if isinstance(value, pd.Series):
        return value.where(pd.notna(value), None).tolist()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def dataframe_sha256(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_lab_run_bundle(
    *,
    workflow: str,
    input_frame: pd.DataFrame,
    outputs: dict[str, Any],
    parameters: dict[str, Any],
    recommendations: list[str] | None = None,
    source_filename: str = "input.csv",
) -> bytes:
    """Build a deterministic, checksum-bound laboratory analysis bundle."""

    files: dict[str, bytes] = {}
    input_name = f"inputs/{source_filename.rsplit('/', 1)[-1]}"
    files[input_name] = input_frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    output_index: list[dict[str, Any]] = []
    for name, value in sorted(outputs.items()):
        safe_name = "".join(character if character.isalnum() or character in "-_" else "_" for character in str(name)).strip("_") or "output"
        if isinstance(value, pd.DataFrame):
            path = f"outputs/{safe_name}.csv"
            payload = value.to_csv(index=False, lineterminator="\n").encode("utf-8")
            rows = int(len(value))
        else:
            path = f"outputs/{safe_name}.json"
            payload = json.dumps(_json_safe(value), indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
            rows = None
        files[path] = payload
        output_index.append({"name": name, "path": path, "sha256": hashlib.sha256(payload).hexdigest(), "rows": rows})
    manifest = {
        "schema": "biointel.lab_run_bundle.v1",
        "workflow": str(workflow),
        "created_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "input": {
            "path": input_name,
            "sha256": hashlib.sha256(files[input_name]).hexdigest(),
            "rows": int(len(input_frame)),
            "columns": list(map(str, input_frame.columns)),
        },
        "parameters": _json_safe(parameters),
        "outputs": output_index,
        "recommendations": list(recommendations or []),
        "software": {
            "biointel_ai": __version__,
            "python": platform.python_version(),
        },
        "scientific_boundary": "Research analytics only; assay validation, instrument qualification and regulated release remain laboratory responsibilities.",
    }
    manifest_payload = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
    files["manifest.json"] = manifest_payload
    checksums = "\n".join(f"{hashlib.sha256(payload).hexdigest()}  {path}" for path, payload in sorted(files.items())) + "\n"
    files["SHA256SUMS.txt"] = checksums.encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, payload in sorted(files.items()):
            info = zipfile.ZipInfo(path, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, payload)
    return buffer.getvalue()
